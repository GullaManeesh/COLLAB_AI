from app.config.settings import settings
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.database.mongodb import get_database
from app.services.email_service import send_email


async def invite_teammate(workspace_id: str, email: str, user: dict) -> dict:
    db = get_database()

    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")

    workspace = await db.workspaces.find_one({
        "_id": ObjectId(workspace_id),
        "owner_id": user["_id"],
    })
    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found or you are not the owner",
        )

    email = email.strip().lower()
    recipient = await db.users.find_one({"email": email})

    if recipient is None:
        raise HTTPException(
            status_code=404,
            detail="No registered CollabAI user has that email",
        )

    if recipient["_id"] == user["_id"]:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    if any(
        member.get("user_id") == recipient["_id"]
        for member in workspace.get("members", [])
    ):
        raise HTTPException(status_code=409, detail="User is already a member")

    existing = await db.invitations.find_one({
        "workspace_id": ObjectId(workspace_id),
        "recipient_user_id": recipient["_id"],
        "status": "pending",
    })
    if existing:
        raise HTTPException(status_code=409, detail="Invitation is already pending")

    now = datetime.now(timezone.utc)
    invitation = {
        "workspace_id": ObjectId(workspace_id),
        "workspace_name": workspace["name"],
        "sender_user_id": user["_id"],
        "sender_name": user.get("name") or user.get("email"),
        "sender_email": user.get("email"),
        "recipient_user_id": recipient["_id"],
        "recipient_email": email,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    result = await db.invitations.insert_one(invitation)

    await db.notifications.insert_one({
        "recipient_user_id": recipient["_id"],
        "type": "invitation",
        "title": "Workspace invitation",
        "message": f'{user.get("name") or user.get("email")} invited you to join "{workspace["name"]}".',
        "actor": {
            "name": user.get("name") or user.get("email"),
            "email": user.get("email"),
            "avatar": user.get("picture"),
        },
        "workspace_id": ObjectId(workspace_id),
        "workspace_name": workspace["name"],
        "invitation_id": result.inserted_id,
        "is_read": False,
        "status": "pending",
        "created_at": now,
    })

    frontend_base = settings.FRONTEND_URL.rstrip("/")
    workspace_url = f"{frontend_base}/w/{workspace_id}"
    login_url = f"{frontend_base}/login"

    email_subject = f'Invitation to {workspace["name"]} on CollabAI'
    email_body = (
        f'{invitation["sender_name"]} invited you to join "{invitation["workspace_name"]}".\n\n'
        f"Sign in to CollabAI to view and respond to your invitation:\n"
        f"{login_url}\n\n"
        f"Project workspace URL:\n"
        f"{workspace_url}"
    )

    # Queue email in outbox
    email_result = await db.email_outbox.insert_one({
        "to": email,
        "subject": email_subject,
        "body": email_body,
        "status": "pending",
        "created_at": now,
    })

    try:
        sent = await send_email(
            invitation["recipient_email"],
            email_subject,
            email_body,
        )
        status = "sent" if sent else "skipped_smtp_not_configured"
        await db.email_outbox.update_one(
            {"_id": email_result.inserted_id},
            {"$set": {"status": status}},
        )
    except Exception as exc:
        await db.email_outbox.update_one(
            {"_id": email_result.inserted_id},
            {"$set": {"status": "failed", "error": str(exc)[:500]}},
        )

    return {
        "message": "Invitation created",
        "invitation_id": str(result.inserted_id),
        "status": "pending",
    }


async def respond_to_invitation(
    invitation_id: str,
    user: dict,
    accept: bool,
) -> dict:
    db = get_database()

    if not ObjectId.is_valid(invitation_id):
        raise HTTPException(status_code=400, detail="Invalid invitation ID")

    invitation = await db.invitations.find_one({
        "_id": ObjectId(invitation_id),
        "recipient_user_id": user["_id"],
    })
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation["status"] != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer pending")

    now = datetime.now(timezone.utc)
    new_status = "accepted" if accept else "declined"

    # Conditional update prevents race conditions or duplicate handling
    result = await db.invitations.update_one(
        {"_id": invitation["_id"], "status": "pending"},
        {"$set": {"status": new_status, "updated_at": now}},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Invitation has already been handled")

    if accept:
        member = {
            "user_id": user["_id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "role": "member",
            "joined_at": now,
        }
        await db.workspaces.update_one(
            {"_id": invitation["workspace_id"]},
            {
                "$addToSet": {"members": member},
                "$set": {"updated_at": now},
            },
        )

    await db.notifications.update_many(
        {
            "recipient_user_id": user["_id"],
            "invitation_id": invitation["_id"],
        },
        {
            "$set": {
                "is_read": True,
                "status": new_status,
                "read_at": now,
            }
        },
    )

    return {
        "message": f"Invitation {new_status}",
        "status": new_status,
    }
