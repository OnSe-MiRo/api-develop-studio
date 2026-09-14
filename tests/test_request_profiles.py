import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
import react_server as studio
from api_test.request_profiles import select_environment, profiles_for_client
from api_test.project_variables import decrypt_secret
from api_test.runner import ApiTestRunner, project_request_settings
from api_test.cli import run_case_files, run_pipeline


class RequestProfilesTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'API_TEST_ENCRYPTION_KEY': Fernet.generate_key().decode(), 'API_TEST_ENCRYPTION_URL': '', 'LOCAL_SERVER': 'true', 'SKIP_OWNERSHIP_VERIFICATION': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = studio.normalize_project_document({
            'name': 'sample', 'base_url': 'https://common.example',
            'variables': {'plain': {'name': 'common'}, 'secret': {'token': {'value': 'common-credential'}}},
            'auth_profiles': {'login': {'type': 'Bearer Token', 'token': '{{project.token}}'}},
            'environments': {name: {'base_url': f'https://{name}.example', 'variables': {'plain': {'name': name}, 'secret': {'token': {'value': f'{name}-credential'}}}} for name in ['local', 'dev', 'stage']},
        })
        (self.root / 'sample.json').write_text(json.dumps(self.project))

    def test_secret_storage_readback_and_preservation(self):
        self.assertNotIn('dev-credential', json.dumps(self.project))
        client = profiles_for_client(self.project)
        self.assertEqual(client['environments']['dev']['variables']['secret']['token'], {'configured': True})
        self.assertNotIn(self.project['variables']['secret']['token'], json.dumps(client))
        for env in client['environments'].values():
            env['variables']['secret']['token'] = {'preserve': True}
        client['variables']['secret']['token'] = {'preserve': True}
        updated = studio.normalize_project_document(client, self.project)
        self.assertEqual(updated, self.project)
        self.assertEqual(studio.normalize_project_document({'name': 'new', 'base_url': 'https://common.example'}, self.project)['environments'], self.project['environments'])

    def test_environment_precedence_and_legacy(self):
        legacy = {'base_url': 'https://legacy.example'}
        self.assertEqual(select_environment(legacy), legacy)
        for name in ['local', 'dev', 'stage']:
            settings = project_request_settings({'project': 'sample.json'}, self.root, name)
            self.assertEqual(settings.base_url, f'https://{name}.example')
            self.assertEqual(settings.variables['name'], name)
            self.assertEqual(decrypt_secret(settings.encrypted_variables['token']), f'{name}-credential')
        with self.assertRaises(ValueError):
            select_environment(self.project, 'unknown')

    def test_invalid_credentials_fail_closed(self):
        for value in ['plaintext', '{{project.name}}']:
            with self.assertRaises(studio.ApiError):
                studio.normalize_project_document({**self.project, 'variables': {}, 'auth_profiles': {'bad': {'type': 'Bearer Token', 'token': value}}, 'environments': {} })

    def test_quick_and_saved_request_use_same_auth_url_and_bytes(self):
        for mode in [{'body': {'hello': 'world'}}, {'text': '  hello\n'}, {'form_data': [{'key': 'hello', 'value': 'world'}]}]:
            request = {'url': '/{{project.name}}', 'method': 'POST', 'auth_profile': 'login', **mode}
            with patch.object(studio, 'PROJECT_ROOT', self.root), patch.object(studio, 'execute_http_call', return_value=(200, {}, '{}', 1)) as quick:
                studio.handle_api_request({'project': 'sample.json', 'environment': 'dev', **request})
            settings = project_request_settings({'project': 'sample.json'}, self.root, 'dev')
            with patch('api_test.runner.execute_http_call', return_value=(200, {}, '{}', 1)) as saved:
                result = ApiTestRunner().run_case('sample', {'request': request, 'expected': {'status': 200}}, base_url=settings.base_url, project_variables=settings.variables, encrypted_project_variables=settings.encrypted_variables, auth_profiles=settings.auth_profiles, file_root=self.root)
            self.assertEqual(result.status, 'passed')
            self.assertEqual(quick.call_args.args[0], saved.call_args.args[0])
            self.assertEqual(quick.call_args.kwargs['headers']['Authorization'], saved.call_args.kwargs['headers']['Authorization'])
            if 'form_data' not in mode:
                self.assertEqual(quick.call_args.kwargs['data'], saved.call_args.kwargs['data'])
            else:
                for call in [quick, saved]:
                    self.assertIn(b'name="hello"\r\n\r\nworld', call.call_args.kwargs['data'])

    def test_echoed_credentials_redacted_from_quick_response(self):
        with patch.object(studio, 'PROJECT_ROOT', self.root), patch.object(studio, 'execute_http_call', return_value=(200, {'Set-Cookie': 'dev-credential', 'X-Echo': 'dev-credential'}, '{"token":"dev-credential"}', 1)):
            response = studio.handle_api_request({'project': 'sample.json', 'environment': 'dev', 'url': '/echo', 'auth_profile': 'login'})
        self.assertNotIn('dev-credential', json.dumps(response))

    def test_case_and_pipeline_environment_and_logs(self):
        case = {'project': 'sample.json', 'request': {'url': '/echo', 'auth_profile': 'login'}, 'expected': {'status': 200}}
        (self.root / 'case.json').write_text(json.dumps(case))
        pipeline = self.root / 'pipeline.json'
        pipeline.write_text(json.dumps({'steps': [{'name': 'echo', 'case': 'case.json'}]}))
        with patch('api_test.runner.execute_http_call', return_value=(200, {}, '{"echo":"stage-credential"}', 1)) as call:
            self.assertEqual(run_case_files(['case.json'], self.root, 1, self.root / 'logs', self.root, environment='stage'), 0)
            self.assertEqual(run_pipeline(pipeline, self.root, 1, self.root / 'logs', self.root, environment='stage'), 0)
            self.assertEqual(call.call_count, 2)
            for args in call.call_args_list:
                self.assertEqual(args.args[0], 'https://stage.example/echo')
        for log in (self.root / 'logs').glob('*'):
            self.assertNotIn('stage-credential', log.read_text())

    def test_case_secret_override_wins_over_environment(self):
        from api_test.project_variables import encrypt_secret
        settings = project_request_settings({'project': 'sample.json'}, self.root, 'dev')
        case = {'request': {'url': '/echo', 'auth_profile': 'login'}, 'expected': {'status': 200},
                'variables': {'secret': {'token': encrypt_secret('case-credential')}}}
        with patch('api_test.runner.execute_http_call', return_value=(200, {}, '{}', 1)) as call:
            ApiTestRunner().run_case('sample', case, base_url=settings.base_url, project_variables=settings.variables,
                encrypted_project_variables=settings.encrypted_variables, auth_profiles=settings.auth_profiles)
        self.assertEqual(call.call_args.kwargs['headers']['Authorization'], 'Bearer case-credential')

    def test_all_first_phase_auth_profiles(self):
        import base64
        profiles = {'none': {'type': 'No Auth'}, 'basic': {'type': 'Basic Auth', 'username': 'user', 'password': '{{project.token}}'},
                    'header': {'type': 'API Key', 'key': 'X-Custom-Key', 'value': '{{project.token}}'},
                    'query': {'type': 'API Key', 'key': 'credential', 'value': '{{project.token}}', 'addTo': 'Query Params'}}
        self.project['auth_profiles'] = profiles
        (self.root / 'sample.json').write_text(json.dumps(self.project))
        for name in profiles:
            with patch.object(studio, 'PROJECT_ROOT', self.root), patch.object(studio, 'execute_http_call', return_value=(200, {}, '{}', 1)) as call:
                studio.handle_api_request({'project': 'sample.json', 'environment': 'dev', 'url': '/echo', 'auth_profile': name})
            headers = call.call_args.kwargs['headers']
            if name == 'basic':
                self.assertEqual(headers['Authorization'], 'Basic ' + base64.b64encode(b'user:dev-credential').decode())
            elif name == 'header':
                self.assertEqual(headers['X-Custom-Key'], 'dev-credential')
            elif name == 'query':
                self.assertIn('credential=dev-credential', call.call_args.args[0])
            else:
                self.assertNotIn('Authorization', headers)
