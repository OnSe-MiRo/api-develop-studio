from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from api_test.collaboration_store import CollaborationStore, RevisionConflictError, RevisionRequiredError
from react_server import StudioHandler, storage_request


class CollaborationStoreTest(unittest.TestCase):
    def store(self, root: Path) -> CollaborationStore:
        roots = {
            "projects": root / "projects",
            "cases": root / "case",
            "pipelines": root / "pipelines",
        }
        store = CollaborationStore(root / "data" / "studio.db", roots)
        store.initialize(import_existing=True)
        return store

    def test_imports_existing_json_as_first_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "case" / "member" / "users" / "get.json"
            path.parent.mkdir(parents=True)
            document = {"project": "member.json", "request": {"url": "/users/1"}, "expected": {"status": 200}}
            original_text = json.dumps(document, separators=(",", ":"))
            path.write_text(original_text, encoding="utf-8")

            stored = self.store(root).get("cases", "member/users/get.json")

            self.assertIsNotNone(stored)
            self.assertEqual(stored.revision, 1)
            self.assertEqual(stored.document, document)
            self.assertTrue(stored.document_id.startswith("doc_"))
            self.assertEqual(path.read_text(encoding="utf-8"), original_text)

    def test_saves_immutable_revisions_and_materializes_current_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            first = store.save(
                "cases",
                "member/users/get.json",
                {"project": "member.json", "request": {"url": "/users/1"}},
                actor_id="alice",
            )
            second_document = {"project": "member.json", "request": {"url": "/users/2"}}
            second = store.save(
                "cases",
                "member/users/get.json",
                second_document,
                expected_revision=first.revision,
                actor_id="bob",
            )

            self.assertEqual(second.document_id, first.document_id)
            self.assertEqual(second.revision, 2)
            self.assertEqual(
                json.loads((root / "case" / "member" / "users" / "get.json").read_text(encoding="utf-8")),
                second_document,
            )
            revisions = store.revisions("cases", "member/users/get.json")
            self.assertEqual([item["revision"] for item in revisions], [2, 1])
            self.assertEqual([item["created_by"] for item in revisions], ["bob", "alice"])

    def test_rejects_stale_revision_without_overwriting_current_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            first = store.save("pipelines", "smoke.json", {"project": "member.json", "steps": []})
            store.save(
                "pipelines",
                "smoke.json",
                {"project": "member.json", "steps": [{"name": "one"}]},
                expected_revision=first.revision,
            )

            with self.assertRaisesRegex(RevisionConflictError, "다른 사용자"):
                store.save(
                    "pipelines",
                    "smoke.json",
                    {"project": "member.json", "steps": [{"name": "stale"}]},
                    expected_revision=first.revision,
                )

            current = store.get("pipelines", "smoke.json")
            self.assertEqual(current.revision, 2)
            self.assertEqual(current.document["steps"], [{"name": "one"}])

    def test_requires_revision_when_updating_existing_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            store.save("projects", "member.json", {"name": "Member", "base_url": "https://one.test"})

            with self.assertRaisesRegex(RevisionRequiredError, "편집 기준 리비전"):
                store.save("projects", "member.json", {"name": "Member", "base_url": "https://two.test"})

            self.assertEqual(store.get("projects", "member.json").document["base_url"], "https://one.test")

    def test_saving_an_unchanged_document_does_not_query_or_create_a_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            document = {"name": "Member", "base_url": "https://one.test"}
            first = store.save("projects", "member.json", document)

            with patch.object(store, "get", side_effect=AssertionError("unchanged save should not re-query")):
                unchanged = store.save("projects", "member.json", document, expected_revision=first.revision)

            self.assertEqual(unchanged.revision, first.revision)
            self.assertEqual(unchanged.document, document)

    def test_filters_documents_by_project_and_soft_deletes_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            store.save("cases", "member/users/get.json", {"project": "member.json", "request": {}})
            store.save("cases", "order/items/get.json", {"project": "order.json", "request": {}})

            self.assertEqual(store.list_references("cases", "member.json"), ["member/users/get.json"])
            deleted = store.delete("cases", "member/users/get.json", actor_id="alice")

            self.assertIsNone(store.get("cases", "member/users/get.json"))
            self.assertEqual(store.get("cases", "member/users/get.json", include_deleted=True).document_id, deleted.document_id)
            self.assertFalse((root / "case" / "member" / "users" / "get.json").exists())

    def test_imports_external_file_change_as_next_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.store(root)
            first = store.save("projects", "member.json", {"name": "Member", "base_url": "https://one.test"})
            path = root / "projects" / "member.json"
            path.write_text(json.dumps({"name": "Member", "base_url": "https://two.test"}), encoding="utf-8")

            store.import_existing_files()

            current = store.get("projects", "member.json")
            self.assertEqual(current.document_id, first.document_id)
            self.assertEqual(current.revision, 2)
            self.assertEqual(current.document["base_url"], "https://two.test")

    def test_storage_request_keeps_metadata_out_of_runtime_document(self) -> None:
        document, revision = storage_request({"request": {}, "_storage": {"id": "doc_one", "revision": 7}})

        self.assertEqual(document, {"request": {}})
        self.assertEqual(revision, 7)

    def test_put_endpoint_returns_revision_and_reports_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = self.store(Path(directory))

            def handler_for(payload: dict[str, object]) -> tuple[StudioHandler, Mock]:
                handler = object.__new__(StudioHandler)
                handler.api_path = Mock(return_value=["api", "projects", "member.json"])
                handler.read_body = Mock(return_value=payload)
                handler.headers = {"X-Studio-Actor": "alice"}
                handler.send_json = Mock()
                return handler, handler.send_json

            first_handler, first_response = handler_for(
                {"name": "Member", "base_url": "https://one.test", "advanced": {"verify": True}}
            )
            with patch("react_server.collaboration_store", return_value=store):
                first_handler.do_PUT()
            first_payload = first_response.call_args.args[1]
            self.assertEqual(first_response.call_args.args[0], 200)
            self.assertEqual(first_payload["_storage"]["revision"], 1)

            update_handler, update_response = handler_for(
                {
                    "name": "Member",
                    "base_url": "https://two.test",
                    "advanced": {"verify": True},
                    "_storage": first_payload["_storage"],
                }
            )
            with patch("react_server.collaboration_store", return_value=store):
                update_handler.do_PUT()
            self.assertEqual(update_response.call_args.args[1]["_storage"]["revision"], 2)

            stale_handler, stale_response = handler_for(
                {
                    "name": "Member",
                    "base_url": "https://stale.test",
                    "advanced": {"verify": True},
                    "_storage": first_payload["_storage"],
                }
            )
            with patch("react_server.collaboration_store", return_value=store):
                stale_handler.do_PUT()
            self.assertEqual(stale_response.call_args.args[0], 409)
            self.assertEqual(stale_response.call_args.args[1]["currentRevision"], 2)
            self.assertEqual(store.get("projects", "member.json").document["base_url"], "https://two.test")


if __name__ == "__main__":
    unittest.main()
