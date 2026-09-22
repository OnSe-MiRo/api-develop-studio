"""End-to-end pipeline execution against real HTTP OpenAPI Mock Server."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from api_test.cli import run_pipeline
from api_test.services.mock import MockServerManager, find_available_port, is_port_available
from api_test.mock_smoke import run_mock_smoke


FIXTURE_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Pipeline Mock Target", "version": "1.0.0"},
    "paths": {
        "/items": {
            "post": {
                "operationId": "createItem",
                "responses": {
                    "201": {
                        "description": "Item created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Item"}
                            }
                        }
                    }
                }
            },
            "get": {
                "operationId": "listItems",
                "responses": {
                    "200": {
                        "description": "List items",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Item"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "/items/{itemId}": {
            "get": {
                "operationId": "getItem",
                "responses": {
                    "200": {
                        "description": "Item details",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Item"}
                            }
                        }
                    },
                    "404": {
                        "description": "Item not found",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"}
                            }
                        }
                    }
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "string", "default": "active"}
                },
                "required": ["id", "title"]
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "code": {"type": "string"}
                }
            }
        }
    }
}


from unittest.mock import patch


class MockPipelineIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {"LOCAL_SERVER": "true", "SKIP_OWNERSHIP_VERIFICATION": "true"})
        self.env_patcher.start()
        self.manager = MockServerManager()
        self.port = find_available_port("127.0.0.1", start_port=8930)
        self.instance = self.manager.start_server(
            project_ref="pipeline-fixture.json",
            document=FIXTURE_SPEC,
            host="127.0.0.1",
            port=self.port,
            seed=42,
        )
        self.base_url = f"http://127.0.0.1:{self.port}"
        time.sleep(0.1)

    def tearDown(self):
        self.manager.stop_all()
        self.env_patcher.stop()

    def test_pipeline_crud_and_error_flow_against_mock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            projects_dir = temp_path / "projects"
            cases_dir = temp_path / "case"
            log_dir = temp_path / "logs"
            projects_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
            # Directory structure: case/{tag}/{api_name}/{case_file}.json
            item_case_dir = cases_dir / "items" / "item_api"
            item_case_dir.mkdir(parents=True, exist_ok=True)

            # Project config pointing to mock server base_url
            project_config = {
                "name": "Pipeline Mock Fixture",
                "base_url": self.base_url,
                "docs_file": {"document": FIXTURE_SPEC},
            }
            (projects_dir / "project.json").write_text(json.dumps(project_config), encoding="utf-8")

            # Setup case: POST /items, extract created id
            setup_case = {
                "name": "create_item",
                "project": "project.json",
                "request": {
                    "method": "POST",
                    "url": "/items",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"title": "Widget Alpha"}
                },
                "expected": {
                    "status": 201
                }
            }
            (item_case_dir / "create.json").write_text(json.dumps(setup_case), encoding="utf-8")

            # Get case: GET /items/{id} with runner body validation contract (expected.body + validation_modes)
            get_case = {
                "name": "get_item",
                "project": "project.json",
                "request": {
                    "method": "GET",
                    "url": "/items/${run.item_id}"
                },
                "expected": {
                    "status": 200,
                    "body": {
                        "id": "1",
                        "title": "Widget Alpha",
                        "status": "active"
                    },
                    "validation_modes": {
                        "exact_body": True
                    }
                }
            }
            (item_case_dir / "get.json").write_text(json.dumps(get_case), encoding="utf-8")

            # Error case: GET /items/non-existent-9999 expecting 404
            error_case = {
                "name": "get_item_not_found",
                "project": "project.json",
                "request": {
                    "method": "GET",
                    "url": "/items/non-existent-9999"
                },
                "expected": {
                    "status": 404
                }
            }
            (item_case_dir / "not_found.json").write_text(json.dumps(error_case), encoding="utf-8")

            # Pipeline definition
            pipeline_file = temp_path / "pipeline.json"
            pipeline_doc = {
                "name": "mock_crud_pipeline",
                "project": "project.json",
                "steps": [
                    {
                        "name": "setup_step",
                        "case": "items/item_api/create.json",
                        "phase": "setup",
                        "extract": {
                            "item_id": "body.id"
                        }
                    },
                    {
                        "name": "get_step",
                        "case": "items/item_api/get.json",
                        "phase": "test"
                    },
                    {
                        "name": "error_step",
                        "case": "items/item_api/not_found.json",
                        "phase": "test"
                    }
                ]
            }
            pipeline_file.write_text(json.dumps(pipeline_doc), encoding="utf-8")

            # Execute pipeline: must succeed
            exit_code = run_pipeline(
                pipeline_path=pipeline_file,
                case_root=cases_dir,
                timeout=5.0,
                log_dir=log_dir,
                project_root=projects_dir,
            )
            self.assertEqual(exit_code, 0, "Pipeline against mock server should pass all steps including body validation")

            # Negative verification: intentionally wrong expected body must cause pipeline to fail
            mismatched_case = copy.deepcopy(get_case)
            mismatched_case["expected"]["body"]["status"] = "mismatched_status"
            (item_case_dir / "get_mismatched.json").write_text(json.dumps(mismatched_case), encoding="utf-8")

            bad_pipeline_file = temp_path / "bad_pipeline.json"
            bad_pipeline_doc = copy.deepcopy(pipeline_doc)
            bad_pipeline_doc["steps"][1]["case"] = "items/item_api/get_mismatched.json"
            bad_pipeline_file.write_text(json.dumps(bad_pipeline_doc), encoding="utf-8")

            fail_exit_code = run_pipeline(
                pipeline_path=bad_pipeline_file,
                case_root=cases_dir,
                timeout=5.0,
                log_dir=log_dir,
                project_root=projects_dir,
            )
            self.assertNotEqual(fail_exit_code, 0, "Pipeline must fail when response body does not match expected body")

    def test_mock_concurrent_smoke_harness(self):
        # Run load smoke against the running mock server
        smoke_result = run_mock_smoke(
            base_url=self.base_url,
            total_requests=50,
            concurrency=5,
            timeout_seconds=5.0,
            endpoints=[
                ("GET", "/items", None, 200),
                ("GET", "/__mock/health", None, 200),
                ("POST", "/items", {"title": "Smoke Item"}, 201),
            ]
        )
        self.assertEqual(smoke_result["total_requests"], 50)
        self.assertEqual(smoke_result["failure_count"], 0)
        self.assertEqual(smoke_result["success_count"], 50)
        self.assertGreater(smoke_result["rps"], 10.0)
        self.assertLess(smoke_result["latency_ms"]["p95"], 200.0)
