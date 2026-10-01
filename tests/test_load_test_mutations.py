"""LT-3 immutable originals, exact write revisions and pinned runner boundary."""
import io
import json
import os
import tempfile
import sqlite3
from contextlib import closing
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from api_test.collaboration_store import CollaborationStore
from api_test.load_test_harness import REPOSITORY, HarnessError, generate_fixture, verify_fixture, workload_configuration
from api_test.load_test_mutations import RUN_CASE, allowed_run_target, expected_mutations, prepare_runner, run_isolated_case, write_document


class LoadTestMutationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "", "STUDIO_REDIS_URL": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def store(self, root):
        store = CollaborationStore(root / "data/studio.db", {"projects": root / "projects", "cases": root / "case", "pipelines": root / "pipelines"})
        store.initialize(import_existing=False)
        return store

    def test_exact_unique_and_contention_revisions_keep_original_fingerprint(self):
        for mode, steps in (("unique", 4), ("contention", 2)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fixture"
                original = generate_fixture(root, "small")["fixtureSha256"]
                store = self.store(root)
                reference = f"load-test/write/{mode}-vu-1-iteration-0.json"
                for step in range(1, steps + 1):
                    document = write_document("load-test/project-000.json", 20260929, mode, 1, 0, step, 3 if mode == "contention" and step == 2 else 0)
                    store.save("cases", reference, document, expected_revision=step - 1 if step > 1 else None)
                extras = expected_mutations(root, workload_configuration(mode))
                result = verify_fixture(root, extras)
                self.assertEqual(result["fixtureSha256"], original)
                self.assertEqual(store.get("cases", reference).revision, steps)
                self.assertEqual(result["counts"]["cases"], 11)

    def test_wrong_write_content_and_partial_flow_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            generate_fixture(root, "small")
            store = self.store(root)
            reference = "load-test/write/unique-vu-1-iteration-0.json"
            store.save("cases", reference, write_document("load-test/project-000.json", 20260929, "unique", 1, 0, 1))
            with self.assertRaisesRegex(ValueError, "did not complete"):
                expected_mutations(root, workload_configuration("unique"))
            for step in (2, 3, 4):
                store.save("cases", reference, write_document("load-test/project-000.json", 20260929, "unique", 1, 0, 999 if step == 4 else step), expected_revision=step - 1)
            with self.assertRaisesRegex(HarnessError, "mutation revision content"):
                verify_fixture(root, expected_mutations(root, workload_configuration("unique")))

    def test_partial_stopped_flows_are_explicit_and_still_validate_revision_audit(self):
        for kind in ("unique", "contention"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fixture"
                original = generate_fixture(root, "small")["fixtureSha256"]
                store = self.store(root)
                reference = f"load-test/write/{kind}-vu-1-iteration-0.json"
                stored = store.save("cases", reference, write_document("load-test/project-000.json", 20260929, kind, 1, 0, 1))
                with self.assertRaises(ValueError):
                    expected_mutations(root, workload_configuration(kind))
                self.assertEqual(verify_fixture(root, expected_mutations(root, workload_configuration(kind), allow_incomplete=True))["fixtureSha256"], original)
                with closing(sqlite3.connect(root / "data/studio.db")) as connection, connection:
                    connection.execute("UPDATE audit_events SET action='unexpected' WHERE document_id=?", (stored.document_id,))
                with self.assertRaisesRegex(ValueError, "audit events"):
                    expected_mutations(root, workload_configuration(kind), allow_incomplete=True)

    def test_unexpected_new_document_or_original_update_is_rejected(self):
        for original_update in (False, True):
            with self.subTest(original_update=original_update), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "fixture"
                generate_fixture(root, "small")
                store = self.store(root)
                reference = store.list_references("cases")[0] if original_update else "unexpected/api/case.json"
                document = store.get("cases", reference).document if original_update else write_document("load-test/project-000.json", 20260929, "unique", 1, 0, 1)
                document["description"] = "unexpected mutation"
                store.save("cases", reference, document, expected_revision=1 if original_update else None)
                with self.assertRaises(HarnessError):
                    verify_fixture(root, expected_mutations(root, workload_configuration("unique")))

    def test_runner_rejects_tampered_case_url_or_method_without_network_even_if_skip_set(self):
        from api_test import cli
        for url, method in (("https://external.invalid/health", "GET"), ("http://127.0.0.1:1/example-api/health", "GET"), ("/example-api/health", "PUT")):
            with self.subTest(url=url, method=method), tempfile.TemporaryDirectory() as directory:
                root = (Path(directory) / "fixture").resolve()
                generate_fixture(root, "small")
                (root / "tmp").mkdir()
                runtime = prepare_runner(root, "http://127.0.0.1:12345", REPOSITORY)
                path = root / "case" / RUN_CASE
                document = json.loads(path.read_text())
                document["request"].update(url=url, method=method)
                path.write_text(json.dumps(document))
                report = root / "tmp/result.json"
                arguments = [str(root / "run_api_tests.py"), "--case", RUN_CASE, "--report-json", str(report), "--run-id", "run_test_guard"]
                previous = Path.cwd()
                with patch.dict(os.environ, {"SKIP_OWNERSHIP_VERIFICATION": "true", "LOCAL_SERVER": "true"}), patch("sys.argv", arguments), patch.object(cli, "execution_guard"), patch.object(cli, "local_policy"), patch("api_test.runner.execute_http_call") as network, redirect_stdout(io.StringIO()) as output:
                    try:
                        os.chdir(root)
                        self.assertEqual(run_isolated_case(), 2)
                    finally:
                        os.chdir(previous)
                network.assert_not_called()
                self.assertIn("outside the prepared loopback", output.getvalue())
                self.assertTrue(allowed_run_target(runtime, runtime["runProject"], runtime["baseUrl"] + "/example-api/health", "GET"))

    def test_runner_report_cannot_escape_private_temporary_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = (Path(directory) / "fixture").resolve()
            generate_fixture(root, "small")
            prepare_runner(root, "http://127.0.0.1:12345", REPOSITORY)
            previous = Path.cwd()
            with patch("sys.argv", ["runner", "--case", RUN_CASE, "--report-json", str(root.parent / "escape.json"), "--run-id", "run_test"]):
                try:
                    os.chdir(root)
                    with self.assertRaisesRegex(ValueError, "private temporary"):
                        run_isolated_case()
                finally:
                    os.chdir(previous)
            self.assertFalse((root.parent / "escape.json").exists())
