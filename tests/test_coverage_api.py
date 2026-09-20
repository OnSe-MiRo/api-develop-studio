from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from api_test.collaboration_store import CollaborationStore
from api_test.execution_history import ExecutionHistory
from api_test.services.studio import openapi_document_operations
from api_test.test_coverage import source_for
from http_client import HttpRequest
from test_test_lifecycle import spec

class CoverageApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = CollaborationStore(root / 'db', {kind: root / kind for kind in ('projects', 'cases', 'pipelines')})
        self.store.initialize()
        self.history = ExecutionHistory(root / 'history.db')
        self.project = {'name': 'Coverage', 'base_url': 'https://example.test', 'docs_file': {'document': spec()}}
        self.store.save('projects', 'p.json', self.project)
        self.case = {'project': 'p.json', 'request': {'method': 'GET', 'url': '/items', 'headers': {'Authorization': 'never-return-me'}}, 'expected': {'status': 200, 'assertions': []}, 'spec_source': source_for(openapi_document_operations(spec())[0], spec())}
        self.store.save('cases', 'tag/api/case.json', self.case)
        self.request = HttpRequest(); self.request.path = '/api/projects/p.json/openapi/coverage'
        self.addCleanup(patch.stopall)
        patch('react_server.collaboration_store', return_value=self.store).start()
        patch('react_server.execution_history', return_value=self.history).start()

    def post(self, payload):
        self.request.payload = payload
        return self.request.send('POST')

    def test_coverage_sync_revision_conflicts_and_secret_preservation(self):
        response = self.post({})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['operations'][0]['responses'][0]['cases'], ['tag/api/case.json'])
        self.assertNotIn('never-return-me', response.text)
        changed = deepcopy(self.project); changed['docs_file']['document'] = spec('/new', '201')
        self.store.save('projects', 'p.json', changed, expected_revision=1)
        response = self.post({'case': 'tag/api/case.json'})
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json(); self.assertTrue(preview['changed'])
        self.assertNotIn('never-return-me', response.text)
        body = {'case': 'tag/api/case.json', 'apply': True, 'fields': ['request.url'], 'projectRevision': 2, 'caseRevision': 1}
        self.assertEqual(self.post({**body, 'projectRevision': 1}).status_code, 409)
        self.assertEqual(self.post({**body, 'fields': ['request.headers']}).status_code, 400)
        self.assertEqual(self.post(body).status_code, 200)
        saved = self.store.get('cases', 'tag/api/case.json').document
        self.assertEqual(saved['request']['url'], '/new')
        self.assertEqual(saved['expected'], self.case['expected'])
        self.assertEqual(saved['request']['headers'], self.case['request']['headers'])
        self.assertEqual(self.post(body).status_code, 409)

    def test_case_project_boundary(self):
        self.store.save('cases', 'tag/api/other.json', {**self.case, 'project': 'other.json'})
        self.assertEqual(self.post({'case': 'tag/api/other.json'}).status_code, 404)
