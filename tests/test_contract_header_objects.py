import json
import unittest
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from api_test.reports import RunReport, now
from test_contracts import document


class HeaderObjectTests(unittest.TestCase):
    def spec(self, version='3.0.3', explode=None, schema=None):
        doc = document(version)
        header = {'required': True, 'schema': schema if schema is not None else {
            'type': 'object', 'required': ['id', 'active'], 'additionalProperties': False,
            'properties': {'id': {'type': 'integer', 'minimum': 1}, 'active': {'type': 'boolean'}}}}
        if explode is not None:
            header.update(style='simple', explode=explode)
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Metadata': header}
        return doc

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-metadata': raw}, {'id': 1})

    def test_versions_explode_refs_and_primitive_types(self):
        for version in ['3.0.3', '3.1.0']:
            for explode in [None, False, True]:
                with self.subTest(version=version, explode=explode):
                    doc = self.spec(version, explode)
                    header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata']
                    header['schema']['properties'].update(ratio={'type': 'number'}, name={'type': 'string', 'enum': ['a%2Cb']})
                    doc['components']['schemas']['Id'] = {'type': 'integer', 'minimum': 1}
                    header['schema']['properties']['id'] = {'$ref': '#/components/schemas/Id'}
                    doc['components']['schemas']['Metadata'] = header['schema']
                    header['schema'] = {'$ref': '#/components/schemas/Metadata'}
                    doc['components']['headers'] = {'Metadata': deepcopy(header)}
                    doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata'] = {'$ref': '#/components/headers/Metadata'}
                    raw = 'id=2, active=true,ratio=1.5,name=a%2Cb' if explode else 'id,2, active,true,ratio,1.5,name,a%2Cb'
                    result = self.check(doc, raw)
                    self.assertTrue(result['valid'], result)

    def test_schema_failures_and_value_free_diagnostics(self):
        for version in ['3.0.3', '3.1.0']:
            for raw, code in [('id,PRIVATE,active,true', 'schema_type'), ('id,0,active,true', 'schema_minimum'),
                              ('id,1', 'schema_required'), ('id,1,active,true,extra,PRIVATE', 'schema_additionalProperties')]:
                result = self.check(self.spec(version), raw)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_malformed_pairs_duplicates_and_empty_keys(self):
        for explode, values in [(False, ['id,1,active', 'id,1,id,2', ',PRIVATE']),
                                (True, ['id=1,PRIVATE', 'id=1,id=2', '=PRIVATE'])]:
            for value in values:
                result = self.check(self.spec(explode=explode), value)
                self.assertEqual([i['code'] for i in result['issues']], ['invalid_header_serialization'])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_maps_empty_values_and_property_constraints(self):
        schema = {'type': 'object', 'additionalProperties': {'type': 'integer'}, 'minProperties': 2, 'maxProperties': 2}
        self.assertTrue(self.check(self.spec(schema=schema), 'a,1,b,2')['valid'])
        self.assertFalse(self.check(self.spec(schema=schema), 'a,1')['valid'])
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'additionalProperties': False}
        self.assertTrue(self.check(self.spec(schema=schema), '')['valid'])
        self.assertTrue(self.check(self.spec(schema=schema), 'name,')['valid'])
        self.assertTrue(self.check(self.spec(schema=schema, explode=True), 'name=a=b')['valid'])
        self.assertTrue(self.check(self.spec(schema={'type': 'object'}), 'name,raw')['valid'])

    def test_unsupported_ambiguous_schemas(self):
        for field in [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'object'}, {}, {'anyOf': [{'type': 'integer'}, {'type': 'string'}]}]:
            schema = {'type': 'object', 'properties': {'id': field}}
            result = self.check(self.spec(schema=schema), 'id,PRIVATE')
            self.assertEqual([i['code'] for i in result['issues']], ['unsupported_header_serialization'])
            self.assertNotIn('PRIVATE', json.dumps(result))
        schema = {'type': 'object', 'allOf': [{'oneOf': [{'properties': {'id': {'type': 'integer'}}}, {'properties': {'id': {'type': 'string'}}}]}]}
        self.assertIn('unsupported_header_serialization', [i['code'] for i in self.check(self.spec(schema=schema), 'id,1')['issues']])

    def test_real_http_runner_and_reports(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Metadata', 'id=2,active=true' if self.path.endswith('/1') else 'id=PRIVATE,active=true')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('object-header', case, contract_document=self.spec(explode=True))
            self.assertEqual(result.status, expected)
            report = RunReport(); report.add(result, 'tag/api/header.json', now(), case_reference='tag/api/header.json'); report.finish(0 if expected == 'passed' else 1)
            self.assertNotIn('PRIVATE', json.dumps(report.data))
            if expected == 'failed': self.assertEqual(report.data['targets'][0]['errorCategory'], 'contract_failed')
