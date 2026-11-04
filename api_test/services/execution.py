from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from copy import deepcopy

from api_test.job_runner import execute_job


def send_request(request, studio):
    return request.json_response(200, studio.handle_api_request(request.read_body()))


def validate_run(body, studio):
    pipelines = body.get("pipelines", [])
    cases = body.get("cases", [])
    inline_case = body.get("inlineCase")
    inline_pipeline = body.get("inlinePipeline")
    if not isinstance(pipelines, list) or not isinstance(cases, list) or not all(isinstance(item, str) for item in pipelines + cases):
        raise studio.ApiError("pipelines and cases must be string arrays")
    preview_count = int(inline_case is not None) + int(inline_pipeline is not None)
    if preview_count > 1 or (preview_count and (pipelines or cases)):
        raise studio.ApiError("Run either saved targets or one unsaved case/pipeline")

    if body.get("environment") is not None and not isinstance(body["environment"], str):
        raise studio.ApiError("environment must be a string")
    if inline_case is not None:
        if not isinstance(inline_case, dict):
            raise studio.ApiError("inlineCase must be an object")
        reference = body.get("caseReference", "preview/unsaved/unsaved_case.json")
        if not isinstance(reference, str):
            raise studio.ApiError("caseReference must be a string")
        studio.safe_file(studio.document_root("cases"), reference)
    if inline_pipeline is not None and not isinstance(inline_pipeline, dict):
        raise studio.ApiError("inlinePipeline must be an object")
    for reference in cases:
        studio.safe_file(studio.document_root("cases"), reference)
    for reference in pipelines:
        studio.safe_file(studio.document_root("pipelines"), reference)


@contextmanager
def run_command(body, studio):
    validate_run(body, studio)
    pipelines, cases = body.get("pipelines", []), body.get("cases", [])
    inline_case, inline_pipeline = body.get("inlineCase"), body.get("inlinePipeline")
    with TemporaryDirectory(prefix="api-test-preview-") as directory:
        if inline_case is not None:
            reference = body.get("caseReference", "preview/unsaved/unsaved_case.json")
            temporary_case_root = Path(directory) / "case"
            temporary_case_path = studio.safe_file(temporary_case_root, reference)
            temporary_case_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_case_path.write_text(
                json.dumps(studio.normalize_case_document(inline_case), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            command = [
                sys.executable, "run_api_tests.py", "--case-root", str(temporary_case_root),
                "--file-root", str(studio.document_root("cases")), "--case", reference,
            ]
        elif inline_pipeline is not None:
            temporary_pipeline = Path(directory) / "unsaved_pipeline.json"
            temporary_pipeline.write_text(json.dumps(inline_pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            command = [sys.executable, "run_api_tests.py", str(temporary_pipeline)]
        else:
            command = [sys.executable, "run_api_tests.py", *[str(studio.safe_file(studio.document_root("pipelines"), item)) for item in pipelines]]
            if cases:
                command.extend(["--case", *cases])
        if inline_case is None:
            command.extend(["--case-root", str(studio.document_root("cases"))])
        command.extend(["--project-root", str(studio.document_root("projects")), "--file-root", str(studio.document_root("cases"))])
        if not cases and not pipelines and inline_case is None and inline_pipeline is None:
            # Resolve the default target list in this workspace, never the CLI's global fallback.
            references = studio.project_json_files(studio.document_root("pipelines"), None)
            if not references:
                raise studio.ApiError("실행할 파이프라인이 없습니다.")
            command[2:2] = [str(studio.safe_file(studio.document_root("pipelines"), ref)) for ref in references]
        environment = body.get("environment")
        if environment:
            command.extend(["--environment", environment])
        yield command


def run_tests(request, studio):
    body = request.read_body()
    manager = request.request.app.state.jobs
    with manager.legacy_slot(), run_command(body, studio) as command:
        response = studio.execute_studio_run(command, body)
    return request.json_response(200, response)


def submit_run(request, studio, body=None):
    body = deepcopy(request.read_body() if body is None else body)
    validate_run(body, studio)
    projects, targets = studio.execution_metadata(body)
    # Include projects of pipeline cases, including pipelines without a project field.
    project_set = set(projects)
    for target in targets:
        if target["kind"] != "pipeline":
            continue
        try:
            document = body.get("inlinePipeline") if target.get("preview") else studio.read_studio_document(studio.document_root("pipelines"), target["reference"])
            steps = document.get("steps") if isinstance(document, dict) else None
            for step in steps if isinstance(steps, list) else []:
                if isinstance(step, dict) and isinstance(step.get("case"), str):
                    case = studio.read_studio_document(studio.document_root("cases"), step["case"])
                    if isinstance(case, dict) and isinstance(case.get("project"), str) and case["project"]:
                        project_set.add(case["project"])
        except (studio.ApiError, OSError, ValueError):
            pass  # The runner reports invalid targets using the normal result contract.
    projects = sorted(project_set)
    # Identity is server-owned; request body user/workspace fields are never trusted.
    manager = request.request.app.state.jobs
    def task(job):
        studio.ensure_run_ready()
        with run_command(body, studio) as command:
            return execute_job(job, command, studio, projects, targets, body.get("environment"))
    initial = {}
    case_reference = body.get("caseReference", "preview/unsaved/unsaved_case.json") if body.get("inlineCase") is not None else (body.get("cases") or [None])[0]
    if case_reference and len(targets) == 1 and targets[0]["kind"] == "case" and len(projects) == 1:
        initial = {"caseReference": case_reference.replace("\\", "/"), "project": projects[0]}
    return request.json_response(202, manager.submit(task, owner=studio.current_context(), projects=projects, initial=initial))


def get_run(request, studio, run_id):
    return request.json_response(200, request.request.app.state.jobs.get(run_id, studio.current_context()))


def cancel_run(request, studio, run_id):
    return request.json_response(200, request.request.app.state.jobs.cancel(run_id, studio.current_context()))


def save_run_result(request, studio, run_id):
    from api_test.saved_results import SavedResults
    from api_test.jobs import TERMINAL
    store = SavedResults(studio.execution_history())
    # Saving the same run remains idempotent after the transient job expires.
    existing = store.get(run_id)
    if existing is not None:
        return request.json_response(200, existing)
    job = request.request.app.state.jobs.get(run_id, studio.current_context())
    if job.get("status") not in TERMINAL:
        raise studio.ApiError("완료된 실행만 저장할 수 있습니다.", status_code=409)
    if not job.get("project") or not job.get("caseReference"):
        raise studio.ApiError("단일 케이스 실행 결과만 저장할 수 있습니다.")
    if len(json.dumps(job, ensure_ascii=False).encode("utf-8")) > 4 * 1024 * 1024:
        raise studio.ApiError("실행 결과 저장 한도 4 MiB를 초과했습니다.", status_code=413)
    return request.json_response(200, store.save(job))


def list_saved_results(request, studio):
    from api_test.saved_results import SavedResults
    query = request.request.query_params
    project, reference = query.get("project", ""), query.get("caseReference", "")
    if not project or not reference:
        raise studio.ApiError("프로젝트와 케이스 경로가 필요합니다.")
    return request.json_response(200, {"items": SavedResults(studio.execution_history()).list(project, reference.replace("\\", "/"))})


def get_saved_result(request, studio, run_id):
    from api_test.saved_results import SavedResults
    result = SavedResults(studio.execution_history()).get(run_id)
    if result is None:
        raise studio.ApiError("저장된 실행 결과를 찾을 수 없습니다.", status_code=404)
    return request.json_response(200, result)
