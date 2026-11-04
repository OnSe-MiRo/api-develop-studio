from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
import unittest
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from api_test.reports import RunReport, now
from test_contracts import document


class HeaderArrayTests(unittest.TestCase):
    def spec(self, items, version='3.0.3', **constraints):
        doc = document(version)
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {
            'X-Values': {'required': True, 'schema': {'type': 'array', 'items': items, **constraints}}}
        return doc

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200,
                                 {'Content-Type': 'application/json', 'x-values': value}, {'id': 1})

    def test_primitive_arrays_versions_explode_and_refs(self):
        for version in ['3.0.3', '3.1.0']:
            for kind, value in [('string', 'red, blue'), ('integer', '1, 2'),
                                ('number', '1.5,2e2'), ('boolean', 'true, false')]:
                for explode in [None, False, True]:
                    with self.subTest(version=version, kind=kind, explode=explode):
                        doc = self.spec({'type': kind}, version, minItems=2, maxItems=2)
                        header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values']
                        if explode is not None:
                            header.update(style='simple', explode=explode)
                        doc['components']['schemas']['Value'] = header['schema']['items']
                        header['schema']['items'] = {'$ref': '#/components/schemas/Value'}
                        doc['components']['schemas']['Values'] = header['schema']
                        header['schema'] = {'$ref': '#/components/schemas/Values'}
                        doc['components']['headers'] = {'Values': deepcopy(header)}
                        doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values'] = {'$ref': '#/components/headers/Values'}
                        result = self.check(doc, value)
                        self.assertTrue(result['valid'], result)

    def test_constraints_and_safe_diagnostics(self):
        for version in ['3.0.3', '3.1.0']:
            for items, constraints, value, code in [
                ({'type': 'integer'}, {}, '1,PRIVATE', 'schema_type'),
                ({'type': 'number'}, {}, '1,NaN', 'schema_type'),
                ({'type': 'boolean'}, {}, 'true,PRIVATE', 'schema_type'),
                ({'type': 'integer'}, {'minItems': 2}, '1', 'schema_minItems'),
                ({'type': 'integer'}, {'maxItems': 1}, '1,2', 'schema_maxItems'),
                ({'type': 'integer'}, {'uniqueItems': True}, '1,01', 'schema_uniqueItems'),
                ({'type': 'string', 'enum': ['allowed']}, {}, 'PRIVATE', 'schema_enum'),
                ({'type': 'string', 'format': 'uuid'}, {}, 'PRIVATE', 'schema_format'),
                ({'type': 'integer', 'minimum': 2}, {}, '1', 'schema_minimum'),
            ]:
                with self.subTest(version=version, code=code):
                    result = self.check(self.spec(items, version, **constraints), value)
                    self.assertFalse(result['valid'])
                    self.assertIn(code, [item['code'] for item in result['issues']])
                    self.assertNotIn('PRIVATE', json.dumps(result))

    def test_empty_elements_are_not_dropped_or_url_decoded(self):
        doc = self.spec({'type': 'string'}, minItems=1, maxItems=1)
        self.assertTrue(self.check(doc, '')['valid'])  # Present empty header is one empty element.
        doc = self.spec({'type': 'string', 'enum': ['a%2Cb', '']}, minItems=3)
        self.assertTrue(self.check(doc, 'a%2Cb,,')['valid'])
        self.assertFalse(self.check(self.spec({'type': 'integer'}), '1,,2')['valid'])
        missing = validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})
        self.assertIn('missing_header', [item['code'] for item in missing['issues']])

    def test_unsupported_array_shapes_stay_explicit(self):
        for items in [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'object'}]:
            result = self.check(self.spec(items), 'PRIVATE')
            self.assertIn('unsupported_header_serialization', [item['code'] for item in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        doc = self.spec({'type': 'string'}, '3.1.0', prefixItems=[{'type': 'array', 'items': {'type': 'integer'}}])
        self.assertIn('unsupported_header_serialization', [item['code'] for item in self.check(doc, '1')['issues']])

    def test_real_http_runner_and_report(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Values', '1,2' if self.path.endswith('/1') else '1,PRIVATE')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'},
                    'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('header-array', case, contract_document=self.spec({'type': 'integer'}))
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
            report = RunReport()
            report.add(result, 'tag/api/header.json', now(), case_reference='tag/api/header.json')
            report.finish(0 if expected == 'passed' else 1)
            self.assertNotIn('PRIVATE', json.dumps(report.data))
            if expected == 'failed':
                self.assertEqual(report.data['targets'][0]['errorCategory'], 'contract_failed')
