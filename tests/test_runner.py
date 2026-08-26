from __future__ import annotations

import json
import io
import os
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet

from api_test import cli
from api_test.cli import run_case_file, run_case_files, run_pipeline
from api_test.comparison import compare_json
from api_test.project_variables import encrypt_secret
from api_test.runner import ApiTestRunner, CaseConfigurationError, project_base_url, project_request_settings
from react_server import ApiError, safe_attachment_file


class FakeResponse:
    def __init__(self, status: int, body: dict[str, object]) -> None:
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class ApiRunnerTest(unittest.TestCase):
    def test_compare_reports_nested_difference(self) -> None:
        differences = compare_json({"user": {"id": 7}}, {"user": {"id": 8}})
        self.assertEqual(differences[0].path, "$.user.id")
        self.assertEqual(differences[0].reason, "value mismatch")

    def test_non_strict_allows_equivalent_integer_and_float(self) -> None:
        self.assertEqual(compare_json({"score": 9.0}, {"score": 9}, strict=False), [])
        strict_differences = compare_json({"score": 9.0}, {"score": 9}, strict=True)
        self.assertEqual(strict_differences[0].reason, "type mismatch")
        boolean_differences = compare_json({"enabled": True}, {"enabled": 1}, strict=False)
        self.assertEqual(boolean_differences[0].reason, "type mismatch")

    def test_response_assertions_pass_for_ranges_types_and_presence(self) -> None:
        case = {
            "request": {"url": "https://example.test/metrics"},
            "expected": {
                "status": 200,
                "assertions": [
                    {"path": "body.age", "operator": "between", "min": 18, "max": 65},
                    {"path": "body.score", "operator": "gte", "value": 80},
                    {"path": "body.rate", "operator": "gt", "value": 0},
                    {"path": "body.rate", "operator": "lt", "value": 1},
                    {"path": "body.age", "operator": "lte", "value": 30},
                    {"path": "body.name", "operator": "length_between", "min": 1, "max": 10},
                    {"path": "body.items", "operator": "type", "value": "array"},
                    {"path": "body.active", "operator": "type", "value": "boolean"},
                    {"path": "body.optional", "operator": "type", "value": "null"},
                    {"path": "body.name", "operator": "exists"},
                    {"path": "body.password", "operator": "not_exists"},
                ],
            },
        }
        response = {"age": 24, "score": 80, "rate": 0.5, "name": "Ada", "items": [1, 2], "active": True, "optional": None}
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, response)):
            result = ApiTestRunner().run_case("range", case)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.differences, [])
        self.assertEqual(len(result.assertion_results), 11)
        self.assertTrue(all(item.passed for item in result.assertion_results))

    def test_response_assertions_report_every_failed_condition(self) -> None:
        case = {
            "request": {"url": "https://example.test/metrics"},
            "expected": {
                "status": 200,
                "assertions": [
                    {"path": "body.age", "operator": "between", "min": 18, "max": 65},
                    {"path": "body.score", "operator": "gte", "value": 80},
                    {"path": "body.items", "operator": "length_between", "min": 1, "max": 2},
                    {"path": "body.email", "operator": "exists"},
                    {"path": "body.secret", "operator": "not_exists"},
                ],
            },
        }
        response = {"age": 72, "score": "90", "items": [1, 2, 3], "secret": "present"}
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, response)):
            result = ApiTestRunner().run_case("range", case)
        self.assertEqual(result.status, "failed")
        self.assertEqual([difference.path for difference in result.differences], [
            "$.body.age", "$.body.score", "$.body.items", "$.body.email", "$.body.secret",
        ])
        self.assertIn("18 <= value <= 65", result.differences[0].reason)
        self.assertEqual(result.differences[1].reason, "numeric assertion requires a number")
        self.assertIn("actual length 3", result.differences[2].reason)
        self.assertEqual(result.differences[3].reason, "assertion path missing")
        self.assertEqual(len(result.assertion_results), 5)
        self.assertTrue(all(not item.passed for item in result.assertion_results))

    def test_every_assertion_operator_records_both_pass_and_fail_results(self) -> None:
        assertions = [
            {"path": "body.score", "operator": "gt", "value": 4},
            {"path": "body.score", "operator": "gt", "value": 5},
            {"path": "body.score", "operator": "gte", "value": 5},
            {"path": "body.score", "operator": "gte", "value": 6},
            {"path": "body.score", "operator": "lt", "value": 6},
            {"path": "body.score", "operator": "lt", "value": 5},
            {"path": "body.score", "operator": "lte", "value": 5},
            {"path": "body.score", "operator": "lte", "value": 4},
            {"path": "body.score", "operator": "between", "min": 5, "max": 5},
            {"path": "body.score", "operator": "between", "min": 6, "max": 7},
            {"path": "body.name", "operator": "exists"},
            {"path": "body.missing", "operator": "exists"},
            {"path": "body.missing", "operator": "not_exists"},
            {"path": "body.name", "operator": "not_exists"},
            {"path": "body.name", "operator": "type", "value": "string"},
            {"path": "body.name", "operator": "type", "value": "integer"},
            {"path": "body.name", "operator": "length_between", "min": 1, "max": 3},
            {"path": "body.name", "operator": "length_between", "min": 1, "max": 2},
        ]
        case = {
            "request": {"url": "https://example.test/metrics"},
            "expected": {
                "assertions": assertions,
                "validation_modes": {"exact_body": False, "conditions": True},
            },
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"score": 5, "name": "Ada"})):
            result = ApiTestRunner().run_case("all_operators", case)
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.assertion_results), 18)
        self.assertEqual(sum(item.passed for item in result.assertion_results), 9)
        self.assertEqual(len(result.differences), 9)
        for operator in {assertion["operator"] for assertion in assertions}:
            states = {item.passed for item in result.assertion_results if item.operator == operator}
            self.assertEqual(states, {True, False}, operator)

    def test_string_length_condition_reports_value_longer_than_maximum(self) -> None:
        case = {
            "request": {"url": "https://example.test/users/1"},
            "expected": {
                "status": 200,
                "assertions": [{"path": "body.name", "operator": "length_between", "min": 1, "max": 2}],
                "validation_modes": {"exact_body": False, "conditions": True},
            },
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"name": "Ada"})):
            result = ApiTestRunner().run_case("name_length", case)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.differences[0].path, "$.body.name")
        self.assertEqual(
            result.differences[0].reason,
            "length condition not met: expected 1 <= length <= 2, actual length 3",
        )

    def test_exclusive_range_rejects_boundary_value(self) -> None:
        case = {
            "request": {"url": "https://example.test/metrics"},
            "expected": {"assertions": [{
                "path": "body.score", "operator": "between", "min": 0, "max": 100,
                "include_min": False, "include_max": False,
            }]},
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"score": 100})):
            result = ApiTestRunner().run_case("exclusive", case)
        self.assertEqual(result.status, "failed")
        self.assertIn("0 < value < 100", result.differences[0].reason)

    def test_invalid_assertion_is_rejected_before_request(self) -> None:
        case = {
            "request": {"url": "https://example.test/metrics"},
            "expected": {"assertions": [{"path": "body.age", "operator": "between", "min": 65, "max": 18}]},
        }
        with patch("api_test.runner.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(CaseConfigurationError, "min must be less than or equal to max"):
                ApiTestRunner().run_case("invalid", case)
        urlopen.assert_not_called()

    def test_validation_modes_can_run_conditions_only(self) -> None:
        case = {
            "request": {"url": "https://example.test/users/1"},
            "expected": {
                "status": 200,
                "body": {"id": 1, "name": "Grace"},
                "assertions": [{"path": "body.id", "operator": "between", "min": 1, "max": 1}],
                "validation_modes": {"exact_body": False, "conditions": True},
            },
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"id": 1, "name": "Ada"})):
            result = ApiTestRunner().run_case("conditions_only", case)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.differences, [])

    def test_validation_modes_can_run_exact_body_only(self) -> None:
        case = {
            "request": {"url": "https://example.test/users/1"},
            "expected": {
                "status": 200,
                "body": {"id": 1, "name": "Grace"},
                "assertions": [{"path": "body.id", "operator": "between", "min": 2, "max": 3}],
                "validation_modes": {"exact_body": True, "conditions": False},
            },
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"id": 1, "name": "Ada"})):
            result = ApiTestRunner().run_case("exact_only", case)
        self.assertEqual(result.status, "failed")
        self.assertEqual([difference.path for difference in result.differences], ["$.body.name"])

    def test_validation_modes_can_run_exact_body_and_conditions_together(self) -> None:
        case = {
            "request": {"url": "https://example.test/users/1"},
            "expected": {
                "status": 200,
                "body": {"id": 1, "name": "Grace"},
                "assertions": [{"path": "body.id", "operator": "between", "min": 2, "max": 3}],
                "validation_modes": {"exact_body": True, "conditions": True},
            },
        }
        with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"id": 1, "name": "Ada"})):
            result = ApiTestRunner().run_case("combined", case)
        self.assertEqual(result.status, "failed")
        self.assertEqual([difference.path for difference in result.differences], ["$.body.name", "$.body.id"])

    def test_validation_modes_are_checked_before_request(self) -> None:
        case = {
            "request": {"url": "https://example.test/users/1"},
            "expected": {"body": {}, "validation_modes": {"exact_body": "yes", "conditions": False}},
        }
        with patch("api_test.runner.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(CaseConfigurationError, "exact_body must be true or false"):
                ApiTestRunner().run_case("invalid_modes", case)
        urlopen.assert_not_called()

    def test_project_base_url_resolves_relative_case_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "projects"
            project_root.mkdir()
            (project_root / "member.json").write_text(json.dumps({
                "name": "Member API", "base_url": "https://example.test/api/",
            }), encoding="utf-8")
            case = {
                "project": "member.json",
                "request": {"url": "/users"},
                "expected": {"status": 200, "body": {"ok": True}},
            }
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"ok": True})) as urlopen:
                result = ApiTestRunner().run_case("users", case, base_url=project_base_url(case, project_root))
            self.assertEqual(result.status, "passed")
            self.assertEqual(urlopen.call_args.args[0].full_url, "https://example.test/api/users")

    def test_project_advanced_proxy_and_verify_settings_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "projects"
            project_root.mkdir()
            (project_root / "private-api.json").write_text(json.dumps({
                "name": "Private API", "base_url": "https://example.test",
                "advanced": {
                    "http_proxy": "http://http-proxy.example.test:8080",
                    "https_proxy": "http://https-proxy.example.test:8080",
                    "verify": False,
                },
            }), encoding="utf-8")
            case = {"project": "private-api.json", "request": {"url": "/health"}, "expected": {"status": 200}}
            settings = project_request_settings(case, project_root)
            self.assertIsNotNone(settings)
            assert settings is not None
            opener = Mock()
            opener.open.return_value = FakeResponse(200, {"ok": True})
            with patch("api_test.runner.urllib.request.build_opener", return_value=opener) as build_opener:
                result = ApiTestRunner().run_case(
                    "health", case, base_url=settings.base_url, verify_ssl=settings.verify_ssl, proxy_urls=settings.proxy_urls,
                )
            self.assertEqual(result.status, "passed")
            self.assertEqual(opener.open.call_args.args[0].full_url, "https://example.test/health")
            self.assertEqual(build_opener.call_count, 1)
            self.assertEqual(build_opener.call_args.args[0].proxies, {
                "http": "http://http-proxy.example.test:8080",
                "https": "http://https-proxy.example.test:8080",
            })

    def test_project_proxy_addresses_are_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "projects"
            project_root.mkdir()
            (project_root / "direct-api.json").write_text(json.dumps({
                "name": "Direct API", "base_url": "https://example.test",
                "advanced": {"use_proxy": False, "http_proxy": "http://proxy.example.test:8080", "https_proxy": "http://proxy.example.test:8080"},
            }), encoding="utf-8")
            settings = project_request_settings({"project": "direct-api.json"}, project_root)
            self.assertIsNotNone(settings)
            assert settings is not None
            self.assertEqual(settings.proxy_urls, {"http": "http://proxy.example.test:8080", "https": "http://proxy.example.test:8080"})

    def test_project_plain_and_encrypted_variables_are_resolved_in_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "projects"
            project_root.mkdir()
            encryption_key = Fernet.generate_key().decode()
            with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": encryption_key}, clear=False):
                encrypted_api_key = encrypt_secret("private-api-key")
            (project_root / "member.json").write_text(json.dumps({
                "name": "Member API",
                "base_url": "https://example.test/api",
                "variables": {
                    "plain": {"tenant": "alpha", "user_id": "7"},
                    "secret": {"api_key": encrypted_api_key},
                },
            }), encoding="utf-8")
            case = {
                "project": "member.json",
                "request": {
                    "method": "POST",
                    "url": "/{{project.tenant}}/users/{{project.user_id}}",
                    "headers": {"X-API-Key": "{{project.api_key}}"},
                    "body": {"tenant": "{{project.tenant}}"},
                },
                "expected": {"status": 200, "body": {"ok": True}},
            }
            settings = project_request_settings(case, project_root)
            assert settings is not None
            with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": encryption_key}, clear=False), patch(
                "api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"ok": True})
            ) as urlopen:
                result = ApiTestRunner().run_case(
                    "users", case, base_url=settings.base_url,
                    project_variables=settings.variables,
                    encrypted_project_variables=settings.encrypted_variables,
                )

            self.assertEqual(result.status, "passed")
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.test/api/alpha/users/7")
            self.assertEqual(request.get_header("X-api-key"), "private-api-key")
            self.assertEqual(json.loads(request.data), {"tenant": "alpha"})
            self.assertEqual(result.sensitive_values, {"private-api-key"})

    def test_case_encrypted_variables_are_resolved_and_redacted(self) -> None:
        encryption_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": encryption_key, "API_TEST_ENCRYPTION_URL": ""}, clear=False):
            encrypted_api_key = encrypt_secret("case-private-api-key")
            case = {
                "request": {
                    "method": "GET",
                    "url": "https://example.test/secure?key={{case.api_key}}",
                    "headers": {"X-API-Key": "{{case.api_key}}"},
                },
                "expected": {"status": 200, "body": {"ok": True}},
                "variables": {"secret": {"api_key": encrypted_api_key}},
            }
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"ok": True})) as urlopen:
                result = ApiTestRunner().run_case("secure", case)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/secure?key=case-private-api-key")
        self.assertEqual(request.get_header("X-api-key"), "case-private-api-key")
        self.assertEqual(result.sensitive_values, {"case-private-api-key"})

    def test_missing_project_variable_is_rejected_before_request(self) -> None:
        case = {
            "request": {"url": "https://example.test/{{project.missing}}"},
            "expected": {"status": 200},
        }
        with patch("api_test.runner.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(CaseConfigurationError, "not defined: missing"):
                ApiTestRunner().run_case("missing", case, project_variables={"tenant": "alpha"})
        urlopen.assert_not_called()

    def test_encrypted_project_variable_is_redacted_from_failure_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            project_root = root / "projects"
            log_root = root / "logs"
            (case_root / "member" / "security").mkdir(parents=True)
            project_root.mkdir()
            encryption_key = Fernet.generate_key().decode()
            with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": encryption_key}, clear=False):
                encrypted_api_key = encrypt_secret("private-api-key")
            (project_root / "member.json").write_text(json.dumps({
                "name": "Member API",
                "base_url": "https://example.test",
                "variables": {"plain": {}, "secret": {"api_key": encrypted_api_key}},
            }), encoding="utf-8")
            reference = "member/security/get.json"
            (case_root / reference).write_text(json.dumps({
                "project": "member.json",
                "request": {
                    "url": "/secure?key={{project.api_key}}",
                    "headers": {"X-API-Key": "{{project.api_key}}"},
                },
                "expected": {"status": 200, "body": {"error": "expected-error"}},
            }), encoding="utf-8")

            with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": encryption_key}, clear=False), patch(
                "api_test.runner.urllib.request.urlopen", return_value=FakeResponse(500, {"error": "private-api-key"})
            ):
                self.assertEqual(run_case_files([reference], case_root, 2, log_root, project_root), 1)

            log_content = next(log_root.glob("api-test_*.log")).read_text(encoding="utf-8")
            self.assertNotIn("private-api-key", log_content)
            self.assertIn("***REDACTED***", log_content)

    def test_runs_multipart_form_data_with_file_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attachment = root / "member" / "documents" / "files" / "profile.txt"
            attachment.parent.mkdir(parents=True)
            attachment.write_text("hello from attachment", encoding="utf-8")
            case = {
                "request": {
                    "method": "POST", "url": "https://example.test/documents",
                    "headers": {"Content-Type": "application/json"},
                    "form_data": [
                        {"key": "title", "value": "profile"},
                        {"key": "file", "file": "member/documents/files/profile.txt", "filename": "profile.txt", "content_type": "text/plain"},
                    ],
                },
                "expected": {"status": 200, "body": {"ok": True}},
            }
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"ok": True})) as urlopen:
                result = ApiTestRunner().run_case("upload", case, file_root=root)
            self.assertEqual(result.status, "passed")
            request = urlopen.call_args.args[0]
            headers = dict(request.header_items())
            self.assertTrue(headers["Content-type"].startswith("multipart/form-data; boundary="))
            self.assertIn(b'name="title"', request.data)
            self.assertIn(b"profile", request.data)
            self.assertIn(b'filename="profile.txt"', request.data)
            self.assertIn(b"hello from attachment", request.data)

    def test_attachment_paths_are_restricted_to_case_files_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            self.assertEqual(
                safe_attachment_file(root, "member/documents/files/profile.txt"),
                (root / "member" / "documents" / "files" / "profile.txt").resolve(),
            )
            with self.assertRaises(ApiError):
                safe_attachment_file(root, "member/documents/profile.txt")

    def test_pipeline_resolves_previous_response_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            api_dir = case_root / "account" / "users"
            api_dir.mkdir(parents=True)
            (api_dir / "get_user.json").write_text(json.dumps({
                "request": {"url": "https://example.test/user"},
                "expected": {"status": 200, "body": {"id": 7, "name": "Ada"}},
            }), encoding="utf-8")
            (api_dir / "get_user_detail.json").write_text(json.dumps({
                "request": {"url": "https://example.test/user/${get_user.response.body.id}"},
                "expected": {"status": 200, "body": {"id": 7, "active": True}},
            }), encoding="utf-8")
            (api_dir / "retry.json").write_text(json.dumps({
                "request": {"url": "https://example.test/retry"},
                "expected": {"status": 200, "body": {"ok": True}},
            }), encoding="utf-8")
            pipeline = root / "pipeline.json"
            pipeline.write_text(json.dumps({
                "steps": [
                    {"name": "get_user", "case": "account/users/get_user.json"},
                    {"name": "detail", "case": "account/users/get_user_detail.json"},
                    {"name": "retry", "case": "account/users/retry.json", "retry": 1},
                ],
            }), encoding="utf-8")
            failed_retry = urllib.error.HTTPError(
                "https://example.test/retry", 500, "Internal Server Error", Message(), io.BytesIO(b'{"ok": false}')
            )
            responses = [
                FakeResponse(200, {"id": 7, "name": "Ada"}),
                FakeResponse(200, {"id": 7, "active": True}),
                failed_retry,
                FakeResponse(200, {"ok": True}),
            ]
            log_dir = root / "logs"
            with patch("api_test.runner.urllib.request.urlopen", side_effect=responses) as urlopen:
                self.assertEqual(run_pipeline(pipeline, case_root, 2, log_dir), 0)
            self.assertEqual(urlopen.call_count, 4)
            self.assertEqual(urlopen.call_args_list[1].args[0].full_url, "https://example.test/user/7")
            logs = list(log_dir.glob("api-test_*.log"))
            self.assertEqual(len(logs), 1)
            log_content = logs[0].read_text(encoding="utf-8")
            self.assertIn("Step started: name=retry", log_content)
            self.assertIn("[PASSED] retry (attempts: 2)", log_content)
            self.assertIn("account: TOTAL 3 | PASS 3 | FAIL 0 | ERROR 0 | SKIPPED 0", log_content)

    def test_pipeline_applies_previous_response_value_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            api_dir = case_root / "member" / "users"
            api_dir.mkdir(parents=True)
            (api_dir / "create.json").write_text(json.dumps({
                "request": {"method": "POST", "url": "https://example.test/users"},
                "expected": {"status": 201, "body": {"id": 7}},
            }), encoding="utf-8")
            (api_dir / "detail.json").write_text(json.dumps({
                "request": {"method": "POST", "url": "https://example.test/users", "body": {"from_case": True}},
                "expected": {"status": 200, "body": {"ok": True}},
            }), encoding="utf-8")
            pipeline = root / "pipeline.json"
            pipeline.write_text(json.dumps({"steps": [
                {"name": "create_user", "case": "member/users/create.json"},
                {"name": "get_user", "case": "member/users/detail.json", "input_mappings": [
                    {"source_step": "create_user", "response_path": "body.id", "target": "url", "template": "https://example.test/users/{{value}}"},
                    {"source_step": "create_user", "response_path": "body.id", "target": "header", "target_key": "X-User-Id"},
                    {"source_step": "create_user", "response_path": "body.id", "target": "body", "target_key": "user.id"},
                ]},
            ]}), encoding="utf-8")
            with patch("api_test.runner.urllib.request.urlopen", side_effect=[FakeResponse(201, {"id": 7}), FakeResponse(200, {"ok": True})]) as urlopen:
                self.assertEqual(run_pipeline(pipeline, case_root, 2, root / "logs"), 0)
            mapped_request = urlopen.call_args_list[1].args[0]
            self.assertEqual(mapped_request.full_url, "https://example.test/users/7")
            self.assertEqual(dict(mapped_request.header_items())["X-user-id"], "7")
            self.assertEqual(json.loads(mapped_request.data), {"from_case": True, "user": {"id": 7}})

    def test_tag_summary_counts_failed_and_skipped_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            (case_root / "alpha" / "users").mkdir(parents=True)
            (case_root / "beta" / "orders").mkdir(parents=True)
            failed_case = {"request": {"url": "https://example.test/fail"}, "expected": {"status": 200, "strict": True}}
            skipped_case = {"request": {"url": "https://example.test/skip"}, "expected": {"status": 200}}
            (case_root / "alpha" / "users" / "fail.json").write_text(json.dumps(failed_case), encoding="utf-8")
            (case_root / "beta" / "orders" / "skip.json").write_text(json.dumps(skipped_case), encoding="utf-8")
            pipeline = root / "pipeline.json"
            pipeline.write_text(json.dumps({"steps": [
                {"name": "fail", "case": "alpha/users/fail.json"},
                {"name": "skip", "case": "beta/orders/skip.json"},
            ]}), encoding="utf-8")
            log_dir = root / "logs"
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(500, {"error": "failure"})):
                self.assertEqual(run_pipeline(pipeline, case_root, 2, log_dir), 1)
            log_content = next(log_dir.glob("api-test_*.log")).read_text(encoding="utf-8")
            self.assertIn("alpha: TOTAL 1 | PASS 0 | FAIL 1 | ERROR 0 | SKIPPED 0", log_content)
            self.assertIn("beta: TOTAL 1 | PASS 0 | FAIL 0 | ERROR 0 | SKIPPED 1", log_content)
            self.assertIn('request_value={"url": "https://example.test/fail"}', log_content)
            self.assertIn('expected_response={"status": 200}', log_content)
            self.assertIn('actual_response={"status": 500, "body": {"error": "failure"}}', log_content)
            self.assertIn('comparison_options={"strict": true}', log_content)

    def test_runs_a_single_case_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            api_dir = case_root / "single" / "health"
            api_dir.mkdir(parents=True)
            (api_dir / "get.json").write_text(json.dumps({
                "request": {"url": "https://example.test/health"},
                "expected": {"status": 200, "body": {"ok": True}},
            }), encoding="utf-8")
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"ok": True})):
                self.assertEqual(run_case_file("single/health/get.json", case_root, 2, root / "logs"), 0)

    def test_success_log_lists_every_condition_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            api_dir = case_root / "sample" / "users"
            api_dir.mkdir(parents=True)
            (api_dir / "get.json").write_text(json.dumps({
                "request": {"url": "https://example.test/users/1"},
                "expected": {
                    "status": 200,
                    "assertions": [
                        {"path": "body.name", "operator": "length_between", "min": 1, "max": 3},
                        {"path": "body.id", "operator": "gte", "value": 1},
                    ],
                    "validation_modes": {"exact_body": False, "conditions": True},
                },
            }), encoding="utf-8")
            log_dir = root / "logs"
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"id": 1, "name": "Ada"})):
                self.assertEqual(run_case_file("sample/users/get.json", case_root, 2, log_dir), 0)
            log_content = next(log_dir.glob("api-test_*.log")).read_text(encoding="utf-8")
            self.assertIn("Condition results: TOTAL 2 | PASS 2 | FAIL 0", log_content)
            self.assertIn("[PASS] $.body.name length_between: expected 1 <= length <= 3, actual length 3", log_content)
            self.assertIn("[PASS] $.body.id gte: condition met: expected >= 1", log_content)

    def test_failure_log_keeps_passed_and_failed_condition_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            api_dir = case_root / "sample" / "users"
            api_dir.mkdir(parents=True)
            (api_dir / "get.json").write_text(json.dumps({
                "request": {"url": "https://example.test/users/1"},
                "expected": {
                    "assertions": [
                        {"path": "body.name", "operator": "length_between", "min": 1, "max": 2},
                        {"path": "body.id", "operator": "gte", "value": 1},
                    ],
                    "validation_modes": {"exact_body": False, "conditions": True},
                },
            }), encoding="utf-8")
            log_dir = root / "logs"
            with patch("api_test.runner.urllib.request.urlopen", return_value=FakeResponse(200, {"id": 1, "name": "Ada"})):
                self.assertEqual(run_case_file("sample/users/get.json", case_root, 2, log_dir), 1)
            log_content = next(log_dir.glob("api-test_*.log")).read_text(encoding="utf-8")
            self.assertIn("Condition results: TOTAL 2 | PASS 1 | FAIL 1", log_content)
            self.assertIn("ERROR   [FAIL] $.body.name length_between", log_content)
            self.assertIn("INFO   [PASS] $.body.id gte", log_content)

    def test_runs_multiple_case_files_and_summarizes_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_root = root / "case"
            alpha_dir = case_root / "alpha" / "users"
            beta_dir = case_root / "beta" / "orders"
            alpha_dir.mkdir(parents=True)
            beta_dir.mkdir(parents=True)
            case = {"request": {"url": "https://example.test/resource"}, "expected": {"status": 200}}
            (alpha_dir / "get.json").write_text(json.dumps(case), encoding="utf-8")
            (beta_dir / "get.json").write_text(json.dumps(case), encoding="utf-8")
            log_dir = root / "logs"
            with patch("api_test.runner.urllib.request.urlopen", side_effect=[FakeResponse(200, {}), FakeResponse(200, {})]):
                self.assertEqual(run_case_files(["alpha/users/get.json", "beta/orders/get.json"], case_root, 2, log_dir), 0)
            log_content = next(log_dir.glob("api-test_*.log")).read_text(encoding="utf-8")
            self.assertIn("Cases result: 2 passed, 0 failed/error", log_content)
            self.assertIn("alpha: TOTAL 1 | PASS 1 | FAIL 0 | ERROR 0 | SKIPPED 0", log_content)
            self.assertIn("beta: TOTAL 1 | PASS 1 | FAIL 0 | ERROR 0 | SKIPPED 0", log_content)

    def test_cli_runs_pipeline_and_direct_cases_in_one_command(self) -> None:
        with patch("sys.argv", [
            "run_api_tests.py", "pipelines/member.json", "--case", "member/users/get.json",
        ]), patch.object(cli, "run_pipeline", return_value=0) as run_pipeline_mock, patch.object(
            cli, "run_case_files", return_value=0
        ) as run_case_files_mock:
            self.assertEqual(cli.main(), 0)
        run_pipeline_mock.assert_called_once()
        run_case_files_mock.assert_called_once()

    def test_cli_runs_all_pipelines_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pipelines" / "nested").mkdir(parents=True)
            (root / "pipelines" / "first.json").write_text("{}", encoding="utf-8")
            (root / "pipelines" / "nested" / "second.json").write_text("{}", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch("sys.argv", ["run_api_tests.py"]), patch.object(cli, "run_pipeline", return_value=0) as run_pipeline_mock:
                    self.assertEqual(cli.main(), 0)
            finally:
                os.chdir(original_cwd)
            self.assertEqual(run_pipeline_mock.call_count, 2)

    def test_cli_skips_disabled_example_pipeline_in_implicit_run_all(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pipelines").mkdir()
            (root / "pipelines" / "example.json").write_text(json.dumps({"project": "example-api.json"}), encoding="utf-8")
            (root / "pipelines" / "member.json").write_text(json.dumps({"project": "member-api.json"}), encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"EXAMPLE_PROJECT": "false"}, clear=False), patch("sys.argv", ["run_api_tests.py"]), patch.object(cli, "run_pipeline", return_value=0) as run_pipeline_mock:
                    self.assertEqual(cli.main(), 0)
            finally:
                os.chdir(original_cwd)
            self.assertEqual([call.args[0].name for call in run_pipeline_mock.call_args_list], ["member.json"])
