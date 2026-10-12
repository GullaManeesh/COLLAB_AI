from fastapi import Depends, HTTPException, Request

from app.config.settings import settings


def require_csrf_token(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


CsrfProtected = Depends(require_csrf_token)
