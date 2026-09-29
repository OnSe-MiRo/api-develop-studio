"""Reproducible socket-level dashboard API benchmark using only isolated fixtures.

20,000 run metadata over 30 days (about 667/day); the detailed fixture has 500
endpoints and 2,500 series points. This models metadata lookup plus one large run,
not 20,000 fully materialized runs, raw k6 storage, or an operational LT workload.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import socket
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import patch

import uvicorn

from api_test.database import _pools
from api_test.load_test_store import LoadTestStore, _json
from api_test.load_results import _time_text


def detailed_fixture():
    start = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
    latency = {"p50": 10.0, "p90": 20.0, "p95": 30.0, "p99": 40.0, "max": 50.0}
    return {"schemaVersion": 1, "run": {"id": "bench-detail", "project": "benchmark.json", "scenario": "dashboard-api",
        "startedAt": _time_text(start), "endedAt": _time_text(start + timedelta(seconds=2500)), "status": "passed",
        "appVersion": "benchmark", "commitSha": "abcdef1", "environment": {"os": "fixture", "cpu": "fixture",
        "memoryMb": None, "executionMode": "isolated-http", "k6Version": None}},
        "summary": {"requests": 500, "rps": .2, "errorRate": 0.0, "vusMax": 20,
            "thresholdsPassed": True, "latencyMs": latency},
        "thresholds": [{"metric": "http_req_duration", "condition": "p(95)<300", "actualValue": 30.0, "passed": True}],
        "endpointMetrics": [{"method": "GET", "endpoint": "/api/fixture/endpoint-" + chr(97 + i // 26) + chr(97 + i % 26),
            "requestCount": 1, "errorRate": 0.0, "latencyMs": dict(latency)} for i in range(500)],
        "series": [{"bucketAt": _time_text(start + timedelta(seconds=i)), "rps": 10.0, "activeVus": 20,
            "errorRate": 0.0, "p95Ms": 100.0 if i == 2499 else 30.0, "cpuPercent": None, "memoryMb": None,
            "childProcesses": None} for i in range(2500)], "warnings": []}


def populate(store):
    fixture = detailed_fixture()
    store.import_bundle(fixture)
    metadata = fixture["run"]
    start = datetime(2026, 9, 29, tzinfo=timezone.utc)
    with store.connection(write=True) as db, db:
        db.execute("BEGIN IMMEDIATE")
        for i in range(19999):
            at = _time_text(start - timedelta(seconds=(i + 1) * 30 * 86400 / 20000))
            db.execute("""INSERT INTO load_test_runs(id,workspace_id,schema_version,project_reference,scenario,status,
                started_at,ended_at,app_version,commit_sha,environment_json,summary_json,warnings_json,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (f"bench-meta-{i:05}", store.context.workspace_id, 1,
                metadata["project"], metadata["scenario"], "passed", at, _time_text(start - timedelta(seconds=(i + 1) * 30 * 86400 / 20000 - 1)), "benchmark", "abcdef1",
                _json(metadata["environment"]), _json(fixture["summary"]), "[]", store.context.user_id))
        if getattr(db, "dialect", "") == "postgresql":
            db.execute("ANALYZE load_test_runs")
    return fixture


@contextmanager
def isolated_backend(root, *, postgres=False):
    if not postgres:
        yield root / "benchmark.db", ""
        return
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    # Never infer a test/admin connection from the application's production URL.
    admin_url = os.environ.get("FND4_TEST_DATABASE_URL", "postgresql://studio_test:studio_test_local@127.0.0.1:15432/postgres")
    name = "db5_benchmark_" + uuid.uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = make_conninfo(admin_url, dbname=name)
        try:
            yield root / "unused", url
        finally:
            pool = _pools.pop(url, None)
            if pool:
                pool.close()
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def benchmark(*, postgres=False, requests=60, concurrency=8):
    if type(requests) is not int or not 20 <= requests <= 1000 or type(concurrency) is not int or not 1 <= concurrency <= 32:
        raise ValueError("Benchmark requires 20..1000 requests per API and concurrency 1..32")
    with tempfile.TemporaryDirectory(prefix="studio-db5-benchmark-") as directory:
        root = Path(directory)
        with isolated_backend(root, postgres=postgres) as (path, url), patch.dict(os.environ, {
            "STUDIO_DB_PATH": str(path), "STUDIO_DATABASE_URL": url, "STUDIO_DATABASE_URL_FILE": ""}):
            fixture = populate(LoadTestStore(path, url=url))
            from api_test.main import app
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            host = "http://127.0.0.1:" + str(listener.getsockname()[1])
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
            worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            worker.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started and worker.is_alive() and time.monotonic() < deadline:
                    time.sleep(.01)
                if not server.started:
                    raise RuntimeError("Isolated benchmark server failed to start")
                paths = {"list": "/api/load-tests/runs?project=benchmark.json&limit=20",
                         "detail": "/api/load-tests/runs/bench-detail",
                         "series": "/api/load-tests/runs/bench-detail/series?maxPoints=240"}
                def call(name):
                    started = time.perf_counter()
                    with urlopen(host + paths[name], timeout=10) as response:
                        body = response.read()
                        status = response.status
                    elapsed = (time.perf_counter() - started) * 1000
                    value = json.loads(body)
                    if status != 200 or len(body) > 1024 * 1024:
                        raise AssertionError("API status/response budget differs")
                    if name == "list":
                        if len(value["items"]) != 20 or value["items"][0]["run"]["id"] != "bench-detail":
                            raise AssertionError("List golden order/count differs")
                    elif name == "detail":
                        if value["summary"] != fixture["summary"] or value["endpointMetrics"] != fixture["endpointMetrics"] or not value["recommendedBaseline"]:
                            raise AssertionError("Detail golden summary/endpoints/baseline differs")
                    elif value["sourcePoints"] != 2500 or len(value["items"]) > 240 or max(p["p95Ms"] for p in value["items"]) != 100 or any(p["memoryMb"] is not None for p in value["items"]):
                        raise AssertionError("Series golden count/p95 envelope/unknown differs")
                    return name, elapsed, len(body)
                for name in paths:
                    call(name)  # Warm-up excludes migrations/cold startup.
                jobs = [name for _ in range(requests) for name in paths]
                measurements = {name: [] for name in paths}
                sizes = {name: 0 for name in paths}
                started = time.perf_counter()
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    for name, elapsed, size in pool.map(call, jobs):
                        measurements[name].append(elapsed)
                        sizes[name] = max(sizes[name], size)
                report = {"backend": "postgresql" if postgres else "sqlite", "modelDays": 30, "metadataRuns": 20000,
                    "detailedRuns": 1, "endpoints": 500, "sourceSeriesPoints": 2500,
                    "requestsPerApi": requests, "concurrency": concurrency, "errors": 0,
                    "elapsedSeconds": round(time.perf_counter() - started, 3), "apis": {}}
                for name, times in measurements.items():
                    ordered = sorted(times)
                    report["apis"][name] = {"p50Ms": round(ordered[math.ceil(len(ordered)*.5)-1], 3),
                        "p95Ms": round(ordered[math.ceil(len(ordered)*.95)-1], 3), "maxMs": round(max(times), 3),
                        "maxBytes": sizes[name]}
                report["passed"] = report["apis"]["list"]["p95Ms"] <= 500 and report["apis"]["detail"]["p95Ms"] <= 1000
                return report
            finally:
                server.should_exit = True
                worker.join(timeout=10)
                listener.close()
                if worker.is_alive():
                    raise RuntimeError("Benchmark server did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(postgres=args.postgres, requests=args.requests, concurrency=args.concurrency)
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
