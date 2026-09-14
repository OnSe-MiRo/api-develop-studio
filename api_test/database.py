"""Connection boundary shared by SQLite compatibility and PostgreSQL stores.

SQL in repositories uses qmark parameters. The PostgreSQL adapter supports that
small, fixed SQL subset; it never interpolates parameter values into SQL.
"""
from __future__ import annotations

import atexit
import os
import sqlite3
import threading
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone


@dataclass(frozen=True)
class RequestContext:
    workspace_id: str
    user_id: str
    request_id: str | None = None

    def __post_init__(self):
        if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in (self.workspace_id, self.user_id)):
            raise ValueError("Invalid server request context")


LOCAL_CONTEXT = RequestContext("default", "local-user")
_pools = {}
_pool_lock = threading.Lock()


def database_url() -> str:
    secret_file = os.environ.get("STUDIO_DATABASE_URL_FILE")
    if secret_file:
        value = Path(secret_file).read_text().strip()
        if not value:
            raise ValueError("Database URL secret file is empty")
        return value
    return os.environ.get("STUDIO_DATABASE_URL", "")


def postgres_enabled() -> bool:
    return bool(database_url())


class Record(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def _record_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Record(zip(names, values))


class PostgresConnection:
    dialect = "postgresql"

    def __init__(self, pool):
        self.pool = pool
        self.raw = pool.getconn(timeout=10)

    def execute(self, sql, parameters=()):
        if sql.strip() == "BEGIN IMMEDIATE":
            # Preserve SQLite's serialized write semantics, including create races.
            # Read-only queries do not take this transaction-scoped lock.
            return self.raw.execute("SELECT pg_advisory_xact_lock(71404001)")
        sql = sql.replace("?", "%s")
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        sql = sql.replace(" REAL", " DOUBLE PRECISION")
        if "INSERT OR IGNORE INTO" in sql:
            sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO") + " ON CONFLICT DO NOTHING"
        return self.raw.execute(sql, parameters)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        if self.raw is not None:
            try:
                self.raw.rollback()
            finally:
                self.pool.putconn(self.raw)
                self.raw = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.rollback() if exc_type else self.commit()


def connect(path: Path, *, url: str | None = None):
    url = database_url() if url is None else url
    if not url:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        return connection
    from psycopg_pool import ConnectionPool
    with _pool_lock:
        if url not in _pools:
            pool = ConnectionPool(
                url, min_size=1, max_size=5, open=True, timeout=10,
                check=ConnectionPool.check_connection,
                kwargs={"row_factory": _record_factory, "connect_timeout": 5,
                        "options": "-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=15000 -c transaction_timeout=30000"},
            )
            _pools[url] = pool
            atexit.register(pool.close)
        pool = _pools[url]
    return PostgresConnection(pool)


def require_membership(connection, context, *, write=False):
    row = connection.execute(
        "SELECT m.role FROM memberships m JOIN users u ON u.id=m.user_id "
        "JOIN workspaces w ON w.id=m.workspace_id WHERE m.workspace_id=? AND m.user_id=? "
        "AND m.status='active' AND u.status='active' AND w.status='active'",
        (context.workspace_id, context.user_id),
    ).fetchone()
    if row is None or (write and row["role"] not in ("owner", "admin", "editor")):
        raise PermissionError("Active workspace membership with the required role is required")

try:
    from psycopg import Error as PostgresError
    from psycopg_pool import PoolTimeout
    DATABASE_ERRORS = (sqlite3.Error, PostgresError, PoolTimeout)
except ImportError:
    DATABASE_ERRORS = (sqlite3.Error,)


def initialize_local_context(connection):
    """Bootstrap only the fixed server-side local identity; never reactivate it."""
    now = datetime.now(timezone.utc).isoformat()
    connection.execute("INSERT OR IGNORE INTO workspaces(id,name,created_at,updated_at) VALUES (?,?,?,?)",
                       (LOCAL_CONTEXT.workspace_id, "Local workspace", now, now))
    connection.execute("INSERT OR IGNORE INTO users(id,display_name,created_at,updated_at) VALUES (?,?,?,?)",
                       (LOCAL_CONTEXT.user_id, "Local system user", now, now))
    connection.execute("INSERT OR IGNORE INTO memberships(workspace_id,user_id,role,created_at) VALUES (?,?,'owner',?)",
                       (LOCAL_CONTEXT.workspace_id, LOCAL_CONTEXT.user_id, now))
