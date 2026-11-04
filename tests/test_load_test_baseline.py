"""P1 comparison refuses incomplete conditions and records isolated case-list spans."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.responses import Response

from api_test.collaboration_store import CollaborationStore
from api_test.load_test_baseline import SOURCE_FILES, _job_batch, _phase_trace, _single_baseline_reasons, compare_three, render_report, trace_summary
from api_test.load_test_baseline_diagnostics import CaseListProbe, timed_case_list
from api_test.load_test_harness import generate_fixture
from api_test.load_test_monitor import stable_resource_window
from api_test.load_test_mutations import RUN_CASE
from api_test.services import studio
from api_test.services.documents import list_documents


class BaselineP1Tests(unittest.TestCase):
    def fixtures(self):
        origin = datetime(2026, 10, 4, tzinfo=timezone.utc)
        digest = "a" * 64
        identity = {"appVersion": "1.0.1", "commitSha": "b" * 40, "pythonVersion": "3.13.5", "k6Version": "k6 2.3.0",
                    "os": "macOS", "machine": "arm64", "logicalCpuCount": 8, "memoryMb": 16384, "diskDevice": 1,
                    "k6BinarySha256": digest, "sourceSha256": dict.fromkeys(SOURCE_FILES, digest)}
        census = {"serverPid": 101, "threads": [{"name": "studio-run-0", "nativeId": 500, "daemon": True},
                                               {"name": "studio-run-1", "nativeId": 501, "daemon": True},
                                               {"name": "AnyIO worker thread", "nativeId": 502, "daemon": True}]}
        runs = []
        for index, (rps, p95) in enumerate(((1.0, 10.0), (3.0, 30.0), (2.0, 20.0))):
            started = origin + timedelta(seconds=index * 360)
            server_resources = [{"timestamp": (started + timedelta(seconds=step)).isoformat(), "processPid": 101, "treeRole": "server", "cpuPercent": None if step == 0 else .5, "memoryMb": 100} for step in range(0, 301, 5)]
            generator_resources = [{"timestamp": (started + timedelta(seconds=step)).isoformat(), "processPid": 200 + index, "treeRole": "load generator", "cpuPercent": None if step == 0 else .25, "memoryMb": 20} for step in range(0, 301, 5)]
            run_id = f"run_{index}"
            phase = {"status": "passed", "complete": True, "stopReason": None, "serverPid": 101, "generatorPid": 200 + index,
                     "elapsedSeconds": 310, "postRequestCleanup": {"status": "passed", "childProcesses": 0, "tempEntries": 0},
                     "phase": {"phase": "baseline", "durationSeconds": 300, "vus": 5, "validationMode": False,
                               "sampleIntervalSeconds": 5, "captureGenerator": True, "resetCpuAtPhaseStart": True},
                     "summary": {"requests": 100, "rps": rps, "vusMax": 5, "thresholdsPassed": True, "errorRate": 0,
                                 "latencyMs": {"p95": p95}},
                     "client": {"correctnessFailures": 0, "runExitFailures": 0, "capacity429": 0, "networkOr5xxRate": 0},
                     "integrity": {"fixtureSha256": digest}, "resourceWindowSeconds": 60,
                     "resources": server_resources, "generatorResources": generator_resources,
                     "resourceAggregate": stable_resource_window(server_resources, 60),
                     "generatorResourceAggregate": stable_resource_window(generator_resources, 60)}
            runs.append({"phase": phase, "runId": run_id, "bundleRunId": run_id, "runStartedAt": started.isoformat(),
                         "runEndedAt": (started + timedelta(seconds=310)).isoformat(), "identityBefore": identity,
                         "identityAfter": identity, "fixtureBefore": digest, "fixtureAfter": digest, "caseListRequests": 1,
                         "trace": {"status": "passed", "count": 1, "sequenceStart": index, "sequenceEnd": index},
                         "threadsBefore": copy.deepcopy(census), "threadsAfter": copy.deepcopy(census), "serverPid": 101,
                         "artifactsSha256": dict.fromkeys(("raw.jsonl", "bundle.json", "studio-summary.json"), digest)})
        return runs, identity, digest

    def test_three_complete_same_source_runs_have_run_level_median(self):
        runs, identity, digest = self.fixtures()
        outcome = compare_three(runs, identity, digest)
        self.assertEqual(outcome["status"], "comparable")
        self.assertEqual(outcome["runLevelMedianRps"], 2)
        self.assertEqual(outcome["runLevelMedianP95Ms"], 20)
        self.assertEqual(outcome["scope"], "actual_3x300")

    def test_incomplete_source_cleanup_and_time_cannot_publish_median(self):
        changes = (
            lambda runs, identity: runs.pop(),
            lambda runs, identity: runs[1].update(runId=runs[0]["runId"]),
            lambda runs, identity: runs[1]["phase"].update(elapsedSeconds=1),
            lambda runs, identity: runs[1]["phase"]["postRequestCleanup"].update(childProcesses=1),
            lambda runs, identity: runs[1]["phase"]["summary"].update(thresholdsPassed=False),
            lambda runs, identity: runs[1]["phase"]["client"].update(correctnessFailures=1),
            lambda runs, identity: runs[1]["phase"]["phase"].update(durationSeconds=25),
            lambda runs, identity: runs[1].update(identityAfter={**identity, "os": "changed"}),
            lambda runs, identity: runs[1].update(bundleRunId="different"),
            lambda runs, identity: runs[1]["trace"].update(sequenceStart=0),
            lambda runs, identity: runs[1]["threadsAfter"]["threads"][0].update(nativeId=999),
            lambda runs, identity: runs[1]["phase"]["generatorResources"].__setitem__(30, None),
            lambda runs, identity: runs[1]["phase"]["resources"].__setitem__(30, runs[1]["phase"]["resources"][29]),
            lambda runs, identity: runs[1]["phase"]["generatorResources"].__delitem__(slice(1, -1)),
        )
        for change in changes:
            runs, identity, digest = copy.deepcopy(self.fixtures())
            change(runs, identity)
            with self.subTest(change=change.__code__.co_firstlineno):
                outcome = compare_three(runs, identity, digest)
                self.assertEqual(outcome["status"], "incomparable")
                self.assertIsNone(outcome["runLevelMedianRps"])
        runs, identity, digest = self.fixtures()
        identity["sourceSha256"] = {}
        self.assertIsNone(compare_three(runs, identity, digest)["runLevelMedianP95Ms"])

    def test_recovery_baseline_requires_complete_resource_window_and_clean_client(self):
        runs, identity, digest = self.fixtures()
        after = runs[0]
        self.assertEqual(_single_baseline_reasons(after, identity, digest, 300), [])
        after["phase"]["generatorResources"] = after["phase"]["generatorResources"][:2]
        self.assertIn("server_or_generator_resource_window_unknown", _single_baseline_reasons(after, identity, digest, 300))
        runs, identity, digest = self.fixtures()
        after = runs[0]
        after["phase"]["client"]["correctnessFailures"] = 1
        self.assertIn("client_failure_or_unknown", _single_baseline_reasons(after, identity, digest, 300))
        runs, identity, digest = self.fixtures()
        after = runs[0]
        after["phase"]["elapsedSeconds"] = 1
        self.assertIn("phase_elapsed_shorter_than_nominal_duration", _single_baseline_reasons(after, identity, digest, 300))

    def test_unrun_recovery_report_does_not_claim_completed_batches(self):
        report = render_report({"status": "unknown", "mode": "recovery-diagnose", "validationMode": True,
                                "serverPid": 101, "fixtureSha256": "a" * 64,
                                "diagnosis": {"status": "not_run", "reason": "before baseline did not pass eligibility", "batches": []}})
        self.assertIn("terminal 완료한 async 5개 batch: 0회", report)
        self.assertNotIn("반복 5개 batch의 이름", report)

    def test_trace_requires_exclusive_accounting_sequence_and_exact_request_count(self):
        row = {"formatVersion": 1, "operation": "GET /api/cases", "timestamp": datetime.now(timezone.utc).isoformat(),
               "sequence": 10, "caseCount": 100, "projectionReadBytes": 4000, "responseBytes": 500,
               "lookupNs": 10, "pathResolutionNs": 20, "projectionReadNs": 30, "utf8DecodeNs": 40,
               "jsonParseNs": 50, "fieldSelectionNs": 60, "serializationNs": 70, "otherNs": 80, "handlerNs": 360}
        self.assertEqual(trace_summary([row], 1)["status"], "passed")
        self.assertEqual(trace_summary([row], 2)["status"], "unknown")
        self.assertEqual(trace_summary([row, row], 2)["status"], "unknown")
        broken = {**row, "handlerNs": 359}
        self.assertEqual(trace_summary([broken], 1)["status"], "unknown")
        self.assertEqual(trace_summary([{**row, "jsonParseNs": float("nan")}], 1)["status"], "unknown")

    def test_manifest_microseconds_normalize_to_bundle_milliseconds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "run_normalized"
            manifest = {"run": {"id": run_id, "startedAt": "2026-10-04T09:28:54.012264+00:00", "endedAt": "2026-10-04T09:29:25.301Z"}}
            bundle = {"run": {"id": run_id, "startedAt": "2026-10-04T09:28:54.012Z", "endedAt": "2026-10-04T09:29:25.301Z"},
                      "endpointMetrics": [{"method": "GET", "endpoint": "/api/cases", "requestCount": 1}]}
            (root / "studio-summary.json").write_text(json.dumps(manifest))
            (root / "bundle.json").write_text(json.dumps(bundle))
            row = {"formatVersion": 1, "operation": "GET /api/cases", "timestamp": "2026-10-04T09:29:00+00:00",
                   "sequence": 1, "caseCount": 100, "projectionReadBytes": 1000, "responseBytes": 300,
                   "lookupNs": 10, "pathResolutionNs": 20, "projectionReadNs": 30, "utf8DecodeNs": 40,
                   "jsonParseNs": 50, "fieldSelectionNs": 60, "serializationNs": 70, "otherNs": 80, "handlerNs": 360}
            self.assertEqual(_phase_trace(root, [row])[0]["status"], "passed")
            bundle["run"]["startedAt"] = "2026-10-04T09:28:54.010Z"
            (root / "bundle.json").write_text(json.dumps(bundle))
            self.assertEqual(_phase_trace(root, [row])[0]["status"], "unknown")

    def test_prepared_async_job_accepts202_without_invented_admission_field(self):
        census = {"serverPid": 101, "threads": []}
        reports = [(202, {"runId": "run_one", "status": "queued"}),
                   (200, {"runId": "run_one", "status": "passed", "exitCode": 0,
                          "result": {"targets": [{"caseReference": RUN_CASE, "status": "passed", "httpStatus": 200}]}}),
                   (200, census)]
        sampler = Mock()
        sampler.sample.return_value = {"childProcesses": 0, "tempEntries": 0}
        with patch("api_test.load_test_baseline._private_json", side_effect=reports) as client:
            result = _job_batch("http://127.0.0.1:12345", 1, sampler, 101)
        self.assertEqual(result["terminalPassed"], 1)
        self.assertEqual(client.call_count, 3)
        reports[1][1]["result"]["targets"][0]["status"] = "failed"
        with patch("api_test.load_test_baseline._private_json", side_effect=reports):
            with self.assertRaises(ValueError):
                _job_batch("http://127.0.0.1:12345", 1, sampler, 101)

    def test_pagination_bypasses_legacy_full_list_instrumentation(self):
        for parameter in ('page_size', 'q', 'tag', 'sort', 'cursor'):
            with self.subTest(parameter=parameter):
                request = SimpleNamespace(request=SimpleNamespace(query_params={parameter: ''}))
                original, service, trace = Mock(return_value='bounded page'), Mock(), Mock()
                self.assertEqual(timed_case_list(request, service, 'cases', trace, original), 'bounded page')
                service.collaboration_store.assert_not_called()
                trace.record.assert_not_called()
                original.assert_called_once_with(request, service, 'cases')

    def test_instrumented_cases_match_original_response_without_leaking_references(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "", "STUDIO_REDIS_URL": ""}):
            root = Path(directory) / "fixture"
            generate_fixture(root, "small")
            store = CollaborationStore(root / "data/studio.db", {"projects": root / "projects", "cases": root / "case", "pipelines": root / "pipelines"})
            store.initialize(import_existing=False)
            project = "load-test/project-000.json"
            request = SimpleNamespace(request=SimpleNamespace(query_params={"project": project}),
                                      query_value=lambda name: project if name == "project" else None,
                                      json_response=lambda status, payload: Response(json.dumps(payload, ensure_ascii=False).encode(), status_code=status, media_type="application/json", headers={"Cache-Control": "no-store"}))
            service = SimpleNamespace(collaboration_store=lambda: store, CASE_ROOT=root / "case", safe_file=studio.safe_file,
                                      case_summaries=studio.case_summaries, document_root=lambda kind: root / "case")
            expected = list_documents(request, service, "cases")
            path = Path(directory) / "trace.jsonl"
            actual = timed_case_list(request, service, "cases", CaseListProbe(path), list_documents)
            self.assertEqual(actual.status_code, expected.status_code)
            self.assertEqual(actual.headers, expected.headers)
            self.assertEqual(actual.body, expected.body)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(trace_summary(rows, 1)["status"], "passed")
            self.assertNotIn("project-000-case", path.read_text(encoding="utf-8"))
            self.assertNotIn("padding", path.read_text(encoding="utf-8"))
