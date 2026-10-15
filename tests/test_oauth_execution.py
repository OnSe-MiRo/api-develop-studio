"""Saved OAuth profiles in quick calls, cases and CLI environment selection."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

import react_server as studio
from api_test.project_variables import encrypt_secret
from api_test.runner import ApiTestRunner, CaseConfigurationError, project_request_settings


class OAuthExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                                          "API_TEST_ENCRYPTION_URL": "", "LOCAL_SERVER": "true",
                                          "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "",
                                          "STUDIO_DB_PATH": str(self.root / "oauth.db"),
                                          "SKIP_OWNERSHIP_VERIFICATION": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.project = studio.normalize_project_document({
            "name": "OAuth", "base_url": "https://api.example.test",
            "variables": {"plain": {}, "secret": {"CLIENT": {"value": "project-secret"}}},
            "auth_profiles": {"service": {"type": "OAuth 2.0", "grantType": "client_credentials",
                "clientId": "client", "clientSecret": "{{project.CLIENT}}",
                "tokenUrl": "https://issuer.example.test/token", "clientAuthMethod": "basic",
                "scopes": ["read"]}},
            "environments": {"dev": {"base_url": "https://dev.example.test", "variables": {
                "plain": {}, "secret": {"CLIENT": {"value": "dev-secret"}}}}},
            "default_environment": "dev",
        })
        (self.root / "oauth.json").write_text(json.dumps(self.project), encoding="utf-8")

    def test_quick_call_uses_default_environment_header_only_and_no_redirect(self):
        with patch.object(studio, "PROJECT_ROOT", self.root),              patch("api_test.oauth_service.resource_token", return_value="synthetic-token") as mint,              patch.object(studio, "execute_http_call", return_value=(200, {}, '{"echo":"synthetic-token"}', 1)) as http:
            response = studio.handle_api_request({"project": "oauth.json", "url": "/protected", "auth_profile": "service"})
        self.assertEqual(http.call_args.args[0], "https://dev.example.test/protected")
        self.assertEqual(http.call_args.kwargs["headers"]["Authorization"], "Bearer synthetic-token")
        self.assertFalse(http.call_args.kwargs["allow_redirects"])
        self.assertTrue(http.call_args.kwargs["verify_ssl"])
        self.assertEqual(mint.call_args.args[1:3], ("dev", "service"))
        self.assertNotIn("synthetic-token", json.dumps(response))

    def test_case_retry_mints_once_keeps_token_out_of_request_and_ignores_case_secret_override(self):
        settings = project_request_settings({"project": "oauth.json"}, self.root)
        self.assertEqual(settings.environment_name, "dev")
        override = encrypt_secret("case-override")
        case = {"request": {"url": "/protected", "auth_profile": "service"},
                "expected": {"status": 200},
                "variables": {"secret": {"CLIENT": override}}}
        with patch("api_test.oauth_service.resource_token", return_value="synthetic-token") as mint,              patch("api_test.runner.execute_http_call", side_effect=[
                 (500, {}, '{"echo":"synthetic-token"}', 1),
                 (200, {}, '{"echo":"synthetic-token"}', 1)]) as http:
            result = ApiTestRunner().run_case(
                "case", case, retry=1, base_url=settings.base_url, auth_profiles=settings.auth_profiles,
                project_variables=settings.variables, encrypted_project_variables=settings.encrypted_variables,
                oauth_project_reference="oauth.json", oauth_environment=settings.environment_name,
                verify_ssl=False)
        self.assertEqual(result.status, "passed")
        self.assertEqual(mint.call_count, 1)
        self.assertEqual(mint.call_args.args[4], settings.encrypted_variables)
        self.assertNotEqual(mint.call_args.args[4]["CLIENT"], override)
        self.assertEqual(http.call_count, 2)
        for call in http.call_args_list:
            self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer synthetic-token")
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertTrue(call.kwargs["verify_ssl"])
        from api_test.cli import _result_lines
        from api_test.reports import RunReport
        self.assertNotIn("synthetic-token", json.dumps(result.request_definition))
        self.assertNotIn("synthetic-token", "\n".join(_result_lines(result)))
        report = RunReport()
        report.add(result, "case.json", "2026-10-04T00:00:00Z", project="oauth.json", case_reference="case.json")
        self.assertNotIn("synthetic-token", json.dumps(report.data))

    def test_loopback_http_oauth_ignores_ambient_proxy_without_bypassing_https_proxy(self):
        case = {"request": {"url": "/protected", "auth_profile": "service"}, "expected": {"status": 200}}
        profile = self.project["auth_profiles"]["service"]
        encrypted = self.project["variables"]["secret"]
        with patch.dict(os.environ, {"HTTP_PROXY": "http://proxy.example.test:8080"}), \
             patch("api_test.oauth_service.resource_token", return_value="synthetic-token"), \
             patch("api_test.runner.execute_http_call", return_value=(200, {}, '{}', 1)) as http:
            result = ApiTestRunner().run_case("case", case, base_url="http://127.0.0.1:8123",
                auth_profiles={"service": profile}, encrypted_project_variables=encrypted,
                oauth_project_reference="oauth.json")
        self.assertEqual(result.status, "passed")
        self.assertTrue(http.call_args.kwargs["no_proxy"])
        with patch("api_test.oauth_service.resource_token", return_value="synthetic-token"), \
             patch("api_test.runner.execute_http_call", return_value=(200, {}, '{}', 1)) as http:
            result = ApiTestRunner().run_case("case", case, base_url="https://api.example.test",
                auth_profiles={"service": profile}, encrypted_project_variables=encrypted,
                oauth_project_reference="oauth.json", proxy_url="http://proxy.example.test:8080")
        self.assertEqual(result.status, "passed")
        self.assertEqual(http.call_args.kwargs["proxy_url"], "http://proxy.example.test:8080")
        self.assertFalse(http.call_args.kwargs["no_proxy"])

    def test_public_https_callback_origin_accepts_http_backend_only_with_preserved_host(self):
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.testclient import TestClient
        from api_test.oauth_service import OAuthError, _callback_origin
        from types import SimpleNamespace
        application = FastAPI()
        @application.get("/origin")
        def origin(request: Request):
            try:
                return {"callbackOrigin": _callback_origin(SimpleNamespace(request=request, headers=request.headers))}
            except OAuthError:
                raise HTTPException(status_code=400)
        with patch.dict(os.environ, {"LOCAL_SERVER": "false", "STUDIO_OAUTH_CALLBACK_ORIGIN": "https://studio.example"}):
            with TestClient(application, base_url="http://studio.example") as client:
                good = client.get("/origin", headers={"Origin": "https://studio.example"})
                self.assertEqual(good.status_code, 200)
                self.assertEqual(good.json()["callbackOrigin"], "https://studio.example")
                denied = client.get("/origin", headers={"Host": "evil.example", "X-Forwarded-Proto": "https"})
                self.assertEqual(denied.status_code, 400)

    def test_token_exchange_classifies_invalid_timeout_and_storage_failure(self):
        from api_test.oauth_service import OAuthError, _exchange
        from api_test.oauth_transport import OAuthTimeoutError
        from api_test.oauth_vault import Vault
        vault = Vault(self.root / "oauth.db")
        identity = vault.identity("oauth.json", "dev", "service")
        profile = self.project["auth_profiles"]["service"]
        encrypted = self.project["environments"]["dev"]["variables"]["secret"]
        lease = vault.acquire(identity, "a" * 64, "client_credentials")
        with patch("api_test.oauth_service.post_token_form", return_value={"token_type": "Bearer", "access_token": "bad\r\nHeader"}):
            with self.assertRaises(OAuthError) as invalid:
                _exchange(profile, encrypted, lease, vault)
        self.assertEqual(invalid.exception.status_code, 502)
        lease = vault.acquire(identity, "a" * 64, "client_credentials")
        with patch("api_test.oauth_service.post_token_form", side_effect=OAuthTimeoutError("internal")):
            with self.assertRaises(OAuthError) as timeout:
                _exchange(profile, encrypted, lease, vault)
        self.assertEqual(timeout.exception.status_code, 504)
        lease = vault.acquire(identity, "a" * 64, "client_credentials")
        with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": ""}):
            with self.assertRaises(OAuthError) as unavailable:
                _exchange(profile, encrypted, lease, vault)
        self.assertEqual(unavailable.exception.status_code, 503)

    def test_saved_origin_mismatch_blocks_before_resource_request(self):
        settings = project_request_settings({"project": "oauth.json"}, self.root)
        case = {"request": {"url": "https://elsewhere.test/protected", "auth_profile": "service"},
                "expected": {"status": 200}}
        from api_test.oauth_service import _bound_resource, OAuthError
        with self.assertRaises(OAuthError):
            _bound_resource(settings.base_url, case["request"]["url"])
        with patch("api_test.runner.execute_http_call") as http:
            with self.assertRaises(CaseConfigurationError):
                ApiTestRunner().run_case("case", case, base_url=settings.base_url,
                    auth_profiles=settings.auth_profiles, encrypted_project_variables=settings.encrypted_variables,
                    oauth_project_reference="oauth.json", oauth_environment="dev")
            http.assert_not_called()

if __name__ == "__main__":
    unittest.main()
