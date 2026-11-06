import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from api_test.database import RequestContext
from api_test.jobs import JobError, JobManager, TERMINAL
from api_test.job_runner import execute_job
from api_test.main import create_app
from api_test.services import studio


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError('Timed out waiting for job state')


class JobManagerTests(unittest.TestCase):
    def manager(self, **kwargs):
        manager = JobManager(**kwargs)
        self.addCleanup(manager.close)
        return manager

    def test_capacity_queued_cancel_and_owner_isolation(self):
        manager = self.manager(workers=1, capacity=2, user_limit=2)
        started = threading.Event()
        def task(job):
            started.set()
            job.cancel.wait(3)
            return {'status': 'cancelled'}
        first = manager.submit(task)['runId']
        self.assertTrue(started.wait(2))
        second = manager.submit(task)['runId']
        with self.assertRaises(JobError) as rejected:
            manager.submit(task)
        self.assertEqual(rejected.exception.status_code, 429)
        for action in (manager.get, manager.cancel):
            with self.assertRaises(JobError) as denied:
                action(first, RequestContext('default', 'another-user'))
            self.assertEqual(denied.exception.status_code, 404)
        self.assertEqual(manager.cancel(second)['status'], 'cancelled')
        self.assertEqual(manager.cancel(second)['status'], 'cancelled')
        third = manager.submit(task)['runId']
        manager.cancel(third)
        manager.cancel(first)
        eventually(lambda: manager.get(first)['status'] == 'cancelled')

    def test_project_quota_counts_other_users_and_user_quota_ignores_request_id(self):
        manager = self.manager(workers=1, project_limit=1, user_limit=1)
        def task(job):
            job.cancel.wait(3)
            return {'status': 'cancelled'}
        first = manager.submit(task, owner=RequestContext('w', 'u', 'r1'), projects=['p'])['runId']
        for owner, projects in [(RequestContext('w', 'other'), ['p']), (RequestContext('w', 'u', 'r2'), ['other'])]:
            with self.assertRaises(JobError):
                manager.submit(task, owner=owner, projects=projects)
        manager.cancel(first, RequestContext('w', 'u'))

    def test_worker_ceiling_and_shutdown(self):
        manager = self.manager(workers=2)
        entered = []
        lock = threading.Lock()
        def task(job):
            with lock:
                entered.append(job.id)
            job.cancel.wait(3)
            return {'status': 'cancelled'}
        ids = [manager.submit(task)['runId'] for _ in range(4)]
        eventually(lambda: len(entered) == 2)
        with self.assertRaises(JobError):
            with manager.legacy_slot():
                self.fail('legacy must share worker ceiling')
        manager.close()
        self.assertTrue(all(manager.get(i)['status'] == 'cancelled' for i in ids))
        self.assertFalse(any(t.is_alive() for t in manager.threads))
        with self.assertRaises(JobError):
            manager.submit(task)

    def test_completed_retention_is_bounded_and_expired_ids_are_404(self):
        manager = self.manager(max_completed=1)
        first = manager.submit(lambda job: {'status': 'passed'})['runId']
        eventually(lambda: manager.get(first)['status'] == 'passed')
        second = manager.submit(lambda job: {'status': 'passed'})['runId']
        eventually(lambda: manager.get(second)['status'] == 'passed')
        with self.assertRaises(JobError):
            manager.get(first)
        manager.jobs[second].finished -= 601
        with self.assertRaises(JobError):
            manager.get(second)


class ProcessJobTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX process group verification; Windows taskkill needs Windows runner')
    def test_cancel_timeout_and_shutdown_kill_descendants_and_clean_files(self):
        for operation in ('cancel', 'timeout', 'shutdown'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                marker = Path(directory) / 'marker.json'
                script = """import json, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
pathlib.Path(sys.argv[1]).write_text(json.dumps({'child': child.pid, 'logs': sys.argv[sys.argv.index('--log-dir')+1]}))
time.sleep(60)
"""
                manager = JobManager(workers=1)
                try:
                    with patch.dict(os.environ, {'RUN_TIMEOUT_SECONDS': '0.4' if operation == 'timeout' else '30'}), patch.object(studio, 'execution_history', return_value=Mock()):
                        run_id = manager.submit(lambda job: execute_job(job, [sys.executable, '-c', script, str(marker)], studio, [], []))['runId']
                        eventually(marker.exists)
                        data = json.loads(marker.read_text())
                        if operation == 'cancel':
                            manager.cancel(run_id)
                        elif operation == 'shutdown':
                            manager.close()
                        eventually(lambda: manager.get(run_id)['status'] in TERMINAL)
                        self.assertEqual(manager.get(run_id)['status'], 'timeout' if operation == 'timeout' else 'cancelled')
                        self.assertFalse(Path(data['logs']).parent.exists())
                        def child_dead():
                            result = subprocess.run(['ps', '-o', 'stat=', '-p', str(data['child'])], capture_output=True, text=True)
                            return not result.stdout.strip() or result.stdout.strip().startswith('Z')
                        eventually(child_dead)
                finally:
                    manager.close()


class JobApiTests(unittest.TestCase):
    def test_async_contract_validation_result_and_independent_lookup(self):
        app = create_app(studio)
        with patch.object(studio, 'execution_history', return_value=Mock()), TestClient(app, base_url='http://127.0.0.1:8765') as client:
            self.assertEqual(client.post('/api/runs', json={'cases': '../bad'}).status_code, 400)
            self.assertEqual(client.post('/api/runs', json={'cases': ['../bad.json']}).status_code, 400)
            self.assertEqual(client.get('/api/runs/missing').status_code, 404)
            self.assertEqual(client.post('/api/runs', content='x' * (1024 * 1024 + 1)).status_code, 413)
            submitted = client.post('/api/runs', json={'inlineCase': {'request': {}, 'expected': {}}, 'user_id': 'spoofed'})
            self.assertEqual(submitted.status_code, 202)
            run_id = submitted.json()['runId']
            # A new client connection can still inspect the server-owned job.
            other = TestClient(app, base_url='http://127.0.0.1:8765')
            result = eventually(lambda: (data if (data := other.get('/api/runs/' + run_id).json())['status'] in TERMINAL else None))
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['runId'], result['result']['runId'])
            self.assertEqual(client.post(f'/api/runs/{run_id}/cancel').json()['status'], 'error')

    def test_queue_rejection_is_http_429_and_cancel_is_available(self):
        app = create_app(studio)
        app.state.jobs = JobManager(workers=1, capacity=1)
        def blocked(job, *args):
            job.cancel.wait(3)
            return {'status': 'cancelled'}
        with patch('api_test.services.execution.execute_job', side_effect=blocked), TestClient(app, base_url='http://127.0.0.1:8765') as client:
            first = client.post('/api/runs', json={'cases': []}).json()['runId']
            self.assertEqual(client.post('/api/runs', json={'cases': []}).status_code, 429)
            self.assertIn(client.post(f'/api/runs/{first}/cancel').json()['status'], ('cancelling', 'cancelled'))
            eventually(lambda: client.get('/api/runs/' + first).json()['status'] == 'cancelled')

class AdmissionPolicyTests(unittest.TestCase):
    def test_rejection_reasons_never_create_jobs_and_limits_recover(self):
        for options, code in (({'capacity': 1}, 'RUN_CAPACITY_EXCEEDED'),
                              ({'user_limit': 1}, 'RUN_USER_LIMIT_EXCEEDED'),
                              ({'project_limit': 1}, 'RUN_PROJECT_LIMIT_EXCEEDED')):
            with self.subTest(code=code):
                manager = JobManager(workers=1, **options)
                try:
                    first = manager.submit(lambda job: (job.cancel.wait(3), {'status': 'cancelled'})[1])['runId']
                    with self.assertRaises(JobError) as rejected:
                        manager.submit(lambda job: {'status': 'passed'})
                    self.assertEqual(rejected.exception.code, code)
                    self.assertEqual(set(manager.jobs), {first})
                    manager.cancel(first)
                    eventually(lambda: manager.get(first)['status'] == 'cancelled')
                    resumed = manager.submit(lambda job: {'status': 'passed'})['runId']
                    eventually(lambda: manager.get(resumed)['status'] == 'passed')
                finally:
                    manager.close()

    def test_sync_wait_limit_order_and_slot_release_after_error(self):
        manager = JobManager(workers=1, sync_waiters=2)
        self.addCleanup(manager.close)
        started = []

        def execute(name):
            with manager.legacy_slot(wait_on_busy=True):
                started.append(name)
                if name == 'first':
                    raise RuntimeError('runner failed')

        with ThreadPoolExecutor(2) as pool:
            with manager.legacy_slot():
                first = pool.submit(execute, 'first')
                eventually(lambda: len(manager._sync_waiters) == 1)
                second = pool.submit(execute, 'second')
                eventually(lambda: len(manager._sync_waiters) == 2)
                for wait_on_busy in (True, False):
                    with self.assertRaises(JobError) as rejected, manager.legacy_slot(wait_on_busy=wait_on_busy):
                        self.fail('capacity must be bounded')
                    self.assertEqual(rejected.exception.code, 'RUN_WORKERS_BUSY')
            with self.assertRaisesRegex(RuntimeError, 'runner failed'):
                first.result(timeout=2)
            second.result(timeout=2)
        self.assertEqual(started, ['first', 'second'])
        self.assertFalse(manager._sync_waiters)

    def test_async_completion_wakes_waiting_sync_run(self):
        manager = JobManager(workers=1)
        self.addCleanup(manager.close)
        started, release = threading.Event(), threading.Event()

        def async_task(job):
            started.set()
            release.wait(3)
            return {'status': 'passed'}

        def sync_run():
            with manager.legacy_slot(wait_on_busy=True):
                return 'ran once'

        run_id = manager.submit(async_task)['runId']
        with ThreadPoolExecutor(1) as pool:
            try:
                self.assertTrue(started.wait(2))
                waiting = pool.submit(sync_run)
                eventually(lambda: bool(manager._sync_waiters))
            finally:
                release.set()
            self.assertEqual(waiting.result(timeout=1), 'ran once')
        eventually(lambda: manager.get(run_id)['status'] == 'passed')

    def test_shutdown_wakes_sync_waiter_without_dispatch(self):
        manager = JobManager(workers=1)
        def wait_for_run():
            with manager.legacy_slot(wait_on_busy=True):
                self.fail('shutdown must not admit the waiting run')
        with ThreadPoolExecutor(1) as pool, manager.legacy_slot():
            waiting = pool.submit(wait_for_run)
            eventually(lambda: bool(manager._sync_waiters))
            manager.close()
            with self.assertRaises(JobError) as stopped:
                waiting.result(timeout=1)
        self.assertEqual(stopped.exception.status_code, 503)
        self.assertFalse(manager._sync_waiters)

    def test_sync_wait_settings_allow_immediate_rejection_and_reject_unbounded_values(self):
        for setting, invalid in (('RUN_SYNC_WAITERS', '17'), ('RUN_SYNC_WAIT_SECONDS', '11')):
            with patch.dict(os.environ, {setting: invalid}), self.assertRaises(ValueError):
                JobManager.from_environment()
            with patch.dict(os.environ, {setting: '0'}):
                manager = JobManager.from_environment()
                self.addCleanup(manager.close)
                with patch.object(manager.slots, 'acquire', return_value=False), \
                        patch.object(manager.condition, 'wait') as wait:
                    with self.assertRaises(JobError) as rejected, manager.legacy_slot(wait_on_busy=True):
                        self.fail('disabled wait must reject')
                    self.assertEqual(rejected.exception.status_code, 429)
                    wait.assert_not_called()

    def test_sync_http_burst_finishes_once_per_request_with_two_workers(self):
        app = create_app(studio)
        app.state.jobs = JobManager(workers=2)
        both_running = threading.Event()
        third_arrived = threading.Event()
        release = threading.Event()
        lock = threading.Lock()
        calls = []
        active = peak = 0
        read_body = studio.StudioRequest.read_body

        def observe_request(request):
            body = read_body(request)
            if body['inlineCase']['name'] == 'third':
                third_arrived.set()
            return body

        def execute(command, body):
            nonlocal active, peak
            name = body['inlineCase']['name']
            with lock:
                active += 1
                peak = max(peak, active)
                calls.append(name)
                if active == 2:
                    both_running.set()
            try:
                if name != 'third':
                    self.assertTrue(release.wait(3))
                return {'runId': name, 'exitCode': 0}
            finally:
                with lock:
                    active -= 1

        with TestClient(app, base_url='http://127.0.0.1:8765') as client, \
                patch.object(studio.StudioRequest, 'read_body', observe_request), \
                patch.object(studio, 'execute_studio_run', side_effect=execute), ThreadPoolExecutor(3) as pool:
            def submit(name):
                return pool.submit(client.post, '/api/run', json={'inlineCase': {'name': name}})

            first, second = submit('first'), submit('second')
            try:
                self.assertTrue(both_running.wait(2))
                third = submit('third')
                self.assertTrue(third_arrived.wait(2))
                with self.assertRaises(FutureTimeout):
                    third.result(timeout=0.1)
            finally:
                release.set()
            for future, name in ((first, 'first'), (second, 'second'), (third, 'third')):
                response = future.result(timeout=3)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['runId'], name)
            self.assertCountEqual(calls, ['first', 'second', 'third'])
            self.assertEqual(peak, 2)
            self.assertFalse(app.state.jobs.jobs)

    def test_sync_429_guidance_and_async_queue_share_slots_without_fallback(self):
        app = create_app(studio)
        app.state.jobs = JobManager(workers=1, sync_wait_seconds=0.05)
        started = threading.Event()
        def blocked(job, *args):
            started.set()
            job.cancel.wait(3)
            return {'status': 'cancelled'}
        with patch('api_test.services.execution.execute_job', side_effect=blocked), TestClient(app, base_url='http://127.0.0.1:8765') as client:
            first = client.post('/api/runs', json={'cases': []}).json()['runId']
            self.assertTrue(started.wait(2))
            with patch.object(studio, 'execute_studio_run') as runner:
                rejected = client.post('/api/run', json={'cases': []})
                self.assertEqual(rejected.status_code, 429)
                self.assertEqual(rejected.json()['error'], '동시 실행 한도를 초과했습니다.')
                self.assertEqual(rejected.json()['code'], 'RUN_WORKERS_BUSY')
                self.assertFalse(rejected.json()['admission']['accepted'])
                self.assertIn('POST /api/runs', rejected.json()['admission']['guidance'])
                runner.assert_not_called()
                self.assertEqual(set(app.state.jobs.jobs), {first})
            self.assertFalse(app.state.jobs._sync_waiters)
            second = client.post('/api/runs', json={'cases': []})
            self.assertEqual(second.status_code, 202)
            self.assertEqual(second.json()['status'], 'queued')
            client.post('/api/runs/' + second.json()['runId'] + '/cancel')
            client.post('/api/runs/' + first + '/cancel')

    def test_queue_429_response_preserves_error_and_contains_no_run_id(self):
        app = create_app(studio)
        app.state.jobs = JobManager(workers=1, capacity=1)
        with patch('api_test.services.execution.execute_job', side_effect=lambda job, *args: (job.cancel.wait(3), {'status': 'cancelled'})[1]), TestClient(app, base_url='http://127.0.0.1:8765') as client:
            first = client.post('/api/runs', json={'cases': []}).json()['runId']
            rejected = client.post('/api/runs', json={'cases': []})
            self.assertEqual(rejected.status_code, 429)
            self.assertEqual(rejected.json()['code'], 'RUN_CAPACITY_EXCEEDED')
            self.assertFalse(rejected.json()['admission']['accepted'])
            self.assertNotIn('runId', rejected.json())
            self.assertEqual(set(app.state.jobs.jobs), {first})
            client.post('/api/runs/' + first + '/cancel')
