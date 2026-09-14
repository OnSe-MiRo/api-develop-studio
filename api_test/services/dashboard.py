from __future__ import annotations

from api_test.database import DATABASE_ERRORS


def get_dashboard(request, studio):
    try:
        data = studio.execution_history().dashboard(
            project=request.query_value("project") or "",
            days=int(request.query_value("days") or "7"),
            status=request.query_value("status") or "",
            page=int(request.query_value("page") or "1"),
        )
    except (TypeError, ValueError) as exc:
        raise studio.ApiError("대시보드 조회 조건이 올바르지 않습니다.") from exc
    except DATABASE_ERRORS as exc:
        raise studio.ApiError("실행 이력을 불러오지 못했습니다.") from exc
    return request.json_response(200, data)
