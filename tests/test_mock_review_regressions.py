"""Regression tests reproducing findings R1-R8 from docs/mock-1-review.md."""
import asyncio
import json
import random
import unittest
from fastapi.testclient import TestClient
from api_test.main import app, studio
from api_test.mock_engine import (
    MockApp,
    MockEngineError,
    DeclarativeStateStore,
    synthesize_schema,
    resolve_operation_response,
)
from api_test.services.mock import MockServerInstance, validate_overrides
import jsonschema


class TestMockReviewRegressions(unittest.IsolatedAsyncioTestCase):

    async def test_unchanged_seed_and_scenario_preserve_state(self):
        instance = MockApp({'paths': {}}, seed=42)
        created = await instance.state_store.create_item('/items', {'name': 'kept'})
        instance.update_config(seed=42, scenario='default', default_latency_ms=5, overrides={})
        self.assertEqual(await instance.state_store.get_item('/items', created['id']), created)
        instance.update_config(seed=43)
        self.assertIsNone(await instance.state_store.get_item('/items', created['id']))

    def test_unsupported_schema_is_rejected_instead_of_invalid_response(self):
        for schema in (
            {'type': 'array', 'minItems': 101, 'items': {'type': 'integer'}},
            {'type': 'string', 'pattern': '^[0-9]+$'},
        ):
            with self.subTest(schema=schema), self.assertRaises(MockEngineError):
                synthesize_schema(schema, {}, random.Random(1))
        schema = {'type': 'integer', 'minimum': 1.5, 'maximum': 3.5}
        jsonschema.validate(synthesize_schema(schema, {}, random.Random(1)), schema)

    def test_override_types_are_rejected_before_execution(self):
        for override in ({'latencyMs': '10'}, {'latencyMs': True}, {'status': 200.5},
                         {'mediaType': []}, {'exampleKey': 1}, {'errorResponse': 'false'}):
            with self.subTest(override=override), self.assertRaises(studio.ApiError):
                validate_overrides({'GET /items': override}, studio)

    async def test_crud_explicit_example_uses_selected_media_without_mutation(self):
        operation = {'responses': {'200': {'description': 'OK', 'content': {
            'text/plain': {'examples': {'chosen': {'value': 'selected'}}},
        }}}}
        instance = MockApp({'paths': {'/items/{id}': {'get': operation, 'put': operation}}},
                           overrides={'/items/{id}': {'mediaType': 'text/plain', 'exampleKey': 'chosen'}})
        created = await instance.state_store.create_item('/items', {'id': '1', 'name': 'original'})
        sent = []
        async def receive():
            return {'type': 'http.request', 'body': b'{"name":"changed"}', 'more_body': False}
        async def send(message):
            sent.append(message)
        await instance({'type': 'http', 'method': 'PUT', 'path': '/items/1'}, receive, send)
        self.assertTrue(dict(sent[0]['headers'])[b'content-type'].startswith(b'text/plain'))
        self.assertEqual(sent[1]['body'], b'selected')
        self.assertEqual(await instance.state_store.get_item('/items', '1'), created)

    def test_smoke_deadline_cancels_unsubmitted_work(self):
        import threading
        import time
        from unittest.mock import patch
        from api_test.mock_smoke import run_mock_smoke
        release = threading.Event()
        finished = threading.Event()
        def stalled(*args):
            release.wait(2)
            finished.set()
            return 200, 1.0, None
        try:
            with patch('api_test.mock_smoke.send_http_request', side_effect=stalled) as request:
                start = time.monotonic()
                result = run_mock_smoke('http://127.0.0.1', total_requests=5, concurrency=1, deadline_seconds=.05)
                self.assertLess(time.monotonic() - start, 1)
                self.assertLessEqual(request.call_count, 1)
                self.assertEqual(result['failure_count'], 5)
                self.assertEqual(result['unfinished_requests'], 5)
        finally:
            release.set()
            finished.wait(2)

    async def test_r1_state_isolation_between_different_resources(self):
        """R1: State from /api/users must not leak into /api/orders."""
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Multi Resource API", "version": "1.0.0"},
            "paths": {
                "/api/users": {
                    "post": {
                        "operationId": "createUser",
                        "responses": {
                            "201": {
                                "description": "Created",
                                "content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}}}}
                            }
                        }
                    }
                },
                "/api/users/{id}": {
                    "get": {
                        "operationId": "getUser",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}}}}
                            },
                            "404": {"description": "Not Found"}
                        }
                    }
                },
                "/api/orders": {
                    "post": {
                        "operationId": "createOrder",
                        "responses": {
                            "201": {
                                "description": "Created",
                                "content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}, "total": {"type": "number"}}}}}
                            }
                        }
                    }
                },
                "/api/orders/{id}": {
                    "get": {
                        "operationId": "getOrder",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {"application/json": {"schema": {"type": "object", "properties": {"id": {"type": "string"}, "total": {"type": "number"}}}}}
                            },
                            "404": {"description": "Not Found"}
                        }
                    }
                },
            }
        }
        mock_app = MockApp(document=spec)

        async def make_request(method, path, body=None):
            messages = []
            async def send(msg):
                messages.append(msg)
            body_bytes = json.dumps(body).encode("utf-8") if body else b""
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [(b"host", b"localhost:8880")],
            }
            await mock_app(scope, receive, send)
            status = messages[0]["status"]
            resp_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            data = json.loads(resp_body.decode("utf-8")) if resp_body else None
            return status, data

        # Create a user
        status, user = await make_request("POST", "/api/users", {"name": "Alice"})
        self.assertEqual(status, 201)
        self.assertEqual(user["id"], "1")

        # GET /api/orders/1 MUST return 404 (NOT user Alice's data!)
        order_status, order_data = await make_request("GET", "/api/orders/1")
        self.assertEqual(order_status, 404, f"Expected 404 for /api/orders/1, but got {order_status}: {order_data}")

    async def test_r2_id_counter_after_deletion(self):
        """R2: Deleting an item and creating a new one must not overwrite existing items."""
        store = DeclarativeStateStore(seed=42)
        # Create item 1 and item 2
        item1 = await store.create_item("items", {"title": "First"})
        item2 = await store.create_item("items", {"title": "Second"})
        self.assertEqual(item1["id"], "1")
        self.assertEqual(item2["id"], "2")

        # Delete item 1
        deleted = await store.delete_item("items", "1")
        self.assertTrue(deleted)

        # Create item 3 -> must not overwrite item 2
        item3 = await store.create_item("items", {"title": "Third"})
        self.assertNotEqual(item3["id"], "2", "New item ID must not reuse existing item 2 ID")

        # Verify item 2 is intact
        fetched2 = await store.get_item("items", "2")
        self.assertIsNotNone(fetched2)
        self.assertEqual(fetched2["title"], "Second")

        # Verify item 3 exists
        fetched3 = await store.get_item("items", item3["id"])
        self.assertIsNotNone(fetched3)
        self.assertEqual(fetched3["title"], "Third")

    async def test_r3_crud_status_override_and_error_simulation(self):
        """R3: CRUD routes must respect status overrides and must not mutate state on error."""
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Items API", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createItem",
                        "responses": {
                            "201": {
                                "description": "Created",
                                "content": {"application/json": {"schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "status": {"type": "string", "default": "active"}
                                    },
                                    "required": ["id", "title", "status"]
                                }}}
                            },
                            "500": {
                                "description": "Server Error",
                                "content": {"application/json": {"schema": {"type": "object", "properties": {"error": {"type": "string"}}}}}
                            }
                        }
                    }
                },
                "/items/{id}": {
                    "get": {
                        "operationId": "getItem",
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {"application/json": {"schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "status": {"type": "string"}
                                    }
                                }}}
                            },
                            "503": {"description": "Service Unavailable"}
                        }
                    }
                }
            }
        }
        # App with override for GET /items/{id} returning 503
        mock_app = MockApp(document=spec, overrides={
            "/items/{id}": {"status": 503}
        })

        async def make_request(app_inst, method, path, body=None):
            messages = []
            async def send(msg):
                messages.append(msg)
            body_bytes = json.dumps(body).encode("utf-8") if body else b""
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [(b"host", b"localhost:8880")],
            }
            await app_inst(scope, receive, send)
            status = messages[0]["status"]
            resp_body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            data = json.loads(resp_body.decode("utf-8")) if resp_body else None
            return status, data

        # 1. Create item: schema defaults ("status": "active") must be populated
        status, created = await make_request(mock_app, "POST", "/items", {"title": "Widget"})
        self.assertEqual(status, 201)
        self.assertEqual(created.get("status"), "active", "POST response must merge schema defaults")

        # 2. GET /items/1 must return 503 per override (NOT 200)
        status, data = await make_request(mock_app, "GET", f"/items/{created['id']}")
        self.assertEqual(status, 503, f"Expected 503 from override, got {status}")

        # 3. POST with 500 error override must return 500 and NOT mutate state
        error_app = MockApp(document=spec, overrides={
            "/items": {"status": 500}
        })
        status, _ = await make_request(error_app, "POST", "/items", {"title": "Should Not Exist"})
        self.assertEqual(status, 500)
        # Check that state store has 0 items
        items = await error_app.state_store.list_items("/items")
        self.assertEqual(len(items), 0, "Error status must not mutate state")

    def test_r4_schema_constraints(self):
        """R4: Synthesizer must satisfy schema constraints (minItems, maximum, maxLength, non-null cycle cutoff)."""
        doc = {}
        prng = random.Random(42)

        # 1. minItems: 5
        schema_array = {"type": "array", "minItems": 5, "items": {"type": "string"}}
        arr = synthesize_schema(schema_array, doc, prng)
        self.assertGreaterEqual(len(arr), 5, f"Array length {len(arr)} < minItems 5")
        jsonschema.validate(instance=arr, schema=schema_array)

        # 2. maximum: 0
        schema_int = {"type": "integer", "maximum": 0}
        val_int = synthesize_schema(schema_int, doc, prng)
        self.assertLessEqual(val_int, 0, f"Integer {val_int} > maximum 0")
        jsonschema.validate(instance=val_int, schema=schema_int)

        # 3. maxLength: 2
        schema_str = {"type": "string", "maxLength": 2}
        val_str = synthesize_schema(schema_str, doc, prng)
        self.assertLessEqual(len(val_str), 2, f"String '{val_str}' length > maxLength 2")
        jsonschema.validate(instance=val_str, schema=schema_str)

        # 4. Circular / depth cutoff on non-null object must return non-null (e.g. {})
        schema_cycle = {
            "type": "object",
            "properties": {
                "child": {"$ref": "#/components/schemas/Node"}
            },
            "required": ["child"]
        }
        cycle_doc = {
            "components": {
                "schemas": {
                    "Node": schema_cycle
                }
            }
        }
        with self.assertRaises(MockEngineError):
            synthesize_schema(schema_cycle, cycle_doc, prng, depth=11)

    def test_r8_non_json_media_types(self):
        """R8: text/plain response must return text/plain Content-Type and raw string body, not json."""
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Text API", "version": "1.0.0"},
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "getHealth",
                        "responses": {
                            "200": {
                                "description": "Health text",
                                "content": {
                                    "text/plain": {
                                        "example": "OK healthy"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        mock_app = MockApp(document=spec)

        messages = []
        async def send(msg):
            messages.append(msg)
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"host", b"localhost:8880"), (b"accept", b"text/plain")],
        }
        asyncio.run(mock_app(scope, receive, send))

        start_msg = messages[0]
        headers_dict = dict(start_msg.get("headers", []))
        content_type = headers_dict.get(b"content-type", b"").decode("utf-8")
        self.assertTrue(content_type.startswith("text/plain"), f"Expected text/plain, got {content_type}")

        body_bytes = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        self.assertEqual(body_bytes, b"OK healthy", f"Expected b'OK healthy', got {body_bytes}")

    def test_r5_admin_api_validation(self):
        """R5: Management API must reject invalid port/seed/latency with 400 instead of 500, reject port 0, and not kill running server on failed restart."""
        client = TestClient(app)
        proj_ref = "example-api.json"

        # 1. Start server with seed="invalid" -> 400 (not 500)
        res = client.post(f"/api/projects/{proj_ref}/mock/start", json={"seed": "invalid"})
        self.assertEqual(res.status_code, 400, f"Expected 400 for invalid seed, got {res.status_code}")

        # 2. Start server with port=70000 -> 400 (not 500)
        res = client.post(f"/api/projects/{proj_ref}/mock/start", json={"port": 70000})
        self.assertEqual(res.status_code, 400, f"Expected 400 for out-of-range port, got {res.status_code}")

        # 3. Start server with port=0 -> 400
        res = client.post(f"/api/projects/{proj_ref}/mock/start", json={"port": 0})
        self.assertEqual(res.status_code, 400, f"Expected 400 for port 0, got {res.status_code}")

        # 4. Start valid server
        res = client.post(f"/api/projects/{proj_ref}/mock/start", json={"seed": 42})
        self.assertEqual(res.status_code, 200)
        orig_port = res.json()["port"]

        try:
            # 5. Config with defaultLatencyMs="invalid" -> 400 (not 500)
            res = client.post(f"/api/projects/{proj_ref}/mock/config", json={"defaultLatencyMs": "invalid"})
            self.assertEqual(res.status_code, 400, f"Expected 400 for invalid latency, got {res.status_code}")

            # 6. Attempt restart with invalid port -> 400, and previous server must STILL be running!
            res = client.post(f"/api/projects/{proj_ref}/mock/start", json={"port": 99999})
            self.assertEqual(res.status_code, 400)

            # Check status of server: still running on orig_port
            status_res = client.get(f"/api/projects/{proj_ref}/mock")
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.json()["status"], "running")
            self.assertEqual(status_res.json()["port"], orig_port)
        finally:
            client.post(f"/api/projects/{proj_ref}/mock/stop")
