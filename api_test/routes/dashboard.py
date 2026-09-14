from __future__ import annotations

import sqlite3


def handle_get(handler, parts: list[str], studio) -> bool:
    if parts != ["api", "dashboard"]:
        return False
    try:
        data = studio.execution_history().dashboard(
            project=handler.query_value("project") or "",
            days=int(handler.query_value("days") or "7"),
            status=handler.query_value("status") or "",
            page=int(handler.query_value("page") or "1"),
        )
    except (TypeError, ValueError) as exc:
        raise studio.ApiError("대시보드 조회 조건이 올바르지 않습니다.") from exc
    except sqlite3.Error as exc:
        raise studio.ApiError("실행 이력을 불러오지 못했습니다.") from exc
    handler.send_json(200, data)
    return True
