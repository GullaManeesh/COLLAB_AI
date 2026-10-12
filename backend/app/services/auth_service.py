import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException, Response
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database.mongodb import get_database


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(user_id: ObjectId) -> str:
    db = get_database()
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.sessions.insert_one(
        {
            "token_hash": hash_session_token(raw_token),
            "user_id": user_id,
            "created_at": now,
            "expires_at": now + timedelta(days=settings.SESSION_TTL_DAYS),
        }
    )
    return raw_token


async def revoke_session(token: str) -> None:
    await get_database().sessions.delete_one({"token_hash": hash_session_token(token)})


def verify_credential(credential: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google authentication is not configured")
    try:
        return id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired Google ID token") from exc


async def find_or_create_google_user(claims: dict) -> dict:
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
        "$setOnInsert": {"google_sub": google_sub, "created_at": now},
    }
    db = get_database()
    try:
        await db.users.update_one({"google_sub": google_sub}, update, upsert=True)
    except DuplicateKeyError:
        if await db.users.find_one({"google_sub": google_sub}) is None:
            raise

    user = await db.users.find_one({"google_sub": google_sub})
    if user is None:
        raise RuntimeError("Could not retrieve the authenticated user")
    return user


async def get_user_from_session_token(token: str) -> dict | None:
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
    result = await get_database().users.find_one_and_update(
        {"_id": user_id},
        {"$set": {"username": username, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise ValueError("User account was not found")
    return result


def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "username": user.get("username"),
        "email_verified": user.get("email_verified", False),
    }


logger = logging.getLogger(__name__)


def set_session_cookie(response: Response, token: str) -> None:
    is_cross_origin = settings.COOKIE_SAMESITE == "none"
    logger.info(
        "Setting session cookie: secure=%s, samesite=%s, partitioned=%s",
        settings.COOKIE_SECURE, settings.COOKIE_SAMESITE, is_cross_origin,
    )
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        partitioned=is_cross_origin,
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    is_cross_origin = settings.COOKIE_SAMESITE == "none"
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        partitioned=is_cross_origin,
    )
