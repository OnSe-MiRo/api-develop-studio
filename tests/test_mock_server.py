"""Unit and integration tests for OpenAPI Mock Server engine and management service."""
from __future__ import annotations
import asyncio
import socket
import unittest
from fastapi.testclient import TestClient
from api_test.main import app, studio
from api_test.mock_engine import MockApp, MockEngineError, resolve_local_ref, synthesize_schema, resolve_operation_response
from api_test.services.mock import MockServerManager, validate_loopback_host, is_port_available, find_available_port
import random


SAMPLE_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Sample Mock API", "version": "1.0.0"},
    "paths": {
        "/users/me": {
            "get": {
                "operationId": "getCurrentUser",
                "responses": {
                    "200": {
                        "description": "Current user",
                        "content": {
                            "application/json": {
                                "example": {"id": "me", "name": "Current User", "email": "me@example.test"}
                            }
                        }
                    }
                }
            }
        },
        "/users/{userId}": {
            "get": {
                "operationId": "getUserById",
                "responses": {
                    "200": {
                        "description": "User by ID",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    },
                    "404": {
                        "description": "User not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        }
                    }
                }
            },
            "put": {
                "operationId": "updateUser",
                "responses": {
                    "200": {
                        "description": "User updated",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    }
                }
            },
            "delete": {
                "operationId": "deleteUser",
                "responses": {
                    "204": {
                        "description": "User deleted"
                    }
                }
            }
        },
        "/users": {
            "get": {
                "operationId": "listUsers",
                "responses": {
                    "200": {
                        "description": "List users",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            },
            "post": {
                "operationId": "createUser",
                "responses": {
                    "201": {
                        "description": "User created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        }
                    }
                }
            }
        },
        "/no-content": {
            "post": {
                "operationId": "noContentAction",
                "responses": {
                    "204": {
                        "description": "No content response"
                    }
                }
            }
        },
        "/examples-priority": {
            "get": {
                "operationId": "examplesPriority",
                "responses": {
                    "200": {
                        "description": "Priority test",
                        "content": {
                            "application/json": {
                                "examples": {
                                    "first": {"value": {"source": "named_example_first"}},
                                    "second": {"value": {"source": "named_example_second"}}
                                },
                                "example": {"source": "single_example"},
                                "schema": {
                                    "type": "object",
                                    "example": {"source": "schema_example"},
                                    "properties": {"source": {"type": "string", "default": "schema_default"}}
                                }
                            }
                        }
                    }
                }
            }
        }
    },
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string", "default": "Ada Lovelace"},
                    "email": {"type": "string", "format": "email"},
                    "age": {"type": "integer", "minimum": 20},
                    "isActive": {"type": "boolean", "default": True},
                    "createdAt": {"type": "string", "format": "date-time"}
                },
                "required": ["id", "name"]
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "code": {"type": "string"}
                }
            },
            "CyclicNode": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "next": {"$ref": "#/components/schemas/CyclicNode"}
                }
            }
        }
    }
}


class MockEngineUnitTest(unittest.TestCase):
    def setUp(self):
        self.mock_app = MockApp(SAMPLE_SPEC, seed=42)

    def test_routing_static_over_param_priority(self):
        # /users/me should match static route before /users/{userId}
        async def run_req(path, method="GET"):
            scope = {"type": "http", "method": method, "path": path}
            sent_messages = []
            async def receive():
                return {"body": b"", "more_body": False}
            async def send(msg):
                sent_messages.append(msg)
            await self.mock_app(scope, receive, send)
            status = sent_messages[0]["status"]
            body = sent_messages[1]["body"]
            return status, json.loads(body.decode("utf-8")) if body else None

        import json
        status, data = asyncio.run(run_req("/users/me"))
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], "me")
        self.assertEqual(data["name"], "Current User")

    def test_routing_unregistered_path_and_method(self):
        async def run_req(path, method="GET"):
            scope = {"type": "http", "method": method, "path": path}
            sent = []
            async def receive(): return {"body": b"", "more_body": False}
            async def send(msg): sent.append(msg)
            await self.mock_app(scope, receive, send)
            return sent[0]["status"], sent[0].get("headers", []), sent[1]["body"]

        import json
        status, headers, body = asyncio.run(run_req("/not-exists"))
        self.assertEqual(status, 404)
        self.assertIn("PATH_NOT_FOUND", body.decode("utf-8"))

        # Registered path but method not allowed
        status, headers, body = asyncio.run(run_req("/users/me", method="POST"))
        self.assertEqual(status, 405)
        self.assertTrue(any(k == b"allow" for k, v in headers))

    def test_response_priority_and_named_examples(self):
        prng = random.Random(42)
        op = SAMPLE_SPEC["paths"]["/examples-priority"]["get"]

        # 1. Default: first named example
        status, _, val = resolve_operation_response(op, SAMPLE_SPEC, prng)
        self.assertEqual(val["source"], "named_example_first")

        # 2. Specific named example key
        status, _, val = resolve_operation_response(op, SAMPLE_SPEC, prng, example_key="second")
        self.assertEqual(val["source"], "named_example_second")

        # 3. Without named examples: fallback to single example
        op_copy = copy.deepcopy(op)
        del op_copy["responses"]["200"]["content"]["application/json"]["examples"]
        status, _, val = resolve_operation_response(op_copy, SAMPLE_SPEC, prng)
        self.assertEqual(val["source"], "single_example")

        # 4. Without single example: fallback to schema example
        del op_copy["responses"]["200"]["content"]["application/json"]["example"]
        status, _, val = resolve_operation_response(op_copy, SAMPLE_SPEC, prng)
        self.assertEqual(val["source"], "schema_example")

        # 5. Without schema example: fallback to schema examples[0]
        del op_copy["responses"]["200"]["content"]["application/json"]["schema"]["example"]
        op_copy["responses"]["200"]["content"]["application/json"]["schema"]["examples"] = [{"source": "schema_examples_list"}]
        status, _, val = resolve_operation_response(op_copy, SAMPLE_SPEC, prng)
        self.assertEqual(val["source"], "schema_examples_list")

        # 6. Without schema examples[0]: fallback to schema default
        del op_copy["responses"]["200"]["content"]["application/json"]["schema"]["examples"]
        op_copy["responses"]["200"]["content"]["application/json"]["schema"]["default"] = {"source": "schema_default"}
        status, _, val = resolve_operation_response(op_copy, SAMPLE_SPEC, prng)
        self.assertEqual(val["source"], "schema_default")

    def test_deterministic_schema_synthesis(self):
        prng1 = random.Random(123)
        prng2 = random.Random(123)
        schema = SAMPLE_SPEC["components"]["schemas"]["User"]
        res1 = synthesize_schema(schema, SAMPLE_SPEC, prng1)
        res2 = synthesize_schema(schema, SAMPLE_SPEC, prng2)
        self.assertEqual(res1, res2)
        self.assertEqual(res1["name"], "Ada Lovelace")
        self.assertEqual(res1["email"], "user@example.test")
        self.assertEqual(res1["age"], 20)
        self.assertEqual(res1["isActive"], True)
        self.assertEqual(res1["createdAt"], "2026-09-21T00:00:00Z")

    def test_external_reference_forbidden(self):
        schema = {"$ref": "https://attacker.test/schema.json"}
        with self.assertRaises(MockEngineError) as ctx:
            synthesize_schema(schema, SAMPLE_SPEC, random.Random(42))
        self.assertEqual(ctx.exception.code, "FORBIDDEN_REFERENCE")

    def test_circular_reference_does_not_infinite_loop(self):
        schema = SAMPLE_SPEC["components"]["schemas"]["CyclicNode"]
        # Recursive synthesis is explicitly unsupported; never emit invalid null/{}.
        with self.assertRaises(MockEngineError):
            synthesize_schema(schema, SAMPLE_SPEC, random.Random(42))

    def test_no_content_responses_have_empty_body(self):
        async def run_req(path, method="POST"):
            scope = {"type": "http", "method": method, "path": path}
            sent = []
            async def receive(): return {"body": b"", "more_body": False}
            async def send(msg): sent.append(msg)
            await self.mock_app(scope, receive, send)
            return sent[0]["status"], sent[1]["body"]

        status, body = asyncio.run(run_req("/no-content"))
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")

    def test_declarative_crud_state_machine_flow(self):
        import json
        async def call(path, method="GET", payload=None):
            body_bytes = json.dumps(payload).encode("utf-8") if payload else b""
            scope = {"type": "http", "method": method, "path": path}
            sent = []
            async def receive(): return {"body": body_bytes, "more_body": False}
            async def send(msg): sent.append(msg)
            await self.mock_app(scope, receive, send)
            status = sent[0]["status"]
            resp_body = sent[1]["body"]
            return status, json.loads(resp_body.decode("utf-8")) if resp_body else None

        # 1. Create item via POST /users
        status, user1 = asyncio.run(call("/users", "POST", {"name": "Grace Hopper", "email": "grace@navy.mil"}))
        self.assertEqual(status, 201)
        self.assertEqual(user1["name"], "Grace Hopper")
        item_id = user1["id"]
        self.assertTrue(item_id)

        # 2. Read item via GET /users/{id}
        status, fetched = asyncio.run(call(f"/users/{item_id}", "GET"))
        self.assertEqual(status, 200)
        self.assertEqual(fetched["id"], item_id)
        self.assertEqual(fetched["name"], "Grace Hopper")

        # 3. Read non-existent item returns 404
        status, err = asyncio.run(call("/users/non-existent-999", "GET"))
        self.assertEqual(status, 404)

        # 4. Update item via PUT /users/{id}
        status, updated = asyncio.run(call(f"/users/{item_id}", "PUT", {"name": "Rear Admiral Grace Hopper"}))
        self.assertEqual(status, 200)
        self.assertEqual(updated["name"], "Rear Admiral Grace Hopper")

        # 5. Delete item via DELETE /users/{id}
        status, _ = asyncio.run(call(f"/users/{item_id}", "DELETE"))
        self.assertEqual(status, 204)

        # 6. Read after delete returns 404
        status, _ = asyncio.run(call(f"/users/{item_id}", "GET"))
        self.assertEqual(status, 404)

        # 7. Reset restores clean state
        asyncio.run(call("/users", "POST", {"name": "Test User"}))
        asyncio.run(self.mock_app.state_store.reset())
        items = asyncio.run(self.mock_app.state_store.list_items("users"))
        self.assertEqual(len(items), 0)


class MockServerManagementTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.manager = MockServerManager()

    def tearDown(self):
        self.manager.stop_all()

    def test_loopback_policy_enforcement(self):
        # Loopback hosts allowed
        self.assertEqual(validate_loopback_host("127.0.0.1", studio), "127.0.0.1")
        self.assertEqual(validate_loopback_host("::1", studio), "::1")
        self.assertEqual(validate_loopback_host("localhost", studio), "localhost")

        # Wildcard / public IPs rejected
        with self.assertRaises(studio.ApiError):
            validate_loopback_host("0.0.0.0", studio)
        with self.assertRaises(studio.ApiError):
            validate_loopback_host("192.168.1.100", studio)
        with self.assertRaises(studio.ApiError):
            validate_loopback_host("*", studio)

    def test_real_mock_server_http_lifecycle(self):
        import urllib.request
        port = find_available_port("127.0.0.1", start_port=8910)
        instance = self.manager.start_server(
            project_ref="test-proj",
            document=SAMPLE_SPEC,
            host="127.0.0.1",
            port=port,
            seed=42,
            studio=studio,
        )
        self.assertIsNotNone(instance)
        url = f"http://127.0.0.1:{port}"

        # Real HTTP GET /__mock/health
        with urllib.request.urlopen(f"{url}/__mock/health", timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)

        # Real HTTP GET /users/me
        with urllib.request.urlopen(f"{url}/users/me", timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], "me")

        # Stop server
        stopped = self.manager.stop_server("test-proj")
        self.assertTrue(stopped)

        # Verify port released (allow socket to close)
        port_released = False
        for _ in range(20):
            if is_port_available("127.0.0.1", port):
                port_released = True
                break
            time.sleep(0.1)
        self.assertTrue(port_released, f"Port {port} was not released in time")

    def test_management_api_endpoints(self):
        # 1. Get status for example-api.json
        res = self.client.get("/api/projects/example-api.json/mock")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "stopped")

        # 2. Start mock server
        port = find_available_port("127.0.0.1", start_port=8920)
        res = self.client.post("/api/projects/example-api.json/mock/start", json={"port": port, "seed": 100})
        self.assertEqual(res.status_code, 200)
        started_data = res.json()
        self.assertEqual(started_data["status"], "running")
        self.assertEqual(started_data["port"], port)
        self.assertEqual(started_data["seed"], 100)

        # 3. Get status while running
        res = self.client.get("/api/projects/example-api.json/mock")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "running")

        # 4. Update config
        res = self.client.post("/api/projects/example-api.json/mock/config", json={"scenario": "error_simulation", "defaultLatencyMs": 50})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["scenario"], "error_simulation")
        self.assertEqual(res.json()["defaultLatencyMs"], 50)

        # 5. Reset server
        res = self.client.post("/api/projects/example-api.json/mock/reset")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "reset")

        # 6. Stop server
        res = self.client.post("/api/projects/example-api.json/mock/stop")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "stopped")

        # 7. Get status after stop
        res = self.client.get("/api/projects/example-api.json/mock")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "stopped")


import json
import time
import copy
