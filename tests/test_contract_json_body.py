import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import Mock, patch
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from api_test.reports import RunReport, now
from api_test.services import studio
from test_contracts import document


class JsonBodyTests(unittest.TestCase):
    def spec(self, version='3.0.3', schema=None, media='application/json'):
        doc = document(version)
        doc['paths']['/items/{id}']['get']['responses']['200']['content'] = {media: {} if schema is None else {'schema': schema}}
        return doc

    def check(self, doc, raw, media='application/json'):
        return validate_response(doc, 'GET', '/items/1', 200,
                                 {'Content-Type': media, 'X-Count': '1'}, None, raw_body=raw)

    def test_bad_json_rejected_with_or_without_schema(self):
        for version in ['3.0.3', '3.1.0']:
            for schema in [None, {}]:
                for raw in ['', 'PRIVATE', '{"id":', 'NaN', 'Infinity', '-Infinity', '1e400',
                            '{"id":1,"id":2}', '{"nested":{"x":1,"x":2}}', '[0,NaN]']:
                    with self.subTest(version=version, schema=schema, raw=raw[:30]):
                        result = self.check(self.spec(version, schema), raw)
                        self.assertFalse(result['valid'])
                        self.assertEqual(result['issues'], [{'code': 'invalid_json', 'path': '#/response/body', 'severity': 'error', 'message': 'invalid_json'}])
                        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_valid_json_and_schema_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            for raw in ['null', 'false', '0', '1e2', '"text"', '[]', '{}', '{"a":{"id":1},"b":{"id":2}}']:
                self.assertTrue(self.check(self.spec(version), raw)['valid'])
            doc = self.spec(version, {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}})
            self.assertTrue(self.check(doc, '{"id":1}')['valid'])
            result = self.check(doc, '{"id":"PRIVATE"}')
            self.assertIn('schema_type', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_json_media_wildcard_and_non_json_boundaries(self):
        doc = self.spec(media='application/*')
        self.assertFalse(self.check(doc, 'PRIVATE', 'application/problem+json; charset=utf-8')['valid'])
        self.assertTrue(self.check(doc, '{"id":1}', 'application/problem+json')['valid'])
        doc = self.spec(media='text/plain', schema={'type': 'string'})
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'text/plain', 'X-Count': '1'}, 'PRIVATE', raw_body='PRIVATE')['valid'])
        doc = self.spec(schema={'type': 'integer'})
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, 1)['valid'])

    def test_no_body_status_and_header_errors_remain(self):
        doc = self.spec()
        result = validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, None, raw_body='PRIVATE')
        self.assertEqual([i['code'] for i in result['issues']], ['missing_header', 'invalid_json'])
        for status in [204, 304]:
            doc = self.spec()
            responses = doc['paths']['/items/{id}']['get']['responses']
            responses[str(status)] = responses.pop('200')
            result = validate_response(doc, 'GET', '/items/1', status, {'Content-Type': 'application/json', 'X-Count': '1'}, None, raw_body='')
            self.assertTrue(result['valid'])
            result = validate_response(doc, 'GET', '/items/1', status, {'Content-Type': 'application/json', 'X-Count': '1'}, None, raw_body='{}')
            self.assertIn('unexpected_body', [i['code'] for i in result['issues']])

    def test_quick_call_rejects_duplicate_keys_without_leaking_values(self):
        store = Mock(); store.get.return_value = Mock(document={'docs_file': {'document': self.spec()}})
        settings = Mock(auth_profiles={}, variables={}, encrypted_variables={}, base_url='https://example.test')
        with patch.object(studio, 'collaboration_store', return_value=store), patch.object(studio, 'project_request_settings', return_value=settings), patch.object(studio, 'local_policy', return_value={'skip_verification': True}), patch.object(studio, 'execute_http_call', return_value=(200, {'Content-Type': 'application/json', 'X-Count': '1'}, '{"id":"PRIVATE","id":2}', 1)):
            result = studio.handle_api_request({'project': 'demo.json', 'url': '/items/1', 'validateContract': True})
        self.assertFalse(result['contract']['valid'])
        self.assertNotIn('PRIVATE', json.dumps(result['contract']))

    def test_real_http_runner_contract_opt_in_and_reports(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}' if self.path.endswith('/1') else b'{"id":"PRIVATE","id":2}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Count', '1'); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, enabled, expected in [('1', True, 'passed'), ('2', True, 'failed'), ('2', False, 'passed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': enabled}}
            result = ApiTestRunner().run_case('json-body', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            report = RunReport(); report.add(result, 'tag/api/body.json', now(), case_reference='tag/api/body.json'); report.finish(0 if expected == 'passed' else 1)
            self.assertNotIn('PRIVATE', json.dumps(report.data))
            if expected == 'failed': self.assertEqual(report.data['targets'][0]['errorCategory'], 'contract_failed')
