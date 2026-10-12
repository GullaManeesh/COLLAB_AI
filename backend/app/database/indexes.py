from pymongo.errors import OperationFailure

from app.database.mongodb import get_database


async def _safe_create_index(collection, keys, **kwargs) -> None:
    """Creates an index, handling existing indexes and replacing conflicting options."""
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code == 85:
            # Index already exists under a different name or options
            pass
        elif exc.code == 86 and "name" in kwargs:
            # Code 86 is IndexKeySpecsConflict - drop previous version and recreate with new options
            await collection.drop_index(kwargs["name"])
            await collection.create_index(keys, **kwargs)
        else:
            raise


async def create_indexes() -> None:
    db = get_database()

    await _safe_create_index(
        db.invitations,
        [("token_hash", 1)],
        unique=True,
        sparse=True,
        name="uq_invitation_token_hash",
    )
    await _safe_create_index(
        db.users,
        [("google_sub", 1)],
        unique=True,
        name="uq_users_google_sub",
    )
    await _safe_create_index(
        db.users,
        [("username", 1)],
        unique=True,
        sparse=True,
        name="uq_users_username",
    )
    await _safe_create_index(
        db.sessions,
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="ttl_sessions_expires_at",
    )
    await _safe_create_index(
        db.sessions,
        [("token_hash", 1)],
        unique=True,
        name="uq_sessions_token_hash",
    )
    await _safe_create_index(
        db.invitations,
        [("recipient_user_id", 1), ("status", 1), ("created_at", -1)],
        name="idx_invitation_recipient_status",
    )
    await _safe_create_index(
        db.notifications,
        [("recipient_user_id", 1), ("created_at", -1)],
        name="idx_notifications_recipient_created",
    )
    await _safe_create_index(
        db.email_outbox,
        [("status", 1), ("created_at", 1)],
        name="idx_email_outbox_status_created",
    )
    await _safe_create_index(
        db.documents,
        [("workspace_id", 1), ("created_at", -1)],
        name="idx_documents_workspace_created",
    )
    await _safe_create_index(
        db.documents,
        [("uploader_id", 1), ("created_at", -1)],
        name="idx_documents_uploader_created",
    )
    await _safe_create_index(
        db.chunks,
        [("workspace_id", 1), ("document_id", 1), ("chunk_index", 1)],
        name="idx_chunks_workspace_document_index",
    )
    await _safe_create_index(
        db.chunks,
        [("document_id", 1)],
        name="idx_chunks_document",
    )
    await _safe_create_index(
        db.messages,
        [("workspace_id", 1), ("created_at", -1), ("_id", -1)],
        name="idx_messages_workspace_created",
    )