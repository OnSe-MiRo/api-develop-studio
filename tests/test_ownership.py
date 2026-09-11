import io
import json
import os
import socket
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from api_test.ownership import OwnershipStore, OwnershipError, local_policy, origin, fetch_challenge
from api_test.cli import run_pipeline, run_case_file
from api_test.runner import CaseConfigurationError, execute_http_call
from react_server import handle_api_request, StudioHandler


class OwnershipTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {"LOCAL_SERVER": "false", "SKIP_OWNERSHIP_VERIFICATION": "false", "STUDIO_OWNERSHIP_DB_PATH": str(self.root / "ownership.db")}))
        self.store = OwnershipStore()
        self.doc = {"base_url": "https://api.example.com"}

    def issue(self):
        return self.store.issue("p.json", self.doc, self.doc["base_url"], "session-a")

    def verified(self):
        issued = self.issue()
        with patch("api_test.ownership.fetch_challenge", return_value=issued["challenge"]):
            self.store.verify("p.json", self.doc, issued["verification_id"], "session-a")
        return issued

    def test_environment_matrix(self):
        for local, skip in [(False, False), (True, False), (True, True), (False, True)]:
            with self.subTest(local=local, skip=skip), patch.dict(os.environ, {"LOCAL_SERVER": str(local), "SKIP_OWNERSHIP_VERIFICATION": str(skip)}):
                if skip and not local:
                    with self.assertRaises(OwnershipError): local_policy()
                else:
                    self.assertEqual(local_policy()["skip_verification"], local and skip)

    def test_challenge_is_hashed_and_not_in_status(self):
        issued = self.issue()
        self.assertNotIn(issued["challenge"], json.dumps(self.store.status("p.json", self.doc)))
        self.assertNotIn(issued["challenge"].encode(), self.store.path.read_bytes())
        with self.assertRaises(OwnershipError): self.issue()

    def test_session_and_project_bound_before_network(self):
        issued = self.issue()
        with patch("api_test.ownership.fetch_challenge") as fetch:
            for project, session in [("other.json", "session-a"), ("p.json", "session-b")]:
                with self.assertRaises(OwnershipError):
                    self.store.verify(project, self.doc, issued["verification_id"], session)
            fetch.assert_not_called()

    def test_mismatch_then_success_then_replay_denied(self):
        issued = self.issue()
        with patch("api_test.ownership.fetch_challenge", return_value="wrong"):
            with self.assertRaises(OwnershipError): self.store.verify("p.json", self.doc, issued["verification_id"], "session-a")
        with patch("api_test.ownership.fetch_challenge", return_value=issued["challenge"]):
            self.store.verify("p.json", self.doc, issued["verification_id"], "session-a")
            with self.assertRaises(OwnershipError): self.store.verify("p.json", self.doc, issued["verification_id"], "session-a")

    def test_expired_and_reissued_challenges_denied(self):
        with patch("api_test.ownership.time.time", return_value=10000): old = self.issue()
        with patch("api_test.ownership.time.time", return_value=11801), patch("api_test.ownership.fetch_challenge") as fetch:
            with self.assertRaises(OwnershipError): self.store.verify("p.json", self.doc, old["verification_id"], "session-a")
            fresh = self.issue()
            self.assertNotEqual(old["challenge"], fresh["challenge"])
            with self.assertRaises(OwnershipError): self.store.verify("p.json", self.doc, old["verification_id"], "session-a")
            fetch.assert_not_called()

    def test_verified_origin_only_and_idle_expiration(self):
        with patch("api_test.ownership.time.time", return_value=10000): self.verified()
        with patch("api_test.ownership.time.time", return_value=10001):
            self.store.authorize("p.json", self.doc, "https://api.example.com/v1", "GET")
            with self.assertRaises(OwnershipError): self.store.authorize("p.json", self.doc, "https://other.example.com/v1", "GET")
        with patch("api_test.ownership.time.time", return_value=10001+30*86400):
            with self.assertRaises(OwnershipError): self.store.authorize("p.json", self.doc, "https://api.example.com/v1", "GET")

    def test_absolute_expiry_despite_recent_use(self):
        with patch("api_test.ownership.time.time", return_value=10000): self.verified()
        with self.store.db() as db:
            db.execute("UPDATE proofs SET last_used=?", (10000+89*86400,))
        with patch("api_test.ownership.time.time", return_value=10000+90*86400):
            with self.assertRaises(OwnershipError): self.store.authorize("p.json", self.doc, "https://api.example.com", "GET")

    def test_configuration_change_revoke_and_delete(self):
        self.verified()
        altered = {"base_url": "https://new.example.com"}
        with self.assertRaises(OwnershipError): self.store.authorize("p.json", altered, "https://api.example.com", "GET")
        self.store.revoke("p.json", remove=True)
        self.assertEqual(self.store.status("p.json", self.doc)["proofs"], [])

    def test_bypass_does_not_persist_verification(self):
        with patch.dict(os.environ, {"LOCAL_SERVER": "true", "SKIP_OWNERSHIP_VERIFICATION": "true"}):
            self.store.authorize("p.json", self.doc, "http://localhost:8000", "GET")
        self.assertEqual(self.store.status("p.json", self.doc)["proofs"], [])

    def test_external_grant_exact_scope_rate_limit_and_removal(self):
        url = "https://auth.example.com/token"
        self.store.grant("p.json", url, "POST")
        for project, target, method in [("other.json", url, "POST"), ("p.json", url, "GET"), ("p.json", url+"/extra", "POST"), ("p.json", url+"?x=1", "POST")]:
            with self.assertRaises(OwnershipError): self.store.authorize(project, self.doc, target, method, external=True)
        self.store.authorize("p.json", self.doc, url, "POST", external=True)
        with self.assertRaises(OwnershipError): self.store.authorize("p.json", self.doc, url, "POST", external=True)
        self.store.grant("p.json", url, "POST", remove=True)
        self.assertEqual(self.store.status("p.json", self.doc)["grants"], [])

    def test_public_dns_required(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            with patch("api_test.ownership.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))]), patch("api_test.ownership.socket.socket") as sock:
                with self.assertRaises(OwnershipError): fetch_challenge("https://api.example.com", "vid")
                sock.assert_not_called()

    def test_invalid_urls(self):
        for url in (None, {}, "file:///etc/passwd", "https://user:pass@example.com", "https://example.com/#x", "https://example.com\\@evil.test", "https://example.com:bad"):
            with self.subTest(url=url), self.assertRaises(OwnershipError): origin(url)

    def test_verification_transport_pins_ip_and_does_not_send_challenge(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch('api_test.ownership.socket.getaddrinfo', return_value=addresses), patch('api_test.ownership.socket.socket') as sock, patch('api_test.ownership.http.client.HTTPSConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"challenge":"server-value"}'
            self.assertEqual(fetch_challenge('https://api.example.com', 'verification-id'), 'server-value')
            sock.return_value.connect.assert_called_once_with(('93.184.216.34', 443))
            args, kwargs = connection.return_value.request.call_args
            self.assertEqual(args, ('GET', '/.well-known/api-develop-studio-verification/verification-id'))
            self.assertNotIn('server-value', repr(kwargs))
            response.read.assert_called_once_with(4097)
            for status, content in [(302, b'{}'), (200, b'x'*4097), (200, b'[]')]:
                response.status, response.read.return_value = status, content
                with self.assertRaises(OwnershipError): fetch_challenge('https://api.example.com', 'verification-id')

    def test_guarded_transport_disables_redirect(self):
        with patch('api_test.runner.urllib.request.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status, response.read.return_value = 200, b'{}'
            execute_http_call('https://api.example.com', allow_redirects=False)
            handlers = opener.call_args.args
            redirect_handler = next(h for h in handlers if hasattr(h, 'redirect_request'))
            self.assertIsNone(redirect_handler.redirect_request(None, None, 302, '', {}, 'https://other.example.com'))

    def test_concurrent_external_runs_only_one_is_admitted(self):
        self.store.grant('p.json', 'https://auth.example.com/token', 'POST')
        def attempt(_):
            try:
                self.store.authorize('p.json', self.doc, 'https://auth.example.com/token', 'POST', external=True)
                return True
            except OwnershipError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sum(executor.map(attempt, range(2))), 1)

    def test_cross_origin_browser_requests_denied(self):
        handler = object.__new__(StudioHandler)
        handler.headers = {'Host': '127.0.0.1:8765', 'Origin': 'https://evil.example'}
        with self.assertRaises(OwnershipError): handler.check_request_origin()
        with patch.dict(os.environ, {'LOCAL_SERVER': 'true'}):
            handler.headers = {'Host': 'rebind.example:8765'}
            with self.assertRaises(OwnershipError): handler.check_request_origin()

    def fixture(self, steps):
        projects, cases = self.root / "projects", self.root / "case"
        projects.mkdir(exist_ok=True); cases.mkdir(exist_ok=True)
        (projects / "p.json").write_text(json.dumps(self.doc))
        (cases / "setup.json").write_text(json.dumps({"project": "p.json", "request": {"url": "https://auth.example.com/token", "method": "POST"}, "expected": {"status": 200}}))
        (cases / "test.json").write_text(json.dumps({"project": "p.json", "request": {"url": "/users", "method": "GET"}, "expected": {"status": 200}}))
        pipeline = self.root / "pipeline.json"
        pipeline.write_text(json.dumps({"project": "p.json", "steps": steps}))
        return pipeline, cases, projects

    def test_pipeline_setup_once_and_pass_token_to_test(self):
        steps = [{"name": "login", "case": "setup.json", "phase": "setup", "external_once": True},
                 {"name": "users", "case": "test.json", "input_mappings": [{"source_step": "login", "response_path": "body.token", "target": "header", "target_key": "Authorization", "template": "Bearer {{value}}"}]}]
        pipeline, cases, projects = self.fixture(steps)
        self.verified()
        self.store.grant("p.json", "https://auth.example.com/token", "POST")
        with patch("api_test.runner.execute_http_call", side_effect=[(200, {}, '{"token":"secret"}', 0), (200, {}, '{}', 0)]) as call, redirect_stdout(io.StringIO()):
            self.assertEqual(run_pipeline(pipeline, cases, 2, self.root / "logs", projects), 0)
        self.assertEqual(call.call_count, 2)
        self.assertFalse(call.call_args_list[0].kwargs["allow_redirects"])
        self.assertEqual(call.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer secret")

    def test_external_setup_validation_before_any_call(self):
        base = {"name": "login", "case": "setup.json", "phase": "setup", "external_once": True}
        for steps in [[{**base, "retry": 1}], [{**base, "phase": "test"}], [base, {**base, "name": "again"}], [{"name": "test", "case": "test.json"}, base], [{**base, "continue_on_failure": True}]]:
            pipeline, cases, projects = self.fixture(steps)
            with patch("api_test.runner.execute_http_call") as call, self.assertRaises(CaseConfigurationError):
                run_pipeline(pipeline, cases, 2, self.root / "logs", projects)
            call.assert_not_called()

    def test_unverified_cli_and_quick_request_blocked(self):
        _, cases, projects = self.fixture([])
        with patch("api_test.runner.execute_http_call") as call:
            with self.assertRaises(OwnershipError): run_case_file("test.json", cases, 2, self.root / "logs", projects)
            call.assert_not_called()
        with patch("react_server.PROJECT_ROOT", projects), patch("react_server.execute_http_call") as call:
            with self.assertRaises(OwnershipError): handle_api_request({"project": "p.json", "url": "https://api.example.com/users"})
            call.assert_not_called()

    def test_external_setup_failure_stops_before_test(self):
        pipeline, cases, projects = self.fixture([{"name": "login", "case": "setup.json", "phase": "setup", "external_once": True}, {"name": "users", "case": "test.json"}])
        self.store.grant("p.json", "https://auth.example.com/token", "POST")
        with patch("api_test.runner.execute_http_call", return_value=(500, {}, '{}', 0)) as call, redirect_stdout(io.StringIO()):
            self.assertEqual(run_pipeline(pipeline, cases, 2, self.root / "logs", projects), 1)
            self.assertEqual(call.call_count, 1)

    def test_external_without_grant_blocked_before_network_even_in_bypass(self):
        pipeline, cases, projects = self.fixture([{'name': 'login', 'case': 'setup.json', 'phase': 'setup', 'external_once': True}])
        with patch.dict(os.environ, {'LOCAL_SERVER': 'true', 'SKIP_OWNERSHIP_VERIFICATION': 'true'}), patch('api_test.runner.execute_http_call') as call:
            with self.assertRaises(OwnershipError): run_pipeline(pipeline, cases, 2, self.root / 'logs', projects)
            call.assert_not_called()

    def test_server_external_approval_key_required(self):
        handler = object.__new__(StudioHandler)
        handler.headers = {"Origin": "https://studio.example.com", "Host": "studio.example.com"}
        handler.ownership_session = Mock(return_value="session-a")
        handler.query_value = Mock(return_value="p.json")
        handler.read_body = Mock(return_value={"url": "https://auth.example.com/token", "method": "POST"})
        handler.send_json = Mock()
        with patch("react_server.collaboration_store") as store, patch.dict(os.environ, {"STUDIO_APPROVER_KEY": "k"*32}):
            store.return_value.get.return_value.document = self.doc
            with self.assertRaises(OwnershipError): handler.ownership_action(["api", "ownership", "grant"])
            handler.headers["X-Studio-Approver-Key"] = "k"*32
            handler.ownership_action(["api", "ownership", "grant"])
            self.assertEqual(len(self.store.status("p.json", self.doc)["grants"]), 1)


if __name__ == '__main__':
    unittest.main()
