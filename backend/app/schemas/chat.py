
from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ChatMessageResponse(BaseModel):
    id: str
    workspace_id: str
    sender_id: str
    sender_name: str
    sender_picture: str | None = None
    content: str
    created_at: datetime
    client_message_id: str | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
    has_more: bool
