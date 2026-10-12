from app.services import notification_service


async def list_notifications_controller(user: dict, tab: str = "inbox", page: int = 1, limit: int = 20):
    return await notification_service.list_notifications(user, tab=tab, page=page, limit=limit)


async def get_unread_count_controller(user: dict):
    return await notification_service.get_unread_count(user)


async def mark_as_read_controller(notification_id: str, user: dict):
    return await notification_service.mark_as_read(notification_id, user)


async def mark_all_as_read_controller(user: dict):
    return await notification_service.mark_all_as_read(user)
