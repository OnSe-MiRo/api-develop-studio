from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
import yaml

from api_test.collaboration_store import CollaborationStore
from api_test.project_variables import case_variables_for_client, decrypt_secret, project_variables_for_client
from react_server import (
    EXAMPLE_API_KEY,
    EXAMPLE_PROJECT_REFERENCE,
    StudioHandler,
    case_summaries,
    ensure_example_project_security_key,
    author_openapi_operation,
    generate_openapi_archive,
    delete_project_pipelines,
    example_openapi_document,
    example_project_enabled,
    load_openapi_document,
    openapi_operations,
    normalize_project_document,
    normalize_case_document,
    project_has_cases,
    project_openapi_document,
    resolve_openapi_bundle,
    split_openapi_bundle,
    project_json_files,
    project_summaries,
    validate_project_document,
    visible_project_files,
)


class ReactServerRunTest(unittest.TestCase):
    def test_normalize_case_preserves_response_time_limit(self) -> None:
        for limit in [0.5, 125]:
            with self.subTest(limit=limit):
                document = normalize_case_document({"expected": {"status": 200, "max_response_time_ms": limit}, "_expectedBodyRaw": "{}"})
                self.assertEqual(document["expected"], {"status": 200, "max_response_time_ms": limit, "body": {}})
        self.assertNotIn("max_response_time_ms", normalize_case_document({"expected": {"status": 200}})["expected"])

    def test_normalize_case_rejects_invalid_response_time_limit(self) -> None:
        for limit in [0, -1, True, "125", None, float("nan"), float("inf"), [], {}]:
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "expected.max_response_time_ms"):
                normalize_case_document({"expected": {"status": 200, "max_response_time_ms": limit}})

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
                    "max_response_time_ms": 125,
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
            self.assertEqual(document["expected"]["max_response_time_ms"], 125)
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
                        "tags": ["Users"],
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
        self.assertEqual(operation["tag"], "Users")
        self.assertEqual(operation["parameters"], [
            {"name": "userId", "in": "path", "value": 7},
            {"name": "dryRun", "in": "query", "value": True},
            {"name": "X-Client", "in": "header", "value": "studio"},
        ])
        self.assertEqual(operation["request_body"], {"name": "Ada", "enabled": False})
        self.assertEqual(operation["expected_status"], 201)
        self.assertEqual(operation["response_body"], {"id": 7, "name": "Ada"})

    def test_date_and_date_time_parameter_examples_keep_entered_strings(self) -> None:
        document = {
            "openapi": "3.0.3",
            "paths": {
                "/events": {
                    "get": {
                        "parameters": [{
                            "name": "from", "in": "query",
                            "schema": {"type": "string", "format": "date"},
                            "example": "2026-08-31",
                        }, {
                            "name": "at", "in": "query",
                            "schema": {"type": "string", "format": "date-time"},
                            "example": "2026-08-31T12:34:56.000+09:00",
                        }],
                        "responses": {"200": {"description": "OK"}},
                    },
                },
            },
        }

        operation = openapi_operations(document, for_case=True)[0]

        self.assertEqual(operation["parameters"][0]["value"], "2026-08-31")
        self.assertEqual(operation["parameters"][1]["value"], "2026-08-31T12:34:56.000+09:00")

    def test_yaml_date_parameter_example_is_json_safe(self) -> None:
        document = yaml.safe_load("""
openapi: 3.0.3
paths:
  /events:
    get:
      parameters:
        - name: from
          in: query
          schema:
            type: string
            format: date
          example: 2026-08-31
      responses:
        '200':
          description: OK
""")

        operation = openapi_operations(document, for_case=True)[0]

        self.assertEqual(operation["parameters"][0]["value"], "2026-08-31")
        json.dumps(operation)

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

    def test_docs_endpoint_can_bypass_proxies(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.api_path = Mock(return_value=["api", "docs"])
        handler.read_body = Mock(return_value={"url": "https://api.example.test/openapi.json", "no_proxy": True, "for_case": True})
        handler.send_json = Mock()

        with patch("react_server.load_openapi_document", return_value=[]) as load_document:
            handler.do_POST()

        load_document.assert_called_once_with("https://api.example.test/openapi.json", no_proxy=True, for_case=True)

    def test_docs_endpoint_accepts_split_openapi_bundle(self) -> None:
        document, _operation = author_openapi_operation({"name": "Member"}, {
            "method": "GET", "path": "/members", "operation_id": "listMembers",
            "response_status": 200, "response_description": "OK", "error_statuses": [400],
        })
        handler = object.__new__(StudioHandler)
        handler.api_path = Mock(return_value=["api", "docs"])
        handler.read_body = Mock(return_value={"bundle": split_openapi_bundle(document)})
        handler.send_json = Mock()

        handler.do_POST()

        response = handler.send_json.call_args.args
        self.assertEqual(response[0], 200)
        self.assertEqual(response[1]["operations"][0]["responses"][1]["status"], 400)

    def test_date_parameter_normalization_is_case_specific(self) -> None:
        from datetime import datetime

        document = {
            "openapi": "3.0.3",
            "paths": {"/events": {"get": {
                "parameters": [{
                    "name": "at", "in": "query",
                    "schema": {"type": "string", "format": "date-time"},
                    "example": datetime(2026, 8, 31, 12, 34, 56),
                }],
                "responses": {"200": {"description": "OK"}},
            }}},
        }

        authoring_value = openapi_operations(document)[0]["parameters"][0]["value"]
        case_value = openapi_operations(document, for_case=True)[0]["parameters"][0]["value"]

        self.assertIsInstance(authoring_value, datetime)
        self.assertEqual(case_value, "2026-08-31T12:34:56")

    def test_openapi_authoring_endpoint_saves_a_project_revision(self) -> None:
        handler = object.__new__(StudioHandler)
        handler.api_path = Mock(return_value=["api", "projects", "member.json", "openapi", "operations"])
        handler.read_body = Mock(return_value={
            "method": "GET", "path": "/members", "operation_id": "listMembers",
            "summary": "회원 목록", "response_status": 200, "response_description": "OK",
            "_storage": {"revision": 3},
        })
        handler.actor_id = Mock(return_value="author")
        handler.send_json = Mock()
        current = Mock(document={
            "name": "Member API", "base_url": "https://api.example.test", "docs_url": "",
            "docs_file": {"name": "openapi.json", "document": {
                "openapi": "3.0.3", "info": {"title": "Member API", "version": "1.0.0"}, "paths": {},
            }},
            "variables": {"plain": {}, "secret": {"api_key": "encrypted-value"}},
        })
        saved = Mock()
        saved.metadata.return_value = {"revision": 4}
        store = Mock()
        store.get.return_value = current
        store.save.return_value = saved

        with patch("react_server.collaboration_store", return_value=store):
            handler.do_POST()

        saved_project = store.save.call_args.args[2]
        self.assertEqual(store.save.call_args.kwargs["expected_revision"], 3)
        self.assertEqual(store.save.call_args.kwargs["action"], "author_openapi_operation")
        self.assertEqual(saved_project["variables"]["secret"]["api_key"], "encrypted-value")
        self.assertNotIn("docs_file", saved_project)
        resolved = resolve_openapi_bundle(saved_project["docs_bundle"])
        self.assertEqual(resolved["paths"]["/members"]["get"]["operationId"], "listMembers")
        handler.send_json.assert_called_once_with(200, {
            "operation": resolved["paths"]["/members"]["get"],
            "_storage": {"revision": 4},
        })

    def test_openapi_url_errors_include_http_cause(self) -> None:
        from urllib.error import HTTPError

        error = HTTPError("https://api.example.test/openapi.json", 404, "Not Found", None, None)
        with patch("react_server.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 404 Not Found"):
                load_openapi_document("https://api.example.test/openapi.json")

    def test_openapi_url_timeout_has_a_clear_cause(self) -> None:
        with patch("react_server.urlopen", side_effect=TimeoutError):
            with self.assertRaisesRegex(ValueError, "request timed out"):
                load_openapi_document("https://api.example.test/openapi.json")

    def test_project_openapi_document_requires_a_configured_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "OpenAPI"):
            project_openapi_document({"name": "Member"})

    def test_authors_openapi_operation_with_parameters_and_examples(self) -> None:
        document, operation = author_openapi_operation({"name": "Member API"}, {
            "method": "POST", "path": "/members/{memberId}", "operation_id": "updateMember",
            "summary": "회원 수정", "tag": "Members",
            "parameters": [
                {"name": "dryRun", "in": "query", "type": "boolean", "example": True},
                {"name": "X-Request-Id", "in": "header", "type": "string", "required": True, "example": "req-1"},
            ],
            "has_request_body": True, "request_body_required": True, "request_body": {"name": "Ada"},
            "response_status": 200, "response_description": "Updated",
            "has_response_body": True, "response_body": {"id": 7, "name": "Ada"},
            "error_statuses": [400, 404, 500],
        })

        self.assertEqual(document["info"]["title"], "Member API")
        self.assertEqual(operation["operationId"], "updateMember")
        self.assertEqual(operation["parameters"][1]["in"], "header")
        self.assertEqual(operation["parameters"][2]["name"], "memberId")
        normalized = openapi_operations(document)[0]
        self.assertEqual(normalized["tag"], "Members")
        self.assertEqual(normalized["parameters"][1], {"name": "X-Request-Id", "in": "header", "value": "req-1"})
        self.assertEqual(normalized["request_body"], {"name": "Ada"})
        self.assertEqual(normalized["response_body"], {"id": 7, "name": "Ada"})

    def test_splits_and_resolves_openapi_bundle_with_common_errors(self) -> None:
        document, _operation = author_openapi_operation({"name": "Member API"}, {
            "method": "GET", "path": "/members/{memberId}", "operation_id": "getMember",
            "response_status": 200, "response_description": "OK", "error_statuses": [400, 404],
            "has_response_body": True, "response_body": {"id": 7, "name": "Ada"},
        })

        bundle = split_openapi_bundle(document)
        files = bundle["files"]
        self.assertIn("openapi.yaml", files)
        self.assertIn("components/error.yaml", files)
        self.assertTrue(any(path.startswith("paths/") for path in files))
        self.assertTrue(any(path.startswith("components/schemas/") for path in files))
        resolved = resolve_openapi_bundle(bundle)
        operation = resolved["paths"]["/members/{memberId}"]["get"]
        self.assertEqual(operation["responses"]["400"]["description"], "잘못된 요청")
        self.assertEqual(operation["responses"]["404"]["content"]["application/json"]["example"]["code"], "RESOURCE_NOT_FOUND")
        resplit = split_openapi_bundle(resolved)
        path_content = next(content for path, content in resplit["files"].items() if path.startswith("paths/"))
        self.assertIn("../openapi.yaml#/components/responses/BadRequest", path_content)

    def test_openapi_bundle_rejects_external_or_escaping_references(self) -> None:
        for reference in ("https://example.test/schema.yaml", "../outside.yaml"):
            with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, "외부 URL|내부 YAML"):
                resolve_openapi_bundle({
                    "entrypoint": "openapi.yaml",
                    "files": {"openapi.yaml": yaml.safe_dump({
                        "openapi": "3.0.3", "info": {"title": "API", "version": "1"},
                        "paths": {"/items": {"$ref": reference}},
                    })},
                })

    def test_authored_api_rejects_duplicate_or_swagger_document(self) -> None:
        payload = {
            "method": "GET", "path": "/members", "operation_id": "listMembers",
            "response_status": 200, "response_description": "OK",
        }
        document, _operation = author_openapi_operation({"name": "Member"}, payload)
        with self.assertRaisesRegex(ValueError, "이미 작성된"):
            author_openapi_operation({"name": "Member"}, payload, document)
        with self.assertRaisesRegex(ValueError, "Operation ID"):
            author_openapi_operation({"name": "Member"}, {**payload, "path": "/accounts"}, document)
        with self.assertRaisesRegex(ValueError, "OpenAPI 3"):
            author_openapi_operation({"name": "Member"}, payload, {"swagger": "2.0", "paths": {}})

    def test_generates_language_client_zip_with_normalized_yaml(self) -> None:
        document = {
            "openapi": "3.0.3",
            "info": {"title": "Member API", "version": "1.0.0"},
            "paths": {"/members": {"get": {"responses": {"200": {"description": "OK"}}}}},
        }

        def execute(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command[command.index("-g") + 1], "typescript-axios")
            source_path = Path(command[command.index("-i") + 1])
            self.assertIn("openapi: 3.0.3", source_path.read_text(encoding="utf-8"))
            output_path = Path(command[command.index("-o") + 1])
            output_path.mkdir()
            (output_path / "README.md").write_text("generated client", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "generated", "")

        def command_for(source_path: Path, generator: str, output_path: Path) -> list[str]:
            return ["java", "-jar", "generator.jar", "generate", "-i", str(source_path), "-g", generator, "-o", str(output_path)]

        with patch("react_server.openapi_generator_command", side_effect=command_for), patch("react_server.subprocess.run", side_effect=execute):
            archive, filename = generate_openapi_archive(document, "typescript", "Member API")

        self.assertEqual(filename, "member-api-typescript-client.zip")
        with zipfile.ZipFile(BytesIO(archive)) as generated:
            self.assertEqual(
                sorted(generated.namelist()),
                [
                    "member-api-typescript-client/README.md",
                    "member-api-typescript-client/openapi.yaml",
                ],
            )
            self.assertIn("title: Member API", generated.read("member-api-typescript-client/openapi.yaml").decode())

    def test_generates_client_zip_with_split_openapi_sources(self) -> None:
        document, _operation = author_openapi_operation({"name": "Member API"}, {
            "method": "GET", "path": "/members", "operation_id": "listMembers",
            "response_status": 200, "response_description": "OK", "error_statuses": [400],
        })
        bundle = split_openapi_bundle(document)

        def command_for(source_path: Path, generator: str, output_path: Path) -> list[str]:
            self.assertEqual(source_path.name, "openapi.yaml")
            self.assertTrue((source_path.parent / "components" / "error.yaml").is_file())
            self.assertTrue(any((source_path.parent / "paths").glob("*.yaml")))
            output_path.mkdir()
            (output_path / "README.md").write_text("generated", encoding="utf-8")
            return ["generator"]

        with patch("react_server.openapi_generator_command", side_effect=command_for), patch(
            "react_server.subprocess.run", return_value=subprocess.CompletedProcess(["generator"], 0, "", ""),
        ):
            archive, _filename = generate_openapi_archive(document, "typescript", "Member API", bundle)

        with zipfile.ZipFile(BytesIO(archive)) as generated:
            self.assertIn("member-api-typescript-client/openapi/openapi.yaml", generated.namelist())
            self.assertIn("member-api-typescript-client/openapi/components/error.yaml", generated.namelist())
            self.assertTrue(any(name.startswith("member-api-typescript-client/openapi/paths/") for name in generated.namelist()))

    def test_rejects_unsupported_generation_language(self) -> None:
        with self.assertRaisesRegex(ValueError, "지원하지 않는"):
            generate_openapi_archive({"openapi": "3.0.3", "paths": {}}, "ruby", "Member")

    def test_project_docs_url_must_be_an_absolute_http_url(self) -> None:
        payload = {"name": "Member", "base_url": "https://api.example.test", "docs_url": "https://api.example.test/openapi.yaml"}
        validate_project_document(payload)
        with self.assertRaisesRegex(ValueError, "docs_url"):
            validate_project_document({**payload, "docs_url": "/openapi.yaml"})
        with self.assertRaisesRegex(ValueError, "use_proxy"):
            validate_project_document({**payload, "advanced": {"use_proxy": "false"}})

    def test_project_accepts_uploaded_json_docs_instead_of_url(self) -> None:
        docs_file = {
            "name": "openapi.json",
            "document": {"openapi": "3.0.3", "paths": {}},
        }
        payload = {"name": "Member", "base_url": "https://api.example.test", "docs_url": "", "docs_file": docs_file}

        validate_project_document(payload)
        bundle = split_openapi_bundle(docs_file["document"])
        validate_project_document({"name": "Member", "base_url": "https://api.example.test", "docs_url": "", "docs_bundle": bundle})

        with self.assertRaisesRegex(ValueError, "either"):
            validate_project_document({**payload, "docs_url": "https://api.example.test/openapi.json"})
        with self.assertRaisesRegex(ValueError, "JSON filename"):
            validate_project_document({**payload, "docs_file": {**docs_file, "name": "openapi.yaml"}})
        with self.assertRaisesRegex(ValueError, "either"):
            validate_project_document({**payload, "docs_bundle": bundle})

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
