from __future__ import annotations

import copy
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .comparison import Difference, compare_json


REFERENCE_PATTERN = re.compile(r"\$\{([A-Za-z_][\w-]*)\.response\.(body|status)(?:\.([\w.]+))?\}")


class CaseConfigurationError(ValueError):
    pass


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
    ) -> CaseResult:
        request_definition = case.get("request")
        expected = case.get("expected")
        if not isinstance(request_definition, dict) or not isinstance(expected, dict):
            raise CaseConfigurationError("A case needs object-valued request and expected fields")
        if not isinstance(request_definition.get("url"), str):
            raise CaseConfigurationError("request.url is required")

        resolved_request = resolve_references(copy.deepcopy(request_definition), context or {})
        attempts = max(0, retry) + 1
        last_result: CaseResult | None = None
        for attempt in range(1, attempts + 1):
            result = self._run_once(case_id, resolved_request, expected, attempt)
            if result.status == "passed":
                return result
            last_result = result
            if attempt < attempts and retry_interval_seconds > 0:
                time.sleep(retry_interval_seconds)
        assert last_result is not None
        return last_result

    def _run_once(self, case_id: str, request_definition: dict[str, Any], expected: dict[str, Any], attempt: int) -> CaseResult:
        method = str(request_definition.get("method", "GET")).upper()
        headers = {str(key): str(value) for key, value in request_definition.get("headers", {}).items()}
        payload = request_definition.get("body")
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(request_definition["url"], data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as opened:
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
