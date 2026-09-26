import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from api_test.load_results import LoadResultError, import_k6_result, normalize_endpoint, validate_bundle


FIXTURES = Path(__file__).parent / "fixtures" / "load-tests"


class LoadResultTests(unittest.TestCase):
    def test_smoke_fixture_matches_hand_calculated_totals_and_buckets(self):
        bundle = import_k6_result(FIXTURES / "smoke-summary.json", FIXTURES / "smoke-raw.jsonl")

        self.assertEqual(bundle["schemaVersion"], 1)
        self.assertEqual(bundle["run"]["status"], "passed")
        self.assertEqual(bundle["summary"]["requests"], 4)
        self.assertEqual(bundle["summary"]["rps"], 0.4)
        self.assertEqual(bundle["summary"]["errorRate"], 0.25)
        self.assertEqual(bundle["summary"]["latencyMs"], {
            "p50": 125.0,
            "p90": 185.0,
            "p95": 192.5,
            "p99": 198.5,
            "max": 200.0,
        })
        self.assertEqual(bundle["summary"]["vusMax"], 2)
        self.assertTrue(bundle["summary"]["thresholdsPassed"])
        self.assertEqual(
            [(item["method"], item["endpoint"], item["requestCount"]) for item in bundle["endpointMetrics"]],
            [("GET", "/api/users/{id}", 2), ("POST", "/api/orders", 2)],
        )
        self.assertEqual(bundle["endpointMetrics"][0]["latencyMs"]["p95"], 145.0)
        self.assertEqual(bundle["endpointMetrics"][1]["errorRate"], 0.5)
        self.assertEqual(len(bundle["series"]), 2)
        self.assertEqual(bundle["series"][0], {
            "bucketAt": "2026-09-26T00:00:00.000Z",
            "rps": 0.4,
            "activeVus": 1,
            "errorRate": 0.0,
            "p95Ms": 97.5,
            "cpuPercent": 50.0,
            "memoryMb": 512.0,
            "childProcesses": 1,
        })
        self.assertEqual(bundle["series"][1]["errorRate"], 0.5)
        self.assertNotIn("PRIVATE", json.dumps(bundle))
        self.assertFalse(bundle["warnings"])

    def test_target_fixture_preserves_failed_threshold_and_manual_percentiles(self):
        bundle = import_k6_result(FIXTURES / "target-summary.json", FIXTURES / "target-raw.jsonl")

        self.assertEqual(bundle["run"]["status"], "failed")
        self.assertEqual(bundle["summary"]["requests"], 6)
        self.assertEqual(bundle["summary"]["rps"], 0.4)
        self.assertEqual(bundle["summary"]["errorRate"], 0.333333)
        self.assertEqual(bundle["summary"]["latencyMs"]["p50"], 350.0)
        self.assertEqual(bundle["summary"]["latencyMs"]["p90"], 550.0)
        self.assertEqual(bundle["summary"]["latencyMs"]["p95"], 575.0)
        self.assertEqual(bundle["summary"]["latencyMs"]["p99"], 595.0)
        self.assertFalse(bundle["summary"]["thresholdsPassed"])
        self.assertEqual(bundle["thresholds"][0]["actualValue"], 575.0)
        self.assertFalse(bundle["thresholds"][0]["passed"])
        self.assertEqual([item["activeVus"] for item in bundle["series"]], [20, 35, 50])
        self.assertEqual(
            {(item["method"], item["endpoint"]): item["requestCount"] for item in bundle["endpointMetrics"]},
            {("GET", "/api/projects"): 3, ("PUT", "/api/cases/{reference}"): 3},
        )

    def test_import_is_deterministic_and_accepts_gzip_raw_output(self):
        first = import_k6_result(FIXTURES / "target-summary.json", FIXTURES / "target-raw.jsonl")
        second = import_k6_result(FIXTURES / "target-summary.json", FIXTURES / "target-raw.jsonl")
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            compressed = Path(directory) / "target-raw.json.gz"
            with gzip.open(compressed, "wt", encoding="utf-8") as handle:
                handle.write((FIXTURES / "target-raw.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(first, import_k6_result(FIXTURES / "target-summary.json", compressed))

    def test_raw_thresholds_determine_status_when_current_summary_has_no_verdicts(self):
        manifest = json.loads((FIXTURES / "target-summary.json").read_text())
        manifest["run"]["status"] = "passed"
        manifest["thresholds"] = []
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            summary.write_text(json.dumps(manifest), encoding="utf-8")
            bundle = import_k6_result(summary, FIXTURES / "target-raw.jsonl")
        self.assertEqual(bundle["run"]["status"], "failed")
        self.assertEqual(bundle["thresholds"][0]["actualValue"], 575.0)
        self.assertFalse(bundle["thresholds"][0]["passed"])

    def test_mismatched_http_metric_counts_are_rejected(self):
        lines = (FIXTURES / "target-raw.jsonl").read_text().splitlines()
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "incomplete.jsonl"
            raw.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(LoadResultError, "sample counts do not match"):
                import_k6_result(FIXTURES / "target-summary.json", raw)

    def test_summary_threshold_must_exist_in_raw_metrics(self):
        manifest = json.loads((FIXTURES / "smoke-summary.json").read_text())
        manifest["thresholds"].append({"metric": "missing_metric", "condition": "rate<1", "passed": True})
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            summary.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(LoadResultError, "threshold metric is missing"):
                import_k6_result(summary, FIXTURES / "smoke-raw.jsonl")

    def test_invalid_inputs_fail_without_echoing_raw_secret_values(self):
        with self.assertRaisesRegex(LoadResultError, "run.scenario"):
            import_k6_result(FIXTURES / "invalid-summary.json", FIXTURES / "smoke-raw.jsonl")
        with self.assertRaises(LoadResultError) as caught:
            import_k6_result(FIXTURES / "smoke-summary.json", FIXTURES / "invalid-raw.jsonl")
        self.assertNotIn("PRIVATE", str(caught.exception))
        with self.assertRaisesRegex(LoadResultError, "bucket seconds"):
            import_k6_result(FIXTURES / "smoke-summary.json", FIXTURES / "smoke-raw.jsonl", 0)

    def test_schema_is_valid_and_rejects_bad_ratio(self):
        schema = json.loads((Path(__file__).parents[1] / "docs" / "load-test-result.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        invalid = json.loads((FIXTURES / "invalid-bundle.json").read_text())
        with self.assertRaisesRegex(LoadResultError, "summary.errorRate"):
            validate_bundle(invalid)
        valid = import_k6_result(FIXTURES / "smoke-summary.json", FIXTURES / "smoke-raw.jsonl")
        valid["futureExtension"] = {"supportedLater": True}
        validate_bundle(valid)

    def test_endpoint_normalization_drops_origin_query_and_dynamic_ids(self):
        self.assertEqual(
            normalize_endpoint({
                "method": "get",
                "url": "https://user:PRIVATE@example.test/api/users/123e4567-e89b-12d3-a456-426614174000?token=PRIVATE",
            }),
            ("GET", "/api/users/{id}"),
        )

    def test_cli_writes_schema_valid_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bundle.json"
            command = [
                sys.executable,
                "-m",
                "api_test.load_results",
                "--summary",
                str(FIXTURES / "smoke-summary.json"),
                "--raw",
                str(FIXTURES / "smoke-raw.jsonl"),
                "--output",
                str(output),
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            validate_bundle(json.loads(output.read_text()))
            first = output.read_bytes()
            repeated = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(first, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
