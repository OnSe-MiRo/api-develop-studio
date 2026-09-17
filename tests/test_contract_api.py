from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from api_test.collaboration_store import CollaborationStore, DocumentNotFoundError
from api_test.database import RequestContext
from http_client import HttpRequest
from api_test.services import studio
from test_contracts import document


class ContractApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.store = CollaborationStore(root / 'studio.db', {kind: root / kind for kind in ('projects', 'cases', 'pipelines')})
        self.store.initialize()
        project = {'name': 'Contract', 'base_url': 'https://example.test', 'docs_file': {'document': document()}}
        self.store.save('projects', 'contract.json', project)
        changed = deepcopy(project)
        changed['docs_file']['document']['paths'].clear()
        self.store.save('projects', 'contract.json', changed, expected_revision=1)

    def test_revision_comparison_and_missing_revision(self):
        request = HttpRequest()
        request.path = '/api/projects/contract.json/openapi/contract'
        with patch('react_server.collaboration_store', return_value=self.store):
            request.payload = {'baselineRevision': 1}
            request.send('POST')
            self.assertEqual(request.response.status_code, 200, request.response.text)
            result = request.response.json()
            self.assertEqual(result['currentRevision'], 2)
            self.assertFalse(result['compatible'])
            self.assertEqual(result['changes'][0]['code'], 'operation_removed')
            request.payload = {'baselineRevision': 99}
            request.send('POST')
            self.assertEqual(request.response.status_code, 404)
            request.payload = {'baselineRevision': True}
            request.send('POST')
            self.assertEqual(request.response.status_code, 400)

    def test_revision_workspace_boundary(self):
        other = CollaborationStore(self.store.database_path, self.store.roots, context=RequestContext(workspace_id='other', user_id='other'))
        with self.assertRaises(DocumentNotFoundError):
            other.revision_document('projects', 'contract.json', 1)

    def test_actual_quick_response_is_validated_before_masking(self):
        saved = Mock(document={'docs_file': {'document': document()}})
        store = Mock(); store.get.return_value = saved
        settings = Mock(auth_profiles={}, variables={}, encrypted_variables={}, base_url='https://example.test')
        with patch.object(studio, 'collaboration_store', return_value=store), \
             patch.object(studio, 'project_request_settings', return_value=settings), \
             patch.object(studio, 'local_policy', return_value={'skip_verification': True}), \
             patch.object(studio, 'execute_http_call', return_value=(200, {'Content-Type': 'application/json', 'X-Count': '1'}, '{"id":"secret-value"}', 1)):
            result = studio.handle_api_request({'project': 'contract.json', 'url': '/items/1', 'validateContract': True})
        self.assertFalse(result['contract']['valid'])
        self.assertIn('schema_type', [item['code'] for item in result['contract']['issues']])
        self.assertNotIn('secret-value', json.dumps(result['contract']))

    def test_invalid_contract_prevents_outbound_call(self):
        saved = Mock(document={'docs_file': {'document': {'openapi': '3.0.3', 'paths': {}}}})
        store = Mock(); store.get.return_value = saved
        settings = Mock(auth_profiles={}, variables={}, encrypted_variables={}, base_url='https://example.test')
        with patch.object(studio, 'collaboration_store', return_value=store), patch.object(studio, 'project_request_settings', return_value=settings), patch.object(studio, 'execute_http_call') as send:
            with self.assertRaises(studio.ApiError):
                studio.handle_api_request({'project': 'contract.json', 'url': '/items/1', 'validateContract': True})
        send.assert_not_called()
