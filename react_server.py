"""Local REST server used by the React API Develop Studio."""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

import yaml

from api_test.collaboration_store import (
    CollaborationStore,
    CollaborationStoreError,
    DocumentNotFoundError,
    RevisionConflictError,
    RevisionRequiredError,
)
from api_test.project_variables import (
    ProjectVariableError,
    case_variables_for_client,
    normalize_case_variables,
    normalize_project_variables,
    project_variables_for_client,
)


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT / "case"
PIPELINE_ROOT = ROOT / "pipelines"
PROJECT_ROOT = ROOT / "projects"
WEB_DIST = ROOT / "web" / "dist"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
EXAMPLE_PROJECT_REFERENCE = "example-api.json"
EXAMPLE_PROJECT_TRUE_VALUES = {"1", "true", "yes", "on"}
EXAMPLE_API_KEY = "example-api-key"
MISSING = object()
_COLLABORATION_STORE: CollaborationStore | None = None


class ApiError(ValueError):
    pass


def collaboration_store() -> CollaborationStore:
    """Return the lazily initialized versioned document store."""
    global _COLLABORATION_STORE
    if _COLLABORATION_STORE is None:
        database_path = Path(os.environ.get("STUDIO_DB_PATH", ROOT / "data" / "studio.db"))
        _COLLABORATION_STORE = CollaborationStore(
            database_path,
            {"projects": PROJECT_ROOT, "cases": CASE_ROOT, "pipelines": PIPELINE_ROOT},
        )
        _COLLABORATION_STORE.initialize(import_existing=True)
        ensure_example_project_security_key(_COLLABORATION_STORE)
    return _COLLABORATION_STORE


def storage_request(payload: dict[str, object]) -> tuple[dict[str, object], int | None]:
    """Remove editor storage metadata and return its optimistic-lock revision."""
    document = dict(payload)
    metadata = document.pop("_storage", None)
    if metadata is None:
        return document, None
    if not isinstance(metadata, dict):
        raise ApiError("_storage must be an object")
    revision = metadata.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ApiError("_storage.revision must be a positive integer")
    return document, revision


def example_project_enabled() -> bool:
    """Return whether the built-in example API and project are available."""
    return os.environ.get("EXAMPLE_PROJECT", "true").strip().lower() in EXAMPLE_PROJECT_TRUE_VALUES


def ensure_example_project_enabled(reference: str) -> None:
    if reference == EXAMPLE_PROJECT_REFERENCE and not example_project_enabled():
        raise ApiError("The example project is disabled. Set EXAMPLE_PROJECT=true to enable it.")


def ensure_example_project_security_key(store: CollaborationStore) -> None:
    """Add the secure-data demo key using the active encryption backend once."""
    if not example_project_enabled():
        return
    if not (
        os.environ.get("API_TEST_ENCRYPTION_URL", "").strip()
        or os.environ.get("API_TEST_ENCRYPTION_KEY", "").strip()
    ):
        return
    current = store.get("projects", EXAMPLE_PROJECT_REFERENCE)
    if current is None:
        return
    variables = current.document.get("variables", {})
    secret = variables.get("secret", {}) if isinstance(variables, dict) else {}
    if isinstance(secret, dict) and "api_key" in secret:
        return
    plain = variables.get("plain", {}) if isinstance(variables, dict) else {}
    document = dict(current.document)
    document["variables"] = {
        "plain": dict(plain) if isinstance(plain, dict) else {},
        "secret": {
            **{
                name: {"preserve": True}
                for name, token in secret.items()
                if isinstance(name, str) and isinstance(token, str)
            },
            "api_key": {"value": EXAMPLE_API_KEY},
        },
    }
    document = normalize_project_document(document, current.document)
    store.save(
        "projects",
        EXAMPLE_PROJECT_REFERENCE,
        document,
        expected_revision=current.revision,
        actor_id="example-initializer",
        action="initialize_example_security_key",
    )


def resolve_openapi_reference(document: dict[str, object], value: object) -> object:
    """Resolve local OpenAPI/Swagger JSON pointers without following external references."""
    current = value
    visited: set[str] = set()
    while isinstance(current, dict) and isinstance(current.get("$ref"), str):
        reference = current["$ref"]
        if not reference.startswith("#/") or reference in visited:
            return current
        visited.add(reference)
        target: object = document
        for segment in reference[2:].split("/"):
            if not isinstance(target, dict):
                return current
            target = target.get(segment.replace("~1", "/").replace("~0", "~"), MISSING)
        if target is MISSING:
            return current
        current = target
    return current


def schema_example(schema: object, document: dict[str, object], depth: int = 0) -> object:
    """Create an editor-friendly example from an OpenAPI schema."""
    if depth > 8:
        return MISSING
    resolved = resolve_openapi_reference(document, schema)
    if not isinstance(resolved, dict):
        return MISSING
    for key in ("example", "default"):
        if key in resolved:
            return resolved[key]
    enum = resolved.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    for composition in ("allOf", "oneOf", "anyOf"):
        variants = resolved.get(composition)
        if isinstance(variants, list) and variants:
            return schema_example(variants[0], document, depth + 1)
    schema_type = resolved.get("type")
    if schema_type == "object" or isinstance(resolved.get("properties"), dict):
        example: dict[str, object] = {}
        properties = resolved.get("properties", {})
        if isinstance(properties, dict):
            for name, property_schema in properties.items():
                value = schema_example(property_schema, document, depth + 1)
                if value is not MISSING:
                    example[name] = value
        return example
    if schema_type == "array":
        item = schema_example(resolved.get("items"), document, depth + 1)
        return [] if item is MISSING else [item]
    if schema_type in {"integer", "number"}:
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        return ""
    return MISSING


def content_example(content: object, document: dict[str, object]) -> object:
    if not isinstance(content, dict) or not content:
        return MISSING
    content_type = next((key for key in content if key == "application/json"), None)
    content_type = content_type or next((key for key in content if key.endswith("+json")), None)
    content_type = content_type or next(iter(content))
    media = resolve_openapi_reference(document, content[content_type])
    if not isinstance(media, dict):
        return MISSING
    if "example" in media:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = resolve_openapi_reference(document, next(iter(examples.values())))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
    return schema_example(media.get("schema"), document)


def parameter_example(parameter: dict[str, object], document: dict[str, object]) -> object:
    if "example" in parameter:
        return parameter["example"]
    return schema_example(parameter.get("schema"), document)


def openapi_operations(document: dict[str, object]) -> list[dict[str, object]]:
    """Normalize OpenAPI 3.x and Swagger 2.0 operations for the React editor."""
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ApiError("The API document must contain an OpenAPI/Swagger paths object")
    operations: list[dict[str, object]] = []
    for path, raw_path_item in paths.items():
        if not isinstance(path, str):
            continue
        path_item = resolve_openapi_reference(document, raw_path_item)
        if not isinstance(path_item, dict):
            continue
        path_parameters = path_item.get("parameters", [])
        if not isinstance(path_parameters, list):
            path_parameters = []
        for method in HTTP_METHODS:
            raw_operation = path_item.get(method)
            operation = resolve_openapi_reference(document, raw_operation)
            if not isinstance(operation, dict):
                continue
            raw_parameters = [*path_parameters, *(operation.get("parameters", []) if isinstance(operation.get("parameters"), list) else [])]
            parameters: dict[tuple[str, str], dict[str, object]] = {}
            for raw_parameter in raw_parameters:
                parameter = resolve_openapi_reference(document, raw_parameter)
                if not isinstance(parameter, dict):
                    continue
                name, location = parameter.get("name"), parameter.get("in")
                if not isinstance(name, str) or not isinstance(location, str):
                    continue
                value = parameter_example(parameter, document)
                parameters[(name, location)] = {"name": name, "in": location, "value": "" if value is MISSING else value}

            request_body = MISSING
            raw_request_body = resolve_openapi_reference(document, operation.get("requestBody"))
            if isinstance(raw_request_body, dict):
                request_body = content_example(raw_request_body.get("content"), document)
            else:  # Swagger 2.0 body parameter
                body_parameter = next((item for item in parameters.values() if item["in"] == "body"), None)
                if body_parameter:
                    raw_body_parameter = next((resolve_openapi_reference(document, item) for item in raw_parameters if isinstance(resolve_openapi_reference(document, item), dict) and resolve_openapi_reference(document, item).get("in") == "body"), None)
                    if isinstance(raw_body_parameter, dict):
                        request_body = schema_example(raw_body_parameter.get("schema"), document)

            responses = operation.get("responses", {})
            responses = responses if isinstance(responses, dict) else {}
            response_key = next((key for key in sorted(responses, key=str) if str(key).startswith("2")), None)
            response_key = response_key or ("default" if "default" in responses else next(iter(responses), "200"))
            response = resolve_openapi_reference(document, responses.get(response_key, {}))
            response = response if isinstance(response, dict) else {}
            response_body = content_example(response.get("content"), document)
            if response_body is MISSING:  # Swagger 2.0 response schema
                response_body = schema_example(response.get("schema"), document)
            status = int(response_key) if str(response_key).isdigit() else 200
            summary = operation.get("summary") or operation.get("operationId") or ""
            operations.append({
                "id": f"{method.upper()} {path}", "method": method.upper(), "path": path,
                "summary": summary if isinstance(summary, str) else "", "parameters": list(parameters.values()),
                "has_request_body": request_body is not MISSING, "request_body": None if request_body is MISSING else request_body,
                "expected_status": status, "has_response_body": response_body is not MISSING,
                "response_body": None if response_body is MISSING else response_body,
            })
    return operations


def openapi_document_operations(document: object) -> list[dict[str, object]]:
    """Validate an uploaded OpenAPI JSON document and normalize its operations."""
    if not isinstance(document, dict):
        raise ApiError("API docs root must be an object")
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ApiError("API docs file must be 5 MB or smaller")
    return openapi_operations(document)


def load_openapi_document(url: str) -> list[dict[str, object]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApiError("API docs URL must be an absolute HTTP URL")
    try:
        with urlopen(Request(url, headers={"Accept": "application/json, application/yaml, text/yaml"}), timeout=20) as response:
            content = response.read(MAX_DOCUMENT_BYTES + 1)
    except HTTPError as exc:
        raise ApiError(f"API docs request failed: HTTP {exc.code}") from exc
    except URLError as exc:
        raise ApiError(f"API docs request failed: {exc.reason}") from exc
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ApiError("API docs file must be 5 MB or smaller")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            document = yaml.safe_load(content.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise ApiError("API docs must be valid OpenAPI/Swagger JSON or YAML") from exc
    return openapi_document_operations(document)


def safe_file(root: Path, reference: str) -> Path:
    candidate = (root / reference).resolve()
    if root.resolve() not in candidate.parents or candidate.suffix != ".json":
        raise ApiError("Invalid JSON file path")
    return candidate


def safe_attachment_file(root: Path, reference: str) -> Path:
    """Allow binary form-data attachments only below case/{tag}/{api}/files/."""
    resolved_root = root.resolve()
    candidate = (root / reference).resolve()
    if resolved_root not in candidate.parents:
        raise ApiError("Invalid attachment file path")
    relative = candidate.relative_to(resolved_root)
    if len(relative.parts) != 4 or relative.parts[2] != "files":
        raise ApiError("Attachments must be stored in case/{tag}/{api_name}/files")
    return candidate


def json_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    # API references are persisted and consumed by the browser, so keep their separator
    # stable even when the server runs on Windows.
    return [path.relative_to(root).as_posix() for path in sorted(root.rglob("*.json"))]


def project_json_files(root: Path, project_reference: str | None) -> list[str]:
    """Return only documents belonging to a project when one is selected."""
    if not project_reference:
        return json_files(root)
    items: list[str] = []
    for reference in json_files(root):
        document = json.loads(safe_file(root, reference).read_text(encoding="utf-8"))
        if document.get("project") == project_reference:
            items.append(reference)
    return items


def visible_project_files(root: Path = PROJECT_ROOT) -> list[str]:
    """List projects that may be shown in the browser for the current environment."""
    references = json_files(root)
    if example_project_enabled():
        return references
    return [reference for reference in references if reference != EXAMPLE_PROJECT_REFERENCE]


def example_openapi_document() -> dict[str, object]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "API Develop Studio Example API", "version": "1.0.0"},
        "paths": {
            "/example-api/health": {
                "get": {
                    "summary": "Example API health check",
                    "responses": {"200": {"content": {"application/json": {"example": {"status": "ok", "service": "example-api"}}}}},
                },
            },
            "/example-api/users": {
                "post": {
                    "summary": "Create an example user",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string", "example": "Ada"}}}}},
                    },
                    "responses": {"201": {"content": {"application/json": {"example": {"id": 1, "name": "Ada"}}}}},
                },
            },
            "/example-api/users/{userId}": {
                "get": {
                    "summary": "Get an example user",
                    "parameters": [{"name": "userId", "in": "path", "required": True, "schema": {"type": "integer", "example": 1}}],
                    "responses": {"200": {"content": {"application/json": {"example": {"id": 1, "name": "Ada"}}}}},
                },
            },
            "/example-api/secure-data": {
                "get": {
                    "summary": "Get data using an API key",
                    "security": [{"ApiKeyAuth": []}],
                    "responses": {
                        "200": {
                            "description": "API key accepted",
                            "content": {
                                "application/json": {
                                    "example": {"authorized": True, "message": "API key accepted"},
                                },
                            },
                        },
                        "401": {
                            "description": "Missing or invalid API key",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Invalid or missing API key"},
                                },
                            },
                        },
                    },
                },
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            },
        },
    }


def case_summaries(root: Path, references: list[str]) -> dict[str, dict[str, str]]:
    """Return the request details needed to identify saved cases in the UI."""
    summaries: dict[str, dict[str, str]] = {}
    for reference in references:
        document = json.loads(safe_file(root, reference).read_text(encoding="utf-8"))
        request = document.get("request", {})
        if not isinstance(request, dict):
            request = {}
        url = request.get("url", "")
        summaries[reference] = {"url": url if isinstance(url, str) else ""}
    return summaries


def project_summaries(root: Path, references: list[str]) -> dict[str, dict[str, str]]:
    """Return the public project details displayed on project cards."""
    summaries: dict[str, dict[str, str]] = {}
    for reference in references:
        document = json.loads(safe_file(root, reference).read_text(encoding="utf-8"))
        name = document.get("name", "")
        base_url = document.get("base_url", "")
        summaries[reference] = {
            "name": name if isinstance(name, str) else "",
            "base_url": base_url if isinstance(base_url, str) else "",
        }
    return summaries


def validate_project_document(payload: dict[str, object]) -> None:
    name = payload.get("name")
    base_url = payload.get("base_url")
    if not isinstance(name, str) or not name.strip():
        raise ApiError("Project name is required")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ApiError("Project base_url is required")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ApiError("Project base_url must be an absolute HTTP URL")
    docs_url = payload.get("docs_url", "")
    if not isinstance(docs_url, str):
        raise ApiError("Project docs_url must be a string")
    if docs_url.strip():
        parsed_docs_url = urlparse(docs_url)
        if parsed_docs_url.scheme not in {"http", "https"} or not parsed_docs_url.netloc:
            raise ApiError("Project docs_url must be an absolute HTTP URL")
    docs_file = payload.get("docs_file")
    if docs_file is not None:
        if not isinstance(docs_file, dict):
            raise ApiError("Project docs_file must be an object")
        file_name = docs_file.get("name")
        if not isinstance(file_name, str) or not file_name.strip().lower().endswith(".json") or Path(file_name).name != file_name:
            raise ApiError("Project docs_file name must be a JSON filename")
        openapi_document_operations(docs_file.get("document"))
    if docs_url.strip() and docs_file is not None:
        raise ApiError("Use either Project docs_url or docs_file, not both")
    advanced = payload.get("advanced", {})
    if not isinstance(advanced, dict):
        raise ApiError("Project advanced settings must be an object")
    for key in ("proxy", "http_proxy", "https_proxy"):
        proxy = advanced.get(key, "")
        if not isinstance(proxy, str):
            raise ApiError(f"Project {key} must be a string")
        if proxy.strip():
            proxy_url = urlparse(proxy)
            if proxy_url.scheme not in {"http", "https"} or not proxy_url.netloc:
                raise ApiError(f"Project {key} must be an absolute HTTP URL")
    verify = advanced.get("verify", True)
    if not isinstance(verify, bool):
        raise ApiError("Project verify must be true or false")


def normalize_project_document(
    payload: dict[str, object],
    existing: dict[str, object] | None = None,
) -> dict[str, object]:
    """Encrypt submitted project secrets and preserve masked values when requested."""
    document = dict(payload)
    if "variables" not in document:
        if existing is not None and "variables" in existing:
            document["variables"] = existing["variables"]
        return document
    existing_variables = existing.get("variables") if isinstance(existing, dict) else None
    try:
        document["variables"] = normalize_project_variables(document["variables"], existing_variables)
    except ProjectVariableError as exc:
        raise ApiError(str(exc)) from exc
    return document


def validate_project_reference(payload: dict[str, object]) -> None:
    project_reference = payload.get("project")
    if not isinstance(project_reference, str) or not project_reference:
        raise ApiError("A project must be selected")
    if not safe_file(PROJECT_ROOT, project_reference).is_file():
        raise ApiError("Selected project does not exist")


def project_document_references(root: Path, project_reference: str) -> list[str]:
    return [
        reference for reference in json_files(root)
        if json.loads(safe_file(root, reference).read_text(encoding="utf-8")).get("project") == project_reference
    ]


def project_has_cases(reference: str, case_root: Path = CASE_ROOT) -> bool:
    return bool(project_document_references(case_root, reference))


def delete_project_pipelines(reference: str, pipeline_root: Path = PIPELINE_ROOT) -> list[str]:
    deleted: list[str] = []
    for pipeline_reference in project_document_references(pipeline_root, reference):
        safe_file(pipeline_root, pipeline_reference).unlink()
        deleted.append(pipeline_reference)
    return deleted


def normalize_case_document(
    payload: dict[str, object],
    existing: dict[str, object] | None = None,
) -> dict[str, object]:
    """Apply editor-only fields while keeping the persisted/temporary case schema clean."""
    document = dict(payload)
    expected_body_raw = document.pop("_expectedBodyRaw", None)
    if expected_body_raw is not None:
        if not isinstance(expected_body_raw, str):
            raise ApiError("_expectedBodyRaw must be a string")
        expected = document.get("expected")
        if not isinstance(expected, dict):
            raise ApiError("Case expected must be an object")
        if expected_body_raw.strip():
            expected["body"] = json.loads(expected_body_raw)
        else:
            expected.pop("body", None)
    if "variables" not in document:
        if existing is not None and "variables" in existing:
            document["variables"] = existing["variables"]
        return document
    existing_variables = existing.get("variables") if isinstance(existing, dict) else None
    try:
        document["variables"] = normalize_case_variables(document["variables"], existing_variables)
    except ProjectVariableError as exc:
        raise ApiError(str(exc)) from exc
    return document


class StudioHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        print(f"[react-server] {format % args}")

    def send_json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError("Invalid request JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError("Request body must be a JSON object")
        return payload

    def read_upload(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ApiError("Upload size must be between 1 byte and 25 MB")
        return self.rfile.read(length)

    def api_path(self) -> list[str]:
        return [unquote(part) for part in urlparse(self.path).path.split("/") if part]

    def query_value(self, name: str) -> str | None:
        values = parse_qs(urlparse(self.path).query).get(name)
        return values[0] if values else None

    def actor_id(self) -> str:
        """Identify the caller for revision and audit records until auth is added."""
        return self.headers.get("X-Studio-Actor", "local-user")

    def serve_example_api(self) -> bool:
        """Serve the optional deterministic API used by the bundled example tests."""
        parts = self.api_path()
        if not parts or parts[0] != "example-api":
            return False
        if not example_project_enabled():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Example API is disabled. Set EXAMPLE_PROJECT=true to enable it."})
            return True

        if self.command == "GET" and parts == ["example-api", "openapi.json"]:
            self.send_json(200, example_openapi_document())
        elif self.command == "GET" and parts == ["example-api", "health"]:
            self.send_json(200, {"status": "ok", "service": "example-api"})
        elif self.command == "GET" and parts == ["example-api", "users", "1"]:
            self.send_json(200, {"id": 1, "name": "Ada"})
        elif self.command == "GET" and parts == ["example-api", "secure-data"]:
            if self.headers.get("X-API-Key") != EXAMPLE_API_KEY:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid or missing API key"})
            else:
                self.send_json(200, {"authorized": True, "message": "API key accepted"})
        elif self.command == "POST" and parts == ["example-api", "users"]:
            payload = self.read_body()
            name = payload.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ApiError("Example user name is required")
            self.send_json(201, {"id": 1, "name": name})
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Example API endpoint not found"})
        return True

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.serve_example_api():
                return
            parts = self.api_path()
            store = collaboration_store()
            if parts == ["api", "cases"]:
                references = store.list_references("cases", self.query_value("project"))
                self.send_json(200, {"items": references, "details": case_summaries(CASE_ROOT, references)})
            elif parts == ["api", "pipelines"]:
                self.send_json(200, {"items": store.list_references("pipelines", self.query_value("project"))})
            elif parts == ["api", "projects"]:
                references = store.list_references("projects")
                if not example_project_enabled():
                    references = [reference for reference in references if reference != EXAMPLE_PROJECT_REFERENCE]
                self.send_json(200, {"items": references, "details": project_summaries(PROJECT_ROOT, references)})
            elif len(parts) == 4 and parts[:2] == ["api", "cases"] and parts[3] == "revisions":
                self.send_json(200, {"items": store.revisions("cases", parts[2])})
            elif len(parts) == 4 and parts[:2] == ["api", "pipelines"] and parts[3] == "revisions":
                self.send_json(200, {"items": store.revisions("pipelines", parts[2])})
            elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "revisions":
                ensure_example_project_enabled(parts[2])
                self.send_json(200, {"items": store.revisions("projects", parts[2])})
            elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
                stored = store.get("cases", parts[2])
                if stored is None:
                    raise DocumentNotFoundError("JSON file not found")
                document = case_variables_for_client(stored.document)
                expected = document.get("expected", {})
                if isinstance(expected, dict) and "body" in expected:
                    # JavaScript parses 9.0 as 9. Keep the original JSON numeric spelling for the editor.
                    document["_expectedBodyRaw"] = json.dumps(expected["body"], ensure_ascii=False, indent=2)
                document["_storage"] = stored.metadata()
                self.send_json(200, document)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                stored = store.get("pipelines", parts[2])
                if stored is None:
                    raise DocumentNotFoundError("JSON file not found")
                self.send_json(200, {**stored.document, "_storage": stored.metadata()})
            elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
                ensure_example_project_enabled(parts[2])
                stored = store.get("projects", parts[2])
                if stored is None:
                    raise DocumentNotFoundError("JSON file not found")
                project = project_variables_for_client(stored.document)
                self.send_json(200, {**project, "_storage": stored.metadata()})
            else:
                self.serve_frontend()
        except (ApiError, CollaborationStoreError, OSError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def do_PUT(self) -> None:  # noqa: N802
        try:
            parts = self.api_path()
            payload, expected_revision = storage_request(self.read_body())
            store = collaboration_store()
            if len(parts) == 3 and parts[:2] == ["api", "cases"]:
                kind = "cases"
                current = store.get(kind, parts[2])
                payload = normalize_case_document(payload, current.document if current is not None else None)
                validate_project_reference(payload)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                kind = "pipelines"
                validate_project_reference(payload)
            elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
                ensure_example_project_enabled(parts[2])
                kind = "projects"
                current = store.get(kind, parts[2])
                existing = current.document if current is not None else None
                payload = normalize_project_document(payload, existing)
                validate_project_document(payload)
            else:
                raise ApiError("Unknown save endpoint")
            stored = store.save(
                kind,
                parts[2],
                payload,
                expected_revision=expected_revision,
                actor_id=self.actor_id(),
            )
            path = safe_file({"cases": CASE_ROOT, "pipelines": PIPELINE_ROOT, "projects": PROJECT_ROOT}[kind], parts[2])
            self.send_json(200, {"path": str(path.relative_to(ROOT)), "_storage": stored.metadata()})
        except RevisionConflictError as exc:
            self.send_json(409, {"error": str(exc), "currentRevision": exc.current_revision})
        except RevisionRequiredError as exc:
            self.send_json(409, {"error": str(exc), "currentRevision": exc.current_revision})
        except (ApiError, CollaborationStoreError, OSError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.serve_example_api():
                return
            parts = self.api_path()
            if len(parts) == 3 and parts[:2] == ["api", "uploads"]:
                path = safe_attachment_file(CASE_ROOT, parts[2])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.read_upload())
                self.send_json(200, {"path": path.relative_to(CASE_ROOT).as_posix()})
                return
            if parts == ["api", "docs"]:
                body = self.read_body()
                document = body.get("document")
                url = body.get("url")
                if document is not None:
                    if url not in (None, ""):
                        raise ApiError("Use either API docs URL or document, not both")
                    operations = openapi_document_operations(document)
                else:
                    if not isinstance(url, str) or not url.strip():
                        raise ApiError("API docs URL or JSON document is required")
                    operations = load_openapi_document(url.strip())
                self.send_json(200, {"operations": operations})
                return
            if parts != ["api", "run"]:
                raise ApiError("Unknown run endpoint")
            body = self.read_body()
            pipelines = body.get("pipelines", [])
            cases = body.get("cases", [])
            inline_case = body.get("inlineCase")
            inline_pipeline = body.get("inlinePipeline")
            if not isinstance(pipelines, list) or not isinstance(cases, list) or not all(isinstance(item, str) for item in pipelines + cases):
                raise ApiError("pipelines and cases must be string arrays")
            preview_count = int(inline_case is not None) + int(inline_pipeline is not None)
            if preview_count > 1 or (preview_count and (pipelines or cases)):
                raise ApiError("Run either saved targets or one unsaved case/pipeline")

            with TemporaryDirectory(prefix="api-test-preview-") as directory:
                if inline_case is not None:
                    if not isinstance(inline_case, dict):
                        raise ApiError("inlineCase must be an object")
                    reference = body.get("caseReference", "preview/unsaved/unsaved_case.json")
                    if not isinstance(reference, str):
                        raise ApiError("caseReference must be a string")
                    temporary_case_root = Path(directory) / "case"
                    temporary_case_path = safe_file(temporary_case_root, reference)
                    temporary_case_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_case_path.write_text(
                        json.dumps(normalize_case_document(inline_case), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    command = [
                        sys.executable, "run_api_tests.py", "--case-root", str(temporary_case_root), "--file-root", str(CASE_ROOT), "--case", reference,
                    ]
                elif inline_pipeline is not None:
                    if not isinstance(inline_pipeline, dict):
                        raise ApiError("inlinePipeline must be an object")
                    temporary_pipeline = Path(directory) / "unsaved_pipeline.json"
                    temporary_pipeline.write_text(
                        json.dumps(inline_pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                    )
                    command = [sys.executable, "run_api_tests.py", str(temporary_pipeline)]
                else:
                    command = [sys.executable, "run_api_tests.py", *pipelines]
                    if cases:
                        command.extend(["--case", *cases])
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
            self.send_json(200, {"exitCode": result.returncode, "output": result.stdout + result.stderr})
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "Test run timed out after 300 seconds"})
        except (ApiError, OSError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            parts = self.api_path()
            if len(parts) != 3 or parts[0] != "api" or parts[1] not in {"cases", "pipelines", "projects"}:
                raise ApiError("Unknown delete endpoint")
            store = collaboration_store()
            if parts[1] == "projects":
                ensure_example_project_enabled(parts[2])
            deleted_pipelines: list[str] = []
            if parts[1] == "projects":
                if store.list_references("cases", parts[2]):
                    raise ApiError("Delete the project's API cases before deleting the project")
                deleted_pipelines = store.list_references("pipelines", parts[2])
                for pipeline_reference in deleted_pipelines:
                    store.delete("pipelines", pipeline_reference, actor_id=self.actor_id())
            store.delete(parts[1], parts[2], actor_id=self.actor_id())
            root_name = {"cases": "case", "pipelines": "pipelines", "projects": "projects"}[parts[1]]
            self.send_json(200, {"deleted": f"{root_name}/{parts[2]}", "deleted_pipelines": deleted_pipelines})
        except (ApiError, CollaborationStoreError, OSError) as exc:
            self.send_json(400, {"error": str(exc)})

    def serve_frontend(self) -> None:
        if not WEB_DIST.exists():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "React build not found. Run npm run build in web/."})
            return
        requested = urlparse(self.path).path.lstrip("/")
        path = (WEB_DIST / requested).resolve() if requested else WEB_DIST / "index.html"
        if WEB_DIST.resolve() not in path.parents or not path.is_file():
            path = WEB_DIST / "index.html"
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    host = os.environ.get("API_TEST_HOST", "127.0.0.1")
    port = int(os.environ.get("API_TEST_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), StudioHandler)
    print(f"API Develop Studio server: http://{host}:{port}")
    server.serve_forever()
