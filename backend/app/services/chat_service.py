
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.database.mongodb import get_database
from app.schemas.chat import ChatMessageResponse
from app.services.chat_connection_manager import chat_manager


def serialize_message(message: dict) -> dict:
    created_at = message["created_at"]
    return {
        "id": str(message["_id"]),
        "workspace_id": str(message["workspace_id"]),
        "sender_id": str(message["sender_id"]),
        "sender_name": message.get("sender_name") or "Workspace member",
        "sender_picture": message.get("sender_picture"),
        "content": message["content"],
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "client_message_id": message.get("client_message_id"),
        "message_type": message.get("message_type", "user"),
        "agent_type": message.get("agent_type"),
        "sources": message.get("sources", []),
    }


async def get_workspace_for_member(workspace_id: str, user: dict) -> dict:
    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")

    db = get_database()
    workspace_oid = ObjectId(workspace_id)
    user_id = user["_id"]

    workspace = await db.workspaces.find_one(
        {
            "_id": workspace_oid,
            "$or": [
                {"owner_id": user_id},
                {"members.user_id": user_id},
            ],
        }
    )

    if workspace is None:
        # Avoid disclosing whether a workspace exists to non-members.
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace


async def get_chat_history(
    workspace_id: str,
    user: dict,
    limit: int = 50,
    before: str | None = None,
) -> dict:
    db = get_database()
    await get_workspace_for_member(workspace_id, user)

    query: dict = {"workspace_id": ObjectId(workspace_id)}

    if before:
        if not ObjectId.is_valid(before):
            raise HTTPException(status_code=400, detail="Invalid message cursor")

        cursor_message = await db.messages.find_one(
            {
                "_id": ObjectId(before),
                "workspace_id": ObjectId(workspace_id),
            },
            {"created_at": 1},
        )

        if cursor_message is None:
            raise HTTPException(status_code=400, detail="Message cursor not found")

        query["$or"] = [
            {"created_at": {"$lt": cursor_message["created_at"]}},
            {
                "created_at": cursor_message["created_at"],
                "_id": {"$lt": cursor_message["_id"]},
            },
        ]

    cursor = (
        db.messages.find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit + 1)
    )

    records = [record async for record in cursor]
    has_more = len(records) > limit
    records = records[:limit]
    records.reverse()

    return {
        "messages": [
            ChatMessageResponse(**serialize_message(record))
            for record in records
        ],
        "has_more": has_more,
    }


async def save_team_message(
    workspace_id: str,
    user: dict,
    content: str,
    client_message_id: str | None = None,
    authorized_delivery: bool = False,
) -> dict:
    content = content.strip()

    if not content:
        raise ValueError("Message cannot be empty")

    if len(content) > 5000:
        raise ValueError("Message cannot exceed 5000 characters")

    await get_workspace_for_member(workspace_id, user)

    db = get_database()
    now = datetime.now(timezone.utc)

    record = {
        "workspace_id": ObjectId(workspace_id),
        "sender_id": user["_id"],
        "sender_name": user.get("name") or user.get("username") or user.get("email") or "Workspace member",
        "sender_picture": user.get("picture"),
        "content": content,
        "created_at": now,
        "client_message_id": client_message_id,
        "message_type": "user",
    }

    result = await db.messages.insert_one(record)
    record["_id"] = result.inserted_id

    message = serialize_message(record)

    # Only broadcast after MongoDB confirms the message was saved.
    event = {"type": "message", "message": message}
    if authorized_delivery:
        await chat_manager.broadcast_authorized(workspace_id, event)
    else:
        await chat_manager.broadcast(workspace_id, event)

    return message


async def save_agent_message(
    workspace_id: str,
    requester: dict,
    content: str,
    *,
    agent_type: str,
    sources: list[dict],
) -> dict:
    """Persist a server-authored message without attributing it to a user."""
    content = content.strip()
    if not content or len(content) > 5000:
        raise ValueError("Agent response must contain between 1 and 5000 characters")

    workspace = await get_workspace_for_member(workspace_id, requester)
    db = get_database()
    record = {
        "workspace_id": workspace["_id"],
        "sender_id": f"agent:{agent_type}",
        "sender_name": "Summarizer" if agent_type == "summarizer" else "CollabAI Agent",
        "sender_picture": None,
        "content": content,
        "created_at": datetime.now(timezone.utc),
        "client_message_id": None,
        "message_type": "agent",
        "agent_type": agent_type,
        "sources": sources,
    }
    result = await db.messages.insert_one(record)
    record["_id"] = result.inserted_id
    message = serialize_message(record)
    await chat_manager.broadcast_authorized(
        workspace_id,
        {"type": "message", "message": message},
    )
    return message
