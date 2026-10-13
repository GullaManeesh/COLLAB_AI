from app.config.settings import settings
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.database.mongodb import get_database
from app.services.email_service import send_email
import logging

logger = logging.getLogger(__name__)
INVITATION_VALID_DAYS = 7


def _hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _invitation_email_body(invitation: dict, token: str) -> str:
    frontend_base = settings.FRONTEND_URL.rstrip("/")
    invitation_url = f"{frontend_base}/invite#{token}"
    inviter = invitation.get("sender_name") or invitation.get("sender_email") or "A CollabAI teammate"
    expires_at = invitation["expires_at"].strftime("%B %d, %Y at %H:%M UTC")
    return (
        f'{inviter} invited you to join "{invitation["workspace_name"]}" on CollabAI.\n\n'
        f"Open the invitation to review the workspace and accept after signing in with "
        f"{invitation['recipient_email']}:\n{invitation_url}\n\n"
        f"This invitation expires on {expires_at}. You will need to sign in with the invited email address."
    )


async def _deliver_email_outbox(db, outbox: dict, body: str) -> str:
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
            outbox["to"], outbox["subject"], body,
            idempotency_key=outbox.get("delivery_key", str(outbox["_id"])),
        )
    except Exception as exc:
        safe_message = str(exc)
        for secret in (settings.SMTP_PASSWORD, settings.RESEND_API_KEY):
            if secret:
                safe_message = safe_message.replace(secret, "[redacted]")
        safe_error = f"{type(exc).__name__}: {safe_message[:400]}"
        logger.error(
            "Invitation email failed invitation_id=%s error=%s",
            outbox.get("invitation_id"), safe_error,
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
    if email == (user.get("email") or "").strip().lower():
        raise HTTPException(status_code=400, detail="You cannot invite yourself")

    if any(
        (recipient is not None and member.get("user_id") == recipient["_id"])
        or (member.get("email") or "").strip().lower() == email
        for member in workspace.get("members", [])
    ):
        raise HTTPException(status_code=409, detail="User is already a member")

    existing = await db.invitations.find_one({
        "workspace_id": ObjectId(workspace_id),
        "recipient_email": email,
        "status": "pending",
    })
    if existing and existing.get("expires_at") and _as_utc(existing["expires_at"]) <= datetime.now(timezone.utc):
        await db.invitations.update_one(
            {"_id": existing["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc)}},
        )
        existing = None
    if existing:
        failed_outbox = await db.email_outbox.find_one({
            "invitation_id": existing["_id"],
            "status": "failed",
        })
        if failed_outbox:
            raw_token = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=INVITATION_VALID_DAYS)
            updated = await db.invitations.update_one(
                {"_id": existing["_id"], "status": "pending"},
                {"$set": {"token_hash": _hash_invitation_token(raw_token), "expires_at": expires_at, "updated_at": now}},
            )
            if getattr(updated, "modified_count", 0) != 1:
                raise HTTPException(status_code=409, detail="Invitation is no longer pending")
            await db.email_outbox.update_one(
                {"_id": failed_outbox["_id"], "status": "failed"},
                {"$set": {"delivery_key": _hash_invitation_token(raw_token)}},
            )
            failed_outbox = {**failed_outbox, "delivery_key": _hash_invitation_token(raw_token)}
            retry_invitation = {**existing, "expires_at": expires_at}
            delivery_status = await _deliver_email_outbox(db, failed_outbox, _invitation_email_body(retry_invitation, raw_token))
            return {
                "message": "Pending invitation email retried",
                "invitation_id": str(existing["_id"]),
                "status": "pending",
                "email_status": delivery_status,
            }
        raise HTTPException(status_code=409, detail="Invitation is already pending")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=INVITATION_VALID_DAYS)
    raw_token = secrets.token_urlsafe(32)
    invitation = {
        "workspace_id": ObjectId(workspace_id),
        "workspace_name": workspace["name"],
        "sender_user_id": user["_id"],
        "sender_name": user.get("name") or user.get("email"),
        "sender_email": user.get("email"),
        "recipient_user_id": recipient["_id"] if recipient else None,
        "recipient_email": email,
        "token_hash": _hash_invitation_token(raw_token),
        "status": "pending",
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db.invitations.insert_one(invitation)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Invitation is already pending") from exc

    if recipient:
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

    email_subject = f'Invitation to {workspace["name"]} on CollabAI'
    email_body = _invitation_email_body(invitation, raw_token)

    # Queue email in outbox
    email_result = await db.email_outbox.insert_one({
        "invitation_id": result.inserted_id,
        "workspace_id": ObjectId(workspace_id),
        "recipient_user_id": recipient["_id"] if recipient else None,
        "workspace_name": workspace["name"],
        "sender_name": invitation["sender_name"],
        "sender_email": invitation["sender_email"],
        "delivery_key": _hash_invitation_token(raw_token),
        "to": email,
        "subject": email_subject,
        "status": "pending",
        "attempts": 0,
        "created_at": now,
    })

    delivery_status = await _deliver_email_outbox(db, {
        "_id": email_result.inserted_id,
        "invitation_id": result.inserted_id,
        "to": email,
        "subject": email_subject,
        "status": "pending",
    }, email_body)

    return {
        "message": "Invitation created",
        "invitation_id": str(result.inserted_id),
        "status": "pending",
        "email_status": delivery_status,
    }


async def resolve_invitation_token(token: str) -> dict:
    if not token or len(token) > 256:
        raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
    db = get_database()
    now = datetime.now(timezone.utc)
    invitation = await db.invitations.find_one({"token_hash": _hash_invitation_token(token)})
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
    if invitation.get("status") != "pending":
        raise HTTPException(status_code=410, detail="This invitation has already been used or revoked")
    expires_at = invitation.get("expires_at")
    if expires_at is None or _as_utc(expires_at) <= now:
        await db.invitations.update_one(
            {"_id": invitation["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=410, detail="This invitation has expired")
    workspace = await db.workspaces.find_one({"_id": invitation["workspace_id"]})
    if workspace is None:
        raise HTTPException(status_code=410, detail="This workspace is no longer available")
    return {
        "workspace_id": str(workspace["_id"]),
        "workspace_name": workspace.get("name", invitation.get("workspace_name", "Workspace")),
        "inviter_name": invitation.get("sender_name") or invitation.get("sender_email") or "A CollabAI teammate",
        "recipient_email": invitation["recipient_email"],
        "expires_at": _as_utc(expires_at).isoformat(),
        "status": "pending",
    }


async def accept_invitation_token(token: str, user: dict) -> dict:
    if not token or len(token) > 256:
        raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
    db = get_database()
    now = datetime.now(timezone.utc)
    invitation = await db.invitations.find_one({
        "token_hash": _hash_invitation_token(token),
        "status": "pending",
        "expires_at": {"$gt": now},
    })
    if invitation is None:
        raise HTTPException(status_code=410, detail="This invitation is invalid, expired, or already used")
    if invitation.get("status") != "pending":
        raise HTTPException(status_code=410, detail="This invitation has already been used or revoked")
    if invitation.get("expires_at") is None or _as_utc(invitation["expires_at"]) <= now:
        await db.invitations.update_one(
            {"_id": invitation["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=410, detail="This invitation has expired")

    account_email = (user.get("email") or "").strip().lower()
    if not user.get("email_verified", False) or account_email != invitation.get("recipient_email", "").strip().lower():
        raise HTTPException(status_code=403, detail="Sign in with the invited email address to accept this invitation")

    workspace = await db.workspaces.find_one({"_id": invitation["workspace_id"]})
    if workspace is None:
        raise HTTPException(status_code=410, detail="This workspace is no longer available")
    if any(
        member.get("user_id") == user["_id"]
        or (member.get("email") or "").strip().lower() == account_email
        for member in workspace.get("members", [])
    ):
        raise HTTPException(status_code=409, detail="You are already a member of this workspace")

    claimed = await db.invitations.update_one(
        {
            "_id": invitation["_id"], "status": "pending", "token_hash": _hash_invitation_token(token),
            "expires_at": {"$gt": now},
        },
        {"$set": {
            "status": "accepted", "recipient_user_id": user["_id"],
            "accepted_at": now, "updated_at": now,
        }},
    )
    if getattr(claimed, "modified_count", 0) != 1:
        raise HTTPException(status_code=409, detail="This invitation has already been handled")

    member = {
        "user_id": user["_id"], "email": account_email, "name": user.get("name"),
        "role": "member", "joined_at": now,
    }
    await db.workspaces.update_one(
        {"_id": invitation["workspace_id"], "members.user_id": {"$ne": user["_id"]}},
        {"$push": {"members": member}, "$set": {"updated_at": now}},
    )
    await db.notifications.update_many(
        {"recipient_user_id": user["_id"], "invitation_id": invitation["_id"]},
        {"$set": {"is_read": True, "status": "accepted", "read_at": now}},
    )
    if invitation.get("sender_user_id"):
        await db.notifications.insert_one({
            "recipient_user_id": invitation["sender_user_id"], "type": "workspace_event",
            "event_type": "workspace.member_added", "title": "Teammate joined",
            "message": f'{user.get("name") or account_email} accepted your invitation to "{workspace.get("name", "the workspace")}".',
            "workspace_id": workspace["_id"], "workspace_name": workspace.get("name", ""),
            "is_read": False, "created_at": now,
        })
    return {"message": "Invitation accepted", "status": "accepted", "workspace_id": str(workspace["_id"])}


async def list_workspace_invitations(workspace_id: str, user: dict) -> list[dict]:
    if not ObjectId.is_valid(workspace_id):
        raise HTTPException(status_code=400, detail="Invalid workspace ID")
    db = get_database()
    workspace = await db.workspaces.find_one({"_id": ObjectId(workspace_id), "owner_id": user["_id"]})
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found or you are not the owner")
    cursor = db.invitations.find({"workspace_id": workspace["_id"], "status": "pending"}).sort("created_at", -1)
    members = workspace.get("members", [])
    result = []
    async for invitation in cursor:
        expires_at = invitation.get("expires_at")
        if expires_at and _as_utc(expires_at) <= datetime.now(timezone.utc):
            await db.invitations.update_one(
                {"_id": invitation["_id"], "status": "pending"},
                {"$set": {"status": "expired", "updated_at": datetime.now(timezone.utc)}},
            )
            continue

        # A few legacy/direct-add flows may have added the account to the
        # workspace without transitioning its pending invite. Membership is
        # authoritative: reconcile the stale invitation so it cannot still be
        # revoked or shown as pending.
        invitation_email = (invitation.get("recipient_email") or "").strip().lower()
        invitation_user_id = invitation.get("recipient_user_id")
        matching_member = next((
            member for member in members
            if (invitation_user_id and member.get("user_id") == invitation_user_id)
            or (invitation_email and (member.get("email") or "").strip().lower() == invitation_email)
        ), None)
        if matching_member is None and invitation_email:
            invitation_user = await db.users.find_one({"email": invitation_email})
            if invitation_user:
                matching_member = next((
                    member for member in members
                    if member.get("user_id") == invitation_user["_id"]
                ), None)
                if matching_member:
                    invitation_user_id = invitation_user["_id"]
        if matching_member:
            now = datetime.now(timezone.utc)
            accepted_fields = {"status": "accepted", "accepted_at": now, "updated_at": now}
            if invitation_user_id:
                accepted_fields["recipient_user_id"] = invitation_user_id
            await db.invitations.update_one(
                {"_id": invitation["_id"], "status": "pending"},
                {"$set": accepted_fields},
            )
            continue

        outbox = await db.email_outbox.find_one({"invitation_id": invitation["_id"]}, sort=[("created_at", -1)])
        result.append({
            "invitation_id": str(invitation["_id"]), "email": invitation["recipient_email"],
            "status": "pending", "email_status": outbox.get("status") if outbox else None,
            "created_at": _as_utc(invitation["created_at"]).isoformat(),
            "expires_at": _as_utc(expires_at).isoformat() if expires_at else None,
        })
    return result


async def revoke_workspace_invitation(workspace_id: str, invitation_id: str, user: dict) -> dict:
    if not ObjectId.is_valid(workspace_id) or not ObjectId.is_valid(invitation_id):
        raise HTTPException(status_code=400, detail="Invalid workspace or invitation ID")
    db = get_database()
    workspace_oid = ObjectId(workspace_id)
    invitation_oid = ObjectId(invitation_id)
    if await db.workspaces.find_one({"_id": workspace_oid, "owner_id": user["_id"]}) is None:
        raise HTTPException(status_code=404, detail="Workspace not found or you are not the owner")
    result = await db.invitations.update_one(
        {"_id": invitation_oid, "workspace_id": workspace_oid, "status": "pending"},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
    )
    if getattr(result, "modified_count", 0) != 1:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    return {"message": "Invitation revoked", "status": "revoked"}


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
    if invitation.get("expires_at") and _as_utc(invitation["expires_at"]) <= now:
        await db.invitations.update_one(
            {"_id": invitation["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        raise HTTPException(status_code=410, detail="This invitation has expired")
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
