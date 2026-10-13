
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CreateWorkspaceRequest(BaseModel):
    """Validated data submitted when creating a workspace."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    initial_members: list[EmailStr] = Field(
        default_factory=list,
        max_length=50,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Workspace name cannot be empty")

        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("initial_members")
    @classmethod
    def normalize_invitees(
        cls,
        emails: list[EmailStr],
    ) -> list[EmailStr]:
        normalized = []
        seen = set()

        for email in emails:
            email = str(email).strip().lower()

            if email not in seen:
                seen.add(email)
                normalized.append(email)

        return normalized


class WorkspaceResponse(BaseModel):
    """Public representation of a workspace."""

    id: str
    name: str
    description: str
    owner_id: str
    member_count: int = 1
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    """Response returned when listing workspaces."""

    workspaces: list[WorkspaceResponse]
    total: int




class UpdateWorkspaceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Workspace name cannot be empty")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TeammateSuggestion(BaseModel):
    user_id: str
    email: EmailStr
    name: str | None = None
    picture: str | None = None
    username: str | None = None


class TeammateSuggestionResponse(BaseModel):
    suggestions: list[TeammateSuggestion]


class WorkspaceDetailResponse(WorkspaceResponse):
    members: list[dict] = Field(default_factory=list)
    channels: list[dict] = Field(default_factory=list)


class InvitationActionResponse(BaseModel):
    message: str
    status: str
    workspace_id: str | None = None
