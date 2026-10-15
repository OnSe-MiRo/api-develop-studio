"""Shared SDK jobs, private ZIP limits and raw OpenAPI source boundaries."""
import json
import io
import os
import tempfile
import threading
import time
import unittest
import zipfile
import yaml
from pathlib import Path
from unittest.mock import patch

from api_test.database import RequestContext
from api_test.jobs import JobError, JobManager
from api_test.sdk_generation import SDKGenerationError, _generator_bundle_copy, _materialize, _package, _preflight, initial_metadata, snapshot_project
from api_test.services import studio


def eventually(predicate, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.01)
    raise AssertionError("job did not reach expected state")


def sdk_task(data: bytes, filename="client.zip"):
    return lambda _: {"status": "passed", "exitCode": 0, "generation": {"sourceDigest": "a" * 64},
                      "_artifact": data, "_artifact_filename": filename}


class SDKGenerationTests(unittest.TestCase):
    def test_snapshot_excludes_project_secrets_and_url_is_not_fetched_at_submit(self):
        document = {"openapi": "3.0.3", "info": {"title": "X", "version": "1"}, "paths": {}}
        project = {"name": "X", "auth_profiles": {"secret": "PRIVATE-SENTINEL"},
                   "variables": {"secret": {"key": "PRIVATE-SENTINEL"}},
                   "docs_file": {"name": "spec.json", "document": document}}
        snapshot = snapshot_project(project, "p.json", 7, "python", studio)
        self.assertEqual(snapshot["source"]["kind"], "file")
        self.assertEqual(snapshot["projectRevision"], 7)
        long = snapshot_project({**project, "name": "a" * 10000}, "p.json", 7, "python", studio)
        self.assertLessEqual(len(long["projectName"]), 120)
        self.assertNotIn("PRIVATE-SENTINEL", json.dumps(snapshot))
        self.assertEqual(len(snapshot["sourceDigest"]), 64)
        project = {"name": "X", "docs_url": "https://issuer.example.test/spec.json"}
        with patch.object(studio, "fetch_openapi_document", side_effect=AssertionError("submit fetched URL")):
            remote = snapshot_project(project, "p.json", 7, "java", studio)
        self.assertIsNone(remote["sourceDigest"])
        self.assertEqual(initial_metadata(remote)["sourceKind"], "url")

    def test_all_local_references_checked_without_flattening_recursive_or_swagger2(self):
        swagger = {"swagger": "2.0", "info": {"title": "Legacy", "version": "1"}, "paths": {
            "/x": {"get": {"responses": {"200": {"description": "OK",
                "schema": {"$ref": "#/definitions/Node"}}}}}},
            "definitions": {"Node": {"type": "object", "properties": {
                "next": {"$ref": "#/definitions/Node"}}}}}
        _preflight(swagger)
        bundle = {"entrypoint": "openapi.yaml", "files": {
            "openapi.yaml": "openapi: 3.0.3\ninfo: {title: X, version: '1'}\npaths: {/x: {$ref: './paths/x.yaml'}}\ncomponents: {schemas: {Node: {$ref: './schemas/node.yaml'}}}\n",
            "paths/x.yaml": "get: {responses: {'200': {description: OK, content: {application/json: {schema: {$ref: '../openapi.yaml#/components/schemas/Node'}}}}}}\n",
            "schemas/node.yaml": "type: object\nproperties: {next: {$ref: './node.yaml'}}\n",
        }}
        _preflight(None, bundle)
        self.assertIn("$ref", bundle["files"]["schemas/node.yaml"])
        for reference in ("https://elsewhere.test/schema", "../outside.yaml", "#/missing"):
            bad = {"openapi": "3.0.3", "info": {"title": "X", "version": "1"},
                   "paths": {}, "components": {"schemas": {"X": {"$ref": reference}}}}
            with self.subTest(reference=reference), self.assertRaises(SDKGenerationError):
                _preflight(bad)

    def test_remote_source_materializes_once_inside_worker_and_is_preflighted(self):
        doc = {"openapi": "3.0.3", "info": {"title": "X", "version": "1"}, "paths": {}}
        snapshot = {"source": {"kind": "url", "url": "https://example.test/spec", "no_proxy": True}}
        with tempfile.TemporaryDirectory() as directory, patch("api_test.sdk_generation._fetch_url_once", return_value=doc) as fetch:
            root = Path(directory)
            path, source, fetched_at = _materialize(snapshot, root, studio, threading.Event())
            self.assertEqual(source["kind"], "file")
            self.assertEqual(json.loads(path.read_text()), doc)
            self.assertIsNotNone(fetched_at)
            fetch.assert_called_once_with("https://example.test/spec", True, studio)

    def test_empty_generator_output_cannot_be_disguised_by_original_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source", root / "client"
            source.mkdir()
            output.mkdir()
            (source / "openapi.json").write_text("{}")
            with self.assertRaises(SDKGenerationError):
                _package(output, source, {"projectName": "Example", "language": "python"},
                         "file", threading.Event(), studio, time.monotonic() + 1)
            self.assertEqual(list(output.iterdir()), [])

    def test_inline_zip_keeps_legacy_openapi_yaml_semantics_for_swagger2_and_3(self):
        for version_key, version_value in (("swagger", "2.0"), ("openapi", "3.0.3")):
            document = {version_key: version_value, "info": {"title": "X", "version": "1"},
                        "paths": {}, "x-false": False, "x-zero": 0}
            with self.subTest(version=version_value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, output = root / "source", root / "client"
                source.mkdir(); output.mkdir()
                (source / "openapi.json").write_text(json.dumps(document))
                (output / "client.py").write_text("generated")
                data, filename = _package(output, source, {"projectName": "X", "language": "python"},
                                          "file", threading.Event(), studio, time.monotonic() + 2)
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    sources = [name for name in archive.namelist() if name.endswith("/openapi.yaml")]
                    self.assertEqual(len(sources), 1)
                    self.assertEqual(yaml.safe_load(archive.read(sources[0])), document)
                    self.assertFalse(any(name.endswith("/openapi.json") for name in archive.namelist()))
                self.assertEqual(filename, "x-python-client.zip")

    @unittest.skipUnless(os.name == "posix", "symlink fixture uses POSIX")
    def test_symlink_output_root_is_rejected_before_any_external_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, outside = root / "work", root / "outside"
            work.mkdir(); outside.mkdir()
            source = work / "source"
            source.mkdir()
            (source / "openapi.json").write_text('{"openapi":"3.0.3"}')
            (outside / "client.py").write_text("generated")
            sentinel = outside / "openapi.json"
            sentinel.write_text("ORIGINAL")
            (work / "client").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SDKGenerationError):
                _package(work / "client", source, {"projectName": "Example", "language": "python"},
                         "file", threading.Event(), studio, time.monotonic() + 1)
            self.assertEqual(sentinel.read_text(), "ORIGINAL")

    def test_windows_style_escape_member_is_rejected_before_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source", root / "client"
            source.mkdir(); output.mkdir()
            (source / "openapi.json").write_text("{}")
            (output / (".." + chr(92) + ".." + chr(92) + "escape.txt")).write_text("generated")
            with self.assertRaises(SDKGenerationError):
                _package(output, source, {"projectName": "Example", "language": "python"},
                         "file", threading.Event(), studio, time.monotonic() + 1)

    def test_bundle_source_windows_unsafe_name_is_rejected_before_archive(self):
        bundle = {"entrypoint": "openapi.yaml", "files": {
            "openapi.yaml": "openapi: 3.0.3\ninfo: {title: X, version: '1'}\npaths: {}\n",
            "models/a:b.yaml": "type: string\n",
        }}
        with self.assertRaises(SDKGenerationError):
            _preflight(None, bundle)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source, output = root / "source", root / "client"
            source.mkdir(); output.mkdir()
            (output / "client.py").write_text("generated")
            with self.assertRaises(SDKGenerationError):
                _package(output, source, {"projectName": "X", "language": "python", "source": bundle},
                         "bundle", threading.Event(), studio, time.monotonic() + 1)

    def test_generator_only_copy_normalizes_external_self_root_without_changing_raw_bundle(self):
        files = {"openapi.yaml": "openapi: 3.0.3\ninfo: {title: X, version: '1'}\npaths: {}\n",
                 "schemas/node.yaml": "# Original comment\ntype: object\nproperties: {next: {$ref: '#'}}\n"}
        snapshot = {"source": {"kind": "bundle", "entrypoint": "openapi.yaml", "files": files}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, normalized = root / "source", root / "generator-source"
            original.mkdir()
            for name, content in files.items():
                path = original / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            entry = _generator_bundle_copy(snapshot, original, normalized, studio)
            self.assertEqual(entry, normalized / "openapi.yaml")
            self.assertEqual((original / "schemas/node.yaml").read_text(), files["schemas/node.yaml"])
            parsed = studio.parse_bundle_file("schemas/node.yaml", (normalized / "schemas/node.yaml").read_text())
            self.assertEqual(parsed["properties"]["next"]["$ref"], "./node.yaml")
            self.assertEqual((normalized / "openapi.yaml").read_text(), files["openapi.yaml"])

    def test_artifact_owner_kind_quota_inflight_expiry_and_shutdown(self):
        owner = RequestContext("w", "u")
        other = RequestContext("w", "other")
        manager = JobManager(workers=1, retention=.15, artifact_limit=9, artifact_total=10)
        self.addCleanup(manager.close)
        initial = {"kind": "sdk_generation", "generation": {"artifactReady": False, "artifact": None}}
        first = manager.submit(sdk_task(b"first-1"), owner=owner, projects=["p"], initial=initial)["runId"]
        eventually(lambda: manager.get(first, owner)["status"] == "passed")
        self.assertTrue(manager.get(first, owner)["generation"]["artifactReady"])
        with self.assertRaises(JobError) as denied:
            manager.artifact(first, other)
        self.assertEqual(denied.exception.status_code, 404)
        data, filename, lease = manager.artifact(first, owner)
        self.assertEqual((data, filename), (b"first-1", "client.zip"))
        manager.release_artifact(lease)
        second = manager.submit(sdk_task(b"second2"), owner=owner, projects=["p"], initial=initial)["runId"]
        eventually(lambda: manager.get(second, owner)["status"] == "passed")
        self.assertFalse(manager.get(first, owner)["generation"]["artifactReady"])
        with self.assertRaises(JobError) as expired:
            manager.artifact(first, owner)
        self.assertEqual(expired.exception.status_code, 404)
        manager.artifact_total = 100  # Isolate the four-download count gate after the cache-quota assertion.
        leases = [manager.artifact(second, owner)[2] for _ in range(4)]
        with self.assertRaises(JobError) as busy:
            manager.artifact(second, owner)
        self.assertEqual(busy.exception.status_code, 429)
        for key in leases:
            manager.release_artifact(key)
        manager.close()
        self.assertFalse(manager.get(second, owner)["generation"]["artifactReady"])

    def test_expired_artifact_bytes_are_cleared_even_while_worker_idles(self):
        owner = RequestContext("w", "u")
        manager = JobManager(workers=1, retention=.2)
        self.addCleanup(manager.close)
        run_id = manager.submit(sdk_task(b"private-zip"), owner=owner,
            initial={"kind": "sdk_generation", "generation": {"artifactReady": False}})["runId"]
        eventually(lambda: manager.get(run_id, owner)["status"] == "passed")
        old = manager.jobs[run_id]
        time.sleep(.25)
        with self.assertRaises(JobError):
            manager.get(run_id, owner)
        self.assertIsNone(old.artifact)
        self.assertIsNone(old.artifact_filename)
        self.assertFalse(old.data["generation"]["artifactReady"])
        import sys
        worker_frame = sys._current_frames()[manager.threads[0].ident]
        self.assertIsNone(worker_frame.f_locals.get("artifact"))
        self.assertIsNone(worker_frame.f_locals.get("job"))

    def test_queued_cancel_never_invokes_sdk_task(self):
        manager = JobManager(workers=1, capacity=2)
        self.addCleanup(manager.close)
        gate = threading.Event()
        started = threading.Event()
        def hold(job):
            started.set()
            while not gate.is_set() and not job.cancel.is_set():
                time.sleep(.01)
            return {"status": "cancelled"}
        first = manager.submit(hold)["runId"]
        self.assertTrue(started.wait(1))
        called = []
        pending = manager.submit(lambda job: called.append(job.id) or {"status": "passed"},
                                 initial={"kind": "sdk_generation", "generation": {"artifactReady": False}})["runId"]
        self.assertEqual(manager.cancel(pending)["status"], "cancelled")
        gate.set()
        eventually(lambda: manager.get(first)["status"] == "cancelled")
        self.assertEqual(called, [])
        with self.assertRaises(JobError) as incomplete:
            manager.artifact(pending)
        self.assertEqual(incomplete.exception.status_code, 409)

if __name__ == "__main__":
    unittest.main()
