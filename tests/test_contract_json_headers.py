import json
import unittest
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import Mock, patch
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from api_test.reports import RunReport, now
from api_test.services import studio
from test_contracts import document


class JsonHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.0.3', media='application/json'):
        doc = document(version)
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {
            'X-Metadata': {'required': True, 'content': {media: {'schema': schema}}}}
        return doc

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200,
                                 {'Content-Type': 'application/json', 'x-metadata': value}, {'id': 1})

    def test_versions_media_types_values_and_refs(self):
        for version in ['3.0.3', '3.1.0']:
            for media in ['application/json', 'application/vnd.studio+json', 'Application/JSON; charset=utf-8']:
                for schema, value in [
                    ({'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}}, {'id': 2}),
                    ({'type': 'array', 'items': {'type': 'array', 'items': {'type': 'integer'}}}, [[1, 2]]),
                    ({'type': 'string'}, 'a,b'), ({'type': 'boolean'}, False), ({'type': 'number'}, 2.5),
                ]:
                    with self.subTest(version=version, media=media, schema=schema):
                        doc = self.spec(schema, version, media)
                        doc['components']['schemas']['Metadata'] = schema
                        header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata']
                        header['content'][media]['schema'] = {'$ref': '#/components/schemas/Metadata'}
                        doc['components']['headers'] = {'Metadata': deepcopy(header)}
                        doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata'] = {'$ref': '#/components/headers/Metadata'}
                        result = self.check(doc, json.dumps(value))
                        self.assertTrue(result['valid'], result)

    def test_invalid_json_is_value_free_and_never_passes(self):
        for version in ['3.0.3', '3.1.0']:
            doc = self.spec({}, version)
            for value in ['', 'PRIVATE', '{"id":', '1,2', '{"id":1,"id":2}', 'NaN', 'Infinity', '1e400', '[1,NaN]', '{"nested":{"x":1,"x":2}}']:
                with self.subTest(version=version, value=value):
                    result = self.check(doc, value)
                    self.assertEqual([i['code'] for i in result['issues']], ['invalid_header_json'])
                    self.assertEqual(result['issues'][0]['path'], '#/response/headers/X-Metadata')
                    self.assertNotIn('PRIVATE', json.dumps(result))

    def test_schema_constraints_missing_optional_and_null(self):
        for version in ['3.0.3', '3.1.0']:
            for schema, value, code in [
                ({'type': 'integer'}, '"PRIVATE"', 'schema_type'),
                ({'type': 'object', 'required': ['id']}, '{}', 'schema_required'),
                ({'type': 'array', 'items': {'type': 'integer'}, 'uniqueItems': True}, '[1,1]', 'schema_uniqueItems'),
                ({'type': 'string', 'format': 'uuid'}, '"PRIVATE"', 'schema_format'),
                ({'type': 'string', 'enum': ['allowed']}, '"PRIVATE"', 'schema_enum'),
            ]:
                result = self.check(self.spec(schema, version), value)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))
            nullable = {'type': 'string', 'nullable': True} if version.startswith('3.0') else {'type': ['string', 'null']}
            self.assertTrue(self.check(self.spec(nullable, version), 'null')['valid'])
            doc = self.spec({}, version)
            self.assertIn('missing_header', [i['code'] for i in validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})['issues']])
            doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata']['required'] = False
            self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})['valid'])

    def test_unsupported_media_and_schema_free_json(self):
        for media in ['text/html', 'application/xml', 'application/*+json', '*/*', 'text/custom+json']:
            result = self.check(self.spec({}, media=media), 'PRIVATE')
            self.assertIn('unsupported_header_content', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        doc = self.spec({})
        del doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata']['content']['application/json']['schema']
        self.assertTrue(self.check(doc, '{"id":1}')['valid'])
        self.assertFalse(self.check(doc, 'PRIVATE')['valid'])
        # Invalid dual schema/content declarations must fail lint, not choose a decoder.
        doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Metadata']['schema'] = {'type': 'string'}
        self.assertFalse(self.check(doc, '"text"')['valid'])

    def test_quick_call_uses_json_header_contract(self):
        doc = self.spec({'type': 'integer'})
        store = Mock(); store.get.return_value = Mock(document={'docs_file': {'document': doc}})
        settings = Mock(auth_profiles={}, variables={}, encrypted_variables={}, base_url='https://example.test')
        with patch.object(studio, 'collaboration_store', return_value=store), patch.object(studio, 'project_request_settings', return_value=settings), patch.object(studio, 'local_policy', return_value={'skip_verification': True}), patch.object(studio, 'execute_http_call', return_value=(200, {'Content-Type': 'application/json', 'X-Metadata': '"PRIVATE"'}, '{"id":1}', 1)):
            result = studio.handle_api_request({'project': 'demo.json', 'url': '/items/1', 'validateContract': True})
        self.assertFalse(result['contract']['valid'])
        self.assertNotIn('PRIVATE', json.dumps(result['contract']))

    def test_real_http_runner_reports_pass_and_safe_contract_failure(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Metadata', '{"id":2}' if self.path.endswith('/1') else '{"id":"PRIVATE"}')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = self.spec({'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}})
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('json-header', case, contract_document=doc)
            self.assertEqual(result.status, expected)
            report = RunReport(); report.add(result, 'tag/api/header.json', now(), case_reference='tag/api/header.json'); report.finish(0 if expected == 'passed' else 1)
            self.assertNotIn('PRIVATE', json.dumps(report.data))
            if expected == 'failed':
                self.assertEqual(report.data['targets'][0]['errorCategory'], 'contract_failed')
