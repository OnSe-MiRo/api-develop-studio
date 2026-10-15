"""OAuth encrypted transient state, rotation, one-time PKCE and context scope."""
import os
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from api_test.database import RequestContext
from api_test.oauth_vault import Lease, OAuthVaultError, Vault
from api_test.request_profiles import normalize_profiles
from api_test.project_variables import ProjectVariableError, encrypt_secret


class OAuthVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "studio.db"
        self.env = patch.dict(os.environ, {
            "STUDIO_DB_PATH": str(self.path), "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "",
            "API_TEST_ENCRYPTION_KEY": Fernet.generate_key().decode(), "API_TEST_ENCRYPTION_URL": "",
            "LOCAL_SERVER": "true",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.vault = Vault(self.path)
        self.identity = self.vault.identity("project.json", "", "oauth")
        self.digest = "a" * 64

    def test_named_profile_requires_encrypted_secret_reference_and_public_code_has_none(self):
        secret = encrypt_secret("synthetic-client-secret")
        common = {"name": "P", "base_url": "https://api.example.test", "variables": {
            "plain": {}, "secret": {"CLIENT": secret}}, "environments": {},
            "auth_profiles": {"service": {"type": "OAuth 2.0", "grantType": "client_credentials",
                "clientId": "client", "clientSecret": "{{project.CLIENT}}",
                "tokenUrl": "https://issuer.example.test/token", "clientAuthMethod": "basic", "scopes": ["read"]}}}
        self.assertEqual(normalize_profiles(common)["auth_profiles"]["service"]["scopes"], ["read"])
        public = {**common, "auth_profiles": {"login": {"type": "OAuth 2.0", "grantType": "authorization_code",
            "clientId": "public", "authorizationUrl": "https://issuer.example.test/authorize",
            "tokenUrl": "https://issuer.example.test/token", "clientAuthMethod": "none", "scopes": []}}}
        normalize_profiles(public)
        public["auth_profiles"]["login"]["clientSecret"] = ""
        with self.assertRaises(ProjectVariableError):
            normalize_profiles(public)
        common["auth_profiles"]["service"]["tokenUrl"] = "http://169.254.169.254/token"
        with self.assertRaises(ProjectVariableError):
            normalize_profiles(common)

    def test_access_ciphertext_cache_and_refresh_survive_access_expiry(self):
        with patch("api_test.oauth_vault.time.time", return_value=1000):
            lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
            self.assertIsInstance(lease, Lease)
            self.assertEqual(self.vault.finish(lease, {"token_type": "Bearer", "access_token": "access-one",
                "refresh_token": "refresh-one", "expires_in": 120}), "access-one")
            self.assertEqual(self.vault.acquire(self.identity, self.digest, "client_credentials"), "access-one")
        raw = self.path.read_bytes()
        self.assertNotIn(b"access-one", raw)
        self.assertNotIn(b"refresh-one", raw)
        with patch("api_test.oauth_vault.time.time", return_value=1121):
            self.assertTrue(self.vault.status(self.identity, self.digest)["canRefresh"])
            lease = self.vault.acquire(self.identity, self.digest, "authorization_code")
            self.assertEqual(lease.action, "refresh")
            self.assertEqual(lease.refresh_token, "refresh-one")
            self.vault.finish(lease, {"token_type": "Bearer", "access_token": "access-two",
                                      "refresh_token": "refresh-two", "expires_in": 120}, public_client=True)
        self.assertNotIn(b"access-two", self.path.read_bytes())
        self.assertNotIn(b"refresh-two", self.path.read_bytes())

    def test_expired_ciphertext_is_pruned_on_next_context_write(self):
        with patch("api_test.oauth_vault.time.time", return_value=1000):
            lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
            self.vault.finish(lease, {"token_type": "Bearer", "access_token": "short", "expires_in": 60})
        with patch("api_test.oauth_vault.time.time", return_value=2000):
            other = self.vault.identity("project.json", "", "another")
            self.vault.acquire(other, self.digest, "client_credentials")
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT profile FROM oauth_tokens ORDER BY profile").fetchall()
        self.assertEqual(rows, [("another",)])

    def test_manual_force_refresh_does_not_queue_rotating_duplicates(self):
        lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
        self.vault.finish(lease, {"token_type": "Bearer", "access_token": "first",
                                  "refresh_token": "rotation-one", "expires_in": 3600})
        refreshing = self.vault.acquire(self.identity, self.digest, "authorization_code", force=True)
        with self.assertRaises(OAuthVaultError):
            self.vault.acquire(self.identity, self.digest, "authorization_code", force=True)
        self.vault.finish(refreshing, {"token_type": "Bearer", "access_token": "second",
                                       "refresh_token": "rotation-two", "expires_in": 3600}, public_client=True)
        self.assertEqual(self.vault.acquire(self.identity, self.digest, "authorization_code"), "second")

    def test_expired_uncertain_refresh_lease_commits_deletion(self):
        with patch("api_test.oauth_vault.time.time", return_value=1000):
            lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
            self.vault.finish(lease, {"token_type": "Bearer", "access_token": "one", "refresh_token": "rotation",
                                      "expires_in": 3600})
        with patch("api_test.oauth_vault.time.time", return_value=1100):
            refresh = self.vault.acquire(self.identity, self.digest, "authorization_code", force=True)
            self.assertEqual(refresh.action, "refresh")
        with patch("api_test.oauth_vault.time.time", return_value=1140):
            with self.assertRaises(OAuthVaultError):
                self.vault.acquire(self.identity, self.digest, "authorization_code")
            self.assertFalse(self.vault.status(self.identity, self.digest)["connected"])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM oauth_tokens").fetchone()[0], 0)

    def test_disconnecting_during_callback_prevents_late_token_resurrection(self):
        state, cookie, verifier = self.vault.create_pending(self.identity, "provider", self.digest,
                                                            "http://127.0.0.1:123/api/oauth/callback/provider", "UA")
        self.assertNotIn(verifier.encode(), self.path.read_bytes())
        pending = self.vault.consume_pending(state, cookie, "provider", "UA")
        with self.assertRaises(OAuthVaultError):
            self.vault.consume_pending(state, cookie, "provider", "UA")
        self.vault.disconnect(self.identity)
        with self.assertRaises(OAuthVaultError):
            self.vault.finish(pending["lease"], {"token_type": "Bearer", "access_token": "late"})
        self.assertFalse(self.vault.status(self.identity, self.digest)["connected"])

    def test_workspace_user_scope_cannot_read_or_consume_other_state(self):
        other = RequestContext("other", "other-user")
        with self.vault.connection(write=True) as db, db:
            db.execute("INSERT INTO workspaces(id,name,created_at,updated_at,status) VALUES ('other','Other','x','x','active')")
            db.execute("INSERT INTO users(id,display_name,created_at,updated_at,status) VALUES ('other-user','Other','x','x','active')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at,status) VALUES ('other','other-user','owner','x','active')")
        second = Vault(self.path, other)
        identity = second.identity("other.json", "", "p")
        lease = second.acquire(identity, self.digest, "client_credentials")
        second.finish(lease, {"token_type": "Bearer", "access_token": "other-secret", "expires_in": 3600})
        state, cookie, _ = second.create_pending(identity, "provider", self.digest, "https://example.test/cb", "UA")
        with self.assertRaises(PermissionError):
            self.vault.status(identity, self.digest)
        with self.assertRaises(PermissionError):
            self.vault.acquire(identity, self.digest, "client_credentials")
        with self.assertRaises(OAuthVaultError):
            self.vault.consume_pending(state, cookie, "provider", "UA")
        self.assertTrue(second.status(identity, self.digest)["connected"])

    def test_invalid_token_and_public_refresh_without_rotation_are_rejected(self):
        lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
        with self.assertRaises(OAuthVaultError):
            self.vault.finish(lease, {"token_type": "Bearer", "access_token": "bad\r\nHeader"})
        with self.assertRaises(OAuthVaultError):
            self.vault.finish(lease, {"token_type": "Bearer", "access_token": "safe", "expires_in": True})
        self.vault.abort(lease)
        lease = self.vault.acquire(self.identity, self.digest, "client_credentials")
        self.vault.finish(lease, {"token_type": "Bearer", "access_token": "safe",
                                  "refresh_token": "first-refresh", "expires_in": 120})
        refresh = self.vault.acquire(self.identity, self.digest, "authorization_code", force=True)
        with self.assertRaises(OAuthVaultError):
            self.vault.finish(refresh, {"token_type": "Bearer", "access_token": "second"},
                              public_client=True)
        self.vault.abort(refresh)
        self.assertFalse(self.vault.status(self.identity, self.digest)["connected"])

if __name__ == "__main__":
    unittest.main()
