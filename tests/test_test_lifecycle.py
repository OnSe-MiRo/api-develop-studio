from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from api_test.cli import run_pipeline
from api_test.runner import CaseConfigurationError, CaseResult, HttpResponse
from api_test.test_data import generate, resolve, extract
from api_test.test_coverage import linked_operation, source_for, sync_preview, apply_sync, response_key
from api_test.services.studio import openapi_document_operations
from api_test.reports import RunReport, history_targets
from api_test.execution_history import ExecutionHistory


def spec(path='/items', status='200'):
    return {'openapi': '3.0.3', 'info': {'title': 'test', 'version': '1'}, 'paths': {path: {'get': {'operationId': 'items', 'responses': {status: {'description': 'OK'}}}}}}


class CoverageTest(unittest.TestCase):
    def test_response_range_and_default_use_most_specific_status(self):
        responses = [{'status': value} for value in ['200', '2XX', 'default']]
        self.assertEqual(response_key(200, responses), '200')
        self.assertEqual(response_key(201, responses), '2XX')
        self.assertEqual(response_key(404, responses), 'default')
        self.assertIsNone(response_key(404, responses[:2]))

    def test_link_identity_survives_path_change_and_preserves_user_values(self):
        old = spec(); op = openapi_document_operations(old)[0]
        case = {'spec_source': source_for(op, old), 'request': {'method': 'GET', 'url': '/items', 'headers': {'X-Key': 'private'}, 'body': {'a': 1}}, 'expected': {'status': 200, 'assertions': [{'path': 'body.id'}]}, 'variables': {'secret': {'a': 'cipher'}}}
        new = spec('/new', '201'); operation = linked_operation(case, openapi_document_operations(new))
        preview = sync_preview(case, operation, source_for(operation, new))
        changed = apply_sync(case, preview, ['request.url', 'expected.status'])
        self.assertEqual(changed['request']['url'], '/new')
        self.assertEqual(changed['expected']['status'], 201)
        self.assertEqual(changed['expected']['assertions'], case['expected']['assertions'])
        self.assertEqual(changed['variables'], case['variables'])
        self.assertEqual(changed['request']['headers'], case['request']['headers'])
        self.assertNotIn('private', json.dumps(preview))
        case['request']['url'] = '/custom?key=secret'
        preview = sync_preview(case, operation, source_for(operation, new))
        with self.assertRaises(ValueError): apply_sync(case, preview, ['request.url'])
        self.assertEqual(apply_sync(case, preview, [])['request']['url'], '/custom?key=secret')

    def test_inference_ambiguity_removed_operations_and_component_changes(self):
        doc = spec('/items/{id}'); operations = openapi_document_operations(doc)
        case = {'request': {'method': 'GET', 'url': 'https://example.test/items/42'}}
        self.assertEqual(linked_operation(case, operations), operations[0])
        self.assertIsNone(linked_operation(case, operations * 2))
        case['spec_source'] = source_for(operations[0], doc)
        self.assertIsNone(linked_operation(case, []))
        doc['components'] = {'schemas': {'Item': {'type': 'string'}}}
        self.assertTrue(sync_preview(case, operations[0], source_for(operations[0], doc))['changed'])

    def test_history_only_persists_outcomes_and_excludes_previews(self):
        report = RunReport(); report.add(CaseResult('a', 'passed', 1, HttpResponse(200, {}, {'secret': 'never-persist'})), 'pipe', 'now', 'p', 'tag/api/a.json')
        targets = history_targets([], report.data)
        self.assertNotIn('secret', json.dumps(targets))
        self.assertEqual(history_targets([{'preview': True}], report.data), [{'preview': True}])
        with tempfile.TemporaryDirectory() as root:
            history = ExecutionHistory(Path(root) / 'history.db')
            history.record(run_id='one', started_at='2026-09-20', finished_at='2026-09-20T12:00:00Z', duration_ms=1, status='failed', exit_code=1, projects=['p'], targets=targets)
            self.assertIn(('tag/api/a.json', '200'), history.case_successes('p'))
            self.assertEqual(history.case_successes('other'), {})


class DataLifecycleTest(unittest.TestCase):
    def test_allowlist_seed_and_typed_resolution(self):
        defs = {'id': {'type': 'uuid'}, 'time': {'type': 'timestamp'}, 'n': {'type': 'integer', 'min': 2, 'max': 2}}
        a = generate(defs, 'fixed')
        self.assertEqual(a, generate(defs, 'fixed'))
        self.assertNotEqual(generate(defs)['id'], generate(defs)['id'])
        self.assertEqual(resolve({'id': '${run.n}', 'url': '/a/${run.n}'}, a), {'id': 2, 'url': '/a/2'})
        for bad in ({'x': {'type': 'shell'}}, {'x': {'type': 'integer', 'min': 4, 'max': 1}}):
            with self.assertRaises(CaseConfigurationError): generate(bad)
        with self.assertRaises(CaseConfigurationError): resolve('${run.missing}', {})
        with self.assertRaises(CaseConfigurationError): extract({'id': 'body.missing'}, HttpResponse(200, {}, {}))

    def execute_pipeline(self, root, fail=False, cleanup_fail=False, invalid=False):
        root.mkdir(exist_ok=True)
        for name in ['create', 'test', 'cleanup', 'last']:
            (root / (name + '.json')).write_text(json.dumps({'request': {'url': '/'+name}, 'expected': {'status': 200}}))
        pipeline = {'generators': {'id': {'type': 'uuid'}}, 'seed': str(root), 'steps': [
            {'name': 'create', 'case': 'create.json', 'phase': 'setup', 'extract': {'created': 'body.id'}},
            {'name': 'test', 'case': 'missing.json' if invalid else 'test.json'},
            {'name': 'cleanup', 'case': 'cleanup.json', 'phase': 'teardown'},
            {'name': 'last', 'case': 'last.json', 'phase': 'teardown'}]}
        path = root / 'pipe.json'; path.write_text(json.dumps(pipeline))
        seen = []
        def run(runner, name, case, *args, **kwargs):
            seen.append((name, deepcopy(runner.run_variables)))
            status = 'failed' if (name == 'test' and fail or name == 'cleanup' and cleanup_fail) else 'passed'
            return CaseResult(name, status, 1, HttpResponse(200, {}, {'id': 'extracted-secret'}), sensitive_values=set(str(v) for v in runner.run_variables.values()))
        report = RunReport()
        with patch('api_test.cli._run_case_with_project_settings', side_effect=run), contextlib.redirect_stdout(io.StringIO()) as output:
            code = run_pipeline(path, root, 1, root / 'logs', report_result=report)
        self.assertNotIn('extracted-secret', output.getvalue())
        return code, seen, report

    def test_failure_and_configuration_error_still_run_all_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, kwargs in enumerate(({'fail': True}, {'invalid': True}, {'cleanup_fail': True})):
                code, seen, report = self.execute_pipeline(Path(directory) / str(index), **kwargs)
                self.assertEqual(code, 1)
                self.assertEqual([name for name, _ in seen][-2:], ['cleanup', 'last'])
                self.assertEqual(seen[-1][1]['created'], 'extracted-secret')
                self.assertEqual(report.data['targets'][-1]['phase'], 'teardown')

    def test_parallel_run_variable_isolation(self):
        # Exercise independent generator state concurrently without globally patched runner.
        with ThreadPoolExecutor() as pool:
            values = list(pool.map(lambda seed: generate({'id': {'type': 'uuid'}}, seed), range(30)))
        self.assertEqual(len({v['id'] for v in values}), 30)
        values[0]['extracted'] = 'one-run-only'
        self.assertTrue(all('extracted' not in v for v in values[1:]))

    def test_concurrent_pipeline_runs_use_their_own_extracted_variables(self):
        import threading
        barrier = threading.Barrier(2)
        seen = []
        def send(url, **kwargs):
            seen.append(url)
            if '/setup/' in url:
                barrier.wait(timeout=5)
            return 200, {}, json.dumps({'id': url.rsplit('/', 1)[-1]}), 1
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'setup.json').write_text(json.dumps({'request': {'url': 'https://example.test/setup/${run.id}'}, 'expected': {'status': 200}}))
            (root/'cleanup.json').write_text(json.dumps({'request': {'url': 'https://example.test/cleanup/${run.created}'}, 'expected': {'status': 200}}))
            for seed in (1, 2):
                (root/f'{seed}.json').write_text(json.dumps({'seed': seed, 'generators': {'id': {'type': 'uuid'}}, 'steps': [{'case': 'setup.json', 'phase': 'setup', 'extract': {'created': 'body.id'}}, {'case': 'cleanup.json', 'phase': 'teardown'}]}))
            with patch('api_test.cli.local_policy', return_value={'skip_verification': True}), patch('api_test.runner.execute_http_call', side_effect=send), ThreadPoolExecutor() as pool:
                codes = list(pool.map(lambda seed: run_pipeline(root/f'{seed}.json', root, 1, root/f'logs-{seed}'), (1, 2)))
            self.assertEqual(codes, [0, 0])
            for seed in (1, 2):
                uid = generate({'id': {'type': 'uuid'}}, seed)['id']
                self.assertIn('https://example.test/cleanup/'+uid, seen)
