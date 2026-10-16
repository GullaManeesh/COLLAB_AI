import sys
import asyncio
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

    def test_model_initialization_is_reused_across_concurrent_callers(self):
        calls = 0

        class FakeModel:
            def embed(self, texts):
                return ([1.0] + [0.0] * 383 for _ in texts)

        def load_model(**kwargs):
            nonlocal calls
            calls += 1
            time.sleep(0.02)
            return FakeModel()

        embedding_service._MODEL = None
        embedding_service._MODEL_ERROR = None
        fake_fastembed = SimpleNamespace(TextEmbedding=load_model)
        with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(
                    lambda _: embedding_service.initialize_embedding_model(force=True),
                    range(8),
                ))

        self.assertTrue(all(results))
        self.assertEqual(calls, 1)


class AsyncEmbeddingServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = embedding_service._MODEL
        self.error = embedding_service._MODEL_ERROR
        self.failed_at = embedding_service._LAST_FAILURE_AT

    def tearDown(self):
        embedding_service._MODEL = self.model
        embedding_service._MODEL_ERROR = self.error
        embedding_service._LAST_FAILURE_AT = self.failed_at

    async def test_concurrent_async_inference_is_offloaded_and_serialized(self):
        state_lock = threading.Lock()
        active = 0
        max_active = 0
        calls = 0

        class FakeModel:
            def embed(self, texts):
                nonlocal active, max_active
                with state_lock:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    time.sleep(0.03)
                    return iter(([1.0] + [0.0] * 383 for _ in texts))
                finally:
                    with state_lock:
                        active -= 1

        def load_model(**kwargs):
            nonlocal calls
            calls += 1
            return FakeModel()

        embedding_service._MODEL = None
        embedding_service._MODEL_ERROR = None
        fake_fastembed = SimpleNamespace(TextEmbedding=load_model)
        with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
            vectors = await asyncio.gather(*(
                embedding_service.async_generate_embeddings([f"chunk {index}"])
                for index in range(6)
            ))

        self.assertEqual(calls, 1)
        self.assertEqual(max_active, 1)
        self.assertEqual([len(batch[0]) for batch in vectors], [384] * 6)

    async def test_async_startup_initialization_does_not_block_event_loop(self):
        started = threading.Event()
        release = threading.Event()

        def blocking_initialize(*, force=False):
            started.set()
            release.wait(timeout=2)
            return True

        with patch.object(embedding_service, "initialize_embedding_model", blocking_initialize):
            task = asyncio.create_task(embedding_service.initialize_embedding_model_async())
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            self.assertTrue(await task)


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
            patch.object(document_service, "async_generate_embeddings", new=AsyncMock(return_value=[[0.1] * 384])),
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

    async def test_retrieval_embeds_query_and_scores_stored_384_dimensional_vectors(self):
        class AsyncCursor:
            def __init__(self, items):
                self.items = items

            def sort(self, *args, **kwargs):
                return self

            def limit(self, *args, **kwargs):
                return self

            def __aiter__(self):
                async def items():
                    for item in self.items:
                        yield item
                return items()

        self.documents_collection.find = Mock(return_value=AsyncCursor([
            {"_id": self.document_id},
        ]))
        matching_embedding = [1.0] + [0.0] * 383
        self.chunks_collection.find = Mock(return_value=AsyncCursor([
            {
                "_id": ObjectId(),
                "document_id": self.document_id,
                "workspace_id": self.workspace_id,
                "filename": "notes.txt",
                "chunk_index": 0,
                "text": "Relevant retrieval text",
                "page": 1,
                "embedding": matching_embedding,
                "embedding_model": embedding_service.MODEL_ID,
            },
        ]))

        with patch.object(document_service, "async_generate_embedding", new=AsyncMock(return_value=matching_embedding)) as embed_query, patch.object(
            document_service, "verify_workspace_access", new=AsyncMock(return_value=self.workspace)
        ):
            result = await document_service.search_workspace_chunks(
                str(self.workspace_id), "relevant query", 5, self.user
            )

        embed_query.assert_awaited_once_with("relevant query")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["text"], "Relevant retrieval text")
        self.assertAlmostEqual(result["results"][0]["score"], 1.0)
        document_filter = self.documents_collection.find.call_args.args[0]
        chunk_filter = self.chunks_collection.find.call_args.args[0]
        self.assertEqual(document_filter["embedding_model"], embedding_service.MODEL_ID)
        self.assertEqual(chunk_filter["embedding_model"], embedding_service.MODEL_ID)


if __name__ == "__main__":
    unittest.main()
