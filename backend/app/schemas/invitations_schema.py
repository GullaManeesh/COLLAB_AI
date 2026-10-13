
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
