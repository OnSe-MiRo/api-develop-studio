"""Persistent execution metadata for the Studio dashboard (no request/response bodies)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


class ExecutionHistory:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL, status TEXT NOT NULL,
                    exit_code INTEGER, projects TEXT NOT NULL, targets TEXT NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS executions_started ON executions(started_at)")
                yield connection
        finally:
            connection.close()

    def record(self, *, started_at: str, duration_ms: float, status: str,
               exit_code: int | None, projects: list[str], targets: list[dict]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO executions (started_at, duration_ms, status, exit_code, projects, targets) VALUES (?, ?, ?, ?, ?, ?)",
                (started_at, round(duration_ms, 3), status, exit_code,
                 json.dumps(sorted(set(projects))), json.dumps(targets, ensure_ascii=False)),
            )

    def dashboard(self, *, project: str = "", days: int = 7, status: str = "", page: int = 1,
                  now: datetime | None = None) -> dict:
        if days not in (7, 30, 90) or status not in ("", "passed", "failed", "error", "timeout") or not 1 <= page <= 1000000:
            raise ValueError("대시보드 조회 조건이 올바르지 않습니다.")
        now = now or datetime.now(timezone.utc)
        start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        where = "started_at >= ? AND started_at <= ?"
        parameters = [start.isoformat(), now.isoformat()]
        if project:
            where += " AND EXISTS (SELECT 1 FROM json_each(executions.projects) WHERE value = ?)"
            parameters.append(project)
        with self.connect() as connection:
            summary = dict(connection.execute(f"""SELECT COUNT(*) AS total,
                COALESCE(SUM(status = 'passed'), 0) AS passed,
                COALESCE(SUM(status = 'failed'), 0) AS failed,
                COALESCE(SUM(status = 'error'), 0) AS error,
                COALESCE(SUM(status = 'timeout'), 0) AS timeout,
                AVG(duration_ms) AS averageDurationMs
                FROM executions WHERE {where}""", parameters).fetchone())
            summary["successRate"] = round(summary["passed"] / summary["total"] * 100, 1) if summary["total"] else None
            daily = {row["date"]: dict(row) for row in connection.execute(f"""SELECT substr(started_at, 1, 10) AS date,
                COUNT(*) AS total, SUM(status = 'passed') AS passed,
                SUM(status != 'passed') AS failed FROM executions WHERE {where} GROUP BY date""", parameters)}
            if status:
                where += " AND status = ?"
                parameters.append(status)
            total = connection.execute(f"SELECT COUNT(*) FROM executions WHERE {where}", parameters).fetchone()[0]
            items = []
            for row in connection.execute(f"SELECT * FROM executions WHERE {where} ORDER BY started_at DESC, id DESC LIMIT 20 OFFSET ?", [*parameters, (page - 1) * 20]):
                items.append({
                    "id": row["id"], "startedAt": row["started_at"], "durationMs": row["duration_ms"],
                    "status": row["status"], "exitCode": row["exit_code"],
                    "projects": json.loads(row["projects"]), "targets": json.loads(row["targets"]),
                })
        trend = []
        for offset in range(days):
            date = (start + timedelta(days=offset)).date().isoformat()
            trend.append(daily.get(date, {"date": date, "total": 0, "passed": 0, "failed": 0}))
        return {"summary": summary, "trend": trend, "items": items, "total": total, "page": page, "pageSize": 20}
