from __future__ import annotations

import copy
import json
import mimetypes
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .comparison import Difference, compare_json


REFERENCE_PATTERN = re.compile(r"\$\{([A-Za-z_][\w-]*)\.response\.(body|status)(?:\.([\w.]+))?\}")


class CaseConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectRequestSettings:
    base_url: str
    proxy_url: str | None = None
    proxy_urls: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: Any


@dataclass
class CaseResult:
    case_id: str
    status: str
    attempts: int
    response: HttpResponse | None = None
    differences: list[Difference] = field(default_factory=list)
    error: str | None = None
    request_definition: dict[str, Any] | None = None
    expected_definition: dict[str, Any] | None = None


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseConfigurationError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CaseConfigurationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CaseConfigurationError(f"{path} must contain a JSON object")
    return value


def resolve_case_path(case_root: Path, reference: str) -> Path:
    candidate = (case_root / reference).resolve()
    root = case_root.resolve()
    if root not in candidate.parents:
        raise CaseConfigurationError(f"Case path escapes root: {reference}")
    if not candidate.is_file():
        raise CaseConfigurationError(f"Case file not found: {reference}")
    return candidate


def resolve_attachment_path(file_root: Path, reference: str) -> Path:
    candidate = (file_root / reference).resolve()
    root = file_root.resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise CaseConfigurationError(f"Attachment file not found: {reference}")
    return candidate


def encode_multipart_form_data(items: Any, file_root: Path | None) -> tuple[bytes, str]:
    if not isinstance(items, list):
        raise CaseConfigurationError("request.form_data must be an array")
    if file_root is None:
        raise CaseConfigurationError("A file root is required for request.form_data")
    boundary = f"----ApiTestStudio{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"]:
            raise CaseConfigurationError(f"request.form_data[{index}] needs a non-empty key")
        key = item["key"]
        if "\r" in key or "\n" in key:
            raise CaseConfigurationError(f"request.form_data[{index}].key contains an invalid character")
        chunks.append(f"--{boundary}\r\n".encode())
        file_reference = item.get("file")
        if file_reference is not None:
            if not isinstance(file_reference, str) or not file_reference:
                raise CaseConfigurationError(f"request.form_data[{index}].file must be a file reference")
            path = resolve_attachment_path(file_root, file_reference)
            filename = item.get("filename", path.name)
            if not isinstance(filename, str) or not filename:
                raise CaseConfigurationError(f"request.form_data[{index}].filename must be a string")
            content_type = item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            if not isinstance(content_type, str):
                raise CaseConfigurationError(f"request.form_data[{index}].content_type must be a string")
            if any("\r" in value or "\n" in value for value in (filename, content_type)):
                raise CaseConfigurationError(f"request.form_data[{index}] contains an invalid header value")
            chunks.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode())
            chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
            chunks.append(path.read_bytes())
        else:
            value = item.get("value", "")
            chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def project_request_settings(case: dict[str, Any], project_root: Path) -> ProjectRequestSettings | None:
    """Read a project's Base URL and optional transport settings."""
    project_reference = case.get("project")
    if project_reference is None:
        return None
    if not isinstance(project_reference, str) or not project_reference:
        raise CaseConfigurationError("case.project must be a non-empty project JSON reference")
    project_path = resolve_case_path(project_root, project_reference)
    project = read_json(project_path)
    base_url = project.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise CaseConfigurationError(f"project.base_url is required: {project_reference}")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CaseConfigurationError(f"project.base_url must be an absolute HTTP URL: {project_reference}")
    advanced = project.get("advanced", {})
    if not isinstance(advanced, dict):
        raise CaseConfigurationError(f"project.advanced must be an object: {project_reference}")
    legacy_proxy = advanced.get("proxy")
    if legacy_proxy is not None and not isinstance(legacy_proxy, str):
        raise CaseConfigurationError(f"project.advanced.proxy must be a string: {project_reference}")
    proxy_values = {
        "http": advanced.get("http_proxy", legacy_proxy),
        "https": advanced.get("https_proxy", legacy_proxy),
    }
    normalized_proxies: dict[str, str] = {}
    for protocol, value in proxy_values.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise CaseConfigurationError(f"project.advanced.{protocol}_proxy must be a string: {project_reference}")
        proxy_url = value.strip()
        if not proxy_url:
            continue
        proxy_parsed = urlparse(proxy_url)
        if proxy_parsed.scheme not in {"http", "https"} or not proxy_parsed.netloc:
            raise CaseConfigurationError(f"project.advanced.{protocol}_proxy must be an absolute HTTP URL: {project_reference}")
        normalized_proxies[protocol] = proxy_url
    verify_ssl = advanced.get("verify", True)
    if not isinstance(verify_ssl, bool):
        raise CaseConfigurationError(f"project.advanced.verify must be true or false: {project_reference}")
    return ProjectRequestSettings(
        base_url=urlunparse(parsed._replace(path=parsed.path.rstrip("/"))),
        proxy_url=legacy_proxy.strip() if isinstance(legacy_proxy, str) and legacy_proxy.strip() else None,
        proxy_urls=normalized_proxies,
        verify_ssl=verify_ssl,
    )


def project_base_url(case: dict[str, Any], project_root: Path) -> str | None:
    """Backward-compatible helper returning only the project Base URL."""
    settings = project_request_settings(case, project_root)
    return settings.base_url if settings else None


def resolve_request_url(url: str, base_url: str | None) -> str:
    """Keep absolute URLs unchanged and resolve project-relative endpoints."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    if not base_url:
        raise CaseConfigurationError("request.url must be absolute when case.project is not set")
    return f"{base_url.rstrip('/')}/{url.lstrip('/')}"


def _dig(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for piece in path.split("."):
        if isinstance(current, dict) and piece in current:
            current = current[piece]
        elif isinstance(current, list) and piece.isdigit() and int(piece) < len(current):
            current = current[int(piece)]
        else:
            raise CaseConfigurationError(f"Reference path does not exist: {path}")
    return current


def resolve_references(value: Any, context: dict[str, CaseResult]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_references(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_references(item, context) for item in value]
    if not isinstance(value, str):
        return value

    def resolve(match: re.Match[str]) -> Any:
        step_name, section, nested_path = match.groups()
        result = context.get(step_name)
        if not result or not result.response:
            raise CaseConfigurationError(f"No successful response for pipeline step: {step_name}")
        source: Any = result.response.body if section == "body" else result.response.status
        return _dig(source, nested_path or "")

    match = REFERENCE_PATTERN.fullmatch(value)
    if match:
        return resolve(match)
    return REFERENCE_PATTERN.sub(lambda item: str(resolve(item)), value)


class ApiTestRunner:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run_case(
        self,
        case_id: str,
        case: dict[str, Any],
        context: dict[str, CaseResult] | None = None,
        retry: int = 0,
        retry_interval_seconds: float = 0,
        base_url: str | None = None,
        proxy_url: str | None = None,
        verify_ssl: bool = True,
        file_root: Path | None = None,
        proxy_urls: dict[str, str] | None = None,
    ) -> CaseResult:
        request_definition = case.get("request")
        expected = case.get("expected")
        if not isinstance(request_definition, dict) or not isinstance(expected, dict):
            raise CaseConfigurationError("A case needs object-valued request and expected fields")
        if not isinstance(request_definition.get("url"), str):
            raise CaseConfigurationError("request.url is required")

        resolved_request = resolve_references(copy.deepcopy(request_definition), context or {})
        resolved_request["url"] = resolve_request_url(resolved_request["url"], base_url)
        attempts = max(0, retry) + 1
        last_result: CaseResult | None = None
        for attempt in range(1, attempts + 1):
            result = self._run_once(case_id, resolved_request, expected, attempt, proxy_url, verify_ssl, file_root, proxy_urls)
            if result.status == "passed":
                return result
            last_result = result
            if attempt < attempts and retry_interval_seconds > 0:
                time.sleep(retry_interval_seconds)
        assert last_result is not None
        return last_result

    def _run_once(
        self, case_id: str, request_definition: dict[str, Any], expected: dict[str, Any], attempt: int,
        proxy_url: str | None = None, verify_ssl: bool = True, file_root: Path | None = None, proxy_urls: dict[str, str] | None = None,
    ) -> CaseResult:
        method = str(request_definition.get("method", "GET")).upper()
        headers = {str(key): str(value) for key, value in request_definition.get("headers", {}).items()}
        form_data = request_definition.get("form_data")
        payload = request_definition.get("body")
        data = None
        if form_data is not None:
            data, content_type = encode_multipart_form_data(form_data, file_root)
            headers["Content-Type"] = content_type
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(request_definition["url"], data=data, headers=headers, method=method)
        try:
            if proxy_url or proxy_urls or not verify_ssl:
                handlers: list[Any] = []
                if proxy_urls:
                    handlers.append(urllib.request.ProxyHandler(proxy_urls))
                elif proxy_url:
                    handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
                if not verify_ssl:
                    handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
                opener = urllib.request.build_opener(*handlers)
                opened_response = opener.open(request, timeout=self.timeout_seconds)
            else:
                opened_response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
            with opened_response as opened:
                status = opened.status
                response_headers = dict(opened.headers.items())
                raw_body = opened.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = dict(exc.headers.items()) if exc.headers else {}
            raw_body = exc.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return CaseResult(
                case_id, "error", attempt, error=str(exc),
                request_definition=request_definition, expected_definition=expected,
            )

        try:
            body: Any = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError:
            body = raw_body
        response = HttpResponse(status, response_headers, body)
        differences: list[Difference] = []
        if "status" in expected and expected["status"] != status:
            differences.append(Difference("$.status", expected["status"], status, "status mismatch"))
        if "body" in expected:
            differences.extend(compare_json(expected["body"], body, "$.body", strict=expected.get("strict", True)))
        return CaseResult(
            case_id, "passed" if not differences else "failed", attempt, response, differences,
            request_definition=request_definition, expected_definition=expected,
        )
