"""Ordered, transactional Studio and ownership schema migrations."""

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

    def run(self, connection: sqlite3.Connection, table: str = "schema_migrations") -> int:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {table} (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            applied = {
                row[0] for row in connection.execute(f"SELECT version FROM {table}")
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
                    f"INSERT INTO {table}(version, name) VALUES (?, ?)",
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


def _create_context_schema(connection):
    for statement in (
        "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN updated_at TEXT",
        "ALTER TABLE workspaces ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE workspaces ADD COLUMN updated_at TEXT",
        "ALTER TABLE memberships ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "CREATE TABLE user_identities (user_id TEXT NOT NULL REFERENCES users(id), provider TEXT NOT NULL, provider_subject TEXT NOT NULL, PRIMARY KEY(provider, provider_subject))",
        "ALTER TABLE documents ADD COLUMN created_by TEXT REFERENCES users(id)",
        "ALTER TABLE documents ADD COLUMN updated_by TEXT REFERENCES users(id)",
        "ALTER TABLE documents ADD COLUMN deleted_by TEXT REFERENCES users(id)",
        "ALTER TABLE executions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'",
        "ALTER TABLE executions ADD COLUMN requested_by TEXT NOT NULL DEFAULT 'local-user'",
        "ALTER TABLE executions ADD COLUMN retention_until TEXT",
        "ALTER TABLE audit_events ADD COLUMN request_id TEXT",
        "CREATE TABLE projection_jobs (document_id TEXT PRIMARY KEY REFERENCES documents(id), revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending')",
        "CREATE INDEX executions_workspace_started ON executions(workspace_id, started_at)",
        "UPDATE users SET updated_at = created_at",
        "UPDATE workspaces SET updated_at = created_at",
        "UPDATE documents SET created_by = (SELECT created_by FROM document_revisions WHERE document_id = documents.id AND revision = 1), updated_by = (SELECT created_by FROM document_revisions WHERE document_id = documents.id AND revision = documents.current_revision)",
        "UPDATE documents SET deleted_by = (SELECT actor_id FROM audit_events WHERE document_id=documents.id AND action='delete' ORDER BY id DESC LIMIT 1) WHERE deleted_at IS NOT NULL",
    ):
        connection.execute(statement)
    if getattr(connection, "dialect", "") == "postgresql":
        connection.execute("CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit events are append-only'; END; $$")
        connection.execute("CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()")



STUDIO_MIGRATIONS = (
    Migration(1, "collaboration schema", _create_collaboration_schema),
    Migration(2, "execution history schema", _create_execution_schema),
    Migration(3, "request context and projection recovery", _create_context_schema),
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


def _scope_ownership_schema(connection):
    connection.execute("CREATE TABLE proofs_scoped (project TEXT, origin TEXT, fingerprint TEXT, id TEXT UNIQUE, session_hash TEXT, token_hash TEXT, state TEXT, issued REAL, verified REAL, last_used REAL, attempts INTEGER DEFAULT 0, workspace_id TEXT NOT NULL DEFAULT 'default', PRIMARY KEY(workspace_id,project,origin))")
    connection.execute("INSERT INTO proofs_scoped(project,origin,fingerprint,id,session_hash,token_hash,state,issued,verified,last_used,attempts) SELECT project,origin,fingerprint,id,session_hash,token_hash,state,issued,verified,last_used,attempts FROM proofs")
    connection.execute("DROP TABLE proofs")
    connection.execute("ALTER TABLE proofs_scoped RENAME TO proofs")
    connection.execute("CREATE TABLE grants_scoped (project TEXT, url TEXT, method TEXT, last_used REAL DEFAULT 0, workspace_id TEXT NOT NULL DEFAULT 'default', PRIMARY KEY(workspace_id,project,url,method))")
    connection.execute("INSERT INTO grants_scoped(project,url,method,last_used) SELECT project,url,method,last_used FROM grants")
    connection.execute("DROP TABLE grants")
    connection.execute("ALTER TABLE grants_scoped RENAME TO grants")


OWNERSHIP_MIGRATIONS = (
    Migration(1, "ownership schema", _create_ownership_schema),
    Migration(2, "workspace scoped ownership", _scope_ownership_schema),
)


def migrate_ownership_database(connection: sqlite3.Connection) -> int:
    return MigrationRunner(OWNERSHIP_MIGRATIONS).run(
        connection, "ownership_schema_migrations" if getattr(connection, "dialect", "") == "postgresql" else "schema_migrations"
    )
