from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from react_server import StudioHandler, project_json_files


class ReactServerRunTest(unittest.TestCase):
    def handler_for(self, payload: dict[str, object]) -> tuple[StudioHandler, Mock]:
        handler = object.__new__(StudioHandler)
        handler.api_path = Mock(return_value=["api", "run"])
        handler.read_body = Mock(return_value=payload)
        send_json = Mock()
        handler.send_json = send_json
        return handler, send_json

    def test_runs_inline_case_from_temporary_file(self) -> None:
        payload = {
            "caseReference": "draft/users/current.json",
            "inlineCase": {
                "request": {"url": "https://example.test/users"},
                "expected": {"status": 200, "strict": True, "body": {"score": 9}},
                "_expectedBodyRaw": '{"score": 9.0}',
            },
        }
        handler, send_json = self.handler_for(payload)
        temporary_path: Path | None = None

        def execute(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal temporary_path
            case_root = Path(command[command.index("--case-root") + 1])
            reference = command[command.index("--case") + 1]
            temporary_path = case_root / reference
            document = json.loads(temporary_path.read_text(encoding="utf-8"))
            self.assertEqual(document["expected"]["body"]["score"], 9.0)
            self.assertIsInstance(document["expected"]["body"]["score"], float)
            self.assertNotIn("_expectedBodyRaw", document)
            return subprocess.CompletedProcess(command, 0, "inline case passed", "")

        with patch("react_server.subprocess.run", side_effect=execute):
            handler.do_POST()

        self.assertIsNotNone(temporary_path)
        self.assertFalse(temporary_path.exists())
        send_json.assert_called_once_with(200, {"exitCode": 0, "output": "inline case passed"})

    def test_runs_inline_pipeline_from_temporary_file(self) -> None:
        pipeline = {
            "defaults": {"retry": 1, "retry_interval_seconds": 0.2},
            "steps": [{"name": "users", "case": "sample/users/get.json"}],
        }
        handler, send_json = self.handler_for({"inlinePipeline": pipeline})
        temporary_path: Path | None = None

        def execute(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal temporary_path
            temporary_path = Path(command[2])
            self.assertEqual(json.loads(temporary_path.read_text(encoding="utf-8")), pipeline)
            return subprocess.CompletedProcess(command, 1, "inline pipeline failed", "")

        with patch("react_server.subprocess.run", side_effect=execute):
            handler.do_POST()

        self.assertIsNotNone(temporary_path)
        self.assertFalse(temporary_path.exists())
        send_json.assert_called_once_with(200, {"exitCode": 1, "output": "inline pipeline failed"})

    def test_filters_saved_documents_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "member").mkdir()
            (root / "member" / "get.json").write_text(json.dumps({"project": "member.json"}), encoding="utf-8")
            (root / "member" / "legacy.json").write_text(json.dumps({"request": {}}), encoding="utf-8")
            self.assertEqual(project_json_files(root, "member.json"), ["member/get.json"])


if __name__ == "__main__":
    unittest.main()
