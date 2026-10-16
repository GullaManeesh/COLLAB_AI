import sys
import asyncio
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bson import ObjectId
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from pymongo.errors import PyMongoError

from app.routes import document_routes
from app.services import document_service, embedding_service


def make_text_pdf(text):
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 12 Tf 50 740 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    ).encode("ascii")
    return pdf


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
        self.persisted_chunks = []

        async def insert_chunks(chunks, ordered=True):
            self.persisted_chunks.extend(chunks)
            return SimpleNamespace(inserted_ids=[ObjectId() for _ in chunks])

        async def delete_chunks(query):
            self.persisted_chunks = [
                chunk for chunk in self.persisted_chunks
                if chunk["document_id"] != query["document_id"]
            ]

        async def count_chunks(query):
            return sum(
                chunk["document_id"] == query["document_id"]
                for chunk in self.persisted_chunks
            )

        class AsyncCursor:
            def __init__(self, items):
                self.items = items

            def __aiter__(self):
                async def items():
                    for item in self.items:
                        yield item
                return items()

        self.chunks_collection = SimpleNamespace(
            insert_many=AsyncMock(side_effect=insert_chunks),
            delete_many=AsyncMock(side_effect=delete_chunks),
            count_documents=AsyncMock(side_effect=count_chunks),
        )
        self.documents_collection = SimpleNamespace(
            insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id=self.document_id)),
            update_one=AsyncMock(),
            update_many=AsyncMock(return_value=SimpleNamespace(modified_count=0)),
            find=Mock(return_value=AsyncCursor([])),
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
            patch.object(
                document_service,
                "async_generate_embeddings",
                new=AsyncMock(side_effect=lambda texts: [[0.1] * 384 for _ in texts]),
            ),
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

    async def test_small_pdf_is_extracted_and_indexed_successfully(self):
        pdf_bytes = make_text_pdf("A small PDF with useful searchable content.")
        pdf_stream = BytesIO(pdf_bytes)
        result = await document_service.upload_document(
            str(self.workspace_id), "small.pdf", "application/pdf", pdf_stream, self.user,
            file_size=len(pdf_bytes),
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["chunk_count"], 1)
        self.assertEqual(self.persisted_chunks[0]["page"], 1)
        self.assertEqual(len(self.persisted_chunks[0]["embedding"]), 384)

    async def test_upload_route_passes_spooled_stream_without_copying_entire_pdf(self):
        from tempfile import SpooledTemporaryFile

        spool = SpooledTemporaryFile()
        spool.write(b"%PDF sample")
        spool.seek(0)
        upload = UploadFile(
            file=spool,
            size=11,
            filename="sample.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        expected = {
            "id": str(self.document_id),
            "workspace_id": str(self.workspace_id),
            "filename": "sample.pdf",
            "content_type": "application/pdf",
            "size_bytes": 11,
            "status": "ready",
            "chunk_count": 1,
            "created_at": datetime.now(timezone.utc),
        }

        with patch.object(document_routes, "upload_document", new=AsyncMock(return_value=expected)) as upload_service:
            response = await document_routes.upload_document_route(
                str(self.workspace_id), self.user, None, upload
            )

        self.assertEqual(response.status, "ready")
        self.assertIs(upload_service.await_args.kwargs["file_bytes"], spool)
        self.assertEqual(upload_service.await_args.kwargs["file_size"], 11)
        self.assertTrue(spool.closed)

    async def test_larger_pdf_is_processed_in_bounded_embedding_batches(self):
        pdf_bytes = make_text_pdf("Evidence from a large PDF page. " * 1500)
        async def embed_batch(texts):
            return [[0.1] * 384 for _ in texts]

        embedder = document_service.async_generate_embeddings
        embedder.side_effect = embed_batch

        result = await document_service.upload_document(
            str(self.workspace_id), "large.pdf", "application/pdf", pdf_bytes, self.user
        )

        self.assertEqual(result["status"], "ready")
        self.assertGreater(result["chunk_count"], document_service.DOCUMENT_EMBEDDING_BATCH_SIZE)
        embedding_batch_sizes = [len(call.args[0]) for call in embedder.await_args_list]
        self.assertGreater(len(embedding_batch_sizes), 1)
        self.assertLessEqual(max(embedding_batch_sizes), document_service.DOCUMENT_EMBEDDING_BATCH_SIZE)
        self.assertEqual(sum(embedding_batch_sizes), result["chunk_count"])
        self.assertEqual(
            [len(call.args[0]) for call in self.chunks_collection.insert_many.await_args_list],
            embedding_batch_sizes,
        )

    async def test_extraction_failure_marks_document_failed(self):
        with patch.object(
            document_service,
            "iter_document_chunks",
            side_effect=ValueError("No extractable text was found in this document"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await document_service.upload_document(
                    str(self.workspace_id), "empty.pdf", "application/pdf", b"pdf", self.user
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]["status"], "failed")
        self.assertEqual(self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]["chunk_count"], 0)

    async def test_embedding_failure_cleans_chunks_and_marks_document_failed(self):
        document_service.async_generate_embeddings.side_effect = RuntimeError("provider detail must not leak")

        with self.assertRaises(HTTPException) as raised:
            await document_service.upload_document(
                str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
            )

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(raised.exception.detail, "Document processing failed. Please retry the upload.")
        self.chunks_collection.delete_many.assert_awaited()
        failure_update = self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]
        self.assertEqual(failure_update["status"], "failed")
        self.assertEqual(failure_update["chunk_count"], 0)
        self.assertNotIn("provider detail", failure_update["error"])

    async def test_mongodb_chunk_insertion_failure_marks_document_failed(self):
        self.chunks_collection.insert_many.side_effect = PyMongoError("Mongo insert failed")

        with self.assertRaises(HTTPException) as raised:
            await document_service.upload_document(
                str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
            )

        self.assertEqual(raised.exception.status_code, 503)
        self.chunks_collection.delete_many.assert_awaited()
        failed_update = self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]
        self.assertEqual(failed_update["status"], "failed")
        self.assertIn("could not be saved completely", failed_update["error"])

    async def test_incomplete_chunk_persistence_never_marks_document_ready(self):
        self.chunks_collection.count_documents.side_effect = None
        self.chunks_collection.count_documents.return_value = 0

        with self.assertRaises(HTTPException):
            await document_service.upload_document(
                str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
            )

        failed_update = self.documents_collection.update_one.await_args_list[-1].args[1]["$set"]
        self.assertEqual(failed_update["status"], "failed")
        self.assertEqual(failed_update["chunk_count"], 0)
        self.assertNotIn("ready", [call.args[1]["$set"].get("status") for call in self.documents_collection.update_one.await_args_list])

    async def test_retry_for_same_document_id_cleans_previous_chunks_and_restarts_indices(self):
        for _ in range(2):
            result = await document_service.upload_document(
                str(self.workspace_id), "notes.txt", "text/plain", b"text", self.user
            )
            self.assertEqual(result["status"], "ready")

        self.assertEqual(self.chunks_collection.delete_many.await_count, 2)
        self.assertEqual(len(self.persisted_chunks), 1)
        self.assertEqual(self.persisted_chunks[0]["chunk_index"], 0)

    async def test_startup_recovery_marks_only_stale_processing_documents_failed(self):
        result = await document_service.recover_interrupted_document_uploads()

        self.assertEqual(result, 0)
        query = self.documents_collection.find.call_args.args[0]
        self.assertEqual(query["status"], "processing")

    async def test_startup_recovery_cleans_chunks_for_a_stale_failed_document(self):
        stale_time = datetime.now(timezone.utc) - timedelta(hours=1)
        self.documents_collection.find.return_value = self._async_cursor([
            {"_id": self.document_id, "updated_at": stale_time},
        ])
        self.documents_collection.update_one.return_value = SimpleNamespace(modified_count=1)

        recovered = await document_service.recover_interrupted_document_uploads()

        self.assertEqual(recovered, 1)
        query = self.documents_collection.update_one.await_args.args[0]
        update = self.documents_collection.update_one.await_args.args[1]
        self.assertEqual(query["status"], "processing")
        self.assertEqual(update["$set"]["status"], "failed")
        self.assertIn("Upload the document again", update["$set"]["error"])
        self.chunks_collection.delete_many.assert_awaited_with({"document_id": self.document_id})

    @staticmethod
    def _async_cursor(items):
        class Cursor:
            def __aiter__(self):
                async def iterate():
                    for item in items:
                        yield item
                return iterate()
        return Cursor()

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
