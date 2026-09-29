import copy
import json
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_test.collaboration_store import CollaborationStore
from api_test.database import RequestContext
from api_test.load_results import LoadResultError, import_k6_result
from api_test.load_test_store import DuplicateRunError, LoadTestStore
from api_test.main import app


FIXTURES = Path(__file__).parent / "fixtures" / "load-tests"


def bundle(kind="smoke"):
    return import_k6_result(FIXTURES / f"{kind}-summary.json", FIXTURES / f"{kind}-raw.jsonl")


class LoadTestStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = LoadTestStore(self.root / "studio.db")

    def test_atomic_import_duplicate_and_read_contract(self):
        value = bundle()
        self.assertEqual(self.store.import_bundle(value), {"id": value["run"]["id"]})
        with self.assertRaises(DuplicateRunError):
            self.store.import_bundle(value)
        self.assertEqual(self.store.detail(value["run"]["id"])["summary"], value["summary"])
        self.assertEqual(self.store.detail(value["run"]["id"])["endpointMetrics"], value["endpointMetrics"])
        self.assertEqual(self.store.series(value["run"]["id"], max_points=1)["sourcePoints"], 2)
        self.assertEqual(self.store.series(value["run"]["id"], max_points=1)["items"][0]["p95Ms"], max(p["p95Ms"] for p in value["series"]))
        with closing(sqlite3.connect(self.store.path)) as db, db:
            self.assertEqual(db.execute("SELECT count(*) FROM load_test_runs").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM load_test_series").fetchone()[0], 2)

    def test_child_insert_failure_rolls_back_entire_run(self):
        self.store.initialize()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("CREATE TRIGGER fail_series BEFORE INSERT ON load_test_series BEGIN SELECT RAISE(ABORT, 'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.import_bundle(bundle())
        with closing(sqlite3.connect(self.store.path)) as db, db:
            for table in ("load_test_runs", "load_test_thresholds", "load_test_endpoint_metrics", "load_test_series"):
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_concurrent_duplicate_has_one_winner(self):
        value = bundle()
        def import_once(_):
            try:
                return self.store.import_bundle(value)["id"]
            except DuplicateRunError:
                return "duplicate"
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(import_once, range(2)))
        self.assertCountEqual(outcomes, [value["run"]["id"], "duplicate"])

    def test_invalid_bundle_is_not_partially_written_or_leaked(self):
        for mutation in (
            lambda v: v["summary"].update(errorRate=float("nan")),
            lambda v: v["summary"].update(requests=2**80),
            lambda v: v["summary"].update(requests=10**400),
            lambda v: v["endpointMetrics"][0].update(endpoint="/api/users/123?token=private"),
            lambda v: v.update(warnings=["token=private"]),
            lambda v: v.update(secret="private"),
        ):
            value = bundle()
            mutation(value)
            if value.get("secret"):
                self.store.import_bundle(value)
                self.assertNotIn("private", json.dumps(self.store.detail(value["run"]["id"])))
                continue
            with self.assertRaises(LoadResultError):
                self.store.import_bundle(value)
            self.store.initialize()
            with closing(sqlite3.connect(self.store.path)) as db, db:
                self.assertEqual(db.execute("SELECT count(*) FROM load_test_runs").fetchone()[0], 0)

    def test_keyset_filters_cursor_and_workspace(self):
        value = bundle()
        for index in range(5):
            item = copy.deepcopy(value)
            item["run"]["id"] = f"run-{index}"
            item["run"]["project"] = "a.json" if index % 2 else "b.json"
            self.store.import_bundle(item)
        first = self.store.list_runs(project="a.json", limit=1)
        second = self.store.list_runs(project="a.json", limit=1, cursor=first["nextCursor"])
        self.assertNotEqual(first["items"][0]["run"]["id"], second["items"][0]["run"]["id"])
        self.assertIsNone(second["nextCursor"])
        with self.assertRaises(ValueError):
            self.store.list_runs(project="b.json", cursor=first["nextCursor"])
        with self.assertRaises(ValueError):
            self.store.list_runs(limit=101)
        other = LoadTestStore(self.store.path, context=RequestContext("other", "local-user"))
        with self.store.connection(write=True) as db, db:
            db.execute("INSERT INTO workspaces(id,name,created_at,updated_at) VALUES ('other','Other','now','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('other','local-user','viewer','now')")
        self.assertEqual(other.list_runs()["items"], [])
        self.assertIsNone(other.detail("run-1"))
        with self.assertRaises(PermissionError):
            other.import_bundle(bundle())

    def test_compare_compatible_and_incompatible(self):
        baseline = bundle()
        candidate = bundle("target")
        candidate["run"]["scenario"] = baseline["run"]["scenario"]
        candidate["endpointMetrics"][0]["endpoint"] = "/api/users/{id}"
        candidate["endpointMetrics"][1]["method"] = "POST"
        candidate["endpointMetrics"][1]["endpoint"] = "/api/orders"
        self.store.import_bundle(baseline)
        self.store.import_bundle(candidate)
        result = self.store.compare(baseline["run"]["id"], candidate["run"]["id"])
        self.assertAlmostEqual(result["metrics"]["p95Ms"]["delta"], 382.5)
        self.assertIn("vusMax", result["conditionWarnings"])
        self.assertEqual(result["endpoints"][0]["endpoint"], "/api/orders")
        self.assertAlmostEqual(result["endpoints"][0]["p95Ms"]["delta"], 385.0)
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_runs SET scenario='different' WHERE id=?", (candidate["run"]["id"],))
        with self.assertRaises(ValueError):
            self.store.compare(baseline["run"]["id"], candidate["run"]["id"])

    def test_recommendation_is_candidate_predecessor_with_time_id_and_workspace_order(self):
        def store_run(run_id, minutes, **changes):
            value = bundle()
            value["run"]["id"] = run_id
            shift = timedelta(minutes=minutes)
            for key in ("startedAt", "endedAt"):
                stamp = datetime.fromisoformat(value["run"][key].replace("Z", "+00:00"))
                value["run"][key] = (stamp + shift).isoformat().replace("+00:00", "Z")
            for item in value["series"]:
                stamp = datetime.fromisoformat(item["bucketAt"].replace("Z", "+00:00"))
                item["bucketAt"] = (stamp + shift).isoformat().replace("+00:00", "Z")
            value["run"].update(changes)
            self.store.import_bundle(value)
        store_run("earliest", -10)
        store_run("tie-a", 0)
        store_run("tie-b", 0)
        store_run("tie-c", 0)
        store_run("newer", 10)
        store_run("other-project", -1, project="another.json")
        store_run("other-scenario", -1, scenario="another")
        store_run("other-schema", -1)
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_runs SET schema_version=2 WHERE id='other-schema'")
            db.execute("INSERT INTO workspaces(id,name,created_at,updated_at) VALUES ('other','Other','now','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('other','local-user','editor','now')")
        other = LoadTestStore(self.store.path, context=RequestContext("other", "local-user"))
        remote = bundle()
        remote["run"]["id"] = "workspace-z"
        other.import_bundle(remote)
        self.assertEqual(self.store.detail("tie-b")["recommendedBaseline"]["run"]["id"], "tie-a")
        self.assertEqual(self.store.detail("tie-a")["recommendedBaseline"]["run"]["id"], "earliest")
        self.assertEqual(self.store.detail("newer")["recommendedBaseline"]["run"]["id"], "tie-c")
        self.assertIsNone(self.store.detail("earliest")["recommendedBaseline"])
        self.assertIsNone(other.detail("workspace-z")["recommendedBaseline"])
        self.assertIsNone(other.compare("tie-b", "workspace-z"))

    def test_compare_golden_ratios_zero_missing_and_condition_metadata(self):
        before = bundle()
        after = copy.deepcopy(before)
        after["run"].update(id="candidate", project="different.json", appVersion="2", commitSha="abcdef1234567", status="failed")
        after["run"]["environment"]["memoryMb"] = 4096
        after["summary"].update(rps=before["summary"]["rps"] * 1.2, errorRate=.5, vusMax=4)
        before["summary"]["errorRate"] = .25
        after["summary"]["latencyMs"] = {key: value * 1.2 for key, value in before["summary"]["latencyMs"].items()}
        before["endpointMetrics"][0]["errorRate"] = 0
        after["endpointMetrics"][0]["errorRate"] = .1
        removed = copy.deepcopy(before["endpointMetrics"][0])
        removed.update(method="DELETE", endpoint="/removed")
        before["endpointMetrics"].append(removed)
        before["summary"]["requests"] += removed["requestCount"]
        added = copy.deepcopy(after["endpointMetrics"][0])
        added.update(endpoint="/new")
        after["endpointMetrics"].append(added)
        after["summary"]["requests"] += added["requestCount"]
        self.store.import_bundle(before)
        self.store.import_bundle(after)
        result = self.store.compare(before["run"]["id"], after["run"]["id"])
        self.assertAlmostEqual(result["metrics"]["p95Ms"]["delta"], 38.5)
        self.assertAlmostEqual(result["metrics"]["p95Ms"]["changePercent"], 20)
        self.assertAlmostEqual(result["metrics"]["rps"]["changePercent"], 20)
        self.assertEqual(result["metrics"]["errorRate"], {"baseline": .25, "candidate": .5, "delta": .25, "changePercent": 100})
        self.assertEqual(set(result["conditionWarnings"]), {"project", "environment", "vusMax", "appVersion", "commitSha", "status"})
        by_path = {item["endpoint"]: item for item in result["endpoints"]}
        self.assertIsNone(by_path[before["endpointMetrics"][0]["endpoint"]]["errorRate"]["changePercent"])
        self.assertIsNone(by_path["/new"]["p95Ms"]["delta"])
        self.assertIsNone(by_path["/removed"]["p95Ms"]["delta"])
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_runs SET schema_version=2 WHERE id='candidate'")
        with self.assertRaises(ValueError):
            self.store.compare(before["run"]["id"], "candidate")

    def test_concurrent_document_writes_and_result_imports(self):
        documents = CollaborationStore(self.store.path, {k: self.root / k for k in ("projects", "cases", "pipelines")})
        documents.initialize(False)
        def save(index):
            if index % 2:
                documents.save("projects", f"load-{index}.json", {"name": str(index)})
            else:
                value = bundle()
                value["run"]["id"] = f"concurrent-{index}"
                self.store.import_bundle(value)
        with ThreadPoolExecutor(max_workers=6) as executor:
            list(executor.map(save, range(12)))
        self.assertEqual(len(self.store.list_runs(limit=100)["items"]), 6)
        self.assertEqual(len(documents.list_references("projects")), 6)

    def test_20000_run_query_plan_and_latency(self):
        self.store.initialize()
        started_at = datetime(2026, 9, 26, tzinfo=timezone.utc)
        summary = json.dumps(bundle()["summary"])
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.executemany("""INSERT INTO load_test_runs
                (id,workspace_id,schema_version,project_reference,scenario,status,started_at,ended_at,
                 environment_json,summary_json,warnings_json,created_by) VALUES (?,'default',1,?,'target','passed',?,?, '{}',?,'[]','local-user')""",
                ((f"bulk-{i}", "a.json" if i % 2 else "b.json", (started_at + timedelta(seconds=i)).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "2026-09-27T00:00:00.000Z", summary) for i in range(20000)))
            plan = db.execute("EXPLAIN QUERY PLAN SELECT id FROM load_test_runs WHERE workspace_id=? AND project_reference=? ORDER BY started_at DESC,id DESC LIMIT 21", ("default", "a.json")).fetchall()
        self.assertTrue(any("load_test_runs_project_started" in row[3] for row in plan), plan)
        durations = []
        for _ in range(20):
            started = time.perf_counter()
            self.store.list_runs(project="a.json")
            durations.append((time.perf_counter() - started) * 1000)
        p95 = sorted(durations)[18]
        self.assertLess(p95, 500, f"20,000 metadata list p95={p95:.1f}ms")


class LoadTestApiTests(unittest.TestCase):
    def test_real_asgi_contract_and_error_status(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"STUDIO_DB_PATH": str(Path(directory) / "studio.db"), "STUDIO_DATABASE_URL": ""}):
            client = TestClient(app)
            value = bundle()
            run_id = value["run"]["id"]
            self.assertEqual(client.post("/api/load-tests/runs", json=value).status_code, 201)
            self.assertEqual(client.post("/api/load-tests/runs", json=value).status_code, 409)
            self.assertEqual(client.get("/api/load-tests/runs?limit=0").status_code, 400)
            self.assertEqual(client.get("/api/load-tests/runs/missing").status_code, 404)
            self.assertEqual(client.get(f"/api/load-tests/runs/{run_id}").json()["summary"], value["summary"])
            self.assertEqual(client.get(f"/api/load-tests/runs/{run_id}/series?maxPoints=1").json()["sourcePoints"], 2)
            self.assertEqual(client.get(f"/api/load-tests/compare?baseline={run_id}&candidate={run_id}").status_code, 200)
            self.assertEqual(client.post("/api/load-tests/runs", content=b" " * (4 * 1024 * 1024 + 1)).status_code, 413)
