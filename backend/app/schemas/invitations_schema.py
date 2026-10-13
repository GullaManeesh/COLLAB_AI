
from pydantic import BaseModel, EmailStr, field_validator


class CreateInvitationRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> EmailStr:
        return str(value).strip().lower()


class InvitationResponse(BaseModel):
    message: str
    invitation_id: str
    status: str
    email_status: str | None = None


class InvitationTokenRequest(BaseModel):
    token: str


class InvitationPreviewResponse(BaseModel):
    workspace_id: str
    workspace_name: str
    inviter_name: str
    recipient_email: str
    expires_at: str
    status: str


class InvitationListItem(BaseModel):
    invitation_id: str
    email: str
    status: str
    email_status: str | None = None
    created_at: str
    expires_at: str | None = None
