"""Contract generation and compatibility boundary tests."""
from pathlib import Path
import importlib
import unittest
import yaml
from pydantic import ValidationError
from fastapi.testclient import TestClient

from api_test.main import app, studio
from api_test.generated.main import routers
from api_test.generated.models.case_input import CaseInput
from api_test.generated.models.project_input import ProjectInput
from api_test.generated.models.project_view import ProjectView
from api_test.generated.models.quick_request import QuickRequest

ROOT = Path(__file__).resolve().parents[1]


class GeneratedServerTest(unittest.TestCase):
    def test_every_spec_operation_has_a_generated_route_and_implementation(self):
        spec = yaml.safe_load((ROOT / 'openapi/studio.yaml').read_text())
        routes = {route.operation_id: route for router in routers for route in router.routes if route.include_in_schema}
        expected_ids = set()
        for path, operations in spec['paths'].items():
            for method, operation in operations.items():
                operation_id = operation['operationId']
                expected_ids.add(operation_id)
                route = routes[operation_id]
                self.assertEqual(route.path, operation['x-studio-route'])
                self.assertIn(method.upper(), route.methods)
                self.assertTrue(route.endpoint.__module__.startswith('api_test.generated.apis.'))
                module, function = operation['x-studio-handler'].split('.')
                self.assertTrue(callable(getattr(importlib.import_module('api_test.implementations.' + module), function)))
        self.assertEqual(set(routes), expected_ids)

    def test_published_schema_has_named_inputs_and_no_internal_binding_details(self):
        with TestClient(app) as client:
            result = client.get('/api/schema.json')
        self.assertEqual(result.status_code, 200)
        spec = result.json()
        self.assertEqual(spec['paths']['/api/projects/{reference}']['put']['requestBody']['content']['application/json']['schema'], {'$ref': '#/components/schemas/ProjectInput'})
        self.assertNotIn('x-studio-handler', result.text)
        self.assertIn('environments', spec['components']['schemas']['ProjectInput']['properties'])
        self.assertIn('configured', spec['components']['schemas']['SecretState']['properties'])

    def test_generated_models_preserve_nested_json_null_and_extension_fields(self):
        for payload in [None, False, 0, '', [None, {'score': 9.0}], {'value': None}]:
            document = {'request': {'url': '/echo', 'body': payload}, 'expected': {'body': payload}, 'custom_extension': {'enabled': False}}
            self.assertEqual(CaseInput.from_dict(document).to_dict(), document)
        body = {'url': '/echo', 'body': [None, False], 'params': [{'key': 'x', 'value': '1'}, {'key': 'x', 'value': '2'}]}
        self.assertEqual(QuickRequest.from_dict(body).to_dict(), body)

    def test_models_distinguish_secret_write_and_read_contracts(self):
        document = {'name': 'sample', 'base_url': 'https://example.test', '_storage': {'id': 'document-uuid', 'revision': 1},
                    'environments': {'dev': {'base_url': 'https://dev.example.test', 'variables': {'secret': {'token': {'preserve': True}}}}}}
        self.assertEqual(ProjectInput.from_dict(document).to_dict(), document)
        document['environments']['dev']['variables']['secret']['token'] = {'configured': True}
        self.assertEqual(ProjectView.from_dict(document).to_dict(), document)
        with self.assertRaises(ValidationError):
            ProjectInput.from_dict({'name': 'missing URL'})

    def test_legacy_import_is_the_same_service_context(self):
        import react_server
        self.assertIs(react_server, studio)
        self.assertIs(react_server.app, app)
