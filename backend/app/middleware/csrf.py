import logging

from fastapi import Depends, HTTPException, Request

from app.config.settings import settings

logger = logging.getLogger(__name__)


def require_csrf_token(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get("X-CSRF-Token")
    logger.info(
        "[CSRF] Method: %s, URL: %s, has_cookie_token: %s, has_header_token: %s, match: %s",
        request.method,
        request.url.path,
        bool(cookie_token),
        bool(header_token),
        cookie_token == header_token if (cookie_token and header_token) else False,
    )
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


CsrfProtected = Depends(require_csrf_token)
