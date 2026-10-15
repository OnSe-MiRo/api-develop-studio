import os
import tempfile
from pathlib import Path
from contextlib import closing
from api_test.database import connect, initialize_local_context
from api_test.migrations import migrate_studio_database
from api_test.request_scope import CurrentUser
"""RUN-2 SDK HTTP submission, private artifact and synchronous ZIP compatibility."""
import io
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api_test.database import LOCAL_CONTEXT, RequestContext
from api_test.jobs import JobManager
from api_test.main import app
from api_test.services import studio


def archive():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as file:
        file.writestr("client/readme.txt", "generated")
    return output.getvalue()


def eventually(predicate, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.01)
    raise AssertionError("SDK job did not complete")


class SDKGenerationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {"STUDIO_DB_PATH":str(self.root/"studio.db"),"STUDIO_DATABASE_URL":"","STUDIO_DATABASE_URL_FILE":"","STUDIO_AUTH_MODE":"local"}))
        with closing(connect(self.root/"studio.db")) as db,db:
            migrate_studio_database(db);initialize_local_context(db)
        self.old_jobs = app.state.jobs
        self.manager = JobManager(workers=1, capacity=2)
        app.state.jobs = self.manager
        self.addCleanup(setattr, app.state, "jobs", self.old_jobs)
        self.addCleanup(self.manager.close)
        self.client = TestClient(app,base_url="http://127.0.0.1:8765")
        self.addCleanup(self.client.close)
        self.project = {"name": "Sample", "base_url": "https://api.example.test",
                        "docs_file": {"name": "spec.json", "document": {
                            "openapi": "3.0.3", "info": {"title": "Original", "version": "1"}, "paths": {}}},
                        "auth_profiles": {"private": "DO-NOT-SNAPSHOT"},
                        "variables": {"secret": {"key": "DO-NOT-SNAPSHOT"}}}
        self.current = Mock(document=self.project, revision=4)
        self.store = Mock(context=LOCAL_CONTEXT)
        self.store.get.return_value = self.current
        self.store_patch = patch.object(studio, "collaboration_store", return_value=self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def test_submit_poll_download_and_legacy_zip_use_same_executor(self):
        zipped = archive()
        def generated(snapshot, studio_module, cancel, *, timeout_seconds=None):
            self.assertNotIn("DO-NOT-SNAPSHOT", str(snapshot))
            if timeout_seconds is not None:
                self.assertEqual(timeout_seconds, 300)
            return {"status": "passed", "exitCode": 0, "result": {"format": "zip"},
                    "generation": {"sourceDigest": snapshot["sourceDigest"]},
                    "_artifact": zipped, "_artifact_filename": "sample-python-client.zip"}
        with patch("api_test.services.sdk_generation.execute_snapshot", side_effect=generated) as execute:
            accepted = self.client.post("/api/generations", json={
                "project": "sample.json", "language": "python", "projectRevision": 4})
            self.assertEqual(accepted.status_code, 202, accepted.text)
            job = accepted.json()
            self.assertEqual(job["kind"], "sdk_generation")
            self.assertEqual(job["generation"]["projectRevision"], 4)
            self.assertFalse(job["generation"]["artifactReady"])
            result = eventually(lambda: (value if (value := self.client.get("/api/runs/" + job["runId"]).json())["status"] == "passed" else None))
            self.assertTrue(result["generation"]["artifactReady"])
            self.assertEqual(result["generation"]["artifact"]["sizeBytes"], len(zipped))
            response = self.client.get("/api/generations/" + job["runId"] + "/artifact")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.content, zipped)
            self.assertEqual(response.headers["content-type"], "application/zip")
            self.assertIn("sample-python-client.zip", response.headers["content-disposition"])
            self.assertEqual(self.manager.downloads, {})
            legacy = self.client.post("/api/generate", json={"project": "sample.json", "language": "python"})
            self.assertEqual(legacy.status_code, 200, legacy.text)
            self.assertEqual(legacy.content, zipped)
            self.assertEqual(execute.call_count, 2)

    def test_revision_source_and_kind_errors_fail_before_java(self):
        with patch("api_test.services.sdk_generation.execute_snapshot") as execute:
            for body in ({"project": "sample.json", "language": "python"},
                         {"project": "sample.json", "language": "python", "projectRevision": 3}):
                response = self.client.post("/api/generations", json=body)
                self.assertEqual(response.status_code, 409, response.text)
            invalid = self.client.post("/api/generations", json={
                "project": "sample.json", "language": "unknown", "projectRevision": 4})
            self.assertEqual(invalid.status_code, 400)
            execute.assert_not_called()
        other = self.manager.submit(lambda job: {"status": "passed"})["runId"]
        eventually(lambda: self.manager.get(other)["status"] == "passed")
        self.assertEqual(self.client.get("/api/generations/" + other + "/artifact").status_code, 404)
        self.assertEqual(self.client.get("/api/generations/missing/artifact").status_code, 404)

    def test_trusted_nonlocal_owner_can_get_and_cancel_same_sdk_job(self):
        owner = RequestContext("workspace-a", "user-a")
        self.store.context = owner
        with closing(connect(self.root/'studio.db')) as db,db:
            db.execute("INSERT INTO workspaces(id,name,created_at) VALUES ('workspace-a','A','now')")
            db.execute("INSERT INTO users(id,display_name,created_at) VALUES ('user-a','A','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('workspace-a','user-a','runner','now')")
        self.enterContext(patch.object(app.state, 'current_user_provider', lambda request: CurrentUser('user-a','workspace-a'), create=True))
        gate = threading.Event()
        started = threading.Event()
        def waiting(job):
            started.set()
            gate.wait(2)
            return {"status": "cancelled"}
        run_id = self.manager.submit(waiting, owner=owner, projects=["sample.json"],
            initial={"kind": "sdk_generation", "generation": {"artifactReady": False}})["runId"]
        self.assertTrue(started.wait(1))
        self.assertEqual(self.client.get("/api/runs/" + run_id).status_code, 200)
        self.assertEqual(self.client.post("/api/runs/" + run_id + "/cancel").status_code, 200)
        gate.set()
        eventually(lambda: self.manager.get(run_id, owner)["status"] == "cancelled")

    def test_queued_snapshot_survives_project_revision_change(self):
        gate = threading.Event()
        started = threading.Event()
        def hold(job):
            started.set()
            gate.wait(2)
            return {"status": "cancelled"}
        blocker = self.manager.submit(hold)["runId"]
        self.assertTrue(started.wait(1))
        observed = []
        def generated(snapshot, studio_module, cancel):
            observed.append(snapshot)
            return {"status": "passed", "generation": {"sourceDigest": snapshot["sourceDigest"]},
                    "_artifact": archive(), "_artifact_filename": "client.zip"}
        with patch("api_test.services.sdk_generation.execute_snapshot", side_effect=generated):
            accepted = self.client.post("/api/generations", json={
                "project": "sample.json", "language": "python", "projectRevision": 4})
            self.assertEqual(accepted.status_code, 202)
            self.project["docs_file"]["document"]["info"]["version"] = "changed-after-submit"
            self.current.revision = 5
            gate.set()
            eventually(lambda: self.manager.get(blocker)["status"] == "cancelled")
            eventually(lambda: self.manager.get(accepted.json()["runId"])["status"] == "passed")
        self.assertEqual(observed[0]["source"]["document"]["info"]["version"], "1")
        self.assertEqual(observed[0]["projectRevision"], 4)

if __name__ == "__main__":
    unittest.main()
