import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from api_test.cli import _result_lines
from api_test.runner import ApiTestRunner, CaseConfigurationError


class CaseCallResultsTest(unittest.TestCase):
    def case(self):
        return {'request': {'url': '/items', 'method': 'POST', 'body': {'name': 'Ada'},
                            'auth': {'type': 'Bearer Token', 'token': 'private-token'}},
                'expected': {'status': 200, 'body': {}, 'max_response_time_ms': 0.001,
                             'assertions': [{'operator': 'invalid'}],
                             'validation_modes': {'call_only': True, 'exact_body': True, 'conditions': True}},
                'contract_validation': {'enabled': True}}

    def test_call_only_skips_every_validation_and_keeps_request_and_response(self):
        with patch('api_test.runner.execute_http_call', return_value=(503, {'Retry-After': '5', 'Set-Cookie': 'private-cookie'}, 'unavailable', 0)) as transport:
            result = ApiTestRunner().run_case('items', self.case(), base_url='https://example.test')
        self.assertEqual(result.status, 'passed')
        self.assertEqual(result.differences, [])
        self.assertIsNone(result.contract)
        self.assertEqual(result.response.status, 503)
        details = json.loads(next(line.split('=', 1)[1] for line in _result_lines(result) if line.startswith('  call_details=')))
        self.assertEqual(details['request']['url'], 'https://example.test/items')
        self.assertEqual(details['request']['body'], {'name': 'Ada'})
        self.assertEqual(details['request']['headers']['Content-Type'], 'application/json')
        self.assertEqual(details['request']['headers']['Authorization'], '***REDACTED***')
        self.assertEqual(details['response']['headers']['Set-Cookie'], '***REDACTED***')
        self.assertEqual(details['response']['body'], 'unavailable')
        self.assertEqual(details['mode'], 'call_only')
        self.assertIsInstance(details['elapsedMs'], float)
        self.assertEqual(transport.call_args.kwargs['headers']['Authorization'], 'Bearer private-token')

    def test_timeout_stays_error_with_request_details_and_secret_redaction(self):
        with patch('api_test.runner.execute_http_call', side_effect=TimeoutError('private-token timed out')):
            result = ApiTestRunner().run_case('items', self.case(), base_url='https://example.test')
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.error_category, 'request_timeout')
        output = '\n'.join(_result_lines(result))
        self.assertIn('call_details=', output)
        self.assertNotIn('private-token', output)
        self.assertIn('"response": null', output)

    def test_invalid_mode_rejected_before_request_and_legacy_status_still_validated(self):
        case = self.case()
        case['expected']['validation_modes']['call_only'] = 'true'
        with patch('api_test.runner.execute_http_call') as transport:
            with self.assertRaises(CaseConfigurationError):
                ApiTestRunner().run_case('bad', case)
            transport.assert_not_called()
        with patch('api_test.runner.execute_http_call', return_value=(404, {}, '{}', 0)):
            result = ApiTestRunner().run_case('legacy', {'request': {'url': 'https://example.test'}, 'expected': {'status': 200}})
        self.assertEqual(result.status, 'failed')

    def test_multipart_snapshot_contains_metadata_not_file_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'upload.txt').write_text('PRIVATE FILE CONTENT')
            case = {'request': {'url': 'https://example.test', 'form_data': [{'key': 'file', 'file': 'upload.txt'}]},
                    'expected': {'validation_modes': {'call_only': True}}}
            with patch('api_test.runner.execute_http_call', return_value=(204, {}, '', 0)):
                result = ApiTestRunner().run_case('upload', case, file_root=Path(directory))
        self.assertIn('multipart/form-data', result.request_snapshot['headers']['Content-Type'])
        self.assertNotIn('PRIVATE FILE CONTENT', '\n'.join(_result_lines(result)))

    def test_direct_credentials_and_echoed_values_are_redacted(self):
        case = {'request': {'url': 'https://example.test?api_key=query-private',
                            'headers': {'Authorization': 'Bearer header-private', 'Cookie': 'session=cookie-private'}},
                'expected': {'validation_modes': {'call_only': True}}}
        with patch('api_test.runner.execute_http_call', return_value=(200, {},
                   '{"echo":"header-private query-private session=cookie-private"}', 0)):
            result = ApiTestRunner().run_case('echo', case)
        output = '\n'.join(_result_lines(result))
        for private in ('header-private', 'query-private', 'cookie-private'):
            self.assertNotIn(private, output)
