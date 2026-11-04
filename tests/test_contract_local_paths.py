import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api_test.contracts import ContractError, lint, validate_response
from api_test.contracts.documents import local_path, bundle_document, load_file
from test_contracts import document


class LocalReferencePathTests(unittest.TestCase):
    def test_valid_paths_decode_once_and_stay_relative(self):
        for ref, expected in [
            ('../schemas/%ED%95%9C%EA%B8%80%20file.yaml', 'schemas/한글 file.yaml'),
            ('../schemas/100%25done.yaml', 'schemas/100%done.yaml'),
            ('../schemas/%252e%252e/item.yaml', 'schemas/%2e%2e/item.yaml'),
            ('./nested/../item.json#/properties/a~1b', 'api/item.json'),
            ('#', 'api/openapi.yaml'), ('', 'api/openapi.yaml'),
        ]:
            self.assertEqual(local_path('api/openapi.yaml', ref)[0], expected)
        self.assertEqual(local_path('openapi.yaml', '%20name.yaml')[0], ' name.yaml')

    def test_bad_encoding_controls_backslashes_and_drives_rejected(self):
        for ref in ['PRIVATE%.yaml', 'PRIVATE%G0.yaml', 'PRIVATE%0G.yaml', 'PRIVATE%FF.yaml',
                    'PRIVATE%00.yaml', 'PRIVATE%0a.yaml', 'PRIVATE%7f.yaml', 'PRIVATE\n.yaml',
                    'PRIVATE%5cb.yaml', 'PRIVATE\\b.yaml', 'C%3a/PRIVATE.yaml',
                    'nested/C%3aPRIVATE.yaml', ' PRIVATE.yaml', 'http://[PRIVATE']:
            with self.subTest(ref=ref), self.assertRaises(ContractError) as error:
                local_path('openapi.yaml', ref)
            self.assertNotIn('PRIVATE', str(error.exception))
        for parent in ['C:/PRIVATE.yaml', 'a\\PRIVATE.yaml', 'a\x00.yaml']:
            with self.assertRaises(ContractError): local_path(parent, '#')

    def test_root_and_external_boundaries_remain(self):
        for ref in ['%2e%2e/PRIVATE.yaml', '%2fPRIVATE.yaml', '//server/PRIVATE.yaml',
                    'https://example.test/PRIVATE.yaml', 'file:///PRIVATE.yaml', 'item.yaml?PRIVATE=1']:
            with self.assertRaises(ContractError): local_path('openapi.yaml', ref)
        self.assertEqual(local_path('api/openapi.yaml', '../schemas/item.yaml')[0], 'schemas/item.yaml')

    def test_bundle_and_file_loader_keep_unicode_space_and_percent(self):
        for version in ['3.0.3', '3.1.0']:
            doc = document(version)
            doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = {
                '$ref': 'schemas/%ED%95%9C%EA%B8%80%20100%25.yaml'}
            files = {'openapi.json': json.dumps(doc), 'schemas/한글 100%.yaml': json.dumps({'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}})}
            bundle = bundle_document({'entrypoint': 'openapi.json', 'files': files})
            self.assertEqual(lint(bundle), [])
            self.assertTrue(validate_response(bundle, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, {'id': 1})['valid'])
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/'schemas').mkdir()
                for name, text in files.items(): (root/name).write_text(text, encoding='utf-8')
                self.assertEqual(load_file(root/'openapi.json'), bundle)

    def test_bad_references_stop_before_referenced_file_read(self):
        for ref in ['bad%FF.yaml', 'bad%5cfile.yaml', 'C%3aPRIVATE.yaml', '%2e%2e/PRIVATE.yaml']:
            doc = document()
            doc['paths']['/items/{id}']['get']['responses']['200']['content']['application/json']['schema'] = {'$ref': ref}
            with self.assertRaises(ContractError):
                bundle_document({'entrypoint': 'openapi.json', 'files': {'openapi.json': json.dumps(doc)}})
            with tempfile.TemporaryDirectory() as directory:
                entry = Path(directory)/'openapi.json'; entry.write_text(json.dumps(doc))
                read_text = Path.read_text
                seen = []
                def read(path, *args, **kwargs):
                    seen.append(path)
                    return read_text(path, *args, **kwargs)
                with patch.object(Path, 'read_text', read), self.assertRaises(ContractError): load_file(entry)
                self.assertEqual(seen, [entry.resolve()])
