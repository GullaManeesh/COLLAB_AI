
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    message: str
    workspace_id: str | None = None
    invitation_id: str | None = None
    is_read: bool = False
    created_at: datetime
