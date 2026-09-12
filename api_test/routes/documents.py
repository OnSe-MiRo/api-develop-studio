from __future__ import annotations

import json


def handle_get(handler, parts: list[str], studio) -> bool:
    store = studio.collaboration_store()
    if parts == ["api", "cases"]:
        references = store.list_references("cases", handler.query_value("project"))
        handler.send_json(200, {"items": references, "details": studio.case_summaries(studio.CASE_ROOT, references)})
    elif parts == ["api", "pipelines"]:
        handler.send_json(200, {"items": store.list_references("pipelines", handler.query_value("project"))})
    elif parts == ["api", "projects"]:
        references = store.list_references("projects")
        if not studio.example_project_enabled():
            references = [reference for reference in references if reference != studio.EXAMPLE_PROJECT_REFERENCE]
        handler.send_json(200, {"items": references, "details": studio.project_summaries(studio.PROJECT_ROOT, references)})
    elif len(parts) == 4 and parts[:2] == ["api", "cases"] and parts[3] == "revisions":
        handler.send_json(200, {"items": store.revisions("cases", parts[2])})
    elif len(parts) == 4 and parts[:2] == ["api", "pipelines"] and parts[3] == "revisions":
        handler.send_json(200, {"items": store.revisions("pipelines", parts[2])})
    elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "revisions":
        studio.ensure_example_project_enabled(parts[2])
        handler.send_json(200, {"items": store.revisions("projects", parts[2])})
    elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
        stored = store.get("cases", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        document = studio.case_variables_for_client(stored.document)
        expected = document.get("expected", {})
        if isinstance(expected, dict) and "body" in expected:
            document["_expectedBodyRaw"] = json.dumps(expected["body"], ensure_ascii=False, indent=2)
        document["_storage"] = stored.metadata()
        handler.send_json(200, document)
    elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
        stored = store.get("pipelines", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        handler.send_json(200, {**stored.document, "_storage": stored.metadata()})
    elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
        studio.ensure_example_project_enabled(parts[2])
        stored = store.get("projects", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        project = studio.project_variables_for_client(stored.document)
        handler.send_json(200, {**project, "_storage": stored.metadata()})
    else:
        return False
    return True


def handle_put(handler, parts: list[str], studio) -> bool:
    if len(parts) != 3 or parts[:2] not in (["api", "cases"], ["api", "pipelines"], ["api", "projects"]):
        return False
    payload, expected_revision = studio.storage_request(handler.read_body())
    store = studio.collaboration_store()
    existing = None
    if parts[:2] == ["api", "cases"]:
        kind = "cases"
        current = store.get(kind, parts[2])
        payload = studio.normalize_case_document(payload, current.document if current is not None else None)
        studio.validate_project_reference(payload)
    elif parts[:2] == ["api", "pipelines"]:
        kind = "pipelines"
        studio.validate_project_reference(payload)
    else:
        studio.ensure_example_project_enabled(parts[2])
        kind = "projects"
        current = store.get(kind, parts[2])
        existing = current.document if current is not None else None
        payload = studio.normalize_project_document(payload, existing)
        studio.validate_project_document(payload)
    stored = store.save(kind, parts[2], payload, expected_revision=expected_revision, actor_id=handler.actor_id())
    if kind == "projects" and (existing is None or studio.fingerprint(existing) != studio.fingerprint(payload)):
        studio.OwnershipStore().revoke(parts[2])
    path = studio.safe_file({"cases": studio.CASE_ROOT, "pipelines": studio.PIPELINE_ROOT, "projects": studio.PROJECT_ROOT}[kind], parts[2])
    handler.send_json(200, {"path": str(path.relative_to(studio.ROOT)), "_storage": stored.metadata()})
    return True


def handle_delete(handler, parts: list[str], studio) -> bool:
    if len(parts) != 3 or parts[0] != "api" or parts[1] not in {"cases", "pipelines", "projects"}:
        return False
    store = studio.collaboration_store()
    if parts[1] == "projects":
        studio.ensure_example_project_enabled(parts[2])
    deleted_pipelines: list[str] = []
    if parts[1] == "projects":
        if store.list_references("cases", parts[2]):
            raise studio.ApiError("Delete the project's API cases before deleting the project")
        deleted_pipelines = store.list_references("pipelines", parts[2])
        for pipeline_reference in deleted_pipelines:
            store.delete("pipelines", pipeline_reference, actor_id=handler.actor_id())
    store.delete(parts[1], parts[2], actor_id=handler.actor_id())
    if parts[1] == "projects":
        studio.OwnershipStore().revoke(parts[2], remove=True)
    root_name = {"cases": "case", "pipelines": "pipelines", "projects": "projects"}[parts[1]]
    handler.send_json(200, {"deleted": f"{root_name}/{parts[2]}", "deleted_pipelines": deleted_pipelines})
    return True
