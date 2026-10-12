from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.database.mongodb import get_database


def serialize_notification(doc: dict) -> dict:
    actor = doc.get("actor")
    if not actor:
        actor = {
            "name": doc.get("sender_name", "Team member"),
            "email": doc.get("sender_email"),
            "avatar": doc.get("sender_avatar"),
        }

    return {
        "id": str(doc["_id"]),
        "type": doc.get("type", "general"),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "actor": actor,
        "workspace_id": str(doc["workspace_id"]) if doc.get("workspace_id") else None,
        "workspace_name": doc.get("workspace_name", ""),
        "invitation_id": str(doc["invitation_id"]) if doc.get("invitation_id") else None,
        "created_at": doc.get("created_at", datetime.now(timezone.utc)).isoformat()
        if isinstance(doc.get("created_at"), datetime)
        else doc.get("created_at"),
        "read_at": doc.get("read_at").isoformat()
        if isinstance(doc.get("read_at"), datetime)
        else doc.get("read_at"),
        "is_read": bool(doc.get("is_read", False)),
        "status": doc.get("status", "pending" if doc.get("invitation_id") else "active"),
    }


async def list_notifications(
    user: dict,
    tab: str = "inbox",
    page: int = 1,
    limit: int = 20,
) -> dict:
    db = get_database()
    user_id = user["_id"]

    query = {"recipient_user_id": user_id}
    if tab == "unread":
        query["is_read"] = False

    skip = max(0, (page - 1) * limit)
    cursor = (
        db.notifications.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    notifications = [serialize_notification(doc) async for doc in cursor]
    total = await db.notifications.count_documents(query)
    unread_count = await db.notifications.count_documents({
        "recipient_user_id": user_id,
        "is_read": False,
    })

    return {
        "notifications": notifications,
        "total": total,
        "unread_count": unread_count,
    }


async def get_unread_count(user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]
    count = await db.notifications.count_documents({
        "recipient_user_id": user_id,
        "is_read": False,
    })
    return {"unread_count": count}


async def mark_as_read(notification_id: str, user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]

    if not ObjectId.is_valid(notification_id):
        raise HTTPException(status_code=400, detail="Invalid notification ID")

    now = datetime.now(timezone.utc)
    result = await db.notifications.update_one(
        {"_id": ObjectId(notification_id), "recipient_user_id": user_id},
        {"$set": {"is_read": True, "read_at": now}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"message": "Notification marked as read", "is_read": True}


async def mark_all_as_read(user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]
    now = datetime.now(timezone.utc)

    await db.notifications.update_many(
        {"recipient_user_id": user_id, "is_read": False},
        {"$set": {"is_read": True, "read_at": now}},
    )

    return {"message": "All notifications marked as read"}
