from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from api_test import openapi_editing
from api_test.services import studio
from http_client import HttpRequest


class OperationEditingTest(unittest.TestCase):
    def setUp(self):
        self.document = {'openapi': '3.0.3', 'info': {'title': 'Test', 'version': '1'}, 'paths': {
            '/items': {'parameters': [{'name': 'q', 'in': 'query', 'schema': {'type': 'string'}}],
                       'get': {'operationId': 'listItems', 'responses': {'200': {'description': 'OK'}}, 'x-custom': {'keep': True}},
                       'post': {'operationId': 'createItem', 'responses': {'201': {'description': 'Created'}}}},
        }, 'components': {'schemas': {'Node': {'type': 'object', 'properties': {'next': {'$ref': '#/components/schemas/Node'}}}}}}
        self.project = {'name': 'Test', 'base_url': 'https://example.test', 'docs_bundle': studio.split_openapi_bundle(self.document)}

    def edit(self, **kwargs):
        return openapi_editing.edit_operation(self.project, {'action': 'update', 'method': 'GET', 'path': '/items', 'changes': {'summary': 'Changed'}, **kwargs}, studio)

    def test_bundle_preserves_refs_and_untouched_files(self):
        original = deepcopy(self.project)
        updated, operation = self.edit()
        self.assertEqual(self.project, original)
        self.assertEqual(operation['x-custom'], {'keep': True})
        changed = [name for name, content in original['docs_bundle']['files'].items() if content != updated['docs_bundle']['files'][name]]
        self.assertEqual(len(changed), 1)
        self.assertTrue(changed[0].startswith('paths/'))
        self.assertEqual(studio.project_openapi_document(updated)['paths']['/items']['get']['summary'], 'Changed')

    def test_delete_preserves_sibling_and_path_parameters(self):
        updated, operation = self.edit(action='delete')
        item = studio.project_openapi_document(updated)['paths']['/items']
        self.assertNotIn('get', item)
        self.assertIn('post', item)
        self.assertIn('parameters', item)
        self.assertEqual(operation, {})

    def test_validation_rejects_bad_patches(self):
        for changes in ({'operationId': 'createItem'}, {'operationId': ''}, {'deprecated': 'false'}, {'tags': 'tag'}, {'responses': {}}, {}):
            with self.subTest(changes=changes), self.assertRaises(studio.ApiError):
                self.edit(changes=changes)
        with self.assertRaises(studio.ApiError):
            self.edit(path='/missing')

    def test_inline_document_preserves_recursive_reference(self):
        self.project = {'docs_file': {'document': self.document}}
        updated, _ = self.edit()
        self.assertEqual(updated['docs_file']['document']['components'], self.document['components'])

    def test_endpoint_revision_and_inspection_metadata(self):
        request = HttpRequest()
        request.path = '/api/projects/edit.json/openapi/operations'
        request.payload = {'action': 'update', 'method': 'GET', 'path': '/items', 'changes': {'description': 'New description'}, '_storage': {'revision': 4}}
        store = Mock()
        store.get.return_value = Mock(document=self.project)
        store.save.return_value.metadata.return_value = {'revision': 5}
        with patch('react_server.collaboration_store', return_value=store):
            request.send('POST')
        self.assertEqual(request.response.status_code, 200, request.response.text)
        self.assertEqual(store.save.call_args.kwargs['expected_revision'], 4)
        self.assertEqual(store.save.call_args.kwargs['action'], 'update_openapi_operation')
        request.path = '/api/docs'
        request.payload = {'bundle': store.save.call_args.args[2]['docs_bundle']}
        request.send('POST')
        self.assertEqual(request.response.json()['operations'][0]['editable']['description'], 'New description')

    def test_example_rejects_delete_before_write(self):
        request = HttpRequest()
        request.path = '/api/projects/example-api.json/openapi/operations'
        request.payload = {'action': 'delete', 'method': 'GET', 'path': '/items', '_storage': {'revision': 1}}
        with patch('react_server.collaboration_store') as store:
            request.send('POST')
        self.assertNotEqual(request.response.status_code, 200)
        store.assert_not_called()
