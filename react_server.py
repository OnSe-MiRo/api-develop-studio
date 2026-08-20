"""Local REST server used by the React API Test Studio."""

from __future__ import annotations

import json
import mimetypes
import subprocess
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
CASE_ROOT = ROOT / "case"
PIPELINE_ROOT = ROOT / "pipelines"
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
    return [str(path.relative_to(root)) for path in sorted(root.rglob("*.json"))]


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

    def do_GET(self) -> None:  # noqa: N802
        try:
            parts = self.api_path()
            if parts == ["api", "cases"]:
                self.send_json(200, {"items": json_files(CASE_ROOT)})
            elif parts == ["api", "pipelines"]:
                self.send_json(200, {"items": json_files(PIPELINE_ROOT)})
            elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
                document = json.loads(safe_file(CASE_ROOT, parts[2]).read_text(encoding="utf-8"))
                expected = document.get("expected", {})
                if isinstance(expected, dict) and "body" in expected:
                    # JavaScript parses 9.0 as 9. Keep the original JSON numeric spelling for the editor.
                    document["_expectedBodyRaw"] = json.dumps(expected["body"], ensure_ascii=False, indent=2)
                self.send_json(200, document)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                self.send_json(200, json.loads(safe_file(PIPELINE_ROOT, parts[2]).read_text(encoding="utf-8")))
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
                expected_body_raw = payload.pop("_expectedBodyRaw", None)
                if expected_body_raw is not None:
                    if not isinstance(expected_body_raw, str):
                        raise ApiError("_expectedBodyRaw must be a string")
                    expected = payload.get("expected")
                    if not isinstance(expected, dict):
                        raise ApiError("Case expected must be an object")
                    if expected_body_raw.strip():
                        expected["body"] = json.loads(expected_body_raw)
                    else:
                        expected.pop("body", None)
            elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
                path = safe_file(PIPELINE_ROOT, parts[2])
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
            if not isinstance(pipelines, list) or not isinstance(cases, list) or not all(isinstance(item, str) for item in pipelines + cases):
                raise ApiError("pipelines and cases must be string arrays")
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
            if len(parts) != 3 or parts[0] != "api" or parts[1] not in {"cases", "pipelines"}:
                raise ApiError("Unknown delete endpoint")
            root = CASE_ROOT if parts[1] == "cases" else PIPELINE_ROOT
            path = safe_file(root, parts[2])
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
    server = ThreadingHTTPServer(("127.0.0.1", 8765), StudioHandler)
    print("API Test Studio server: http://127.0.0.1:8765")
    server.serve_forever()
