"""Versioned database persistence for collaborative studio documents.

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

from api_test.migrations import migrate_studio_database
from api_test.database import connect, RequestContext, LOCAL_CONTEXT, postgres_enabled, require_membership, initialize_local_context
from api_test.cache import RevisionCache


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
    projection_pending: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.document_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            **({"projectionPending": True} if self.projection_pending else {}),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical_json(document: dict[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(document: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


class CollaborationStore:
    """Store immutable document revisions and materialize the current JSON."""

    def __init__(self, database_path: Path, roots: Mapping[str, Path], *, context: RequestContext = LOCAL_CONTEXT) -> None:
        self.database_path = database_path
        self.context = context
        self.cache = RevisionCache()
        self.roots = {kind: (Path(roots[kind]) if context.workspace_id == LOCAL_CONTEXT.workspace_id else Path(roots[kind]) / "_workspaces" / context.workspace_id) for kind in DOCUMENT_KINDS}
        self._schema_lock = threading.Lock()
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        connection = connect(self.database_path)
        if postgres_enabled():
            try:
                require_membership(connection, self.context)
                connection.commit()
            except BaseException:
                connection.close()
                raise
        return connection

    def initialize(self, import_existing: bool = True) -> None:
        with self._schema_lock:
            if not self._initialized:
                with closing(connect(self.database_path)) as connection, connection:
                    migrate_studio_database(connection)
                    initialize_local_context(connection)
                self._initialized = True
            if postgres_enabled() and not self._has_documents() and self.database_path.exists():
                with closing(sqlite3.connect(self.database_path.resolve().as_uri() + "?mode=ro", uri=True)) as legacy:
                    has_table = legacy.execute("SELECT 1 FROM sqlite_master WHERE name='documents'").fetchone()
                    if has_table and legacy.execute("SELECT 1 FROM documents LIMIT 1").fetchone():
                        raise CollaborationStoreError("기존 SQLite 이력이 있습니다. api_test.migrate_postgres로 먼저 이관하세요.")
            # Files are a one-time bootstrap in PostgreSQL, never an authority on restart.
            if import_existing and (not postgres_enabled() or not self._has_documents()):
                self.import_existing_files()
            self.repair_projections()

    def _has_documents(self):
        with closing(self.connect()) as connection, connection:
            return connection.execute("SELECT 1 FROM documents WHERE workspace_id = ? LIMIT 1", (self.context.workspace_id,)).fetchone() is not None

    def ensure_actor(self, connection: sqlite3.Connection, actor_id: str) -> str:
        if postgres_enabled():
            require_membership(connection, self.context, write=True)
            return self.context.user_id
        normalized = actor_id.strip() or DEFAULT_ACTOR_ID
        now = utc_now()
        connection.execute(
            "INSERT OR IGNORE INTO users(id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (normalized, normalized, now, now),
        )
        connection.execute(
            "INSERT OR IGNORE INTO memberships(workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (self.context.workspace_id, normalized, "editor", now),
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
                if reference.startswith("_workspaces/"):
                    continue
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
        parameters: list[object] = [self.context.workspace_id, kind]
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
                (self.context.workspace_id, kind, reference),
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
        self._projection_path(kind, reference)
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
                (self.context.workspace_id, kind, reference),
            ).fetchone()
            if row:
                current_revision = int(row["current_revision"])
                if expected_revision is None and action == "save":
                    raise RevisionRequiredError(current_revision)
                if expected_revision is not None and expected_revision != current_revision:
                    raise RevisionConflictError(expected_revision, current_revision)
                if row["content_hash"] == digest and row["deleted_at"] is None:
                    connection.commit()
                    pending = self.repair_projections(row["id"]) if materialize else False
                    return StoredDocument(
                        document_id=row["id"],
                        kind=kind,
                        reference=reference,
                        revision=current_revision,
                        document=document,
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        projection_pending=pending,
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
                        self.context.workspace_id,
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
                INSERT INTO audit_events(workspace_id, document_id, action, revision, actor_id, detail, created_at, request_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (self.context.workspace_id, document_id, action, revision, actor_id, reference, now, self.context.request_id or uuid.uuid4().hex),
            )
            connection.execute(
                "UPDATE documents SET created_by = COALESCE(created_by, ?), updated_by = ?, deleted_by = NULL WHERE id = ? AND workspace_id = ?",
                (actor_id, actor_id, document_id, self.context.workspace_id),
            )
            if materialize:
                self._queue_projection(connection, document_id, revision)
        self.cache.invalidate(self.cache.key(self.context.workspace_id, document_id, revision - 1))
        pending = self.repair_projections(document_id) if materialize else False
        return StoredDocument(document_id, kind, reference, revision, document, created_at, now, pending)

    def delete(self, kind: str, reference: str, actor_id: str = DEFAULT_ACTOR_ID) -> StoredDocument:
        self._validate_kind(kind)
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT d.id, d.kind, d.reference, d.current_revision, d.created_at, d.updated_at, r.content "
                "FROM documents d JOIN document_revisions r ON r.document_id=d.id AND r.revision=d.current_revision "
                "WHERE d.workspace_id=? AND d.kind=? AND d.reference=? AND d.deleted_at IS NULL",
                (self.context.workspace_id, kind, reference),
            ).fetchone()
            if row is None:
                raise DocumentNotFoundError("JSON file not found")
            current = self._stored_document(row)
            actor_id = self.ensure_actor(connection, actor_id)
            now = utc_now()
            connection.execute("UPDATE documents SET deleted_at=?, updated_at=?, deleted_by=?, updated_by=? WHERE id=? AND workspace_id=?",
                               (now, now, actor_id, actor_id, current.document_id, self.context.workspace_id))
            connection.execute(
                "INSERT INTO audit_events(workspace_id, document_id, action, revision, actor_id, detail, created_at, request_id) VALUES (?, ?, 'delete', ?, ?, ?, ?, ?)",
                (self.context.workspace_id, current.document_id, current.revision, actor_id, reference, now, self.context.request_id or uuid.uuid4().hex),
            )
            self._queue_projection(connection, current.document_id, current.revision)
        self.cache.invalidate(self.cache.key(self.context.workspace_id, current.document_id, current.revision))
        self.repair_projections(current.document_id)
        return current

    @staticmethod
    def _queue_projection(connection, document_id, revision):
        connection.execute(
            "INSERT INTO projection_jobs(document_id, revision, status) VALUES (?, ?, 'pending') "
            "ON CONFLICT(document_id) DO UPDATE SET revision=excluded.revision, status='pending'",
            (document_id, revision),
        )

    def repair_projections(self, document_id=None):
        """Replay latest committed state; a durable pending row survives any failure.

        A write lock serializes repair with newer commits and other repairers.
        File failure never rolls back the earlier document/revision/audit commit.
        """
        pending = False
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            query = ("SELECT d.id, d.kind, d.reference, d.deleted_at, r.content FROM projection_jobs p "
                     "JOIN documents d ON d.id=p.document_id JOIN document_revisions r "
                     "ON r.document_id=d.id AND r.revision=d.current_revision WHERE d.workspace_id=?")
            params = [self.context.workspace_id]
            if document_id:
                query += " AND d.id=?"
                params.append(document_id)
            for row in connection.execute(query, params).fetchall():
                try:
                    if row["deleted_at"] is not None:
                        self._projection_path(row["kind"], row["reference"]).unlink(missing_ok=True)
                    else:
                        self._write_projection(row["kind"], row["reference"], json.loads(row["content"]))
                except OSError:
                    pending = True
                    # Do not persist filesystem error messages (paths may be sensitive).
                    connection.execute("UPDATE projection_jobs SET status='failed' WHERE document_id=?", (row["id"],))
                else:
                    connection.execute("DELETE FROM projection_jobs WHERE document_id=?", (row["id"],))

        return pending

    def revision_document(self, kind: str, reference: str, revision: int) -> dict[str, object]:
        """Read an immutable revision inside the bound workspace."""
        self._validate_kind(kind)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise CollaborationStoreError("revision must be a positive integer")
        with closing(self.connect()) as connection, connection:
            row = connection.execute(
                """SELECT r.content FROM documents d
                   JOIN document_revisions r ON r.document_id = d.id
                   WHERE d.workspace_id = ? AND d.kind = ? AND d.reference = ?
                     AND d.deleted_at IS NULL AND r.revision = ?""",
                (self.context.workspace_id, kind, reference, revision),
            ).fetchone()
        if row is None:
            raise DocumentNotFoundError("Document revision not found")
        return json.loads(row["content"])

    def revisions(self, kind: str, reference: str) -> list[dict[str, object]]:
        current = self.get(kind, reference, include_deleted=True)
        if current is None:
            raise DocumentNotFoundError("JSON file not found")
        key = self.cache.key(self.context.workspace_id, current.document_id, current.revision)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT revision, created_by, created_at, content_hash
                FROM document_revisions WHERE document_id = ? ORDER BY revision DESC
                """,
                (current.document_id,),
            ).fetchall()
        result = [dict(row) for row in rows]
        self.cache.set(key, result)
        return result

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
