"""OAS-1 raw source editing and optimistic preview/apply contract."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from http_client import HttpRequest
from api_test.contracts.documents import bundle_document, resolve
from api_test.contracts.validation import lint
from api_test.openapi_editor import _get, inspect, preview
from api_test.services import studio


def document(version="3.0.3"):
    return {
        "openapi": version, "info": {"title": "Editor", "version": "1"},
        "paths": {"/items": {"get": {"operationId": "listItems", "summary": "List", "responses": {
            "200": {"description": "OK", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}},
            "404": {"description": "Missing"}}}}},
        "components": {"schemas": {"Node": {"type": "object", "properties": {
            "name": {"type": "string"}, "next": {"$ref": "#/components/schemas/Node"}}}}},
        "x-unchanged": {"keep": True},
    }


def project(version="3.0.3", *, bundle=True):
    doc = document(version)
    source = {"docs_bundle": studio.split_openapi_bundle(doc)} if bundle else {"docs_file": {"name": "original.json", "document": doc}}
    return {"name": "Editor", "base_url": "https://example.test", "docs_url": "", **source}


class RawOpenApiEditorTests(unittest.TestCase):
    def test_split_bundle_owner_edit_keeps_all_other_bytes_and_recursive_refs(self):
        current = project()
        original = deepcopy(current)
        view = inspect(current, {"revision": 4}, studio)
        node = next(item for item in view["catalog"]["schemas"] if item["name"] == "Node")
        operation = view["catalog"]["operations"][0]
        self.assertEqual(node["refByFile"][operation["file"]], "../openapi.yaml#/components/schemas/Node")
        edited = deepcopy(_get(view["source"]["files"][node["file"]], node["pointer"]))
        edited["properties"]["name"].update(minLength=2, enum=["A", "B"], example="A")
        updated, result = preview(current, {"revision": 4}, {
            "sourceDigest": view["sourceDigest"],
            "edits": [{"file": node["file"], "path": node["pointer"], "op": "replace", "value": edited}],
        }, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["changedFiles"], [node["file"]])
        self.assertEqual([(item["method"], item["path"]) for item in result["affectedOperations"]], [("GET", "/items")])
        for filename, content in current["docs_bundle"]["files"].items():
            if filename != node["file"]:
                self.assertEqual(updated["docs_bundle"]["files"][filename], content)
        self.assertEqual(current, original)
        resolved = bundle_document(updated["docs_bundle"])
        self.assertFalse([issue for issue in lint(resolved) if issue["severity"] == "error"])
        self.assertEqual(resolve(resolved, resolved["components"]["schemas"]["Node"])["properties"]["name"]["minLength"], 2)
        self.assertEqual(resolved["x-unchanged"], {"keep": True})

    def test_inline_31_schema_siblings_security_and_multimedia_round_trip(self):
        current = project("3.1.0", bundle=False)
        view = inspect(current, {"revision": 2}, studio)
        source = view["source"]
        doc = deepcopy(source["files"][source["entrypoint"]])
        doc["components"]["securitySchemes"] = {"Bearer": {"type": "http", "scheme": "bearer"}}
        doc["security"] = [{"Bearer": []}]
        operation = doc["paths"]["/items"]["get"]
        operation["parameters"] = [{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1}}]
        operation["requestBody"] = {"required": False, "content": {"application/json": {"schema": {"type": "object"}}}}
        operation["responses"]["422"] = {"description": "Invalid", "headers": {"X-Reason": {"schema": {"type": "string"}}},
                                          "content": {"application/problem+json": {"schema": {"type": "object"}, "example": {"code": "INVALID"}}}}
        operation["security"] = []  # Explicitly disable inherited auth.
        doc["components"]["schemas"]["Node"]["properties"]["next"]["minProperties"] = 1
        updated, result = preview(current, {"revision": 2}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": source["entrypoint"], "path": "#", "op": "replace", "value": doc}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(updated["docs_file"]["document"], doc)
        self.assertEqual(updated["docs_file"]["name"], "original.json")
        self.assertEqual(current["docs_file"]["document"]["components"].get("securitySchemes"), None)

    def test_invalid_security_names_scopes_and_duplicate_ids_block_apply(self):
        current = project(bundle=False)
        view = inspect(current, {"revision": 1}, studio)
        filename = view["source"]["entrypoint"]
        edits = [{"file": filename, "path": "#/security", "op": "add", "value": [{"Missing": []}]}]
        _, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"], "edits": edits}, studio)
        self.assertFalse(result["valid"])
        self.assertIn("unknown_security_scheme", [issue["code"] for issue in result["issues"]])
        current["docs_file"]["document"]["components"]["securitySchemes"] = {
            "OAuth": {"type": "oauth2", "flows": {"clientCredentials": {"tokenUrl": "https://example.test/token", "scopes": {"read": "Read"}}}}}
        view = inspect(current, {"revision": 1}, studio)
        _, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": filename, "path": "#/security", "op": "add", "value": [{"OAuth": ["write"]}]}]}, studio)
        self.assertIn("unknown_oauth_scope", [issue["code"] for issue in result["issues"]])
        current["docs_file"]["document"]["paths"]["/other"] = deepcopy(current["docs_file"]["document"]["paths"]["/items"])
        view = inspect(current, {"revision": 1}, studio)
        _, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": filename, "path": "#/info/version", "op": "replace", "value": "2"}]}, studio)
        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["code"] in ("duplicate_operation_id", "invalid_structure") for issue in result["issues"]))

    def test_pointer_failure_alias_and_batched_atomicity(self):
        current = project(bundle=False)
        view = inspect(current, {"revision": 1}, studio)
        filename = view["source"]["entrypoint"]
        for pointer in ("#/paths/~2items", "#/paths/~1items/get/parameters/00", "#/paths/~1items/get/parameters/-1"):
            with self.subTest(pointer=pointer), self.assertRaises(studio.ApiError):
                preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
                    "edits": [{"file": filename, "path": pointer, "op": "remove"}]}, studio)
        with self.assertRaises(studio.ApiError):
            preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"], "edits": [
                {"file": filename, "path": "#/info/version", "op": "replace", "value": "2"},
                {"file": filename, "path": "#/missing", "op": "remove"}]}, studio)
        with self.assertRaises(studio.ApiError):
            preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
                "edits": [{"file": filename, "path": "#/x-%7E2", "op": "add", "value": "invalid"}]}, studio)
        self.assertEqual(current["docs_file"]["document"]["info"]["version"], "1")
        current["docs_file"]["document"]["paths"]["/items"]["get"]["parameters"] = [{"name": "q", "in": "query", "schema": {"type": "string"}}]
        view = inspect(current, {"revision": 1}, studio)
        with self.assertRaises(studio.ApiError):
            preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
                "edits": [{"file": filename, "path": "#/paths/~1items/get/parameters/00", "op": "remove"}]}, studio)
        yaml_text = """openapi: 3.0.3
info: {title: Alias, version: '1'}
paths: {}
components:
  schemas:
    First: &same {type: string}
    Second: *same
"""
        alias_project = {"name": "Alias", "base_url": "https://example.test", "docs_url": "",
                         "docs_bundle": {"entrypoint": "openapi.yaml", "files": {"openapi.yaml": yaml_text}}}
        alias_view = inspect(alias_project, {"revision": 1}, studio)
        changed, result = preview(alias_project, {"revision": 1}, {"sourceDigest": alias_view["sourceDigest"],
            "edits": [{"file": "openapi.yaml", "path": "#/components/schemas/First/type", "op": "replace", "value": "integer"}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        parsed = studio.parse_bundle_file("openapi.yaml", changed["docs_bundle"]["files"]["openapi.yaml"])
        self.assertEqual(parsed["components"]["schemas"]["First"]["type"], "integer")
        self.assertEqual(parsed["components"]["schemas"]["Second"]["type"], "string")
        self.assertEqual(alias_project["docs_bundle"]["files"]["openapi.yaml"], yaml_text)

    def test_schema_and_security_crud_with_missing_parent_maps(self):
        current = {"name": "Blank", "base_url": "https://example.test", "docs_url": "",
                   "docs_file": {"name": "blank.json", "document": {
                       "openapi": "3.0.3", "info": {"title": "Blank", "version": "1"}, "paths": {}}}}
        view = inspect(current, {"revision": 1}, studio)
        add = [
            {"file": "blank.json", "op": "add", "path": "#/components/schemas/Widget",
             "value": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string", "format": "uuid"}}}},
            {"file": "blank.json", "op": "add", "path": "#/components/securitySchemes/ApiKey",
             "value": {"type": "apiKey", "name": "X-Api-Key", "in": "header"}},
            {"file": "blank.json", "op": "add", "path": "#/security", "value": [{"ApiKey": []}]},
        ]
        created, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"], "edits": add}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual([item["name"] for item in inspect(created, {"revision": 2}, studio)["catalog"]["schemas"]], ["Widget"])
        remove = [
            {"file": "blank.json", "op": "remove", "path": "#/security"},
            {"file": "blank.json", "op": "remove", "path": "#/components/securitySchemes/ApiKey"},
            {"file": "blank.json", "op": "remove", "path": "#/components/schemas/Widget"},
        ]
        refreshed = inspect(created, {"revision": 2}, studio)
        deleted, result = preview(created, {"revision": 2}, {"sourceDigest": refreshed["sourceDigest"], "edits": remove}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(deleted["docs_file"]["document"]["components"]["schemas"], {})
        self.assertEqual(current["docs_file"]["document"].get("components"), None)

    def test_invalid_apply_returns_diagnostics_without_save_and_missing_revision_conflicts(self):
        current = project(bundle=False)
        store = Mock()
        stored = Mock(document=current, revision=4)
        stored.metadata.return_value = {"revision": 4}
        store.get.return_value = stored
        with patch("react_server.collaboration_store", return_value=store):
            request = HttpRequest()
            request.path = "/api/projects/edit.json/openapi/editor"
            request.send("GET")
            view = request.response.json()
            request.payload = {"action": "apply", "sourceDigest": view["sourceDigest"],
                               "edits": [{"file": "original.json", "op": "add", "path": "#/security", "value": [{"Missing": []}]}]}
            request.send("POST")
            self.assertEqual(request.response.status_code, 409)
            request.payload["_storage"] = {"revision": 4}
            request.send("POST")
            self.assertEqual(request.response.status_code, 400)
            self.assertFalse(request.response.json()["valid"])
            self.assertIn("unknown_security_scheme", [item["code"] for item in request.response.json()["issues"]])
            store.save.assert_not_called()

    def test_raw_yaml_import_and_source_digest(self):
        current = project(bundle=False)
        view = inspect(current, {"revision": 1}, studio)
        yaml_text = """openapi: 3.0.3
info: {title: Imported, version: '1'}
paths: {}
x-custom: {kept: true}
"""
        imported, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "source": {"kind": "bundle", "entrypoint": "spec.yaml", "files": {},
                       "rawFiles": {"spec.yaml": yaml_text}}}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(imported["docs_bundle"]["files"]["spec.yaml"], yaml_text)
        self.assertEqual(result["changedFiles"], ["original.json", "spec.yaml"])
        self.assertEqual(inspect(imported, {"revision": 2}, studio)["sourceDigest"], result["nextSourceDigest"])
        with self.assertRaises(studio.ApiError):
            preview(current, {"revision": 1}, {"sourceDigest": "0" * 64, "source": result["source"]}, studio)
        bad = deepcopy(result["source"])
        bad["files"]["spec.yaml"]["info"]["title"] = "Mismatch"
        with self.assertRaises(studio.ApiError):
            preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"], "source": bad}, studio)

    def test_shared_path_owner_preview_names_both_logical_operations(self):
        shared = {"get": {"summary": "Shared", "responses": {"200": {"description": "OK"}}}}
        root = {"openapi": "3.0.3", "info": {"title": "Shared", "version": "1"}, "paths": {
            "/one": {"$ref": "./paths/shared.yaml"}, "/two": {"$ref": "./paths/shared.yaml", "summary": "Second alias"}}}
        current = {"name": "Shared", "base_url": "https://example.test", "docs_url": "",
                   "docs_bundle": {"entrypoint": "openapi.yaml", "files": {
                       "openapi.yaml": studio.yaml_content(root), "paths/shared.yaml": studio.yaml_content(shared)}}}
        view = inspect(current, {"revision": 1}, studio)
        self.assertEqual(len(view["catalog"]["operations"]), 2)
        _, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": "paths/shared.yaml", "path": "#/get/summary", "op": "replace", "value": "Both"}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual([(item["method"], item["path"]) for item in result["affectedOperations"]],
                         [("GET", "/one"), ("GET", "/two")])

    def test_arbitrary_shared_schema_filename_marks_conservative_impact(self):
        root = document()
        root["components"]["schemas"]["Node"] = {"$ref": "./schemas/node.yaml"}
        current = {"name": "Custom", "base_url": "https://example.test", "docs_url": "",
                   "docs_bundle": {"entrypoint": "openapi.yaml", "files": {
                       "openapi.yaml": studio.yaml_content(root),
                       "schemas/node.yaml": studio.yaml_content({"type": "string"})}}}
        view = inspect(current, {"revision": 1}, studio)
        result_project, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": "schemas/node.yaml", "path": "#/type", "op": "replace", "value": "integer"}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(result["impactScope"], "conservative_shared_source")
        self.assertEqual([(x["method"], x["path"]) for x in result["affectedOperations"]], [("GET", "/items")])
        self.assertEqual(result_project["docs_bundle"]["files"]["openapi.yaml"], current["docs_bundle"]["files"]["openapi.yaml"])

    def test_external_boolean_schema_and_versioned_non_oauth_roles(self):
        root = {"openapi": "3.1.0", "info": {"title": "Boolean", "version": "1"},
                "paths": {"/x": {"get": {"operationId": "x", "summary": "X", "responses": {"200": {"description": "OK"}}}}},
                "components": {"schemas": {"Flag": {"$ref": "./flag.yaml"}},
                               "securitySchemes": {"Key": {"type": "apiKey", "name": "X-Key", "in": "header"}}},
                "security": [{"Key": ["reader"]}]}
        current = {"name": "Boolean", "base_url": "https://example.test", "docs_url": "",
                   "docs_bundle": {"entrypoint": "openapi.yaml", "files": {
                       "openapi.yaml": studio.yaml_content(root), "flag.yaml": "false\n"}}}
        view = inspect(current, {"revision": 1}, studio)
        changed, result = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": "flag.yaml", "path": "#", "op": "replace", "value": True}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertIs(studio.parse_bundle_file("flag.yaml", changed["docs_bundle"]["files"]["flag.yaml"]), True)
        root["openapi"] = "3.0.3"
        current["docs_bundle"]["files"]["openapi.yaml"] = studio.yaml_content(root)
        view = inspect(current, {"revision": 1}, studio)
        _, invalid = preview(current, {"revision": 1}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": "openapi.yaml", "path": "#/info/version", "op": "replace", "value": "2"}]}, studio)
        self.assertIn("unexpected_security_scope", [item["code"] for item in invalid["issues"]])

    def test_blank_project_gets_unsaved_draft_and_can_import_before_apply(self):
        current = {"name": "Fresh API", "base_url": "https://example.test", "docs_url": ""}
        view = inspect(current, {"revision": 3}, studio)
        self.assertEqual(view["source"]["origin"]["kind"], "draft")
        self.assertEqual(view["source"]["files"]["openapi.json"]["info"]["title"], "Fresh API")
        self.assertNotIn("docs_file", current)
        updated, result = preview(current, {"revision": 3}, {"sourceDigest": view["sourceDigest"],
            "edits": [{"file": "openapi.json", "op": "add", "path": "#/components/schemas/New",
                       "value": {"type": "string"}}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(updated["docs_file"]["document"]["components"]["schemas"]["New"], {"type": "string"})
        self.assertNotIn("docs_file", current)
        imported, result = preview(current, {"revision": 3}, {"sourceDigest": view["sourceDigest"],
            "source": {"kind": "bundle", "entrypoint": "spec.yaml", "rawFiles": {"spec.yaml":
                "openapi: 3.1.0\ninfo: {title: Imported, version: '1'}\npaths: {}\n"}}}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(imported["docs_bundle"]["entrypoint"], "spec.yaml")

    def test_url_snapshot_rechecked_and_apply_creates_local_copy(self):
        current = {"name": "Remote", "base_url": "https://example.test", "docs_url": "https://example.test/openapi.json"}
        old = document()
        new = deepcopy(old); new["info"]["version"] = "remote-changed"
        with patch.object(studio, "fetch_openapi_document", side_effect=[old, new]) as fetch:
            view = inspect(current, {"revision": 7}, studio)
            self.assertEqual(view["source"]["origin"]["kind"], "url")
            with self.assertRaises(studio.ApiError) as conflict:
                preview(current, {"revision": 7}, {"sourceDigest": view["sourceDigest"],
                    "edits": [{"file": "openapi.json", "path": "#/info/version", "op": "replace", "value": "local"}]}, studio)
            self.assertEqual(conflict.exception.status_code, 409)
            self.assertEqual(fetch.call_count, 2)
        with patch.object(studio, "fetch_openapi_document", return_value=old):
            view = inspect(current, {"revision": 7}, studio)
            updated, result = preview(current, {"revision": 7}, {"sourceDigest": view["sourceDigest"],
                "edits": [{"file": "openapi.json", "path": "#/info/version", "op": "replace", "value": "local"}]}, studio)
        self.assertTrue(result["valid"], result["issues"])
        self.assertEqual(updated["docs_url"], "")
        self.assertEqual(updated["docs_file"]["document"]["info"]["version"], "local")
        self.assertEqual(current["docs_url"], "https://example.test/openapi.json")

    def test_blank_project_http_draft_import_preview_and_one_revision_apply(self):
        current = {"name": "New API", "base_url": "https://example.test", "docs_url": ""}
        store = Mock()
        stored = Mock(document=current, revision=2)
        stored.metadata.return_value = {"revision": 2}
        store.get.return_value = stored
        store.save.return_value.metadata.return_value = {"revision": 3}
        with patch("react_server.collaboration_store", return_value=store):
            request = HttpRequest()
            request.path = "/api/projects/new.json/openapi/editor"
            request.send("GET")
            self.assertEqual(request.response.status_code, 200)
            view = request.response.json()
            self.assertEqual(view["source"]["origin"]["kind"], "draft")
            store.save.assert_not_called()
            body = {"action": "preview", "_storage": {"revision": 2}, "sourceDigest": view["sourceDigest"],
                    "source": {"kind": "bundle", "entrypoint": "spec.yaml",
                               "rawFiles": {"spec.yaml": "openapi: 3.1.0\ninfo: {title: Imported, version: '1'}\npaths: {}\n"}}}
            request.payload = body
            request.send("POST")
            self.assertEqual(request.response.status_code, 200, request.response.text)
            self.assertTrue(request.response.json()["valid"])
            store.save.assert_not_called()
            body["action"] = "apply"
            request.send("POST")
            self.assertEqual(request.response.status_code, 200, request.response.text)
            self.assertEqual(store.save.call_count, 1)
            self.assertEqual(store.save.call_args.kwargs["expected_revision"], 2)
            self.assertEqual(store.save.call_args.args[2]["docs_bundle"]["entrypoint"], "spec.yaml")
            self.assertEqual(request.response.json()["_storage"]["revision"], 3)
            self.assertNotIn("docs_bundle", current)

    def test_http_preview_no_save_apply_revision_and_digest_conflicts(self):
        current = project(bundle=False)
        store = Mock()
        stored = Mock(document=current, revision=4)
        stored.metadata.return_value = {"revision": 4}
        store.get.return_value = stored
        store.save.return_value.metadata.return_value = {"revision": 5}
        with patch("react_server.collaboration_store", return_value=store):
            request = HttpRequest()
            request.path = "/api/projects/edit.json/openapi/editor"
            request.send("GET")
            self.assertEqual(request.response.status_code, 200, request.response.text)
            view = request.response.json()
            edit = {"file": view["source"]["entrypoint"], "op": "replace", "path": "#/info/version", "value": "2"}
            for action in ("preview", "apply"):
                request.payload = {"action": action, "_storage": {"revision": 4}, "sourceDigest": view["sourceDigest"], "edits": [edit]}
                request.send("POST")
                self.assertEqual(request.response.status_code, 200, request.response.text)
                if action == "preview":
                    store.save.assert_not_called()
                else:
                    self.assertEqual(store.save.call_args.kwargs["expected_revision"], 4)
                    self.assertEqual(store.save.call_args.args[2]["docs_file"]["document"]["info"]["version"], "2")
                    self.assertEqual(request.response.json()["_storage"]["revision"], 5)
            request.payload["_storage"]["revision"] = 3
            request.send("POST")
            self.assertEqual(request.response.status_code, 409)
            request.payload["_storage"]["revision"] = 4
            request.payload["sourceDigest"] = "0" * 64
            request.send("POST")
            self.assertEqual(request.response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
