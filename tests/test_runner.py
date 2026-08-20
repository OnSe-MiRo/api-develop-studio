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

from api_test import cli
from api_test.cli import run_case_file, run_case_files, run_pipeline
from api_test.comparison import compare_json
from api_test.runner import ApiTestRunner, project_base_url, project_request_settings


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
                "advanced": {"proxy": "http://proxy.example.test:8080", "verify": False},
            }), encoding="utf-8")
            case = {"project": "private-api.json", "request": {"url": "/health"}, "expected": {"status": 200}}
            settings = project_request_settings(case, project_root)
            self.assertIsNotNone(settings)
            assert settings is not None
            opener = Mock()
            opener.open.return_value = FakeResponse(200, {"ok": True})
            with patch("api_test.runner.urllib.request.build_opener", return_value=opener) as build_opener:
                result = ApiTestRunner().run_case(
                    "health", case, base_url=settings.base_url, proxy_url=settings.proxy_url, verify_ssl=settings.verify_ssl,
                )
            self.assertEqual(result.status, "passed")
            self.assertEqual(opener.open.call_args.args[0].full_url, "https://example.test/health")
            self.assertEqual(build_opener.call_count, 1)

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
            "run_api_tests.py", "pipelines/sample.json", "--case", "sample/jsonplaceholder/get_post.json",
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
