"""Validated, workspace-scoped load-test result persistence and bounded reads."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from api_test.database import LOCAL_CONTEXT, RequestContext, connect, initialize_local_context, require_membership
from api_test.load_results import LoadResultError, THRESHOLD, _public_metric, _time, _time_text, normalize_endpoint, validate_bundle
from api_test.migrations import migrate_studio_database


MAX_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_SERIES_POINTS = 1000
MAX_RESPONSE_BYTES = 1024 * 1024


class DuplicateRunError(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _normalize(bundle):
    """Copy only approved fields; schema permits future fields but storage does not."""
    validate_bundle(bundle)
    run = bundle["run"]
    environment = run["environment"]
    canonical = {
        "schemaVersion": 1,
        "run": {key: run[key] for key in ("id", "project", "scenario", "status", "appVersion", "commitSha")},
        "summary": {key: bundle["summary"][key] for key in ("requests", "rps", "errorRate", "vusMax", "thresholdsPassed")},
        "thresholds": [{key: item[key] for key in ("metric", "condition", "actualValue", "passed")} for item in bundle["thresholds"]],
        "endpointMetrics": [{key: item[key] for key in ("method", "endpoint", "requestCount", "errorRate", "latencyMs")} for item in bundle["endpointMetrics"]],
        "series": [{key: item[key] for key in ("bucketAt", "rps", "activeVus", "errorRate", "p95Ms", "cpuPercent", "memoryMb", "childProcesses")} for item in bundle["series"]],
        "warnings": list(bundle.get("warnings", [])),
    }
    canonical["run"]["startedAt"] = _time_text(_time(run["startedAt"], "run.startedAt"))
    canonical["run"]["endedAt"] = _time_text(_time(run["endedAt"], "run.endedAt"))
    canonical["run"]["environment"] = {key: environment.get(key) for key in ("os", "cpu", "memoryMb", "executionMode", "k6Version")}
    canonical["summary"]["latencyMs"] = {key: bundle["summary"]["latencyMs"][key] for key in ("p50", "p90", "p95", "p99", "max")}
    for item in canonical["endpointMetrics"]:
        method, endpoint = normalize_endpoint({"method": item["method"], "name": item["endpoint"]})
        if (method, endpoint) != (item["method"], item["endpoint"]):
            raise LoadResultError("result bundle endpoint is not normalized")
        item["latencyMs"] = {key: item["latencyMs"][key] for key in ("p50", "p90", "p95", "p99", "max")}
    for item in canonical["series"]:
        item["bucketAt"] = _time_text(_time(item["bucketAt"], "series.bucketAt"))
    validate_bundle(canonical)
    for item in canonical["thresholds"]:
        if item["metric"] != _public_metric(item["metric"]) or not (THRESHOLD.fullmatch(item["condition"]) or item["condition"] == "unsupported"):
            raise LoadResultError("result bundle threshold is not normalized")
    for value in (canonical["summary"]["requests"], canonical["summary"]["vusMax"],
                  *(item["requestCount"] for item in canonical["endpointMetrics"]),
                  *(item["activeVus"] for item in canonical["series"]),
                  *(item["childProcesses"] for item in canonical["series"] if item["childProcesses"] is not None)):
        if value > 2**63 - 1:
            raise LoadResultError("result bundle integer exceeds the database range")
    allowed_warnings = {prefix + item["metric"] for item in canonical["thresholds"] for prefix in (
        "k6 threshold verdict differs from raw aggregate for ", "unsupported threshold expression for ")}
    for warning in canonical["warnings"]:
        if warning not in allowed_warnings:
            raise LoadResultError("result bundle warning is unsupported")
    return canonical


def _cursor_encode(started_at, run_id, fingerprint):
    content = _json([started_at, run_id, fingerprint]).encode()
    return base64.urlsafe_b64encode(content).rstrip(b"=").decode()


def _cursor_decode(value, fingerprint):
    try:
        if len(value) > 1024:
            raise ValueError
        content = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(content)
        if not isinstance(decoded, list) or len(decoded) != 3 or decoded[2] != fingerprint:
            raise ValueError
        if not all(isinstance(part, str) for part in decoded):
            raise ValueError
        return decoded[0], decoded[1]
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Invalid cursor") from exc


class LoadTestStore:
    def __init__(self, path: Path, *, context: RequestContext = LOCAL_CONTEXT, url: str | None = None):
        self.path = path
        self.context = context
        self.url = url
        self._initialized = False
        self._initialize_lock = threading.Lock()

    def initialize(self):
        with self._initialize_lock:
            if self._initialized:
                return
            db = connect(self.path, url=self.url)
            try:
                migrate_studio_database(db)
                with db:
                    initialize_local_context(db)
            finally:
                db.close()
            self._initialized = True

    @contextmanager
    def connection(self, *, write=False, snapshot=False):
        self.initialize()
        db = connect(self.path, url=self.url)
        try:
            require_membership(db, self.context, write=write)
            db.commit()
            if snapshot:
                db.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY" if getattr(db, "dialect", "") == "postgresql" else "BEGIN")
            yield db
        finally:
            db.close()

    def import_bundle(self, bundle):
        normalized = _normalize(bundle)
        if len(_json(normalized).encode()) > MAX_BUNDLE_BYTES:
            raise LoadResultError("result bundle exceeds the size limit")
        run = normalized["run"]
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._insert_bundle(db, normalized)
        return {"id": run["id"]}

    def _insert_bundle(self, db, normalized):
        """Insert into the caller-owned transaction (import or isolated restore)."""
        run = normalized["run"]
        if db.execute("SELECT 1 FROM load_test_runs WHERE id=?", (run["id"],)).fetchone():
            raise DuplicateRunError("Run ID already exists")
        try:
            db.execute("""INSERT INTO load_test_runs
                (id,workspace_id,schema_version,project_reference,scenario,status,started_at,ended_at,
                 app_version,commit_sha,environment_json,summary_json,warnings_json,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run["id"], self.context.workspace_id, 1, run["project"], run["scenario"],
                 run["status"], run["startedAt"], run["endedAt"], run["appVersion"],
                 run["commitSha"], _json(run["environment"]), _json(normalized["summary"]),
                 _json(normalized["warnings"]), self.context.user_id))
        except sqlite3.IntegrityError as exc:
            raise DuplicateRunError("Run ID already exists") from exc
        for ordinal, item in enumerate(normalized["thresholds"]):
            db.execute("INSERT INTO load_test_thresholds VALUES (?,?,?,?,?,?)",
                       (run["id"], ordinal, item["metric"], item["condition"], item["actualValue"], int(item["passed"])))
        for ordinal, item in enumerate(normalized["endpointMetrics"]):
            db.execute("INSERT INTO load_test_endpoint_metrics VALUES (?,?,?,?,?,?,?)",
                       (run["id"], ordinal, item["method"], item["endpoint"], item["requestCount"],
                        item["errorRate"], _json(item["latencyMs"])))
        for item in normalized["series"]:
            db.execute("INSERT INTO load_test_series VALUES (?,?,?,?,?,?,?,?,?)",
                       (run["id"], item["bucketAt"], item["rps"], item["activeVus"],
                        item["errorRate"], item["p95Ms"], item["cpuPercent"], item["memoryMb"],
                        item["childProcesses"]))

    def list_runs(self, *, project="", scenario="", status="", started_from="", started_to="", limit=20, cursor=""):
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if status and status not in ("passed", "failed", "aborted", "error"):
            raise ValueError("Invalid status")
        if any(len(value) > size for value, size in ((project, 255), (scenario, 120), (started_from, 40), (started_to, 40))):
            raise ValueError("Filter is too long")
        lower = _time_text(_time(started_from, "from")) if started_from else ""
        upper = _time_text(_time(started_to, "to")) if started_to else ""
        if lower and upper and lower > upper:
            raise ValueError("Invalid time interval")
        filters = [project, scenario, status, lower, upper]
        fingerprint = hashlib.sha256(_json([self.context.workspace_id, filters]).encode()).hexdigest()[:24]
        where = ["workspace_id=?"]
        params = [self.context.workspace_id]
        for column, value, operator in (("project_reference", project, "="), ("scenario", scenario, "="),
                                        ("status", status, "="), ("started_at", lower, ">="),
                                        ("started_at", upper, "<=")):
            if value:
                where.append(f"{column}{operator}?")
                params.append(value)
        if cursor:
            started_at, run_id = _cursor_decode(cursor, fingerprint)
            where.append("(started_at<? OR (started_at=? AND id<?))")
            params.extend((started_at, started_at, run_id))
        query = "SELECT id,schema_version,project_reference,scenario,status,started_at,ended_at,app_version,commit_sha,summary_json FROM load_test_runs WHERE " + " AND ".join(where) + " ORDER BY started_at DESC,id DESC LIMIT ?"
        with self.connection() as db:
            rows = db.execute(query, (*params, limit + 1)).fetchall()
        page = rows[:limit]
        items = [self._metadata(row) for row in page]
        next_cursor = _cursor_encode(page[-1]["started_at"], page[-1]["id"], fingerprint) if len(rows) > limit else None
        return {"items": items, "nextCursor": next_cursor}

    @staticmethod
    def _metadata(row):
        return {"schemaVersion": row["schema_version"], "run": {
            "id": row["id"], "project": row["project_reference"], "scenario": row["scenario"],
            "status": row["status"], "startedAt": row["started_at"], "endedAt": row["ended_at"],
            "appVersion": row["app_version"], "commitSha": row["commit_sha"]},
            "summary": json.loads(row["summary_json"])}

    def detail(self, run_id):
        with self.connection(snapshot=True) as db:
            return self._detail(db, run_id)

    def _detail(self, db, run_id):
        row = db.execute("SELECT * FROM load_test_runs WHERE id=? AND workspace_id=?", (run_id, self.context.workspace_id)).fetchone()
        if row is None:
            return None
        thresholds = db.execute("SELECT * FROM load_test_thresholds WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
        endpoints = db.execute("SELECT * FROM load_test_endpoint_metrics WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
        previous = db.execute("""SELECT * FROM load_test_runs
            WHERE workspace_id=? AND project_reference=? AND scenario=? AND schema_version=?
            AND (started_at<? OR (started_at=? AND id<?))
            ORDER BY started_at DESC,id DESC LIMIT 1""",
            (self.context.workspace_id, row["project_reference"], row["scenario"], row["schema_version"],
             row["started_at"], row["started_at"], row["id"])).fetchone()
        result = self._metadata(row)
        result["run"]["environment"] = json.loads(row["environment_json"])
        result["thresholds"] = [{"metric": item["metric"], "condition": item["condition"],
                                 "actualValue": item["actual_value"], "passed": bool(item["passed"])} for item in thresholds]
        result["endpointMetrics"] = [{"method": item["method"], "endpoint": item["endpoint"],
                                      "requestCount": item["request_count"], "errorRate": item["error_rate"],
                                      "latencyMs": json.loads(item["latency_json"])} for item in endpoints]
        result["warnings"] = json.loads(row["warnings_json"])
        result["recommendedBaseline"] = self._metadata(previous) if previous else None
        return result

    def series(self, run_id, *, started_from="", started_to="", max_points=500):
        if not isinstance(max_points, int) or not 1 <= max_points <= MAX_SERIES_POINTS:
            raise ValueError("maxPoints must be between 1 and 1000")
        lower = _time_text(_time(started_from, "from")) if started_from else ""
        upper = _time_text(_time(started_to, "to")) if started_to else ""
        if lower and upper and lower > upper:
            raise ValueError("Invalid time interval")
        with self.connection(snapshot=True) as db:
            exists = db.execute("SELECT 1 FROM load_test_runs WHERE id=? AND workspace_id=?", (run_id, self.context.workspace_id)).fetchone()
            if not exists:
                return None
            where = "run_id=?"
            params = [run_id]
            if lower:
                where += " AND bucket_at>=?"
                params.append(lower)
            if upper:
                where += " AND bucket_at<=?"
                params.append(upper)
            source_points = db.execute("SELECT count(*) FROM load_test_series WHERE " + where, params).fetchone()[0]
            if source_points <= max_points:
                rows = db.execute("SELECT * FROM load_test_series WHERE " + where + " ORDER BY bucket_at", params).fetchall()
                return {"items": [self._series_point(row) for row in rows], "sourcePoints": source_points, "aggregation": "none"}
            width = math.ceil(source_points / max_points)
            # SQL returns only the reduced rows, including with the PostgreSQL
            # buffered cursor. Divide before SUM to keep finite extreme inputs
            # from overflowing AVG's intermediate total. NULL remains unknown.
            rows = db.execute("""WITH numbered AS (
                SELECT *, CAST((ROW_NUMBER() OVER (ORDER BY bucket_at)-1)/? AS BIGINT) AS grp
                FROM load_test_series WHERE """ + where + """
            ), counted AS (
                SELECT *, COUNT(*) OVER (PARTITION BY grp) AS n,
                    COUNT(cpu_percent) OVER (PARTITION BY grp) AS cpu_n,
                    COUNT(memory_mb) OVER (PARTITION BY grp) AS memory_n
                FROM numbered
            ) SELECT MIN(bucket_at) AS bucket_at, SUM(rps/n) AS rps,
                MAX(active_vus) AS active_vus, SUM(error_rate/n) AS error_rate,
                MAX(p95_ms) AS p95_ms, SUM(cpu_percent/NULLIF(cpu_n,0)) AS cpu_percent,
                SUM(memory_mb/NULLIF(memory_n,0)) AS memory_mb,
                MAX(child_processes) AS child_processes
                FROM counted GROUP BY grp ORDER BY grp""", (width, *params)).fetchall()
        reduced = [self._series_point(row) for row in rows]
        for point in reduced:
            for key in ("rps", "errorRate", "cpuPercent", "memoryMb"):
                if point[key] is not None:
                    point[key] = round(point[key], 6)
        return {"items": reduced, "sourcePoints": source_points, "aggregation": "mean-values-peak-p95"}

    @staticmethod
    def _series_point(row):
        return {"bucketAt": row["bucket_at"], "rps": row["rps"], "activeVus": row["active_vus"],
                "errorRate": row["error_rate"], "p95Ms": row["p95_ms"], "cpuPercent": row["cpu_percent"],
                "memoryMb": row["memory_mb"], "childProcesses": row["child_processes"]}

    def compare(self, baseline_id, candidate_id):
        with self.connection(snapshot=True) as db:
            baseline, candidate = self._detail(db, baseline_id), self._detail(db, candidate_id)
        if baseline is None or candidate is None:
            return None
        if baseline["schemaVersion"] != candidate["schemaVersion"] or baseline["run"]["scenario"] != candidate["run"]["scenario"]:
            raise ValueError("Runs must have the same schema version and scenario")
        warning = []
        for field in ("project", "environment", "appVersion", "commitSha", "status"):
            if baseline["run"].get(field) != candidate["run"].get(field):
                warning.append(field)
        if baseline["summary"]["vusMax"] != candidate["summary"]["vusMax"]:
            warning.append("vusMax")
        def difference(before, after):
            if before is None or after is None:
                return {"baseline": before, "candidate": after, "delta": None, "changePercent": None}
            delta = after - before
            change = ((delta / before) * 100) if before else None
            if not math.isfinite(delta) or (change is not None and not math.isfinite(change)):
                raise ValueError("Comparison metric exceeds the supported range")
            return {"baseline": before, "candidate": after, "delta": delta, "changePercent": change}

        metrics = {}
        for label, getter in (("requests", lambda x: x["requests"]), ("rps", lambda x: x["rps"]),
                              ("vusMax", lambda x: x["vusMax"]), ("errorRate", lambda x: x["errorRate"]),
                              ("p50Ms", lambda x: x["latencyMs"]["p50"]),
                              ("p95Ms", lambda x: x["latencyMs"]["p95"]),
                              ("p99Ms", lambda x: x["latencyMs"]["p99"])):
            before, after = getter(baseline["summary"]), getter(candidate["summary"])
            metrics[label] = difference(before, after)
        before_endpoints = {(item["method"], item["endpoint"]): item for item in baseline["endpointMetrics"]}
        after_endpoints = {(item["method"], item["endpoint"]): item for item in candidate["endpointMetrics"]}
        endpoints = []
        for method, endpoint in sorted(before_endpoints.keys() | after_endpoints.keys()):
            before = before_endpoints.get((method, endpoint))
            after = after_endpoints.get((method, endpoint))
            endpoints.append({"method": method, "endpoint": endpoint,
                              "p95Ms": difference(before["latencyMs"]["p95"] if before else None,
                                                  after["latencyMs"]["p95"] if after else None),
                              "errorRate": difference(before["errorRate"] if before else None,
                                                      after["errorRate"] if after else None)})
        endpoints.sort(key=lambda item: (item["p95Ms"]["delta"] is None,
                                         -(item["p95Ms"]["delta"] or 0), item["method"], item["endpoint"]))
        return {"baseline": baseline_id, "candidate": candidate_id, "metrics": metrics,
                "endpoints": endpoints, "conditionWarnings": warning}
