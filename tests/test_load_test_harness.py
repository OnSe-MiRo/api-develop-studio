"""LT-1 fixtures: deterministic shape, actual revision/projection integrity and isolation."""
import json
import os
import sqlite3
import subprocess
import signal
import tempfile
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from api_test.load_test_harness import HarnessError, generate_fixture, isolated_environment, run_probe, run_workload, verify_fixture, workload_configuration, _stop


class LoadTestHarnessTests(unittest.TestCase):
    def test_small_has_exact_counts_body_sizes_and_immutable_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            result = generate_fixture(root, "small", case_revisions=100)
            self.assertEqual(result["counts"], {"projects": 1, "cases": 10, "pipelines": 2})
            self.assertEqual(result["revisionCount"], 1003)
            self.assertEqual(result["bodyCounts"], {"1024": 4, "10240": 3, "102400": 3})
            from api_test.collaboration_store import CollaborationStore
            with patch.dict(os.environ, {"STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "", "STUDIO_REDIS_URL": ""}):
                store = CollaborationStore(root / "data/studio.db", {"projects": root / "projects", "cases": root / "case", "pipelines": root / "pipelines"})
                store.initialize(import_existing=False)
                case = store.list_references("cases")[0]
                self.assertEqual(len(store.revisions("cases", case)), 100)
                self.assertEqual(store.get("cases", case).revision, 100)
                self.assertEqual(store.get("cases", case).document, json.loads((root / "case" / case).read_text()))
                # Seeded data remains compatible with real optimistic writes and projections.
                document = store.get("cases", case).document
                document["description"] = "modified by storage API"
                stored = store.save("cases", case, document, expected_revision=100)
                self.assertEqual(stored.revision, 101)
                self.assertEqual(json.loads((root / "case" / case).read_text()), document)

    def test_same_seed_produces_same_content_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = generate_fixture(root / "one", "small", seed=42)
            second = generate_fixture(root / "two", "small", seed=42)
            different = generate_fixture(root / "three", "small", seed=43)
            self.assertEqual(first["fixtureSha256"], second["fixtureSha256"])
            self.assertNotEqual(first["fixtureSha256"], different["fixtureSha256"])
            self.assertEqual((root / "one/fixture.json").read_bytes(), (root / "two/fixture.json").read_bytes())

    def test_existing_root_is_rejected_without_touching_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sentinel").write_text("preserve")
            with self.assertRaises(FileExistsError):
                generate_fixture(root, "small")
            self.assertEqual((root / "sentinel").read_text(), "preserve")
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["sentinel"])

    def test_invalid_profile_or_revision_depth_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            for dataset, depth in (("unknown", 1), ("small", 0), ("small", 101)):
                with self.assertRaises(HarnessError):
                    generate_fixture(root, dataset, case_revisions=depth)
                self.assertFalse(root.exists())

    def test_projection_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            generate_fixture(root, "small")
            case = next((root / "case").rglob("*.json"))
            document = json.loads(case.read_text())
            document["request"]["url"] = "/wrong"
            case.write_text(json.dumps(document))
            with self.assertRaisesRegex(HarnessError, "projection differs"):
                verify_fixture(root)

    def test_revision_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            generate_fixture(root, "small")
            with closing(sqlite3.connect(root / "data/studio.db")) as connection, connection:
                connection.execute("UPDATE document_revisions SET content='{}' WHERE document_id=(SELECT id FROM documents WHERE kind='cases' LIMIT 1)")
            with self.assertRaisesRegex(HarnessError, "revision content differs"):
                verify_fixture(root)

    def test_environment_does_not_inherit_external_database_proxy_or_secrets(self):
        with patch.dict(os.environ, {"STUDIO_DB_PATH": "/production/studio.db", "STUDIO_DATABASE_URL": "postgresql://secret",
                                     "STUDIO_DATABASE_URL_FILE": "/private/database-secret", "STUDIO_REDIS_URL": "redis://secret",
                                     "HTTPS_PROXY": "https://proxy", "API_TEST_ENCRYPTION_KEY": "secret", "K6_CLOUD_TOKEN": "secret"}):
            environment = isolated_environment()
        self.assertEqual(environment["STUDIO_DATABASE_URL"], "")
        self.assertEqual(environment["STUDIO_DATABASE_URL_FILE"], "")
        self.assertEqual(environment["STUDIO_REDIS_URL"], "")
        for key in ("STUDIO_DB_PATH", "HTTPS_PROXY", "API_TEST_ENCRYPTION_KEY", "K6_CLOUD_TOKEN"):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["LOCAL_SERVER"], "true")

    def test_workload_defaults_and_short_validation_are_bounded(self):
        self.assertEqual(workload_configuration("smoke")["durationSeconds"], 60)
        self.assertEqual(workload_configuration("smoke")["configuredVus"], 7)
        self.assertEqual(workload_configuration("smoke")["vusPerEndpoint"], 1)
        self.assertEqual(workload_configuration("baseline")["durationSeconds"], 300)
        self.assertEqual(workload_configuration("baseline")["configuredVus"], 5)
        self.assertFalse(workload_configuration("baseline")["validationMode"])
        self.assertTrue(workload_configuration("baseline", 20)["validationMode"])
        self.assertEqual(workload_configuration("baseline", 20)["gracefulStopSeconds"], 10)
        for mode, seconds in (("stress", None), ("smoke", 0), ("smoke", 1), ("smoke", 60), ("smoke", 61), ("baseline", 300), ("baseline", 301), ("baseline", True), ("baseline", 2.5), ("probe", 2)):
            with self.subTest(mode=mode, seconds=seconds), self.assertRaises(HarnessError):
                workload_configuration(mode, seconds)

    def test_invalid_workload_does_not_read_fixture_or_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(HarnessError):
                run_workload(root / "absent-fixture", root / "run", mode="baseline", validation_seconds=301)
            self.assertFalse((root / "run").exists())

    def test_target_plateaus_validation_vus_and_contention_bounds(self):
        config = workload_configuration("target")
        self.assertEqual(config["stageVus"], [20, 50])
        self.assertEqual(config["stageSeconds"], 600)
        self.assertEqual(config["durationSeconds"], 1200)
        self.assertEqual(workload_configuration("target", 40, validation_vus=2)["stageVus"], [1, 2])
        for mode, seconds, concurrency, vus in (("target", 41, 5, None), ("target", None, 5, 2), ("target", 40, 5, 20), ("contention", None, 10, None), ("unique", 5, 5, None)):
            with self.subTest(mode=mode), self.assertRaises(HarnessError):
                workload_configuration(mode, seconds, concurrency, vus)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup")
    def test_cleanup_kills_residual_group_even_when_parent_already_exited(self):
        process = Mock()
        process._isolated_group = True
        process.pid = 12345
        process.poll.return_value = 0
        with patch("api_test.load_test_harness.os.killpg") as group_signal:
            _stop(process)
        self.assertEqual([call.args for call in group_signal.call_args_list], [(12345, signal.SIGTERM), (12345, signal.SIGKILL)])
        process.terminate.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX descendant cleanup")
    def test_cleanup_terminates_child_ignoring_sigterm_after_parent_exits(self):
        child_program = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"
        parent_program = "import subprocess,sys,time\nchild=subprocess.Popen([sys.executable,'-c'," + repr(child_program) + "],stdout=subprocess.PIPE,text=True)\nchild.stdout.readline()\nprint(child.pid,flush=True)\ntime.sleep(60)"
        process = subprocess.Popen([sys.executable, "-c", parent_program], stdout=subprocess.PIPE, text=True, start_new_session=True)
        process._isolated_group = True
        try:
            child_pid = int(process.stdout.readline())
            _stop(process)
            self.assertIsNotNone(process.poll())
            deadline = time.monotonic() + 5
            state = "alive"
            while time.monotonic() < deadline:
                result = subprocess.run(["ps", "-o", "stat=", "-p", str(child_pid)], capture_output=True, text=True, timeout=1)
                state = result.stdout.strip()
                if not state or state.startswith("Z"):
                    break
                time.sleep(0.05)
            self.assertTrue(not state or state.startswith("Z"), "descendant remained alive")
        finally:
            _stop(process)
            process.stdout.close()

    def test_output_inside_fixture_is_rejected_without_creating_or_copying_data(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture"
            generate_fixture(fixture, "small")
            before = sorted(path.relative_to(fixture).as_posix() for path in fixture.rglob("*"))
            original = verify_fixture(fixture)["fixtureSha256"]
            for output in (fixture, fixture / "run", fixture / "runs/deep/run"):
                with self.subTest(output=output), self.assertRaisesRegex(HarnessError, "outside the fixture"):
                    run_workload(fixture, output, mode="baseline")
                self.assertEqual(before, sorted(path.relative_to(fixture).as_posix() for path in fixture.rglob("*")))
            self.assertEqual(verify_fixture(fixture)["fixtureSha256"], original)

    def test_execution_failures_and_threshold_verdict_preserve_record_and_stop_server(self):
        fixtures = Path(__file__).parent / "fixtures/load-tests"
        for failure in ("timeout", "threshold", "integrity"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                generate_fixture(root / "fixture", "small")
                output = root / "run"
                server = Mock()
                server.returncode = None
                server.poll.return_value = None

                def terminate(*_args, **_kwargs):
                    server.returncode = 0
                    server.poll.return_value = 0

                server.terminate.side_effect = terminate
                server.wait.side_effect = terminate
                def start_server(*args, **kwargs):
                    (output / "server-ready.json").write_text('{"baseUrl":"http://127.0.0.1:12345"}')
                    return server
                def execute(command, **kwargs):
                    if command[1] == "version":
                        return subprocess.CompletedProcess(command, 0, stdout="k6 test")
                    if command[0] == "git":
                        return subprocess.CompletedProcess(command, 0, stdout="a" * 40 if command[1] == "rev-parse" else "")
                    if failure == "timeout":
                        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                    manifest = json.loads((fixtures / "smoke-summary.json").read_text())
                    manifest["run"]["status"] = "failed" if failure == "threshold" else "passed"
                    (output / "studio-summary.json").write_text(json.dumps(manifest))
                    (output / "raw.jsonl").write_bytes((fixtures / "smoke-raw.jsonl").read_bytes())
                    if failure == "integrity":
                        next((output / "fixture/case").rglob("*.json")).write_text('{}')
                    return subprocess.CompletedProcess(command, 99 if failure == "threshold" else 0)
                opener = Mock()
                opener.open.return_value.__enter__ = Mock(return_value=Mock(status=200))
                opener.open.return_value.__exit__ = Mock(return_value=False)
                with patch("api_test.load_test_harness.shutil.which", return_value="test-k6"), patch("api_test.load_test_harness.subprocess.Popen", side_effect=start_server), patch("api_test.load_test_harness.subprocess.run", side_effect=execute), patch("urllib.request.build_opener", return_value=opener), patch("api_test.load_test_harness.platform.platform", return_value="test-os"), patch("api_test.load_test_harness.platform.processor", return_value="test-cpu"), patch("api_test.load_test_harness.os.killpg", create=True) as group_signal:
                    if failure == "threshold":
                        result = run_workload(root / "fixture", output, mode="smoke", validation_seconds=3)
                        self.assertEqual(result["status"], "failed")
                        self.assertTrue((output / "bundle.json").exists())
                    else:
                        with self.assertRaises((subprocess.TimeoutExpired, HarnessError)):
                            run_workload(root / "fixture", output, mode="smoke", validation_seconds=3)
                record = json.loads((output / "execution.json").read_text())
                self.assertEqual(record["status"], "failed" if failure == "threshold" else "error")
                self.assertTrue(record["serverStopped"])
                if failure == "integrity":
                    self.assertFalse((output / "bundle.json").exists())
                if os.name == "posix":
                    self.assertEqual([call.args[1] for call in group_signal.call_args_list], [signal.SIGTERM, signal.SIGKILL])
                else:
                    server.terminate.assert_called_once()
                server.wait.assert_called_once()
                self.assertEqual(verify_fixture(root / "fixture")["integrity"], "passed")

    def test_missing_k6_creates_no_execution_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate_fixture(root / "fixture", "small")
            with patch("api_test.load_test_harness.shutil.which", return_value=None):
                with self.assertRaisesRegex(HarnessError, "k6 binary"):
                    run_probe(root / "fixture", root / "run")
            self.assertFalse((root / "run").exists())
