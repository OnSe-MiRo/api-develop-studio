"""LT-4 timing, bounded options, nullable resources and local stub contracts."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_test.load_test_campaigns import configuration, install_stub, enriched_raw, capacity_stop_reason
from api_test.load_test_monitor import RawTail, StopPolicy, cpu_seconds, within_baseline, growth_report, stable_resource_window


class LoadTestCampaignTests(unittest.TestCase):
    def test_default_models_and_validation_do_not_silently_scale_stop_timers(self):
        stress = configuration("stress")
        self.assertEqual(stress["durationSeconds"], 2100)
        self.assertEqual(stress["stressMaximumVus"], 200)
        self.assertEqual(stress["stages"][0], {"duration": "300s", "target": 50})
        self.assertEqual(configuration("spike")["stages"][0], {"duration": "30s", "target": 100})
        self.assertEqual(configuration("soak")["durationSeconds"], 7200)
        self.assertEqual(configuration("soak")["vus"], 35)
        shortened = configuration("stress", 40, 2)
        self.assertEqual(shortened["windowSeconds"], 60)
        self.assertEqual(shortened["resourceSustainSeconds"], 120)
        self.assertFalse(shortened["scaledStopTimers"])
        self.assertTrue(configuration("fault", 10, validation_stop_seconds=2)["scaledStopTimers"])
        for arguments in (("stress", 9), ("stress", 121), ("stress", None, 2), ("fault", 10, 2), ("run-capacity", 10, 2), ("fault", 10, None, True), ("fault", 10, None, 2.5)):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                configuration(*arguments)

    def test_real_60_and_120_second_predicates_and_unknown_reset(self):
        policy = StopPolicy(0)
        client = {"networkOr5xxRate": 1}
        self.assertIsNone(policy.evaluate(59.999, client, {}))
        self.assertIn("full_window", policy.evaluate(60, client, {}))
        policy = StopPolicy(0)
        healthy = {"networkOr5xxRate": .05}
        self.assertIsNone(policy.evaluate(0, healthy, {"cpuPercent": 96}))
        self.assertIsNone(policy.evaluate(119.999, healthy, {"cpuPercent": 96}))
        self.assertIn("sustained", policy.evaluate(120, healthy, {"cpuPercent": 96}))
        policy = StopPolicy(0)
        policy.evaluate(0, healthy, {"memoryPercent": 91})
        self.assertIsNone(policy.evaluate(119, healthy, {"memoryPercent": None}))
        self.assertIsNone(policy.evaluate(120, healthy, {"memoryPercent": 91}))
        self.assertIsNone(policy.evaluate(239, healthy, {"memoryPercent": 91}))
        self.assertIn("memory", policy.evaluate(240, healthy, {"memoryPercent": 91}))
        self.assertIn("semantic", StopPolicy(0).evaluate(1, {"correctnessFailures": 1}, {}))
        self.assertIn("capacity", StopPolicy(0).evaluate(1, {"capacity429": 1}, {}))

    def test_capacity_429_can_be_measured_but_unstable_cleanup_or_errors_stop_increase(self):
        phase = {"status": "failed", "stopReason": None, "postRequestCleanup": {"status": "passed"}, "client": {"capacity429": 8, "correctnessFailures": 0, "networkOr5xxRate": 0}}
        self.assertIsNone(capacity_stop_reason(phase))
        self.assertIn("cleanup", capacity_stop_reason({**phase, "postRequestCleanup": {"status": "unknown"}}))
        self.assertIn("execution", capacity_stop_reason({**phase, "status": "error"}))
        self.assertIn("semantic", capacity_stop_reason({**phase, "client": {"correctnessFailures": 1}}))
        self.assertIn("network", capacity_stop_reason({**phase, "client": {"networkOr5xxRate": .01}}))

    def test_raw_tail_reads_incrementally_and_waits_for_complete_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            event = {"type": "Point", "metric": "http_req_failed", "data": {"time": datetime.fromtimestamp(1000, timezone.utc).isoformat(), "value": 1, "tags": {"status": "500", "name": "/api/run"}}}
            text = json.dumps(event)
            path.write_text(text[:15])
            tail = RawTail(path)
            self.assertEqual(tail.poll(1000)["windowRequests"], 0)
            with path.open("a") as output:
                output.write(text[15:] + "\n")
            self.assertEqual(tail.poll(1000)["networkOr5xxRate"], 1)
            offset = tail.offset
            self.assertEqual(tail.poll(1000)["httpStatuses"], {"500": 1})
            self.assertEqual(tail.offset, offset)
            self.assertEqual(tail.poll(1061)["windowRequests"], 0)

    def test_recovery_unknown_and_zero_do_not_become_automatic_pass(self):
        self.assertEqual(within_baseline(None, 0), "unknown")
        self.assertEqual(within_baseline(0, 1), "unknown")
        self.assertEqual(within_baseline(0, 1, absolute_zero=True), "failed")
        self.assertEqual(within_baseline(0, 0), "passed")
        self.assertEqual(within_baseline(100, 120), "passed")
        self.assertEqual(within_baseline(100, 121), "failed")
        self.assertEqual(cpu_seconds("01:02.5"), 62.5)
        self.assertEqual(cpu_seconds("1-01:00:00"), 90000)

    def test_growth_detects_staircase_and_resource_window_excludes_warmup(self):
        samples = [{"timestamp": datetime.fromtimestamp(number, timezone.utc).isoformat(), "memoryMb": value, "threads": 2, "walBytes": 0, "logFiles": number, "cpuPercent": value, "handles": 3, "childProcesses": 0} for number, value in enumerate((1, 1, 2, 2, 3))]
        self.assertTrue(growth_report(samples)["metrics"]["memoryMb"]["continuouslyIncreasing"])
        self.assertEqual(stable_resource_window(samples, 1)["memoryMb"], 2.5)
        self.assertIsNone(stable_resource_window([], 1)["cpuPercent"])

    def test_resource_enrichment_clips_interval_and_preserves_unknown_and_original_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.jsonl"
            raw.write_text('{"type":"Metric","metric":"original","data":{"type":"gauge"}}\n')
            original = raw.read_bytes()
            manifest = {"run": {"startedAt": "2026-09-29T00:00:00Z", "endedAt": "2026-09-29T00:00:10Z"}}
            resources = [{"timestamp": timestamp, "cpuPercent": None, "memoryMb": 100, "childProcesses": 0} for timestamp in ("2026-09-28T23:59:59+00:00", "2026-09-29T00:00:01+00:00", "2026-09-29T00:00:11+00:00")]
            enriched_raw(raw, manifest, resources, root / "enriched.jsonl")
            events = [json.loads(line) for line in (root / "enriched.jsonl").read_text().splitlines()]
            points = [event for event in events if event["type"] == "Point"]
            self.assertEqual(len(points), 2)
            self.assertEqual({point["metric"] for point in points}, {"studio_memory_mb", "studio_child_processes"})
            self.assertEqual(raw.read_bytes(), original)

    def test_stub_controls_are_local_fixed_shape_and_bounded(self):
        application = FastAPI()
        @application.get("/{path:path}")
        def fallback(path):
            return {"fallback": True}
        install_stub(application)
        with TestClient(application) as client:
            self.assertEqual(client.get("/__load_test__/health").status_code, 200)
            self.assertEqual(client.put("/__load_test__/control", json={"delayMs": 0, "status": 500}).status_code, 200)
            self.assertEqual(client.get("/__load_test__/health").status_code, 500)
            for payload in (None, [], {"delayMs": True, "status": 200}, {"delayMs": 6000, "status": 200}, {"delayMs": 0, "status": 200.0}, {"delayMs": 0, "status": 200, "url": "https://external.invalid"}):
                response = client.put("/__load_test__/control", json=payload)
                self.assertEqual(response.status_code, 400)
