from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from api_test.execution_history import ExecutionHistory
from react_server import StudioHandler, execute_studio_run, execution_metadata


class ExecutionHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.history = ExecutionHistory(self.root / "studio.db")
        self.now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)

    def record(
        self,
        status: str = "passed",
        projects: list[str] | None = None,
        started_at: str = "2026-09-12T10:00:00+00:00",
        duration_ms: float = 100,
    ) -> str:
        run_id = str(uuid.uuid4())
        self.history.record(
            run_id=run_id,
            started_at=started_at,
            finished_at="2026-09-12T10:00:00.100000+00:00",
            duration_ms=duration_ms,
            status=status,
            exit_code=0 if status == "passed" else 1,
            projects=projects or ["a.json"],
            targets=[{"kind": "case", "reference": "a/users/get.json", "preview": False}],
        )
        return run_id

    def test_empty_history_has_no_fabricated_rate_or_duration(self) -> None:
        data = self.history.dashboard(now=self.now)
        self.assertEqual(data["summary"]["total"], 0)
        self.assertIsNone(data["summary"]["successRate"])
        self.assertIsNone(data["summary"]["averageDurationMs"])
        self.assertEqual(len(data["trend"]), 7)

    def test_project_period_and_status_filters_do_not_double_count_mixed_run(self) -> None:
        self.record(projects=["a.json", "b.json", "a.json"])
        self.record("failed", duration_ms=300)
        self.record("timeout", projects=["b.json"])
        self.record(started_at="2026-09-05T23:59:59+00:00")
        self.record(started_at="2026-09-13T00:00:00+00:00")
        data = self.history.dashboard(project="a.json", status="failed", now=self.now)
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["successRate"], 50)
        self.assertEqual(data["summary"]["averageDurationMs"], 200)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["status"], "failed")
        self.assertEqual(self.history.dashboard(now=self.now)["summary"]["total"], 3)
        self.assertEqual(self.history.dashboard(project="' OR 1=1 --", now=self.now)["total"], 0)

    def test_pagination_persistence_and_concurrent_writers(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.record(), range(25)))
        reopened = ExecutionHistory(self.history.path)
        first = reopened.dashboard(now=self.now)
        second = reopened.dashboard(now=self.now, page=2)
        self.assertEqual(first["total"], 25)
        self.assertEqual(len(first["items"]), 20)
        self.assertEqual(len(second["items"]), 5)
        self.assertFalse({item["runId"] for item in first["items"]} & {item["runId"] for item in second["items"]})

    def test_invalid_filters_and_status(self) -> None:
        for options in ({"days": 0}, {"days": 365}, {"page": 0}, {"page": 10**100}, {"status": "running"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.history.dashboard(**options)
        with self.assertRaises(ValueError):
            self.record("running")

    def test_metadata_for_saved_inline_and_implicit_targets(self) -> None:
        cases, pipelines = self.root / "case", self.root / "pipelines"
        cases.mkdir()
        pipelines.mkdir()
        (cases / "get.json").write_text(json.dumps({"project": "a.json"}), encoding="utf-8")
        (pipelines / "smoke.json").write_text(json.dumps({"project": "b.json"}), encoding="utf-8")
        (pipelines / "sample.json").write_text(json.dumps({"project": "example-api.json"}), encoding="utf-8")
        with patch("react_server.CASE_ROOT", cases), patch("react_server.PIPELINE_ROOT", pipelines):
            projects, targets = execution_metadata({"cases": ["get.json"], "pipelines": ["smoke.json"]})
            self.assertEqual(projects, ["a.json", "b.json"])
            self.assertEqual(len(targets), 2)
            with patch.dict("os.environ", {"EXAMPLE_PROJECT": "false"}):
                projects, targets = execution_metadata({})
                self.assertEqual(projects, ["b.json"])
                self.assertEqual(len(targets), 1)
        projects, targets = execution_metadata({"inlinePipeline": {"project": "draft.json", "steps": []}})
        self.assertEqual(projects, ["draft.json"])
        self.assertTrue(targets[0]["preview"])

    def test_execution_outcomes_use_run_id_without_persisting_sensitive_output(self) -> None:
        body = {"inlineCase": {"project": "a.json", "request": {"password": "private-value"}}}
        with patch("react_server.execution_history", return_value=self.history):
            for code, expected in ((0, "passed"), (1, "failed"), (2, "error")):
                with patch("react_server.subprocess.run", return_value=subprocess.CompletedProcess([], code, "private-value", "")):
                    response = execute_studio_run(["runner"], body)
                uuid.UUID(response["runId"])
                self.assertEqual(response["exitCode"], code)
                self.assertEqual(self.history.dashboard()["items"][0]["status"], expected)
            error = subprocess.TimeoutExpired("runner", 300)
            with patch("react_server.subprocess.run", side_effect=error), self.assertRaises(subprocess.TimeoutExpired) as raised:
                execute_studio_run(["runner"], body)
            uuid.UUID(raised.exception.run_id)
            self.assertEqual(self.history.dashboard()["items"][0]["status"], "timeout")
        self.assertNotIn(b"private-value", self.history.path.read_bytes())

    def test_record_failure_preserves_execution_response_with_warning(self) -> None:
        broken = Mock()
        broken.record.side_effect = sqlite3.OperationalError("disk full")
        with patch("react_server.execution_history", return_value=broken), patch(
            "react_server.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "done", "")
        ), self.assertLogs(level="WARNING"):
            response = execute_studio_run(["runner"], {"inlineCase": {}})
        self.assertEqual(response["exitCode"], 0)
        self.assertEqual(response["output"], "done")
        self.assertIn("historyWarning", response)

    def test_dashboard_http_defaults_and_validation(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.serve_example_api = Mock(return_value=False)
        handler.path = "/api/dashboard"
        handler.send_json = Mock()
        with patch("react_server.execution_history", return_value=self.history):
            handler.do_GET()
            self.assertEqual(handler.send_json.call_args.args[0], 200)
            self.assertEqual(handler.send_json.call_args.args[1]["summary"]["total"], 0)
            for query in ("days=foo", "days=1", "status=running", "page=-1", "page=" + "9" * 100):
                handler.path = "/api/dashboard?" + query
                handler.do_GET()
                self.assertEqual(handler.send_json.call_args.args[0], 400)


if __name__ == "__main__":
    unittest.main()
