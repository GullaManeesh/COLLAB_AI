from datetime import datetime, timezone
import logging

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.workspaces import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
)
from app.services import invitation_service

logger = logging.getLogger(__name__)


def serialize_workspace(workspace: dict, user_id: ObjectId) -> dict:
    members = workspace.get("members", [])
    is_owner = workspace.get("owner_id") == user_id

    return {
        "id": str(workspace["_id"]),
        "name": workspace["name"],
        "description": workspace.get("description", ""),
        "owner_id": str(workspace["owner_id"]),
        "member_count": len(members),
        "created_at": workspace["created_at"],
        "updated_at": workspace.get("updated_at", workspace["created_at"]),
        "role": "owner" if is_owner else "member",
    }


async def create_workspace(payload: CreateWorkspaceRequest, user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]
    now = datetime.now(timezone.utc)

    workspace = {
        "name": payload.name,
        "description": payload.description,
        "owner_id": user_id,
        "members": [
            {
                "user_id": user_id,
                "email": user.get("email"),
                "name": user.get("name"),
                "role": "owner",
                "joined_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }

    inserted = await db.workspaces.insert_one(workspace)
    workspace_id = inserted.inserted_id

    try:
        await db.channels.insert_many([
            {
                "workspace_id": workspace_id,
                "type": "team_chat",
                "name": "general",
                "created_at": now,
            },
            {
                "workspace_id": workspace_id,
                "type": "copilot",
                "name": "Project Copilot",
                "created_at": now,
            },
        ])
    except PyMongoError:
        await db.workspaces.delete_one({"_id": workspace_id})
        raise

    # If initial members (invitees) were specified, dispatch invitations
    invitation_results = []
    if payload.initial_members:
        for invite_email in payload.initial_members:
            try:
                outcome = await invitation_service.invite_teammate(
                    str(workspace_id), str(invite_email), user
                )
                invitation_results.append({"email": str(invite_email), **outcome})
            except HTTPException as exc:
                # Invitations are independent of workspace creation, but never hide their outcome.
                invitation_results.append({"email": str(invite_email), "status": "not_created", "detail": exc.detail})
            except Exception:
                logger.exception("Invitation processing failed workspace_id=%s", workspace_id)
                invitation_results.append({"email": str(invite_email), "status": "not_created", "detail": "Invitation processing failed"})

    created = await db.workspaces.find_one({"_id": workspace_id})
    response = serialize_workspace(created, user_id)
    response["invitation_results"] = invitation_results
    return response


async def list_workspaces(user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]

    cursor = db.workspaces.find({
        "$or": [
            {"owner_id": user_id},
            {"members.user_id": user_id},
        ]
    }).sort("updated_at", -1)

    items = [
        serialize_workspace(item, user_id)
        async for item in cursor
    ]
    return {"workspaces": items, "total": len(items)}


async def get_workspace_details(workspace_id: str, user: dict) -> dict:
    db = get_database()
    user_id = user["_id"]

    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")

    workspace = await db.workspaces.find_one({
        "_id": ObjectId(workspace_id),
        "$or": [
            {"owner_id": user_id},
            {"members.user_id": user_id},
        ],
    })

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    member_responses = []
    for member in workspace.get("members", []):
        member_user_id = member.get("user_id")
        member_user = await db.users.find_one({"_id": member_user_id}) if member_user_id else None
        member_responses.append({
            "user_id": str(member_user_id),
            "email": (member_user or {}).get("email", member.get("email")),
            "name": (member_user or {}).get("name", member.get("name")),
            "picture": (member_user or {}).get("picture"),
            "username": (member_user or {}).get("username"),
            "role": member.get("role", "member"),
            "joined_at": member.get("joined_at"),
        })

    channels = []
    async for channel in db.channels.find({"workspace_id": ObjectId(workspace_id)}):
        channels.append({
            "id": str(channel["_id"]),
            "name": channel.get("name", ""),
            "type": channel.get("type", "team_chat"),
            "created_at": channel.get("created_at"),
        })

    result = serialize_workspace(workspace, user_id)
    result["members"] = member_responses
    result["channels"] = channels
    return result


async def update_workspace(
    workspace_id: str,
    payload: UpdateWorkspaceRequest,
    user: dict,
) -> dict:
    db = get_database()

    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if any(value is None for value in updates.values()):
        raise HTTPException(status_code=400, detail="Updated fields cannot be null")

    updates["updated_at"] = datetime.now(timezone.utc)

    result = await db.workspaces.update_one(
        {"_id": ObjectId(workspace_id), "owner_id": user["_id"]},
        {"$set": updates},
    )

    if result.matched_count == 0:
        exists = await db.workspaces.find_one({"_id": ObjectId(workspace_id)})
        if exists is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        raise HTTPException(status_code=403, detail="Only the workspace owner can edit it")

    workspace = await db.workspaces.find_one({"_id": ObjectId(workspace_id)})
    now = datetime.now(timezone.utc)
    event_recipients = {
        member.get("user_id") for member in workspace.get("members", [])
        if member.get("user_id") and member.get("user_id") != user["_id"]
    }
    if event_recipients:
        actor = user.get("name") or user.get("email") or "A workspace owner"
        events = [{
            "recipient_user_id": recipient_id,
            "type": "workspace_event",
            "event_type": "workspace.updated",
            "title": "Workspace updated",
            "message": f'{actor} updated "{workspace["name"]}".',
            "action_text": "updated",
            "actor": {"name": actor, "email": user.get("email"), "avatar": user.get("picture")},
            "workspace_id": ObjectId(workspace_id),
            "workspace_name": workspace["name"],
            "is_read": False,
            "created_at": now,
        } for recipient_id in event_recipients]
        try:
            await db.notifications.insert_many(events)
        except Exception:
            logger.exception("Workspace updated but notifications could not be recorded workspace_id=%s", workspace_id)
    return serialize_workspace(workspace, user["_id"])


async def delete_workspace(workspace_id: str, user: dict) -> dict:
    db = get_database()

    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")

    workspace = await db.workspaces.find_one({"_id": ObjectId(workspace_id)})
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the workspace owner can delete it")

    oid = ObjectId(workspace_id)

    await db.workspaces.delete_one({"_id": oid})
    await db.channels.delete_many({"workspace_id": oid})
    await db.messages.delete_many({"workspace_id": oid})
    await db.documents.delete_many({"workspace_id": oid})
    await db.invitations.delete_many({"workspace_id": oid})
    await db.notifications.delete_many({"workspace_id": oid})

    event_recipients = {
        member.get("user_id") for member in workspace.get("members", [])
        if member.get("user_id") and member.get("user_id") != user["_id"]
    }
    if event_recipients:
        now = datetime.now(timezone.utc)
        actor = user.get("name") or user.get("email") or "A workspace owner"
        events = [{
            "recipient_user_id": recipient_id,
            "type": "workspace_event",
            "event_type": "workspace.deleted",
            "title": "Workspace deleted",
            "message": f'{actor} deleted "{workspace["name"]}".',
            "action_text": "deleted",
            "actor": {"name": actor, "email": user.get("email"), "avatar": user.get("picture")},
            "workspace_id": oid,
            "workspace_name": workspace["name"],
            "is_read": False,
            "created_at": now,
        } for recipient_id in event_recipients]
        try:
            await db.notifications.insert_many(events)
        except Exception:
            logger.exception("Workspace deleted but notifications could not be recorded workspace_id=%s", workspace_id)

    return {"message": "Workspace deleted successfully"}


async def remove_workspace_member(workspace_id: str, member_user_id: str, user: dict) -> dict:
    db = get_database()
    if not ObjectId.is_valid(workspace_id) or not ObjectId.is_valid(member_user_id):
        raise HTTPException(status_code=400, detail="Invalid workspace or member ID")
    workspace_oid = ObjectId(workspace_id)
    member_oid = ObjectId(member_user_id)
    workspace = await db.workspaces.find_one({"_id": workspace_oid})
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if workspace.get("owner_id") != user["_id"]:
        raise HTTPException(status_code=403, detail="Only the workspace owner can remove members")
    if member_oid == workspace.get("owner_id"):
        raise HTTPException(status_code=400, detail="The workspace owner cannot be removed")
    member = next((item for item in workspace.get("members", []) if item.get("user_id") == member_oid), None)
    result = await db.workspaces.update_one(
        {"_id": workspace_oid, "owner_id": user["_id"]},
        {"$pull": {"members": {"user_id": member_oid}}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if member:
        now = datetime.now(timezone.utc)
        actor = user.get("name") or user.get("email") or "A workspace owner"
        try:
            await db.notifications.insert_one({
            "recipient_user_id": member_oid,
            "type": "workspace_event",
            "event_type": "workspace.member_removed",
            "title": "Workspace access removed",
            "message": f'{actor} removed you from "{workspace["name"]}".',
            "action_text": "removed you from",
            "actor": {"name": actor, "email": user.get("email"), "avatar": user.get("picture")},
            "workspace_id": workspace_oid,
            "workspace_name": workspace["name"],
            "is_read": False,
            "created_at": now,
            })
        except Exception:
            logger.exception("Member removed but notification could not be recorded workspace_id=%s", workspace_id)
    return {"message": "Workspace member removed"}


async def search_teammates(query: str, user: dict) -> list[dict]:
    db = get_database()
    query = query.strip()

    if len(query) < 2:
        return []

    # Only suggest registered users. Never expose sensitive fields.
    regex = {"$regex": query, "$options": "i"}
    cursor = db.users.find(
        {
            "$and": [
                {"_id": {"$ne": user["_id"]}},
                {
                    "$or": [
                        {"email": regex},
                        {"name": regex},
                        {"username": regex},
                    ]
                },
            ]
        },
        {"email": 1, "name": 1, "picture": 1, "username": 1},
    ).limit(10)

    results = []
    async for item in cursor:
        results.append({
            "user_id": str(item["_id"]),
            "email": item["email"],
            "name": item.get("name"),
            "picture": item.get("picture"),
            "username": item.get("username"),
        })
    return results
