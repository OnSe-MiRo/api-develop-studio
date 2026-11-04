"""P1 comparable read baselines and same-server recovery diagnosis."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import statistics
from datetime import datetime
from api_test.load_test_monitor import stable_resource_window
import subprocess
import sys
from pathlib import Path

from api_test.load_test_harness import REPOSITORY, _host_memory_mb

SOURCE_FILES = (
    "api_test/load_test_baseline.py", "api_test/load_test_baseline_diagnostics.py", "api_test/load_test_campaigns.py",
    "api_test/load_test_monitor.py", "api_test/load_test_harness.py", "api_test/load_test_mutations.py", "api_test/load_results.py",
    "api_test/services/documents.py", "api_test/services/studio.py", "api_test/collaboration_store.py", "api_test/database.py",
    "api_test/jobs.py", "api_test/job_runner.py", "api_test/services/execution.py", "api_test/main.py", "api_test/dependencies.py",
    "api_test/cli.py", "api_test/runner.py", "api_test/reports.py", "api_test/ownership.py", "api_test/request_profiles.py", "api_test/project_variables.py",
    "load-tests/k6/mixed.js",
    "load-tests/k6/read-model.js", "load-tests/k6/mixed-model.js", "load-tests/k6/campaign-model.js", "load-tests/k6/studio-summary.js",
    "web/package.json",
)
COMPONENTS = ("lookupNs", "pathResolutionNs", "projectionReadNs", "utf8DecodeNs", "jsonParseNs", "fieldSelectionNs", "serializationNs", "otherNs")


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def environment_identity(snapshot: Path, k6_version: str) -> dict:
    if not snapshot.exists():
        raise ValueError("isolated snapshot is missing")
    version = json.loads((REPOSITORY / "web/package.json").read_text(encoding="utf-8"))["version"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    return {"appVersion": version, "commitSha": commit, "pythonVersion": platform.python_version(), "k6Version": k6_version,
            "os": platform.platform(), "machine": platform.machine(), "logicalCpuCount": os.cpu_count(),
            "memoryMb": _host_memory_mb(), "diskDevice": snapshot.stat().st_dev, "sourceSha256": source_hashes()}


def _valid_number(value, *, positive=False) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def _workers(census, pid):
    if not isinstance(census, dict) or census.get("serverPid") != pid or type(pid) is not int or pid <= 0 or not isinstance(census.get("threads"), list):
        return None
    workers = [(thread.get("name"), thread.get("nativeId")) for thread in census["threads"] if isinstance(thread, dict) and str(thread.get("name", "")).startswith("studio-run-")]
    ids = [ident for _, ident in workers]
    if sorted(name for name, _ in workers) != ["studio-run-0", "studio-run-1"] or any(type(ident) is not int or ident <= 0 for ident in ids) or len(set(ids)) != 2:
        return None
    return sorted(workers)


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _identity_complete(identity):
    if not isinstance(identity, dict) or not all(isinstance(identity.get(field), str) and identity[field] for field in ("appVersion", "commitSha", "pythonVersion", "k6Version", "os", "machine")):
        return False
    if not re.fullmatch(r"[0-9a-f]{40}", identity["commitSha"]) or type(identity.get("diskDevice")) is not int or identity["diskDevice"] < 0:
        return False
    if not _valid_number(identity.get("logicalCpuCount"), positive=True) or not _valid_number(identity.get("memoryMb"), positive=True) or not re.fullmatch(r"[0-9a-f]{64}", str(identity.get("k6BinarySha256", ""))):
        return False
    hashes = identity.get("sourceSha256")
    return isinstance(hashes, dict) and set(hashes) == set(SOURCE_FILES) and all(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values())


def _resource_covered(phase, duration):
    interval = phase.get("phase", {}).get("sampleIntervalSeconds")
    window = phase.get("resourceWindowSeconds")
    if not _valid_number(interval, positive=True) or not _valid_number(window, positive=True) or window != min(60, duration / 2):
        return False
    for records, aggregate in ((phase.get("resources"), phase.get("resourceAggregate")), (phase.get("generatorResources"), phase.get("generatorResourceAggregate"))):
        if not isinstance(records, list) or len(records) < 2 or not isinstance(aggregate, dict):
            return False
        times = [_time(record.get("timestamp")) for record in records if isinstance(record, dict)]
        if len(times) != len(records) or any(value is None for value in times) or any(current <= previous for previous, current in zip(times, times[1:])):
            return False
        if len(records) < max(2, math.floor(duration / (2 * interval))) or (times[-1] - times[0]).total_seconds() < duration - 2 * interval:
            return False
        if any((current - previous).total_seconds() > 2 * interval + 1 for previous, current in zip(times, times[1:])):
            return False
        if any(not _valid_number(record.get("memoryMb"), positive=True) for record in records) or any(not _valid_number(record.get("cpuPercent")) for record in records[1:]):
            return False
        if any(aggregate.get(field) != stable_resource_window(records, window).get(field) for field in ("cpuPercent", "memoryMb")):
            return False
        if not _valid_number(aggregate.get("cpuPercent")) or not _valid_number(aggregate.get("memoryMb"), positive=True):
            return False
    if phase.get("generatorPid") is None or type(phase["generatorPid"]) is not int or phase["generatorPid"] <= 0:
        return False
    if any(record.get("processPid") != phase["generatorPid"] or record.get("treeRole") != "load generator" for record in phase["generatorResources"]):
        return False
    if any(record.get("processPid") != phase.get("serverPid") or record.get("treeRole") != "server" for record in phase["resources"]):
        return False
    return True


def compare_three(runs: list[dict], expected_identity: dict, fixture_sha: str, duration_seconds=300) -> dict:
    reasons: list[str] = []
    if len(runs) != 3:
        return {"status": "incomparable", "reasons": ["exactly_three_runs_required"], "runLevelMedianRps": None, "runLevelMedianP95Ms": None}
    if not isinstance(fixture_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", fixture_sha):
        reasons.append("fixture_identity_missing")
    if not _identity_complete(expected_identity):
        reasons.append("source_or_environment_identity_incomplete")
    ids, values, periods = [], [], []
    worker_identity = None
    expected_pid = runs[0].get("serverPid")
    if type(expected_pid) is not int or expected_pid <= 0:
        reasons.append("server_pid_missing")
    previous_sequence = None
    for item in runs:
        phase = item.get("phase") or {}
        measured = phase.get("summary") or {}
        config = phase.get("phase") or {}
        run_id = item.get("runId")
        ids.append(run_id)
        if not isinstance(run_id, str) or not run_id or item.get("bundleRunId") != run_id or phase.get("status") != "passed" or phase.get("complete") is not True or phase.get("stopReason") is not None:
            reasons.append("run_not_complete_and_passed")
        if phase.get("postRequestCleanup", {}).get("status") != "passed" or phase.get("postRequestCleanup", {}).get("childProcesses") != 0 or phase.get("postRequestCleanup", {}).get("tempEntries") != 0:
            reasons.append("cleanup_not_verified")
        if config.get("phase") != "baseline" or config.get("durationSeconds") != duration_seconds or config.get("validationMode") != (duration_seconds != 300) or config.get("vus") != 5:
            reasons.append("duration_vus_or_mode_differs")
        if not _valid_number(phase.get("elapsedSeconds")) or phase["elapsedSeconds"] < duration_seconds:
            reasons.append("phase_elapsed_shorter_than_nominal_duration")
        started, ended = _time(item.get("runStartedAt")), _time(item.get("runEndedAt"))
        if started is None or ended is None or ended <= started or (ended - started).total_seconds() < duration_seconds:
            reasons.append("manifest_interval_incomplete")
        else:
            periods.append((started, ended))
        if measured.get("vusMax") != 5 or measured.get("thresholdsPassed") is not True or measured.get("errorRate") != 0 or not _valid_number(measured.get("requests"), positive=True):
            reasons.append("vus_checks_or_requests_invalid")
        client = phase.get("client") or {}
        if any(client.get(field) != 0 for field in ("correctnessFailures", "runExitFailures", "capacity429")) or client.get("networkOr5xxRate") != 0:
            reasons.append("client_failure_or_unknown")
        rps, p95 = measured.get("rps"), (measured.get("latencyMs") or {}).get("p95")
        if not _valid_number(rps, positive=True) or not _valid_number(p95):
            reasons.append("missing_or_invalid_run_metric")
        else:
            values.append((rps, p95))
        if item.get("identityBefore") != expected_identity or item.get("identityAfter") != expected_identity:
            reasons.append("source_or_environment_changed")
        if item.get("fixtureBefore") != fixture_sha or item.get("fixtureAfter") != fixture_sha or phase.get("integrity", {}).get("fixtureSha256") != fixture_sha:
            reasons.append("fixture_changed")
        trace = item.get("trace") or {}
        if trace.get("status") != "passed" or not _valid_number(item.get("caseListRequests"), positive=True) or trace.get("count") != item.get("caseListRequests"):
            reasons.append("case_list_trace_incomplete")
        if type(trace.get("sequenceStart")) is not int or type(trace.get("sequenceEnd")) is not int or trace.get("sequenceStart", -1) < 0 or trace.get("sequenceEnd", -1) - trace.get("sequenceStart", 0) + 1 != trace.get("count"):
            reasons.append("trace_sequence_invalid")
        elif previous_sequence is not None and trace["sequenceStart"] != previous_sequence + 1:
            reasons.append("trace_sequence_reused_or_missing")
        if type(trace.get("sequenceEnd")) is int:
            previous_sequence = trace["sequenceEnd"]
        artifacts = item.get("artifactsSha256") or {}
        if set(artifacts) != {"raw.jsonl", "bundle.json", "studio-summary.json"} or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in artifacts.values()):
            reasons.append("raw_bundle_summary_provenance_missing")
        if item.get("serverPid") != expected_pid or phase.get("serverPid") != expected_pid:
            reasons.append("server_pid_changed")
        if not _resource_covered(phase, duration_seconds):
            reasons.append("server_or_generator_resource_window_unknown")
        before, after = _workers(item.get("threadsBefore"), expected_pid), _workers(item.get("threadsAfter"), expected_pid)
        if before is None or after is None or before != after:
            reasons.append("async_worker_identity_unverified_or_changed")
        elif worker_identity is None:
            worker_identity = before
        elif before != worker_identity:
            reasons.append("async_worker_identity_changed_between_runs")
    if len(periods) == 3 and any(current[0] <= previous[1] for previous, current in zip(periods, periods[1:])):
        reasons.append("baseline_intervals_overlap_or_reorder")
    if len(set(str(item) for item in ids)) != 3:
        reasons.append("run_id_reused")
    reasons = sorted(set(reasons))
    comparable = not reasons
    return {"status": "comparable" if comparable else "incomparable", "reasons": reasons,
            "runLevelMedianRps": statistics.median(value[0] for value in values) if comparable else None,
            "runLevelMedianP95Ms": statistics.median(value[1] for value in values) if comparable else None,
            "scope": "actual_3x300" if comparable and duration_seconds == 300 else "validation_only_or_incomparable"}


def _single_baseline_reasons(entry: dict, identity: dict, fixture_sha: str, duration: int) -> list[str]:
    """Reuse the full baseline contract, ignoring only duplicate-run artifacts."""
    repeated = compare_three([entry, entry, entry], identity, fixture_sha, duration)
    duplicate_only = {"run_id_reused", "trace_sequence_reused_or_missing", "baseline_intervals_overlap_or_reorder"}
    return [reason for reason in repeated["reasons"] if reason not in duplicate_only]


def trace_summary(records: list[dict], expected_requests: int) -> dict:
    if not isinstance(expected_requests, int) or expected_requests < 1 or len(records) != expected_requests:
        return {"status": "unknown", "reason": "trace_and_client_request_counts_differ", "count": len(records)}
    sequences = [row.get("sequence") for row in records if isinstance(row, dict)]
    if len(sequences) != len(records) or any(type(value) is not int or value < 0 for value in sequences) or sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        return {"status": "unknown", "reason": "trace_sequence_invalid", "count": len(records)}
    for row in records:
        if row.get("formatVersion") != 1 or row.get("operation") != "GET /api/cases" or not _valid_number(row.get("caseCount"), positive=True):
            return {"status": "unknown", "reason": "trace_shape_invalid", "count": len(records)}
        if any(not _valid_number(row.get(field)) for field in (*COMPONENTS, "handlerNs", "projectionReadBytes", "responseBytes")):
            return {"status": "unknown", "reason": "trace_metric_invalid", "count": len(records)}
        if sum(row[field] for field in COMPONENTS) != row["handlerNs"]:
            return {"status": "unknown", "reason": "exclusive_span_accounting_differs", "count": len(records)}
    means = {field[:-2] + "Ms": sum(row[field] for row in records) / len(records) / 1_000_000 for field in (*COMPONENTS, "handlerNs")}
    return {"status": "passed", "count": len(records), "sequenceStart": sequences[0], "sequenceEnd": sequences[-1], "caseCountMin": min(row["caseCount"] for row in records),
            "caseCountMax": max(row["caseCount"] for row in records), "projectionReadBytesTotal": sum(row["projectionReadBytes"] for row in records),
            "responseBytesTotal": sum(row["responseBytes"] for row in records), "exclusiveMeanMs": means,
            "scope": "instrumented handler only; trace write, ASGI/network, client timing excluded; p95 parts must not be summed"}


def _private_json(base_url: str, path: str, body=None, method="GET", timeout=5):
    from urllib.request import Request, build_opener, ProxyHandler
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(base_url + path, data=payload, method=method, headers={"Content-Type": "application/json"} if payload else {})
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        return response.status, json.load(response)


def _census(base_url: str, pid: int):
    status, document = _private_json(base_url, "/__load_test__/thread-census")
    if status != 200 or document.get("serverPid") != pid or not isinstance(document.get("threads"), list):
        raise ValueError("private thread census is unavailable")
    return document


def _job_batch(base_url: str, count: int, sampler, pid: int) -> dict:
    from api_test.load_test_mutations import RUN_CASE
    import time
    ids = []
    for _ in range(count):
        status, submitted = _private_json(base_url, "/api/runs", {"cases": [RUN_CASE]}, "POST")
        if status != 202 or submitted.get("status") not in ("queued", "running") or not isinstance(submitted.get("runId"), str) or not submitted["runId"]:
            raise ValueError("prewarm/diagnostic async job was not accepted")
        ids.append(submitted["runId"])
    if len(set(ids)) != count:
        raise ValueError("prewarm/diagnostic async job ID was reused")
    deadline = time.monotonic() + 20
    terminal = {}
    while len(terminal) < count and time.monotonic() < deadline:
        for run_id in ids:
            if run_id in terminal:
                continue
            status, result = _private_json(base_url, "/api/runs/" + run_id)
            if status != 200 or result.get("runId") != run_id:
                raise ValueError("async job ownership/readback differs")
            if result.get("status") in {"passed", "failed", "error", "timeout", "cancelled"}:
                terminal[run_id] = result
        if len(terminal) < count:
            time.sleep(.05)
    if len(terminal) != count:
        raise ValueError("prewarm/diagnostic async jobs did not reach terminal state")
    for run_id in ids:
        value = terminal[run_id]
        targets = (value.get("result") or {}).get("targets") or []
        if value["status"] != "passed" or value.get("exitCode") != 0 or len(targets) != 1 or targets[0].get("caseReference") != RUN_CASE or targets[0].get("status") != "passed" or targets[0].get("httpStatus") != 200:
            raise ValueError("prewarm/diagnostic saved health case failed")
    end = time.monotonic() + 5
    sample = sampler.sample()
    while (sample.get("childProcesses") or sample.get("tempEntries")) and time.monotonic() < end:
        time.sleep(.1)
        sample = sampler.sample()
    if sample.get("childProcesses") != 0 or sample.get("tempEntries") != 0:
        raise ValueError("async batch descendants/temp cleanup is unverified")
    return {"accepted": count, "terminalPassed": count, "runIds": ids, "childProcesses": 0, "tempEntries": 0, "census": _census(base_url, pid), "serverResource": sample}


def _json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _trace_rows(path: Path, offset: int) -> tuple[list[dict], int]:
    if not path.exists():
        return [], offset
    with path.open("rb") as handle:
        handle.seek(offset)
        raw = handle.read()
        ending = handle.tell()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("case-list trace has an incomplete final row")
    return [json.loads(line) for line in raw.splitlines() if line], ending


def _phase_trace(directory: Path, records: list[dict]) -> tuple[dict, int, str, str, str]:
    bundle = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "studio-summary.json").read_text(encoding="utf-8"))["run"]
    endpoints = [item for item in bundle["endpointMetrics"] if item["method"] == "GET" and item["endpoint"] == "/api/cases"]
    if len(endpoints) != 1:
        return {"status": "unknown", "reason": "case_list_endpoint_metric_missing", "count": len(records)}, 0, manifest["id"], bundle["run"]["id"], manifest["startedAt"], manifest["endedAt"]
    result = trace_summary(records, endpoints[0]["requestCount"])
    started, ended = _time(manifest["startedAt"]), _time(manifest["endedAt"])
    def milliseconds(value):
        return value.replace(microsecond=(value.microsecond // 1000) * 1000) if value is not None else None

    if manifest["id"] != bundle["run"]["id"] or milliseconds(started) != _time(bundle["run"].get("startedAt")) or milliseconds(ended) != _time(bundle["run"].get("endedAt")):
        result = {"status": "unknown", "reason": "manifest_bundle_identity_differs", "count": len(records)}
    if started is None or ended is None or any(_time(row.get("timestamp")) is None or not started <= _time(row["timestamp"]) <= ended for row in records):
        result = {"status": "unknown", "reason": "trace_timestamp_outside_run", "count": len(records)}
    return result, endpoints[0]["requestCount"], manifest["id"], bundle["run"]["id"], manifest["startedAt"], manifest["endedAt"]


def _source_hashes_with_k6(executable: str) -> str:
    with Path(executable).open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256")
    return digest.hexdigest()


def run_p1(fixture: Path, output: Path, k6="k6", *, mode="repeat-baseline", validation_seconds=None) -> dict:
    import shutil
    import signal
    import time
    from api_test.load_test_campaigns import _control, _phase
    from api_test.load_test_harness import _new_root, _stop, isolated_environment, verify_fixture
    from api_test.load_test_monitor import ResourceSampler, recovery_report
    from api_test.load_test_mutations import expected_mutations

    if mode not in ("repeat-baseline", "recovery-diagnose") or validation_seconds is not None and (type(validation_seconds) is not int or not 25 <= validation_seconds <= 120):
        raise ValueError("P1 mode/duration is unsupported")
    fixture = fixture.resolve()
    if output.resolve().is_relative_to(fixture):
        raise ValueError("P1 output must be outside the fixture")
    original = verify_fixture(fixture)
    executable = shutil.which(k6)
    if not executable:
        raise ValueError("k6 binary is required")
    output = _new_root(output)
    snapshot = output / "fixture"
    shutil.copytree(fixture, snapshot)
    (snapshot / "tmp").mkdir()
    trace_path = output / "case-list-spans.jsonl"
    environment = {**isolated_environment(), "STUDIO_DB_PATH": str(snapshot / "data/studio.db"), "STUDIO_MUTATION_MODE": "target",
                   "STUDIO_LT4_STUB": "true", "STUDIO_P1_CASE_TRACE": str(trace_path), "XDG_CONFIG_HOME": str(output / "config")}
    for name in ("TEMP", "TMP", "TMPDIR"):
        environment[name] = str(snapshot / "tmp")
    version = subprocess.run([executable, "version"], capture_output=True, text=True, timeout=10, check=True, env=environment).stdout.strip()
    k6_sha = _source_hashes_with_k6(executable)
    identity_before_server = environment_identity(snapshot, version)
    identity_before_server["k6BinarySha256"] = k6_sha
    result = {"formatVersion": 1, "mode": mode, "status": "error", "fixture": original, "k6Version": version, "k6BinarySha256": k6_sha,
              "serverStopped": False, "prewarm": None, "warmup": None, "runs": [], "comparison": None, "maximumStableRps": None,
              "sustainedRunCapacity": None, "diagnosis": None, "validationMode": validation_seconds is not None}
    server = None
    try:
        with (output / "server.log").open("w") as log:
            ready = output / "server-ready.json"
            server = subprocess.Popen([sys.executable, "-m", "api_test.load_test_harness", "_serve", "--root", str(snapshot), "--ready", str(ready)],
                                      cwd=REPOSITORY, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
            server._isolated_group = os.name == "posix"
            deadline = time.monotonic() + 30
            while not ready.exists():
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError("isolated P1 server did not start")
                time.sleep(.05)
            base_url = json.loads(ready.read_text(encoding="utf-8"))["baseUrl"]
            while True:
                try:
                    _control(base_url)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ValueError("isolated P1 control did not become ready")
                    time.sleep(.05)
            duration = validation_seconds or 300
            memory_mb = _host_memory_mb()
            environment.update(STUDIO_BASE_URL=base_url, STUDIO_FIXTURE_PATH=str(snapshot / "fixture.json"), STUDIO_RUNTIME_PATH=str(snapshot / "runtime.json"),
                               STUDIO_PROJECT=f"load-test/{original['dataset']}.json", STUDIO_EXECUTION_MODE="isolated-local-same-server-p1",
                               STUDIO_OS=platform.platform(), STUDIO_CPU=f"{os.cpu_count()} logical CPUs", STUDIO_K6_VERSION=version,
                               STUDIO_APP_VERSION=json.loads((REPOSITORY / "web/package.json").read_text(encoding="utf-8"))["version"],
                               STUDIO_CONFIGURED_VUS="5", STUDIO_CONTENTION_REQUESTS="5", STUDIO_SELECTION_STRIDE="5")
            environment["STUDIO_COMMIT_SHA"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            if memory_mb is not None:
                environment["STUDIO_MEMORY_MB"] = str(memory_mb)
            sampler = ResourceSampler(server.pid, snapshot, memory_mb)
            config = {"mode": mode, "phase": "baseline", "durationSeconds": duration, "baselineSeconds": duration, "configuredVus": 5, "vus": 5,
                      "selectionStride": 5, "contentionRequests": 5, "validationMode": validation_seconds is not None,
                      "sampleIntervalSeconds": 1 if validation_seconds is not None else 5,
                      "windowSeconds": 60, "resourceSustainSeconds": 120, "captureGenerator": True, "resetCpuAtPhaseStart": True}
            identity = environment_identity(snapshot, version)
            identity["k6BinarySha256"] = _source_hashes_with_k6(executable)
            if identity != identity_before_server:
                raise ValueError("P1 environment/source changed during server startup")
            result.update(serverPid=server.pid, baseUrl=base_url, environmentIdentity=identity, fixtureSha256=original["fixtureSha256"])
            result["initialCensus"] = _census(base_url, server.pid)
            result["prewarm"] = _job_batch(base_url, 1, sampler, server.pid)
            if environment_identity(snapshot, version)["sourceSha256"] != identity["sourceSha256"] or _source_hashes_with_k6(executable) != k6_sha:
                raise ValueError("P1 source changed during async worker prewarm")
            if _workers(result["prewarm"]["census"], server.pid) is None:
                raise ValueError("both async workers did not initialize during explicit prewarm")
            warm_config = {**config, "durationSeconds": 25, "validationMode": True}
            warm = _phase(warm_config, output / "warmup", snapshot, environment, executable, server, sampler, config)
            result["warmup"] = {"status": warm["status"], "complete": warm["complete"], "summary": warm.get("summary"), "cleanup": warm["postRequestCleanup"],
                                "serverPid": warm["serverPid"], "generatorResourceAggregate": warm.get("generatorResourceAggregate")}
            if warm["status"] != "passed" or not warm["complete"] or warm["postRequestCleanup"]["status"] != "passed":
                raise ValueError("read cache warmup did not pass")
            result["censusAfterWarmup"] = _census(base_url, server.pid)
            cursor = trace_path.stat().st_size if trace_path.exists() else 0
            rounds = 3 if mode == "repeat-baseline" else 1
            for number in range(1, rounds + 1):
                before = environment_identity(snapshot, version)
                before["k6BinarySha256"] = _source_hashes_with_k6(executable)
                fixture_before = verify_fixture(snapshot, expected_mutations(snapshot, config))["fixtureSha256"]
                thread_before = _census(base_url, server.pid)
                if before != identity or fixture_before != original["fixtureSha256"] or _workers(thread_before, server.pid) is None:
                    raise ValueError("P1 conditions changed before the next baseline")
                directory = output / f"baseline-{number}"
                phase = _phase(config, directory, snapshot, environment, executable, server, sampler, config)
                records, cursor = _trace_rows(trace_path, cursor)
                trace, count, run_id, bundle_id, started_at, ended_at = _phase_trace(directory, records) if (directory / "bundle.json").exists() else ({"status": "unknown", "reason": "bundle_missing", "count": len(records)}, 0, None, None, None, None)
                after = environment_identity(snapshot, version)
                after["k6BinarySha256"] = _source_hashes_with_k6(executable)
                fixture_after = verify_fixture(snapshot, expected_mutations(snapshot, config))["fixtureSha256"]
                entry = {"phase": phase, "runId": run_id, "bundleRunId": bundle_id, "runStartedAt": started_at, "runEndedAt": ended_at,
                         "identityBefore": before, "identityAfter": after, "fixtureBefore": fixture_before, "fixtureAfter": fixture_after,
                         "trace": trace, "caseListRequests": count, "artifactsSha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ("raw.jsonl", "bundle.json", "studio-summary.json") if (directory / name).exists()}, "threadsBefore": thread_before, "threadsAfter": _census(base_url, server.pid),
                         "serverPid": server.pid}
                result["runs"].append(entry)
                _json(output / f"baseline-{number}-context.json", {key: value for key, value in entry.items() if key != "phase"})
                if phase["status"] != "passed" or not phase["complete"] or phase["postRequestCleanup"]["status"] != "passed" or trace["status"] != "passed" or after != identity or fixture_after != original["fixtureSha256"]:
                    result["profileBlockedReason"] = "baseline failed, changed conditions or trace coverage"
                    break
            if mode == "repeat-baseline":
                result["comparison"] = compare_three(result["runs"], identity, original["fixtureSha256"], duration)
                if result["comparison"]["status"] == "comparable":
                    result["status"] = "passed"
                elif any(item["phase"]["status"] in ("failed", "aborted", "error") or item["phase"]["postRequestCleanup"]["status"] == "failed" for item in result["runs"]):
                    result["status"] = "failed"
                else:
                    result["status"] = "unknown"
            else:
                before = result["runs"][0] if result["runs"] else None
                initial_reasons = _single_baseline_reasons(before, identity, original["fixtureSha256"], duration) if before else ["no_before_baseline"]
                if initial_reasons:
                    result["status"] = "failed" if before and before["phase"]["status"] in ("failed", "aborted", "error") else "unknown"
                    result["diagnosis"] = {"status": "not_run", "reason": "before baseline did not pass eligibility", "eligibilityReasons": initial_reasons}
                else:
                    evidence = {"status": "error", "batches": [], "fixtureSha256": original["fixtureSha256"]}
                    result["diagnosis"] = evidence
                    _recovery_diagnosis(output, base_url, server, sampler, snapshot, environment, executable, config, identity, before, cursor, evidence)
                    result["status"] = evidence["status"]
    except BaseException as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        if server is not None:
            from api_test.load_test_harness import _stop
            try:
                _stop(server)
                result["serverStopped"] = server.poll() is not None
            except (OSError, subprocess.SubprocessError) as exc:
                result["status"] = "error"
                result["cleanupError"] = str(exc)
        _json(output / "p1-result.json", result)
    return result


def _recovery_diagnosis(output, base_url, server, sampler, snapshot, environment, executable, config, identity, before, cursor, evidence):
    from api_test.load_test_campaigns import _phase
    from api_test.load_test_harness import verify_fixture
    from api_test.load_test_monitor import recovery_report
    from api_test.load_test_mutations import expected_mutations

    def unchanged():
        current = environment_identity(snapshot, environment["STUDIO_K6_VERSION"])
        current["k6BinarySha256"] = _source_hashes_with_k6(executable)
        return current == identity and verify_fixture(snapshot, expected_mutations(snapshot, config))["fixtureSha256"] == evidence["fixtureSha256"]

    if not unchanged():
        raise ValueError("P1 source, hardware or original fixture changed before diagnostic batch")
    for number in (1, 2):
        batch = _job_batch(base_url, 5, sampler, server.pid)
        evidence["batches"].append(batch)
        _json(output / f"async-batch-{number}.json", batch)
        if not unchanged():
            raise ValueError("P1 source, hardware or original fixture changed after diagnostic batch")
    thread_before = _census(base_url, server.pid)
    identity_before = environment_identity(snapshot, environment["STUDIO_K6_VERSION"])
    identity_before["k6BinarySha256"] = _source_hashes_with_k6(executable)
    fixture_before = verify_fixture(snapshot, expected_mutations(snapshot, config))["fixtureSha256"]
    directory = output / "recovery-baseline"
    phase = _phase(config, directory, snapshot, environment, executable, server, sampler, config)
    records, _ = _trace_rows(output / "case-list-spans.jsonl", cursor)
    trace, count, run_id, bundle_id, started, ended = _phase_trace(directory, records) if (directory / "bundle.json").exists() else ({"status": "unknown", "reason": "bundle_missing", "count": len(records)}, 0, None, None, None, None)
    after = {"phase": phase, "runId": run_id, "bundleRunId": bundle_id, "runStartedAt": started, "runEndedAt": ended,
             "identityBefore": identity_before, "identityAfter": environment_identity(snapshot, environment["STUDIO_K6_VERSION"]),
             "trace": trace, "caseListRequests": count, "threadsBefore": thread_before, "threadsAfter": _census(base_url, server.pid),
             "serverPid": server.pid, "fixtureBefore": fixture_before,
             "fixtureAfter": verify_fixture(snapshot, expected_mutations(snapshot, config))["fixtureSha256"],
             "artifactsSha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ("raw.jsonl", "bundle.json", "studio-summary.json") if (directory / name).exists()}}
    after["identityAfter"]["k6BinarySha256"] = _source_hashes_with_k6(executable)
    evidence["afterBaseline"] = after
    if phase["status"] != "passed" or not phase["complete"] or phase["postRequestCleanup"]["status"] != "passed":
        evidence["status"] = "failed"
        evidence["reason"] = "recovery baseline execution or cleanup failed"
        return evidence
    eligibility_reasons = _single_baseline_reasons(after, identity, evidence["fixtureSha256"], config["durationSeconds"])
    if eligibility_reasons:
        evidence["status"] = "unknown"
        evidence["reason"] = "recovery baseline did not pass eligibility"
        evidence["eligibilityReasons"] = eligibility_reasons
        return evidence
    first = before["phase"]
    evidence["recovery"] = recovery_report(first, phase, {**first["resourceAggregate"], "childProcesses": first["postResource"]["childProcesses"]},
                                            {**phase["resourceAggregate"], "childProcesses": phase["postResource"]["childProcesses"]})
    census = [before["threadsAfter"], *(batch["census"] for batch in evidence["batches"]), after["threadsAfter"]]
    worker_ids = [_workers(item, server.pid) for item in census]
    evidence["threads"] = {"censuses": census, "studioWorkerNativeIdsStable": all(item == worker_ids[0] and item is not None for item in worker_ids),
                           "anyioWorkerCounts": [sum(thread["name"].startswith("AnyIO") for thread in item["threads"]) for item in census],
                           "anyioNativeIds": [[thread["nativeId"] for thread in item["threads"] if thread["name"].startswith("AnyIO")] for item in census],
                           "psThreadCounts": {"before": first["postResource"]["threads"], "after": phase["postResource"]["threads"]},
                           "interpretation": "named Python threads and native ps counts are separate measures; stable worker names do not prove the sole recovery cause"}
    evidence["status"] = "failed" if evidence["recovery"]["status"] == "failed" else evidence["recovery"]["status"] if evidence["threads"]["studioWorkerNativeIdsStable"] else "unknown"
    evidence["attribution"] = "unproven; cache, request scheduling, projection I/O and generator competition require independent traces"
    return evidence


def render_report(result: dict) -> str:
    lines = ["# P1 동일 조건 기준선·회복 진단", "", "이 보고서는 격리된 같은 서버에서 수집한 P1 결과다. 과거 LT-2의 fresh-server 단일 Baseline과 합쳐 중앙값을 계산하지 않는다.", "",
             f"- 상태: {result['status']}; mode={result['mode']}; validation={result['validationMode']}",
             f"- 동일 서버 PID: {result.get('serverPid')}; 원본 fixture SHA256: {result.get('fixtureSha256')}", ""]
    if result["mode"] == "repeat-baseline":
        comparison = result.get("comparison") or {}
        for index, item in enumerate(result["runs"], 1):
            value = item["phase"].get("summary") or {}
            lines.append(f"- 실행 {index}: {item['phase']['status']}, {value.get('requests', '미수집')}요청, {value.get('rps', '미수집')} RPS, p95 {(value.get('latencyMs') or {}).get('p95', '미수집')} ms, case-list trace {item['trace']['status']} ({item['trace'].get('count', 0)}건)")
        if comparison.get("status") == "comparable":
            label = "실제 3×300초" if comparison["scope"] == "actual_3x300" else "축소 검증 전용"
            lines.extend(["", f"**{label} 실행별 중앙값:** RPS {comparison['runLevelMedianRps']}, p95 {comparison['runLevelMedianP95Ms']} ms. Percentile의 원본 표본을 합산하거나 평균하지 않았다."])
        else:
            lines.extend(["", f"**중앙값 미확정:** 비교 불가 사유 {', '.join(comparison.get('reasons', [])) or '측정 미완료'}."])
    else:
        value = result.get("diagnosis") or {}
        recovery = value.get("recovery") or {}
        p95 = (recovery.get("comparison") or {}).get("p95Ms") or {}
        batch_count = len(value.get("batches") or [])
        lines += ["", f"- 회복 진단: {value.get('status', '미실행')}; p95 {p95.get('before', '미수집')} → {p95.get('after', '미수집')} ms, 120% 판정 {p95.get('verdict', '미확정')}.",
                  f"- terminal 완료한 async 5개 batch: {batch_count}회. 이름/native ID, AnyIO 이름·native ID와 ps thread 수는 수집된 범위에서 별도로 기록했다. 이는 초기 thread 증가와 지속 증가를 구분할 자료이며 과거 회복 실패의 단독 원인을 증명하지 않는다."]
    lines += ["", "`/api/cases`의 추적 값은 list_references(connect·query·rows), 경로 확인, 파일 읽기, UTF-8 해독, JSON 파싱, 필드 선택, json_response 직렬화의 handler 내부 exclusive 구간이다. trace 기록·ASGI 전송·네트워크·클라이언트 시간은 제외한다. 서로 다른 구간의 p95를 더하지 않는다.",
              "서버 CPU와 k6 발생기 CPU/RSS는 각각의 현재 관측 가능한 process tree를 논리 CPU 수로 나눈 sample이다. 종료 사이 자식의 CPU, 장치 IOPS/latency와 host 전체 CPU는 미수집이다.",
              "최대 안정 RPS와 지속 안정 run 동시성은 이 P1 기준선 또는 짧은 진단에서 판정하지 않는다. 과거 Target 429·Spike/Stress 회복 실패·Soak unknown을 덮어쓰지 않는다.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for name in ("repeat-baseline", "recovery-diagnose"):
        command = commands.add_parser(name)
        command.add_argument("--fixture", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--k6", default="k6")
        command.add_argument("--validation-seconds", type=int, help="25..120 seconds; distinctly labelled, never a 300-second baseline")
    rendered = commands.add_parser("render")
    rendered.add_argument("--result", type=Path, required=True, help="saved p1-result.json")
    rendered.add_argument("--output", type=Path, required=True, help="Korean Markdown report")
    rendered.add_argument("--check", action="store_true", help="compare without changing the report")
    args = parser.parse_args(argv)
    try:
        if args.mode == "render":
            result = json.loads(args.result.read_text(encoding="utf-8"))
            if result.get("mode") == "repeat-baseline" and result.get("comparison") is not None:
                duration = result["runs"][0]["phase"]["phase"]["durationSeconds"] if result.get("runs") else 300
                if compare_three(result["runs"], result["environmentIdentity"], result["fixtureSha256"], duration) != result["comparison"]:
                    raise ValueError("saved P1 comparison differs from run evidence")
            content = render_report(result)
            if args.check:
                if not args.output.is_file() or args.output.read_text(encoding="utf-8") != content:
                    print("P1 report is stale or missing", file=sys.stderr)
                    return 1
                print("P1 report is reproducible and up to date")
                return 0
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Wrote P1 Korean report: {args.output}")
            return 0
        result = run_p1(args.fixture, args.output, args.k6, mode=args.mode, validation_seconds=args.validation_seconds)
        (args.output / "p1-report.md").write_text(render_report(result), encoding="utf-8")
        print(f"P1 {args.mode}: {result['status']}; evidence: {args.output / 'p1-result.json'}")
        return 0 if result["status"] == "passed" else 1
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"P1 baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
