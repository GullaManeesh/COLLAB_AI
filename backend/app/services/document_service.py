import asyncio
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import BinaryIO

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.services.document_processing_service import (
    iter_document_chunks,
)
from app.services.embedding_service import (
    EmbeddingModelUnavailableError,
    MODEL_ID,
    async_generate_embedding,
    async_generate_embeddings,
)
from app.services.memory_diagnostics import rss_log_value

logger = logging.getLogger(__name__)
DOCUMENT_EMBEDDING_BATCH_SIZE = 32
STALE_DOCUMENT_PROCESSING_AFTER = timedelta(minutes=30)


def _safe_filename(filename: str) -> str:
    basename = os.path.basename(filename.replace("\\", "/"))
    safe = "".join(char for char in basename if char.isprintable())
    return safe[:120] or "unnamed"


def _take_chunk_batch(iterator, batch_size: int) -> tuple[list[dict], bool]:
    batch = []
    exhausted = False
    for _ in range(batch_size):
        try:
            batch.append(next(iterator))
        except StopIteration:
            exhausted = True
            break
    return batch, exhausted


async def recover_interrupted_document_uploads() -> int:
    """Mark old processing records as retryable after an interrupted request."""
    db = get_database()
    now = datetime.now(timezone.utc)
    cutoff = now - STALE_DOCUMENT_PROCESSING_AFTER
    stale_filter = {
        "status": "processing",
        "$or": [
            {"updated_at": {"$lt": cutoff}},
            {"updated_at": {"$exists": False}},
        ],
    }
    stale_documents = [
        document async for document in db.documents.find(stale_filter, {"_id": 1, "updated_at": 1})
    ]
    recovered = 0
    for document in stale_documents:
        expected_updated_at = document.get("updated_at")
        exact_filter = {"_id": document["_id"], "status": "processing"}
        exact_filter["updated_at"] = (
            expected_updated_at if expected_updated_at is not None else {"$exists": False}
        )
        result = await db.documents.update_one(
            exact_filter,
            {
                "$set": {
                    "status": "failed",
                    "chunk_count": 0,
                    "error": "Processing was interrupted. Upload the document again to retry.",
                    "updated_at": now,
                }
            },
        )
        if result.modified_count:
            recovered += 1
            try:
                await db.chunks.delete_many({"document_id": document["_id"]})
            except Exception:
                logger.error("Interrupted document chunk cleanup failed document_id=%s", document["_id"])
    if recovered:
        logger.warning("Recovered interrupted document uploads count=%d", recovered)
    return recovered


async def monitor_interrupted_document_uploads(interval_seconds: int = 300) -> None:
    """Periodically recover stale request uploads without external queue infrastructure."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await recover_interrupted_document_uploads()
        except Exception as exc:
            logger.error(
                "Document recovery scan failed error_type=%s",
                type(exc).__name__,
            )


def _failure_details(exc: Exception, stage: str) -> tuple[str, int, str]:
    if isinstance(exc, EmbeddingModelUnavailableError):
        return (
            "embedding_unavailable",
            503,
            "The local embedding model is unavailable. Please retry the upload later.",
        )
    if isinstance(exc, PyMongoError) or stage == "persistence":
        return (
            "database_persistence",
            503,
            "The document could not be saved completely. Please retry the upload.",
        )
    if stage == "extraction_and_chunking":
        known_messages = {
            "The uploaded file is empty",
            "File exceeds the 10 MB size limit",
            "Password-protected PDFs are not supported",
            "Unsupported file type. Upload PDF, DOCX, TXT, or Markdown.",
            "No extractable text was found in this document",
        }
        safe_message = str(exc) if isinstance(exc, ValueError) and str(exc) in known_messages else (
            "Could not extract readable text from this document. Check that the file is valid and try again."
        )
        return "document_extraction", 422, safe_message
    return "document_processing", 500, "Document processing failed. Please retry the upload."


async def _mark_document_failed(db, document_id: ObjectId, safe_error: str) -> None:
    try:
        await db.chunks.delete_many({"document_id": document_id})
    except Exception:
        logger.error("Document chunk cleanup failed document_id=%s", document_id)
    try:
        await db.documents.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "status": "failed",
                    "chunk_count": 0,
                    "error": safe_error,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    except Exception:
        logger.error("Could not persist failed document status document_id=%s", document_id)


def serialize_document(document: dict) -> dict:
    """Format MongoDB document dictionary for client responses."""
    return {
        "id": str(document["_id"]),
        "workspace_id": str(document["workspace_id"]),
        "uploader_id": str(document.get("uploader_id", "")),
        "uploader_name": document.get("uploader_name"),
        "filename": document["filename"],
        "content_type": document.get("content_type", "application/octet-stream"),
        "size_bytes": document.get("size_bytes", 0),
        "status": document.get("status", "processing"),
        "chunk_count": document.get("chunk_count", 0),
        "error": document.get("error"),
        "created_at": document["created_at"],
        "updated_at": document.get("updated_at", document["created_at"]),
    }


async def verify_workspace_access(
    workspace_id: str,
    user: dict,
) -> dict:
    """Return the workspace only if the user is a member or its owner."""
    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid workspace ID",
        )

    db = get_database()
    user_id = user["_id"]

    workspace = await db.workspaces.find_one({
        "_id": ObjectId(workspace_id),
        "$or": [
            {"owner_id": user_id},
            {"members.user_id": user_id},
        ],
    })

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found or access denied",
        )

    return workspace


async def upload_document(
    workspace_id: str,
    filename: str,
    content_type: str,
    file_bytes: bytes | BinaryIO,
    user: dict,
    file_size: int | None = None,
) -> dict:
    """
    Extract text, partition into overlapping chunks, generate dense vector embeddings,
    and persist into MongoDB `documents` and `chunks` collections with relations.
    """
    db = get_database()
    workspace = await verify_workspace_access(workspace_id, user)

    if not filename or not filename.strip():
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    now = datetime.now(timezone.utc)
    uploader_id = user["_id"]
    uploader_name = user.get("name") or user.get("email") or "Unknown"
    uploader_email = user.get("email", "")
    safe_filename = _safe_filename(filename.strip())
    if file_size is None:
        if isinstance(file_bytes, bytes):
            file_size = len(file_bytes)
        else:
            file_bytes.seek(0, 2)
            file_size = file_bytes.tell()
            file_bytes.seek(0)

    # 1. Register document in db.documents (status: processing)
    document_record = {
        "workspace_id": workspace["_id"],
        "uploader_id": uploader_id,
        "uploader_name": uploader_name,
        "uploader_email": uploader_email,
        "filename": filename.strip(),
        "content_type": content_type or "application/octet-stream",
        "size_bytes": file_size,
        "status": "processing",
        "embedding_model": MODEL_ID,
        "chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.documents.insert_one(document_record)
    document_id = result.inserted_id
    started_at = time.perf_counter()
    logger.info(
        "Document upload registered document_id=%s filename=%s size_bytes=%d rss_mb=%s",
        document_id,
        safe_filename,
        file_size,
        rss_log_value(),
    )

    stage = "prepare"
    stage_started = time.perf_counter()
    extraction_seconds = 0.0
    embedding_seconds = 0.0
    persistence_seconds = 0.0
    extracted_characters = 0
    chunk_count = 0
    try:
        # Retry execution is idempotent for this document ID: stale chunks are
        # removed before a fresh pass, and only complete indexing becomes ready.
        await db.chunks.delete_many({"document_id": document_id})
        await db.documents.update_one(
            {"_id": document_id},
            {"$set": {"status": "processing", "chunk_count": 0, "error": None, "updated_at": now}},
        )

        stage = "extraction_and_chunking"
        stage_started = time.perf_counter()
        chunk_iterator = iter_document_chunks(
            filename,
            file_bytes,
            file_size=file_size,
            diagnostic_id=str(document_id),
        )
        logger.info(
            "Document extraction started document_id=%s filename=%s size_bytes=%d rss_mb=%s",
            document_id,
            safe_filename,
            file_size,
            rss_log_value(),
        )
        batch_number = 0
        exhausted = False

        while not exhausted:
            stage = "extraction_and_chunking"
            stage_started = time.perf_counter()
            extract_started = time.perf_counter()
            chunk_batch, exhausted = await asyncio.to_thread(
                _take_chunk_batch,
                chunk_iterator,
                DOCUMENT_EMBEDDING_BATCH_SIZE,
            )
            extraction_seconds += time.perf_counter() - extract_started

            if not chunk_batch:
                break

            batch_number += 1
            extracted_characters += sum(
                item.get("_extracted_characters", 0) for item in chunk_batch
            )
            chunk_texts = [item["text"] for item in chunk_batch]

            stage = "embedding"
            embedding_started = time.perf_counter()
            stage_started = embedding_started
            logger.info(
                "Document FastEmbed tokenization_inference started document_id=%s batch=%d batch_size=%d chunks_before=%d rss_mb=%s",
                document_id,
                batch_number,
                len(chunk_texts),
                chunk_count,
                rss_log_value(),
            )
            embeddings = await async_generate_embeddings(chunk_texts)
            batch_embedding_seconds = time.perf_counter() - embedding_started
            embedding_seconds += batch_embedding_seconds
            logger.info(
                "Document FastEmbed tokenization_inference completed document_id=%s batch=%d vectors=%d elapsed_seconds=%.3f rss_mb=%s",
                document_id,
                batch_number,
                len(embeddings),
                batch_embedding_seconds,
                rss_log_value(),
            )
            if len(embeddings) != len(chunk_batch):
                raise RuntimeError("Embedding count mismatch with chunk batch")

            stage = "persistence"
            stage_started = time.perf_counter()
            batch_documents = []
            for item, embedding in zip(chunk_batch, embeddings):
                batch_documents.append({
                    "document_id": document_id,
                    "workspace_id": workspace["_id"],
                    "uploader_id": uploader_id,
                    "filename": filename.strip(),
                    "chunk_index": chunk_count + len(batch_documents),
                    "text": item["text"],
                    "page": item.get("page"),
                    "start_index": item.get("start_index", 0),
                    "embedding": embedding,
                    "embedding_model": MODEL_ID,
                    "created_at": now,
                })

            persistence_started = time.perf_counter()
            logger.info(
                "Document chunk persistence started document_id=%s batch=%d batch_size=%d rss_mb=%s",
                document_id,
                batch_number,
                len(batch_documents),
                rss_log_value(),
            )
            insert_result = await db.chunks.insert_many(batch_documents, ordered=True)
            inserted_ids = getattr(insert_result, "inserted_ids", None)
            if inserted_ids is None or len(inserted_ids) != len(batch_documents):
                raise RuntimeError("MongoDB did not confirm every chunk in the batch")
            chunk_count += len(batch_documents)
            completed_at = datetime.now(timezone.utc)
            await db.documents.update_one(
                {"_id": document_id},
                {"$set": {"chunk_count": chunk_count, "updated_at": completed_at}},
            )
            persistence_seconds += time.perf_counter() - persistence_started
            logger.info(
                "Document embedding batch completed document_id=%s batch=%d chunks_processed=%d embedding_seconds=%.3f persistence_seconds=%.3f rss_mb=%s",
                document_id,
                batch_number,
                chunk_count,
                batch_embedding_seconds,
                time.perf_counter() - persistence_started,
                rss_log_value(),
            )

            del chunk_batch, chunk_texts, embeddings, batch_documents

        if chunk_count == 0:
            raise ValueError("No extractable text was found in this document")

        stage = "persistence"
        stage_started = time.perf_counter()
        stored_chunk_count = await db.chunks.count_documents({"document_id": document_id})
        if stored_chunk_count != chunk_count:
            raise RuntimeError("Stored chunk count does not match completed indexing")

        completed_at = datetime.now(timezone.utc)
        await db.documents.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "status": "ready",
                    "chunk_count": chunk_count,
                    "error": None,
                    "updated_at": completed_at,
                }
            },
        )
        await db.workspaces.update_one(
            {"_id": workspace["_id"]},
            {"$set": {"updated_at": completed_at}},
        )

        document_record["_id"] = document_id
        document_record["status"] = "ready"
        document_record["chunk_count"] = chunk_count
        document_record["error"] = None
        document_record["updated_at"] = completed_at
        logger.info(
            "Document upload completed document_id=%s filename=%s size_bytes=%d extracted_characters=%d chunks=%d batches=%d extraction_seconds=%.3f embedding_seconds=%.3f persistence_seconds=%.3f total_seconds=%.3f rss_mb=%s status=ready",
            document_id,
            safe_filename,
            file_size,
            extracted_characters,
            chunk_count,
            batch_number,
            extraction_seconds,
            embedding_seconds,
            persistence_seconds,
            time.perf_counter() - started_at,
            rss_log_value(),
        )
        return serialize_document(document_record)

    except Exception as exc:
        category, http_status, safe_error = _failure_details(exc, stage)
        logger.error(
            "Document upload failed document_id=%s filename=%s size_bytes=%d stage=%s category=%s error_type=%s extracted_characters=%d chunks=%d stage_seconds=%.3f extraction_seconds=%.3f embedding_seconds=%.3f persistence_seconds=%.3f total_seconds=%.3f rss_mb=%s status=failed",
            document_id,
            safe_filename,
            file_size,
            stage,
            category,
            type(exc).__name__,
            extracted_characters,
            chunk_count,
            time.perf_counter() - stage_started,
            extraction_seconds,
            embedding_seconds,
            persistence_seconds,
            time.perf_counter() - started_at,
            rss_log_value(),
        )
        await _mark_document_failed(db, document_id, safe_error)
        raise HTTPException(
            status_code=http_status,
            detail=safe_error,
        ) from exc


async def list_documents(
    workspace_id: str,
    user: dict,
) -> dict:
    """List all documents for an accessible workspace."""
    workspace = await verify_workspace_access(workspace_id, user)
    db = get_database()

    cursor = db.documents.find(
        {"workspace_id": workspace["_id"]}
    ).sort("created_at", -1)

    documents = [serialize_document(doc) async for doc in cursor]
    return {
        "documents": documents,
        "total": len(documents),
    }


async def get_document(
    workspace_id: str,
    document_id: str,
    user: dict,
) -> dict:
    """Retrieve metadata for a single document."""
    workspace = await verify_workspace_access(workspace_id, user)
    db = get_database()

    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")

    document = await db.documents.find_one({
        "_id": ObjectId(document_id),
        "workspace_id": workspace["_id"],
    })

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return serialize_document(document)


async def delete_document(
    workspace_id: str,
    document_id: str,
    user: dict,
) -> dict:
    """
    Delete a document and all of its associated vector chunks.
    Only the document uploader or the workspace owner is authorized to delete.
    """
    workspace = await verify_workspace_access(workspace_id, user)
    db = get_database()

    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc_oid = ObjectId(document_id)
    document = await db.documents.find_one({
        "_id": doc_oid,
        "workspace_id": workspace["_id"],
    })

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    is_workspace_owner = workspace.get("owner_id") == user["_id"]
    is_uploader = document.get("uploader_id") == user["_id"]

    if not (is_workspace_owner or is_uploader):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to delete this document",
        )

    # Delete all chunks for this document
    await db.chunks.delete_many({"document_id": doc_oid})

    # Delete document record
    await db.documents.delete_one({"_id": doc_oid})

    # Update workspace
    now = datetime.now(timezone.utc)
    await db.workspaces.update_one(
        {"_id": workspace["_id"]},
        {"$set": {"updated_at": now}},
    )

    return {
        "message": f"Document '{document['filename']}' deleted successfully",
        "document_id": document_id,
    }


async def search_workspace_chunks(
    workspace_id: str,
    query: str,
    limit: int,
    user: dict,
    max_candidates: int | None = None,
    document_id: str | None = None,
) -> dict:
    """
    Semantic search across all embedded chunks within a workspace.
    Computes cosine similarity between query embedding and stored chunk vectors.
    """
    workspace = await verify_workspace_access(workspace_id, user)
    db = get_database()

    query = query.strip()
    if not query:
        return {"query": query, "results": [], "total": 0}

    query_vector = await async_generate_embedding(query)

    ready_query = {
        "workspace_id": workspace["_id"],
        "status": "ready",
        "embedding_model": MODEL_ID,
    }
    if document_id is not None:
        if not ObjectId.is_valid(document_id):
            return {"query": query, "results": [], "total": 0}
        ready_query["_id"] = ObjectId(document_id)
    ready_documents = [
        document["_id"]
        async for document in db.documents.find(
            ready_query,
            {"_id": 1},
        )
    ]
    if not ready_documents:
        return {"query": query, "results": [], "total": 0}

    cursor = db.chunks.find(
        {
            "workspace_id": workspace["_id"],
            "document_id": {"$in": ready_documents},
            "embedding_model": MODEL_ID,
        },
        {
            "_id": 1,
            "document_id": 1,
            "workspace_id": 1,
            "filename": 1,
            "chunk_index": 1,
            "text": 1,
            "page": 1,
            "embedding": 1,
            "created_at": 1,
        },
    )
    if max_candidates is not None:
        cursor = cursor.sort("created_at", -1).limit(max(1, max_candidates))

    scored_chunks = []
    async for chunk in cursor:
        emb = chunk.get("embedding")
        if not emb or len(emb) != len(query_vector):
            continue

        # Cosine similarity on normalized vectors is dot product
        score = sum(q * c for q, c in zip(query_vector, emb))
        scored_chunks.append({
            "chunk_id": str(chunk["_id"]),
            "document_id": str(chunk["document_id"]),
            "workspace_id": str(chunk["workspace_id"]),
            "filename": chunk.get("filename", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "text": chunk.get("text", ""),
            "page": chunk.get("page"),
            "created_at": chunk.get("created_at"),
            "score": round(float(score), 4),
        })

    # Sort descending by score and pick top limit
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    results = scored_chunks[:limit]

    return {
        "query": query,
        "results": results,
        "total": len(results),
    }
