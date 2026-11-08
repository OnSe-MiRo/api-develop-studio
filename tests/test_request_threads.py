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


class RequestShutdownTests(unittest.TestCase):
    def test_cleanup_failure_still_closes_jobs_and_request_pool(self):
        from fastapi.testclient import TestClient
        from api_test.main import create_app
        from api_test.services import studio
        app = create_app(studio)
        with patch('api_test.services.mock.manager.stop_all', side_effect=RuntimeError('cleanup failure')):
            with self.assertRaisesRegex(RuntimeError, 'cleanup failure'):
                with TestClient(app):
                    pass
        self.assertTrue(app.state.jobs.closed)
        self.assertTrue(app.state.request_threads.closed)


    def test_app_can_start_a_fresh_request_pool_after_completed_lifespan(self):
        from fastapi.testclient import TestClient
        from api_test.main import create_app
        from api_test.services import studio
        from api_test.request_threads import for_app, RequestThreadsUnavailable
        app = create_app(studio)
        async def probe():
            return await for_app(app).run_sync(lambda: 'ok')
        app.add_api_route('/__thread_test__', probe)
        app.router.routes.insert(0, app.router.routes.pop())
        with TestClient(app) as client:
            self.assertEqual(client.get('/__thread_test__').json(), 'ok')
            first = app.state.request_threads
            app.state.request_threads_closing = True
            with self.assertRaises(RequestThreadsUnavailable):
                for_app(app)
            app.state.request_threads_closing = False
        self.assertTrue(first.closed)
        second = TestClient(app)
        try:
            self.assertEqual(second.get('/__thread_test__').json(), 'ok')
            self.assertIsNot(app.state.request_threads, first)
        finally:
            app.state.request_threads.shutdown()
            second.close()
