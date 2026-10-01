"""LT-5 reproducibility and fail-closed evidence consistency."""
import copy
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from api_test.load_test_report import DEFAULT_DIRECTORY, FILENAMES, ReportError, build_report, main, read_inputs, render


class LoadTestReportTests(unittest.TestCase):
    def setUp(self):
        self.inputs, self.hashes = read_inputs(DEFAULT_DIRECTORY)

    def test_baseline_math_and_unknown_capacity_do_not_pool_or_invent_median(self):
        report = build_report(self.inputs, self.hashes)
        baseline = report["readingObservations"]["baseline"]
        self.assertEqual(baseline["requests"], 754)
        self.assertAlmostEqual(baseline["manifestSeconds"], 310.259481)
        self.assertAlmostEqual(baseline["rps"], 2.430224, places=6)
        self.assertEqual(baseline["p95Ms"], 53.183)
        self.assertIsNone(report["maximumStableRps"])
        self.assertIsNone(report["sustainedRunCapacity"])
        self.assertIsNone(report["baselineMedian"])
        self.assertEqual(report["observedAdmissionConcurrency"], 2)

    def test_nonfinite_negative_and_arithmetic_mismatch_are_rejected(self):
        for mutation in (lambda data: data[1]["baseline"]["execution"]["summary"].update(rps=math.nan),
                         lambda data: data[1]["baseline"]["endpointMetrics"][0]["latencyMs"].update(p95=-1),
                         lambda data: data[2]["functionalTarget"]["traffic"].update(totalClassifiedRequests=46),
                         lambda data: data[2]["contention"][0]["traffic"].update(expected409=3)):
            data = copy.deepcopy(self.inputs)
            mutation(data)
            with self.assertRaises(ReportError):
                build_report(data, self.hashes)

    def test_false_pass_and_missing_critical_collections_are_rejected(self):
        for mutation in (lambda data: data[1]["baseline"]["execution"]["summary"].update(thresholdsPassed=False),
                         lambda data: data[1]["baseline"]["execution"]["summary"].update(errorRate=.1),
                         lambda data: data[2].update(contention=[]), lambda data: data[3].update(campaignEvidence=[]),
                         lambda data: data[2]["unique50"].update(status="failed")):
            data = copy.deepcopy(self.inputs)
            mutation(data)
            with self.assertRaises(ReportError):
                build_report(data, self.hashes)

    def test_final_recovered_run_needs_complete_clean_same_server_evidence(self):
        for mutation in (lambda data: data[3]["finalFaultRecovery"].update(serverStopped=False),
                         lambda data: data[3]["finalFaultRecovery"]["executionRecovery"].update(complete=False),
                         lambda data: data[3]["finalFaultRecovery"]["executionRecovery"]["cleanup"].update(status="failed"),
                         lambda data: data[3]["finalFaultRecovery"]["phases"][0].update(serverPid=1)):
            data = copy.deepcopy(self.inputs)
            mutation(data)
            with self.assertRaises(ReportError):
                build_report(data, self.hashes)

    def test_recovery_false_pass_and_pid_mismatch_are_rejected(self):
        data = copy.deepcopy(self.inputs)
        data[3]["campaignEvidence"][0]["recovery"]["comparison"]["p95Ms"]["after"] = 1000
        with self.assertRaises(ReportError):
            build_report(data, self.hashes)
        data = copy.deepcopy(self.inputs)
        data[3]["campaignEvidence"][0]["phases"][0]["serverPid"] = 1
        with self.assertRaises(ReportError):
            build_report(data, self.hashes)

    def test_unexpected_normal5xx_cannot_keep_normal5xx_zero_coverage(self):
        data = copy.deepcopy(self.inputs)
        statuses = data[3]["campaignEvidence"][3]["phases"][0]["client"]["httpStatuses"]
        statuses["200"] -= 1
        statuses["500"] = 1
        with self.assertRaises(ReportError):
            build_report(data, self.hashes)

    def test_fault_http_zero_is_not_business_success(self):
        report = build_report(self.inputs, self.hashes)
        delay = next(item for item in report["faultBusinessErrors"] if item["kind"] == "delay")
        self.assertEqual(delay["httpErrorRate"], 0)
        self.assertEqual(delay["runExitFailures"], 2)
        self.assertIn("HTTP errorRate는 0이지만", render(report))

    def test_determinism_clean_copy_and_check_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, output = root / "evidence", root / "output"
            evidence.mkdir()
            for filename in FILENAMES:
                (evidence / filename).write_bytes((DEFAULT_DIRECTORY / filename).read_bytes())
            arguments = ["--evidence-dir", str(evidence), "--output-dir", str(output)]
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(arguments), 0)
                first = {path.name: path.read_bytes() for path in output.iterdir()}
                self.assertEqual(main(arguments), 0)
                self.assertEqual(first, {path.name: path.read_bytes() for path in output.iterdir()})
                self.assertEqual(main([*arguments, "--check"]), 0)
                report = output / "load-test-baseline-report.md"
                report.write_text("sentinel", encoding="utf-8")
                self.assertEqual(main([*arguments, "--check"]), 1)
                self.assertEqual(report.read_text(encoding="utf-8"), "sentinel")

    def test_original_fingerprint_or_source_hash_mismatch_fails_closed(self):
        for mutation in (lambda data: data[1]["baseline"]["execution"]["postRunIntegrity"].update(fixtureSha256="0" * 64),
                         lambda data: data[1]["baseline"]["execution"]["sourceSha256"].update(**{"source.py": "invalid"})):
            data = copy.deepcopy(self.inputs)
            mutation(data)
            with self.assertRaises(ReportError):
                build_report(data, self.hashes)
