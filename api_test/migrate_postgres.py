"""Offline, idempotent SQLite snapshot -> PostgreSQL import.

Stop writers before running. No source SQLite file is ever modified. Conflicting
or extra destination rows abort the entire data transaction instead of merging.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from api_test.database import connect, database_url
from api_test.identity_store import migrate_studio_with_identity
from api_test.release_store import migrate_studio_with_releases, source_hash
from api_test.migrations import migrate_studio_database, migrate_ownership_database

STUDIO_TABLES = ("workspaces", "users", "memberships", "user_identities", "documents",
                 "document_revisions", "audit_events", "executions", "load_test_runs",
                 "load_test_thresholds", "load_test_endpoint_metrics", "load_test_series", "security_events", "api_releases", "api_release_events", "api_release_artifacts")
OWNERSHIP_TABLES = ("proofs", "grants")
BOOTSTRAP_CONTEXT = {
    "workspaces": [("default", "Local workspace")],
    "users": [("local-user", "Local system user")],
    "memberships": [("default", "local-user", "owner")],
}


def migrate_integrated_studio(connection):
    migrate_studio_with_identity(connection)
    migrate_studio_with_releases(connection)


def snapshot(path, migrate):
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as source:
            source.backup(memory)
        migrate(memory)
        return memory
    except BaseException:
        memory.close()
        raise


def _digest(rows):
    encoded = sorted(json.dumps(dict(row), sort_keys=True, ensure_ascii=False, separators=(",", ":")) for row in rows)
    return hashlib.sha256("\n".join(encoded).encode()).hexdigest()


def clear_bootstrap_context(target) -> None:
    """Remove only the empty local context created by a first API startup.

    A target with documents, executions, ownership records, identities, or any
    context different from the fixed local bootstrap is a real destination and
    must retain the strict conflict check below.
    """
    for table in ("user_identities", "documents", "document_revisions", "audit_events", "executions", "load_test_runs", "security_events", "api_releases", "api_release_events", "api_release_artifacts", "oauth_tokens", "oauth_pending", *OWNERSHIP_TABLES):
        if target.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() is not None:
            return
    if target.execute("SELECT 1 FROM users WHERE status<>'active' UNION ALL SELECT 1 FROM workspaces WHERE status<>'active' UNION ALL SELECT 1 FROM memberships WHERE status<>'active' LIMIT 1").fetchone():
        return
    workspaces = [(row["id"], row["name"]) for row in target.execute("SELECT id, name FROM workspaces ORDER BY id")]
    users = [(row["id"], row["display_name"]) for row in target.execute("SELECT id, display_name FROM users ORDER BY id")]
    memberships = [(row["workspace_id"], row["user_id"], row["role"]) for row in target.execute("SELECT workspace_id, user_id, role FROM memberships ORDER BY workspace_id, user_id")]
    if {"workspaces": workspaces, "users": users, "memberships": memberships} != BOOTSTRAP_CONTEXT:
        return
    target.execute("DELETE FROM memberships")
    target.execute("DELETE FROM users")
    target.execute("DELETE FROM workspaces")


def migrate(studio_path, ownership_path, *, url=None):
    url = url or database_url()
    if not url:
        raise ValueError("STUDIO_DATABASE_URL or STUDIO_DATABASE_URL_FILE is required")
    with closing(snapshot(studio_path, migrate_integrated_studio)) as studio, \
            closing(snapshot(ownership_path, migrate_ownership_database)) as ownership, \
            closing(connect(Path("unused"), url=url)) as target:
        migrate_integrated_studio(target)
        migrate_ownership_database(target)
        manifest = {}
        with target:
            target.execute("BEGIN IMMEDIATE")
            clear_bootstrap_context(target)
            for source, tables in ((studio, STUDIO_TABLES), (ownership, OWNERSHIP_TABLES)):
                for table in tables:
                    rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                    columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
                    names = ", ".join(f'"{column}"' for column in columns)
                    placeholders = ", ".join("?" for _ in columns)
                    for row in rows:
                        target.execute(f'INSERT INTO "{table}" ({names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING', tuple(row))
                    actual = target.execute(f'SELECT {names} FROM "{table}"').fetchall()
                    expected_digest = _digest(rows)
                    if len(actual) != len(rows) or _digest(actual) != expected_digest:
                        raise ValueError(f"migration verification failed: {table}; destination differs from snapshot")
                    manifest[table] = {"rows": len(rows), "sha256": expected_digest}
            # Verify content itself, not only the copied hash field.
            for row in target.execute("SELECT content, content_hash FROM document_revisions"):
                canonical = json.dumps(json.loads(row["content"]), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if hashlib.sha256(canonical.encode()).hexdigest() != row["content_hash"]:
                    raise ValueError("migration verification failed: revision content hash")
            for release in target.execute('SELECT source_json,source_digest FROM api_releases'):
                if source_hash(json.loads(release['source_json'])) != release['source_digest']:
                    raise ValueError('migration verification failed: release source hash')
            if target.execute('SELECT r.id FROM api_releases r JOIN documents d ON d.id=r.project_id WHERE r.workspace_id<>d.workspace_id OR r.project_reference<>d.reference').fetchone():
                raise ValueError('migration verification failed: release workspace')
            if target.execute('SELECT e.id FROM api_release_events e JOIN api_releases r ON r.id=e.release_id WHERE e.workspace_id<>r.workspace_id').fetchone():
                raise ValueError('migration verification failed: release event workspace')
            for artifact in target.execute('SELECT a.*,r.source_digest AS release_digest,r.workspace_id AS release_workspace FROM api_release_artifacts a JOIN api_releases r ON r.id=a.release_id'):
                if artifact['source_digest']!=artifact['release_digest'] or artifact['workspace_id']!=artifact['release_workspace']:
                    raise ValueError('migration verification failed: SDK source digest')
                if artifact['purged_at'] is None:
                    content=base64.b64decode(artifact['payload_base64'],validate=True)
                    if len(content)!=artifact['size_bytes'] or hashlib.sha256(content).hexdigest()!=artifact['sha256']:
                        raise ValueError('migration verification failed: SDK bytes')
            invalid = target.execute("SELECT d.id FROM documents d LEFT JOIN document_revisions r ON r.document_id=d.id AND r.revision=d.current_revision WHERE r.document_id IS NULL OR r.content_hash<>d.content_hash").fetchone()
            if invalid:
                raise ValueError("migration verification failed: current revision")
            target.execute("SELECT setval(pg_get_serial_sequence('audit_events','id'), COALESCE((SELECT MAX(id) FROM audit_events), 1), EXISTS(SELECT 1 FROM audit_events))")
            target.execute("INSERT INTO projection_jobs(document_id,revision) SELECT id,current_revision FROM documents ON CONFLICT(document_id) DO UPDATE SET revision=excluded.revision,status='pending'")
            # Authentication transactions and browser sessions are intentionally not migrated.
            target.execute('DELETE FROM oauth_pending')
            target.execute('DELETE FROM oauth_tokens')
            target.execute('DELETE FROM oidc_login_states')
            target.execute('DELETE FROM login_sessions')
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.studio, args.ownership), indent=2))


if __name__ == "__main__":
    main()
