from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from .run_log import create_run_logger
from .runner import ApiTestRunner, CaseConfigurationError, CaseResult, read_json, resolve_case_path


def _retry_config(item: dict[str, Any], defaults: dict[str, Any]) -> tuple[int, float]:
    retry = item.get("retry", defaults.get("retry", 0))
    interval = item.get("retry_interval_seconds", defaults.get("retry_interval_seconds", 0))
    if not isinstance(retry, int) or retry < 0:
        raise CaseConfigurationError("retry must be an integer greater than or equal to 0")
    if not isinstance(interval, (int, float)) or interval < 0:
        raise CaseConfigurationError("retry_interval_seconds must be a non-negative number")
    return retry, float(interval)


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


def run_pipeline(pipeline_path: Path, case_root: Path, timeout: float, log_dir: Path = Path("logs")) -> int:
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
        result = runner.run_case(name, read_json(case_path), results, retry, interval)
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


def run_case_files(case_references: list[str], case_root: Path, timeout: float, log_dir: Path = Path("logs")) -> int:
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
        result = ApiTestRunner(timeout).run_case(case_id, read_json(case_path))
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


def run_case_file(case_reference: str, case_root: Path, timeout: float, log_dir: Path = Path("logs")) -> int:
    """Backward-compatible helper for programmatic single-case execution."""
    return run_case_files([case_reference], case_root, timeout, log_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API test pipelines and direct case files.")
    parser.add_argument("pipelines", nargs="*", type=Path, help="One or more pipeline JSON files")
    parser.add_argument("--case-root", type=Path, default=Path("case"), help="Root directory containing test cases")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"), help="Directory for per-run log files")
    parser.add_argument("--case", dest="case_references", nargs="+", help="Run one or more case files relative to --case-root")
    args = parser.parse_args()
    if not args.case_references and not args.pipelines:
        args.pipelines = sorted(Path("pipelines").rglob("*.json"))
        if not args.pipelines:
            parser.error("no pipeline files found under pipelines/; provide a pipeline file or --case")
        print(f"No pipeline specified. Running all {len(args.pipelines)} pipeline file(s) under pipelines/.")

    exit_code = 0
    for pipeline_path in args.pipelines:
        try:
            exit_code = max(exit_code, run_pipeline(pipeline_path, args.case_root, args.timeout, args.log_dir))
        except CaseConfigurationError as exc:
            print(f"Configuration error in {pipeline_path}: {exc}")
            exit_code = 2

    if args.case_references:
        try:
            exit_code = max(exit_code, run_case_files(args.case_references, args.case_root, args.timeout, args.log_dir))
        except CaseConfigurationError as exc:
            print(f"Configuration error in direct cases: {exc}")
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
