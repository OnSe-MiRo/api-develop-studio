import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class ComposedHeaderObjectTests(unittest.TestCase):
    def spec(self, version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['HeaderBase'] = {'type': 'object', 'properties': {'id': {'type': 'integer', 'minimum': 1}}, 'required': ['id']}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Object': {'required': True, 'schema': {'allOf': [
            {'$ref': '#/components/schemas/HeaderBase'}, {'properties': {'active': {'type': 'boolean'}}, 'required': ['active']},
            {'minProperties': 2, 'maxProperties': 2, 'properties': {'id': {'maximum': 5}}}]}}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Object']

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-object': raw}, {'id': 1})

    def test_versions_refs_explode_and_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            doc = self.spec(version)
            self.assertTrue(self.check(doc, 'id,2,active,true')['valid'])
            for raw, code in [('id,0,active,true', 'schema_minimum'), ('id,6,active,true', 'schema_maximum'),
                              ('id,2', 'schema_required'), ('id,2,active,true,extra,x', 'schema_maxProperties'),
                              ('id,PRIVATE,active,true', 'schema_type')]:
                result = self.check(doc, raw)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))
            self.header(doc)['explode'] = True
            self.assertTrue(self.check(doc, 'id=2,active=false')['valid'])
            self.assertFalse(self.check(doc, 'id=2,id=3,active=true')['valid'])

    def test_closed_branch_is_not_opened_by_collecting_sibling_properties(self):
        for version in ['3.0.3', '3.1.0']:
            doc = self.spec(version)
            doc['components']['schemas']['HeaderBase']['additionalProperties'] = False
            result = self.check(doc, 'id,2,active,true')
            self.assertIn('schema_additionalProperties', [i['code'] for i in result['issues']])
            # Correctly redeclaring both properties in the closed branch permits them.
            doc['components']['schemas']['HeaderBase']['properties']['active'] = {'type': 'boolean'}
            self.assertTrue(self.check(doc, 'id,2,active,true')['valid'])

    def test_additional_schema_applies_only_to_locally_undeclared_fields(self):
        doc = self.spec()
        self.header(doc)['schema'] = {'allOf': [
            {'type': 'object', 'properties': {'id': {'type': 'integer'}}},
            {'properties': {'name': {'type': 'string'}}, 'additionalProperties': {'type': 'number', 'minimum': 1}}]}
        self.assertTrue(self.check(doc, 'id,2,name,hello,extra,1.5')['valid'])
        self.assertFalse(self.check(doc, 'id,0,name,hello')['valid'])
        self.assertFalse(self.check(doc, 'id,2.5,name,hello')['valid'])
        self.assertFalse(self.check(doc, 'id,2,name,hello,extra,PRIVATE')['valid'])

    def test_nested_nullable_and_empty_object(self):
        doc = self.spec('3.1.0')
        doc['components']['schemas']['HeaderBase']['type'] = ['object', 'null']
        doc['components']['schemas']['HeaderBase']['properties']['id']['type'] = ['integer', 'null']
        self.header(doc)['schema'] = {'allOf': [self.header(doc)['schema']]}
        self.assertTrue(self.check(doc, 'id,2,active,true')['valid'])
        self.assertFalse(self.check(doc, 'id,null,active,true')['valid'])
        self.header(doc)['schema'] = {'allOf': [{'type': 'object'}, {'maxProperties': 0}]}
        self.assertTrue(self.check(doc, '')['valid'])
        self.assertFalse(self.check(doc, 'id,1')['valid'])

    def test_unsupported_shapes_and_cycles_fail_safely(self):
        for extra in [{'oneOf': [{'required': ['a']}, {'required': ['b']}]},
                      {'properties': {'nested': {'type': 'object'}}},
                      {'patternProperties': {'^x': {'type': 'integer'}}},
                      {'unevaluatedProperties': False}]:
            doc = self.spec('3.1.0')
            self.header(doc)['schema'] = {'allOf': [{'type': 'object'}, extra]}
            self.assertFalse(self.check(doc, 'nested,PRIVATE')['valid'])
        doc = self.spec()
        doc['components']['schemas']['HeaderBase'] = {'allOf': [{'$ref': '#/components/schemas/HeaderBase'}]}
        self.assertFalse(self.check(doc, 'id,1')['valid'])
        self.header(doc)['schema'] = {'allOf': [{'type': 'object'}] * 130}
        self.assertFalse(self.check(doc, 'id,1')['valid'])

    def test_real_http_runner_composed_object(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Object', 'id,2,active,true' if self.path.endswith('/1') else 'id,6,active,true')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('composed-object', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
