"""Socket-level load-test API smoke through the actual Uvicorn application."""
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import uvicorn

from api_test.load_results import import_k6_result
from api_test.main import app


class LoadTestLiveHttpTests(unittest.TestCase):
    def test_import_list_detail_and_series_over_loopback(self):
        fixture = Path(__file__).parent / "fixtures" / "load-tests"
        result = import_k6_result(fixture / "smoke-summary.json", fixture / "smoke-raw.jsonl")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "STUDIO_DB_PATH": str(Path(directory) / "studio.db"), "STUDIO_DATABASE_URL": "", "STUDIO_DATABASE_URL_FILE": ""}):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            host = f"http://127.0.0.1:{listener.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
            worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            worker.start()
            try:
                deadline = time.monotonic() + 5
                while not server.started and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(server.started)

                def call(method, path, body=None):
                    payload = json.dumps(body).encode() if body is not None else None
                    request = Request(host + path, data=payload, method=method,
                                      headers={"Content-Type": "application/json"} if payload else {})
                    try:
                        with urlopen(request, timeout=5) as response:
                            return response.status, json.load(response)
                    except HTTPError as exc:
                        return exc.code, json.load(exc)

                run_id = result["run"]["id"]
                self.assertEqual(call("POST", "/api/load-tests/runs", result)[0], 201)
                self.assertEqual(call("POST", "/api/load-tests/runs", result)[0], 409)
                self.assertEqual(call("GET", "/api/load-tests/runs?limit=1")[1]["items"][0]["run"]["id"], run_id)
                self.assertEqual(call("GET", "/api/load-tests/runs/" + run_id)[1]["summary"], result["summary"])
                self.assertEqual(call("GET", "/api/load-tests/runs/" + run_id + "/series?maxPoints=1")[1]["sourcePoints"], 2)
            finally:
                server.should_exit = True
                worker.join(timeout=5)
                listener.close()
                self.assertFalse(worker.is_alive())
