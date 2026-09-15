"""Cancellable process-tree execution. Temporary reports and logs belong to one job."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
from tempfile import TemporaryDirectory
import time

from api_test.reports import now


def stop_process_tree(process):
    if os.name == 'nt':
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        # Kill the session group even after the leader exits: descendants may still be alive.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def execute_job(job, command, studio, projects, targets):
    timeout = float(os.environ.get('RUN_TIMEOUT_SECONDS', '300'))
    if not 0 < timeout <= 86400:
        raise ValueError('RUN_TIMEOUT_SECONDS must be between 0 and 86400')
    started = time.monotonic()
    started_at = now()
    response = {'status': 'error', 'exitCode': None, 'result': None}
    with TemporaryDirectory(prefix='api-test-job-') as directory:
        root = Path(directory)
        report_path = root / 'result.json'
        command = [*command, '--report-json', str(report_path), '--run-id', job.id, '--log-dir', str(root / 'logs')]
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        with (root / "output.txt").open("w+b") as output:
            process = None
            try:
                if job.cancel.is_set():
                    response['status'] = 'cancelled'
                else:
                    process = subprocess.Popen(command, cwd=studio.ROOT, stdout=output, stderr=subprocess.STDOUT, **options)
                    while process.poll() is None:
                        if job.cancel.wait(0.05):
                            response['status'] = 'cancelled'
                            break
                        if time.monotonic() - started >= timeout:
                            response['status'] = 'timeout'
                            break
                        if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 8 * 1024 * 1024:
                            response['error'] = '실행 artifact 크기 한도를 초과했습니다.'
                            break
                    else:
                        response['exitCode'] = process.returncode
                        if report_path.is_file() and report_path.stat().st_size <= 1024 * 1024:
                            report = json.loads(report_path.read_text(encoding='utf-8'))
                            if report.get('runId') == job.id and report.get('exitCode') == process.returncode:
                                report['artifacts'] = []
                                response.update(status=report['status'], result=report)
                        if response['result'] is None:
                            response['error'] = '실행 보고서를 생성하지 못했습니다.'
            finally:
                if process is not None:
                    stop_process_tree(process)
            output.seek(0)
            captured = output.read(1024 * 1024 + 1)
            response['output'] = captured[:1024 * 1024].decode('utf-8', errors='replace')
            if len(captured) > 1024 * 1024:
                response['output'] += '\n[실행 출력은 1 MiB까지만 표시합니다.]'
    # Publish completion only after descendants and both temporary directories are cleaned.
    try:
        studio.execution_history().record(run_id=job.id, started_at=started_at, finished_at=now(),
            duration_ms=(time.monotonic() - started) * 1000, status=response['status'],
            exit_code=response['exitCode'], projects=projects, targets=targets)
    except (OSError, ValueError, *studio.DATABASE_ERRORS):
        response['historyWarning'] = '실행 이력을 저장하지 못했습니다. 저장소 상태를 확인하세요.'
    return response
