"""DB-5 correctness and destructive-boundary tests use only temporary storage."""
import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_test.database import RequestContext
from api_test.load_results import _time, _time_text, import_k6_result
from api_test.load_test_benchmark import detailed_fixture
from api_test.load_test_maintenance import (artifacts_apply, artifacts_preview, backup, restore,
    retention_apply, retention_preview, _digest)
from api_test.load_test_store import LoadTestStore, MAX_RESPONSE_BYTES, _json
from api_test.main import app


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "load-tests"


def sample(run_id="old", days=-40):
    value = import_k6_result(FIXTURES / "smoke-summary.json", FIXTURES / "smoke-raw.jsonl")
    value["run"]["id"] = run_id
    for name in ("startedAt", "endedAt"):
        value["run"][name] = _time_text(_time(value["run"][name], name) + timedelta(days=days))
    for point in value["series"]:
        point["bucketAt"] = _time_text(_time(point["bucketAt"], "bucketAt") + timedelta(days=days))
    return value


class LoadTestOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = LoadTestStore(self.root / "studio.db", url="")
        self.env = patch.dict(os.environ, {"STUDIO_DB_PATH": str(self.store.path), "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def role(self, role, workspace="default"):
        with self.store.connection(write=True) as db, db:
            if workspace != "default":
                db.execute("INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) VALUES (?,?,'now','now')", (workspace, workspace))
                db.execute("INSERT OR IGNORE INTO memberships(workspace_id,user_id,role,created_at) VALUES (?,'local-user',?,'now')", (workspace, role))
            else:
                db.execute("UPDATE memberships SET role=? WHERE workspace_id='default' AND user_id='local-user'", (role,))

    def test_retention_ended_age_timezone_workspace_and_reference_integrity(self):
        self.store.import_bundle(sample("old"))
        recent = sample("recent", 0)
        self.store.import_bundle(recent)
        spanning = sample("long-running")
        spanning["run"]["endedAt"] = recent["run"]["endedAt"]
        self.store.import_bundle(spanning)
        self.role("owner", "other")
        other = LoadTestStore(self.store.path, context=RequestContext("other", "local-user"), url="")
        other.import_bundle(sample("other-run"))
        manifest = retention_preview(self.store, now=NOW)
        equivalent = retention_preview(self.store, now=NOW.astimezone(timezone(timedelta(hours=9))))
        self.assertEqual(manifest, equivalent)
        self.assertEqual({row["id"] for row in manifest["runs"]}, {"old"})
        self.assertIsNotNone(self.store.detail("recent")["recommendedBaseline"])
        self.assertEqual(retention_apply(self.store, manifest, confirmation=_digest(manifest))["deletedRuns"], 1)
        self.assertIsNone(self.store.detail("old"))
        self.assertIsNotNone(self.store.detail("long-running"))
        self.assertIsNotNone(other.detail("other-run"))
        self.assertIsNone(self.store.compare("old", "recent"))
        with self.store.connection() as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table in ("load_test_thresholds", "load_test_endpoint_metrics", "load_test_series"):
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table} WHERE run_id='old'").fetchone()[0], 0)

    def test_identical_database_copy_cannot_apply_another_source_preview(self):
        self.store.import_bundle(sample())
        manifest = retention_preview(self.store, now=NOW)
        destination = self.root / "copy.db"
        with closing(sqlite3.connect(self.store.path)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        copied = LoadTestStore(destination, url="")
        self.assertEqual(copied.detail("old"), self.store.detail("old"))
        with self.assertRaisesRegex(ValueError, "different source"):
            retention_apply(copied, manifest, confirmation=_digest(manifest))
        self.assertIsNotNone(copied.detail("old"))
        self.assertIsNotNone(self.store.detail("old"))

    def test_stale_changed_children_new_old_run_and_wrong_confirmation_do_not_delete(self):
        self.store.import_bundle(sample())
        manifest = retention_preview(self.store, now=NOW)
        with self.assertRaisesRegex(ValueError, "Confirmation"):
            retention_apply(self.store, manifest, confirmation="wrong")
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_series SET p95_ms=p95_ms+1 WHERE run_id='old'")
        with self.assertRaisesRegex(ValueError, "stale"):
            retention_apply(self.store, manifest, confirmation=_digest(manifest))
        manifest = retention_preview(self.store, now=NOW)
        self.store.import_bundle(sample("new-old"))
        with self.assertRaisesRegex(ValueError, "stale"):
            retention_apply(self.store, manifest, confirmation=_digest(manifest))
        self.assertEqual(len(self.store.list_runs()["items"]), 2)

    def test_cleanup_child_deletes_roll_back_if_parent_delete_fails(self):
        self.store.import_bundle(sample())
        manifest = retention_preview(self.store, now=NOW)
        with self.store.connection(write=True) as db, db:
            db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON load_test_runs BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            retention_apply(self.store, manifest, confirmation=_digest(manifest))
        self.assertEqual(self.store.detail("old")["thresholds"], sample()["thresholds"])
        self.assertEqual(self.store.series("old")["sourcePoints"], 2)

    def test_operator_roles_inactive_membership_and_cross_workspace_manifest(self):
        self.store.import_bundle(sample())
        manifest = retention_preview(self.store, now=NOW)
        for role in ("editor", "runner", "viewer"):
            self.role(role)
            with self.assertRaises(PermissionError):
                retention_preview(self.store, now=NOW)
            with self.assertRaises(PermissionError):
                retention_apply(self.store, manifest, confirmation=_digest(manifest))
            with self.assertRaises(PermissionError):
                backup(self.store, self.root / (role + ".jsonl"))
            # Test setup restores the role through direct isolated SQL.
            with closing(sqlite3.connect(self.store.path)) as db, db:
                db.execute("UPDATE memberships SET role='owner'")
        self.role("admin")
        self.assertEqual(retention_preview(self.store, now=NOW), manifest)
        other = LoadTestStore(self.store.path, context=RequestContext("other", "local-user"), url="")
        with self.assertRaisesRegex(ValueError, "workspace"):
            retention_apply(other, manifest, confirmation=_digest(manifest))
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("UPDATE memberships SET status='inactive'")
        with self.assertRaises(PermissionError):
            retention_apply(self.store, manifest, confirmation=_digest(manifest))

    def test_backup_restore_checksum_and_no_overwrite(self):
        for value in (sample(), sample("recent", 0)):
            self.store.import_bundle(value)
        archive = self.root / "backup.jsonl"
        footer = backup(self.store, archive)
        self.assertEqual(footer["runs"], 2)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        destination = self.root / "restored.db"
        self.assertEqual(restore(archive, destination)["restoredRuns"], 2)
        restored = LoadTestStore(destination, url="")
        self.assertEqual(restored.detail("recent"), self.store.detail("recent"))
        self.assertEqual(restored.series("old"), self.store.series("old"))
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            restore(archive, destination)
        self.assertEqual(destination.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            backup(self.store, archive)
        archive.write_bytes(archive.read_bytes().replace(b'"rps":0.4', b'"rps":0.5'))
        # Mutate a guaranteed field if the fixture's RPS differs.
        content = archive.read_bytes()
        archive.write_bytes(content.replace(b'"appVersion":"1.0.1"', b'"appVersion":"1.0.2"') if b'"appVersion":"1.0.1"' in content else content.replace(b'"id":"old"', b'"id":"bad"'))
        with self.assertRaisesRegex(ValueError, "checksum"):
            restore(archive, self.root / "corrupt.db")
        self.assertFalse((self.root / "corrupt.db").exists())

    def test_nondefault_workspace_backup_restore_uses_only_explicit_trusted_context(self):
        self.role("owner", "other")
        context = RequestContext("other", "local-user")
        other = LoadTestStore(self.store.path, context=context, url="")
        other.import_bundle(sample("other-run"))
        self.store.import_bundle(sample("local-run"))
        archive = self.root / "other.jsonl"
        backup(other, archive)
        with self.assertRaisesRegex(ValueError, "workspace"):
            restore(archive, self.root / "wrong.db")
        destination = self.root / "other-restored.db"
        restore(archive, destination, context=context)
        restored = LoadTestStore(destination, context=context, url="")
        self.assertEqual(restored.detail("other-run")["summary"], other.detail("other-run")["summary"])
        self.assertIsNone(restored.detail("local-run"))
        with restored.connection() as db:
            self.assertEqual({row[0] for row in db.execute("SELECT id FROM workspaces").fetchall()}, {"default", "other"})
            self.assertEqual(db.execute("SELECT created_by FROM load_test_runs").fetchone()[0], context.user_id)

    def test_changed_archive_between_validation_and_insertion_rolls_back(self):
        self.store.import_bundle(sample())
        first, second = self.root / "first.jsonl", self.root / "second.jsonl"
        backup(self.store, first)
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_runs SET app_version='changed' WHERE id='old'")
        backup(self.store, second)
        from api_test import load_test_maintenance as operations
        real_open = operations._open_destination
        from contextlib import contextmanager
        @contextmanager
        def replace_then_open(path, url):
            first.write_bytes(second.read_bytes())
            with real_open(path, url) as db:
                yield db
        destination = self.root / "race.db"
        with patch.object(operations, "_open_destination", replace_then_open):
            with self.assertRaisesRegex(ValueError, "changed"):
                restore(first, destination)
        with closing(sqlite3.connect(destination)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM load_test_runs").fetchone()[0], 0)

    def test_full_backup_preserves_legacy_large_series(self):
        value = detailed_fixture()
        start = _time(value["run"]["startedAt"], "startedAt")
        value["run"]["endedAt"] = _time_text(start + timedelta(seconds=12000))
        template = value["series"][0]
        value["series"] = [{**template, "bucketAt": _time_text(start + timedelta(seconds=i))} for i in range(12000)]
        self.store.import_bundle(value)
        archive = self.root / "large.jsonl"
        backup(self.store, archive)
        destination = self.root / "large-restored.db"
        restore(archive, destination)
        restored = LoadTestStore(destination, url="")
        self.assertEqual(restored.series("bench-detail", max_points=1000)["sourcePoints"], 12000)
        self.assertEqual(restored.detail("bench-detail")["summary"], value["summary"])

    def artifact(self):
        self.store.import_bundle(sample())
        root = self.root / "artifacts"
        run = root / "old"
        run.mkdir(parents=True)
        (run / "raw.json").write_text("raw fixture")
        (run / "logs").mkdir()
        (run / "logs" / "server.log").write_text("log fixture")
        return root, run

    def test_artifact_exact_preview_apply_and_db_separation(self):
        root, run = self.artifact()
        keep = root / "unregistered"
        keep.mkdir()
        (keep / "raw.json").write_text("keep")
        manifest = artifacts_preview(self.store, root, now=NOW)
        self.assertEqual({v["path"] for v in manifest["files"]}, {"old/raw.json", "old/logs/server.log"})
        result = artifacts_apply(self.store, root, manifest, confirmation=_digest(manifest))
        self.assertEqual(len(result["deletedFiles"]), 2)
        self.assertFalse(run.exists())
        self.assertTrue((keep / "raw.json").exists())
        self.assertIsNotNone(self.store.detail("old"))
        self.assertFalse(list(root.glob(".studio-retention-*")))

    def test_artifact_stale_content_extra_files_and_wrong_root_never_delete(self):
        root, run = self.artifact()
        manifest = artifacts_preview(self.store, root, now=NOW)
        (run / "raw.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "inventory"):
            artifacts_apply(self.store, root, manifest, confirmation=_digest(manifest))
        self.assertTrue((run / "raw.json").exists())
        manifest = artifacts_preview(self.store, root, now=NOW)
        (run / "new.log").write_text("extra")
        with self.assertRaisesRegex(ValueError, "inventory"):
            artifacts_apply(self.store, root, manifest, confirmation=_digest(manifest))
        other = self.root / "wrong-root"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "root"):
            artifacts_apply(self.store, other, manifest, confirmation=_digest(manifest))

    def test_artifact_symlink_traversal_and_directory_replacement_refused(self):
        root, run = self.artifact()
        outside = self.root / "outside.txt"
        outside.write_text("keep")
        (run / "escape").symlink_to(outside)
        with self.assertRaises(ValueError):
            artifacts_preview(self.store, root, now=NOW)
        (run / "escape").unlink()
        alias = self.root / "alias"
        alias.symlink_to(root)
        with self.assertRaisesRegex(ValueError, "symlink"):
            artifacts_preview(self.store, alias, now=NOW)
        manifest = artifacts_preview(self.store, root, now=NOW)
        run.rename(root / "saved")
        run.mkdir()
        (run / "raw.json").write_text("unpreviewed")
        with self.assertRaisesRegex(ValueError, "inventory"):
            artifacts_apply(self.store, root, manifest, confirmation=_digest(manifest))
        self.assertEqual((run / "raw.json").read_text(), "unpreviewed")
        self.assertEqual(outside.read_text(), "keep")
        tampered = copy.deepcopy(manifest)
        tampered["retention"]["runs"][0]["id"] = "../outside"
        with self.assertRaisesRegex(ValueError, "stale"):
            artifacts_apply(self.store, root, tampered, confirmation=_digest(tampered))

    def test_replaced_target_at_quarantine_capture_is_preserved(self):
        root, run = self.artifact()
        manifest = artifacts_preview(self.store, root, now=NOW)
        real_rename = os.rename
        replaced = []
        def race(source, target, **kwargs):
            if source == "old" and not replaced:
                real_rename(run, root / "original")
                run.mkdir()
                (run / "raw.json").write_text("unpreviewed")
                replaced.append(True)
            return real_rename(source, target, **kwargs)
        with patch("api_test.load_test_maintenance.os.rename", side_effect=race):
            with self.assertRaisesRegex(ValueError, "quarantine=.*deletedFiles=\\[\\]"):
                artifacts_apply(self.store, root, manifest, confirmation=_digest(manifest))
        quarantines = list(root.glob(".studio-retention-*"))
        self.assertEqual(len(quarantines), 1)
        self.assertEqual((quarantines[0] / "old/raw.json").read_text(), "unpreviewed")
        self.assertEqual((root / "original/raw.json").read_text(), "raw fixture")
        self.assertEqual(quarantines[0].stat().st_mode & 0o777, 0o700)

    def test_large_series_bounds_sql_rows_preserves_means_nulls_and_p95(self):
        value = detailed_fixture()
        for i, point in enumerate(value["series"]):
            point.update(rps=float(i % 7), activeVus=i % 5, errorRate=float(i % 2),
                         p95Ms=None if i < 11 else float(i), cpuPercent=None if i % 3 else 30.,
                         memoryMb=None, childProcesses=None if i % 2 else 4)
        self.store.import_bundle(value)
        result = self.store.series("bench-detail", max_points=240)
        self.assertLessEqual(len(result["items"]), 240)
        self.assertEqual(result["sourcePoints"], 2500)
        self.assertIsNone(result["items"][0]["p95Ms"])
        self.assertEqual(result["items"][0]["rps"], round(sum(i % 7 / 11 for i in range(11)), 6))
        self.assertTrue(all(p["memoryMb"] is None for p in result["items"]))
        self.assertEqual(max(p["p95Ms"] or 0 for p in result["items"]), 2499.)
        self.assertEqual(self.store.detail("bench-detail")["summary"], value["summary"])
        # Instrument the result transfer: no unbounded raw SELECT * fetchall is
        # allowed to regress as source grows beyond requested chart points.
        from api_test import load_test_store as repository
        real_connect = repository.connect
        returned = []
        class Cursor:
            def __init__(self, cursor, sql): self.cursor, self.sql = cursor, sql
            def fetchall(self):
                rows = self.cursor.fetchall()
                if "load_test_series" in self.sql: returned.append(len(rows))
                return rows
            def __getattr__(self, name): return getattr(self.cursor, name)
        class Connection:
            def __init__(self, db): self.db = db
            def execute(self, sql, params=()): return Cursor(self.db.execute(sql, params), sql)
            def __getattr__(self, name): return getattr(self.db, name)
        with patch.object(repository, "connect", side_effect=lambda *a, **kw: Connection(real_connect(*a, **kw))):
            self.store.series("bench-detail", max_points=17)
        self.assertTrue(returned)
        self.assertLessEqual(max(returned), 17)
        with self.store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_series SET rps=1e308,memory_mb=1e308 WHERE run_id='bench-detail'")
        extreme = self.store.series("bench-detail", max_points=1)["items"][0]
        self.assertAlmostEqual(extreme["rps"] / 1e308, 1.0)
        self.assertAlmostEqual(extreme["memoryMb"] / 1e308, 1.0)

    def test_api_actual_utf8_body_budget_never_truncates_summary_or_endpoints(self):
        value = detailed_fixture()
        value["endpointMetrics"] = [{**copy.deepcopy(value["endpointMetrics"][0]), "endpoint": "/" + "가" * 450 + chr(97 + i // 26 % 26) + chr(97 + i % 26) + chr(97 + i // 676)} for i in range(800)]
        value["summary"]["requests"] = 800
        client = TestClient(app)
        self.assertEqual(client.post("/api/load-tests/runs", json=value).status_code, 201)
        response = client.get("/api/load-tests/runs/bench-detail")
        # 800 long Unicode endpoints push the actual UTF-8 detail over 1 MiB.
        self.assertEqual(response.status_code, 413)
        self.assertLess(len(response.content), MAX_RESPONSE_BYTES)
        self.assertIn("never truncated", response.json()["error"])
        detail = self.store.detail("bench-detail")
        self.assertEqual(detail["summary"], value["summary"])
        self.assertEqual(len(detail["endpointMetrics"]), 800)
        self.assertEqual(client.get("/api/load-tests/runs/bench-detail/series?maxPoints=1000").status_code, 200)
        # Catch compact-estimate vs actual-spaces serialization mismatch.
        default = client.get("/api/load-tests/runs")
        with patch("api_test.implementations.load_tests.MAX_RESPONSE_BYTES", len(default.content)-1):
            self.assertEqual(client.get("/api/load-tests/runs").status_code, 413)
