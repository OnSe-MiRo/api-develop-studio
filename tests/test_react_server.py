from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet

from api_test.collaboration_store import CollaborationStore
from api_test.project_variables import case_variables_for_client, decrypt_secret, project_variables_for_client
from react_server import (
    EXAMPLE_API_KEY,
    EXAMPLE_PROJECT_REFERENCE,
    StudioHandler,
    case_summaries,
    ensure_example_project_security_key,
    delete_project_pipelines,
    example_openapi_document,
    example_project_enabled,
    openapi_operations,
    normalize_project_document,
    normalize_case_document,
    project_has_cases,
    project_json_files,
    project_summaries,
    validate_project_document,
    visible_project_files,
)


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
                "expected": {
                    "status": 200, "strict": True, "body": {"score": 9},
                    "assertions": [{"path": "body.score", "operator": "gte", "value": 8}],
                    "validation_modes": {"exact_body": False, "conditions": True},
                },
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
            self.assertEqual(document["expected"]["assertions"][0]["path"], "body.score")
            self.assertEqual(document["expected"]["validation_modes"], {"exact_body": False, "conditions": True})
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

    def test_example_project_switch_controls_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / EXAMPLE_PROJECT_REFERENCE).write_text("{}", encoding="utf-8")
            (root / "member.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertTrue(example_project_enabled())
                self.assertEqual(visible_project_files(root), [EXAMPLE_PROJECT_REFERENCE, "member.json"])
            with patch.dict(os.environ, {"EXAMPLE_PROJECT": "false"}, clear=False):
                self.assertFalse(example_project_enabled())
                self.assertEqual(visible_project_files(root), ["member.json"])
            with patch.dict(os.environ, {"EXAMPLE_PROJECT": "true"}, clear=False):
                self.assertTrue(example_project_enabled())
                self.assertEqual(visible_project_files(root), [EXAMPLE_PROJECT_REFERENCE, "member.json"])

    def test_project_summaries_return_name_and_base_url_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "member.json").write_text(json.dumps({
                "name": "Member API",
                "base_url": "https://api.example.test",
                "variables": {"secret": {"api_key": "encrypted-value"}},
            }), encoding="utf-8")

            self.assertEqual(project_summaries(root, ["member.json"]), {
                "member.json": {"name": "Member API", "base_url": "https://api.example.test"},
            })

    def test_example_api_returns_404_when_disabled(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.command = "GET"
        handler.api_path = Mock(return_value=["example-api", "health"])
        handler.send_json = Mock()

        with patch.dict(os.environ, {"EXAMPLE_PROJECT": "false"}, clear=False):
            self.assertTrue(handler.serve_example_api())

        handler.send_json.assert_called_once_with(404, {"error": "Example API is disabled. Set EXAMPLE_PROJECT=true to enable it."})

    def test_example_api_serves_user_when_enabled(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.command = "GET"
        handler.api_path = Mock(return_value=["example-api", "users", "1"])
        handler.send_json = Mock()

        with patch.dict(os.environ, {"EXAMPLE_PROJECT": "true"}, clear=False):
            self.assertTrue(handler.serve_example_api())

        handler.send_json.assert_called_once_with(200, {"id": 1, "name": "Ada"})

    def test_example_api_accepts_demo_api_key(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.command = "GET"
        handler.headers = {"X-API-Key": EXAMPLE_API_KEY}
        handler.api_path = Mock(return_value=["example-api", "secure-data"])
        handler.send_json = Mock()

        with patch.dict(os.environ, {"EXAMPLE_PROJECT": "true"}, clear=False):
            self.assertTrue(handler.serve_example_api())

        handler.send_json.assert_called_once_with(200, {"authorized": True, "message": "API key accepted"})

    def test_example_api_rejects_missing_or_wrong_api_key(self) -> None:
        for headers in ({}, {"X-API-Key": "wrong-api-key"}):
            with self.subTest(headers=headers):
                handler = object.__new__(StudioHandler)
                handler.command = "GET"
                handler.headers = headers
                handler.api_path = Mock(return_value=["example-api", "secure-data"])
                handler.send_json = Mock()

                with patch.dict(os.environ, {"EXAMPLE_PROJECT": "true"}, clear=False):
                    self.assertTrue(handler.serve_example_api())

                handler.send_json.assert_called_once_with(401, {"error": "Invalid or missing API key"})

    def test_example_openapi_documents_api_key_security(self) -> None:
        document = example_openapi_document()

        self.assertEqual(
            document["components"]["securitySchemes"]["ApiKeyAuth"],
            {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        )
        self.assertEqual(
            document["paths"]["/example-api/secure-data"]["get"]["security"],
            [{"ApiKeyAuth": []}],
        )

    def test_case_summaries_return_request_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "member" / "users").mkdir(parents=True)
            reference = "member/users/get.json"
            (root / reference).write_text(
                json.dumps({"request": {"url": "/users?page=1"}}), encoding="utf-8"
            )
            self.assertEqual(case_summaries(root, [reference]), {reference: {"url": "/users?page=1"}})

    def test_openapi_operations_include_request_and_response_examples(self) -> None:
        document = {
            "openapi": "3.0.3",
            "paths": {
                "/users/{userId}": {
                    "parameters": [{"name": "userId", "in": "path", "schema": {"type": "integer", "example": 7}}],
                    "post": {
                        "summary": "Create a user setting",
                        "parameters": [
                            {"name": "dryRun", "in": "query", "schema": {"type": "boolean", "default": True}},
                            {"name": "X-Client", "in": "header", "example": "studio"},
                        ],
                        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserInput"}}}},
                        "responses": {"201": {"content": {"application/json": {"examples": {"created": {"value": {"id": 7, "name": "Ada"}}}}}}},
                    },
                },
            },
            "components": {"schemas": {"UserInput": {"type": "object", "properties": {"name": {"example": "Ada"}, "enabled": {"type": "boolean"}}}}},
        }

        operations = openapi_operations(document)

        self.assertEqual(len(operations), 1)
        operation = operations[0]
        self.assertEqual(operation["method"], "POST")
        self.assertEqual(operation["path"], "/users/{userId}")
        self.assertEqual(operation["parameters"], [
            {"name": "userId", "in": "path", "value": 7},
            {"name": "dryRun", "in": "query", "value": True},
            {"name": "X-Client", "in": "header", "value": "studio"},
        ])
        self.assertEqual(operation["request_body"], {"name": "Ada", "enabled": False})
        self.assertEqual(operation["expected_status"], 201)
        self.assertEqual(operation["response_body"], {"id": 7, "name": "Ada"})

    def test_docs_endpoint_accepts_uploaded_json_document(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.api_path = Mock(return_value=["api", "docs"])
        handler.read_body = Mock(return_value={
            "document": {
                "openapi": "3.0.3",
                "paths": {"/health": {"get": {"responses": {"200": {"description": "OK"}}}}},
            },
        })
        handler.send_json = Mock()

        handler.do_POST()

        response = handler.send_json.call_args.args
        self.assertEqual(response[0], 200)
        self.assertEqual(response[1]["operations"][0]["id"], "GET /health")

    def test_project_docs_url_must_be_an_absolute_http_url(self) -> None:
        payload = {"name": "Member", "base_url": "https://api.example.test", "docs_url": "https://api.example.test/openapi.yaml"}
        validate_project_document(payload)
        with self.assertRaisesRegex(ValueError, "docs_url"):
            validate_project_document({**payload, "docs_url": "/openapi.yaml"})

    def test_project_accepts_uploaded_json_docs_instead_of_url(self) -> None:
        docs_file = {
            "name": "openapi.json",
            "document": {"openapi": "3.0.3", "paths": {}},
        }
        payload = {"name": "Member", "base_url": "https://api.example.test", "docs_url": "", "docs_file": docs_file}

        validate_project_document(payload)

        with self.assertRaisesRegex(ValueError, "either"):
            validate_project_document({**payload, "docs_url": "https://api.example.test/openapi.json"})
        with self.assertRaisesRegex(ValueError, "JSON filename"):
            validate_project_document({**payload, "docs_file": {**docs_file, "name": "openapi.yaml"}})

    def test_project_secrets_are_encrypted_masked_and_preserved(self) -> None:
        key = Fernet.generate_key().decode()
        payload = {
            "name": "Member",
            "base_url": "https://api.example.test",
            "variables": {
                "plain": {"tenant": "alpha"},
                "secret": {"api_key": {"value": "private-api-key"}},
            },
        }
        with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": key}, clear=False):
            stored = normalize_project_document(payload)

        self.assertEqual(stored["variables"]["plain"], {"tenant": "alpha"})
        encrypted = stored["variables"]["secret"]["api_key"]
        self.assertNotEqual(encrypted, "private-api-key")
        self.assertNotIn("private-api-key", json.dumps(stored))
        self.assertEqual(
            project_variables_for_client(stored)["variables"]["secret"],
            {"api_key": {"configured": True}},
        )

        preserved_payload = {
            **payload,
            "variables": {
                "plain": {"tenant": "beta"},
                "secret": {"api_key": {"preserve": True}},
            },
        }
        preserved = normalize_project_document(preserved_payload, stored)
        self.assertEqual(preserved["variables"]["secret"]["api_key"], encrypted)

    def test_project_secret_save_requires_encryption_key(self) -> None:
        payload = {
            "name": "Member",
            "base_url": "https://api.example.test",
            "variables": {
                "plain": {},
                "secret": {"api_key": {"value": "private-api-key"}},
            },
        }
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "API_TEST_ENCRYPTION_KEY"):
                normalize_project_document(payload)

    def test_case_secrets_are_encrypted_masked_and_preserved(self) -> None:
        key = Fernet.generate_key().decode()
        payload = {
            "project": "member.json",
            "request": {"url": "/secure"},
            "expected": {"status": 200},
            "variables": {"secret": {"api_key": {"value": "case-private-key"}}},
        }
        with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": key, "API_TEST_ENCRYPTION_URL": ""}, clear=False):
            stored = normalize_case_document(payload)
            token = stored["variables"]["secret"]["api_key"]
            preserved = normalize_case_document({
                **payload,
                "variables": {"secret": {"api_key": {"preserve": True}}},
            }, stored)

        self.assertNotEqual(token, "case-private-key")
        self.assertEqual(case_variables_for_client(stored)["variables"]["secret"], {"api_key": {"configured": True}})
        self.assertEqual(preserved["variables"]["secret"]["api_key"], token)

    def test_example_project_adds_an_encrypted_shared_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "projects"
            project_root.mkdir()
            (project_root / EXAMPLE_PROJECT_REFERENCE).write_text(json.dumps({
                "name": "Example API",
                "base_url": "https://api.example.test",
                "variables": {"plain": {}, "secret": {"test_key": "existing-token"}},
            }), encoding="utf-8")
            store = CollaborationStore(root / "studio.db", {
                "projects": project_root,
                "cases": root / "case",
                "pipelines": root / "pipelines",
            })
            store.initialize()
            key = Fernet.generate_key().decode()

            with patch.dict(os.environ, {"API_TEST_ENCRYPTION_KEY": key, "API_TEST_ENCRYPTION_URL": ""}, clear=False):
                ensure_example_project_security_key(store)
                document = store.get("projects", EXAMPLE_PROJECT_REFERENCE)
                assert document is not None
                self.assertEqual(decrypt_secret(document.document["variables"]["secret"]["api_key"]), EXAMPLE_API_KEY)
                self.assertEqual(document.document["variables"]["secret"]["test_key"], "existing-token")

    def test_deletes_only_pipelines_connected_to_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipeline_root = root / "pipelines"
            case_root = root / "case"
            pipeline_root.mkdir()
            case_root.mkdir()
            (pipeline_root / "member.json").write_text(json.dumps({"project": "member-api.json", "steps": []}), encoding="utf-8")
            (pipeline_root / "other.json").write_text(json.dumps({"project": "other-api.json", "steps": []}), encoding="utf-8")
            self.assertFalse(project_has_cases("member-api.json", case_root))
            self.assertEqual(delete_project_pipelines("member-api.json", pipeline_root), ["member.json"])
            self.assertFalse((pipeline_root / "member.json").exists())
            self.assertTrue((pipeline_root / "other.json").exists())


if __name__ == "__main__":
    unittest.main()
