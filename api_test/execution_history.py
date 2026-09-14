"""Persistent execution metadata for the Studio dashboard.

Only identifiers and outcome metadata are stored. Request and response bodies,
headers, credentials, and runner output deliberately stay outside this store.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api_test.migrations import migrate_studio_database
from api_test.database import connect, LOCAL_CONTEXT, RequestContext, postgres_enabled, require_membership, initialize_local_context


ALLOWED_STATUSES = ("passed", "failed", "error", "timeout")


class ExecutionHistory:
    def __init__(self, path: Path, *, context: RequestContext = LOCAL_CONTEXT):
        self.path = path
        self.context = context

    @contextmanager
    def connect(self):
        connection = connect(self.path)
        try:
            migrate_studio_database(connection)
            with connection:
                if postgres_enabled():
                    initialize_local_context(connection)
                    require_membership(connection, self.context)
                yield connection
        finally:
            connection.close()

    def record(
        self,
        *,
        run_id: str,
        started_at: str,
        finished_at: str,
        duration_ms: float,
        status: str,
        exit_code: int | None,
        projects: list[str],
        targets: list[dict],
    ) -> None:
        if status not in ALLOWED_STATUSES:
            raise ValueError("지원하지 않는 실행 상태입니다.")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO executions
                   (run_id, started_at, finished_at, duration_ms, status, exit_code, projects, targets, workspace_id, requested_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    started_at,
                    finished_at,
                    round(duration_ms, 3),
                    status,
                    exit_code,
                    json.dumps(sorted(set(projects))),
                    json.dumps(targets, ensure_ascii=False),
                    self.context.workspace_id, self.context.user_id,
                ),
            )

    def dashboard(
        self,
        *,
        project: str = "",
        days: int = 7,
        status: str = "",
        page: int = 1,
        now: datetime | None = None,
    ) -> dict:
        if days not in (7, 30, 90) or status not in ("", *ALLOWED_STATUSES) or not 1 <= page <= 1_000_000:
            raise ValueError("대시보드 조회 조건이 올바르지 않습니다.")
        now = now or datetime.now(timezone.utc)
        start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        where = "workspace_id = ? AND started_at >= ? AND started_at <= ?"
        parameters: list[object] = [self.context.workspace_id, start.isoformat(), now.isoformat()]
        if project:
            where += " AND EXISTS (SELECT 1 FROM json_each(executions.projects) WHERE value = ?)"
            parameters.append(project)

        with self.connect() as connection:
            if getattr(connection, "dialect", "") == "postgresql":
                where = where.replace("json_each(executions.projects)", "jsonb_array_elements_text(executions.projects::jsonb)")
            summary = dict(
                connection.execute(
                    f"""SELECT COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END), 0) AS passed,
                        COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed,
                        COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0) AS error,
                        COALESCE(SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END), 0) AS timeout,
                        AVG(duration_ms) AS "averageDurationMs"
                        FROM executions WHERE {where}""",
                    parameters,
                ).fetchone()
            )
            summary["successRate"] = (
                round(summary["passed"] / summary["total"] * 100, 1) if summary["total"] else None
            )
            daily = {
                row["date"]: dict(row)
                for row in connection.execute(
                    f"""SELECT substr(started_at, 1, 10) AS date,
                        COUNT(*) AS total, SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) AS passed,
                        SUM(CASE WHEN status != 'passed' THEN 1 ELSE 0 END) AS failed
                        FROM executions WHERE {where} GROUP BY date""",
                    parameters,
                )
            }
            item_where = where
            item_parameters = list(parameters)
            if status:
                item_where += " AND status = ?"
                item_parameters.append(status)
            total = connection.execute(
                f"SELECT COUNT(*) FROM executions WHERE {item_where}", item_parameters
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT * FROM executions WHERE {item_where}
                    ORDER BY started_at DESC, run_id DESC LIMIT 20 OFFSET ?""",
                [*item_parameters, (page - 1) * 20],
            )
            items = [
                {
                    "runId": row["run_id"],
                    "startedAt": row["started_at"],
                    "finishedAt": row["finished_at"],
                    "durationMs": row["duration_ms"],
                    "status": row["status"],
                    "exitCode": row["exit_code"],
                    "projects": json.loads(row["projects"]),
                    "targets": json.loads(row["targets"]),
                }
                for row in rows
            ]

        trend = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).date().isoformat()
            trend.append(daily.get(day, {"date": day, "total": 0, "passed": 0, "failed": 0}))
        return {
            "summary": summary,
            "trend": trend,
            "items": items,
            "total": total,
            "page": page,
            "pageSize": 20,
        }
