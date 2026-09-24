"""State reset, invalid input and shutdown boundary regressions."""
import asyncio
import json
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from api_test.main import studio
from api_test.mock_engine import DeclarativeStateStore, MockApp, MockEngineError
from api_test.services.mock import (
    MockServerManager, is_port_available, validate_latency,
    validate_loopback_host, validate_port, validate_seed,
)

SPEC = {'paths': {
    '/items': {'post': {'responses': {'201': {'description': 'created'}}}},
    '/items/{id}': {'get': {'responses': {'200': {'description': 'ok'}}}},
}}


class MockStateBoundaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_response_and_item_are_rejected_without_state_change(self):
        store = DeclarativeStateStore()
        with self.assertRaises(MockEngineError) as rejected:
            await store.create_item('/items', {'name': 'x' * store.MAX_ITEM_BYTES})
        self.assertEqual(rejected.exception.code, 'RESPONSE_TOO_LARGE')
        self.assertEqual(await store.list_items('/items'), [])

        item = await store.create_item('/items', {'name': 'original'})
        with self.assertRaises(MockEngineError):
            await store.update_item('/items', item['id'], {'name': 'x' * store.MAX_ITEM_BYTES})
        self.assertEqual(await store.get_item('/items', item['id']), item)

        large_spec = {'paths': {'/large': {'get': {'responses': {'200': {'content': {
            'text/plain': {'example': 'x' * (MockApp.MAX_RESPONSE_BYTES + 1)},
        }}}}}}}
        sent = []
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            sent.append(message)
        await MockApp(large_spec)({'type': 'http', 'path': '/large', 'method': 'GET'}, receive, send)
        self.assertEqual(sent[0]['status'], 413)
        self.assertEqual(json.loads(sent[1]['body'])['code'], 'RESPONSE_TOO_LARGE')

    async def test_head_requires_get_or_head_and_never_sends_body(self):
        app = MockApp({'paths': {'/write': {'post': {'responses': {'201': {}}}}}})
        sent = []
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            sent.append(message)
        await app({'type': 'http', 'path': '/write', 'method': 'HEAD'}, receive, send)
        self.assertEqual(sent[0]['status'], 405)
        self.assertEqual(sent[1]['body'], b'')

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
    def test_nested_parent_and_project_state_isolation_over_http(self):
        spec = {'paths': {
            '/teams/{teamId}/items': {'post': {'responses': {'201': {}}}},
            '/teams/{teamId}/items/{id}': {'get': {'responses': {'200': {}, '404': {}}}},
        }}
        manager = MockServerManager()
        def call(instance, method, path, body=None):
            data = json.dumps(body).encode() if body is not None else None
            request = urllib.request.Request(instance.base_url + path, data=data, method=method)
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())
        try:
            first = manager.start_server('project-a', spec, studio=studio)
            second = manager.start_server('project-b', spec, studio=studio)
            self.assertEqual(call(first, 'POST', '/teams/A/items', {'name': 'alpha'})[1]['id'], '1')
            self.assertEqual(call(first, 'POST', '/teams/B/items', {'name': 'beta'})[1]['id'], '1')
            self.assertEqual(call(second, 'POST', '/teams/A/items', {'name': 'other project'})[1]['id'], '1')
            self.assertEqual(call(first, 'GET', '/teams/A/items/1')[1]['name'], 'alpha')
            self.assertEqual(call(first, 'GET', '/teams/B/items/1')[1]['name'], 'beta')
            self.assertEqual(call(second, 'GET', '/teams/A/items/1')[1]['name'], 'other project')
            self.assertEqual(call(first, 'GET', '/teams/C/items/1')[0], 404)
        finally:
            manager.stop_all()

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
