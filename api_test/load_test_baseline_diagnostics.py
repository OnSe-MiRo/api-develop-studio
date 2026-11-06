"""Private P1 case-list timings and thread census for the isolated harness only."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from api_test.case_projection import case_url


class CaseListProbe:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._sequence = 0

    def record(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**value, "sequence": self._sequence}, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._sequence += 1


def timed_case_list(request, studio, kind, trace: CaseListProbe, original):
    if kind != "cases" or any(name in request.request.query_params for name in ("page_size", "q", "tag", "sort", "cursor")):
        return original(request, studio, kind)

    started = time.perf_counter_ns()
    store = studio.collaboration_store()
    references = store.list_references("cases", request.query_value("project"))
    lookup_ended = time.perf_counter_ns()
    elapsed = {"pathResolutionNs": 0, "projectionReadNs": 0, "utf8DecodeNs": 0, "jsonParseNs": 0, "fieldSelectionNs": 0}
    read_bytes = files_read = 0

    def resolve(root, reference):
        began = time.perf_counter_ns()
        path = studio.safe_file(root, reference)
        elapsed["pathResolutionNs"] += time.perf_counter_ns() - began
        return path

    def read_projection(source):
        nonlocal read_bytes, files_read
        began = time.perf_counter_ns()
        raw = source.read()
        read = time.perf_counter_ns()
        decoded = raw.decode("utf-8")
        decoded_at = time.perf_counter_ns()
        document = json.loads(decoded)
        parsed = time.perf_counter_ns()
        url = case_url(document)
        selected = time.perf_counter_ns()
        elapsed["projectionReadNs"] += read - began
        elapsed["utf8DecodeNs"] += decoded_at - read
        elapsed["jsonParseNs"] += parsed - decoded_at
        elapsed["fieldSelectionNs"] += selected - parsed
        files_read += 1
        read_bytes += len(raw)
        return url

    details = studio.case_summaries(studio.document_root("cases"), references,
                                    resolve_file=resolve, read_projection=read_projection)
    serializing = time.perf_counter_ns()
    response = request.json_response(200, {"items": references, "details": details})
    finished = time.perf_counter_ns()
    measurements = {"lookupNs": lookup_ended - started, **elapsed, "serializationNs": finished - serializing}
    total = finished - started
    other = total - sum(measurements.values())
    trace.record({"formatVersion": 1, "operation": "GET /api/cases", "timestamp": datetime.now(timezone.utc).isoformat(),
                  "caseCount": len(references), "projectionFilesRead": files_read, "projectionReadBytes": read_bytes, "responseBytes": len(response.body),
                  **measurements, "handlerNs": total, "otherNs": other})
    return response


def thread_census() -> dict:
    threads = sorted((thread for thread in threading.enumerate() if thread.is_alive()), key=lambda thread: (thread.name, thread.native_id or 0))
    return {"serverPid": os.getpid(), "timestamp": datetime.now(timezone.utc).isoformat(),
            "threads": [{"name": thread.name, "nativeId": thread.native_id, "daemon": thread.daemon} for thread in threads]}


def install_diagnostics(application, trace_path: Path) -> None:
    from api_test.implementations import documents as bindings
    original = bindings.list_documents
    trace = CaseListProbe(trace_path)

    def observed(request, studio, kind):
        return timed_case_list(request, studio, kind, trace, original)

    bindings.list_documents = observed
    async def census():
        return thread_census()

    count = len(application.router.routes)
    application.add_api_route("/__load_test__/thread-census", census, methods=["GET"], include_in_schema=False)
    application.router.routes[:] = application.router.routes[count:] + application.router.routes[:count]
