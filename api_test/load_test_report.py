"""Generate a deterministic provisional LT-5 report from checked-in LT1–4 evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "docs"
FILENAMES = [f"load-test-lt{stage}-validation.json" for stage in range(1, 5)]


class ReportError(ValueError):
    pass


def require(value, key):
    if not isinstance(value, dict) or key not in value:
        raise ReportError(f"missing critical evidence: {key}")
    return value[key]


def metric(value, *, integer=False, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (integer and int(value) != value) or (maximum is not None and value > maximum):
        raise ReportError("invalid numeric metric")
    return value


def finite_tree(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("sourceSha256", "currentSourceSha256"):
                if not isinstance(item, dict) or not item or any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in item.values()):
                    raise ReportError("invalid source hash provenance")
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ReportError("non-finite evidence is unsupported")


def summary(value):
    requests = metric(require(value, "requests"), integer=True)
    metric(require(value, "errorRate"), maximum=1)
    metric(require(value, "rps"))
    metric(require(value, "vusMax"), integer=True)
    latency = require(value, "latencyMs")
    values = [metric(require(latency, field)) for field in ("p50", "p90", "p95", "p99", "max")]
    if values != sorted(values):
        raise ReportError("latency percentile order differs")
    if type(require(value, "thresholdsPassed")) is not bool:
        raise ReportError("threshold verdict must be boolean")
    return requests


def equal(actual, expected, label):
    if abs(actual - expected) > 0.000002:
        raise ReportError(f"evidence arithmetic differs: {label}")


def traffic(run):
    count = summary(require(run, "summary"))
    values = require(run, "traffic")
    requests = require(values, "requests")
    for value in requests.values():
        metric(value, integer=True)
    total = sum(requests.values())
    workload = total - require(requests, "support")
    equal(total, count, "classified HTTP count")
    equal(require(values, "totalClassifiedRequests"), total, "total traffic")
    equal(require(values, "workloadRequests"), workload, "workload traffic")
    conflicts = metric(require(values, "expected409"), integer=True)
    if conflicts > require(requests, "contention"):
        raise ReportError("expected409 exceeds contention requests")
    for field, denominator in (("allHttpRatios", total), ("workloadRatios", workload)):
        ratios = require(values, field)
        for category, actual in ratios.items():
            if denominator:
                equal(metric(actual, maximum=1), require(requests, category) / denominator, field)
            elif actual is not None:
                raise ReportError("zero-denominator ratio must remain unknown")
    if require(run, "originalFixtureSha256") != require(run, "postRunOriginalFixtureSha256"):
        raise ReportError("original fixture fingerprint changed")
    if require(run, "status") == "passed" and not run["summary"]["thresholdsPassed"]:
        raise ReportError("failed thresholds cannot be reported passed")


def recovery(value):
    factor = metric(require(value, "factor"))
    if factor != 1.2:
        raise ReportError("recovery factor differs from recorded contract")
    derived = {}
    for name, pair in require(value, "comparison").items():
        before, after = require(pair, "before"), require(pair, "after")
        if before is not None:
            metric(before)
        if after is not None:
            metric(after)
        if before is None or after is None:
            verdict, ratio = "unknown", None
        elif before == 0:
            verdict = "passed" if after == 0 else "failed" if name in ("errorRate", "childProcesses") else "unknown"
            ratio = None
        else:
            ratio = after / before
            verdict = "passed" if ratio <= factor else "failed"
        if require(pair, "verdict") != verdict:
            raise ReportError("stored recovery verdict differs from arithmetic")
        derived[name] = {"before": before, "after": after, "ratio": ratio, "verdict": verdict}
    if not {"p95Ms", "errorRate", "cpuPercent", "memoryMb", "threads", "handles", "childProcesses"}.issubset(derived):
        raise ReportError("recovery is missing critical metrics")
    states = [item["verdict"] for item in derived.values()]
    status = "failed" if "failed" in states else "unknown" if "unknown" in states else "passed"
    if require(value, "status") != status:
        raise ReportError("stored recovery status differs")
    return {"status": status, "comparison": derived}


def read_inputs(directory):
    inputs, hashes = [], []
    for filename in FILENAMES:
        raw = (directory / filename).read_bytes()
        if len(raw) > 4 * 1024 * 1024:
            raise ReportError("evidence file exceeds report input budget")
        def invalid_constant(_value):
            raise ReportError("non-finite evidence is unsupported")
        inputs.append(json.loads(raw, parse_constant=invalid_constant))
        hashes.append({"file": filename, "sha256": hashlib.sha256(raw).hexdigest()})
    return inputs, hashes


def build_report(inputs, hashes):
    if len(inputs) != 4:
        raise ReportError("four LT evidence documents are required")
    for evidence in inputs:
        finite_tree(evidence)
    lt1, lt2, lt3, lt4 = inputs
    fixture_ids = {require(item, "dataset"): require(item, "fixtureSha256") for item in require(lt1, "fixtures")}
    if set(fixture_ids) != {"small", "medium", "large"}:
        raise ReportError("fixture scale evidence is missing")
    readings = {}
    for mode in ("smoke", "baseline"):
        evidence = require(lt2, mode)
        execution = require(evidence, "execution")
        count = summary(require(execution, "summary"))
        try:
            start = datetime.fromisoformat(require(execution, "startedAt").replace("Z", "+00:00"))
            end = datetime.fromisoformat(require(execution, "endedAt").replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise ReportError("invalid baseline timestamps") from exc
        if start.tzinfo is None or end.tzinfo is None or end <= start or count == 0:
            raise ReportError("baseline needs a positive measured interval and requests")
        duration = (end - start).total_seconds()
        equal(execution["summary"]["rps"], count / duration, "baseline RPS")
        endpoints = require(evidence, "endpointMetrics")
        equal(sum(metric(require(endpoint, "requestCount"), integer=True) for endpoint in endpoints), count, "endpoint request count")
        if execution["fixture"]["fixtureSha256"] != fixture_ids["medium"]:
            raise ReportError("baseline fixture identity differs")
        expected_requests = 214 if mode == "smoke" else 754
        if count != expected_requests or execution["summary"]["errorRate"] != 0 or execution["summary"]["thresholdsPassed"] is not True or require(evidence, "checks")["count"] != count * 2:
            raise ReportError("unsupported or contradictory reading snapshot")
        for endpoint in endpoints:
            if metric(require(endpoint, "errorRate"), maximum=1) != 0:
                raise ReportError("healthy reading endpoint contains errors")
            for value in require(endpoint, "latencyMs").values():
                metric(value)
        if require(execution, "postRunIntegrity")["fixtureSha256"] != fixture_ids["medium"] or require(execution, "serverStopped") is not True:
            raise ReportError("reading integrity/cleanup is not verified")
        if require(evidence, "checks")["failed"] != 0 or require(execution, "status") != "passed":
            raise ReportError("baseline functional checks are not passed")
        readings[mode] = {"requests": count, "manifestSeconds": duration, "rps": count / duration, "p95Ms": execution["summary"]["latencyMs"]["p95"],
                          "p99Ms": execution["summary"]["latencyMs"]["p99"], "errorRate": execution["summary"]["errorRate"], "vus": execution["summary"]["vusMax"],
                          "sourceSha256": execution["sourceSha256"], "endpoints": [{"method": item["method"], "endpoint": item["endpoint"], "requests": item["requestCount"], "p95Ms": item["latencyMs"]["p95"]} for item in endpoints]}
    for item in [require(lt3, "functionalTarget"), require(lt3, "shortTargetCapacityFailure"), require(lt3, "unique50"), *require(lt3, "contention")]:
        traffic(item)
    if require(require(lt3, "environment"), "runWorkerLimit") != 2:
        raise ReportError("changed worker snapshot requires source/capacity review")
    contentions = lt3["contention"]
    if len(contentions) != 3 or sorted(item["workload"]["contentionRequests"] for item in contentions) != [5, 20, 50]:
        raise ReportError("three contention scales are required")
    for item in [lt3["functionalTarget"], lt3["unique50"], *contentions]:
        if item["status"] != "passed" or item["summary"]["thresholdsPassed"] is not True or require(item, "integrity") != "passed" or require(item, "serverStopped") is not True:
            raise ReportError("healthy write/run result is not verified")
    if lt3["unique50"]["mutations"]["unique"] != 50 or lt3["unique50"]["traffic"]["requests"]["unique"] != 200:
        raise ReportError("unique50 complete-flow evidence differs")
    for item in contentions:
        group = item["workload"]["contentionRequests"]
        if item["traffic"]["requests"]["contention"] != group or item["traffic"]["expected409"] != group - 1 or item["mutations"]["contention"] != 1:
            raise ReportError("contention winner/error denominator differs")
    admission = []
    for concurrency in (1, 2, 5, 10):
        responses = require(require(lt4, "independentCapacity"), str(concurrency))
        if len(responses) != concurrency:
            raise ReportError("admission batch denominator differs")
        successes = sum(item["httpStatus"] == 200 and item["exitCode"] == 0 and item["resultStatus"] == "passed" for item in responses)
        rejected = sum(item["httpStatus"] == 429 for item in responses)
        if successes + rejected != concurrency:
            raise ReportError("admission batch has unsupported/unverified results")
        admission.append({"concurrency": concurrency, "succeeded": successes, "rejected429": rejected})
    observed = max((item["concurrency"] for item in admission if item["succeeded"] == item["concurrency"]), default=None)
    if admission != [{"concurrency": value, "succeeded": min(value, 2), "rejected429": max(0, value - 2)} for value in (1, 2, 5, 10)]:
        raise ReportError("changed admission snapshot requires a new conclusion")
    campaign_inputs = require(lt4, "campaignEvidence")
    expected_campaigns = {("run-capacity", 10), ("fault", 1), ("stress", 2), ("stress", 200), ("spike", 2), ("soak", 2)}
    if len(campaign_inputs) != 6 or {(item["configuration"]["mode"], item["configuration"]["configuredVus"]) for item in campaign_inputs} != expected_campaigns:
        raise ReportError("critical campaign collection differs")
    campaigns = []
    for evidence in require(lt4, "campaignEvidence"):
        pid = metric(require(evidence, "sameServerPid"), integer=True)
        if evidence.get("serverStopped") is not True or not evidence["phases"]:
            raise ReportError("campaign lifecycle evidence is missing")
        for phase in require(evidence, "phases"):
            if require(phase, "serverPid") != pid:
                raise ReportError("campaign baseline/profile server PID differs")
            for count in require(require(phase, "client"), "httpStatuses").values():
                metric(count, integer=True)
            statuses = phase["client"]["httpStatuses"]
            if phase["phase"]["phase"] != "fault":
                if any(count and (int(status) == 0 or int(status) >= 500) for status, count in statuses.items()):
                    raise ReportError("normal5xx/network result requires a new failed/unknown coverage review")
                if require(phase["client"], "runExitFailures") != 0:
                    raise ReportError("healthy phase contains business execution failure")
            if phase.get("summary"):
                total = sum(statuses.values())
                unexpected = sum(count for status, count in statuses.items() if int(status) == 0 or (int(status) >= 400 and int(status) != 409))
                if total:
                    equal(phase["summary"]["errorRate"], unexpected / total, "phase unexpected errors")
                equal(summary(phase["summary"]), sum(phase["client"]["httpStatuses"].values()), "phase HTTP statuses")
        if require(evidence, "originalFingerprint") != require(evidence, "postOriginalFingerprint"):
            raise ReportError("campaign original fixture changed")
        if require(evidence, "fullDurationCompleted"):
            raise ReportError("report requires a fresh capacity/SLO review for new full campaigns")
        key = (evidence["configuration"]["mode"], evidence["configuration"]["configuredVus"])
        expected_status = {("run-capacity", 10): "failed", ("fault", 1): "failed", ("stress", 2): "passed", ("stress", 200): "failed", ("spike", 2): "failed", ("soak", 2): "unknown"}[key]
        derived_recovery = recovery(require(evidence, "recovery"))
        expected_recovery = "failed" if key in (("spike", 2), ("stress", 200)) else "passed"
        if evidence["status"] != expected_status or derived_recovery["status"] != expected_recovery:
            raise ReportError("changed campaign verdict requires a new reviewed report")
        if key == ("stress", 200):
            profiles = [phase for phase in evidence["phases"] if phase["phase"]["phase"] == "profile"]
            if len(profiles) != 1 or profiles[0]["stopReason"] != "run_capacity_limit_429_before_further_increase" or profiles[0]["phase"].get("startVus") != 50 or profiles[0]["phase"]["stages"][0] != {"duration": "10s", "target": 50} or profiles[0]["elapsedSeconds"] >= 10 or profiles[0]["client"]["capacity429"] != 6:
                raise ReportError("historical initial Stress failure point differs")
        campaigns.append({"mode": evidence["configuration"]["mode"], "vusConfigured": evidence["configuration"]["configuredVus"], "validation": evidence["configuration"]["validationMode"],
                          "status": evidence["status"], "recovery": derived_recovery, "sourceSha256": evidence["sourceSha256"], "evidenceLabel": evidence["evidenceLabel"],
                          "phases": [{"configuredStartVus": phase["phase"].get("startVus"), "kind": phase["phase"]["phase"], "status": phase["status"], "complete": phase["complete"], "stopReason": phase["stopReason"], "elapsedSeconds": phase.get("elapsedSeconds"), "client": phase["client"]} for phase in evidence["phases"]]})
    final_fault = require(lt4, "finalFaultRecovery")
    fault_pid = metric(require(final_fault, "sameServerPid"), integer=True)
    if len(require(final_fault, "phases")) != 5 or any(require(phase, "serverPid") != fault_pid for phase in final_fault["phases"]):
        raise ReportError("final fault recovery server PID differs")
    fault_recovery = recovery(require(final_fault, "recovery"))
    recovered = require(final_fault, "executionRecovery")
    cleanup = require(recovered, "cleanup")
    if require(final_fault, "serverStopped") is not True or require(recovered, "complete") is not True or cleanup.get("status") != "passed" or cleanup.get("childProcesses") != 0 or cleanup.get("tempEntries") != 0:
        raise ReportError("post-fault cleanup/completeness is not verified")
    if recovered["client"]["httpStatuses"] != {"200": 1} or recovered["client"]["runExitFailures"] != 0:
        raise ReportError("normal saved run after reset is not verified")
    faults = [item for item in final_fault["phases"] if item["phase"]["phase"] == "fault"]
    if len(faults) != 2 or {item["phase"]["fault"] for item in faults} != {"error", "delay"} or any(item["client"]["faultObservations"] != 2 for item in faults):
        raise ReportError("both controlled fault observations are required")
    delay = next(item for item in faults if item["phase"]["fault"] == "delay")
    if delay["summary"]["errorRate"] != 0 or delay["client"]["runExitFailures"] != 2:
        raise ReportError("timeout business error evidence differs")
    if require(final_fault, "executionRecovery")["status"] != "passed":
        raise ReportError("post-fault execution recovery is not verified")
    failures = require(lt3, "capacityFailure")
    target = lt3["shortTargetCapacityFailure"]
    equal(failures["unexpected429"] / failures["requests"], target["summary"]["errorRate"], "Target unexpected error denominator")
    if require(lt3, "activeVusCorrection")["correctedActualPeak"] != target["summary"]["vusMax"]:
        raise ReportError("active VU correction differs")
    if target["summary"]["vusMax"] != 20 or failures["requests"] != 125 or failures["unexpected429"] != 2 or target["status"] != "failed" or target["summary"]["thresholdsPassed"] is not False:
        raise ReportError("changed first-failure snapshot requires a new conclusion")
    first = [{"scenario": "Target shortened20→50", "actualPeakVus": target["summary"]["vusMax"], "requests": failures["requests"], "rejected429": failures["unexpected429"], "errorRate": target["summary"]["errorRate"], "reachedNextStage": False}]
    for item in campaigns:
        for phase in item["phases"]:
            if item["mode"] == "stress" and item["vusConfigured"] == 200 and phase["stopReason"] == "run_capacity_limit_429_before_further_increase" and phase["kind"] == "profile":
                first.append({"scenario": "Stress shortened50→200", "actualPeakVus": None, "configuredInitialVus": phase["configuredStartVus"], "requests": sum(phase["client"]["httpStatuses"].values()), "rejected429": phase["client"]["capacity429"], "errorRate": None,
                              "elapsedSeconds": phase["elapsedSeconds"], "reachedNextStage": False})
    coverage = [
        ("Smoke", "observed-pass", "endpoint별1VU60초·214요청;1회"), ("Baseline", "provisional", "5VU300초·754요청;동일조건3회/중앙값 미확정"),
        ("Target", "observed-fail", "실제20VU429;50VU/전체1200초/3회 미검증"), ("고유 저장/경합", "observed-pass", "50VU단일batch revision4;5/20/50정확히1승자;지속시험 아님"),
        ("Stress", "observed-fail", "50VU429중단·회복실패;full단계/SLO/최대RPS 미확정"), ("Spike", "observed-fail", "축소1→2→1에서p95회복실패;full100VU미검증"),
        ("Soak", "unknown", "2VU40초;35VU2시간안정성 미검증"), ("Target 읽기p95≤300/p99≤1000ms", "unknown", "Baseline값으로TargetSLO를 판정하지 않음"),
        ("Target 고유 쓰기p95≤1000ms", "unknown", "unique50의단일batch값으로TargetSLO를 판정하지 않음"), ("비예상 오류율<1%", "observed-fail", "축소Target125요청중429두건=1.6%"),
        ("정상입력5xx0", "observed-pass", "관측normal호출 범위;intentional500별도;production보장 아님"), ("run exit0/고아0", "partial", "healthy호출/정리확인;429거부·injectedtimeout exit실패 별도"),
        ("CPU85%/메모리80% 5분", "unknown", "실제지속시험 미실행;timer단위테스트만"), ("중단60/120초", "partial", "fake timestamp검증·scaled2초fault·실제429중단;full실시간120초미검증"),
        ("회복120%", "observed-fail", "Spike/50VUStress p95초과;다른resource통과가 원인증명은 아님"), ("IOPS/latency/Windows/별도발생기", "unknown", "수집/실행 미검증")]
    return {"reportVersion": 1, "supportedSnapshotLayout": "2026-09-29 checked-in LT1-LT4; changed critical results require review rather than silent fixed conclusions", "date": require(lt4, "date"), "status": "provisional-incomplete-campaign", "inputSha256": hashes,
            "environment": lt3["environment"], "readingObservations": readings, "baselineRepeatCount": 1, "baselineMedian": None,
            "maximumStableRps": None, "sustainedRunCapacity": None, "observedAdmissionConcurrency": observed, "admissionBatches": admission,
            "firstFailurePoints": first, "campaigns": campaigns, "finalFaultRecovery": fault_recovery, "coverage": [{"item": item, "status": status, "scope": scope} for item, status, scope in coverage],
            "bottlenecks": [{"confidence": "confirmed measured constraint", "topic": "synchronous admission", "evidence": "measurement workers2 +singlebatch1/2pass,5/10→429;legacy_slot nonblocking rejection", "sourceReference": "api_test/jobs.py at measurement snapshot4832615; historical code/admission corroboration, current arbitrarysettings not inferred"},
                            {"confidence": "hypothesis", "topic": "case list projection work", "evidence": "Baseline/api/cases highestread p95;list→case_summaries→SQLite projectionread/JSON parse path confirmed, causalshare unmeasured"},
                            {"confidence": "unproven cause", "topic": "recovery p95", "evidence": "singlehost shortwindows,different source versions,no per-query/file-I/O trace;no SQLitecapacity orleak conclusion"}],
            "faultBusinessErrors": [{"kind": phase["phase"].get("fault"), "httpErrorRate": (phase.get("summary") or {}).get("errorRate"), "runExitFailures": phase["client"]["runExitFailures"], "faultObservations": phase["client"]["faultObservations"]} for phase in final_fault["phases"] if phase["phase"]["phase"] == "fault"]}


def render(report):
    baseline = report["readingObservations"]["baseline"]
    case = next(item for item in baseline["endpoints"] if item["endpoint"] == "/api/cases")
    lines = ["# LT-5 잠정 기준선·용량·병목 보고서", "", f"측정일: {report['date']}. 보고서 작성은 완료했지만 전체 부하 캠페인과 SLO 검증은 미완료다.", "",
             f"**최대 안정 RPS와 지속 안정 동시성은 미확정이다. 한 번의 동시 요청에서 모두 성공한 관측 요청 수는 {report['observedAdmissionConcurrency']}개다.**", "",
             "## 관측된 기준선", "", f"Medium 데이터셋, 같은 호스트의 macOS·SQLite에서 5 VU Baseline을 실행했다. {baseline['requests']}개 요청 ÷ {baseline['manifestSeconds']:.6f}초 = **{baseline['rps']:.6f} RPS**이며, p95는 **{baseline['p95Ms']} ms**, p99는 {baseline['p99Ms']} ms, HTTP 오류율은 {baseline['errorRate']:.1%}다.",
             "이 처리량에는 1~3초 think time, setup과 graceful stop이 포함된다. 서버의 최대 처리량을 뜻하지 않는다. 같은 조건의 3회 실행이 없어 중앙값은 null로 유지한다. 서로 다른 코드·설정·짧은 window의 p95/p99를 합산하거나 평균 내지 않는다.", "",
             f"`/api/cases`의 p95는 {case['p95Ms']} ms다. 전체 endpoint 관측값은 machine summary에 보존한다.", "", "## 최초 실패와 회복", "", "| 시험 | 관측 | 판정 |", "| --- | --- | --- |"]
    for failure in report["firstFailurePoints"]:
        vus = f"실제 {failure['actualPeakVus']} VU" if failure["actualPeakVus"] is not None else f"초기 설정 {failure['configuredInitialVus']} VU"
        lines.append(f"| {failure['scenario']} | {vus}, {failure['requests']}개 요청, 429 {failure['rejected429']}건 | 다음 단계 미도달·용량 실패 |")
    for campaign in report["campaigns"]:
        if campaign["recovery"]["status"] == "failed":
            value = campaign["recovery"]["comparison"]["p95Ms"]
            lines.append(f"| {campaign['mode']} 회복 ({campaign['vusConfigured']} VU 설정·축소) | {value['before']} → {value['after']} ms, 기준선의 {value['ratio']*100:.2f}% | 120% 초과·실패 |")
    lines += ["", "Target의 실제 활성 20 VU와 할당 50 VU를 구분했다. Stress는 초기 50 VU plateau 10초가 끝나기 전에 중단되어 75 VU로 올라가지 않았다. LT-4의 기록과 별도 raw 검증은 실제 peak 50 VU를 확인했으며, 할당 200 VU를 peak로 사용하지 않는다. 실패를 재실행으로 덮어쓰지 않는다.", "", "## 단일 동시 요청과 장애 주입", "", "| 동시 요청 | 200/exit 0 | 429 |", "| --- | ---: | ---: |"]
    lines += [f"| {item['concurrency']} | {item['succeeded']} | {item['rejected429']} |" for item in report["admissionBatches"]]
    lines += ["", "측정 snapshot의 worker 설정 2와 [측정 당시 JobManager](../api_test/jobs.py)의 nonblocking `legacy_slot` 거부 구조가 이 결과를 설명한다. 현재 다른 설정이나 지속 부하에서의 최대 동시성을 검증한 것은 아니다.",
              "의도적으로 주입한 500은 명시적으로 축소한 2초 gate에서 중단됐다. stub의 3초 지연은 saved case의 HTTP timeout 2초를 초과했다. Studio subprocess watchdog 300초와는 별도 경로다. delay phase의 HTTP errorRate는 0이지만 run exit 실패 2건을 별도로 기록했다. reset 후 정상 saved run 1회의 exit 0, 정리와 회복도 확인했다.", "", "## 시나리오와 SLO 검증 범위", "", "| 항목 | 상태 | 증거 범위 |", "| --- | --- | --- |"]
    labels = {"observed-pass": "관측 범위 통과", "observed-fail": "관측 실패", "provisional": "잠정", "unknown": "미확정", "partial": "부분 검증"}
    lines += [f"| {item['item']} | {labels[item['status']]} | {item['scope']} |" for item in report["coverage"]]
    lines += ["", "## 병목의 증거와 가설", "", "- 확인된 제약은 측정 환경의 동시 실행 2개와 429다. 정책과 queue 사용 흐름을 먼저 검토한다. 이 보고서는 worker를 증가시키지 않았다.",
              "- 확인된 코드 패턴은 [case 목록](../api_test/services/documents.py) → [case_summaries/read_studio_document](../api_test/services/studio.py)다. SQLite 경로는 프로젝트의 JSON 투영을 읽고 파싱한다. 관측된 Medium은 프로젝트당 100개 case와 1/10/100 KiB 본문을 포함한다. 파일 읽기, SQL, serialization의 실제 비중과 최적화 효과는 미측정이다.",
              "- 회복 p95가 기준선의 137.54%와 144.87%가 된 것은 측정 사실이다. 같은 호스트의 부하 경쟁, 짧은 window, 캐시나 파일 읽기의 영향은 가설이다. per-query/file trace가 없어 원인을 단정하지 않는다. lock 오류가 보이지 않았다는 사실도 SQLite 용량의 증거가 아니다. PostgreSQL 부하 경로는 미검증이다.", "", "## 우선 후속 작업", ""]
    followups = [
        ("P0 실행 정책", "동시 실행 2개, 429 안내와 RUN-2 queue 사용 기준을 확정한다.", "python -m api_test.load_test_harness run-capacity --fixture data/lt-fixtures/medium-01 --output data/load-tests/admission-review", "이 명령은 단일 batch만 측정한다. sustained executor는 아직 없으므로 별도로 구현·검증하고, 지속 실행 성공과 고아 프로세스 0을 확인해야 안정 동시성을 판정할 수 있다."),
        ("P1 비교 가능한 기준선", "동일한 코드 hash, fixture, hardware, 발생기와 window로 Baseline 3회를 수집한다.", "python -m api_test.load_test_harness baseline --fixture data/lt-fixtures/medium-01 --output data/load-tests/baseline-repeat-01", "01/02/03의 새 output으로 반복한다. 동일 조건을 확인한 뒤 run 단위 중앙값을 검토하며 percentile 표본을 pool하지 않는다."),
        ("P1 회복 원인 분리", "목록 SQL, 투영 읽기·JSON 파싱, serialization과 서버·발생기 CPU를 분리 계측한다.", "python -m api_test.load_test_harness spike --fixture data/lt-fixtures/medium-01 --output data/load-tests/spike-cause --validation-seconds 120 --validation-vus 2", "기존 실패를 보존하고 같은 window의 120% 조건과 원인 trace를 비교한다. 현재 명령은 query trace나 device IOPS를 수집하지 않으므로 별도 계측이 필요하다."),
        ("P2 데이터 규모와 전체 캠페인", "실행 정책과 안전 조건을 해결한 뒤 Small/Medium/Large, Target 3회, Stress·Spike·Soak을 격리 환경에서 측정한다.", "python -m api_test.load_test_harness soak --fixture data/lt-fixtures/medium-01 --output data/load-tests/soak-full", "실제 2시간, 단계별 SLO, 중단·회복과 장시간 추세 근거가 없으면 최대 용량과 안정성은 미확정으로 유지한다. 전체 실행을 이 보고서 생성 과정에서 수행하지 않는다."),
        ("P2 재현과 보존", "원본, 환경, 실행 코드와 importer 버전을 정규화 결과와 연결해 보존한다.", "python -m api_test.load_test_report --check", "clean clone에서 checked-in JSON만으로 같은 보고서를 만든다. /tmp 경로는 증거 포인터이며 필수 입력이 아니다."),
    ]
    for title, work, command, criterion in followups:
        lines += [f"**{title}** — {work}", "", f"`{command}`", "", f"완료 기준: {criterion}", ""]
    lines += ["## provenance와 재생성", "", "생성기는 2026-09-29 LT-1~LT-4 snapshot의 주요 결과를 검증한다. 숫자, 분모, 상태, PID와 회복 산술이 모순되거나 중요한 collection이 없으면 보고서를 만들지 않는다. 주요 결과가 달라진 새 snapshot은 별도 검토가 필요하다. source hash와 진단·최종 버전 차이는 evidence 파일에 보존한다. 원본 raw의 독립 검증은 별도이며, 입력 hash가 원본의 진실성을 증명하지는 않는다.", "", "| 입력 | SHA256 |", "| --- | --- |"]
    lines += [f"| [{item['file']}]({item['file']}) | `{item['sha256']}` |" for item in report["inputSha256"]]
    lines += ["", "`python -m api_test.load_test_report`로 재생성하고, `--check`로 파일을 변경하지 않고 일치 여부를 확인한다.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        inputs, hashes = read_inputs(args.evidence_dir)
        report = build_report(inputs, hashes)
        files = {"load-test-baseline-report.md": render(report), "load-test-baseline-summary.json": json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"}
        if args.check:
            if any(not (args.output_dir / name).is_file() or (args.output_dir / name).read_text(encoding="utf-8") != content for name, content in files.items()):
                print("LT-5 report outputs are stale or missing", file=sys.stderr)
                return 1
            print("LT-5 report is reproducible and up to date")
        else:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (args.output_dir / name).write_text(content, encoding="utf-8")
            print("Wrote provisional LT-5 report and machine summary")
        return 0
    except (ReportError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"LT-5 report: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
