"""Explicit workspace retention and portable normalized-result backup commands.

Database cleanup is atomic. Artifact cleanup is a separate, fail-closed POSIX
operation with exact previewed files and per-file progress; stop artifact writers
for its duration. No scheduler, automatic deletion, or database overwrite exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api_test.database import LOCAL_CONTEXT, RequestContext, connect, require_membership
from api_test.load_results import _time, _time_text
from api_test.load_test_store import LoadTestStore, MAX_BUNDLE_BYTES, _json, _normalize
from api_test.migrations import migrate_studio_database

TABLES = ("load_test_runs", "load_test_thresholds", "load_test_endpoint_metrics", "load_test_series")
ORDERS = ("r.id", "t.run_id,t.ordinal", "t.run_id,t.ordinal", "t.run_id,t.bucket_at")
BACKUP_FORMAT = "studio-load-results-backup-v1"


def _private_create(path, mode="wb"):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, mode, **({"encoding": "utf-8"} if "b" not in mode else {}))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _operator(db, context):
    require_membership(db, context, write=True)
    role = db.execute("SELECT role FROM memberships WHERE workspace_id=? AND user_id=?",
                      (context.workspace_id, context.user_id)).fetchone()[0]
    if role not in ("owner", "admin"):
        raise PermissionError("Load-test maintenance requires an active owner or admin")


def _maintenance_timeout(db):
    if getattr(db, "dialect", "") == "postgresql":
        # Session defaults are restored on commit/rollback by SET LOCAL.
        db.execute("SET LOCAL transaction_timeout='0'")
        db.execute("SET LOCAL statement_timeout='120s'")


@contextmanager
def _rows(db, sql, params=()):
    """Server-side PG cursor: fetchmany on a normal cursor still buffers libpq."""
    if getattr(db, "dialect", "") == "postgresql":
        cursor = db.raw.cursor(name="load_maintenance_" + os.urandom(8).hex())
        cursor.execute(sql.replace("?", "%s"), params)
    else:
        cursor = db.execute(sql, params)
    try:
        yield cursor
    finally:
        cursor.close()


def _iter_rows(cursor):
    while True:
        batch = cursor.fetchmany(256)
        if not batch:
            return
        yield from batch


def _source_identity(db, store):
    if getattr(db, "dialect", "") == "postgresql":
        row = db.execute("SELECT current_database() AS name, oid FROM pg_database WHERE datname=current_database()").fetchone()
        # No URL, password, credential, or connection string enters the manifest.
        return {"backend": "postgresql", "fingerprint": _digest([
            db.raw.info.host, db.raw.info.port, row["name"], row["oid"]])}
    path = store.path.resolve()
    status = path.stat()
    return {"backend": "sqlite", "path": str(path), "identity": _identity(status)}


def _selection(db, store, cutoff):
    context = store.context
    scope = "r.workspace_id=? AND r.ended_at<?"
    params = (context.workspace_id, cutoff)
    runs = [dict(row) for row in db.execute(
        "SELECT r.id,r.project_reference,r.ended_at FROM load_test_runs r WHERE " + scope + " ORDER BY r.id", params).fetchall()]
    hashes = {}
    for table, order in zip(TABLES, ORDERS):
        sql = ("SELECT r.* FROM load_test_runs r WHERE " + scope if table == TABLES[0] else
               f"SELECT t.* FROM {table} t JOIN load_test_runs r ON r.id=t.run_id WHERE " + scope)
        sha = hashlib.sha256()
        count = 0
        with _rows(db, sql + " ORDER BY " + order, params) as cursor:
            for row in _iter_rows(cursor):
                sha.update((_json(dict(row)) + "\n").encode())
                count += 1
        hashes[table] = {"rows": count, "sha256": sha.hexdigest()}
    return {"format": "studio-load-retention-v1", "workspace": context.workspace_id, "source": _source_identity(db, store),
            "cutoff": cutoff, "runs": runs, "tables": hashes}


def retention_preview(store, *, days=30, now=None):
    if type(days) is not int or not 1 <= days <= 36500:
        raise ValueError("Retention days must be between 1 and 36500")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Retention reference time requires a timezone")
    cutoff = _time_text(now.astimezone(timezone.utc) - timedelta(days=days))
    with store.connection(snapshot=True) as db:
        _maintenance_timeout(db)
        _operator(db, store.context)
        return _selection(db, store, cutoff)


def _check_manifest(manifest, confirmation, context):
    if _digest(manifest) != confirmation:
        raise ValueError("Confirmation SHA256 does not match the preview manifest")
    if manifest.get("format") != "studio-load-retention-v1" or manifest.get("workspace") != context.workspace_id:
        raise ValueError("Retention manifest workspace or format differs")
    cutoff = _time_text(_time(manifest["cutoff"], "cutoff"))
    if cutoff != manifest["cutoff"] or cutoff > _time_text(datetime.now(timezone.utc)):
        raise ValueError("Invalid retention cutoff")
    return cutoff


def _lock_selection(db):
    db.execute("BEGIN IMMEDIATE")
    _maintenance_timeout(db)
    if getattr(db, "dialect", "") == "postgresql":
        db.execute("LOCK TABLE " + ",".join(TABLES) + " IN SHARE ROW EXCLUSIVE MODE")


def retention_apply(store, manifest, *, confirmation):
    cutoff = _check_manifest(manifest, confirmation, store.context)
    with store.connection(write=True) as db, db:
        _lock_selection(db)
        _operator(db, store.context)
        if manifest.get("source") != _source_identity(db, store):
            raise ValueError("Retention manifest belongs to a different source database")
        if _selection(db, store, cutoff) != manifest:
            raise ValueError("Retention preview is stale; create a new preview")
        params = (store.context.workspace_id, cutoff)
        selected = "SELECT id FROM load_test_runs WHERE workspace_id=? AND ended_at<?"
        for table in TABLES[1:]:
            db.execute(f"DELETE FROM {table} WHERE run_id IN ({selected})", params)
        db.execute("DELETE FROM load_test_runs WHERE workspace_id=? AND ended_at<?", params)
    # Baseline recommendations are derived on reads, so no stored dangling link.
    return {"deletedRuns": len(manifest["runs"]), "tables": manifest["tables"]}


def _bundle(db, row):
    value = LoadTestStore._metadata(row)
    value["run"]["environment"] = json.loads(row["environment_json"])
    run_id = row["id"]
    value["thresholds"] = [{"metric": r["metric"], "condition": r["condition"],
        "actualValue": r["actual_value"], "passed": bool(r["passed"])} for r in db.execute(
            "SELECT * FROM load_test_thresholds WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()]
    value["endpointMetrics"] = [{"method": r["method"], "endpoint": r["endpoint"], "requestCount": r["request_count"],
        "errorRate": r["error_rate"], "latencyMs": json.loads(r["latency_json"])} for r in db.execute(
            "SELECT * FROM load_test_endpoint_metrics WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()]
    value["series"] = [LoadTestStore._series_point(r) for r in db.execute(
        "SELECT * FROM load_test_series WHERE run_id=? ORDER BY bucket_at", (run_id,)).fetchall()]
    value["warnings"] = json.loads(row["warnings_json"])
    return value


def backup(store, destination):
    destination = Path(destination)
    # 'x' refuses both an existing file and a symlink. No source database path is written.
    with store.connection(snapshot=True) as db:
        _maintenance_timeout(db)
        _operator(db, store.context)
        with _private_create(destination) as output:
            sha = hashlib.sha256()
            def write(value):
                data = (_json(value) + "\n").encode()
                output.write(data)
                sha.update(data)
            write({"format": BACKUP_FORMAT, "workspace": store.context.workspace_id, "schemaVersion": 1})
            count = 0
            with _rows(db, "SELECT * FROM load_test_runs WHERE workspace_id=? ORDER BY id", (store.context.workspace_id,)) as cursor:
                for row in _iter_rows(cursor):
                    value = _normalize(_bundle(db, row))
                    if len(_json(value).encode()) > MAX_BUNDLE_BYTES:
                        raise ValueError("Stored run exceeds the supported backup bundle size")
                    write(value)
                    count += 1
            footer = {"runs": count, "sha256": sha.hexdigest()}
            output.write((_json(footer) + "\n").encode())
            output.flush()
            os.fsync(output.fileno())
    return footer


def _backup_values(path, context, verified=None):
    """Validate all bytes, schema, and trusted workspace before yielding footer."""
    sha = hashlib.sha256()
    count = 0
    with Path(path).open("rb") as source:
        first = source.readline(1024)
        header = json.loads(first)
        if header != {"format": BACKUP_FORMAT, "workspace": context.workspace_id, "schemaVersion": 1}:
            raise ValueError("Backup header/schema/workspace differs from trusted restore context")
        sha.update(first)
        while True:
            line = source.readline(MAX_BUNDLE_BYTES + 2)
            if not line or len(line) > MAX_BUNDLE_BYTES + 1 or not line.endswith(b"\n"):
                raise ValueError("Backup is incomplete or its bundle exceeds the size limit")
            value = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite backup number")))
            if not isinstance(value, dict):
                raise ValueError("Backup entry must be an object")
            if set(value) == {"runs", "sha256"}:
                if value != {"runs": count, "sha256": sha.hexdigest()} or source.read(1):
                    raise ValueError("Backup checksum/count/trailing content differs")
                if verified is not None:
                    if verified and verified != value:
                        raise ValueError("Backup changed during restore")
                    verified.update(value)
                return
            normalized = _normalize(value)
            if normalized != value:
                raise ValueError("Backup contains unsupported fields")
            sha.update(line)
            count += 1
            yield normalized


def restore(archive, destination, *, context=LOCAL_CONTEXT, url=""):
    # Full validation precedes destination creation, then the insertion pass is
    # independently validated inside one transaction to catch archive changes.
    verified = {}
    expected_count = sum(1 for _ in _backup_values(archive, context, verified))
    destination = Path(destination)
    if not url:
        with _private_create(destination):
            pass
    with _open_destination(destination, url) as db:
        if url:
            # Refuse any existing user table, including other Studio services.
            if db.execute("SELECT 1 FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND LEFT(table_schema,3)<>'pg_' LIMIT 1").fetchone() or db.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name NOT IN ('public','pg_catalog','information_schema') AND LEFT(schema_name,3)<>'pg_' LIMIT 1").fetchone():
                raise ValueError("PostgreSQL restore destination must be a new empty database")
            db.commit()
        migrate_studio_database(db)
        with db:
            _lock_selection(db)
            # Only the fixed local bootstrap or an already provisioned trusted
            # membership may authorize restore; archive identity data is absent.
            from api_test.database import initialize_local_context
            if context == LOCAL_CONTEXT:
                initialize_local_context(db)
            else:
                # Identity comes only from the explicit trusted operator context,
                # never from a run, a header beyond its matching workspace, or JSON.
                now = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT INTO workspaces(id,name,created_at,updated_at) VALUES (?,?,?,?)",
                           (context.workspace_id, "Restored workspace", now, now))
                db.execute("INSERT INTO users(id,display_name,created_at,updated_at) VALUES (?,?,?,?)",
                           (context.user_id, "Restore operator", now, now))
                db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES (?,?,'owner',?)",
                           (context.workspace_id, context.user_id, now))
            _operator(db, context)
            target = LoadTestStore(destination, context=context, url=url)
            count = 0
            for value in _backup_values(archive, context, verified):
                target._insert_bundle(db, value)
                count += 1
            if count != expected_count:
                raise ValueError("Backup changed during restore")
    return {"restoredRuns": count, "workspace": context.workspace_id}


@contextmanager
def _open_destination(path, url):
    db = connect(path, url=url)
    try:
        yield db
    finally:
        db.close()


def _safe_root(root):
    root = Path(root).absolute()
    for part in (root, *root.parents):
        if part.is_symlink():
            raise ValueError("Artifact root and its ancestors must not be symlinks")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ValueError("Safe artifact removal requires POSIX no-follow directory descriptors")
    return root


@contextmanager
def _directory(root, relative="", expected=None):
    root = Path(root).absolute()
    descriptor = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in (*root.parts[1:], *Path(relative).parts):
            if name in ("", ".", "..") or "/" in name or "\\" in name:
                raise ValueError("Invalid artifact path")
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        if expected is not None and _identity(os.fstat(descriptor)) != expected:
            raise ValueError("Artifact directory changed during apply")
        yield descriptor
    finally:
        os.close(descriptor)


def _identity(status):
    return [status.st_dev, status.st_ino]


def _file_entry(descriptor, name, path):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Artifacts must contain only regular files and directories")
        sha = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as source:
            for data in iter(lambda: source.read(1024 * 1024), b""):
                sha.update(data)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("Artifact changed while reading")
        return {"path": path, "identity": _identity(after), "bytes": after.st_size, "sha256": sha.hexdigest()}
    finally:
        os.close(fd)


def _artifact_inventory(root, run_ids):
    with _directory(root) as root_fd:
        files, directories = [], []
        def walk(fd, relative):
            directories.append({"path": relative, "identity": _identity(os.fstat(fd))})
            for name in sorted(os.listdir(fd)):
                path = relative + "/" + name
                status = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(status.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, path)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(status.st_mode):
                    files.append(_file_entry(fd, name, path))
                else:
                    raise ValueError("Symlinks and special files are forbidden in artifact targets")
        for run_id in run_ids:
            if not run_id or any(c in run_id for c in ("/", "\\")) or run_id in (".", ".."):
                raise ValueError("Invalid artifact run ID")
            try:
                child = os.open(run_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            except FileNotFoundError:
                continue
            try:
                walk(child, run_id)
            finally:
                os.close(child)
        return {"rootIdentity": _identity(os.fstat(root_fd)), "files": files, "directories": directories}


def artifacts_preview(store, root, *, days=30, now=None):
    root = _safe_root(root)
    retention = retention_preview(store, days=days, now=now)
    inventory = _artifact_inventory(root, [row["id"] for row in retention["runs"]])
    return {"format": "studio-load-artifacts-v1", "root": str(root), "retention": retention, **inventory}


def artifacts_apply(store, root, manifest, *, confirmation):
    root = _safe_root(root)
    if _digest(manifest) != confirmation or manifest.get("format") != "studio-load-artifacts-v1" or manifest.get("root") != str(root):
        raise ValueError("Artifact manifest confirmation/root/format differs")
    retention = manifest["retention"]
    cutoff = _check_manifest(retention, _digest(retention), store.context)
    # Hold DB lock while applying so the authorizing workspace/run cannot change.
    with store.connection(write=True) as db, db:
        _lock_selection(db)
        _operator(db, store.context)
        if retention.get("source") != _source_identity(db, store):
            raise ValueError("Artifact manifest belongs to a different source database")
        if _selection(db, store, cutoff) != retention:
            raise ValueError("Artifact retention preview is stale")
        inventory = _artifact_inventory(root, [row["id"] for row in retention["runs"]])
        if any(inventory[key] != manifest[key] for key in ("rootIdentity", "files", "directories")):
            raise ValueError("Artifact inventory changed; create a new preview")
        # Atomically capture whole run directories in private quarantine before
        # checking them again. A replaced target is preserved, never unlinked.
        # Stop artifact writers; filesystem cleanup is intentionally separate
        # from SQL deletion and recoverable quarantine is reported on any failure.
        quarantine_name = ".studio-retention-" + os.urandom(12).hex()
        quarantine = root / quarantine_name
        captured, deleted = [], []
        top_dirs = [entry for entry in manifest["directories"] if "/" not in entry["path"]]
        with _directory(root, expected=manifest["rootIdentity"]) as root_fd:
            os.mkdir(quarantine_name, 0o700, dir_fd=root_fd)
            quarantine_fd = os.open(quarantine_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                for entry in top_dirs:
                    os.rename(entry["path"], entry["path"], src_dir_fd=root_fd, dst_dir_fd=quarantine_fd)
                    captured.append(entry["path"])
                captured_inventory = _artifact_inventory(quarantine, captured)
                if any(captured_inventory[key] != manifest[key] for key in ("files", "directories")):
                    raise ValueError("Artifact target changed while entering quarantine")
                directory_ids = {entry["path"]: entry["identity"] for entry in manifest["directories"]}
                for entry in manifest["files"]:
                    path = Path(entry["path"])
                    with _directory(quarantine, path.parent.as_posix(), expected=directory_ids[path.parent.as_posix()]) as fd:
                        if _file_entry(fd, path.name, entry["path"]) != entry:
                            raise ValueError("Quarantined artifact changed during apply")
                        os.unlink(path.name, dir_fd=fd)
                        deleted.append(entry["path"])
                for entry in reversed(manifest["directories"]):
                    path = Path(entry["path"])
                    with _directory(quarantine, path.parent.as_posix() if path.parent != Path(".") else "",
                                    expected=directory_ids.get(path.parent.as_posix(), captured_inventory["rootIdentity"])) as fd:
                        status = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
                        if _identity(status) != entry["identity"] or not stat.S_ISDIR(status.st_mode):
                            raise ValueError("Quarantined directory changed during apply")
                        os.rmdir(path.name, dir_fd=fd)
                os.rmdir(quarantine_name, dir_fd=root_fd)
            except (OSError, ValueError) as exc:
                raise ValueError("Artifact apply stopped; quarantine=" + str(quarantine) + "; capturedRuns=" +
                                 _json(captured) + "; deletedFiles=" + _json(deleted) +
                                 "; inspect retained quarantine and create a new preview") from exc
            finally:
                os.close(quarantine_fd)
    return {"deletedFiles": deleted, "deletedDirectories": [item["path"] for item in manifest["directories"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/studio.db"))
    parser.add_argument("--workspace", default=LOCAL_CONTEXT.workspace_id)
    parser.add_argument("--user", default=LOCAL_CONTEXT.user_id)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("retention-preview", "artifacts-preview"):
        command = sub.add_parser(name)
        command.add_argument("--days", type=int, default=30)
        command.add_argument("--output", type=Path, required=True)
    for name in ("retention-apply", "artifacts-apply"):
        command = sub.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--confirm-sha256", required=True)
    command = sub.add_parser("backup")
    command.add_argument("--output", type=Path, required=True)
    command = sub.add_parser("restore")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--destination", type=Path, required=True)
    command.add_argument("--postgres", action="store_true", help="Use configured URL, which must designate an empty isolated database")
    args = parser.parse_args()
    context = RequestContext(args.workspace, args.user)
    store = LoadTestStore(args.db, context=context)
    # Only deployment configuration selects the approved artifact root, never a manifest.
    root = Path(os.environ.get("STUDIO_LOAD_TEST_ARTIFACT_ROOT", "data/load-tests"))
    if args.command.endswith("preview"):
        manifest = (retention_preview(store, days=args.days) if args.command == "retention-preview" else
                    artifacts_preview(store, root, days=args.days))
        with _private_create(args.output, "w") as output:
            output.write(_json(manifest) + "\n")
        result = {"manifest": manifest, "sha256": _digest(manifest)}
    elif args.command.endswith("apply"):
        manifest = json.loads(args.manifest.read_text())
        result = (retention_apply(store, manifest, confirmation=args.confirm_sha256) if args.command == "retention-apply" else
                  artifacts_apply(store, root, manifest, confirmation=args.confirm_sha256))
    elif args.command == "backup":
        result = backup(store, args.output)
    else:
        from api_test.database import database_url
        url = database_url() if args.postgres else ""
        if args.postgres and not url:
            raise ValueError("PostgreSQL restore requires configured URL for an empty isolated destination")
        result = restore(args.archive, args.destination, context=context, url=url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
