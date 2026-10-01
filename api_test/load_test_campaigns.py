"""LT-4 bounded campaigns, one-server recovery and controlled local faults."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request as UrlRequest, build_opener, ProxyHandler

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from api_test.load_results import import_k6_result
from api_test.load_test_monitor import RawTail, ResourceSampler, StopPolicy, recovery_report, aggregate_resources, growth_report, stable_resource_window
from api_test.load_test_mutations import expected_mutations, traffic_report

MODES = ("stress", "spike", "soak", "run-capacity", "run-sustained", "fault")


def configuration(mode, validation_seconds=None, validation_vus=None, validation_stop_seconds=None):
    if mode not in MODES:
        raise ValueError("unsupported LT-4 campaign")
    if validation_seconds is not None and (isinstance(validation_seconds, bool) or not isinstance(validation_seconds, int) or not 10 <= validation_seconds <= 120):
        raise ValueError("validation duration must be10..120seconds")
    if validation_vus is not None and (mode not in ("stress", "spike", "soak") or validation_seconds is None or validation_vus not in (1, 2) or isinstance(validation_vus, bool)):
        raise ValueError("reduced VUs require explicit validation and may be1or2")
    if validation_stop_seconds is not None and (validation_seconds is None or isinstance(validation_stop_seconds, bool) or not isinstance(validation_stop_seconds, int) or not 2 <= validation_stop_seconds <= 30):
        raise ValueError("scaled stop timers require validation and2..30seconds")
    validation = validation_seconds is not None
    config = {"mode": mode, "validationMode": validation, "baselineSeconds": 25 if validation else 300,
              "sampleIntervalSeconds": 1 if validation or mode in ("run-capacity", "run-sustained", "fault") else 5,
              "windowSeconds": validation_stop_seconds or 60, "resourceSustainSeconds": validation_stop_seconds or 120,
              "scaledStopTimers": validation_stop_seconds is not None, "configuredVus": validation_vus or {"stress": 200, "spike": 100, "soak": 35, "run-capacity": 10, "run-sustained": 2, "fault": 1}[mode],
              "selectionStride": validation_vus or {"stress": 200, "spike": 100, "soak": 35, "run-capacity": 10, "run-sustained": 2, "fault": 1}[mode], "contentionRequests": 5}
    reduced = validation_vus or config["configuredVus"]
    if mode == "stress":
        levels = [50, 75, 100, 125, 150, 175, 200] if not validation_vus else [1, reduced]
        hold = max(1, validation_seconds // len(levels)) if validation else 300
        stages = []
        for index, level in enumerate(levels):
            if index:
                stages.append({"duration": "0s", "target": level})
            stages.append({"duration": f"{hold}s", "target": level})
        config.update(phase="profile", startVus=levels[0], stages=stages, durationSeconds=hold * len(levels), stressMaximumVus=200)
    elif mode == "spike":
        ramp, hold, down = (max(1, validation_seconds // 4), max(1, validation_seconds // 2), max(1, validation_seconds // 4)) if validation else (30, 120, 1)
        base = 1 if validation_vus else 5
        config.update(phase="profile", startVus=base, stages=[{"duration": f"{ramp}s", "target": reduced}, {"duration": f"{hold}s", "target": reduced}, {"duration": f"{down}s", "target": base}], durationSeconds=ramp + hold + down)
    elif mode == "soak":
        config.update(phase="profile", vus=reduced, durationSeconds=validation_seconds or 7200, soakTargetBasis="70% of planned Target50VU; proven stable capacity is not established")
    elif mode == "run-sustained":
        config.update(durationSeconds=validation_seconds or 60, queueBatchSize=5, queueStubDelayMs=500)
    else:
        config.update(durationSeconds=validation_seconds or 90)
    return config


def install_stub(application):
    state = {"delayMs": 0, "status": 200}
    async def health():
        await asyncio.sleep(state["delayMs"] / 1000)
        return JSONResponse({"status": "ok", "service": "example-api"} if state["status"] == 200 else {"error": "controlled local failure"}, status_code=state["status"])
    async def control(request: Request):
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(400, "unsupported controlled stub configuration") from exc
        if not isinstance(body, dict) or set(body) != {"delayMs", "status"} or isinstance(body["delayMs"], bool) or not isinstance(body["delayMs"], int) or not 0 <= body["delayMs"] <= 5000 or isinstance(body["status"], bool) or not isinstance(body["status"], int) or body["status"] not in (200, 500):
            raise HTTPException(400, "unsupported controlled stub configuration")
        state.update(body)
        return dict(state)
    count = len(application.router.routes)
    application.add_api_route("/__load_test__/health", health, methods=["GET"], include_in_schema=False)
    application.add_api_route("/__load_test__/control", control, methods=["PUT"], include_in_schema=False)
    application.router.routes[:] = application.router.routes[count:] + application.router.routes[:count]


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _control(base_url, delay=0, status=200):
    request = UrlRequest(base_url + "/__load_test__/control", data=json.dumps({"delayMs": delay, "status": status}).encode(), method="PUT", headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
        return json.load(response)


def enriched_raw(raw, manifest, resources, output):
    start = datetime.fromisoformat(manifest["run"]["startedAt"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(manifest["run"]["endedAt"].replace("Z", "+00:00"))
    metrics = {"cpuPercent": "studio_cpu_percent", "memoryMb": "studio_memory_mb", "childProcesses": "studio_child_processes"}
    with output.open("w") as target:
        with raw.open() as source:
            shutil.copyfileobj(source, target)
        for metric in metrics.values():
            target.write(json.dumps({"type": "Metric", "metric": metric, "data": {"type": "gauge", "thresholds": []}}) + "\n")
        for resource in resources:
            timestamp = datetime.fromisoformat(resource["timestamp"])
            if start <= timestamp <= end:
                for field, metric in metrics.items():
                    if resource[field] is not None:
                        target.write(json.dumps({"type": "Point", "metric": metric, "data": {"time": resource["timestamp"], "value": resource[field], "tags": None}}) + "\n")


def _phase(config, directory, snapshot, environment, executable, server, sampler, audit_config, *, allow_incomplete=False):
    directory.mkdir()
    started = time.monotonic()
    raw = directory / "raw.jsonl"
    env = {**environment, "STUDIO_CAMPAIGN_CONFIG": json.dumps(config), "STUDIO_SUMMARY_PATH": str(directory / "studio-summary.json"),
           "STUDIO_STARTED_AT": datetime.now(timezone.utc).isoformat(), "STUDIO_RUN_ID": "run_lt4_" + uuid.uuid4().hex,
           "STUDIO_SCENARIO": f"lt4-{config['mode']}-{config['phase']}" + ("-validation" if config["validationMode"] else "")}
    from api_test.load_test_harness import REPOSITORY, _stop, verify_fixture
    script = "run-admission.js" if config["mode"] == "run-sustained" and config["phase"] != "baseline" else "mixed.js"
    command = [executable, "run", "--out", f"json={raw}", str(REPOSITORY / "load-tests/k6" / script)]
    result = {"phase": config, "serverPid": server.pid, "command": command, "status": "error", "complete": False, "stopReason": None, "resources": []}
    client = RawTail(raw, config["windowSeconds"])
    policy = StopPolicy(started, config["windowSeconds"], config["resourceSustainSeconds"])
    process = None
    try:
        with (directory / "k6.log").open("w") as log, (directory / "server-metrics.jsonl").open("w") as resource_log:
            process = subprocess.Popen(command, cwd=REPOSITORY, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
            process._isolated_group = os.name == "posix"
            deadline = started + config["durationSeconds"] + 25
            next_sample, stopped_at = 0, None
            while process.poll() is None:
                now = time.monotonic()
                observed = client.poll(time.time())
                if now >= next_sample:
                    resource = sampler.sample()
                    result["resources"].append(resource)
                    resource_log.write(json.dumps(resource) + "\n")
                    resource_log.flush()
                    next_sample = now + config["sampleIntervalSeconds"]
                    reason = policy.evaluate(now, observed, resource) if config["phase"] != "run" else None
                    if server.poll() is not None:
                        reason = "server_process_exited"
                    if now >= deadline:
                        reason = "hard_execution_deadline"
                    if reason and stopped_at is None:
                        result["stopReason"], stopped_at = reason, now
                        process.send_signal(signal.SIGINT)
                if now >= deadline and stopped_at is None:
                    result["stopReason"], stopped_at = "hard_execution_deadline", now
                    process.send_signal(signal.SIGINT)
                if stopped_at is not None and now - stopped_at > 10:
                    _stop(process)
                    break
                time.sleep(.1)
            result["k6ExitCode"] = process.returncode
            result["client"] = client.poll(time.time())
        settle_until = time.monotonic() + 5
        result["postResource"] = sampler.sample()
        while (result["postResource"].get("childProcesses") or result["postResource"].get("tempEntries")) and time.monotonic() < settle_until:
            time.sleep(.1)
            result["postResource"] = sampler.sample()
        summary = directory / "studio-summary.json"
        if summary.exists() and result["stopReason"] is None:
            manifest = json.loads(summary.read_text())
            enriched_raw(raw, manifest, result["resources"], directory / "enriched-raw.jsonl")
            bundle = import_k6_result(summary, directory / "enriched-raw.jsonl")
            result.update(summary=bundle["summary"], traffic=traffic_report(raw), status=bundle["run"]["status"])
            extras = expected_mutations(snapshot, {**audit_config, "mode": "target"}, allow_incomplete=allow_incomplete)
            integrity = verify_fixture(snapshot, extras)
            result.update(integrity=integrity, complete=process.returncode in (0, 99))
            if result["complete"]:
                _json(directory / "bundle.json", bundle)
        elif result["stopReason"]:
            result["status"] = "aborted"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        result["elapsedSeconds"] = time.monotonic() - started
        result["resourceWindowSeconds"] = min(60, config["durationSeconds"] / 2) if config["phase"] == "baseline" else config["durationSeconds"]
        result["resourceAggregate"] = stable_resource_window(result["resources"], result["resourceWindowSeconds"])
        result["growth"] = growth_report(result["resources"])
        result["postRequestCleanup"] = {"childProcesses": result.get("postResource", {}).get("childProcesses"), "tempEntries": result.get("postResource", {}).get("tempEntries"),
            "status": "unknown" if any(result.get("postResource", {}).get(field) is None for field in ("childProcesses", "tempEntries")) else "passed" if result["postResource"]["childProcesses"] == 0 and result["postResource"]["tempEntries"] == 0 else "failed"}
        if process is not None:
            try:
                _stop(process)
            except (OSError, subprocess.SubprocessError) as exc:
                result["status"] = "error"
                result["cleanupError"] = str(exc)
        _json(directory / "phase.json", result)
    return result


def capacity_stop_reason(phase):
    if phase["status"] == "error" or phase.get("stopReason"):
        return "capacity_phase_execution_error"
    if phase.get("postRequestCleanup", {}).get("status") != "passed":
        return "capacity_phase_cleanup_not_verified"
    if phase.get("client", {}).get("correctnessFailures", 0):
        return "capacity_phase_semantic_failure"
    rate = phase.get("client", {}).get("networkOr5xxRate")
    if rate is not None and rate > 0:
        return "capacity_phase_network_or_server_failure"
    return None


def sustained_verdict(phase):
    """Require repeated logical successes per VU and verified cleanup, never infer capacity."""
    if phase.get("status") != "passed" or phase.get("complete") is not True or phase.get("stopReason"):
        return {"status": "failed", "reason": "execution_or_threshold_failure"}
    if phase.get("postRequestCleanup", {}).get("status") != "passed":
        return {"status": "failed" if phase.get("postRequestCleanup", {}).get("status") == "failed" else "unknown", "reason": "cleanup_not_verified"}
    client = phase.get("client", {})
    if any(client.get(field) != 0 for field in ("correctnessFailures", "runExitFailures", "capacity429")) or client.get("networkOr5xxRate") != 0:
        return {"status": "failed", "reason": "logical_or_http_failure"}
    config = phase["phase"]
    if config["phase"] == "sustained":
        counts = client.get("sustainedRunsByVu", {})
        windows = client.get("sustainedSuccessWindowsByVu", {})
        if any(counts.get(str(vu), 0) < 2 or windows.get(str(vu), {}).get("observedSpanSeconds", 0) < config["durationSeconds"] / 2 for vu in range(1, config["vus"] + 1)) or phase.get("elapsedSeconds", 0) < config["durationSeconds"]:
            return {"status": "failed", "reason": "repeated_duration_or_per_vu_success_missing"}
    else:
        counts = client.get("asyncJobs", {})
        if counts.get("accepted") != 5 or counts.get("passed") != 5 or counts.get("queued", 0) < 1 or counts.get("running", 0) < 1:
            return {"status": "failed", "reason": "queue_admission_or_terminal_success_missing"}
    return {"status": "passed", "reason": None}


def run_campaign(fixture, output, k6="k6", mode="stress", validation_seconds=None, validation_vus=None, validation_stop_seconds=None):
    config = configuration(mode, validation_seconds, validation_vus, validation_stop_seconds)
    from api_test.load_test_harness import REPOSITORY, HarnessError, _new_root, _stop, _host_memory_mb, isolated_environment, verify_fixture
    fixture = fixture.resolve()
    if output.resolve().is_relative_to(fixture):
        raise HarnessError("campaign output must be outside fixture")
    original = verify_fixture(fixture)
    executable = shutil.which(k6)
    if executable is None:
        raise HarnessError("k6 binary is required")
    output = _new_root(output)
    snapshot = output / "fixture"
    shutil.copytree(fixture, snapshot)
    (snapshot / "tmp").mkdir()
    environment = {**isolated_environment(), "STUDIO_DB_PATH": str(snapshot / "data/studio.db"), "STUDIO_MUTATION_MODE": "target", "STUDIO_LT4_STUB": "true", "XDG_CONFIG_HOME": str(output / "config")}
    for temporary_variable in ("TMPDIR", "TEMP", "TMP"):
        environment[temporary_variable] = str(snapshot / "tmp")
    server = None
    result = {"configuration": config, "originalFixture": original, "status": "error", "phases": [], "fullDurationConfigured": not config["validationMode"], "fullDurationCompleted": False}
    files = ("api_test/jobs.py", "api_test/main.py", "api_test/services/execution.py", "api_test/job_runner.py", "load-tests/k6/run-admission.js", "api_test/load_test_campaigns.py", "api_test/load_test_monitor.py", "api_test/load_test_mutations.py", "api_test/load_test_harness.py", "api_test/load_results.py", "load-tests/k6/mixed.js", "load-tests/k6/mixed-model.js", "load-tests/k6/read-model.js", "load-tests/k6/campaign-model.js", "load-tests/k6/studio-summary.js")
    result["sourceSha256"] = {name: hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() for name in files}
    result["k6Version"] = subprocess.run([executable, "version"], capture_output=True, text=True, env=environment, timeout=10, check=True).stdout.strip()
    result["appVersion"] = json.loads((REPOSITORY / "web/package.json").read_text())["version"]
    result["commitSha"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True, timeout=5).stdout.strip()
    result["workingTreeDirty"] = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPOSITORY, capture_output=True, text=True, timeout=5).stdout.strip())
    try:
        with (output / "server.log").open("w") as log:
            ready = output / "server-ready.json"
            server = subprocess.Popen([sys.executable, "-m", "api_test.load_test_harness", "_serve", "--root", str(snapshot), "--ready", str(ready)], cwd=REPOSITORY, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
            server._isolated_group = os.name == "posix"
            deadline = time.monotonic() + 30
            while not ready.exists():
                if server.poll() is not None or time.monotonic() > deadline:
                    raise HarnessError("campaign server did not start")
                time.sleep(.05)
            base_url = json.loads(ready.read_text())["baseUrl"]
            while True:
                try:
                    _control(base_url)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise HarnessError("campaign health/control timed out")
                    time.sleep(.05)
            environment.update(STUDIO_BASE_URL=base_url, STUDIO_FIXTURE_PATH=str(snapshot / "fixture.json"), STUDIO_RUNTIME_PATH=str(snapshot / "runtime.json"),
                               STUDIO_PROJECT=f"load-test/{original['dataset']}.json", STUDIO_EXECUTION_MODE="isolated-local-same-server-campaign", STUDIO_OS=sys.platform,
                               STUDIO_CPU=f"{os.cpu_count()} logical CPUs", STUDIO_K6_VERSION=result["k6Version"], STUDIO_APP_VERSION=result["appVersion"], STUDIO_COMMIT_SHA=result["commitSha"], STUDIO_CONFIGURED_VUS=str(config["configuredVus"]),
                               STUDIO_CONTENTION_REQUESTS="5", STUDIO_SELECTION_STRIDE=str(config["selectionStride"]))
            if _host_memory_mb() is not None:
                environment["STUDIO_MEMORY_MB"] = str(_host_memory_mb())
            result.update(serverPid=server.pid, baseUrl=base_url, runnerTimeoutSeconds=2, studioSubprocessWatchdogSeconds=300)
            sampler = ResourceSampler(server.pid, snapshot, _host_memory_mb())
            baseline_config = {**config, "phase": "baseline", "durationSeconds": config["baselineSeconds"]}
            before = _phase(baseline_config, output / "before", snapshot, environment, executable, server, sampler, config)
            result["phases"].append(before)
            if before["status"] != "passed" or before["postRequestCleanup"]["status"] != "passed":
                result["status"] = "failed"
                result["profileBlocked"] = "before baseline did not pass"
                return result
            if mode == "run-capacity":
                for concurrency in (1, 2, 5, 10):
                    phase = _phase({**config, "phase": "run", "vus": concurrency, "durationSeconds": 30}, output / f"run-{concurrency}", snapshot, environment, executable, server, sampler, config)
                    result["phases"].append(phase)
                    reason = capacity_stop_reason(phase)
                    if reason:
                        result["capacityStoppedReason"] = reason
                        break
                result["maxObservedSuccessfulConcurrency"] = max((phase["phase"]["vus"] for phase in result["phases"] if phase["phase"]["phase"] == "run" and phase["status"] == "passed"), default=None)
            elif mode == "run-sustained":
                for concurrency in (1, 2):
                    phase = _phase({**config, "phase": "sustained", "vus": concurrency}, output / f"sustained-{concurrency}", snapshot, environment, executable, server, sampler, config)
                    result["phases"].append(phase)
                    verdict = sustained_verdict(phase)
                    phase["admissionValidation"] = verdict
                    _json(output / f"sustained-{concurrency}" / "phase.json", phase)
                    if verdict["status"] != "passed":
                        result["sustainedStoppedReason"] = verdict["reason"]
                        break
                if not result.get("sustainedStoppedReason"):
                    _control(base_url, config["queueStubDelayMs"])
                    phase = _phase({**config, "phase": "queue", "vus": 1}, output / "queue", snapshot, environment, executable, server, sampler, config)
                    result["phases"].append(phase)
                    phase["admissionValidation"] = sustained_verdict(phase)
                    _json(output / "queue" / "phase.json", phase)
                result["sustainedScope"] = "bounded repeated local execution and explicit queue admission; maximum stable capacity is not established"
                result["maximumStableConcurrency"] = None
                admission_phases = [item for item in result["phases"] if item.get("admissionValidation")]
                result["admissionStatus"] = "failed" if any(item["admissionValidation"]["status"] == "failed" for item in admission_phases) else "unknown" if len(admission_phases) != 3 or any(item["admissionValidation"]["status"] == "unknown" for item in admission_phases) else "passed"
            elif mode == "fault":
                for fault, delay, status in (("error", 0, 500), ("delay", 3000, 200)):
                    _control(base_url, delay, status)
                    phase = _phase({**config, "phase": "fault", "fault": fault}, output / fault, snapshot, environment, executable, server, sampler, config)
                    result["phases"].append(phase)
                    _control(base_url)
            else:
                result["phases"].append(_phase(config, output / "profile", snapshot, environment, executable, server, sampler, config))
            _control(base_url)
            if mode == "fault":
                recovered_run = _phase({**config, "phase": "run", "vus": 1, "durationSeconds": 30}, output / "run-recovered", snapshot, environment, executable, server, sampler, config)
                result["phases"].append(recovered_run)
                result["executionRecovery"] = {"status": recovered_run["status"], "complete": recovered_run["complete"], "client": recovered_run.get("client"), "cleanup": recovered_run["postRequestCleanup"]}
            interrupted_profile = any(phase["phase"]["phase"] == "profile" and phase["stopReason"] is not None for phase in result["phases"])
            after = _phase(baseline_config, output / "after", snapshot, environment, executable, server, sampler, config, allow_incomplete=interrupted_profile)
            result["phases"].append(after)
            result["recovery"] = recovery_report(before, after, {**before["resourceAggregate"], "childProcesses": before.get("postResource", {}).get("childProcesses")}, {**after["resourceAggregate"], "childProcesses": after.get("postResource", {}).get("childProcesses")})
            result["partialFlowsAllowedOnlyForStoppedProfile"] = interrupted_profile
            result["postOriginalFingerprint"] = verify_fixture(snapshot, expected_mutations(snapshot, {**config, "mode": "target"}, allow_incomplete=result["partialFlowsAllowedOnlyForStoppedProfile"]))["fixtureSha256"]
            result["fullDurationCompleted"] = not config["validationMode"] and mode in ("stress", "spike", "soak") and all(phase["complete"] for phase in result["phases"]) and result["phases"][1]["elapsedSeconds"] >= config["durationSeconds"]
            profile = next((phase for phase in result["phases"] if phase["phase"]["phase"] == "profile"), None)
            result["soakStability"] = "failed" if mode == "soak" and result["fullDurationCompleted"] and any(profile["growth"]["metrics"][field]["continuouslyIncreasing"] for field in ("memoryMb", "threads", "walBytes")) else "unknown"
            result["soakTrendScope"] = "sample trend is informational; absence of monotonic growth does not prove2-hour stability"
            result["stableStressRps"] = None
            result["stressCapacityStatus"] = "not established; full stable stage/SLO evidence required"
            result["resourceUnknown"] = [field for field in ("diskIops", "diskLatencyMs")]
            result["status"] = "failed" if any(phase.get("admissionValidation", {}).get("status", "passed") == "failed" for phase in result["phases"]) or any(phase["status"] in ("failed", "aborted", "error") for phase in result["phases"]) or any(phase["postRequestCleanup"]["status"] == "failed" for phase in result["phases"]) or result["recovery"]["status"] == "failed" or result["soakStability"] == "failed" else "unknown" if any(phase.get("admissionValidation", {}).get("status") == "unknown" for phase in result["phases"]) or (mode == "soak" and result["soakStability"] == "unknown") or any(phase["postRequestCleanup"]["status"] == "unknown" for phase in result["phases"]) else result["recovery"]["status"]
    except BaseException as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        if server is not None:
            try:
                _stop(server)
                result["serverStopped"] = server.poll() is not None
            except (OSError, subprocess.SubprocessError) as exc:
                result["status"] = "error"
                result["cleanupError"] = str(exc)
        _json(output / "campaign.json", result)
    return result
