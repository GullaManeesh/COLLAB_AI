from typing import Annotated

import logging

from fastapi import Cookie, Depends, HTTPException, Request
from pymongo.errors import PyMongoError

from app.config.settings import settings
from app.services.auth_service import get_user_from_session_token

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> dict:
    """Reusable FastAPI authentication dependency equivalent to Express protect middleware.

    1. Reads the session cookie using SESSION_COOKIE_NAME.
    2. Raises 401 if missing.
    3. Hashes session token via SHA-256 and queries valid unexpired session in MongoDB.
    4. Raises 401 if session is missing, invalid, or expired.
    5. Retrieves user document by user_id.
    6. Raises 401 if user no longer exists.
    7. Raises 503 if MongoDB storage is unavailable.
    8. Returns the authenticated user document.
    """
    logger.info(
        "[AUTH] Cookie check - cookie_name=%s, has_cookie=%s, origin=%s, all_cookies=%s",
        settings.SESSION_COOKIE_NAME,
        session_cookie is not None,
        request.headers.get("origin", "N/A"),
        list(request.cookies.keys()),
    )
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        user = await get_user_from_session_token(session_cookie)
    except (PyMongoError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication storage is temporarily unavailable",
        ) from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


CurrentUser = Annotated[dict, Depends(get_current_user)]
