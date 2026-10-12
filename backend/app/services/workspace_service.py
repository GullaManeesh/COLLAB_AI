from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.workspaces import (
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
)
from app.services import invitation_service


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
    if payload.initial_members:
        for invite_email in payload.initial_members:
            try:
                await invitation_service.invite_teammate(
                    str(workspace_id), str(invite_email), user
                )
            except Exception:
                # Do not fail workspace creation if an invitee is not yet registered or self
                pass

    created = await db.workspaces.find_one({"_id": workspace_id})
    return serialize_workspace(created, user_id)


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

    return {"message": "Workspace deleted successfully"}


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
