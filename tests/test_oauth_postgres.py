"""OAuth v6 token state on the dedicated disposable PostgreSQL test service."""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from psycopg import connect
from psycopg.conninfo import make_conninfo

from api_test.oauth_vault import Vault
from api_test.database import _pools, _pool_lock


DEFAULT_ADMIN = "postgresql://studio_test:studio_test_local@127.0.0.1:15432/postgres"


@unittest.skipUnless(os.environ.get("FND4_TEST_DATABASE_URL", DEFAULT_ADMIN),
                     "Dedicated PostgreSQL test URL disabled")
class OAuthPostgresTests(unittest.TestCase):
    def test_migration_lease_refresh_and_disconnect(self):
        admin_url = os.environ.get("FND4_TEST_DATABASE_URL", DEFAULT_ADMIN)
        name = "oauth_test_" + uuid.uuid4().hex[:12]
        with connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
            try:
                isolated = make_conninfo(admin_url, dbname=name)
                with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                    "STUDIO_DATABASE_URL": isolated, "STUDIO_DATABASE_URL_FILE": "",
                    "API_TEST_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                    "API_TEST_ENCRYPTION_URL": "",
                }):
                    first, second = Vault(Path(directory) / "unused.db"), Vault(Path(directory) / "unused.db")
                    identity = first.identity("p.json", "dev", "login")
                    lease = first.acquire(identity, "a" * 64, "client_credentials")
                    first.finish(lease, {"token_type": "Bearer", "access_token": "pg-access",
                                         "refresh_token": "pg-refresh", "expires_in": 120})
                    self.assertEqual(second.acquire(identity, "a" * 64, "client_credentials"), "pg-access")
                    refreshing = second.acquire(identity, "a" * 64, "authorization_code", force=True)
                    self.assertEqual(refreshing.refresh_token, "pg-refresh")
                    first.finish(refreshing, {"token_type": "Bearer", "access_token": "pg-next",
                                              "refresh_token": "pg-rotated", "expires_in": 120}, public_client=True)
                    second.disconnect(identity)
                    self.assertFalse(first.status(identity, "a" * 64)["connected"])
            finally:
                if 'isolated' in locals():
                    with _pool_lock:
                        pool = _pools.pop(isolated, None)
                    if pool is not None:
                        pool.close()
                admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')

if __name__ == "__main__":
    unittest.main()
