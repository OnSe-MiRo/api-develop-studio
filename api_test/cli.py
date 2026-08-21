from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from .run_log import create_run_logger
from .runner import ApiTestRunner, CaseConfigurationError, CaseResult, project_request_settings, read_json, resolve_case_path


SENSITIVE_FIELD_PARTS = ("authorization", "token", "secret", "password", "api_key", "apikey", "cookie")
MAPPING_RESPONSE_PATH = re.compile(r"(?:body(?:\.[\w-]+)*|status)$")
MAPPING_TARGET_KEY = re.compile(r"[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*$")
EXAMPLE_PROJECT_REFERENCE = "example-api.json"
EXAMPLE_PROJECT_TRUE_VALUES = {"1", "true", "yes", "on"}


def example_project_enabled() -> bool:
    return os.environ.get("EXAMPLE_PROJECT", "false").strip().lower() in EXAMPLE_PROJECT_TRUE_VALUES


def is_disabled_example_pipeline(path: Path) -> bool:
    """Keep the optional sample out of an implicit run-all command when disabled."""
    if example_project_enabled():
        return False
    try:
        document = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return document.get("project") == EXAMPLE_PROJECT_REFERENCE


def _redact(value: Any, key: str = "") -> Any:
    """Keep failure diagnostics useful without writing credentials to disk."""
    if any(part in key.lower() for part in SENSITIVE_FIELD_PARTS):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _json_log_value(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, default=str)


def _retry_config(item: dict[str, Any], defaults: dict[str, Any]) -> tuple[int, float]:
    retry = item.get("retry", defaults.get("retry", 0))
    interval = item.get("retry_interval_seconds", defaults.get("retry_interval_seconds", 0))
    if not isinstance(retry, int) or retry < 0:
        raise CaseConfigurationError("retry must be an integer greater than or equal to 0")
    if not isinstance(interval, (int, float)) or interval < 0:
        raise CaseConfigurationError("retry_interval_seconds must be a non-negative number")
    return retry, float(interval)


def _set_body_value(body: dict[str, Any], path: str, value: Any) -> None:
    target = body
    parts = path.split(".")
    for key in parts[:-1]:
        current = target.get(key)
        if current is None:
            current = {}
            target[key] = current
        if not isinstance(current, dict):
            raise CaseConfigurationError(f"Cannot map a value below non-object body field: {path}")
        target = current
    target[parts[-1]] = value


def apply_input_mappings(case: dict[str, Any], mappings: Any, completed_steps: dict[str, CaseResult], step_index: int) -> dict[str, Any]:
    """Apply pipeline-only previous-step values to a case request before it runs."""
    if mappings is None:
        return case
    if not isinstance(mappings, list):
        raise CaseConfigurationError(f"steps[{step_index}].input_mappings must be an array")
    document = copy.deepcopy(case)
    request = document.get("request")
    if not isinstance(request, dict):
        raise CaseConfigurationError("A case needs an object-valued request")
    for mapping_index, mapping in enumerate(mappings, start=1):
        prefix = f"steps[{step_index}].input_mappings[{mapping_index}]"
        if not isinstance(mapping, dict):
            raise CaseConfigurationError(f"{prefix} must be an object")
        source_step = mapping.get("source_step")
        response_path = mapping.get("response_path")
        target = mapping.get("target")
        template = mapping.get("template", "{{value}}")
        if not isinstance(source_step, str) or source_step not in completed_steps:
            raise CaseConfigurationError(f"{prefix}.source_step must reference an earlier pipeline step")
        if not isinstance(response_path, str) or not MAPPING_RESPONSE_PATH.fullmatch(response_path):
            raise CaseConfigurationError(f"{prefix}.response_path must be body, body.field, or status")
        if target not in {"url", "header", "body"}:
            raise CaseConfigurationError(f"{prefix}.target must be url, header, or body")
        if not isinstance(template, str) or "{{value}}" not in template:
            raise CaseConfigurationError(f"{prefix}.template must contain {{value}}")
        reference = f"${{{source_step}.response.{response_path}}}"
        value = template.replace("{{value}}", reference)
        if target == "url":
            request["url"] = value
            continue
        target_key = mapping.get("target_key")
        if not isinstance(target_key, str) or not MAPPING_TARGET_KEY.fullmatch(target_key):
            raise CaseConfigurationError(f"{prefix}.target_key is required for header and body mappings")
        if target == "header":
            headers = request.setdefault("headers", {})
            if not isinstance(headers, dict):
                raise CaseConfigurationError("request.headers must be an object for a header mapping")
            headers[target_key] = value
            continue
        if "form_data" in request:
            raise CaseConfigurationError("Body mappings cannot be used with request.form_data")
        body = request.setdefault("body", {})
        if not isinstance(body, dict):
            raise CaseConfigurationError("request.body must be an object for a body mapping")
        _set_body_value(body, target_key, value)
    return document


def _result_lines(result: CaseResult) -> list[str]:
    lines = [f"[{result.status.upper()}] {result.case_id} (attempts: {result.attempts})"]
    if result.error:
        lines.append(f"  error: {result.error}")
    for difference in result.differences:
        lines.append(
            f"  {difference.path}: {difference.reason}; "
            f"expected={json.dumps(difference.expected, ensure_ascii=False)}, "
            f"actual={json.dumps(difference.actual, ensure_ascii=False)}"
        )
    if result.status != "passed":
        request_value = result.request_definition or {}
        expected_value = dict(result.expected_definition or {})
        strict = expected_value.pop("strict", None)
        actual_value: dict[str, Any] | None = None
        if result.response:
            actual_value = {"status": result.response.status, "body": result.response.body}
        lines.extend([
            f"  request_value={_json_log_value(request_value)}",
            f"  expected_response={_json_log_value(expected_value)}",
            f"  actual_response={_json_log_value(actual_value)}",
        ])
        if strict is not None:
            lines.append(f"  comparison_options={_json_log_value({'strict': strict})}")
    return lines


def _tag_summary_lines(steps: list[Any], results: dict[str, CaseResult]) -> list[str]:
    """Summarize every planned pipeline step, including steps skipped after a stop."""
    summary: dict[str, dict[str, int]] = {}
    for index, raw_step in enumerate(steps, start=1):
        assert isinstance(raw_step, dict)
        case_reference = raw_step["case"]
        assert isinstance(case_reference, str)
        parts = Path(case_reference).parts
        tag = parts[0] if parts else "unknown"
        counts = summary.setdefault(tag, {"TOTAL": 0, "PASS": 0, "FAIL": 0, "ERROR": 0, "SKIPPED": 0})
        counts["TOTAL"] += 1
        name = raw_step.get("name", f"step_{index}")
        result = results.get(name)
        if result is None:
            counts["SKIPPED"] += 1
        elif result.status == "passed":
            counts["PASS"] += 1
        elif result.status == "failed":
            counts["FAIL"] += 1
        else:
            counts["ERROR"] += 1
    return [
        f"{tag}: TOTAL {counts['TOTAL']} | PASS {counts['PASS']} | FAIL {counts['FAIL']} | "
        f"ERROR {counts['ERROR']} | SKIPPED {counts['SKIPPED']}"
        for tag, counts in summary.items()
    ]


def run_pipeline(
    pipeline_path: Path, case_root: Path, timeout: float, log_dir: Path = Path("logs"), project_root: Path = Path("projects"), file_root: Path | None = None,
) -> int:
    logger, log_path = create_run_logger(log_dir)

    def report(message: str, level: int = logging.INFO) -> None:
        print(message)
        logger.log(level, message)

    logger.info("Pipeline started: pipeline=%s case_root=%s timeout=%s", pipeline_path, case_root, timeout)
    logger.info("Sensitive request headers and bodies are intentionally not written to logs.")
    pipeline = read_json(pipeline_path)
    steps = pipeline.get("steps")
    if not isinstance(steps, list) or not steps:
        raise CaseConfigurationError("pipeline.steps must be a non-empty list")
    defaults = pipeline.get("defaults", {})
    if not isinstance(defaults, dict):
        raise CaseConfigurationError("pipeline.defaults must be an object")
    runner = ApiTestRunner(timeout)
    results: dict[str, CaseResult] = {}
    failures = 0
    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict) or not isinstance(raw_step.get("case"), str):
            raise CaseConfigurationError(f"steps[{index}] needs a case string")
        name = raw_step.get("name", f"step_{index}")
        if not isinstance(name, str) or not name:
            raise CaseConfigurationError(f"steps[{index}].name must be a non-empty string")
        if name in results:
            raise CaseConfigurationError(f"Duplicate pipeline step name: {name}")
        retry, interval = _retry_config(raw_step, defaults)
        case_path = resolve_case_path(case_root, raw_step["case"])
        logger.info("Step started: name=%s case=%s retry=%s retry_interval_seconds=%s", name, case_path, retry, interval)
        case_document = apply_input_mappings(read_json(case_path), raw_step.get("input_mappings"), results, index)
        project_settings = project_request_settings(case_document, project_root)
        result = runner.run_case(
            name, case_document, results, retry, interval,
            project_settings.base_url if project_settings else None,
            project_settings.proxy_url if project_settings else None,
            project_settings.verify_ssl if project_settings else True, file_root or case_root,
            project_settings.proxy_urls if project_settings else None,
        )
        results[name] = result
        for line in _result_lines(result):
            report(line, logging.INFO if result.status == "passed" else logging.ERROR)
        if result.status != "passed":
            failures += 1
            if raw_step.get("continue_on_failure", False) is not True:
                report("Pipeline stopped because the step did not pass.", logging.ERROR)
                break
    report(f"Pipeline result: {len(results) - failures} passed, {failures} failed/error")
    for summary_line in _tag_summary_lines(steps, results):
        report(summary_line)
    report(f"Log file: {log_path}")
    return 0 if failures == 0 and len(results) == len(steps) else 1


def run_case_files(
    case_references: list[str], case_root: Path, timeout: float, log_dir: Path = Path("logs"), project_root: Path = Path("projects"), file_root: Path | None = None,
) -> int:
    """Run independent case files directly, without requiring a pipeline JSON file."""
    logger, log_path = create_run_logger(log_dir)

    def report(message: str, level: int = logging.INFO) -> None:
        print(message)
        logger.log(level, message)

    logger.info("Direct case run started: case_count=%s case_root=%s timeout=%s", len(case_references), case_root, timeout)
    results: dict[str, CaseResult] = {}
    steps: list[dict[str, str]] = []
    for index, case_reference in enumerate(case_references, start=1):
        case_path = resolve_case_path(case_root, case_reference)
        case_id = f"case_{index}_{case_path.stem}"
        logger.info("Case started: case=%s", case_path)
        case_document = read_json(case_path)
        project_settings = project_request_settings(case_document, project_root)
        result = ApiTestRunner(timeout).run_case(
            case_id, case_document,
            base_url=project_settings.base_url if project_settings else None,
            proxy_url=project_settings.proxy_url if project_settings else None,
            verify_ssl=project_settings.verify_ssl if project_settings else True, file_root=file_root or case_root,
            proxy_urls=project_settings.proxy_urls if project_settings else None,
        )
        results[case_id] = result
        steps.append({"name": case_id, "case": case_reference})
        for line in _result_lines(result):
            report(line, logging.INFO if result.status == "passed" else logging.ERROR)
    passed = sum(result.status == "passed" for result in results.values())
    failed = len(results) - passed
    report(f"Cases result: {passed} passed, {failed} failed/error")
    for summary_line in _tag_summary_lines(steps, results):
        report(summary_line)
    report(f"Log file: {log_path}")
    return 0 if failed == 0 else 1


def run_case_file(
    case_reference: str, case_root: Path, timeout: float, log_dir: Path = Path("logs"), project_root: Path = Path("projects"),
) -> int:
    """Backward-compatible helper for programmatic single-case execution."""
    return run_case_files([case_reference], case_root, timeout, log_dir, project_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API test pipelines and direct case files.")
    parser.add_argument("pipelines", nargs="*", type=Path, help="One or more pipeline JSON files")
    parser.add_argument("--case-root", type=Path, default=Path("case"), help="Root directory containing test cases")
    parser.add_argument("--project-root", type=Path, default=Path("projects"), help="Root directory containing project Base URL JSON files")
    parser.add_argument("--file-root", type=Path, help="Root directory containing form-data attachment files; defaults to --case-root")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"), help="Directory for per-run log files")
    parser.add_argument("--case", dest="case_references", nargs="+", help="Run one or more case files relative to --case-root")
    args = parser.parse_args()
    if not args.case_references and not args.pipelines:
        args.pipelines = [path for path in sorted(Path("pipelines").rglob("*.json")) if not is_disabled_example_pipeline(path)]
        if not args.pipelines:
            parser.error("no pipeline files found under pipelines/; provide a pipeline file or --case")
        print(f"No pipeline specified. Running all {len(args.pipelines)} pipeline file(s) under pipelines/.")

    exit_code = 0
    for pipeline_path in args.pipelines:
        try:
            exit_code = max(exit_code, run_pipeline(pipeline_path, args.case_root, args.timeout, args.log_dir, args.project_root, args.file_root))
        except CaseConfigurationError as exc:
            print(f"Configuration error in {pipeline_path}: {exc}")
            exit_code = 2

    if args.case_references:
        try:
            exit_code = max(exit_code, run_case_files(args.case_references, args.case_root, args.timeout, args.log_dir, args.project_root, args.file_root))
        except CaseConfigurationError as exc:
            print(f"Configuration error in direct cases: {exc}")
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
