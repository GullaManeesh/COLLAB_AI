
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.db.mongodb import get_database

from app.services.auth_service import hash_session_token

async def find_or_create_google_user(claims: dict) -> dict:
    """Find an existing Google user or create a new CollabAI user."""
    db = get_database()
    google_sub = claims.get("sub")
    email = claims.get("email")

    if not google_sub or not email:
        raise ValueError("Google token is missing required identity claims")
    if claims.get("email_verified") is not True:
        raise ValueError("Google email must be verified")

    now = datetime.now(timezone.utc)
    update = {
        "$set": {
            "email": email.lower(),
            "email_verified": True,
            "name": claims.get("name"),
            "picture": claims.get("picture"),
            "updated_at": now,
        },
        "$setOnInsert": {
            "google_sub": google_sub,
            "created_at": now,
        },
    }

    try:
        await db.users.update_one({"google_sub": google_sub}, update, upsert=True)
    except DuplicateKeyError:
        existing = await db.users.find_one({"google_sub": google_sub})
        if existing is None:
            raise

    user = await db.users.find_one({"google_sub": google_sub})
    if user is None:
        raise RuntimeError("Could not retrieve the authenticated user")
    return user






async def get_user_from_session_token(token: str) -> dict | None:
    """Resolve a non-expired browser session to its stored user."""
    db = get_database()
    session = await db.sessions.find_one(
        {
            "token_hash": hash_session_token(token),
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if session is None:
        return None
    return await db.users.find_one({"_id": session["user_id"]})


async def update_username(user_id: ObjectId, username: str) -> dict:
    """Persist a validated username and return the updated user."""
    db = get_database()
    now = datetime.now(timezone.utc)
    result = await db.users.find_one_and_update(
        {"_id": user_id},
        {"$set": {"username": username, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise ValueError("User account was not found")
    return result


def serialize_user(user: dict) -> dict:
    """Return only public user fields; never expose MongoDB internals."""
    return {
        "id": str(user["_id"]),
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "username": user.get("username"),
        "email_verified": user.get("email_verified", False),
    }



