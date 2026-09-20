"""Spec linkage and conservative, field-selective case synchronization."""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_for(operation, document):
    # Include shared components: a referenced schema change must invalidate its consumers.
    return {"id": operation.get("editable", {}).get("operationId") or operation["id"],
            "method": operation["method"], "path": operation["path"],
            "status": operation["expected_status"],
            "fingerprint": fingerprint([operation["method"], operation["path"], document.get("paths", {}).get(operation["path"]), document.get("components", {}), document.get("definitions", {})])}


def linked_operation(case, operations):
    source = case.get("spec_source") or {}
    if source:
        matches = [op for op in operations if (op.get("editable", {}).get("operationId") or op["id"]) == source.get("id")]
        return matches[0] if len(matches) == 1 else None
    request = case.get("request", {})
    path = urlsplit(request.get("url", "")).path
    matches = [op for op in operations if op["method"] == request.get("method", "GET").upper()
               and re.fullmatch(re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(op["path"])), path)]
    return matches[0] if len(matches) == 1 else None


def sync_preview(case, operation, source):
    previous = case.get("spec_source") or {}
    changes = []
    for field, old, new in (("request.method", previous.get("method"), source["method"]),
                            ("request.url", previous.get("path"), source["path"]),
                            ("expected.status", previous.get("status"), source["status"])):
        section, key = field.split(".")
        current = case.get(section, {}).get(key)
        if old != new:
            changes.append({"field": field, "before": old, "after": new,
                            "selectable": bool(previous) and current == old,
                            "reason": "" if previous and current == old else "기준 없음 또는 사용자 수정 값 보존"})
    return {"changed": previous.get("fingerprint") != source["fingerprint"], "changes": changes,
            "source": source, "preserved": ["assertions", "body", "headers", "auth", "variables", "사용자가 수정한 요청 값"]}


def apply_sync(case, preview, fields):
    available = {c["field"]: c for c in preview["changes"] if c["selectable"]}
    if not isinstance(fields, list) or not all(isinstance(f, str) and f in available for f in fields):
        raise ValueError("갱신 가능한 필드만 선택하세요.")
    updated = copy.deepcopy(case)
    for field in fields:
        section, key = field.split(".")
        updated[section][key] = available[field]["after"]
    updated["spec_source"] = preview["source"]
    return updated


def response_key(status, responses):
    status = str(status)
    keys = {str(item['status']) for item in responses}
    if status in keys:
        return status
    if len(status) == 3 and status[0] + 'XX' in keys:
        return status[0] + 'XX'
    return 'default' if 'default' in keys else None
