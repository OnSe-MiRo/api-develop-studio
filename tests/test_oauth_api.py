"""ASGI contract tests for saved OAuth profile issuance and browser callbacks."""
import base64
import hashlib
import logging
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

import react_server as studio
from api_test.collaboration_store import CollaborationStore
from api_test.database import RequestContext
from api_test.oauth_transport import OAuthTransportError


class OAuthApiTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.database = self.root / "studio.db"
        self.roots = {name: self.root / folder for name, folder in
                      (("projects", "projects"), ("cases", "case"), ("pipelines", "pipelines"))}
        for folder in self.roots.values():
            folder.mkdir()
        for name, value in {"ROOT": self.root, "PROJECT_ROOT": self.roots["projects"],
                            "CASE_ROOT": self.roots["cases"], "PIPELINE_ROOT": self.roots["pipelines"],
                            "WEB_DIST": self.root / "web"}.items():
            self.enterContext(patch.object(studio, name, value))
        self.enterContext(patch.dict(os.environ, {
            "STUDIO_DB_PATH": str(self.database),
            "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "",
            "STUDIO_OWNERSHIP_DB_PATH": str(self.root / "ownership.db"),
            "API_TEST_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "API_TEST_ENCRYPTION_URL": "", "LOCAL_SERVER": "true",
            "SKIP_OWNERSHIP_VERIFICATION": "true", "STUDIO_OAUTH_CALLBACK_ORIGIN": "",
        }))
        self.store = CollaborationStore(self.database, self.roots)
        self.store.initialize()
        self.enterContext(patch.object(studio, "collaboration_store", return_value=self.store))
        self.client = self.enterContext(TestClient(studio.app, base_url="http://127.0.0.1:8765"))
        self.logged_messages = []
        captured = self.logged_messages
        class Capture(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())
        handler = Capture()
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        self.addCleanup(root_logger.removeHandler, handler)
        self.service_profile = {
            "type": "OAuth 2.0", "grantType": "client_credentials", "clientId": "service-client",
            "clientSecret": "{{project.CLIENT}}", "tokenUrl": "https://issuer.example.test/token",
            "clientAuthMethod": "basic", "scopes": ["read,write"],
        }
        self.code_profile = {
            "type": "OAuth 2.0", "grantType": "authorization_code", "clientId": "public-client",
            "tokenUrl": "https://issuer.example.test/token",
            "authorizationUrl": "https://issuer.example.test/authorize",
            "clientAuthMethod": "none", "scopes": ["openid", "profile"],
        }
        self.project = {
            "name": "OAuth API", "base_url": "https://api.example.test",
            "variables": {"secret": {"CLIENT": {"value": "synthetic-client-secret"}}},
            "auth_profiles": {"service": self.service_profile, "login": self.code_profile},
            "environments": {"dev": {"base_url": "https://dev.example.test",
                                     "auth_profiles": {"service": {**self.service_profile, "clientId": "dev-client"}}}},
        }
        response = self.client.put("/api/projects/p.json", json=self.project)
        self.assertEqual(response.status_code, 200, response.text)
        self.profile_path = "/api/projects/p.json/oauth/profiles"

    def _authorize(self, name="login", environment=""):
        response = self.client.post(f"{self.profile_path}/{name}/authorize", json={"environment": environment})
        self.assertEqual(response.status_code, 200, response.text)
        authorization = response.json()
        query = parse_qs(urlsplit(authorization["authorizationUrl"]).query)
        provider_key = authorization["callbackUri"].rsplit("/", 1)[-1]
        return response, authorization, query, provider_key

    def _update_project(self, project):
        revision = self.client.get("/api/projects/p.json").json()["_storage"]
        response = self.client.put("/api/projects/p.json", json={**project, "_storage": revision})
        self.assertEqual(response.status_code, 200, response.text)

    def test_status_issue_environment_override_and_disconnect_are_metadata_only(self):
        common = self.client.get(f"{self.profile_path}/service")
        self.assertEqual(common.status_code, 200, common.text)
        self.assertEqual(common.json()["grantType"], "client_credentials")
        self.assertFalse(common.json()["connected"])
        self.assertEqual(set(common.json()), {"configured", "connected", "grantType", "expiresAt", "canRefresh", "callbackUri"})
        self.assertNotIn("synthetic-client-secret", common.text)
        calls = []

        def provider(url, fields, *, client_id, client_secret, method):
            calls.append((url, fields, client_id, client_secret, method))
            return {"token_type": "Bearer", "access_token": f"opaque-access-{len(calls)}", "expires_in": 3600}

        with patch("api_test.oauth_service.post_token_form", side_effect=provider):
            issued = self.client.post(f"{self.profile_path}/service/token", json={"environment": "dev", "action": "issue"})
            self.assertEqual(issued.status_code, 200, issued.text)
            self.assertTrue(issued.json()["connected"])
            self.assertEqual(calls[0][2], "dev-client")
            self.assertEqual(calls[0][1], {"grant_type": "client_credentials", "scope": "read,write"})
            self.assertEqual(calls[0][3], "synthetic-client-secret")
            self.assertEqual(calls[0][4], "basic")
            self.assertFalse(self.client.get(f"{self.profile_path}/service").json()["connected"])
            self.assertTrue(self.client.get(f"{self.profile_path}/service?environment=dev").json()["connected"])
            self.assertEqual(self.client.post(f"{self.profile_path}/service/token", json={"action": "refresh"}).status_code, 400)
        for response in (issued, self.client.get(f"{self.profile_path}/service?environment=dev")):
            self.assertNotIn("opaque-access", response.text)
            self.assertNotIn("synthetic-client-secret", response.text)
        self.assertNotIn("opaque-access", "\n".join(self.logged_messages))
        self.assertNotIn("synthetic-client-secret", "\n".join(self.logged_messages))
        disconnected = self.client.delete(f"{self.profile_path}/service?environment=dev")
        self.assertEqual(disconnected.status_code, 200, disconnected.text)
        self.assertFalse(disconnected.json()["connected"])
        self.assertFalse(self.client.get(f"{self.profile_path}/service?environment=dev").json()["connected"])

    def test_authorize_callback_pkce_binding_clean_redirect_and_replay(self):
        response, authorization, query, key = self._authorize()
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["client_id"], ["public-client"])
        self.assertEqual(query["scope"], ["openid profile"])
        self.assertEqual(query["redirect_uri"], [authorization["callbackUri"]])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=Lax", response.headers["set-cookie"])
        self.assertIn("Path=/api/oauth/callback/", response.headers["set-cookie"])
        self.assertNotIn("code_verifier", authorization["authorizationUrl"])
        self.assertNotIn("synthetic-client-secret", response.text)
        callback_path = f"/api/oauth/callback/{key}?state={query['state'][0]}&code=synthetic-code"
        exchange = []

        def provider(url, fields, *, client_id, client_secret, method):
            exchange.append((url, fields, client_id, client_secret, method))
            return {"token_type": "Bearer", "access_token": "code-access", "refresh_token": "code-refresh", "expires_in": 1800}

        with patch("api_test.oauth_service.post_token_form", side_effect=provider):
            callback = self.client.get(callback_path, follow_redirects=False)
        self.assertEqual(callback.status_code, 303, callback.text)
        self.assertEqual(callback.headers["location"], "/projects/settings?project=p")
        self.assertEqual(callback.headers["cache-control"], "no-store")
        self.assertEqual(callback.headers["referrer-policy"], "no-referrer")
        self.assertNotIn("synthetic-code", callback.text + callback.headers["location"])
        self.assertNotIn(query["state"][0], callback.text + callback.headers["location"])
        self.assertEqual(exchange[0][1]["grant_type"], "authorization_code")
        self.assertEqual(exchange[0][1]["code"], "synthetic-code")
        self.assertEqual(exchange[0][1]["redirect_uri"], authorization["callbackUri"])
        verifier = exchange[0][1]["code_verifier"]
        self.assertEqual(base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(), query["code_challenge"][0])
        self.assertIsNone(exchange[0][3])
        self.assertEqual(exchange[0][4], "none")
        self.assertTrue(self.client.get(f"{self.profile_path}/login").json()["connected"])
        self.assertNotIn("synthetic-code", "\n".join(self.logged_messages))
        self.assertNotIn("code-access", "\n".join(self.logged_messages))
        self.assertNotIn("code-refresh", "\n".join(self.logged_messages))
        replay = self.client.get(callback_path, follow_redirects=False)
        self.assertEqual(replay.status_code, 409, replay.text)
        self.assertNotIn("synthetic-code", replay.text)
        self.assertNotIn(query["state"][0], replay.text)

    def test_callback_rejects_wrong_cookie_agent_provider_expiry_and_profile_change(self):
        for mutation in ("cookie", "agent", "provider", "expired", "changed"):
            with self.subTest(mutation=mutation):
                _, _, query, key = self._authorize()
                state = query["state"][0]
                path = f"/api/oauth/callback/{key}?state={state}&code=synthetic-code"
                headers = {}
                if mutation == "cookie":
                    headers["Cookie"] = "studio_oauth_state=wrong"
                elif mutation == "agent":
                    headers["User-Agent"] = "different-browser"
                elif mutation == "provider":
                    path = f"/api/oauth/callback/wrong-provider?state={state}&code=synthetic-code"
                elif mutation == "expired":
                    with closing(sqlite3.connect(self.database)) as db, db:
                        db.execute("UPDATE oauth_pending SET expires_at=0")
                elif mutation == "changed":
                    changed = deepcopy(self.project)
                    changed["auth_profiles"]["login"]["clientId"] = "changed-client"
                    self._update_project(changed)
                    self.project = changed
                with patch("api_test.oauth_service.post_token_form") as provider:
                    result = self.client.get(path, headers=headers, follow_redirects=False)
                self.assertEqual(result.status_code, 409, result.text)
                self.assertEqual(result.json(), {"error": "OAuth callback could not be completed"})
                self.assertNotIn(state, result.text)
                self.assertNotIn("synthetic-code", result.text)
                provider.assert_not_called()

    def test_provider_error_and_failed_token_exchange_are_sanitized(self):
        _, _, query, key = self._authorize()
        path = f"/api/oauth/callback/{key}?state={query['state'][0]}&error=private-provider-detail"
        denied = self.client.get(path, follow_redirects=False)
        self.assertEqual(denied.status_code, 400, denied.text)
        self.assertEqual(denied.json(), {"error": "OAuth callback could not be completed"})
        self.assertNotIn("private-provider-detail", denied.text)
        with patch("api_test.oauth_service.post_token_form", side_effect=OAuthTransportError("provider-secret-error")):
            result = self.client.post(f"{self.profile_path}/service/token", json={"action": "issue"})
        self.assertEqual(result.status_code, 502, result.text)
        self.assertNotIn("provider-secret-error", result.text)
        self.assertNotIn("synthetic-client-secret", result.text)
        self.assertNotIn("provider-secret-error", "\n".join(self.logged_messages))

    def test_profile_validation_state_invalidation_and_bad_request_contract(self):
        bad = deepcopy(self.project)
        bad["auth_profiles"]["service"]["clientSecret"] = "literal-client-secret"
        rejected = self.client.put("/api/projects/bad.json", json=bad)
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertNotIn("literal-client-secret", rejected.text)
        for body in ({}, {"action": "bogus"}, {"action": "issue", "environment": 3}):
            with self.subTest(body=body):
                result = self.client.post(f"{self.profile_path}/service/token", json=body)
                self.assertEqual(result.status_code, 400, result.text)
        invalid = self.client.post(f"{self.profile_path}/login/authorize", json={"environment": 3})
        self.assertEqual(invalid.status_code, 400, invalid.text)
        missing = self.client.get(f"{self.profile_path}/missing")
        self.assertEqual(missing.status_code, 400, missing.text)
        with patch("api_test.oauth_service.post_token_form", return_value={"token_type": "Bearer", "access_token": "cached-access", "expires_in": 3600}):
            issued = self.client.post(f"{self.profile_path}/service/token", json={"action": "issue"})
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertTrue(self.client.get(f"{self.profile_path}/service").json()["connected"])
        changed = deepcopy(self.project)
        changed["variables"]["secret"]["CLIENT"]["value"] = "rotated-client-secret"
        self._update_project(changed)
        self.assertFalse(self.client.get(f"{self.profile_path}/service").json()["connected"])

    def test_viewer_membership_cannot_issue_or_disconnect(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO users(id,display_name,created_at,updated_at,status) VALUES ('viewer','Viewer','x','x','active')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at,status) VALUES ('default','viewer','viewer','x','active')")
        viewer = CollaborationStore(self.database, self.roots, context=RequestContext("default", "viewer"))
        with patch.object(studio, "collaboration_store", return_value=viewer), TestClient(
            studio.app, base_url="http://127.0.0.1:8765", raise_server_exceptions=False
        ) as client:
            self.assertEqual(client.get(f"{self.profile_path}/service").status_code, 200)
            issue = client.post(f"{self.profile_path}/service/token", json={"action": "issue"})
            disconnect = client.delete(f"{self.profile_path}/service")
        self.assertEqual(issue.status_code, 403, issue.text)
        self.assertEqual(disconnect.status_code, 403, disconnect.text)


if __name__ == "__main__":
    unittest.main()
