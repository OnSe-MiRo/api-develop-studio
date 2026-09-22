"""State reset, invalid input and shutdown boundary regressions."""
import asyncio
import json
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from api_test.main import studio
from api_test.mock_engine import MockApp
from api_test.services.mock import (
    MockServerManager, is_port_available, validate_latency,
    validate_loopback_host, validate_port, validate_seed,
)

SPEC = {'paths': {
    '/items': {'post': {'responses': {'201': {'description': 'created'}}}},
    '/items/{id}': {'get': {'responses': {'200': {'description': 'ok'}}}},
}}


class MockStateBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_reset_and_seed_change_reject_pending_mutation(self):
        for action in ('reset', 'seed'):
            with self.subTest(action=action):
                app = MockApp(SPEC)
                entered, release = asyncio.Event(), asyncio.Event()
                sent = []
                async def receive():
                    entered.set()
                    await release.wait()
                    return {'type': 'http.request', 'body': b'{"name":"old"}', 'more_body': False}
                async def send(message):
                    sent.append(message)
                pending = asyncio.create_task(app({'type': 'http', 'path': '/items', 'method': 'POST'}, receive, send))
                await entered.wait()
                if action == 'reset':
                    await app.reset_state()
                else:
                    app.update_config(seed=43)
                release.set()
                await pending
                self.assertEqual(sent[0]['status'], 409)
                self.assertEqual(await app.state_store.list_items('/items'), [])

    async def test_invalid_crud_body_and_disconnect_do_not_mutate(self):
        app = MockApp(SPEC)
        for body in (b'[1]', b'null', b'{broken'):
            sent = []
            async def receive():
                return {'type': 'http.request', 'body': body, 'more_body': False}
            async def send(message):
                sent.append(message)
            await app({'type': 'http', 'path': '/items', 'method': 'POST'}, receive, send)
            self.assertEqual(sent[0]['status'], 400)
        sent = []
        async def disconnected():
            return {'type': 'http.disconnect'}
        async def send(message):
            sent.append(message)
        await app({'type': 'http', 'path': '/items', 'method': 'POST'}, disconnected, send)
        self.assertEqual(sent, [])
        self.assertEqual(await app.state_store.list_items('/items'), [])


class MockServerBoundaryTest(unittest.TestCase):
    def test_integer_inputs_reject_coercion(self):
        for validate in (validate_port, validate_seed, validate_latency):
            for value in (True, 1.5, '10', float('inf')):
                with self.subTest(validator=validate.__name__, value=value), self.assertRaises(studio.ApiError):
                    validate(value, studio)
        with self.assertRaises(studio.ApiError):
            validate_loopback_host(123, studio)

    def test_stop_during_latency_closes_loop_thread_and_socket(self):
        manager = MockServerManager()
        instance = manager.start_server('shutdown-fixture', SPEC, default_latency_ms=5000, studio=studio)
        def request():
            try:
                with urllib.request.urlopen(instance.base_url + '/items/1', timeout=8) as response:
                    return response.status
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                return None
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(request)
                deadline = time.monotonic() + 2
                while instance.mock_app.request_count == 0 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreater(instance.mock_app.request_count, 0)
                start = time.monotonic()
                manager.stop_server('shutdown-fixture')
                self.assertLess(time.monotonic() - start, 4)
                future.result(timeout=2)
            self.assertFalse(instance.thread.is_alive())
            self.assertTrue(instance.loop.is_closed())
            self.assertTrue(is_port_available(instance.host, instance.port))
        finally:
            manager.stop_all()
