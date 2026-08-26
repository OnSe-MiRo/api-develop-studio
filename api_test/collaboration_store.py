"""Versioned SQLite persistence for collaborative studio documents.

The database is the source of truth for the web studio. JSON files are kept as
runtime projections so the existing CLI and repository layout remain
compatible.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


DOCUMENT_KINDS = ("projects", "cases", "pipelines")
DEFAULT_WORKSPACE_ID = "default"
DEFAULT_ACTOR_ID = "local-user"


class CollaborationStoreError(ValueError):
    """Base error raised by the collaboration store."""


class DocumentNotFoundError(CollaborationStoreError):
    pass


class RevisionConflictError(CollaborationStoreError):
    def __init__(self, expected_revision: int, current_revision: int) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__(
            f"문서가 다른 사용자에 의해 변경되었습니다. "
            f"현재 리비전은 {current_revision}, 편집 기준 리비전은 {expected_revision}입니다. "
            "최신 내용을 다시 불러온 뒤 변경사항을 적용하세요."
        )


class RevisionRequiredError(CollaborationStoreError):
    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision
        super().__init__(
            f"기존 문서를 저장하려면 편집 기준 리비전이 필요합니다. 현재 리비전은 {current_revision}입니다. "
            "문서를 다시 불러온 뒤 저장하세요."
        )


@dataclass(frozen=True)
class StoredDocument:
    document_id: str
    kind: str
    reference: str
    revision: int
    document: dict[str, object]
    created_at: str
    updated_at: str

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.document_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical_json(document: dict[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(document: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


class CollaborationStore:
    """Store immutable document revisions and materialize the current JSON."""

    def __init__(self, database_path: Path, roots: Mapping[str, Path]) -> None:
        self.database_path = database_path
        self.roots = {kind: Path(roots[kind]) for kind in DOCUMENT_KINDS}
        self._schema_lock = threading.Lock()
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self, import_existing: bool = True) -> None:
        with self._schema_lock:
            if not self._initialized:
                with closing(self.connect()) as connection, connection:
                    connection.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS workspaces (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS users (
                            id TEXT PRIMARY KEY,
                            display_name TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS memberships (
                            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                            user_id TEXT NOT NULL REFERENCES users(id),
                            role TEXT NOT NULL CHECK(role IN ('owner', 'admin', 'editor', 'runner', 'viewer')),
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (workspace_id, user_id)
                        );
                        CREATE TABLE IF NOT EXISTS documents (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                            kind TEXT NOT NULL CHECK(kind IN ('projects', 'cases', 'pipelines')),
                            reference TEXT NOT NULL,
                            project_reference TEXT,
                            current_revision INTEGER NOT NULL,
                            content_hash TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            deleted_at TEXT,
                            UNIQUE (workspace_id, kind, reference)
                        );
                        CREATE TABLE IF NOT EXISTS document_revisions (
                            document_id TEXT NOT NULL REFERENCES documents(id),
                            revision INTEGER NOT NULL,
                            content TEXT NOT NULL,
                            content_hash TEXT NOT NULL,
                            created_by TEXT NOT NULL REFERENCES users(id),
                            created_at TEXT NOT NULL,
                            PRIMARY KEY (document_id, revision)
                        );
                        CREATE TABLE IF NOT EXISTS audit_events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                            document_id TEXT NOT NULL REFERENCES documents(id),
                            action TEXT NOT NULL,
                            revision INTEGER,
                            actor_id TEXT NOT NULL REFERENCES users(id),
                            detail TEXT,
                            created_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS documents_project_idx
                            ON documents(workspace_id, kind, project_reference, deleted_at);
                        CREATE INDEX IF NOT EXISTS revisions_document_idx
                            ON document_revisions(document_id, revision DESC);
                        """
                    )
                    now = utc_now()
                    connection.execute(
                        "INSERT OR IGNORE INTO workspaces(id, name, created_at) VALUES (?, ?, ?)",
                        (DEFAULT_WORKSPACE_ID, "기본 워크스페이스", now),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO users(id, display_name, created_at) VALUES (?, ?, ?)",
                        (DEFAULT_ACTOR_ID, "로컬 사용자", now),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO memberships(workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                        (DEFAULT_WORKSPACE_ID, DEFAULT_ACTOR_ID, "owner", now),
                    )
                self._initialized = True
            if import_existing:
                self.import_existing_files()

    def ensure_actor(self, connection: sqlite3.Connection, actor_id: str) -> str:
        normalized = actor_id.strip() or DEFAULT_ACTOR_ID
        now = utc_now()
        connection.execute(
            "INSERT OR IGNORE INTO users(id, display_name, created_at) VALUES (?, ?, ?)",
            (normalized, normalized, now),
        )
        connection.execute(
            "INSERT OR IGNORE INTO memberships(workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (DEFAULT_WORKSPACE_ID, normalized, "editor", now),
        )
        return normalized

    def import_existing_files(self) -> None:
        """Import new or externally changed JSON files as immutable revisions."""
        for kind, root in self.roots.items():
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.json")):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(document, dict):
                    continue
                reference = path.relative_to(root).as_posix()
                current = self.get(kind, reference, include_deleted=True)
                if current is None:
                    self.save(
                        kind,
                        reference,
                        document,
                        actor_id=DEFAULT_ACTOR_ID,
                        action="import",
                        materialize=False,
                    )
                elif self.get(kind, reference) is None or current.document != document:
                    self.save(
                        kind,
                        reference,
                        document,
                        expected_revision=current.revision,
                        actor_id=DEFAULT_ACTOR_ID,
                        action="filesystem_import",
                        materialize=False,
                    )

    def list_references(self, kind: str, project_reference: str | None = None) -> list[str]:
        self._validate_kind(kind)
        query = "SELECT reference FROM documents WHERE workspace_id = ? AND kind = ? AND deleted_at IS NULL"
        parameters: list[object] = [DEFAULT_WORKSPACE_ID, kind]
        if project_reference is not None:
            query += " AND project_reference = ?"
            parameters.append(project_reference)
        query += " ORDER BY reference"
        with closing(self.connect()) as connection, connection:
            return [row["reference"] for row in connection.execute(query, parameters)]

    def get(self, kind: str, reference: str, include_deleted: bool = False) -> StoredDocument | None:
        self._validate_kind(kind)
        deleted_filter = "" if include_deleted else " AND d.deleted_at IS NULL"
        with closing(self.connect()) as connection, connection:
            row = connection.execute(
                f"""
                SELECT d.id, d.kind, d.reference, d.current_revision, d.created_at, d.updated_at, r.content
                FROM documents d
                JOIN document_revisions r ON r.document_id = d.id AND r.revision = d.current_revision
                WHERE d.workspace_id = ? AND d.kind = ? AND d.reference = ?{deleted_filter}
                """,
                (DEFAULT_WORKSPACE_ID, kind, reference),
            ).fetchone()
        return self._stored_document(row) if row else None

    def save(
        self,
        kind: str,
        reference: str,
        document: dict[str, object],
        expected_revision: int | None = None,
        actor_id: str = DEFAULT_ACTOR_ID,
        action: str = "save",
        materialize: bool = True,
    ) -> StoredDocument:
        self._validate_kind(kind)
        if not isinstance(document, dict):
            raise CollaborationStoreError("저장할 문서는 JSON 객체여야 합니다.")
        digest = content_hash(document)
        now = utc_now()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            actor_id = self.ensure_actor(connection, actor_id)
            row = connection.execute(
                """
                SELECT id, current_revision, content_hash, created_at, updated_at, deleted_at
                FROM documents
                WHERE workspace_id = ? AND kind = ? AND reference = ?
                """,
                (DEFAULT_WORKSPACE_ID, kind, reference),
            ).fetchone()
            if row:
                current_revision = int(row["current_revision"])
                if expected_revision is None and action == "save":
                    raise RevisionRequiredError(current_revision)
                if expected_revision is not None and expected_revision != current_revision:
                    raise RevisionConflictError(expected_revision, current_revision)
                if row["content_hash"] == digest and row["deleted_at"] is None:
                    return StoredDocument(
                        document_id=row["id"],
                        kind=kind,
                        reference=reference,
                        revision=current_revision,
                        document=document,
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                document_id = row["id"]
                revision = current_revision + 1
                connection.execute(
                    """
                    UPDATE documents
                    SET project_reference = ?, current_revision = ?, content_hash = ?, updated_at = ?, deleted_at = NULL
                    WHERE id = ?
                    """,
                    (self._project_reference(kind, reference, document), revision, digest, now, document_id),
                )
                created_at = row["created_at"]
            else:
                if expected_revision not in (None, 0):
                    raise RevisionConflictError(expected_revision, 0)
                document_id = f"doc_{uuid.uuid4().hex}"
                revision = 1
                created_at = now
                connection.execute(
                    """
                    INSERT INTO documents(
                        id, workspace_id, kind, reference, project_reference, current_revision,
                        content_hash, created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        document_id,
                        DEFAULT_WORKSPACE_ID,
                        kind,
                        reference,
                        self._project_reference(kind, reference, document),
                        revision,
                        digest,
                        created_at,
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO document_revisions(document_id, revision, content, content_hash, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (document_id, revision, canonical_json(document), digest, actor_id, now),
            )
            connection.execute(
                """
                INSERT INTO audit_events(workspace_id, document_id, action, revision, actor_id, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (DEFAULT_WORKSPACE_ID, document_id, action, revision, actor_id, reference, now),
            )
            if materialize:
                self._write_projection(kind, reference, document)
        return StoredDocument(document_id, kind, reference, revision, document, created_at, now)

    def delete(self, kind: str, reference: str, actor_id: str = DEFAULT_ACTOR_ID) -> StoredDocument:
        current = self.get(kind, reference)
        if current is None:
            raise DocumentNotFoundError("JSON file not found")
        now = utc_now()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            actor_id = self.ensure_actor(connection, actor_id)
            connection.execute("UPDATE documents SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, current.document_id))
            connection.execute(
                """
                INSERT INTO audit_events(workspace_id, document_id, action, revision, actor_id, detail, created_at)
                VALUES (?, ?, 'delete', ?, ?, ?, ?)
                """,
                (DEFAULT_WORKSPACE_ID, current.document_id, current.revision, actor_id, reference, now),
            )
            path = self._projection_path(kind, reference)
            if path.is_file():
                path.unlink()
        return current

    def revisions(self, kind: str, reference: str) -> list[dict[str, object]]:
        current = self.get(kind, reference, include_deleted=True)
        if current is None:
            raise DocumentNotFoundError("JSON file not found")
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT revision, created_by, created_at, content_hash
                FROM document_revisions WHERE document_id = ? ORDER BY revision DESC
                """,
                (current.document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _projection_path(self, kind: str, reference: str) -> Path:
        root = self.roots[kind].resolve()
        candidate = (root / reference).resolve()
        if root not in candidate.parents or candidate.suffix.lower() != ".json":
            raise CollaborationStoreError("Invalid JSON file path")
        return candidate

    def _write_projection(self, kind: str, reference: str, document: dict[str, object]) -> None:
        path = self._projection_path(kind, reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        finally:
            temporary_path = Path(temporary_name)
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _project_reference(kind: str, reference: str, document: dict[str, object]) -> str | None:
        if kind == "projects":
            return reference
        project = document.get("project")
        return project if isinstance(project, str) else None

    @staticmethod
    def _stored_document(row: sqlite3.Row) -> StoredDocument:
        return StoredDocument(
            document_id=row["id"],
            kind=row["kind"],
            reference=row["reference"],
            revision=int(row["current_revision"]),
            document=json.loads(row["content"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in DOCUMENT_KINDS:
            raise CollaborationStoreError(f"지원하지 않는 문서 종류입니다: {kind}")
