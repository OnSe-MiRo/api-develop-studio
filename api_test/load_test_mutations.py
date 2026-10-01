"""LT-3 allowlisted fixture preparation, write audit and isolated saved-case runner."""
from __future__ import annotations
import json
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from api_test.collaboration_store import CollaborationStore

WRITE_REFERENCE = re.compile(r"load-test/write/(unique|contention)-vu-(\d+)-iteration-(\d+)\.json")
RUN_PROJECT = "load-test-runtime.json"
RUN_CASE = "load-test/runtime/health.json"


def write_document(project, seed, kind, vu, iteration, step, winner=0):
    body = {"fixture": seed, "padding": ""}
    body["padding"] = "x" * (1024 - len(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()))
    return {"project": project, "request": {"method": "GET", "url": "/example-api/health", "body": body},
            "expected": {"status": 200, "body": {"status": "ok", "service": "example-api"}, "strict": True},
            "loadTest": {"kind": kind, "vu": vu, "iteration": iteration, "step": step, "winner": winner}}


def prepare_runner(root: Path, base_url: str, repository: Path, run_path="/example-api/health") -> dict:
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+", base_url):
        raise ValueError("runner preparation needs the isolated loopback origin")
    if run_path not in ("/example-api/health", "/__load_test__/health"):
        raise ValueError("unsupported isolated runner path")
    project = {"name": "LT-3 isolated execution", "base_url": base_url, "advanced": {"use_proxy": False}, "variables": {"plain": {}, "secret": {}}}
    case = {"project": RUN_PROJECT, "timeout": 2, "request": {"method": "GET", "url": run_path},
            "expected": {"status": 200, "body": {"status": "ok", "service": "example-api"}, "strict": True}}
    store = CollaborationStore(root / "data/studio.db", {"projects": root / "projects", "cases": root / "case", "pipelines": root / "pipelines"})
    store.initialize(import_existing=False)
    store.save("projects", RUN_PROJECT, project)
    store.save("cases", RUN_CASE, case)
    runtime = {"baseUrl": base_url, "runPath": run_path, "runProject": RUN_PROJECT, "runCase": RUN_CASE,
               "documents": [{"kind": "projects", "reference": RUN_PROJECT, "document": project}, {"kind": "cases", "reference": RUN_CASE, "document": case}]}
    (root / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
    (root / "run_api_tests.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(repository)!r})\n"
        "from api_test.load_test_mutations import run_isolated_case\n"
        "raise SystemExit(run_isolated_case())\n")
    return runtime


def allowed_run_target(runtime, project, url, method):
    return runtime.get("runPath", "/example-api/health") in ("/example-api/health", "/__load_test__/health") and project == RUN_PROJECT and method.upper() == "GET" and url == runtime["baseUrl"] + runtime.get("runPath", "/example-api/health") and urlsplit(url).hostname == "127.0.0.1"


def run_isolated_case() -> int:
    # The real CLI/report contract is used, with a guard pinned to one dedicated saved case.
    root = Path.cwd().resolve()
    runtime = json.loads((root / "runtime.json").read_text())
    arguments = sys.argv[1:]
    if len(arguments) not in (6, 8) or arguments[0:2] != ["--case", RUN_CASE] or arguments[2] != "--report-json" or arguments[4] != "--run-id":
        raise ValueError("isolated runner accepts only the prepared saved health case")
    if not Path(arguments[3]).resolve().is_relative_to(root / "tmp"):
        raise ValueError("isolated report must remain in its private temporary directory")
    if len(arguments) == 8 and (arguments[6] != "--log-dir" or not Path(arguments[7]).resolve().is_relative_to(root / "tmp")):
        raise ValueError("isolated async logs must remain in the private temporary directory")
    from api_test import cli
    from api_test.ownership import OwnershipError
    def guard(project, _root, external=False):
        def check(url, method):
            if external or not allowed_run_target(runtime, project, url, method):
                raise OwnershipError("isolated runner target is outside the prepared loopback health case")
        return check
    cli.execution_guard = guard
    cli.local_policy = lambda: {"local_server": True, "skip_verification": False}
    sys.argv = [sys.argv[0], "--case-root", str(root / "case"), "--project-root", str(root / "projects"),
                "--file-root", str(root / "case"), "--log-dir", str(root / "logs"), "--timeout", "2", *arguments]
    return cli.main()


def expected_mutations(root: Path, workload: dict, *, allow_incomplete=False) -> dict:
    manifest = json.loads((root / "fixture.json").read_text())
    extras = {}
    runtime_path = root / "runtime.json"
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text())
        for item in runtime["documents"]:
            extras[(item["kind"], item["reference"])] = [item["document"]]
    with closing(sqlite3.connect((root / "data/studio.db").resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        references = connection.execute("SELECT id, reference, current_revision FROM documents WHERE kind='cases' AND reference LIKE 'load-test/write/%' ORDER BY reference").fetchall()
        for document_id, reference, revision in references:
            match = WRITE_REFERENCE.fullmatch(reference)
            if match is None:
                raise ValueError("unexpected write reference")
            kind, vu_text, iteration_text = match.groups()
            vu, iteration = int(vu_text), int(iteration_text)
            if not 1 <= vu <= workload["configuredVus"] or iteration > workload["durationSeconds"] + 100:
                raise ValueError("write worker/iteration is outside the bounded workload")
            if workload["mode"] != "target" and kind != workload["mode"]:
                raise ValueError("write kind is outside the selected workload")
            project = manifest["projects"][(iteration * workload["selectionStride"] + vu - 1) % len(manifest["projects"])]
            if kind == "unique":
                if revision != 4 and not (allow_incomplete and 1 <= revision < 4):
                    raise ValueError("unique create and three updates did not complete")
                expected = [write_document(project, manifest["seed"], kind, vu, iteration, step) for step in range(1, revision + 1)]
            else:
                if revision == 1 and allow_incomplete:
                    expected = [write_document(project, manifest["seed"], kind, vu, iteration, 1)]
                else:
                    if revision != 2:
                        raise ValueError("contention did not commit exactly one update")
                    content = json.loads(connection.execute("SELECT content FROM document_revisions WHERE document_id=? AND revision=2", (document_id,)).fetchone()[0])
                    winner = content.get("loadTest", {}).get("winner")
                    if isinstance(winner, bool) or not isinstance(winner, int) or not 1 <= winner <= workload["contentionRequests"]:
                        raise ValueError("contention winner is outside the prepared request group")
                    expected = [write_document(project, manifest["seed"], kind, vu, iteration, 1), write_document(project, manifest["seed"], kind, vu, iteration, 2, winner)]
            audits = connection.execute("SELECT action, revision, actor_id FROM audit_events WHERE document_id=? ORDER BY id", (document_id,)).fetchall()
            if audits != [("save", number, "local-user") for number in range(1, len(expected) + 1)]:
                raise ValueError("write audit events differ from committed revisions")
            extras[("cases", reference)] = expected
    return extras


def traffic_report(raw_path: Path) -> dict:
    categories = ("list", "single", "revision", "unique", "contention", "run", "support")
    counts = dict.fromkeys(categories, 0)
    conflicts = 0
    active_peak = allocated_peak = None
    with raw_path.open() as source:
        for line in source:
            event = json.loads(line)
            if event.get("type") != "Point":
                continue
            metric = event.get("metric", "")
            if metric == "vus":
                active_peak = max(active_peak or 0, event["data"]["value"])
            elif metric == "vus_max":
                allocated_peak = max(allocated_peak or 0, event["data"]["value"])
            for category in categories:
                if metric == f"studio_mix_{category}_requests":
                    counts[category] += int(event["data"]["value"])
            if metric == "studio_expected_conflicts":
                conflicts += int(event["data"]["value"])
    workload_total = sum(counts[category] for category in categories if category != "support")
    total = workload_total + counts["support"]
    return {"requests": counts, "workloadRequests": workload_total, "totalClassifiedRequests": total,
            "expected409": conflicts, "activePeakVus": active_peak, "allocatedMaxVus": allocated_peak, "workloadRatios": {category: counts[category] / workload_total if workload_total else None for category in categories if category != "support"},
            "allHttpRatios": {category: counts[category] / total if total else None for category in categories}}
