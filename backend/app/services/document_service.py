from datetime import datetime, timezone
import math

from bson import ObjectId
from fastapi import HTTPException

from app.database.mongodb import get_database
from app.services.document_processing_service import (
    chunk_text,
    extract_text,
)
from app.services.embedding_service import (
    EmbeddingModelUnavailableError,
    MODEL_ID,
    async_generate_embedding,
    async_generate_embeddings,
)


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
    file_bytes: bytes,
    user: dict,
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

    # 1. Register document in db.documents (status: processing)
    document_record = {
        "workspace_id": workspace["_id"],
        "uploader_id": uploader_id,
        "uploader_name": uploader_name,
        "uploader_email": uploader_email,
        "filename": filename.strip(),
        "content_type": content_type or "application/octet-stream",
        "size_bytes": len(file_bytes),
        "status": "processing",
        "embedding_model": MODEL_ID,
        "chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.documents.insert_one(document_record)
    document_id = result.inserted_id

    try:
        # 2. Complete text extraction
        extracted_pages = extract_text(filename, file_bytes)
        if not extracted_pages:
            raise ValueError("No extractable text was found in this document")

        # 3. Text chunking
        chunks = chunk_text(extracted_pages)
        if not chunks:
            raise ValueError("The document did not produce any valid text chunks")

        # 4. Dense local FastEmbed vectors (BAAI/bge-small-en-v1.5, 384 dims)
        chunk_texts = [c["text"] for c in chunks]
        embeddings = await async_generate_embeddings(chunk_texts)

        if len(embeddings) != len(chunks):
            raise RuntimeError("Embeddings count mismatch with chunk count")

        # 5. Build chunk records referencing document, workspace, and user collections
        chunk_documents = []
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_documents.append({
                "document_id": document_id,
                "workspace_id": workspace["_id"],
                "uploader_id": uploader_id,
                "filename": filename.strip(),
                "chunk_index": index,
                "text": chunk["text"],
                "page": chunk.get("page"),
                "start_index": chunk.get("start_index", 0),
                "embedding": embedding,
                "embedding_model": MODEL_ID,
                "created_at": now,
            })

        # 6. Bulk insert chunks in controlled batches of 100
        batch_size = 100
        for i in range(0, len(chunk_documents), batch_size):
            await db.chunks.insert_many(
                chunk_documents[i : i + batch_size],
                ordered=True,
            )

        # 7. Update document status to ready
        completed_at = datetime.now(timezone.utc)
        await db.documents.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "status": "ready",
                    "chunk_count": len(chunk_documents),
                    "updated_at": completed_at,
                }
            },
        )

        # 8. Touch workspace updated_at
        await db.workspaces.update_one(
            {"_id": workspace["_id"]},
            {"$set": {"updated_at": completed_at}},
        )

        document_record["_id"] = document_id
        document_record["status"] = "ready"
        document_record["chunk_count"] = len(chunk_documents)
        document_record["updated_at"] = completed_at
        return serialize_document(document_record)

    except Exception as exc:
        # Atomic cleanup on failure
        await db.chunks.delete_many({"document_id": document_id})
        failed_at = datetime.now(timezone.utc)

        await db.documents.update_one(
            {"_id": document_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc)[:500],
                    "updated_at": failed_at,
                }
            },
        )

        if isinstance(exc, HTTPException):
            raise

        if isinstance(exc, EmbeddingModelUnavailableError):
            raise HTTPException(
                status_code=503,
                detail=str(exc),
            ) from exc

        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        raise HTTPException(
            status_code=500,
            detail="Document processing failed",
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

    ready_documents = [
        document["_id"]
        async for document in db.documents.find(
            {
                "workspace_id": workspace["_id"],
                "status": "ready",
                "embedding_model": MODEL_ID,
            },
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
