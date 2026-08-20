"""Local REST server used by the React API Test Studio."""

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
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT / "case"
PIPELINE_ROOT = ROOT / "pipelines"
PROJECT_ROOT = ROOT / "projects"
WEB_DIST = ROOT / "web" / "dist"


class ApiError(ValueError):
    pass


def safe_file(root: Path, reference: str) -> Path:
    candidate = (root / reference).resolve()
    if root.resolve() not in candidate.parents or candidate.suffix != ".json":
        raise ApiError("Invalid JSON file path")
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
    advanced = payload.get("advanced", {})
    if not isinstance(advanced, dict):
        raise ApiError("Project advanced settings must be an object")
    proxy = advanced.get("proxy", "")
    if not isinstance(proxy, str):
        raise ApiError("Project proxy must be a string")
    if proxy.strip():
        proxy_url = urlparse(proxy)
        if proxy_url.scheme not in {"http", "https"} or not proxy_url.netloc:
            raise ApiError("Project proxy must be an absolute HTTP URL")
    verify = advanced.get("verify", True)
    if not isinstance(verify, bool):
        raise ApiError("Project verify must be true or false")


def validate_project_reference(payload: dict[str, object]) -> None:
    project_reference = payload.get("project")
    if not isinstance(project_reference, str) or not project_reference:
        raise ApiError("A project must be selected")
    if not safe_file(PROJECT_ROOT, project_reference).is_file():
        raise ApiError("Selected project does not exist")


def project_is_in_use(reference: str) -> bool:
    for root in (CASE_ROOT, PIPELINE_ROOT):
        for item in json_files(root):
            document = json.loads(safe_file(root, item).read_text(encoding="utf-8"))
            if document.get("project") == reference:
                return True
    return False


def normalize_case_document(payload: dict[str, object]) -> dict[str, object]:
    """Apply editor-only fields while keeping the persisted/temporary case schema clean."""
    document = dict(payload)
    expected_body_raw = document.pop("_expectedBodyRaw", None)
    if expected_body_raw is None:
        return document
    if not isinstance(expected_body_raw, str):
        raise ApiError("_expectedBodyRaw must be a string")
    expected = document.get("expected")
    if not isinstance(expected, dict):
        raise ApiError("Case expected must be an object")
    if expected_body_raw.strip():
        expected["body"] = json.loads(expected_body_raw)
    else:
        expected.pop("body", None)
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

    def api_path(self) -> list[str]:
        return [unquote(part) for part in urlparse(self.path).path.split("/") if part]

    def query_value(self, name: str) -> str | None:
        values = parse_qs(urlparse(self.path).query).get(name)
        return values[0] if values else None

    def do_GET(self) -> None:  # noqa: N802
        try:
            parts = self.api_path()
            if parts == ["api", "cases"]:
                self.send_json(200, {"items": project_json_files(CASE_ROOT, self.query_value("project"))})
            elif parts == ["api", "pipelines"]:
                self.send_json(200, {"items": project_json_files(PIPELINE_ROOT, self.query_value("project"))})
            elif parts == ["api", "projects"]:
                self.send_json(200, {"items": json_files(PROJECT_ROOT)})
            elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
                document = json.loads(safe_file(CASE_ROOT, parts[2]).read_text(encoding="utf-8"))
                expected = document.get("expected", {})
                if isinstance(expected, dict) and "body" in expected:
                    # JavaScript parses 9.0 as 9. Keep the original JSON numeric spelling for the editor.
                    document["_expectedBodyRaw"] = json.dumps(expected["body"], ensure_ascii=False, indent=2)
                self.send_json(200, document)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                self.send_json(200, json.loads(safe_file(PIPELINE_ROOT, parts[2]).read_text(encoding="utf-8")))
            elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
                self.send_json(200, json.loads(safe_file(PROJECT_ROOT, parts[2]).read_text(encoding="utf-8")))
            else:
                self.serve_frontend()
        except (ApiError, OSError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def do_PUT(self) -> None:  # noqa: N802
        try:
            parts = self.api_path()
            payload = self.read_body()
            if len(parts) == 3 and parts[:2] == ["api", "cases"]:
                path = safe_file(CASE_ROOT, parts[2])
                payload = normalize_case_document(payload)
                validate_project_reference(payload)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                path = safe_file(PIPELINE_ROOT, parts[2])
                validate_project_reference(payload)
            elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
                path = safe_file(PROJECT_ROOT, parts[2])
                validate_project_document(payload)
            else:
                raise ApiError("Unknown save endpoint")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.send_json(200, {"path": str(path.relative_to(ROOT))})
        except (ApiError, OSError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.api_path() != ["api", "run"]:
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
                        sys.executable, "run_api_tests.py", "--case-root", str(temporary_case_root), "--case", reference,
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
            root = {"cases": CASE_ROOT, "pipelines": PIPELINE_ROOT, "projects": PROJECT_ROOT}[parts[1]]
            path = safe_file(root, parts[2])
            if parts[1] == "projects" and project_is_in_use(parts[2]):
                raise ApiError("Delete the project's cases and pipelines before deleting the project")
            if not path.is_file():
                raise ApiError("JSON file not found")
            path.unlink()
            self.send_json(200, {"deleted": str(path.relative_to(ROOT))})
        except (ApiError, OSError) as exc:
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
    print(f"API Test Studio server: http://{host}:{port}")
    server.serve_forever()
