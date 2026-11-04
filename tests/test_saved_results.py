import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api_test.database import LOCAL_CONTEXT, RequestContext
from api_test.execution_history import ExecutionHistory
from api_test.main import create_app
from api_test.saved_results import SavedResults
from api_test.services import studio


class SavedResultsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.enterContext(patch.dict(os.environ, {'STUDIO_DB_PATH': str(self.root / 'studio.db'),
            'STUDIO_DATABASE_URL': '', 'STUDIO_DATABASE_URL_FILE': '', 'STUDIO_AUTH_MODE': 'local',
            'LOCAL_SERVER': 'true', 'SKIP_OWNERSHIP_VERIFICATION': 'true'}))
        for name, value in {'ROOT': self.root, 'CASE_ROOT': self.root / 'case',
                            'PROJECT_ROOT': self.root / 'project', 'PIPELINE_ROOT': self.root / 'pipeline',
                            '_COLLABORATION_STORE': None}.items():
            self.enterContext(patch.object(studio, name, value))
        studio.collaboration_store()
        self.history = ExecutionHistory(self.root / 'studio.db')
        self.store = SavedResults(self.history)
        self.app = create_app(studio)
        self.client = self.enterContext(TestClient(self.app, base_url='http://127.0.0.1:8765'))

    def completed(self, status='passed'):
        import threading
        done = threading.Event()
        def task(job):
            done.set()
            return {'status': status, 'output': 'sanitized result', 'exitCode': 0}
        job = self.app.state.jobs.submit(task, initial={'project': 'demo.json', 'caseReference': 'tag/api/case.json'})
        self.assertTrue(done.wait(2))
        self.assertTrue(self.app.state.jobs.jobs[job['runId']].done.wait(2))
        return job['runId']

    def test_save_uses_server_snapshot_is_idempotent_and_survives_job_loss(self):
        run_id = self.completed()
        self.assertEqual(self.store.list('demo.json', 'tag/api/case.json'), [])
        response = self.client.post(f'/api/runs/{run_id}/save', json={'output': 'FORGED', 'project': 'other'})
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(saved['output'], 'sanitized result')
        self.assertEqual(saved['project'], 'demo.json')
        self.app.state.jobs.jobs.clear()
        self.assertEqual(self.client.get(f'/api/runs/{run_id}').status_code, 404)
        self.assertEqual(self.client.post(f'/api/runs/{run_id}/save').json(), saved)
        self.assertEqual(SavedResults(ExecutionHistory(self.history.path)).get(run_id), saved)
        self.assertEqual(self.client.get(f'/api/saved-results/{run_id}').json(), saved)
        listing = self.client.get('/api/saved-results', params={'project': 'demo.json', 'caseReference': 'tag/api/case.json'})
        self.assertEqual([item['runId'] for item in listing.json()['items']], [run_id])
        self.assertNotIn('output', listing.text)
        self.assertEqual(self.store.list('other.json', 'tag/api/case.json'), [])
        self.assertEqual(self.client.get('/api/saved-results/missing').status_code, 404)

    def test_running_rejected_failure_saved_and_case_identity_from_submission(self):
        import threading
        release = threading.Event()
        self.addCleanup(release.set)
        with patch('api_test.services.execution.execute_job', side_effect=lambda *args: (release.wait(2) and {}) or {'status': 'failed', 'output': 'failure'}), patch.object(studio, 'ensure_run_ready'):
            response = self.client.post('/api/runs', json={'inlineCase': {'project': 'demo.json', 'request': {'url': '/items'}, 'expected': {}}, 'caseReference': 'tag/api/case.json'})
            self.assertEqual(response.status_code, 202, response.text)
            run_id = response.json()['runId']
            self.assertEqual(response.json()['project'], 'demo.json')
            self.assertEqual(response.json()['caseReference'], 'tag/api/case.json')
            self.assertEqual(self.client.post(f'/api/runs/{run_id}/save').status_code, 409)
            self.app.state.jobs.cancel(run_id)
            release.set()
            self.app.state.jobs.jobs[run_id].done.wait(3)
        failure = self.completed('failed')
        self.assertEqual(self.client.post(f'/api/runs/{failure}/save').json()['status'], 'failed')

    def test_user_workspace_isolation_and_read_only_role(self):
        run_id = self.completed()
        self.assertEqual(self.client.post(f'/api/runs/{run_id}/save').status_code, 200)
        contexts = [RequestContext(LOCAL_CONTEXT.workspace_id, 'other-user'), RequestContext('other-workspace', LOCAL_CONTEXT.user_id)]
        with self.history.connect() as connection:
            connection.execute("INSERT INTO users(id, display_name, created_at) VALUES ('other-user', 'other', 'now')")
            connection.execute("INSERT INTO workspaces(id, name, created_at) VALUES ('other-workspace', 'other', 'now')")
            for context in contexts:
                connection.execute("INSERT INTO memberships(workspace_id, user_id, role, created_at) VALUES (?, ?, 'viewer', 'now')", (context.workspace_id, context.user_id))
        for context in contexts:
            store = SavedResults(ExecutionHistory(self.history.path, context=context))
            self.assertIsNone(store.get(run_id))
            self.assertEqual(store.list('demo.json', 'tag/api/case.json'), [])
            with self.assertRaises(PermissionError):
                store.save({'runId': 'forged'})
        with self.history.connect() as connection:
            connection.execute("UPDATE memberships SET role = 'viewer' WHERE workspace_id = ? AND user_id = ?", (LOCAL_CONTEXT.workspace_id, LOCAL_CONTEXT.user_id))
        self.assertEqual(self.client.post(f'/api/runs/{run_id}/save').status_code, 403)
