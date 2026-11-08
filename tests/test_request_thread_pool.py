import asyncio
from contextvars import ContextVar
import threading
import time
import unittest
from unittest.mock import patch

from api_test.request_threads import RequestThreads


class RequestPoolTests(unittest.TestCase):
    def test_ceiling_context_failure_and_idle_expiry(self):
        pool = RequestThreads(max_workers=2, idle_seconds=.05)
        self.addCleanup(pool.shutdown)
        value = ContextVar('test_scope', default='missing')
        value.set('workspace-a')
        gate = threading.Event()
        started = []
        def task():
            started.append(threading.get_ident())
            gate.wait(2)
            return value.get()
        first, second = pool.submit(task), pool.submit(task)
        deadline = time.monotonic()+1
        while len(started)<2 and time.monotonic()<deadline:
            time.sleep(.005)
        self.assertEqual(len(set(started)),2)
        third = pool.submit(lambda: 1/0)
        try:
            self.assertFalse(third.done())
        finally:
            gate.set()
        self.assertEqual(first.result(timeout=1),'workspace-a')
        self.assertEqual(second.result(timeout=1),'workspace-a')
        with self.assertRaises(ZeroDivisionError):
            third.result(timeout=1)
        deadline = time.monotonic()+1
        while pool._workers and time.monotonic()<deadline:
            time.sleep(.005)
        self.assertFalse(pool._workers)
        self.assertEqual(pool.submit(lambda: 'restarted').result(timeout=1),'restarted')

    def test_shutdown_cancels_pending_and_failed_start_can_retry(self):
        pool = RequestThreads(max_workers=1)
        gate = threading.Event()
        first = pool.submit(lambda: gate.wait(2))
        deadline = time.monotonic() + 1
        while not first.running() and time.monotonic()<deadline:
            time.sleep(.005)
        waiting=pool.submit(lambda: self.fail('cancelled queued task ran'))
        with self.assertRaises(RuntimeError):
            pool.submit(lambda: self.fail('queue overflow ran'))
        pool.shutdown(wait=False,cancel_futures=True)
        self.assertTrue(waiting.cancelled())
        with self.assertRaises(RuntimeError):
            pool.submit(lambda: None)
        gate.set()
        pool.shutdown()
        other=RequestThreads(max_workers=1)
        self.addCleanup(other.shutdown)
        with patch('threading.Thread.start',side_effect=RuntimeError('start failed')),self.assertRaises(RuntimeError):
            other.submit(lambda: 1)
        self.assertFalse(other._pending)
        self.assertEqual(other.submit(lambda: 2).result(timeout=1),2)

    def test_submit_during_idle_retirement_never_strands_work(self):
        pool = RequestThreads(max_workers=1, idle_seconds=.002)
        self.addCleanup(pool.shutdown)
        for number in range(40):
            self.assertEqual(pool.submit(lambda n=number: n).result(timeout=1), number)
            time.sleep(.002)

    def test_cancelled_caller_drains_running_work(self):
        async def check():
            pool=RequestThreads(max_workers=1,idle_seconds=.05)
            gate = threading.Event()
            started = threading.Event()
            def task():
                started.set()
                gate.wait(2)
                return 'done'
            call = asyncio.create_task(pool.run_sync(task))
            while not started.is_set():
                await asyncio.sleep(.005)
            call.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(call.done())
            gate.set()
            with self.assertRaises(asyncio.CancelledError):
                await call
            self.assertEqual(await pool.run_sync(lambda:'next'),'next')
            pool.shutdown()
        asyncio.run(check())
