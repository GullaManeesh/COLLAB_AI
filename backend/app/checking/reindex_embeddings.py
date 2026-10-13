"""Re-embed stored document chunks after changing the embedding model.

Run from the backend directory with:
    python -m app.checking.reindex_embeddings
"""

import asyncio
import logging
from datetime import datetime, timezone

from pymongo import UpdateOne

from app.database.mongodb import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_database,
)
from app.services.embedding_service import (
    MODEL_ID,
    generate_embeddings,
    initialize_embedding_model,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
REEMBED_BATCH_SIZE = 64


async def reindex_documents() -> tuple[int, int]:
    db = get_database()
    succeeded = 0
    failed = 0
    cursor = db.documents.find({"status": {"$in": ["ready", "reindexing"]}})

    async for document in cursor:
        document_id = document["_id"]
        chunks = [
            chunk async for chunk in db.chunks.find(
                {"document_id": document_id}
            ).sort("chunk_index", 1)
        ]
        if not chunks:
            logger.warning("Skipping document with no stored chunks document_id=%s", document_id)
            continue

        await db.documents.update_one(
            {"_id": document_id},
            {"$set": {"status": "reindexing", "updated_at": datetime.now(timezone.utc)}},
        )
        try:
            for offset in range(0, len(chunks), REEMBED_BATCH_SIZE):
                batch = chunks[offset : offset + REEMBED_BATCH_SIZE]
                vectors = generate_embeddings([chunk["text"] for chunk in batch])
                operations = [
                    UpdateOne(
                        {"_id": chunk["_id"]},
                        {"$set": {"embedding": vector, "embedding_model": MODEL_ID}},
                    )
                    for chunk, vector in zip(batch, vectors)
                ]
                if len(operations) != len(batch):
                    raise RuntimeError("Embedding count mismatch during reindex")
                await db.chunks.bulk_write(operations, ordered=True)

            await db.documents.update_one(
                {"_id": document_id},
                {"$set": {
                    "status": "ready",
                    "embedding_model": MODEL_ID,
                    "updated_at": datetime.now(timezone.utc),
                }, "$unset": {"error": ""}},
            )
            succeeded += 1
            logger.info("Reindexed document_id=%s chunks=%d", document_id, len(chunks))
        except Exception as exc:
            # Leave it out of search and eligible for a safe rerun.
            await db.documents.update_one(
                {"_id": document_id},
                {"$set": {
                    "status": "reindexing",
                    "error": f"Reindex failed: {type(exc).__name__}: {str(exc)[:400]}",
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            failed += 1
            logger.exception("Reindex failed document_id=%s", document_id)

    return succeeded, failed


async def main() -> None:
    try:
        await connect_to_mongodb()
        if not initialize_embedding_model():
            raise RuntimeError("FastEmbed model could not be initialized; no documents were reindexed")
        succeeded, failed = await reindex_documents()
        logger.info("Reindex complete succeeded=%d failed=%d", succeeded, failed)
        if failed:
            raise RuntimeError(f"{failed} document(s) remain in reindexing state; rerun after resolving errors")
    finally:
        await close_mongodb_connection()


if __name__ == "__main__":
    asyncio.run(main())
