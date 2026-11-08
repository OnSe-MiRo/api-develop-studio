"""Bounded HTTP workers whose idle threads expire during the application's lifetime."""
import asyncio
from collections import deque
from concurrent.futures import Future
from contextvars import copy_context
from functools import partial
import threading

import anyio


class RequestThreads:
    def __init__(self, max_workers=40, idle_seconds=1):
        if max_workers < 1 or idle_seconds <= 0:
            raise ValueError('Request thread limits must be positive')
        self.max_workers = max_workers
        self.idle_seconds = idle_seconds
        self.closed = False
        self._condition = threading.Condition()
        self._pending = deque()
        self._workers = set()
        self._idle = 0
        self._sequence = 0

    def submit(self, function, *args):
        future = Future()
        context = copy_context()
        with self._condition:
            if self.closed:
                raise RuntimeError('Request workers are closed')
            if len(self._pending) >= self.max_workers:
                raise RuntimeError('Request worker queue is full')
            item = (future, context, partial(function, *args))
            self._pending.append(item)
            if len(self._pending) > self._idle and len(self._workers) < self.max_workers:
                self._sequence += 1
                thread = threading.Thread(target=self._work, name=f'studio-http-{self._sequence}', daemon=True)
                self._workers.add(thread)
                try:
                    thread.start()
                except BaseException:
                    self._workers.remove(thread)
                    self._pending.remove(item)
                    raise
            self._condition.notify()
        return future

    def _work(self):
        try:
            while True:
                with self._condition:
                    self._idle += 1
                    try:
                        self._condition.wait_for(lambda: self.closed or self._pending, self.idle_seconds)
                    finally:
                        self._idle -= 1
                    if not self._pending:
                        self._workers.discard(threading.current_thread())
                        self._condition.notify_all()
                        return
                    future, context, function = self._pending.popleft()
                try:
                    if future.set_running_or_notify_cancel():
                        try:
                            result = context.run(function)
                        except BaseException as error:
                            future.set_exception(error)
                        else:
                            future.set_result(result)
                            del result
                finally:
                    del future, context, function
        finally:
            with self._condition:
                self._workers.discard(threading.current_thread())
                self._condition.notify_all()

    async def run_sync(self, function, *args):
        # Keep the same admission limiter as the original AnyIO dispatch. A cancelled
        # caller retains its admission token until its synchronous work has finished.
        async with anyio.to_thread.current_default_thread_limiter():
            with anyio.CancelScope(shield=True):
                future = asyncio.wrap_future(self.submit(function, *args))
                cancelled = False
                while True:
                    try:
                        result = await asyncio.shield(future)
                    except asyncio.CancelledError:
                        if future.done():
                            raise
                        cancelled = True
                    except BaseException:
                        if cancelled:
                            raise asyncio.CancelledError
                        raise
                    else:
                        if cancelled:
                            raise asyncio.CancelledError
                        return result

    def shutdown(self, wait=True, cancel_futures=False):
        with self._condition:
            self.closed = True
            if cancel_futures:
                while self._pending:
                    future, _, _ = self._pending.popleft()
                    future.cancel()
            workers = tuple(self._workers)
            self._condition.notify_all()
        if wait:
            for worker in workers:
                worker.join()
