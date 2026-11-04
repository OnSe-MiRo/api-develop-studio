import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class UnionHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['Small'] = {'type': 'integer', 'maximum': 0}
        doc['components']['schemas']['Large'] = {'type': 'integer', 'minimum': 10}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Value': {'required': True, 'schema': schema}}
        return doc

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Value': raw}, {'id': 1})

    def union(self, keyword):
        return {keyword: [{'$ref': '#/components/schemas/Small'}, {'allOf': [{'$ref': '#/components/schemas/Large'}, {'maximum': 20}]}]}

    def test_versions_references_nested_allof_and_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            for keyword in ['oneOf', 'anyOf']:
                doc = self.spec(self.union(keyword), version)
                for raw in ['-1', '10', '20']:
                    self.assertTrue(self.check(doc, raw)['valid'])
                for raw in ['5', '21', 'PRIVATE']:
                    result = self.check(doc, raw)
                    self.assertIn('schema_' + keyword, [i['code'] for i in result['issues']])
                    self.assertNotIn('PRIVATE', json.dumps(result))

    def test_oneof_overlap_is_rejected_but_anyof_overlap_is_allowed(self):
        branches = [{'type': 'integer', 'minimum': 0}, {'type': 'integer', 'maximum': 10}]
        for version in ['3.0.3', '3.1.0']:
            self.assertFalse(self.check(self.spec({'oneOf': branches}, version), '5')['valid'])
            self.assertTrue(self.check(self.spec({'anyOf': branches}, version), '5')['valid'])
            for kind, raw in [('string', 'text'), ('number', '1.5'), ('boolean', 'true')]:
                self.assertTrue(self.check(self.spec({'anyOf': [{'type': kind}, {'type': kind}]}, version), raw)['valid'])

    def test_array_object_and_nullable_branches(self):
        for keyword in ['oneOf', 'anyOf']:
            for schema, good, bad in [
                ({'type': 'array', 'items': self.union(keyword)}, '-1,10', '-1,5'),
                ({'type': 'object', 'properties': {'id': self.union(keyword)}, 'required': ['id']}, 'id,10', 'id,5'),
                ({'type': 'object', 'additionalProperties': self.union(keyword)}, 'a,-1,b,10', 'a,5'),
            ]:
                self.assertTrue(self.check(self.spec(schema), good)['valid'])
                self.assertFalse(self.check(self.spec(schema), bad)['valid'])
        schema = {'anyOf': [{'type': ['integer', 'null'], 'minimum': 1}, {'type': 'integer', 'maximum': 0}]}
        self.assertTrue(self.check(self.spec(schema, '3.1.0'), '2')['valid'])
        self.assertFalse(self.check(self.spec(schema, '3.1.0'), 'null')['valid'])

    def test_mixed_untyped_cyclic_and_large_unions_are_not_decoded(self):
        for branches in [[{'type': 'integer'}, {'type': 'string'}], [{'type': 'integer'}, {}],
                         [{'type': 'integer'}, {'type': 'number'}], [{'type': 'integer'}] * 130]:
            doc = self.spec({'type': 'array', 'items': {'anyOf': branches}})
            result = self.check(doc, 'PRIVATE')
            self.assertIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        doc = self.spec({'type': 'array', 'items': {'$ref': '#/components/schemas/Small'}})
        doc['components']['schemas']['Small'] = {'anyOf': [{'type': 'integer'}, {'$ref': '#/components/schemas/Small'}]}
        self.assertFalse(self.check(doc, '1')['valid'])

    def test_real_http_runner_preserves_oneof_semantics(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Value', '10' if self.path.endswith('/1') else '5')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = self.spec(self.union('oneOf'))
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('union-header', case, contract_document=doc)
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
