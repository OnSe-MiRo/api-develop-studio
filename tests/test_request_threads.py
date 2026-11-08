"""Request contexts and idle worker reclamation through the real HTTP dispatch."""
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from api_test.request_scope import current_context


class RequestThreadLifecycleTests(unittest.TestCase):
    def setUp(self):
        from test_workspace_isolation import WorkspaceIsolationTest
        WorkspaceIsolationTest.setUp(self)

    def test_completed_http_burst_reclaims_idle_threads_and_keeps_scope(self):
        baseline_ids = {t.ident for t in threading.enumerate()}
        from api_test.implementations import documents
        original = documents.list_documents
        gate = threading.Event()
        lock = threading.Lock()
        workers, contexts = set(), []

        def handle(*args):
            with lock:
                workers.add(threading.get_ident())
                contexts.append(current_context().workspace_id)
            gate.wait(4)
            return original(*args)

        with patch.object(documents, 'list_documents', handle), ThreadPoolExecutor(6) as clients:
            futures = [clients.submit(self.client.get, '/api/projects',
                                      headers={'test-principal': 'team-a-owner'}) for _ in range(6)]
            try:
                end = time.monotonic() + 3
                while len(workers) < 6 and time.monotonic() < end:
                    time.sleep(.01)
                self.assertEqual(len(workers), 6)
            finally:
                gate.set()
            for future in futures:
                self.assertEqual(future.result(timeout=3).status_code, 200)
        self.assertEqual(contexts, ['team-a'] * 6)
        conflict = self.client.put('/api/projects/same.json', headers={'test-principal': 'team-a-owner'},
                                   json={'name':'conflict', 'base_url':'https://example.test'})
        self.assertEqual(conflict.status_code, 409)
        def remaining():
            return [t.name for t in threading.enumerate() if t.ident not in baseline_ids and
                    (t.name.startswith('studio-http-') or t.name == 'AnyIO worker thread')]
        end = time.monotonic() + 2
        while remaining() and time.monotonic() < end:
            time.sleep(.02)
        self.assertFalse(remaining())
        self.assertEqual(self.client.get('/api/projects', headers={'test-principal':'team-b-owner'}).status_code,200)
