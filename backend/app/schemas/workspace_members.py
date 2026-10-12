
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceMemberResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    username: str | None = None
    role: str = Field(pattern=r"^(owner|admin|member)$")
    joined_at: datetime | None = None


class WorkspaceMembersResponse(BaseModel):
    members: list[WorkspaceMemberResponse]
    total: int
