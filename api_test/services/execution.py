from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from copy import deepcopy

from api_test.database import LOCAL_CONTEXT
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
        studio.safe_file(studio.CASE_ROOT, reference)
    if inline_pipeline is not None and not isinstance(inline_pipeline, dict):
        raise studio.ApiError("inlinePipeline must be an object")
    for reference in cases:
        studio.safe_file(studio.CASE_ROOT, reference)
    for reference in pipelines:
        studio.safe_file(studio.PIPELINE_ROOT, reference)


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
                "--file-root", str(studio.CASE_ROOT), "--case", reference,
            ]
        elif inline_pipeline is not None:
            temporary_pipeline = Path(directory) / "unsaved_pipeline.json"
            temporary_pipeline.write_text(json.dumps(inline_pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            command = [sys.executable, "run_api_tests.py", str(temporary_pipeline)]
        else:
            command = [sys.executable, "run_api_tests.py", *[str(studio.safe_file(studio.PIPELINE_ROOT, item)) for item in pipelines]]
            if cases:
                command.extend(["--case", *cases])
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


def submit_run(request, studio):
    body = deepcopy(request.read_body())
    validate_run(body, studio)
    projects, targets = studio.execution_metadata(body)
    # Include projects of pipeline cases, including pipelines without a project field.
    project_set = set(projects)
    for target in targets:
        if target["kind"] != "pipeline":
            continue
        try:
            document = body.get("inlinePipeline") if target.get("preview") else studio.read_studio_document(studio.PIPELINE_ROOT, target["reference"])
            steps = document.get("steps") if isinstance(document, dict) else None
            for step in steps if isinstance(steps, list) else []:
                if isinstance(step, dict) and isinstance(step.get("case"), str):
                    case = studio.read_studio_document(studio.CASE_ROOT, step["case"])
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
            return execute_job(job, command, studio, projects, targets)
    return request.json_response(202, manager.submit(task, owner=LOCAL_CONTEXT, projects=projects))


def get_run(request, studio, run_id):
    return request.json_response(200, request.request.app.state.jobs.get(run_id, LOCAL_CONTEXT))


def cancel_run(request, studio, run_id):
    return request.json_response(200, request.request.app.state.jobs.cancel(run_id, LOCAL_CONTEXT))
