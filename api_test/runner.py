from __future__ import annotations

import copy
import base64
import binascii
import ipaddress
import json
import mimetypes
import math
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from .comparison import Difference, compare_json
from .project_variables import (
    ProjectVariableError,
    resolve_case_references,
    resolve_project_references,
    stored_case_variables,
    stored_project_variables,
)


REFERENCE_PATTERN = re.compile(r"\$\{([A-Za-z_][\w-]*)\.response\.(body|status)(?:\.([\w.]+))?\}")
ASSERTION_PATH_PATTERN = re.compile(r"^(?:\$\.)?(?:body(?:\.(?:[A-Za-z_][\w-]*|\d+))*|status)$")
ASSERTION_OPERATORS = {"gt", "gte", "lt", "lte", "between", "exists", "not_exists", "type", "length_between", "format"}
JSON_TYPE_NAMES = {"number", "integer", "string", "boolean", "object", "array", "null"}
NO_STRING_FORMAT = "none"
CUSTOM_STRING_FORMAT = "custom"
STRING_FORMATS = {
    "base64url", "binary", "byte", "char", "commonmark", "date-time-local", "date-time", "date", "decimal", "decimal128",
    "duration", "email", "hostname", "html", "http-date", "idn-email", "idn-hostname", "int64", "ipv4-cidr", "ipv4",
    "ipv6-cidr", "ipv6", "iri-reference", "iri", "json-pointer", "language", "media-range", "password", "regex",
    "relative-json-pointer", "sf-binary", "sf-boolean", "sf-string", "sf-token", "time-local", "time", "uint64", "unixtime",
    "uri-reference", "uri-template", "uri", "uuid",
}
MISSING = object()


class CaseConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProjectRequestSettings:
    base_url: str
    proxy_url: str | None = None
    proxy_urls: dict[str, str] = field(default_factory=dict)
    no_proxy: bool = False
    verify_ssl: bool = True
    variables: dict[str, str] = field(default_factory=dict)
    encrypted_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: Any


@dataclass(frozen=True)
class AssertionResult:
    path: str
    operator: str
    passed: bool
    expected: dict[str, Any]
    actual: Any
    message: str


@dataclass
class CaseResult:
    case_id: str
    status: str
    attempts: int
    response: HttpResponse | None = None
    differences: list[Difference] = field(default_factory=list)
    assertion_results: list[AssertionResult] = field(default_factory=list)
    error: str | None = None
    request_definition: dict[str, Any] | None = None
    expected_definition: dict[str, Any] | None = None
    sensitive_values: set[str] = field(default_factory=set)


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
    use_proxy = advanced.get("use_proxy", True)
    if not isinstance(use_proxy, bool):
        raise CaseConfigurationError(f"project.advanced.use_proxy must be true or false: {project_reference}")
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
    try:
        variables, encrypted_variables = stored_project_variables(project, project_reference)
    except ProjectVariableError as exc:
        raise CaseConfigurationError(str(exc)) from exc
    no_proxy = not use_proxy
    return ProjectRequestSettings(
        base_url=urlunparse(parsed._replace(path=parsed.path.rstrip("/"))),
        proxy_url=None if no_proxy else legacy_proxy.strip() if isinstance(legacy_proxy, str) and legacy_proxy.strip() else None,
        proxy_urls={} if no_proxy else normalized_proxies,
        no_proxy=no_proxy,
        verify_ssl=verify_ssl,
        variables=variables,
        encrypted_variables=encrypted_variables,
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


def _is_number(value: Any) -> bool:
    return type(value) in {int, float}


def _assertion_path_value(response: HttpResponse, path: str) -> Any:
    normalized = path.removeprefix("$.")
    current: Any = {"status": response.status, "body": response.body}
    for piece in normalized.split("."):
        if isinstance(current, dict) and piece in current:
            current = current[piece]
        elif isinstance(current, list) and piece.isdigit() and int(piece) < len(current):
            current = current[int(piece)]
        else:
            return MISSING
    return current


def _json_type_matches(value: Any, expected_type: str) -> bool:
    return {
        "number": _is_number(value),
        "integer": type(value) is int,
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "null": value is None,
    }[expected_type]


def _base64_matches(value: str, *, urlsafe: bool = False) -> bool:
    alphabet = r"[A-Za-z0-9_-]" if urlsafe else r"[A-Za-z0-9+/]"
    if not re.fullmatch(rf"{alphabet}*(?:={{1,2}})?", value) or "=" in value.rstrip("="):
        return False
    try:
        padding = "=" * (-len(value) % 4)
        base64.b64decode(value + padding, altchars=b"-_" if urlsafe else None, validate=True)
        return True
    except (ValueError, binascii.Error):
        return False


def _hostname_matches(value: str) -> bool:
    hostname = value[:-1] if value.endswith(".") else value
    if not hostname or len(hostname) > 253:
        return False
    return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in hostname.split("."))


def _time_matches(value: str, *, timezone_required: bool) -> bool:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:(Z)|([+-])(\d{2}):(\d{2}))?", value)
    if not match:
        return False
    hour, minute, second = (int(match.group(index)) for index in range(1, 4))
    has_timezone = bool(match.group(4) or match.group(5))
    if hour > 23 or minute > 59 or second > 60 or has_timezone != timezone_required:
        return False
    return not match.group(5) or (int(match.group(6)) <= 23 and int(match.group(7)) <= 59)


def _date_time_matches(value: str, *, timezone_required: bool) -> bool:
    date_part, separator, time_part = value.partition("T")
    if not separator:
        return False
    try:
        date.fromisoformat(date_part)
    except ValueError:
        return False
    return _time_matches(time_part, timezone_required=timezone_required)


def _uri_reference_matches(value: str) -> bool:
    return not re.search(r"\s", value) and not re.search(r"%(?![0-9A-Fa-f]{2})", value)


def _string_format_matches(value: str, expected_format: str) -> bool:
    if expected_format in {"binary", "commonmark", "html", "password"}:
        return True
    if expected_format == "base64url":
        return _base64_matches(value, urlsafe=True)
    if expected_format == "byte":
        return _base64_matches(value)
    if expected_format == "char":
        return len(value) == 1
    if expected_format == "date":
        try:
            date.fromisoformat(value)
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        except ValueError:
            return False
    if expected_format == "date-time":
        return _date_time_matches(value, timezone_required=True)
    if expected_format == "date-time-local":
        return _date_time_matches(value, timezone_required=False)
    if expected_format == "time":
        return _time_matches(value, timezone_required=True)
    if expected_format == "time-local":
        return _time_matches(value, timezone_required=False)
    if expected_format == "duration":
        return bool(re.fullmatch(r"P(?=\d|T\d)(?:\d+Y)?(?:\d+M)?(?:\d+D)?(?:T(?=\d)(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?", value))
    if expected_format in {"email", "idn-email"}:
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))
    if expected_format in {"hostname", "idn-hostname"}:
        try:
            return _hostname_matches(value.encode("idna").decode("ascii"))
        except UnicodeError:
            return False
    if expected_format == "http-date":
        try:
            return parsedate_to_datetime(value) is not None
        except (TypeError, ValueError):
            return False
    if expected_format in {"decimal", "decimal128"}:
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
            return False
        return expected_format != "decimal128" or len(value.lstrip("+-").replace(".", "")) <= 34
    if expected_format == "int64":
        return bool(re.fullmatch(r"-?\d+", value)) and -(2**63) <= int(value) < 2**63
    if expected_format == "uint64":
        return bool(re.fullmatch(r"\d+", value)) and int(value) < 2**64
    if expected_format == "unixtime":
        return bool(re.fullmatch(r"-?\d+", value))
    if expected_format in {"ipv4", "ipv6"}:
        try:
            return ipaddress.ip_address(value).version == (4 if expected_format == "ipv4" else 6)
        except ValueError:
            return False
    if expected_format in {"ipv4-cidr", "ipv6-cidr"}:
        try:
            return "/" in value and ipaddress.ip_network(value, strict=False).version == (4 if expected_format == "ipv4-cidr" else 6)
        except ValueError:
            return False
    if expected_format in {"iri", "uri"}:
        return _uri_reference_matches(value) and bool(re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", value))
    if expected_format in {"iri-reference", "uri-reference"}:
        return _uri_reference_matches(value)
    if expected_format == "uri-template":
        expressions = re.findall(r"\{[^{}]+\}", value)
        return _uri_reference_matches(value) and value.count("{") == len(expressions) and value.count("}") == len(expressions)
    if expected_format == "uuid":
        try:
            return str(uuid.UUID(value)) == value.lower()
        except ValueError:
            return False
    if expected_format == "json-pointer":
        return bool(re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", value))
    if expected_format == "relative-json-pointer":
        return bool(re.fullmatch(r"(?:0|[1-9]\d*)(?:#|(?:/(?:[^~/]|~[01])*)*)", value))
    if expected_format == "language":
        return bool(re.fullmatch(r"(?:[A-Za-z]{2,8}|x)(?:-[A-Za-z0-9]{1,8})*", value))
    if expected_format == "media-range":
        return bool(re.fullmatch(r"[^/\s;]+/(?:[^\s;]+|\*)(?:\s*;\s*[^=\s;]+=[^;]+)*", value))
    if expected_format == "regex":
        try:
            re.compile(value)
            return True
        except re.error:
            return False
    if expected_format == "sf-binary":
        return len(value) >= 2 and value.startswith(":") and value.endswith(":") and _base64_matches(value[1:-1])
    if expected_format == "sf-boolean":
        return value in {"?0", "?1"}
    if expected_format == "sf-string":
        return bool(re.fullmatch(r'"(?:[\x20-\x21\x23-\x5B\x5D-\x7E]|\\["\\])*"', value))
    if expected_format == "sf-token":
        return bool(re.fullmatch(r"[A-Za-z*][!#$%&'*+\-.^_`|~:/0-9A-Za-z]*", value))
    return False


def _validate_string_format(expected_format: Any, pattern: Any, prefix: str) -> None:
    if expected_format not in STRING_FORMATS | {NO_STRING_FORMAT, CUSTOM_STRING_FORMAT}:
        raise CaseConfigurationError(f"{prefix} must be one of: {', '.join(sorted(STRING_FORMATS | {NO_STRING_FORMAT, CUSTOM_STRING_FORMAT}))}")
    if expected_format != CUSTOM_STRING_FORMAT:
        return
    pattern_prefix = f"{prefix.rpartition('.')[0]}.pattern"
    if not isinstance(pattern, str) or not pattern:
        raise CaseConfigurationError(f"{pattern_prefix} must be a non-empty regular expression for custom format")
    try:
        re.compile(pattern)
    except re.error as error:
        raise CaseConfigurationError(f"{pattern_prefix} is not a valid regular expression: {error}") from error


def validate_assertions(assertions: Any) -> None:
    """Validate response conditions before an HTTP request is sent."""
    if assertions is None:
        return
    if not isinstance(assertions, list):
        raise CaseConfigurationError("expected.assertions must be an array")
    for index, assertion in enumerate(assertions, start=1):
        prefix = f"expected.assertions[{index}]"
        if not isinstance(assertion, dict):
            raise CaseConfigurationError(f"{prefix} must be an object")
        path = assertion.get("path")
        if not isinstance(path, str) or not ASSERTION_PATH_PATTERN.fullmatch(path):
            raise CaseConfigurationError(f"{prefix}.path must be body, body.field, body.items.0, or status")
        operator = assertion.get("operator")
        if operator not in ASSERTION_OPERATORS:
            raise CaseConfigurationError(f"{prefix}.operator is not supported: {operator}")
        if operator in {"gt", "gte", "lt", "lte"}:
            if not _is_number(assertion.get("value")):
                raise CaseConfigurationError(f"{prefix}.value must be a number for {operator}")
        elif operator == "between":
            minimum, maximum = assertion.get("min"), assertion.get("max")
            if not _is_number(minimum) or not _is_number(maximum):
                raise CaseConfigurationError(f"{prefix}.min and max must be numbers for between")
            if minimum > maximum:
                raise CaseConfigurationError(f"{prefix}.min must be less than or equal to max")
            for option in ("include_min", "include_max"):
                if option in assertion and not isinstance(assertion[option], bool):
                    raise CaseConfigurationError(f"{prefix}.{option} must be true or false")
        elif operator == "length_between":
            minimum, maximum = assertion.get("min"), assertion.get("max")
            if type(minimum) is not int or type(maximum) is not int or minimum < 0 or maximum < 0:
                raise CaseConfigurationError(f"{prefix}.min and max must be non-negative integers for length_between")
            if minimum > maximum:
                raise CaseConfigurationError(f"{prefix}.min must be less than or equal to max")
        elif operator == "format":
            _validate_string_format(assertion.get("value", NO_STRING_FORMAT), assertion.get("pattern"), f"{prefix}.value")
        elif operator == "type":
            expected_type = assertion.get("value")
            if expected_type not in JSON_TYPE_NAMES:
                raise CaseConfigurationError(f"{prefix}.value must be one of: {', '.join(sorted(JSON_TYPE_NAMES))}")
            if expected_type == "string":
                _validate_string_format(assertion.get("format", NO_STRING_FORMAT), assertion.get("pattern"), f"{prefix}.format")
            elif "format" in assertion:
                raise CaseConfigurationError(f"{prefix}.format is only supported when {prefix}.value is string")


def response_validation_modes(expected: dict[str, Any]) -> tuple[bool, bool]:
    """Return exact-body and condition validation flags with legacy-case defaults."""
    modes = expected.get("validation_modes")
    if modes is None:
        return "body" in expected, "assertions" in expected
    if not isinstance(modes, dict):
        raise CaseConfigurationError("expected.validation_modes must be an object")
    exact_body = modes.get("exact_body", "body" in expected)
    conditions = modes.get("conditions", "assertions" in expected)
    if not isinstance(exact_body, bool):
        raise CaseConfigurationError("expected.validation_modes.exact_body must be true or false")
    if not isinstance(conditions, bool):
        raise CaseConfigurationError("expected.validation_modes.conditions must be true or false")
    if exact_body and "body" not in expected:
        raise CaseConfigurationError("expected.body is required when exact_body validation is enabled")
    if conditions and not expected.get("assertions"):
        raise CaseConfigurationError("expected.assertions needs at least one condition when conditions validation is enabled")
    return exact_body, conditions


def evaluate_assertions(assertions: Any, response: HttpResponse) -> tuple[list[AssertionResult], list[Difference]]:
    """Evaluate every response condition and return its result plus failed differences."""
    validate_assertions(assertions)
    results: list[AssertionResult] = []
    differences: list[Difference] = []
    for assertion in assertions or []:
        path = assertion["path"].removeprefix("$.")
        display_path = f"$.{path}"
        operator = assertion["operator"]
        actual = _assertion_path_value(response, path)
        expected_condition = {key: value for key, value in assertion.items() if key != "path"}

        def record(passed: bool, result_actual: Any, message: str) -> None:
            results.append(AssertionResult(display_path, operator, passed, expected_condition, result_actual, message))
            if not passed:
                differences.append(Difference(display_path, expected_condition, result_actual, message))

        if operator == "exists":
            if actual is MISSING:
                record(False, None, "assertion path missing")
            else:
                record(True, actual, "path exists")
            continue
        if operator == "not_exists":
            if actual is not MISSING:
                record(False, actual, "condition not met: expected path to be absent")
            else:
                record(True, None, "path is absent")
            continue
        if actual is MISSING:
            record(False, None, "assertion path missing")
            continue
        if operator == "type":
            expected_type = assertion["value"]
            if not _json_type_matches(actual, expected_type):
                record(False, actual, f"type mismatch: expected {expected_type}")
                continue
            if expected_type != "string":
                record(True, actual, f"type matched: {expected_type}")
                continue
            expected_format = assertion.get("format", NO_STRING_FORMAT)
            if expected_format == NO_STRING_FORMAT:
                record(True, actual, "type matched: string; format validation skipped")
                continue
            if expected_format == CUSTOM_STRING_FORMAT:
                pattern = assertion["pattern"]
                passed = re.fullmatch(pattern, actual) is not None
                record(passed, actual, "custom format matched" if passed else f"format mismatch: pattern {pattern}")
                continue
            passed = _string_format_matches(actual, expected_format)
            record(passed, actual, f"format matched: {expected_format}" if passed else f"format mismatch: expected {expected_format}")
            continue
        if operator == "length_between":
            if not isinstance(actual, (str, list)):
                record(False, actual, "length assertion requires a string or array")
                continue
            actual_length = len(actual)
            passed = assertion["min"] <= actual_length <= assertion["max"]
            description = f"expected {assertion['min']} <= length <= {assertion['max']}, actual length {actual_length}"
            record(passed, actual_length, description if passed else f"length condition not met: {description}")
            continue
        if operator == "format":
            expected_format = assertion.get("value", NO_STRING_FORMAT)
            if expected_format == NO_STRING_FORMAT:
                record(True, actual, "format validation skipped")
                continue
            if not isinstance(actual, str):
                record(False, actual, "format assertion requires a string")
                continue
            if expected_format == CUSTOM_STRING_FORMAT:
                pattern = assertion["pattern"]
                passed = re.fullmatch(pattern, actual) is not None
                record(passed, actual, "custom format matched" if passed else f"format mismatch: pattern {pattern}")
                continue
            passed = _string_format_matches(actual, expected_format)
            record(passed, actual, f"format matched: {expected_format}" if passed else f"format mismatch: expected {expected_format}")
            continue
        if not _is_number(actual):
            record(False, actual, "numeric assertion requires a number")
            continue

        passed = False
        description = ""
        if operator == "gt":
            passed, description = actual > assertion["value"], f"> {assertion['value']}"
        elif operator == "gte":
            passed, description = actual >= assertion["value"], f">= {assertion['value']}"
        elif operator == "lt":
            passed, description = actual < assertion["value"], f"< {assertion['value']}"
        elif operator == "lte":
            passed, description = actual <= assertion["value"], f"<= {assertion['value']}"
        elif operator == "between":
            include_min = assertion.get("include_min", True)
            include_max = assertion.get("include_max", True)
            lower_passed = actual >= assertion["min"] if include_min else actual > assertion["min"]
            upper_passed = actual <= assertion["max"] if include_max else actual < assertion["max"]
            passed = lower_passed and upper_passed
            description = (
                f"{'<=' if include_min else '<'} value {'<=' if include_max else '<'} {assertion['max']}"
            )
            description = f"{assertion['min']} {description}"
        record(passed, actual, f"condition met: expected {description}" if passed else f"condition not met: expected {description}")
    return results, differences


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
        no_proxy: bool = False,
        project_variables: dict[str, str] | None = None,
        encrypted_project_variables: dict[str, str] | None = None,
    ) -> CaseResult:
        request_definition = case.get("request")
        expected = case.get("expected")
        if not isinstance(request_definition, dict) or not isinstance(expected, dict):
            raise CaseConfigurationError("A case needs object-valued request and expected fields")
        if not isinstance(request_definition.get("url"), str):
            raise CaseConfigurationError("request.url is required")
        _, validate_conditions = response_validation_modes(expected)
        if validate_conditions:
            validate_assertions(expected.get("assertions"))
        timeout_seconds = self.timeout_seconds
        case_timeout = case.get("timeout")
        if case_timeout is not None:
            if isinstance(case_timeout, bool) or not isinstance(case_timeout, (int, float)) or not math.isfinite(case_timeout) or case_timeout <= 0:
                raise CaseConfigurationError("case.timeout must be a positive number of seconds")
            timeout_seconds = float(case_timeout)

        resolved_request = resolve_references(copy.deepcopy(request_definition), context or {})
        try:
            resolved_request, sensitive_values = resolve_project_references(
                resolved_request,
                project_variables or {},
                encrypted_project_variables or {},
            )
            resolved_request, case_sensitive_values = resolve_case_references(
                resolved_request,
                stored_case_variables(case, case_id),
            )
            sensitive_values.update(case_sensitive_values)
        except ProjectVariableError as exc:
            raise CaseConfigurationError(str(exc)) from exc
        resolved_request["url"] = resolve_request_url(resolved_request["url"], base_url)
        attempts = max(0, retry) + 1
        last_result: CaseResult | None = None
        for attempt in range(1, attempts + 1):
            result = self._run_once(
                case_id, resolved_request, expected, attempt, proxy_url, verify_ssl,
                file_root, proxy_urls, no_proxy, sensitive_values, timeout_seconds,
            )
            if result.status == "passed":
                return result
            last_result = result
            if attempt < attempts and retry_interval_seconds > 0:
                time.sleep(retry_interval_seconds)
        assert last_result is not None
        return last_result

    def _run_once(
        self, case_id: str, request_definition: dict[str, Any], expected: dict[str, Any], attempt: int,
        proxy_url: str | None = None, verify_ssl: bool = True, file_root: Path | None = None,
        proxy_urls: dict[str, str] | None = None, no_proxy: bool = False, sensitive_values: set[str] | None = None,
        timeout_seconds: float | None = None,
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
        request_timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            if no_proxy or proxy_url or proxy_urls or not verify_ssl:
                handlers: list[Any] = []
                if no_proxy:
                    handlers.append(urllib.request.ProxyHandler({}))
                elif proxy_urls:
                    handlers.append(urllib.request.ProxyHandler(proxy_urls))
                elif proxy_url:
                    handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
                if not verify_ssl:
                    handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
                opener = urllib.request.build_opener(*handlers)
                opened_response = opener.open(request, timeout=request_timeout)
            else:
                opened_response = urllib.request.urlopen(request, timeout=request_timeout)
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
                sensitive_values=set(sensitive_values or ()),
            )

        try:
            body: Any = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError:
            body = raw_body
        response = HttpResponse(status, response_headers, body)
        differences: list[Difference] = []
        assertion_results: list[AssertionResult] = []
        if "status" in expected and expected["status"] != status:
            differences.append(Difference("$.status", expected["status"], status, "status mismatch"))
        validate_exact_body, validate_conditions = response_validation_modes(expected)
        if validate_exact_body:
            differences.extend(compare_json(expected["body"], body, "$.body", strict=expected.get("strict", True)))
        if validate_conditions:
            assertion_results, assertion_differences = evaluate_assertions(expected.get("assertions"), response)
            differences.extend(assertion_differences)
        return CaseResult(
            case_id, "passed" if not differences else "failed", attempt, response, differences,
            assertion_results=assertion_results,
            request_definition=request_definition, expected_definition=expected,
            sensitive_values=set(sensitive_values or ()),
        )
