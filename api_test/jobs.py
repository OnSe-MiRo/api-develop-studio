"""Bounded, process-local job lifecycle shared by Studio execution workers."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from contextvars import copy_context
from datetime import datetime, timedelta, timezone
import hashlib
from dataclasses import dataclass, field
import os
import threading
import time
import uuid

from api_test.database import LOCAL_CONTEXT
from api_test.reports import now

TERMINAL = frozenset({'passed', 'failed', 'error', 'timeout', 'cancelled'})


class JobError(Exception):
    def __init__(self, message, status_code, *, code=None, guidance=None):
        super().__init__(message)
        self.status_code = status_code
        self.code, self.guidance = code, guidance


@dataclass
class Job:
    id: str
    owner: object
    projects: tuple
    task: object
    data: dict
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    finished: float = 0
    committed: bool = False
    artifact: bytes | None = None
    artifact_filename: str | None = None


class JobManager:
    def __init__(self, *, workers=2, capacity=20, user_limit=10, project_limit=10, retention=600, max_completed=100,
                 artifact_limit=32 * 1024 * 1024, artifact_total=128 * 1024 * 1024):
        if min(workers, capacity, user_limit, project_limit, retention, max_completed, artifact_limit, artifact_total) <= 0 or artifact_limit > artifact_total:
            raise ValueError('Job limits must be positive')
        self.workers, self.capacity = workers, capacity
        self.user_limit, self.project_limit = user_limit, project_limit
        self.retention, self.max_completed = retention, max_completed
        self.artifact_limit, self.artifact_total = artifact_limit, artifact_total
        self.jobs, self.pending, self.threads = {}, deque(), []
        self.downloads = {}
        self.download_limit = 4
        self.condition = threading.Condition()
        self.slots = threading.BoundedSemaphore(workers)
        self.closed = False

    @classmethod
    def from_environment(cls):
        names = {'workers': 2, 'capacity': 20, 'user_limit': 10, 'project_limit': 10,
                 'retention': 600, 'max_completed': 100}
        return cls(**{key: int(os.environ.get('RUN_' + key.upper(), default)) for key, default in names.items()})

    def _prune(self):
        complete = [j for j in self.jobs.values() if j.done.is_set()]
        complete.sort(key=lambda j: j.finished)
        for index, job in enumerate(complete):
            if time.monotonic() - job.finished > self.retention or index < len(complete) - self.max_completed:
                job.artifact = None
                job.artifact_filename = None
                job.data.get('generation', {})['artifactReady'] = False
                job.data.get('generation', {})['artifact'] = None
                del self.jobs[job.id]

    def submit(self, task, *, owner=LOCAL_CONTEXT, projects=(), initial=None):
        with self.condition:
            self._prune()
            if self.closed:
                raise JobError('실행 worker가 종료 중입니다.', 503)
            active = [j for j in self.jobs.values() if not j.done.is_set()]
            if len(active) >= self.capacity:
                raise JobError('실행 대기 한도를 초과했습니다. 진행 중인 작업이 끝난 후 다시 실행하세요.', 429,
                               code='RUN_CAPACITY_EXCEEDED', guidance='접수되지 않았습니다. 기존 Run ID로 완료 상태를 확인한 뒤 새 작업을 명시적으로 제출하세요.')
            if sum((j.owner.workspace_id, j.owner.user_id) == (owner.workspace_id, owner.user_id) for j in active) >= self.user_limit:
                raise JobError('실행 대기 한도를 초과했습니다. 진행 중인 작업이 끝난 후 다시 실행하세요.', 429,
                               code='RUN_USER_LIMIT_EXCEEDED', guidance='접수되지 않았습니다. 본인의 기존 Run ID로 완료 상태를 확인한 뒤 새 작업을 명시적으로 제출하세요.')
            projects = tuple(sorted(set(projects))) or ('__unassigned__',)
            for project in projects:
                if sum(j.owner.workspace_id == owner.workspace_id and project in j.projects for j in active) >= self.project_limit:
                    raise JobError('프로젝트 실행 대기 한도를 초과했습니다.', 429,
                                   code='RUN_PROJECT_LIMIT_EXCEEDED', guidance='접수되지 않았습니다. 해당 프로젝트의 진행 중 작업이 끝난 뒤 새 작업을 명시적으로 제출하세요.')
            run_id = str(uuid.uuid4())
            scope = copy_context()
            job = Job(run_id, owner, projects, lambda job: scope.run(task, job), {
                'runId': run_id, 'status': 'queued', 'createdAt': now(), 'startedAt': None,
                'finishedAt': None, 'exitCode': None, 'result': None,
                **deepcopy(initial or {}),
            })
            self.jobs[run_id] = job
            self.pending.append(job)
            if not self.threads:
                for index in range(self.workers):
                    thread = threading.Thread(target=self._worker, name=f'studio-run-{index}', daemon=True)
                    self.threads.append(thread)
                    thread.start()
            self.condition.notify_all()
            return deepcopy(job.data)

    def _owned(self, run_id, owner):
        self._prune()
        job = self.jobs.get(run_id)
        if job is None or (job.owner.workspace_id, job.owner.user_id) != (owner.workspace_id, owner.user_id):
            raise JobError('실행 작업을 찾을 수 없습니다.', 404)
        return job

    def get(self, run_id, owner=LOCAL_CONTEXT):
        with self.condition:
            return deepcopy(self._owned(run_id, owner).data)

    def artifact(self, run_id, owner=LOCAL_CONTEXT):
        with self.condition:
            job = self._owned(run_id, owner)
            if job.data.get('kind') != 'sdk_generation':
                raise JobError('SDK artifact를 찾을 수 없습니다.', 404)
            if not job.done.is_set() or job.data['status'] != 'passed':
                raise JobError('SDK 생성 결과가 아직 준비되지 않았습니다.', 409)
            if job.artifact is None or not job.artifact_filename:
                raise JobError('SDK artifact를 찾을 수 없습니다.', 404)
            size = len(job.artifact)
            if len(self.downloads) >= self.download_limit or sum(self.downloads.values()) + size > self.artifact_total:
                raise JobError('SDK artifact 다운로드 한도를 초과했습니다.', 429)
            lease_id = str(uuid.uuid4())
            self.downloads[lease_id] = size
            # Immutable bytes outlive an eviction racing with response streaming.
            return job.artifact, job.artifact_filename, lease_id

    def release_artifact(self, lease_id):
        with self.condition:
            self.downloads.pop(lease_id, None)

    def _publish_artifact(self, job, artifact, filename):
        if (not isinstance(artifact, bytes) or not artifact or len(artifact) > self.artifact_limit or
                not isinstance(filename, str) or not filename.endswith('.zip') or
                '/' in filename or chr(92) in filename or any(ord(char) < 33 for char in filename)):
            return False
        completed = sorted((item for item in self.jobs.values() if item.done.is_set() and item.artifact),
                           key=lambda item: item.finished)
        total = sum(len(item.artifact) for item in completed)
        for old in completed:
            if total + len(artifact) <= self.artifact_total:
                break
            total -= len(old.artifact)
            old.artifact = None
            old.artifact_filename = None
            old.data.get('generation', {})['artifactReady'] = False
            old.data.get('generation', {})['artifact'] = None
        if total + len(artifact) > self.artifact_total:
            return False
        job.artifact, job.artifact_filename = artifact, filename
        job.data.get('generation', {})['artifactReady'] = True
        job.data.get('generation', {})['artifact'] = {
            'sizeBytes': len(artifact), 'sha256': hashlib.sha256(artifact).hexdigest(),
            'expiresAt': (datetime.now(timezone.utc) + timedelta(seconds=self.retention)).isoformat(),
        }
        return True

    def cancel(self, run_id, owner=LOCAL_CONTEXT):
        with self.condition:
            job = self._owned(run_id, owner)
            if not job.done.is_set() and not job.committed:
                job.cancel.set()
                if job in self.pending:
                    self.pending.remove(job)
                    self._finish(job, {'status': 'cancelled'})
                else:
                    job.data['status'] = 'cancelling'
                self.condition.notify_all()
            return deepcopy(job.data)

    def _finish(self, job, result):
        job.data.update(result, finishedAt=now())
        job.task = None
        job.finished = time.monotonic()
        job.done.set()
        self._prune()
        self.condition.notify_all()

    def _worker(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.closed)
                if self.closed and not self.pending:
                    return
                job = self.pending.popleft()
            while not self.slots.acquire(timeout=0.1):
                if job.cancel.is_set():
                    break
            else:
                try:
                    with self.condition:
                        job.data.update(status='running', startedAt=now())
                    if job.cancel.is_set():
                        result = {'status': 'cancelled'}
                    else:
                        result = job.task(job)
                except Exception:
                    # Neither exception text nor tracebacks are retained in queryable job results.
                    result = {'status': 'error', 'error': '실행 작업 처리에 실패했습니다.'}
                finally:
                    self.slots.release()
                with self.condition:
                    artifact = result.pop('_artifact', None)
                    filename = result.pop('_artifact_filename', None)
                    if job.cancel.is_set():
                        result.update(status='cancelled', exitCode=None, result=None)
                        result.get('generation', {})['artifactReady'] = False
                    elif artifact is not None:
                        if result.get('status') != 'passed' or not self._publish_artifact(job, artifact, filename):
                            result.update(status='error', exitCode=None, result=None,
                                          error='SDK artifact 보존 한도를 초과했습니다.')
                            result.get('generation', {})['artifactReady'] = False
                        else:
                            result['generation'] = {**deepcopy(job.data.get('generation', {})),
                                                    **result.get('generation', {}),
                                                    'artifactReady': True,
                                                    'artifact': deepcopy(job.data['generation']['artifact'])}
                    self._finish(job, result)
                # Worker threads may idle indefinitely: drop their last ZIP/Job locals.
                artifact = filename = result = job = None
                continue
            with self.condition:
                self._finish(job, {'status': 'cancelled'})

    @contextmanager
    def legacy_slot(self):
        """Synchronous compatibility calls share the worker concurrency ceiling."""
        if self.closed:
            raise JobError('실행 worker가 종료 중입니다.', 503)
        if not self.slots.acquire(blocking=False):
            raise JobError('동시 실행 한도를 초과했습니다.', 429, code='RUN_WORKERS_BUSY',
                           guidance='실행이 시작되지 않았습니다. 대기가 필요하면 POST /api/runs로 한 번 제출하고 반환된 Run ID를 조회하세요. 비동기 대기열에도 한도가 있습니다.')
        try:
            yield
        finally:
            self.slots.release()

    def close(self):
        with self.condition:
            self.closed = True
            for job in self.jobs.values():
                if not job.done.is_set() and not job.committed:
                    job.cancel.set()
            self.condition.notify_all()
        for thread in self.threads:
            thread.join()
        with self.condition:
            for job in self.jobs.values():
                job.artifact = None
                job.artifact_filename = None
                job.data.get('generation', {})['artifactReady'] = False
                job.data.get('generation', {})['artifact'] = None
