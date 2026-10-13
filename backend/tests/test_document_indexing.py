import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.services import document_service, embedding_service


class EmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        self.model = embedding_service._MODEL
        self.error = embedding_service._MODEL_ERROR
        self.failed_at = embedding_service._LAST_FAILURE_AT

    def tearDown(self):
        embedding_service._MODEL = self.model
        embedding_service._MODEL_ERROR = self.error
        embedding_service._LAST_FAILURE_AT = self.failed_at

    def test_local_model_generates_normalized_384_dimensional_vectors(self):
        class FakeModel:
            def embed(self, texts):
                return ([1.0] + [0.0] * 383 for _ in texts)

        embedding_service._MODEL = FakeModel()
        embedding_service._MODEL_ERROR = None

        vectors = embedding_service.generate_embeddings(["first chunk", "second chunk"])

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 384)
        self.assertEqual(vectors[0][0], 1.0)

    def test_model_initialization_failure_is_reported_and_not_silenced(self):
        def fail_to_load(**kwargs):
            raise OSError("model host DNS unavailable")

        fake_fastembed = SimpleNamespace(TextEmbedding=fail_to_load)
        embedding_service._MODEL = None
        embedding_service._MODEL_ERROR = None

        with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
            self.assertFalse(embedding_service.initialize_embedding_model(force=True))
            with self.assertRaisesRegex(RuntimeError, "model host DNS unavailable"):
                embedding_service.generate_embedding("index this")


class DocumentIndexingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.workspace_id = ObjectId()
        self.document_id = ObjectId()
        self.workspace = {"_id": self.workspace_id}
        self.user = {"_id": ObjectId(), "name": "Uploader"}
        self.chunks_collection = SimpleNamespace(
            insert_many=AsyncMock(), delete_many=AsyncMock()
        )
        self.documents_collection = SimpleNamespace(
            insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=self.document_id)),
            update_one=AsyncMock(),
        )
        self.workspaces_collection = SimpleNamespace(update_one=AsyncMock())
        self.db = SimpleNamespace(
            documents=self.documents_collection,
            chunks=self.chunks_collection,
            workspaces=self.workspaces_collection,
        )
        self.patches = [
            patch.object(document_service, "get_database", return_value=self.db),
            patch.object(document_service, "verify_workspace_access", new=AsyncMock(return_value=self.workspace)),
            patch.object(document_service, "extract_text", return_value=[{"page": 1, "text": "text"}]),
            patch.object(document_service, "chunk_text", return_value=[{"text": "text", "page": 1}]),
            patch.object(document_service, "generate_embeddings", return_value=[[0.1] * 384]),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()

    async def test_successful_indexing_stores_chunks_and_marks_document_ready(self):
        result = await document_service.upload_document(
            str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["chunk_count"], 1)
        stored = self.chunks_collection.insert_many.await_args.args[0]
        self.assertEqual(len(stored[0]["embedding"]), 384)
        self.assertEqual(stored[0]["embedding_model"], embedding_service.MODEL_ID)
        self.assertEqual(self.documents_collection.update_one.await_args.args[1]["$set"]["status"], "ready")

    async def test_mongodb_chunk_insertion_failure_marks_document_failed(self):
        self.chunks_collection.insert_many.side_effect = PyMongoError("Mongo insert failed")

        with self.assertRaises(HTTPException) as raised:
            await document_service.upload_document(
                str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
            )

        self.assertEqual(raised.exception.status_code, 500)
        self.chunks_collection.delete_many.assert_awaited_once_with({"document_id": self.document_id})
        failed_update = self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]
        self.assertEqual(failed_update["status"], "failed")
        self.assertIn("Mongo insert failed", failed_update["error"])


if __name__ == "__main__":
    unittest.main()
