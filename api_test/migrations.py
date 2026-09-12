"""Ordered, transactional SQLite schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass


MigrationOperation = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationOperation


class MigrationRunner:
    """Apply each migration once and roll the complete run back on failure."""

    def __init__(self, migrations: Sequence[Migration]) -> None:
        self.migrations = tuple(sorted(migrations, key=lambda item: item.version))
        versions = [item.version for item in self.migrations]
        if versions != list(range(1, len(versions) + 1)):
            raise ValueError("migration versions must be consecutive and start at 1")

    def run(self, connection: sqlite3.Connection) -> int:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            applied = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            unknown = applied - {item.version for item in self.migrations}
            if unknown:
                raise sqlite3.DatabaseError(
                    f"database has unsupported migration versions: {sorted(unknown)}"
                )
            for migration in self.migrations:
                if migration.version in applied:
                    continue
                migration.apply(connection)
                connection.execute(
                    "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return self.migrations[-1].version if self.migrations else 0


def _create_collaboration_schema(connection: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS memberships (
            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            role TEXT NOT NULL CHECK(role IN ('owner', 'admin', 'editor', 'runner', 'viewer')),
            created_at TEXT NOT NULL, PRIMARY KEY (workspace_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            kind TEXT NOT NULL CHECK(kind IN ('projects', 'cases', 'pipelines')),
            reference TEXT NOT NULL, project_reference TEXT, current_revision INTEGER NOT NULL,
            content_hash TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            deleted_at TEXT, UNIQUE (workspace_id, kind, reference))""",
        """CREATE TABLE IF NOT EXISTS document_revisions (
            document_id TEXT NOT NULL REFERENCES documents(id), revision INTEGER NOT NULL,
            content TEXT NOT NULL, content_hash TEXT NOT NULL,
            created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
            PRIMARY KEY (document_id, revision))""",
        """CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            document_id TEXT NOT NULL REFERENCES documents(id), action TEXT NOT NULL,
            revision INTEGER, actor_id TEXT NOT NULL REFERENCES users(id),
            detail TEXT, created_at TEXT NOT NULL)""",
        """CREATE INDEX IF NOT EXISTS documents_project_idx
            ON documents(workspace_id, kind, project_reference, deleted_at)""",
        """CREATE INDEX IF NOT EXISTS revisions_document_idx
            ON document_revisions(document_id, revision DESC)""",
    )
    for statement in statements:
        connection.execute(statement)


def _create_execution_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS executions (
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
            duration_ms REAL NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
            projects TEXT NOT NULL, targets TEXT NOT NULL)"""
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS executions_started ON executions(started_at)"
    )


STUDIO_MIGRATIONS = (
    Migration(1, "collaboration schema", _create_collaboration_schema),
    Migration(2, "execution history schema", _create_execution_schema),
)


def migrate_studio_database(connection: sqlite3.Connection) -> int:
    return MigrationRunner(STUDIO_MIGRATIONS).run(connection)


def _create_ownership_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS proofs (
            project TEXT, origin TEXT, fingerprint TEXT, id TEXT UNIQUE,
            session_hash TEXT, token_hash TEXT, state TEXT, issued REAL,
            verified REAL, last_used REAL, attempts INTEGER DEFAULT 0,
            PRIMARY KEY(project, origin))"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS grants (
            project TEXT, url TEXT, method TEXT, last_used REAL DEFAULT 0,
            PRIMARY KEY(project, url, method))"""
    )


OWNERSHIP_MIGRATIONS = (Migration(1, "ownership schema", _create_ownership_schema),)


def migrate_ownership_database(connection: sqlite3.Connection) -> int:
    return MigrationRunner(OWNERSHIP_MIGRATIONS).run(connection)
