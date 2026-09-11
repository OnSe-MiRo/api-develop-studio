"""Exercise the checked-in example documents against the actual example handler."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from api_test.cli import run_pipeline
from api_test.ownership import OwnershipError
from react_server import StudioHandler

ROOT = Path(__file__).resolve().parents[1]


class ExampleOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.projects = self.root / 'projects'
        self.projects.mkdir()
        # Isolate existing user-edited project credentials and encryption keys.
        (self.projects / 'example-api.json').write_text(json.dumps({'base_url': 'http://127.0.0.1:8765'}))
        self.enterContext(patch.dict(os.environ, {
            'EXAMPLE_PROJECT': 'true', 'LOCAL_SERVER': 'true',
            'SKIP_OWNERSHIP_VERIFICATION': 'true',
            'STUDIO_OWNERSHIP_DB_PATH': str(self.root / 'ownership.db'),
        }))

    def run_example(self):
        with redirect_stdout(io.StringIO()):
            return run_pipeline(ROOT / 'pipelines/example-ownership-local.json', ROOT / 'case', 2, self.root / 'logs', self.projects)

    def test_local_pipeline_keeps_api_authentication(self):
        statuses = []
        def dispatch(url, method='GET', headers=None, **kwargs):
            handler = object.__new__(StudioHandler)
            handler.command = method
            handler.headers = headers or {}
            handler.api_path = Mock(return_value=urlsplit(url).path.strip('/').split('/'))
            handler.send_json = Mock()
            self.assertTrue(handler.serve_example_api())
            status, body = handler.send_json.call_args.args
            statuses.append(status)
            return status, {'Content-Type': 'application/json'}, json.dumps(body), 0
        with patch('api_test.runner.execute_http_call', side_effect=dispatch) as transport:
            self.assertEqual(self.run_example(), 0)
            self.assertEqual(transport.call_count, 3)
        self.assertEqual(statuses, [200, 401, 200])

    def test_disabling_bypass_blocks_before_first_request(self):
        with patch.dict(os.environ, {'SKIP_OWNERSHIP_VERIFICATION': 'false'}), patch('api_test.runner.execute_http_call') as transport:
            with self.assertRaises(OwnershipError):
                self.run_example()
            transport.assert_not_called()

    def test_example_pipeline_has_one_non_external_setup(self):
        pipeline = json.loads((ROOT / 'pipelines/example-ownership-local.json').read_text())
        self.assertEqual(pipeline['steps'][0]['phase'], 'setup')
        self.assertTrue(all(not step.get('external_once') for step in pipeline['steps']))
        for step in pipeline['steps']:
            case = json.loads((ROOT / 'case' / step['case']).read_text())
            self.assertEqual(case['project'], pipeline['project'])
