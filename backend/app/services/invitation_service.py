from app.config.settings import settings
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.services.email_service import send_email
import logging

logger = logging.getLogger(__name__)


async def _deliver_email_outbox(db, outbox: dict) -> str:
    """Claim one pending/failed outbox row and perform a single provider attempt."""
    now = datetime.now(timezone.utc)
    claim = await db.email_outbox.update_one(
        {"_id": outbox["_id"], "status": {"$in": ["pending", "failed"]}},
        {"$set": {"status": "sending", "last_attempt_at": now}, "$inc": {"attempts": 1}},
    )
    if getattr(claim, "modified_count", 0) != 1:
        return "sending"

    try:
        delivery = await send_email(
            outbox["to"], outbox["subject"], outbox["body"],
            idempotency_key=str(outbox["_id"]),
        )
    except Exception as exc:
        safe_message = str(exc)
        for secret in (settings.SMTP_PASSWORD, settings.RESEND_API_KEY):
            if secret:
                safe_message = safe_message.replace(secret, "[redacted]")
        safe_error = f"{type(exc).__name__}: {safe_message[:400]}"
        logger.error(
            "Invitation email failed invitation_id=%s recipient=%s error=%s",
            outbox.get("invitation_id"), outbox.get("to"), safe_error,
        )
        await db.email_outbox.update_one(
            {"_id": outbox["_id"], "status": "sending"},
            {"$set": {"status": "failed", "error": safe_error}},
        )
        return "failed"

    try:
        await db.email_outbox.update_one(
            {"_id": outbox["_id"], "status": "sending"},
            {
                "$set": {
                    "status": delivery["status"],
                    "provider": delivery["provider"],
                    "provider_message_id": delivery.get("message_id"),
                    "accepted_at": datetime.now(timezone.utc),
                },
                "$unset": {"error": ""},
            },
        )
    except Exception:
        logger.exception(
            "Provider accepted invitation email, but outbox status update failed invitation_id=%s",
            outbox.get("invitation_id"),
        )
    return delivery["status"]


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
        failed_outbox = await db.email_outbox.find_one({
            "invitation_id": existing["_id"],
            "status": "failed",
        })
        if failed_outbox:
            delivery_status = await _deliver_email_outbox(db, failed_outbox)
            return {
                "message": "Pending invitation email retried",
                "invitation_id": str(existing["_id"]),
                "status": "pending",
                "email_status": delivery_status,
            }
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
    try:
        result = await db.invitations.insert_one(invitation)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Invitation is already pending") from exc

    try:
        await db.notifications.insert_one({
        "recipient_user_id": recipient["_id"],
        "type": "invitation",
        "event_type": "invitation.created",
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
    except Exception:
        logger.exception("Invitation created but notification could not be recorded invitation_id=%s", result.inserted_id)

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
        "invitation_id": result.inserted_id,
        "workspace_id": ObjectId(workspace_id),
        "recipient_user_id": recipient["_id"],
        "to": email,
        "subject": email_subject,
        "body": email_body,
        "status": "pending",
        "attempts": 0,
        "created_at": now,
    })

    delivery_status = await _deliver_email_outbox(db, {
        "_id": email_result.inserted_id,
        "invitation_id": result.inserted_id,
        "to": email,
        "subject": email_subject,
        "body": email_body,
        "status": "pending",
    })

    return {
        "message": "Invitation created",
        "invitation_id": str(result.inserted_id),
        "status": "pending",
        "email_status": delivery_status,
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
        if invitation.get("sender_user_id"):
            try:
                await db.notifications.insert_one({
                "recipient_user_id": invitation["sender_user_id"],
                "type": "workspace_event",
                "event_type": "workspace.member_added",
                "title": "Teammate joined",
                "message": f'{user.get("name") or user.get("email") or "A teammate"} accepted your invitation to "{invitation.get("workspace_name", "the workspace")}".',
                "action_text": "accepted your invitation to",
                "actor": {"name": user.get("name") or user.get("email"), "email": user.get("email"), "avatar": user.get("picture")},
                "workspace_id": invitation["workspace_id"],
                "workspace_name": invitation.get("workspace_name", ""),
                "is_read": False,
                "created_at": now,
                })
            except Exception:
                logger.exception("Member added but notification could not be recorded invitation_id=%s", invitation_id)

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
