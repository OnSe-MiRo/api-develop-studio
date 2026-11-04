import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api_test.contracts import lint, validate_response, ContractError
from api_test.contracts.documents import pointer, resolve, bundle_document, load_file, local_path
from api_test.runner import ApiTestRunner, CaseConfigurationError
from test_contracts import document


class JsonPointerTests(unittest.TestCase):
    def test_root_empty_key_escapes_and_utf8(self):
        doc = {'': 'empty', 'a/b': 1, 'm~n': 2, '~1': 3, '한글': 4, 'a%2Fb': 5, 'list': [10, 20]}
        self.assertIs(pointer(doc, '#'), doc)
        for ref, expected in [('#/', 'empty'), ('#/a~1b', 1), ('#/m~0n', 2), ('#/~01', 3),
                              ('#/%ED%95%9C%EA%B8%80', 4), ('#/a%252Fb', 5), ('#%2Flist%2F0', 10)]:
            self.assertEqual(pointer(doc, ref), expected)
        self.assertEqual(pointer({'01': 1, '-1': 2, '١': 3}, '#/01'), 1)
        self.assertEqual(pointer({'-1': 2}, '#/-1'), 2)

    def test_noncanonical_array_indices_and_scalar_traversal_rejected(self):
        for token in ['-1', '+1', '01', '00', ' 1', '1 ', '١', '-', '2', '1.0', '1e0']:
            with self.subTest(token=token), self.assertRaises(ContractError):
                pointer({'values': ['a', 'b']}, '#/values/' + token)
        with self.assertRaises(ContractError): pointer({'value': 'abc'}, '#/value/0')

    def test_invalid_fragments_do_not_echo_values(self):
        for ref in ['https://example.test/PRIVATE', 'file:///PRIVATE', '#PRIVATE', '#/PRIVATE~2', '#/PRIVATE~', '#/PRIVATE%', '#/PRIVATE%GG', '#/%FF']:
            with self.assertRaises(ContractError) as error: pointer({}, ref)
            self.assertNotIn('PRIVATE', str(error.exception))
        with self.assertRaises(ContractError): resolve({'$ref': '#'}, {'$ref': '#'})

    def test_bundle_percent_filename_and_fragment_decode_once(self):
        doc = document()
        response = doc['paths']['/items/{id}']['get']['responses']['200']
        response['content']['application/json']['schema'] = {'$ref': 'schemas/100%25done.yaml#/properties/a%252Fb'}
        files = {'openapi.json': json.dumps(doc), 'schemas/100%done.yaml': json.dumps({'properties': {'a%2Fb': {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}}}})}
        target, fragment = local_path('openapi.json', 'schemas/100%25done.yaml#/properties/a%252Fb')
        self.assertEqual(fragment, '/properties/a%252Fb')
        from api_test.openapi_editor import _get
        self.assertEqual(_get(json.loads(files[target]), '#' + fragment)['type'], 'object')
        bundle = bundle_document({'entrypoint': 'openapi.json', 'files': files})
        self.assertEqual(lint(bundle), [])
        self.assertTrue(validate_response(bundle, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, {'id': 1})['valid'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'schemas').mkdir()
            for name, text in files.items(): (root/name).write_text(text)
            self.assertEqual(load_file(root/'openapi.json'), bundle)

    def test_bundle_root_reference_and_encoded_pointer_separator(self):
        doc = document()
        doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = {'$ref': 'item.json#'}
        item = {'type': 'object', 'properties': {'id': {'type': 'integer'}, 'next': {'$ref': '#'}}}
        bundle = bundle_document({'entrypoint': 'openapi.json', 'files': {'openapi.json': json.dumps(doc), 'item.json': json.dumps(item)}})
        self.assertEqual(lint(bundle), [])
        self.assertTrue(validate_response(bundle, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, {'id': 1, 'next': {'id': 2}})['valid'])
        doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = {'$ref': 'item.json#%2Fproperties%2Fid'}
        bundle = bundle_document({'entrypoint': 'openapi.json', 'files': {'openapi.json': json.dumps(doc), 'item.json': json.dumps(item)}})
        self.assertTrue(validate_response(bundle, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, 1)['valid'])

    def test_invalid_reference_blocks_runner_before_http(self):
        for version in ['3.0.3', '3.1.0']:
            for index in ['-1', '01', '+1']:
                doc = document(version)
                doc['x-schemas'] = [{'type': 'object'}, {'type': 'object'}]
                doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = {'$ref': '#/x-schemas/' + index}
                self.assertIn('unresolved_or_external_ref', [i['code'] for i in lint(doc)])
                case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': 'http://127.0.0.1:12345/items/1'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
                with patch('api_test.runner.execute_http_call') as send:
                    with self.assertRaises(CaseConfigurationError): ApiTestRunner().run_case('pointer', case, contract_document=doc)
                    send.assert_not_called()
