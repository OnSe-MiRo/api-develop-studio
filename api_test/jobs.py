"""Bounded, process-local job lifecycle shared by Studio execution workers."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import os
import threading
import time
import uuid

from api_test.database import LOCAL_CONTEXT
from api_test.reports import now

TERMINAL = frozenset({'passed', 'failed', 'error', 'timeout', 'cancelled'})


class JobError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


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


class JobManager:
    def __init__(self, *, workers=2, capacity=20, user_limit=10, project_limit=10, retention=600, max_completed=100):
        if min(workers, capacity, user_limit, project_limit, retention, max_completed) <= 0:
            raise ValueError('Job limits must be positive')
        self.workers, self.capacity = workers, capacity
        self.user_limit, self.project_limit = user_limit, project_limit
        self.retention, self.max_completed = retention, max_completed
        self.jobs, self.pending, self.threads = {}, deque(), []
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
                del self.jobs[job.id]

    def submit(self, task, *, owner=LOCAL_CONTEXT, projects=()):
        with self.condition:
            self._prune()
            if self.closed:
                raise JobError('실행 worker가 종료 중입니다.', 503)
            active = [j for j in self.jobs.values() if not j.done.is_set()]
            if len(active) >= self.capacity or sum((j.owner.workspace_id, j.owner.user_id) == (owner.workspace_id, owner.user_id) for j in active) >= self.user_limit:
                raise JobError('실행 대기 한도를 초과했습니다. 진행 중인 작업이 끝난 후 다시 실행하세요.', 429)
            projects = tuple(sorted(set(projects))) or ('__unassigned__',)
            for project in projects:
                if sum(j.owner.workspace_id == owner.workspace_id and project in j.projects for j in active) >= self.project_limit:
                    raise JobError('프로젝트 실행 대기 한도를 초과했습니다.', 429)
            run_id = str(uuid.uuid4())
            job = Job(run_id, owner, projects, task, {
                'runId': run_id, 'status': 'queued', 'createdAt': now(), 'startedAt': None,
                'finishedAt': None, 'exitCode': None, 'result': None,
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

    def cancel(self, run_id, owner=LOCAL_CONTEXT):
        with self.condition:
            job = self._owned(run_id, owner)
            if not job.done.is_set():
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
                    self._finish(job, result)
                continue
            with self.condition:
                self._finish(job, {'status': 'cancelled'})

    @contextmanager
    def legacy_slot(self):
        """Synchronous compatibility calls share the worker concurrency ceiling."""
        if self.closed:
            raise JobError('실행 worker가 종료 중입니다.', 503)
        if not self.slots.acquire(blocking=False):
            raise JobError('동시 실행 한도를 초과했습니다.', 429)
        try:
            yield
        finally:
            self.slots.release()

    def close(self):
        with self.condition:
            self.closed = True
            for job in self.jobs.values():
                if not job.done.is_set():
                    job.cancel.set()
            self.condition.notify_all()
        for thread in self.threads:
            thread.join()
