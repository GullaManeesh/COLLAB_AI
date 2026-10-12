from fastapi import APIRouter, Cookie, Response

from app.config.settings import settings
from app.controllers.auth_controller import (
    current_user,
    google_login,
    logout,
    save_username,
)
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.models.user_model import (
    AuthResponse,
    GoogleTokenRequest,
    UserResponse,
    UsernameRequest,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/google", response_model=AuthResponse)
async def google_login_route(payload: GoogleTokenRequest, response: Response) -> AuthResponse:
    return await google_login(payload, response)


@router.get("/me", response_model=AuthResponse)
async def current_user_route(
    response: Response,
    user: CurrentUser,
) -> AuthResponse:
    return await current_user(response, user)


@router.patch("/username", response_model=UserResponse)
@router.post("/username", response_model=UserResponse, include_in_schema=False)
async def save_username_route(
    payload: UsernameRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
) -> UserResponse:
    return await save_username(payload, user)


@router.post("/logout", status_code=204)
async def logout_route(
    response: Response,
    user: CurrentUser,
    _: None = CsrfProtected,
    session_cookie: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> None:
    await logout(response, session_cookie)
