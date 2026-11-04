import json
import unittest
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class UnionHeaderObjectTests(unittest.TestCase):
    def spec(self, keyword='oneOf', version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['A'] = {'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['a']}, 'id': {'type': 'integer', 'enum': [1]}}, 'required': ['kind', 'id'], 'additionalProperties': False}
        doc['components']['schemas']['B'] = {'allOf': [{'type': 'object', 'properties': {'kind': {'type': 'string', 'enum': ['b']}, 'id': {'type': 'integer', 'enum': [10]}}, 'required': ['kind', 'id'], 'additionalProperties': False}, {'maxProperties': 2}]}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Object': {'required': True, 'schema': {keyword: [{'$ref': '#/components/schemas/A'}, {'$ref': '#/components/schemas/B'}]}}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Object']

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Object': raw}, {'id': 1})

    def test_versions_refs_allof_and_whole_object_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            for keyword in ['oneOf', 'anyOf']:
                doc = self.spec(keyword, version)
                for raw in ['kind,a,id,1', 'kind,b,id,10']:
                    self.assertTrue(self.check(doc, raw)['valid'])
                for raw in ['kind,a,id,10', 'kind,a', 'kind,a,id,1,extra,x', 'kind,a,id,PRIVATE']:
                    result = self.check(doc, raw)
                    self.assertIn('schema_' + keyword, [i['code'] for i in result['issues']])
                    self.assertNotIn('PRIVATE', json.dumps(result))
                self.header(doc)['explode'] = True
                self.assertTrue(self.check(doc, 'kind=a,id=1')['valid'])

    def test_overlap_and_closed_branch_semantics(self):
        for keyword, expected in [('oneOf', False), ('anyOf', True)]:
            doc = self.spec(keyword)
            doc['components']['schemas']['B'] = deepcopy(doc['components']['schemas']['A'])
            self.assertEqual(self.check(doc, 'kind,a,id,1')['valid'], expected)
            doc['components']['schemas']['B']['additionalProperties'] = True
            self.assertTrue(self.check(doc, 'kind,a,id,1,extra,text')['valid'])

    def test_nested_union_and_nullable_property(self):
        doc = self.spec('anyOf', '3.1.0')
        doc['components']['schemas']['A']['properties']['id']['type'] = ['integer', 'null']
        self.header(doc)['schema'] = {'anyOf': [self.header(doc)['schema']]}
        self.assertTrue(self.check(doc, 'kind,a,id,1')['valid'])
        self.assertFalse(self.check(doc, 'kind,a,id,null')['valid'])

    def test_different_shapes_and_limits_are_not_decoded(self):
        for change in ['type', 'field', 'additional']:
            doc = self.spec()
            other = deepcopy(doc['components']['schemas']['A'])
            if change == 'type': other['properties']['id']['type'] = 'string'
            if change == 'field': other['properties']['extra'] = {'type': 'string'}
            if change == 'additional': other['additionalProperties'] = {'type': 'integer'}
            doc['components']['schemas']['B'] = other
            self.assertFalse(self.check(doc, 'kind,a,id,1')['valid'])
        doc = self.spec()
        self.header(doc)['schema'] = {'oneOf': [{'$ref': '#/components/schemas/A'}] * 130}
        self.assertFalse(self.check(doc, 'kind,a,id,1')['valid'])
        doc['components']['schemas']['Loop'] = {'anyOf': [{'$ref': '#/components/schemas/A'}, {'$ref': '#/components/schemas/Loop'}]}
        self.header(doc)['schema'] = {'anyOf': [{'$ref': '#/components/schemas/Loop'}]}
        self.assertFalse(self.check(doc, 'kind,a,id,1')['valid'])

    def test_real_http_runner_union_object(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Object', 'kind,a,id,1' if self.path.endswith('/1') else 'kind,a,id,10')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('union-object', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
