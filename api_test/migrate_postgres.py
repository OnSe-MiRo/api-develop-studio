"""Offline, idempotent SQLite snapshot -> PostgreSQL import.

Stop writers before running. No source SQLite file is ever modified. Conflicting
or extra destination rows abort the entire data transaction instead of merging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from api_test.database import connect, database_url
from api_test.migrations import migrate_studio_database, migrate_ownership_database

STUDIO_TABLES = ("workspaces", "users", "memberships", "user_identities", "documents",
                 "document_revisions", "audit_events", "executions")
OWNERSHIP_TABLES = ("proofs", "grants")


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


def migrate(studio_path, ownership_path, *, url=None):
    url = url or database_url()
    if not url:
        raise ValueError("STUDIO_DATABASE_URL or STUDIO_DATABASE_URL_FILE is required")
    with closing(snapshot(studio_path, migrate_studio_database)) as studio, \
            closing(snapshot(ownership_path, migrate_ownership_database)) as ownership, \
            closing(connect(Path("unused"), url=url)) as target:
        migrate_studio_database(target)
        migrate_ownership_database(target)
        manifest = {}
        with target:
            target.execute("BEGIN IMMEDIATE")
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
            invalid = target.execute("SELECT d.id FROM documents d LEFT JOIN document_revisions r ON r.document_id=d.id AND r.revision=d.current_revision WHERE r.document_id IS NULL OR r.content_hash<>d.content_hash").fetchone()
            if invalid:
                raise ValueError("migration verification failed: current revision")
            target.execute("SELECT setval(pg_get_serial_sequence('audit_events','id'), COALESCE((SELECT MAX(id) FROM audit_events), 1), EXISTS(SELECT 1 FROM audit_events))")
            target.execute("INSERT INTO projection_jobs(document_id,revision) SELECT id,current_revision FROM documents ON CONFLICT(document_id) DO UPDATE SET revision=excluded.revision,status='pending'")
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio", type=Path, required=True)
    parser.add_argument("--ownership", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.studio, args.ownership), indent=2))


if __name__ == "__main__":
    main()
