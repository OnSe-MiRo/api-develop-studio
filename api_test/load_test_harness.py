"""Deterministic LT fixtures and isolated k6 probe/Smoke/read Baseline execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from api_test.collaboration_store import canonical_json
from api_test.database import initialize_local_context
from api_test.load_results import import_k6_result, validate_bundle
from api_test.migrations import migrate_studio_database

REPOSITORY = Path(__file__).resolve().parents[1]
PROFILES = {"small": (1, 10, 2), "medium": (20, 2000, 100), "large": (100, 20000, 0)}
BODY_BYTES = (1024, 10240, 102400)
FIXED_TIME = "2026-01-01T00:00:00+00:00"
ROOTS = {"projects": "projects", "cases": "case", "pipelines": "pipelines"}


class HarnessError(ValueError):
    pass


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _new_root(path: Path) -> Path:
    root = path.resolve()
    # Never reuse a directory: the caller must choose a new, dedicated location.
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    return root


def _body(size: int, seed: int) -> dict:
    body = {"fixture": seed, "padding": ""}
    body["padding"] = "x" * (size - len(canonical_json(body).encode("utf-8")))
    return body


def generate_fixture(root: Path, dataset: str, seed: int = 20260929, case_revisions: int = 1) -> dict:
    if dataset not in PROFILES or not 1 <= case_revisions <= 100:
        raise HarnessError("dataset must be small/medium/large and case revisions must be 1..100")
    root = _new_root(root)
    counts = dict(zip(ROOTS, PROFILES[dataset]))
    for directory in (*ROOTS.values(), "logs", "data"):
        (root / directory).mkdir()
    database = root / "data/studio.db"
    projects = [f"load-test/project-{index:03d}.json" for index in range(counts["projects"])]
    cases = []
    pipelines = []
    identity = hashlib.sha256(f"{dataset}:{seed}:{case_revisions}\n".encode())
    body_counts = dict.fromkeys(map(str, BODY_BYTES), 0)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        migrate_studio_database(connection)
        initialize_local_context(connection)

        def insert(kind, reference, document, revisions=1):
            document_id = "doc_" + hashlib.sha256(f"{kind}:{reference}".encode()).hexdigest()[:32]
            content = digest = None
            for revision in range(1, revisions + 1):
                if kind == "cases":
                    document["loadTest"]["revision"] = revision
                content = canonical_json(document)
                digest = hashlib.sha256(content.encode()).hexdigest()
                identity.update(f"{kind}:{reference}:{revision}:{digest}\n".encode())
                if revision == 1:
                    connection.execute(
                        "INSERT INTO documents(id, workspace_id, kind, reference, project_reference, current_revision, "
                        "content_hash, created_at, updated_at, created_by, updated_by) VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, 'local-user', 'local-user')",
                        (document_id, kind, reference, document.get("project") if kind != "projects" else reference,
                         revisions, digest, FIXED_TIME, FIXED_TIME))
                connection.execute("INSERT INTO document_revisions VALUES (?, ?, ?, ?, 'local-user', ?)",
                                   (document_id, revision, content, digest, FIXED_TIME))
                connection.execute("INSERT INTO audit_events(workspace_id, document_id, action, revision, actor_id, detail, created_at, request_id) "
                                   "VALUES ('default', ?, 'import', ?, 'local-user', ?, ?, ?)",
                                   (document_id, revision, reference, FIXED_TIME, f"fixture-{document_id}-{revision}"))
            connection.execute("UPDATE documents SET content_hash=? WHERE id=?", (digest, document_id))
            path = root / ROOTS[kind] / reference
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8")

        for index, reference in enumerate(projects):
            insert("projects", reference, {"name": f"Load test project {index:03d}", "base_url": "http://127.0.0.1:8765",
                                           "variables": {"plain": {}, "secret": {}}})
        per_project = counts["cases"] // counts["projects"]
        for index in range(counts["cases"]):
            project = projects[index // per_project]
            reference = f"load-test/health/project-{index // per_project:03d}-case-{index % per_project:04d}.json"
            size = BODY_BYTES[index % len(BODY_BYTES)]
            body_counts[str(size)] += 1
            insert("cases", reference, {"project": project, "request": {"method": "GET", "url": "/example-api/health", "body": _body(size, seed)},
                                        "expected": {"status": 200, "body": {"status": "ok", "service": "example-api"}, "strict": True},
                                        "loadTest": {"bodyBytes": size, "revision": 1}}, case_revisions)
            cases.append({"reference": reference, "project": project, "bodyBytes": size, "revision": case_revisions})
        for index in range(counts["pipelines"]):
            case = cases[(index * per_project) % len(cases)]
            reference = f"load-test/pipeline-{index:04d}.json"
            insert("pipelines", reference, {"name": f"Load test pipeline {index:04d}", "project": case["project"],
                                            "steps": [{"name": "health", "case": case["reference"]}]})
            pipelines.append(reference)
    random.Random(seed).shuffle(cases)
    manifest = {"formatVersion": 1, "dataset": dataset, "seed": seed, "caseRevisions": case_revisions,
                "counts": counts, "bodyCounts": body_counts, "fixtureSha256": identity.hexdigest(),
                "projects": projects, "cases": cases, "pipelines": pipelines}
    _json(root / "fixture.json", manifest)
    report = verify_fixture(root)
    _json(root / "verification.json", report)
    return report


def verify_fixture(root: Path, extra_documents: dict | None = None) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "fixture.json").read_text(encoding="utf-8"))
    counts = dict(zip(ROOTS, PROFILES[manifest["dataset"]]))
    depth = manifest["caseRevisions"]
    if manifest.get("formatVersion") != 1 or manifest["counts"] != counts or not 1 <= depth <= 100:
        raise HarnessError("unsupported fixture manifest")
    extra_documents = extra_documents or {}
    expected_counts = {kind: count + sum(1 for extra_kind, _ in extra_documents if extra_kind == kind) for kind, count in counts.items()}
    body_counts = dict.fromkeys(map(str, BODY_BYTES), 0)
    identity = hashlib.sha256(f"{manifest['dataset']}:{manifest['seed']}:{depth}\n".encode())
    case_index = {item["reference"]: item for item in manifest["cases"]}
    if len(case_index) != counts["cases"] or len(manifest["projects"]) != counts["projects"] or len(manifest["pipelines"]) != counts["pipelines"]:
        raise HarnessError("fixture reference manifest differs")
    projection_bytes = revision_bytes = 0
    database = root / "data/studio.db"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchone():
            raise HarnessError("fixture database integrity failed")
        actual = dict(connection.execute("SELECT kind, COUNT(*) FROM documents GROUP BY kind"))
        if {kind: actual.get(kind, 0) for kind in ROOTS} != expected_counts:
            raise HarnessError("fixture document counts differ")
        # Order matches generation: projects, cases, pipelines, then reference.
        if connection.execute("SELECT 1 FROM documents WHERE deleted_at IS NOT NULL LIMIT 1").fetchone():
            raise HarnessError("fixture contains an unexpected deleted document")
        rows = connection.execute("SELECT id, kind, reference, current_revision, content_hash FROM documents "
                                  "ORDER BY CASE kind WHEN 'projects' THEN 0 WHEN 'cases' THEN 1 ELSE 2 END, reference")
        for document_id, kind, reference, current_revision, current_hash in rows:
            expected_extra = extra_documents.get((kind, reference))
            if expected_extra is not None:
                saved = connection.execute("SELECT revision, content, content_hash FROM document_revisions WHERE document_id=? ORDER BY revision", (document_id,)).fetchall()
                if current_revision != len(expected_extra) or len(saved) != len(expected_extra):
                    raise HarnessError("mutation revision count differs")
                for number, ((revision, content, digest), expected) in enumerate(zip(saved, expected_extra), 1):
                    if revision != number or json.loads(content) != expected or hashlib.sha256(content.encode()).hexdigest() != digest:
                        raise HarnessError("mutation revision content differs")
                    revision_bytes += len(content.encode())
                raw = (root / ROOTS[kind] / reference).read_bytes()
                projection_bytes += len(raw)
                if json.loads(raw) != expected_extra[-1] or current_hash != saved[-1][2]:
                    raise HarnessError("mutation JSON projection differs")
                continue
            if current_revision != (depth if kind == "cases" else 1):
                raise HarnessError("fixture revision depth differs")
            revisions = connection.execute("SELECT revision, content, content_hash FROM document_revisions WHERE document_id=? ORDER BY revision", (document_id,))
            latest = None
            seen = 0
            for revision, content, digest in revisions:
                seen += 1
                if revision != seen or hashlib.sha256(content.encode()).hexdigest() != digest:
                    raise HarnessError("fixture revision content differs")
                identity.update(f"{kind}:{reference}:{revision}:{digest}\n".encode())
                revision_bytes += len(content.encode())
                latest = json.loads(content)
            if seen != current_revision or digest != current_hash:
                raise HarnessError("fixture latest revision differs")
            if not reference.startswith("load-test/") or ".." in Path(reference).parts or "\\" in reference:
                raise HarnessError("fixture reference is not a dedicated relative path")
            path = root / ROOTS[kind] / reference
            raw = path.read_bytes()
            projection_bytes += len(raw)
            if json.loads(raw) != latest:
                raise HarnessError("fixture JSON projection differs")
            if kind == "cases":
                body_size = len(canonical_json(latest["request"]["body"]).encode())
                if body_size != latest["loadTest"]["bodyBytes"] or body_size not in BODY_BYTES:
                    raise HarnessError("fixture body size differs")
                if case_index.get(reference) != {"reference": reference, "project": latest["project"], "bodyBytes": body_size, "revision": depth} or latest["request"]["body"]["fixture"] != manifest["seed"]:
                    raise HarnessError("fixture case manifest differs")
                body_counts[str(body_size)] += 1
            elif reference not in manifest[kind]:
                raise HarnessError("fixture reference manifest differs")
        for kind, directory in ROOTS.items():
            if sum(1 for _ in (root / directory).rglob("*.json")) != expected_counts[kind]:
                raise HarnessError("fixture projection counts differ")
        revision_count = connection.execute("SELECT COUNT(*) FROM document_revisions").fetchone()[0]
        if revision_count != counts["cases"] * depth + counts["projects"] + counts["pipelines"] + sum(map(len, extra_documents.values())):
            raise HarnessError("fixture revision count differs")
    if identity.hexdigest() != manifest["fixtureSha256"] or body_counts != manifest["bodyCounts"]:
        raise HarnessError("fixture fingerprint differs")
    return {"dataset": manifest["dataset"], "seed": manifest["seed"], "counts": expected_counts, "caseRevisions": depth,
            "revisionCount": revision_count, "bodyCounts": body_counts, "fixtureSha256": identity.hexdigest(),
            "databaseBytes": database.stat().st_size, "projectionBytes": projection_bytes, "revisionContentBytes": revision_bytes,
            "integrity": "passed"}


def isolated_environment() -> dict:
    # Inherited database, Redis, proxy, credentials and Python path never select the target.
    names = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG")
    return {**{key: os.environ[key] for key in names if key in os.environ}, "LOCAL_SERVER": "true", "EXAMPLE_PROJECT": "true",
            "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": "", "STUDIO_REDIS_URL": "",
            "NO_PROXY": "127.0.0.1,localhost", "PYTHONUNBUFFERED": "1", "K6_NO_USAGE_REPORT": "true"}


def _serve(root: Path, ready: Path) -> None:
    import uvicorn
    from api_test.services import studio
    from api_test.collaboration_store import CollaborationStore
    from api_test.main import create_app
    root = root.resolve()
    os.environ["STUDIO_DB_PATH"] = str(root / "data/studio.db")
    studio.ROOT = root
    studio.PROJECT_ROOT = root / "projects"
    studio.CASE_ROOT = root / "case"
    studio.PIPELINE_ROOT = root / "pipelines"
    store = CollaborationStore(root / "data/studio.db", {kind: root / directory for kind, directory in ROOTS.items()})
    store.initialize(import_existing=False)
    studio._COLLABORATION_STORE = store
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    application = create_app(studio)
    if os.environ.get("STUDIO_LT4_STUB") == "true":
        from api_test.load_test_campaigns import install_stub
        install_stub(application)
    server = uvicorn.Server(uvicorn.Config(application, log_level="info", access_log=True, proxy_headers=False))
    base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    if os.environ.get("STUDIO_MUTATION_MODE") == "target":
        from api_test.load_test_mutations import prepare_runner
        prepare_runner(root, base_url, REPOSITORY, "/__load_test__/health" if os.environ.get("STUDIO_LT4_STUB") == "true" else "/example-api/health")
    _json(ready, {"baseUrl": base_url})
    server.run(sockets=[listener])


def _stop(process) -> None:
    group = getattr(process, "_isolated_group", False) is True
    if group:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        if not group:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if group:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
    if group:
        # A server may exit while a descendant ignores SIGTERM. Reap its private group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _host_memory_mb():
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024)
    except (AttributeError, OSError, ValueError):
        return None


def workload_configuration(mode: str, validation_seconds: int | None = None, concurrency: int = 5, validation_vus: int | None = None) -> dict:
    if mode not in ("probe", "smoke", "baseline", "target", "unique", "contention"):
        raise HarnessError("unsupported workload")
    maximum = {"probe": 30, "smoke": 60, "baseline": 300, "target": 1200, "unique": 60, "contention": 30}[mode]
    if concurrency not in (5, 20, 50) or isinstance(concurrency, bool):
        raise HarnessError("write concurrency must be 5,20 or 50")
    if validation_seconds is not None and (mode in ("probe", "unique", "contention") or isinstance(validation_seconds, bool) or not isinstance(validation_seconds, int) or not 2 <= validation_seconds < maximum):
        raise HarnessError("validation seconds must be an integer from 2 to below the default duration")
    if mode == "target" and validation_seconds is not None and validation_seconds % 2:
        raise HarnessError("target validation duration must be even for two equal plateaus")
    if validation_vus is not None and (mode != "target" or validation_seconds is None or validation_vus not in (1, 2) or isinstance(validation_vus, bool)):
        raise HarnessError("reduced VUs require target validation and may be 1 or 2")
    duration = validation_seconds if validation_seconds is not None else maximum
    vus = {"probe": 1, "smoke": 7, "baseline": 5, "target": validation_vus or 50, "unique": concurrency, "contention": 1}[mode]
    config = {"mode": mode, "durationSeconds": duration, "configuredVus": vus,
              "vusPerEndpoint": 1 if mode == "smoke" else None, "gracefulStopSeconds": 30 if mode == "probe" else 10,
              "validationMode": validation_seconds is not None, "scope": "one-project" if mode == "probe" else "whole-dataset"}
    if mode in ("target", "unique", "contention"):
        config.update(selectionStride=50 if mode == "target" else vus, contentionRequests=5 if mode == "target" else concurrency)
    if mode == "target":
        config.update(stageSeconds=duration // 2, stageVus=[1, validation_vus] if validation_vus else [20, 50],
                      nominalWorkloadHttpRatios={"list": .35, "single": .35, "revision": .10, "unique": .10, "contention": .05, "run": .05})
    return config


def run_probe(fixture: Path, output: Path, k6: str = "k6") -> dict:
    return run_workload(fixture, output, k6)


def run_workload(fixture: Path, output: Path, k6: str = "k6", mode: str = "probe", validation_seconds: int | None = None, concurrency: int = 5, validation_vus: int | None = None) -> dict:
    workload = workload_configuration(mode, validation_seconds, concurrency, validation_vus)
    fixture = fixture.resolve()
    if output.resolve().is_relative_to(fixture):
        raise HarnessError("execution output must be outside the fixture directory")
    verification = verify_fixture(fixture)
    executable = shutil.which(k6)
    if executable is None:
        raise HarnessError("k6 binary is required; pass --k6 /absolute/path/to/k6")
    output = _new_root(output)
    environment = isolated_environment()
    environment["XDG_CONFIG_HOME"] = str(output / "config")
    version = subprocess.run([executable, "version"], capture_output=True, text=True, check=True, env=environment).stdout.strip()
    snapshot = output / "fixture"
    shutil.copytree(fixture.resolve(), snapshot)
    manifest = json.loads((snapshot / "fixture.json").read_text())
    environment["STUDIO_DB_PATH"] = str(snapshot / "data/studio.db")
    environment["STUDIO_MUTATION_MODE"] = mode
    (snapshot / "tmp").mkdir()
    for temporary_variable in ("TMPDIR", "TEMP", "TMP"):
        environment[temporary_variable] = str(snapshot / "tmp")
    ready = output / "server-ready.json"
    server = None
    memory_mb = _host_memory_mb()
    disk = shutil.disk_usage(output)
    script = "load-tests/k6/harness-probe.js" if mode == "probe" else "load-tests/k6/mixed.js" if mode in ("target", "unique", "contention") else "load-tests/k6/read.js"
    source_files = ("api_test/load_test_harness.py", "api_test/load_results.py", script, "load-tests/k6/studio-summary.js")
    if mode != "probe":
        source_files += ("load-tests/k6/read-model.js",)
    if mode in ("target", "unique", "contention"):
        source_files += ("load-tests/k6/mixed-model.js", "api_test/load_test_mutations.py")
    source_hashes = {name: hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() for name in source_files}
    result = {"fixture": verification, "executionMode": "isolated-local-same-host", "k6Version": version,
              "pythonVersion": platform.python_version(), "os": platform.platform(), "cpu": f"{platform.processor() or 'unknown'}, {os.cpu_count()} logical CPUs",
              "memoryMb": memory_mb, "diskTotalBytes": disk.total, "diskFreeBytes": disk.free, "sourceSha256": source_hashes,
              "command": [executable, "run", "--out", f"json={output / 'raw.jsonl'}", str(REPOSITORY / script)],
              "workload": workload,
              "status": "error"}
    bundle = None
    try:
        with (output / "server.log").open("w") as server_log:
            server = subprocess.Popen([sys.executable, "-m", "api_test.load_test_harness", "_serve", "--root", str(snapshot), "--ready", str(ready)],
                                      cwd=REPOSITORY, env=environment, stdout=server_log, stderr=subprocess.STDOUT, start_new_session=os.name == "posix")
            server._isolated_group = os.name == "posix"
            deadline = time.monotonic() + 30
            while not ready.exists():
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise HarnessError("isolated server did not become ready; inspect server.log")
                time.sleep(0.05)
            base_url = json.loads(ready.read_text())["baseUrl"]
            from urllib.request import build_opener, ProxyHandler
            opener = build_opener(ProxyHandler({}))
            while True:
                try:
                    with opener.open(base_url + "/example-api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise HarnessError("isolated server health timed out")
                    time.sleep(0.05)
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True).stdout.strip()
            result["commitSha"] = commit
            result["workingTreeDirty"] = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPOSITORY, capture_output=True, text=True).stdout.strip())
            app_version = json.loads((REPOSITORY / "web/package.json").read_text())["version"]
            result["appVersion"] = app_version
            run_id = "run_lt1_" + uuid.uuid4().hex
            result["runId"] = run_id
            env = {**environment, "STUDIO_BASE_URL": base_url, "STUDIO_FIXTURE_PATH": str(snapshot / "fixture.json"),
                   "STUDIO_RUN_ID": run_id, "STUDIO_PROJECT": manifest["projects"][0] if mode == "probe" else f"load-test/{manifest['dataset']}.json",
                   "STUDIO_SCENARIO": "harness-probe" if mode == "probe" else f"{mode}-mixed" if mode == "target" else f"{mode}-writes" if mode in ("unique", "contention") else f"{mode}-read",
                   "STUDIO_READ_MODE": mode, "STUDIO_DURATION_SECONDS": str(workload["durationSeconds"]),
                   "STUDIO_SUMMARY_PATH": str(output / "studio-summary.json"), "STUDIO_OS": platform.platform(),
                   "STUDIO_CPU": result["cpu"], "STUDIO_COMMIT_SHA": commit, "STUDIO_APP_VERSION": app_version,
                   "STUDIO_EXECUTION_MODE": result["executionMode"], "STUDIO_K6_VERSION": version,
                   "STUDIO_STARTED_AT": datetime.now(timezone.utc).isoformat()}
            if workload["validationMode"]:
                env["STUDIO_SCENARIO"] += "-validation"
            if mode in ("target", "unique", "contention"):
                env.update(STUDIO_MUTATION_MODE=mode, STUDIO_CONTENTION_REQUESTS=str(workload["contentionRequests"]),
                           STUDIO_CONFIGURED_VUS=str(workload["configuredVus"]), STUDIO_SELECTION_STRIDE=str(workload["selectionStride"]),
                           STUDIO_RUNTIME_PATH=str(snapshot / "runtime.json"))
            if mode == "target" and validation_seconds is not None:
                env["STUDIO_TARGET_VALIDATION_SECONDS"] = str(validation_seconds)
                if validation_vus is not None:
                    env["STUDIO_TARGET_VALIDATION_VUS"] = str(validation_vus)
            if memory_mb is not None:
                env["STUDIO_MEMORY_MB"] = str(memory_mb)
            result["startedAt"] = env["STUDIO_STARTED_AT"]
            with (output / "k6.log").open("w") as k6_log:
                completed = subprocess.run(result["command"], cwd=REPOSITORY, env=env, stdout=k6_log, stderr=subprocess.STDOUT, timeout=workload["durationSeconds"] + workload["gracefulStopSeconds"] + 15)
            result["k6ExitCode"] = completed.returncode
            if (output / "studio-summary.json").exists():
                bundle = import_k6_result(output / "studio-summary.json", output / "raw.jsonl")
                validate_bundle(bundle)
                result["summary"] = bundle["summary"]
                result["endedAt"] = bundle["run"]["endedAt"]
                result["status"] = bundle["run"]["status"] if completed.returncode in (0, 99) else "error"
            if mode in ("target", "unique", "contention"):
                from api_test.load_test_mutations import expected_mutations, traffic_report
                extras = expected_mutations(snapshot, workload)
                result["postRunIntegrity"] = verify_fixture(snapshot, extras)
                result["mutations"] = {"documents": len(extras), "unique": sum(1 for kind, reference in extras if "/unique-" in reference),
                                       "contention": sum(1 for kind, reference in extras if "/contention-" in reference)}
                result["traffic"] = traffic_report(output / "raw.jsonl")
                if result["traffic"]["totalClassifiedRequests"] != result.get("summary", {}).get("requests"):
                    raise HarnessError("classified traffic does not match HTTP requests")
            else:
                result["postRunIntegrity"] = verify_fixture(snapshot)
            if result["postRunIntegrity"]["fixtureSha256"] != verification["fixtureSha256"]:
                raise HarnessError("read workload changed fixture content")
            if bundle is not None:
                _json(output / "bundle.json", bundle)
    except BaseException as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        cleanup_error = None
        if server is not None:
            try:
                _stop(server)
                result["serverExitCode"] = server.returncode
                result["serverStopped"] = server.poll() is not None
            except (OSError, subprocess.SubprocessError) as exc:
                cleanup_error = exc
                result["status"] = "error"
                result["cleanupError"] = str(exc)
        _json(output / "execution.json", result)
        if cleanup_error is not None:
            raise HarnessError("isolated server cleanup failed; inspect execution.json") from cleanup_error
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--root", type=Path, required=True)
    generate.add_argument("--dataset", choices=PROFILES, required=True)
    generate.add_argument("--seed", type=int, default=20260929)
    generate.add_argument("--case-revisions", type=int, choices=range(1, 101), default=1, metavar="1..100")
    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    for mode in ("probe", "smoke", "baseline", "target", "unique", "contention"):
        run = commands.add_parser(mode)
        run.add_argument("--fixture", type=Path, required=True)
        run.add_argument("--output", type=Path, required=True)
        run.add_argument("--k6", default="k6")
        if mode in ("smoke", "baseline", "target"):
            run.add_argument("--validation-seconds", type=int, help="bounded shorter run, labelled as validation")
        if mode in ("unique", "contention"):
            run.add_argument("--concurrency", type=int, choices=(5, 20, 50), default=5)
        if mode == "target":
            run.add_argument("--validation-vus", type=int, choices=(1, 2), help="reduced 1-to-N VUs, requires shortened validation mode")
    for mode in ("stress", "spike", "soak", "run-capacity", "run-sustained", "fault"):
        campaign = commands.add_parser(mode)
        campaign.add_argument("--fixture", type=Path, required=True)
        campaign.add_argument("--output", type=Path, required=True)
        campaign.add_argument("--k6", default="k6")
        campaign.add_argument("--validation-seconds", type=int)
        campaign.add_argument("--validation-vus", type=int, choices=(1, 2))
        campaign.add_argument("--validation-stop-seconds", type=int)
    serve = commands.add_parser("_serve", help=argparse.SUPPRESS)
    serve.add_argument("--root", type=Path, required=True)
    serve.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_fixture(args.root, args.dataset, args.seed, args.case_revisions)
        elif args.command == "verify":
            result = verify_fixture(args.root)
        elif args.command in ("stress", "spike", "soak", "run-capacity", "run-sustained", "fault"):
            from api_test.load_test_campaigns import run_campaign
            result = run_campaign(args.fixture, args.output, args.k6, args.command, args.validation_seconds, args.validation_vus, args.validation_stop_seconds)
        elif args.command in ("probe", "smoke", "baseline", "target", "unique", "contention"):
            result = run_workload(args.fixture, args.output, args.k6, args.command, getattr(args, "validation_seconds", None), getattr(args, "concurrency", 5), getattr(args, "validation_vus", None))
        else:
            _serve(args.root, args.ready)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status", "passed") == "passed" else 1
    except (HarnessError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"LT harness: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
