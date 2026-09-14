"""HTTP-level regression matrix for the FND-3 transport migration."""
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from fastapi.testclient import TestClient

import react_server as studio
from api_test.collaboration_store import CollaborationStore


class AsgiContractTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        roots = {"projects": self.root / "projects", "cases": self.root / "case", "pipelines": self.root / "pipelines"}
        for path in roots.values():
            path.mkdir()
        for name, value in {"ROOT": self.root, "PROJECT_ROOT": roots["projects"], "CASE_ROOT": roots["cases"],
                            "PIPELINE_ROOT": roots["pipelines"], "WEB_DIST": self.root / "web"}.items():
            self.enterContext(patch.object(studio, name, value))
        self.enterContext(patch.dict(os.environ, {
            "STUDIO_DB_PATH": str(self.root / "studio.db"),
            "STUDIO_OWNERSHIP_DB_PATH": str(self.root / "ownership.db"),
            "LOCAL_SERVER": "false", "SKIP_OWNERSHIP_VERIFICATION": "false", "EXAMPLE_PROJECT": "true",
        }))
        self.store = CollaborationStore(self.root / "studio.db", roots)
        self.store.initialize()
        self.enterContext(patch.object(studio, "collaboration_store", return_value=self.store))
        self.client = self.enterContext(TestClient(studio.app, base_url="http://127.0.0.1:8765"))
        self.project = {"name": "Contract", "base_url": "https://example.test"}
        self.assertEqual(self.client.put("/api/projects/p.json", json=self.project).status_code, 200)

    def test_nested_and_encoded_case_crud_and_revision_precedence(self):
        reference = "팀/users/get.json"
        path = "/api/cases/" + quote(reference, safe="")
        document = {"project": "p.json", "request": {"url": "/users"}, "expected": {"status": 200, "body": {"score": 9.0}}}
        created = self.client.put(path, json=document)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["path"], "case/" + reference)
        read = self.client.get(path)
        self.assertEqual(read.status_code, 200)
        self.assertIn("9.0", read.json()["_expectedBodyRaw"])
        revisions = self.client.get(path + "/revisions")
        self.assertEqual(revisions.status_code, 200)
        self.assertEqual(len(revisions.json()["items"]), 1)
        self.assertEqual(self.client.get("/api/cases/" + quote(reference, safe="/")).json(), read.json())
        missing_revision = self.client.put(path, json=document)
        self.assertEqual(missing_revision.status_code, 409)
        self.assertEqual(missing_revision.json()["currentRevision"], 1)
        updated = self.client.put(path, json={**document, "name": "updated", "_storage": created.json()["_storage"]})
        self.assertEqual(updated.json()["_storage"]["revision"], 2)
        stale = self.client.put(path, json={**document, "_storage": created.json()["_storage"]})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["currentRevision"], 2)
        self.assertEqual(self.client.delete(path).json()["deleted"], "case/" + reference)
        self.assertEqual(self.client.get(path).status_code, 400)

    def test_lists_filters_pipeline_revision_and_project_delete_rules(self):
        case = {"project": "p.json", "request": {}, "expected": {"status": 200}}
        self.assertEqual(self.client.put("/api/cases/tag/api/a.json", json=case).status_code, 200)
        self.assertEqual(self.client.put("/api/pipelines/a.json", json={"project": "p.json", "steps": []}).status_code, 200)
        for kind in ("projects", "cases", "pipelines"):
            response = self.client.get("/api/" + kind + "?project=p.json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(len(self.client.get("/api/pipelines/a.json/revisions").json()["items"]), 1)
        self.assertEqual(len(self.client.get("/api/projects/p.json/revisions").json()["items"]), 1)
        self.assertEqual(self.client.delete("/api/projects/p.json").status_code, 400)
        self.client.delete("/api/cases/tag/api/a.json")
        self.assertEqual(self.client.delete("/api/projects/p.json").json()["deleted_pipelines"], ["a.json"])
        self.assertEqual(self.client.get("/api/pipelines").json()["items"], [])

    def test_invalid_json_has_legacy_400_and_no_store(self):
        for path in ("/api/docs", "/api/run", "/api/request", "/example-api/users"):
            for body, message in ((b'{', "Invalid request JSON"), (b'\xff', "Invalid request JSON"),
                                  (b'[]', "Request body must be a JSON object"), (b'', "Invalid request JSON")):
                with self.subTest(path=path, body=body):
                    response = self.client.post(path, content=body)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json(), {"error": message})
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertEqual(response.headers["content-type"], "application/json; charset=utf-8")
                    self.assertEqual(int(response.headers["content-length"]), len(response.content))

    def test_trailing_collection_slashes_and_bare_policy_endpoints(self):
        for path in ("/api/projects", "/api/cases", "/api/pipelines", "/api/dashboard"):
            self.assertEqual(self.client.get(path + "/").json(), self.client.get(path).json())
        self.assertEqual(self.client.get("/example-api").status_code, 404)
        self.assertEqual(self.client.post("/api/ownership", json={}).status_code, 403)

    def test_unknown_mutations_keep_errors(self):
        for method, error in (("POST", "Unknown run endpoint"), ("PUT", "Unknown save endpoint"), ("DELETE", "Unknown delete endpoint")):
            response = self.client.request(method, "/api/unknown", json={})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"error": error})

    def test_raw_upload_and_size_limits_do_not_create_invalid_files(self):
        reference = "tag/users/files/body.bin"
        response = self.client.post("/api/uploads/" + quote(reference, safe=""), content=b'\x00\xffraw')
        self.assertEqual(response.json(), {"path": reference})
        self.assertEqual((studio.CASE_ROOT / reference).read_bytes(), b'\x00\xffraw')
        with patch.object(studio, "MAX_UPLOAD_BYTES", 4):
            for content in (b'', b'12345', iter([b'12', b'345'])):
                response = self.client.post("/api/uploads/tag/users/files/invalid.bin", content=content)
                self.assertEqual(response.status_code, 400)
                self.assertFalse((studio.CASE_ROOT / "tag/users/files/invalid.bin").exists())
        traversal = self.client.post("/api/uploads/..%2Foutside.bin", content=b'x')
        self.assertEqual(traversal.status_code, 400)
        self.assertFalse((self.root / "outside.bin").exists())

    def test_ownership_cookie_roundtrip_and_origin_gate(self):
        response = self.client.get("/api/ownership?project=p.json")
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"]
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertEqual(len(self.client.cookies.get("studio_ownership")), 43)
        self.assertNotIn("set-cookie", self.client.get("/api/ownership?project=p.json").headers)
        response = self.client.post("/api/ownership/issue?project=p.json", json={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "OWNERSHIP_POLICY_DENIED")
        with patch.object(studio.OwnershipStore, "issue", return_value={"verification_id": "fixture"}) as issue:
            response = self.client.post("/api/ownership/issue?project=p.json", json={"url": "https://example.test"},
                                        headers={"Origin": "http://127.0.0.1:8765"})
        self.assertEqual(response.json(), {"verification_id": "fixture"})
        self.assertEqual(issue.call_args.args[-1], self.client.cookies.get("studio_ownership"))

    def test_origin_denial_status_depends_on_legacy_method(self):
        for method in ("GET", "PUT", "DELETE", "POST"):
            response = self.client.request(method, "/api/projects/p.json", json={}, headers={"Origin": "https://other.test"})
            self.assertEqual(response.status_code, 403 if method == "POST" else 400)
            self.assertEqual("code" in response.json(), method == "POST")

    def test_zip_response_preserves_artifact_bytes_and_headers(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("README.md", "contract")
        with patch.object(studio, "project_openapi_document", return_value={}), patch.object(
            studio, "generate_openapi_archive", return_value=(buffer.getvalue(), "contract-python.zip")
        ):
            response = self.client.post("/api/generate", json={"project": "p.json", "language": "python"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, buffer.getvalue())
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="contract-python.zip"')
        self.assertEqual(int(response.headers["content-length"]), len(response.content))

    def test_execution_timeout_and_network_errors_keep_status(self):
        timeout = subprocess.TimeoutExpired(["runner"], 300)
        with patch.object(studio.subprocess, "run", side_effect=timeout):
            response = self.client.post("/api/run", json={"inlineCase": {"request": {}, "expected": {"status": 200}}})
        self.assertEqual(response.status_code, 504)
        self.assertIn("runId", response.json())
        self.assertEqual(studio.execution_history().dashboard()["summary"]["total"], 1)
        for status in (502, 504):
            with patch.object(studio, "handle_api_request", side_effect=studio.ApiError("network failure", status)):
                response = self.client.post("/api/request", json={})
            self.assertEqual(response.status_code, status)
        with patch.object(studio, "generate_openapi_archive", side_effect=timeout), patch.object(studio, "project_openapi_document", return_value={}):
            response = self.client.post("/api/generate", json={"project": "p.json", "language": "python"})
        self.assertEqual(response.status_code, 504)
        self.assertIn("OpenAPI", response.json()["error"])

    def test_example_readonly_and_public_fixture(self):
        example = "example-api.json"
        self.store.save("projects", example, {**self.project, "variables": {"plain": {}, "secret": {}}})
        case = {"project": example, "request": {}, "expected": {"status": 200}}
        self.store.save("cases", "example/users/get.json", case)
        self.store.save("pipelines", "example.json", {"project": example, "steps": []})
        for path, body in (("/api/projects/" + example, self.project), ("/api/cases/example/users/get.json", case),
                           ("/api/pipelines/example.json", {"project": example, "steps": []})):
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.client.put(path, json=body).status_code, 400)
            self.assertEqual(self.client.delete(path).status_code, 400)
        self.assertEqual(self.client.post("/api/projects/example-api.json/openapi/operations", json={}).status_code, 400)
        self.assertEqual(self.client.get("/example-api/secure-data").status_code, 401)
        self.assertEqual(self.client.get("/example-api/secure-data", headers={"X-API-Key": studio.EXAMPLE_API_KEY}).status_code, 200)
        self.assertEqual(self.client.post("/example-api/users", json={"name": "Ada"}).status_code, 201)
        with patch.dict(os.environ, {"EXAMPLE_PROJECT": "false"}):
            self.assertEqual(self.client.get("/example-api/health").status_code, 404)
            self.assertNotIn(example, self.client.get("/api/projects").json()["items"])

    def test_spa_fallback_assets_and_missing_build(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 404)
        studio.WEB_DIST.mkdir()
        (studio.WEB_DIST / "index.html").write_text("<html>Studio</html>")
        (studio.WEB_DIST / "app.js").write_text("console.log('studio')")
        for path in ("/", "/dashboard", "/docs", "/api/unknown", "/missing.js", "/..%2Fprojects/p.json"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "<html>Studio</html>")
        self.assertEqual(self.client.get("/app.js").text, "console.log('studio')")

    def test_long_execution_does_not_block_asgi_event_loop(self):
        started, release = threading.Event(), threading.Event()
        def execute(_body):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test did not release worker")
            return {"status": 200}
        with patch.object(studio, "handle_api_request", side_effect=execute), ThreadPoolExecutor() as executor:
            future = executor.submit(self.client.post, "/api/request", json={})
            try:
                self.assertTrue(started.wait(2))
                health = executor.submit(self.client.get, "/example-api/health")
                self.assertEqual(health.result(timeout=2).status_code, 200)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=2).status_code, 200)

    def test_openapi_exposes_registered_business_routes(self):
        schema = self.client.get("/api/schema.json").json()
        for path in ("/api/cases/{reference}/revisions", "/api/cases/{reference}", "/api/run", "/api/uploads/{reference}"):
            self.assertIn(path, schema["paths"])
        parameter = schema["paths"]["/api/cases/{reference}"]["get"]["parameters"][0]
        self.assertEqual(parameter["name"], "reference")
        self.assertTrue(parameter["required"])
