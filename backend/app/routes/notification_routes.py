from fastapi import APIRouter, Query

from app.controllers import notification_controller as controller
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    user: CurrentUser,
    tab: str = Query(default="inbox"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    return await controller.list_notifications_controller(
        user=user, tab=tab, page=page, limit=limit
    )


@router.get("/unread-count")
async def get_unread_count(user: CurrentUser):
    return await controller.get_unread_count_controller(user=user)


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.mark_as_read_controller(
        notification_id=notification_id, user=user
    )


@router.post("/mark-all-read")
async def mark_all_as_read(
    user: CurrentUser,
    _: None = CsrfProtected,
):
    return await controller.mark_all_as_read_controller(user=user)
