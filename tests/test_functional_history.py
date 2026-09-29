import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api_test.database import RequestContext
from api_test.execution_history import ExecutionHistory
from api_test.reports import failed_run_request
from react_server import app


class FunctionalHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.history = ExecutionHistory(self.root / 'studio.db')
        self.targets = [{'kind': 'case', 'reference': 'tag/api/pass.json'},
                        {'kind': 'pipeline', 'reference': 'flows/fail.json'}]
        self.report = {'targets': [
            {'target': 'tag/api/pass.json', 'caseReference': 'tag/api/pass.json', 'status': 'passed', 'assertions': []},
            {'target': '/some/path/pipelines/flows/fail.json', 'caseReference': 'tag/api/fail.json',
             'status': 'failed', 'phase': 'teardown', 'errorCategory': 'assertion_failed',
             'body': 'secret-marker', 'headers': {'Authorization': 'secret-marker'},
             'assertions': [{'index': 0, 'passed': False, 'actual': 'secret-marker'}]},
        ], 'actor': 'spoofed', 'output': 'secret-marker'}

    def record(self, run_id='run-failed', **overrides):
        timestamp = datetime.now(timezone.utc).isoformat()
        values = dict(run_id=run_id, started_at=timestamp, finished_at=timestamp, duration_ms=100,
                      status='failed', exit_code=1, projects=['p.json'], targets=self.targets,
                      report=self.report, environment='qa', project_environments={'p.json': 'qa'})
        values.update(overrides)
        self.history.record(**values)
        return self.history.detail(run_id)

    def test_details_survive_reopen_and_redact_payload_and_assertion_values(self):
        with patch.dict('os.environ', {'APP_VERSION': 'v1', 'APP_COMMIT': 'abc123'}):
            self.record()
        run = ExecutionHistory(self.history.path).detail('run-failed')
        self.assertEqual((run['actor'], run['environment'], run['appVersion'], run['commit']),
                         ('local-user', 'qa', 'v1', 'abc123'))
        self.assertEqual(run['detail']['projectEnvironments'], {'p.json': 'qa'})
        self.assertEqual(run['detail']['outcomes'][1]['assertions'], [{'index': 0, 'passed': False}])
        self.assertNotIn(b'secret-marker', self.history.path.read_bytes())
        self.assertNotIn('spoofed', json.dumps(run))
        self.assertNotIn('detail', self.history.dashboard()['items'][0])

    def test_default_environment_is_resolved_from_project_without_secret_values(self):
        from api_test.services.studio import execution_environments
        project = {'default_environment': 'staging', 'variables': {'secret': {'TOKEN': 'secret-marker'}}}
        with patch('react_server.read_studio_document', return_value=project):
            self.assertEqual(execution_environments(['p.json'], None), {'p.json': 'staging'})
            self.assertEqual(execution_environments(['p.json'], 'qa'), {'p.json': 'qa'})
        with patch('react_server.read_studio_document', side_effect=OSError()):
            self.assertEqual(execution_environments(['missing.json'], None), {'missing.json': None})

    def test_failure_rerun_keeps_whole_pipeline_and_environment(self):
        run = self.record()
        self.assertEqual(failed_run_request(run), {'cases': [], 'pipelines': ['flows/fail.json'], 'environment': 'qa'})
        self.assertEqual(run['detail']['outcomes'][1]['phase'], 'teardown')

    def test_nested_pipeline_references_select_the_most_specific_saved_target(self):
        targets = [{'kind': 'pipeline', 'reference': 'fail.json'},
                   {'kind': 'pipeline', 'reference': 'flows/fail.json'}]
        run = self.record(targets=targets)
        self.assertEqual(failed_run_request(run)['pipelines'], ['flows/fail.json'])

    def test_preview_success_and_legacy_cannot_rerun(self):
        for key, options in [('preview', {'targets': [{'kind': 'case', 'reference': 'x.json', 'preview': True}]}),
                             ('passed', {'status': 'passed'})]:
            self.assertIsNone(failed_run_request(self.record(key, **options)))
        self.record('legacy')
        with self.history.connect() as db:
            db.execute('UPDATE executions SET detail_json = NULL WHERE run_id = ?', ('legacy',))
        self.assertIsNone(failed_run_request(self.history.detail('legacy')))

    def test_interrupted_run_retries_original_saved_targets(self):
        run = self.record(status='timeout', report=None)
        self.assertEqual(failed_run_request(run)['cases'], ['tag/api/pass.json'])
        self.assertEqual(failed_run_request(run)['pipelines'], ['flows/fail.json'])

    def test_literal_search_pagination_summary_and_workspace_isolation(self):
        self.record('run_100%')
        self.record('other')
        self.assertEqual(self.history.dashboard(search='100%')['total'], 1)
        self.assertEqual(self.history.dashboard(search='FLOWs/fail')['total'], 2)
        self.assertEqual(self.history.dashboard(search="' OR 1=1 --")['total'], 0)
        self.assertEqual(self.history.dashboard(search='missing')['summary']['total'], 2)
        other = ExecutionHistory(self.history.path, context=RequestContext('other', 'local-user'))
        self.assertIsNone(other.detail('run_100%'))
        self.assertEqual(other.dashboard()['total'], 0)
        with self.assertRaises(ValueError):
            self.history.dashboard(search='x' * 201)

    def test_http_detail_errors_and_rerun_submission_ignores_body_override(self):
        self.record()
        pipelines = self.root / 'pipelines'
        (pipelines / 'flows').mkdir(parents=True)
        (pipelines / 'flows/fail.json').write_text('{}')
        with patch('react_server.execution_history', return_value=self.history), patch('react_server.PIPELINE_ROOT', pipelines), TestClient(app) as client:
            self.assertEqual(client.get('/api/executions/missing').status_code, 404)
            self.assertEqual(client.post('/api/executions/run-failed/rerun', content=b'x' * (1024 * 1024 + 1)).status_code, 413)
            self.assertEqual(client.get('/api/executions/run-failed').json()['environment'], 'qa')
            self.assertEqual(client.get('/api/dashboard?search=' + 'x' * 201).status_code, 400)
            with patch('api_test.services.execution.submit_run', return_value={'runId': 'new'}) as submit:
                response = client.post('/api/executions/run-failed/rerun', json={'environment': 'production', 'cases': ['evil']})
                self.assertEqual(response.status_code, 200)  # mocked transport, actual submit_run returns 202
                self.assertEqual(submit.call_args.args[2], {'cases': [], 'pipelines': ['flows/fail.json'], 'environment': 'qa'})
            (pipelines / 'flows/fail.json').unlink()
            self.assertEqual(client.post('/api/executions/run-failed/rerun', json={}).status_code, 409)
            self.record('success', status='passed')
            self.assertEqual(client.post('/api/executions/success/rerun', json={}).status_code, 409)

    def test_http_rerun_enters_async_queue_and_retains_environment(self):
        self.record()
        pipelines = self.root / 'pipelines'
        (pipelines / 'flows').mkdir(parents=True)
        (pipelines / 'flows/fail.json').write_text('{}')
        with patch('react_server.execution_history', return_value=self.history), patch('react_server.PIPELINE_ROOT', pipelines), patch('api_test.services.execution.execute_job', return_value={'status': 'passed'}) as execute, TestClient(app) as client:
            response = client.post('/api/executions/run-failed/rerun', json={})
            self.assertEqual(response.status_code, 202)
            run_id = response.json()['runId']
            self.assertNotEqual(run_id, 'run-failed')
            app.state.jobs.jobs[run_id].done.wait(5)
            self.assertEqual(client.get('/api/runs/' + run_id).json()['status'], 'passed')
            self.assertEqual(execute.call_args.args[-1], 'qa')
