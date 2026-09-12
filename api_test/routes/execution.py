from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def handle_post(handler, parts: list[str], studio) -> bool:
    if parts == ["api", "request"]:
        handler.send_json(200, studio.handle_api_request(handler.read_body()))
        return True
    if parts != ["api", "run"]:
        return False

    body = handler.read_body()
    pipelines = body.get("pipelines", [])
    cases = body.get("cases", [])
    inline_case = body.get("inlineCase")
    inline_pipeline = body.get("inlinePipeline")
    if not isinstance(pipelines, list) or not isinstance(cases, list) or not all(isinstance(item, str) for item in pipelines + cases):
        raise studio.ApiError("pipelines and cases must be string arrays")
    preview_count = int(inline_case is not None) + int(inline_pipeline is not None)
    if preview_count > 1 or (preview_count and (pipelines or cases)):
        raise studio.ApiError("Run either saved targets or one unsaved case/pipeline")

    with TemporaryDirectory(prefix="api-test-preview-") as directory:
        if inline_case is not None:
            if not isinstance(inline_case, dict):
                raise studio.ApiError("inlineCase must be an object")
            reference = body.get("caseReference", "preview/unsaved/unsaved_case.json")
            if not isinstance(reference, str):
                raise studio.ApiError("caseReference must be a string")
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
            if not isinstance(inline_pipeline, dict):
                raise studio.ApiError("inlinePipeline must be an object")
            temporary_pipeline = Path(directory) / "unsaved_pipeline.json"
            temporary_pipeline.write_text(json.dumps(inline_pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            command = [sys.executable, "run_api_tests.py", str(temporary_pipeline)]
        else:
            command = [sys.executable, "run_api_tests.py", *[str(studio.safe_file(studio.PIPELINE_ROOT, item)) for item in pipelines]]
            if cases:
                command.extend(["--case", *cases])
        response = studio.execute_studio_run(command, body)
    handler.send_json(200, response)
    return True
