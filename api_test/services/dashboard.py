from __future__ import annotations

from api_test.database import DATABASE_ERRORS


def get_dashboard(request, studio):
    try:
        data = studio.execution_history().dashboard(
            project=request.query_value("project") or "",
            days=int(request.query_value("days") or "7"),
            status=request.query_value("status") or "",
            page=int(request.query_value("page") or "1"),
            search=request.query_value("search") or "",
        )
    except (TypeError, ValueError) as exc:
        raise studio.ApiError("대시보드 조회 조건이 올바르지 않습니다.") from exc
    except DATABASE_ERRORS as exc:
        raise studio.ApiError("실행 이력을 불러오지 못했습니다.") from exc
    return request.json_response(200, data)


def history_run(studio, run_id):
    try:
        run = studio.execution_history().detail(run_id)
    except DATABASE_ERRORS as exc:
        raise studio.ApiError("실행 이력을 불러오지 못했습니다.", 503) from exc
    if run is None:
        raise studio.ApiError("실행 이력을 찾을 수 없습니다.", 404)
    return run


def get_execution(request, studio, run_id):
    from api_test.reports import failed_run_request
    run = history_run(studio, run_id)
    run['rerunRequest'] = failed_run_request(run)
    return request.json_response(200, run)


def rerun_execution(request, studio, run_id):
    from api_test.reports import failed_run_request
    from api_test.services.execution import submit_run
    body = failed_run_request(history_run(studio, run_id))
    if body is None:
        raise studio.ApiError("재실행 가능한 저장된 실패 대상이 없습니다.", 409)
    for kind, root in (('cases', studio.CASE_ROOT), ('pipelines', studio.PIPELINE_ROOT)):
        for reference in body[kind]:
            if not studio.safe_file(root, reference).is_file():
                raise studio.ApiError("재실행 대상이 삭제되었습니다. 케이스와 파이프라인을 확인하세요.", 409)
    return submit_run(request, studio, body)
