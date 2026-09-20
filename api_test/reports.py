"""Versioned execution reports. Never serialize HTTP payloads or exception text."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


def now():
    return datetime.now(timezone.utc).isoformat()


class RunReport:
    def __init__(self, environment=None, run_id=None):
        self.data = {
            "schemaVersion": 1, "runId": run_id or str(uuid.uuid4()),
            "environment": environment, "actor": "local-user",
            "appVersion": os.environ.get("APP_VERSION"), "commit": os.environ.get("APP_COMMIT"),
            "startedAt": now(), "finishedAt": None, "status": "passed", "exitCode": 0,
            "targets": [], "artifacts": [],
        }

    def add(self, result, target, started_at, project=None, case_reference=None, phase="test"):
        status = result.status
        reason = None
        if status == "error":
            # Exception text can contain credentials/response fragments: use a safe category.
            reason = "request_error"
            if result.error_category == "request_timeout" or result.error and ("timed out" in result.error.lower() or "timeout" in result.error.lower() or "타임아웃" in result.error):
                status, reason = "timeout", "request_timeout"
        elif status == "failed":
            reason = "assertion_failed"
        self.data["targets"].append({
            "target": target, "caseId": result.case_id, "project": project,
            "caseReference": case_reference, "phase": phase,
            "startedAt": started_at, "finishedAt": now(), "status": status,
            "attempts": result.attempts, "httpStatus": result.response.status if result.response else None,
            "elapsedMs": result.response_time_ms, "errorCategory": reason,
            "assertions": [{"index": i, "passed": item.passed} for i, item in enumerate(result.assertion_results)],
        })

    def error(self, target):
        self.data["targets"].append({"target": target, "caseId": target, "project": None,
            "startedAt": now(), "finishedAt": now(), "status": "error", "attempts": 0,
            "httpStatus": None, "elapsedMs": None, "errorCategory": "configuration_error", "assertions": []})

    def finish(self, exit_code):
        states = {item["status"] for item in self.data["targets"]}
        self.data.update(finishedAt=now(), exitCode=exit_code,
                         status=next((s for s in ("cancelled", "timeout", "error", "failed") if s in states),
                                     "passed" if exit_code == 0 else "error"))
        for field, selected in (("mainStatus", [i for i in self.data["targets"] if i.get("phase") != "teardown"]),
                                ("cleanupStatus", [i for i in self.data["targets"] if i.get("phase") == "teardown"])):
            self.data[field] = next((state for state in ("cancelled", "timeout", "error", "failed") if any(i["status"] == state for i in selected)), "passed" if selected else "not_run")
        return self.data

    def write(self, json_path=None, junit_path=None):
        self.data["artifacts"] = [{"format": kind, "reference": Path(path).name}
                                  for kind, path in (("json", json_path), ("junit", junit_path)) if path]
        if json_path:
            self._write(json_path, json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")
        if junit_path:
            items = self.data["targets"]
            suite = ET.Element("testsuite", name="api-tests", tests=str(len(items)),
                               failures=str(sum(i["status"] == "failed" for i in items)),
                               errors=str(sum(i["status"] in ("error", "timeout") for i in items)),
                               skipped=str(sum(i["status"] == "cancelled" for i in items)))
            for item in items:
                case = ET.SubElement(suite, "testcase", name=item["caseId"], classname=item["target"],
                                     time=str((item["elapsedMs"] or 0) / 1000))
                if item["status"] != "passed":
                    tag = "failure" if item["status"] == "failed" else "skipped" if item["status"] == "cancelled" else "error"
                    failed = [str(a["index"]) for a in item["assertions"] if not a["passed"]]
                    message = item["errorCategory"] or item["status"]
                    if failed:
                        message += "; failed assertion indexes: " + ", ".join(failed)
                    ET.SubElement(case, tag, message=message)
            self._write(junit_path, ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n")

    @staticmethod
    def _write(path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def history_targets(targets, report):
    """Keep only saved-case outcome metadata, never response data or preview runs."""
    if any(t.get('preview') for t in targets):
        return targets
    return targets + [{key: item.get(key) for key in ('caseReference', 'project', 'status', 'httpStatus', 'phase')}
                      for item in (report or {}).get('targets', []) if item.get('caseReference')]
