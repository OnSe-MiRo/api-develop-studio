import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from api_test import cli
from api_test.reports import RunReport, now
from api_test.runner import ApiTestRunner, AssertionResult, CaseResult, HttpResponse
from api_test.services import studio


class ReportTests(unittest.TestCase):
    def test_cli_json_junit_verdicts_and_secret_exclusion(self):
        for status, error in [('passed', None), ('failed', None), ('error', 'token=PRIVATE'), ('error', 'timed out PRIVATE')]:
            with self.subTest(status=status, error=error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'case.json').write_text('{"request": {"url": "https://example.test"}}')
                result = CaseResult('case_1_case', status, 2, response=HttpResponse(500, {'Authorization': 'PRIVATE'}, {'secret': 'PRIVATE'}),
                                    error=error, assertion_results=[AssertionResult('PRIVATE', 'eq', status == 'passed', {'value': 'PRIVATE'}, 'PRIVATE', 'PRIVATE')])
                args = ['runner', '--case-root', directory, '--case', 'case.json', '--log-dir', str(root / 'logs'),
                        '--report-json', str(root / 'report.json'), '--report-junit', str(root / 'report.xml')]
                with patch.object(sys, 'argv', args), patch.object(cli, '_run_case_with_project_settings', return_value=result), contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main()
                data = json.loads((root / 'report.json').read_text())
                suite = ET.parse(root / 'report.xml').getroot()
                self.assertEqual(code, 0 if status == 'passed' else 1)
                self.assertEqual(data['exitCode'], code)
                self.assertEqual(data['status'], 'timeout' if error and 'timed out' in error else status)
                self.assertEqual(len(suite.findall('testcase')), 1)
                self.assertEqual(len(suite.find('testcase')), 0 if code == 0 else 1)
                self.assertNotIn('PRIVATE', (root / 'report.json').read_text() + (root / 'report.xml').read_text())

    def test_empty_timeout_exception_is_classified_without_message(self):
        with patch('api_test.runner.execute_http_call', side_effect=TimeoutError()):
            result = ApiTestRunner(1).run_case('timeout', {'request': {'url': 'https://example.test'}, 'expected': {}})
        report = RunReport()
        report.add(result, 'timeout.json', now())
        self.assertEqual(report.finish(1)['status'], 'timeout')

    def test_pipeline_retains_completed_steps_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'case.json').write_text('{"request": {"url": "https://example.test"}}')
            pipeline = root / 'pipeline.json'
            pipeline.write_text(json.dumps({'steps': [{'name': name, 'case': 'case.json'} for name in ['first', 'second', 'third']]}))
            report = RunReport()
            results = [CaseResult('first', 'passed', 1), CaseResult('second', 'failed', 1)]
            with patch.object(cli, '_run_case_with_project_settings', side_effect=results), contextlib.redirect_stdout(io.StringIO()):
                code = cli.run_pipeline(pipeline, root, 1, root / 'logs', report_result=report)
            self.assertEqual(code, 1)
            self.assertEqual([i['caseId'] for i in report.finish(code)['targets']], ['first', 'second'])
            self.assertEqual(report.data['status'], 'failed')

    def test_configuration_error_produces_reports_in_real_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.run([sys.executable, 'run_api_tests.py', str(root / 'missing.json'),
                                        '--report-json', str(root / 'report.json'), '--report-junit', str(root / 'report.xml'),
                                        '--log-dir', str(root / 'logs')], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads((root / 'report.json').read_text())['status'], 'error')
            self.assertEqual(ET.parse(root / 'report.xml').getroot().attrib['errors'], '1')

    def test_web_reuses_report_run_id_and_cleans_artifact(self):
        paths = []
        def run(command, **kwargs):
            path = Path(command[command.index('--report-json') + 1])
            paths.append(path)
            report = RunReport(run_id=command[command.index('--run-id') + 1])
            report.add(CaseResult('failed_case', 'failed', 1), 'case.json', now())
            report.finish(1)
            report.write(path)
            return subprocess.CompletedProcess(command, 1, 'failed', '')
        with patch.object(studio, 'postgres_enabled', return_value=False), patch.object(studio, 'execution_metadata', return_value=([], [])), \
             patch.object(studio, 'execution_history') as history, patch.object(studio.subprocess, 'run', side_effect=run):
            response = studio.execute_studio_run(['runner'], {})
            self.assertEqual(response['runId'], response['result']['runId'])
            self.assertEqual(response['exitCode'], response['result']['exitCode'])
            self.assertEqual(history.return_value.record.call_args.kwargs['status'], 'failed')
        self.assertFalse(paths[0].exists())
