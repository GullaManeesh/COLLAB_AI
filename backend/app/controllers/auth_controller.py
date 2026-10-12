import secrets

from fastapi import HTTPException, Response
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config.settings import settings
from app.models.user_model import (
    AuthResponse,
    GoogleTokenRequest,
    PublicUser,
    UserResponse,
    UsernameRequest,
)
from app.services import auth_service


def _auth_response(user: dict) -> AuthResponse:
    public_user = auth_service.serialize_user(user)
    return AuthResponse(
        user=PublicUser.model_validate(public_user),
        needs_username=not bool(public_user.get("username")),
    )


async def google_login(payload: GoogleTokenRequest, response: Response) -> AuthResponse:
    claims = auth_service.verify_credential(payload.credential)
    if claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="A verified Google email is required")

    try:
        user = await auth_service.find_or_create_google_user(claims)
        session_token = await auth_service.create_session(user["_id"])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (PyMongoError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication storage is temporarily unavailable",
        ) from exc

    auth_service.set_session_cookie(response, session_token)
    auth_service.set_csrf_cookie(response, secrets.token_urlsafe(32))
    return _auth_response(user)


async def current_user(
    response: Response,
    user: dict,
) -> AuthResponse:
    auth_service.set_csrf_cookie(response, secrets.token_urlsafe(32))
    return _auth_response(user)


async def save_username(
    payload: UsernameRequest,
    user: dict,
) -> UserResponse:
    try:
        updated_user = await auth_service.update_username(user["_id"], payload.username)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="That username is already taken") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PyMongoError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication storage is temporarily unavailable",
        ) from exc
    return UserResponse(user=PublicUser.model_validate(auth_service.serialize_user(updated_user)))


async def logout(
    response: Response,
    session_cookie: str | None,
) -> None:
    if session_cookie:
        try:
            await auth_service.revoke_session(session_cookie)
        except (PyMongoError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Authentication storage is temporarily unavailable",
            ) from exc
    is_cross_origin = settings.COOKIE_SAMESITE == "none"
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        partitioned=is_cross_origin,
    )
    response.delete_cookie(
        settings.CSRF_COOKIE_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        partitioned=is_cross_origin,
    )
