"""Build a sanitized load-test result bundle from k6 summary and JSON output."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, TextIO
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_VERSION = 1
DEFAULT_BUCKET_SECONDS = 5
MAX_BUCKETS = 100_000
MAX_RAW_LINE_CHARS = 1_048_576
SENSITIVE_PARTS = ("authorization", "apikey", "cookie", "password", "secret", "token")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
COMMIT_SHA = re.compile(r"^[0-9A-Fa-f]{7,64}$")
METHOD = re.compile(r"^[A-Za-z]+$")
UUID_SEGMENT = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
HEX_SEGMENT = re.compile(r"^[0-9a-fA-F]{20,64}$")
OPAQUE_SEGMENT = re.compile(r"^(?=.{20,128}$)(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]+$")
THRESHOLD = re.compile(
    r"^\s*(p\((\d+(?:\.\d+)?)\)|avg|min|max|med|rate|count|value)\s*"
    r"(<=|>=|==|!=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)


class LoadResultError(ValueError):
    """A safe, user-facing importer error that never includes raw event values."""


@dataclass
class Bucket:
    requests: float = 0.0
    durations: list[float] = field(default_factory=list)
    failures: float = 0.0
    failure_samples: int = 0
    active_vus: float = 0.0
    active_vus_at: datetime | None = None
    cpu_percent: float | None = None
    cpu_at: datetime | None = None
    memory_mb: float | None = None
    memory_at: datetime | None = None
    child_processes: float | None = None
    child_processes_at: datetime | None = None


@dataclass
class Endpoint:
    durations: list[float] = field(default_factory=list)
    failures: float = 0.0
    failure_samples: int = 0


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite number")


def _number(value: Any, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LoadResultError(f"{label} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise LoadResultError(f"{label} is below its minimum")
    if maximum is not None and result > maximum:
        raise LoadResultError(f"{label} is above its maximum")
    return result


def _whole(value: float, label: str) -> int:
    rounded = round(value)
    if not math.isclose(value, rounded, abs_tol=1e-9):
        raise LoadResultError(f"{label} must resolve to a whole number")
    return int(rounded)


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(char) < 32 for char in value):
        raise LoadResultError(f"{label} must be a non-empty safe string")
    return value


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise LoadResultError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise LoadResultError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise LoadResultError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _time_text(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _rounded(value: float) -> float:
    return round(value, 6)


def _load_json(path: Path, label: str) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LoadResultError(f"{label} is not readable valid JSON") from exc


def _manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], datetime, datetime]:
    document = _load_json(path, "summary manifest")
    if not isinstance(document, dict) or document.get("formatVersion") != 1:
        raise LoadResultError("summary manifest formatVersion must be 1")
    raw_run = document.get("run")
    if not isinstance(raw_run, dict):
        raise LoadResultError("summary manifest run must be an object")

    run_id = _text(raw_run.get("id"), "run.id", 128)
    if not RUN_ID.fullmatch(run_id):
        raise LoadResultError("run.id has an unsupported format")
    started_at = _time(raw_run.get("startedAt"), "run.startedAt")
    ended_at = _time(raw_run.get("endedAt"), "run.endedAt")
    if ended_at <= started_at:
        raise LoadResultError("run.endedAt must be after run.startedAt")
    status = raw_run.get("status", "passed")
    if status not in {"passed", "failed", "aborted", "error"}:
        raise LoadResultError("run.status is unsupported")

    commit_sha = raw_run.get("commitSha")
    if commit_sha is not None and (not isinstance(commit_sha, str) or not COMMIT_SHA.fullmatch(commit_sha)):
        raise LoadResultError("run.commitSha must be a hexadecimal Git revision")
    app_version = raw_run.get("appVersion")
    if app_version is not None:
        app_version = _text(app_version, "run.appVersion", 120)

    raw_environment = raw_run.get("environment")
    if not isinstance(raw_environment, dict):
        raise LoadResultError("run.environment must be an object")
    memory_mb = raw_environment.get("memoryMb")
    if memory_mb is not None:
        memory_mb = _number(memory_mb, "run.environment.memoryMb", minimum=0)
    k6_version = raw_environment.get("k6Version")
    if k6_version is not None:
        k6_version = _text(k6_version, "run.environment.k6Version", 80)
    environment = {
        "os": _text(raw_environment.get("os"), "run.environment.os", 120),
        "cpu": _text(raw_environment.get("cpu"), "run.environment.cpu", 120),
        "memoryMb": memory_mb,
        "executionMode": _text(raw_environment.get("executionMode"), "run.environment.executionMode", 80),
        "k6Version": k6_version,
    }
    run = {
        "id": run_id,
        "project": _text(raw_run.get("project"), "run.project", 255),
        "scenario": _text(raw_run.get("scenario"), "run.scenario", 120),
        "startedAt": _time_text(started_at),
        "endedAt": _time_text(ended_at),
        "status": status,
        "appVersion": app_version,
        "commitSha": commit_sha,
        "environment": environment,
    }

    manifest_thresholds = []
    raw_thresholds = document.get("thresholds", [])
    if not isinstance(raw_thresholds, list):
        raise LoadResultError("summary manifest thresholds must be an array")
    for index, item in enumerate(raw_thresholds):
        if not isinstance(item, dict) or not isinstance(item.get("passed"), bool):
            raise LoadResultError(f"summary manifest threshold {index} is invalid")
        manifest_thresholds.append({
            "metric": _text(item.get("metric"), f"thresholds[{index}].metric", 200),
            "condition": _text(item.get("condition"), f"thresholds[{index}].condition", 200),
            "passed": item["passed"],
        })
    return run, manifest_thresholds, started_at, ended_at


def _open_raw(path: Path) -> TextIO:
    try:
        if path.suffix == ".gz":
            return gzip.open(path, mode="rt", encoding="utf-8")
        return path.open(encoding="utf-8")
    except OSError as exc:
        raise LoadResultError("raw k6 output is not readable") from exc


def _raw_events(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    try:
        with _open_raw(path) as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                if len(line) > MAX_RAW_LINE_CHARS:
                    raise LoadResultError(f"raw k6 line {line_number} exceeds the size limit")
                try:
                    event = json.loads(line, parse_constant=_reject_constant)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise LoadResultError(f"raw k6 line {line_number} is invalid JSON") from exc
                if not isinstance(event, dict):
                    raise LoadResultError(f"raw k6 line {line_number} must be an object")
                yield line_number, event
    except (OSError, UnicodeError) as exc:
        raise LoadResultError("raw k6 output could not be read") from exc


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _latency(values: list[float]) -> dict[str, float]:
    return {
        "p50": _rounded(_percentile(values, 0.50)),
        "p90": _rounded(_percentile(values, 0.90)),
        "p95": _rounded(_percentile(values, 0.95)),
        "p99": _rounded(_percentile(values, 0.99)),
        "max": _rounded(max(values, default=0.0)),
    }


def normalize_endpoint(tags: dict[str, Any]) -> tuple[str, str]:
    raw_method = tags.get("method")
    if not isinstance(raw_method, str) or not METHOD.fullmatch(raw_method):
        raise LoadResultError("an HTTP metric is missing a safe method tag")
    raw_endpoint = tags.get("name") or tags.get("url")
    if not isinstance(raw_endpoint, str) or not raw_endpoint:
        raise LoadResultError("an HTTP metric is missing a name or URL tag")
    if len(raw_endpoint) > 4096 or any(ord(char) < 32 for char in raw_endpoint):
        raise LoadResultError("an HTTP metric endpoint tag is unsafe")

    value = raw_endpoint.strip()
    if " " in value and value.split(" ", 1)[0].upper() == raw_method.upper():
        value = value.split(" ", 1)[1]
    try:
        parsed = urlsplit(value if "://" in value else "http://studio.local" + (value if value.startswith("/") else "/" + value))
    except ValueError as exc:
        raise LoadResultError("an HTTP metric endpoint tag is invalid") from exc
    path = parsed.path or "/"
    segments = []
    for segment in path.split("/"):
        if not segment:
            continue
        if segment.isdigit() or UUID_SEGMENT.fullmatch(segment) or HEX_SEGMENT.fullmatch(segment) or OPAQUE_SEGMENT.fullmatch(segment):
            segments.append("{id}")
        else:
            segments.append(segment)
    normalized = "/" + "/".join(segments)
    if len(normalized) > 512:
        raise LoadResultError("a normalized endpoint exceeds the size limit")
    return raw_method.upper(), normalized


def _public_metric(metric: str) -> str:
    base = metric.split("{", 1)[0]
    normalized = re.sub(r"[^a-z0-9]", "", base.lower())
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", base) or any(part in normalized for part in SENSITIVE_PARTS):
        return "custom_metric"
    return base + ("{filtered}" if "{" in metric else "")


def _threshold_actual(
    metric: str,
    condition: str,
    definitions: dict[str, dict[str, Any]],
    samples: dict[str, list[tuple[datetime, float]]],
    duration_seconds: float,
) -> tuple[float | None, bool | None]:
    match = THRESHOLD.fullmatch(condition)
    if not match or metric not in definitions or not samples.get(metric):
        return None, None
    selector, percentile_text, operator, expected_text = match.groups()
    values = [value for _, value in samples[metric]]
    metric_type = definitions[metric].get("type")
    actual: float | None = None
    if selector.startswith("p(") and metric_type == "trend":
        percentile = float(percentile_text)
        if 0 <= percentile <= 100:
            actual = _percentile(values, percentile / 100)
    elif selector == "med" and metric_type == "trend":
        actual = _percentile(values, 0.5)
    elif selector == "avg" and metric_type == "trend":
        actual = sum(values) / len(values)
    elif selector == "min":
        actual = min(values)
    elif selector == "max":
        actual = max(values)
    elif selector == "count" and metric_type == "counter":
        actual = sum(values)
    elif selector == "rate" and metric_type == "counter":
        actual = sum(values) / duration_seconds
    elif selector == "rate" and metric_type == "rate":
        actual = sum(values) / len(values)
    elif selector == "value" and metric_type == "gauge":
        actual = max(samples[metric], key=lambda item: item[0])[1]
    if actual is None:
        return None, None
    expected = float(expected_text)
    verdict = {
        "<": actual < expected,
        "<=": actual <= expected,
        ">": actual > expected,
        ">=": actual >= expected,
        "==": actual == expected,
        "!=": actual != expected,
    }[operator]
    return _rounded(actual), verdict


def _latest(bucket: Bucket, attribute: str, timestamp_attribute: str, timestamp: datetime, value: float) -> None:
    previous = getattr(bucket, timestamp_attribute)
    if previous is None or timestamp >= previous:
        setattr(bucket, timestamp_attribute, timestamp)
        setattr(bucket, attribute, value)


def import_k6_result(summary_path: Path, raw_path: Path, bucket_seconds: int = DEFAULT_BUCKET_SECONDS) -> dict[str, Any]:
    if not isinstance(bucket_seconds, int) or isinstance(bucket_seconds, bool) or not 1 <= bucket_seconds <= 3600:
        raise LoadResultError("bucket seconds must be an integer between 1 and 3600")
    run, manifest_thresholds, started_at, ended_at = _manifest(Path(summary_path))
    duration_seconds = (ended_at - started_at).total_seconds()
    bucket_count = math.ceil(duration_seconds / bucket_seconds)
    if bucket_count > MAX_BUCKETS:
        raise LoadResultError("run duration creates too many time buckets")

    definitions: dict[str, dict[str, Any]] = {}
    definition_thresholds: list[tuple[str, str]] = []
    threshold_metrics = {item["metric"] for item in manifest_thresholds}
    samples: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    buckets: dict[int, Bucket] = defaultdict(Bucket)
    endpoints: dict[tuple[str, str], Endpoint] = defaultdict(Endpoint)
    requests = 0.0
    durations: list[float] = []
    failures = 0.0
    failure_samples = 0
    vus_max = 0.0

    for line_number, event in _raw_events(Path(raw_path)):
        event_type = event.get("type")
        metric = event.get("metric")
        data = event.get("data")
        if event_type not in {"Metric", "Point"} or not isinstance(metric, str) or not isinstance(data, dict):
            raise LoadResultError(f"raw k6 line {line_number} has an unsupported event shape")
        if event_type == "Metric":
            metric_type = data.get("type")
            if metric_type not in {"counter", "gauge", "rate", "trend"}:
                raise LoadResultError(f"raw k6 line {line_number} declares an unsupported metric type")
            raw_thresholds = data.get("thresholds") or []
            if not isinstance(raw_thresholds, list) or not all(isinstance(item, str) for item in raw_thresholds):
                raise LoadResultError(f"raw k6 line {line_number} has invalid thresholds")
            definitions[metric] = {"type": metric_type, "tainted": data.get("tainted")}
            definition_thresholds.extend((metric, item) for item in raw_thresholds)
            if raw_thresholds:
                threshold_metrics.add(metric)
            continue

        if metric not in definitions:
            raise LoadResultError(f"raw k6 line {line_number} uses a metric before its declaration")
        timestamp = _time(data.get("time"), f"raw k6 line {line_number} time")
        if timestamp < started_at or timestamp > ended_at:
            raise LoadResultError(f"raw k6 line {line_number} is outside the declared run interval")
        value = _number(data.get("value"), f"raw k6 line {line_number} value")
        tags = data.get("tags") or {}
        if not isinstance(tags, dict):
            raise LoadResultError(f"raw k6 line {line_number} tags must be an object or null")
        if metric in threshold_metrics:
            samples[metric].append((timestamp, value))

        index = min(int((timestamp - started_at).total_seconds() // bucket_seconds), bucket_count - 1)
        bucket = buckets[index]
        if metric == "http_reqs":
            requests += value
            bucket.requests += value
        elif metric == "http_req_duration":
            if value < 0:
                raise LoadResultError(f"raw k6 line {line_number} has negative latency")
            key = normalize_endpoint(tags)
            durations.append(value)
            endpoints[key].durations.append(value)
            bucket.durations.append(value)
        elif metric == "http_req_failed":
            if not 0 <= value <= 1:
                raise LoadResultError(f"raw k6 line {line_number} has an invalid failure sample")
            key = normalize_endpoint(tags)
            failures += value
            failure_samples += 1
            endpoints[key].failures += value
            endpoints[key].failure_samples += 1
            bucket.failures += value
            bucket.failure_samples += 1
        elif metric in {"vus", "vus_max"}:
            vus_max = max(vus_max, value)
            if metric == "vus":
                _latest(bucket, "active_vus", "active_vus_at", timestamp, value)
        elif metric == "studio_cpu_percent":
            _number(value, "studio_cpu_percent", minimum=0, maximum=100)
            _latest(bucket, "cpu_percent", "cpu_at", timestamp, value)
        elif metric == "studio_memory_mb":
            _number(value, "studio_memory_mb", minimum=0)
            _latest(bucket, "memory_mb", "memory_at", timestamp, value)
        elif metric == "studio_child_processes":
            _number(value, "studio_child_processes", minimum=0)
            _latest(bucket, "child_processes", "child_processes_at", timestamp, value)

    missing = sorted({"http_reqs", "http_req_duration", "http_req_failed"} - definitions.keys())
    if missing:
        raise LoadResultError("raw k6 output is missing required HTTP metric declarations")
    if any(item["metric"] not in definitions for item in manifest_thresholds):
        raise LoadResultError("summary threshold metric is missing from raw k6 output")
    request_count = _whole(requests, "http_reqs total")
    if request_count != len(durations) or request_count != failure_samples:
        raise LoadResultError("raw k6 HTTP metric sample counts do not match")
    for endpoint in endpoints.values():
        if len(endpoint.durations) != endpoint.failure_samples:
            raise LoadResultError("raw k6 endpoint metric sample counts do not match")

    warnings: list[str] = []
    manifest_verdicts = {(item["metric"], item["condition"]): item["passed"] for item in manifest_thresholds}
    ordered_thresholds: list[tuple[str, str]] = []
    for item in [*definition_thresholds, *((item["metric"], item["condition"]) for item in manifest_thresholds)]:
        if item not in ordered_thresholds:
            ordered_thresholds.append(item)
    threshold_results = []
    for metric, condition in ordered_thresholds:
        actual, calculated = _threshold_actual(metric, condition, definitions, samples, duration_seconds)
        manifest_verdict = manifest_verdicts.get((metric, condition))
        if manifest_verdict is not None:
            passed = manifest_verdict
            if calculated is not None and calculated != manifest_verdict:
                warnings.append(f"k6 threshold verdict differs from raw aggregate for {_public_metric(metric)}")
        elif calculated is not None:
            passed = calculated
        else:
            same_metric = [item for item in definition_thresholds if item[0] == metric]
            tainted = definitions.get(metric, {}).get("tainted")
            if isinstance(tainted, bool) and len(same_metric) == 1:
                passed = not tainted
            else:
                passed = False
                warnings.append(f"unsupported threshold expression for {_public_metric(metric)}")
        threshold_results.append({
            "metric": _public_metric(metric),
            "condition": condition if THRESHOLD.fullmatch(condition) else "unsupported",
            "actualValue": actual,
            "passed": passed,
        })

    thresholds_passed = all(item["passed"] for item in threshold_results)
    if run["status"] == "passed" and not thresholds_passed:
        run["status"] = "failed"
    endpoint_metrics = []
    for (method, endpoint_name), values in sorted(endpoints.items()):
        endpoint_metrics.append({
            "method": method,
            "endpoint": endpoint_name,
            "requestCount": len(values.durations),
            "errorRate": _rounded(values.failures / values.failure_samples),
            "latencyMs": _latency(values.durations),
        })

    series = []
    active_vus = 0
    for index in range(bucket_count):
        bucket = buckets[index]
        if bucket.active_vus_at is not None:
            active_vus = _whole(bucket.active_vus, "active VUs")
        bucket_at = started_at + timedelta(seconds=index * bucket_seconds)
        span = min(bucket_seconds, (ended_at - bucket_at).total_seconds())
        series.append({
            "bucketAt": _time_text(bucket_at),
            "rps": _rounded(bucket.requests / span),
            "activeVus": active_vus,
            "errorRate": _rounded(bucket.failures / bucket.failure_samples) if bucket.failure_samples else 0.0,
            "p95Ms": _rounded(_percentile(bucket.durations, 0.95)) if bucket.durations else None,
            "cpuPercent": _rounded(bucket.cpu_percent) if bucket.cpu_percent is not None else None,
            "memoryMb": _rounded(bucket.memory_mb) if bucket.memory_mb is not None else None,
            "childProcesses": _whole(bucket.child_processes, "child process count") if bucket.child_processes is not None else None,
        })

    bundle = {
        "schemaVersion": SCHEMA_VERSION,
        "run": run,
        "summary": {
            "requests": request_count,
            "rps": _rounded(request_count / duration_seconds),
            "errorRate": _rounded(failures / failure_samples) if failure_samples else 0.0,
            "latencyMs": _latency(durations),
            "vusMax": _whole(vus_max, "maximum VUs"),
            "thresholdsPassed": thresholds_passed,
        },
        "thresholds": threshold_results,
        "endpointMetrics": endpoint_metrics,
        "series": series,
        "warnings": warnings,
    }
    validate_bundle(bundle)
    return bundle


def _walk_numbers(value: Any, path: str = "$") -> Iterable[tuple[str, float]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_numbers(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_numbers(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, float(value)


def validate_bundle(bundle: dict[str, Any], schema_path: Path | None = None) -> None:
    for path, value in _walk_numbers(bundle):
        if not math.isfinite(value):
            raise LoadResultError(f"result bundle contains a non-finite number at {path}")
    selected_schema = schema_path or Path(__file__).resolve().parents[1] / "docs" / "load-test-result.schema.json"
    schema = _load_json(selected_schema, "load-test result schema")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(bundle), key=lambda item: tuple(str(part) for part in item.absolute_path))
    if errors:
        location = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in errors[0].absolute_path)
        raise LoadResultError(f"result bundle does not match schema at {location}")
    started_at = _time(bundle["run"]["startedAt"], "run.startedAt")
    ended_at = _time(bundle["run"]["endedAt"], "run.endedAt")
    if ended_at <= started_at:
        raise LoadResultError("result bundle run interval is invalid")
    endpoint_requests = sum(item["requestCount"] for item in bundle["endpointMetrics"])
    if endpoint_requests != bundle["summary"]["requests"]:
        raise LoadResultError("result bundle endpoint request counts do not match the summary")
    if bundle["summary"]["thresholdsPassed"] != all(item["passed"] for item in bundle["thresholds"]):
        raise LoadResultError("result bundle threshold summary is inconsistent")
    if bundle["run"]["status"] == "passed" and not bundle["summary"]["thresholdsPassed"]:
        raise LoadResultError("a passed result bundle cannot contain failed thresholds")
    bucket_times = [_time(item["bucketAt"], "series.bucketAt") for item in bundle["series"]]
    if bucket_times != sorted(set(bucket_times)):
        raise LoadResultError("result bundle series timestamps must be unique and ordered")
    if any(timestamp < started_at or timestamp >= ended_at for timestamp in bucket_times):
        raise LoadResultError("result bundle series timestamps must be inside the run interval")
    if bundle["summary"]["requests"] and not bucket_times:
        raise LoadResultError("a non-empty result bundle must contain time series points")
    for item in bundle["endpointMetrics"]:
        if "?" in item["endpoint"] or "://" in item["endpoint"]:
            raise LoadResultError("result bundle endpoints must not contain origins or query strings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True, help="Studio manifest written by the k6 handleSummary helper")
    parser.add_argument("--raw", type=Path, required=True, help="k6 --out json JSON Lines file, optionally gzip-compressed")
    parser.add_argument("--output", type=Path, required=True, help="Destination for the normalized result bundle")
    parser.add_argument("--bucket-seconds", type=int, default=DEFAULT_BUCKET_SECONDS, help="Time-series bucket width (1..3600)")
    args = parser.parse_args(argv)
    try:
        bundle = import_k6_result(args.summary, args.raw, args.bucket_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (LoadResultError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Wrote load-test result bundle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
