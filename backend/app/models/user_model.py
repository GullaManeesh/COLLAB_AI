from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserModel(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    id: ObjectId | None = Field(default=None, alias="_id")
    google_sub: str = Field(min_length=1)
    email: EmailStr
    email_verified: bool
    name: str | None = None
    picture: str | None = None
    username: str | None = None
    created_at: datetime
    updated_at: datetime


class PublicUser(BaseModel):
    id: str
    email: EmailStr
    email_verified: bool
    name: str | None = None
    picture: str | None = None
    username: str | None = None


class GoogleTokenRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=10000)


class UsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-z0-9_]+$")


class AuthResponse(BaseModel):
    user: PublicUser
    needs_username: bool


class UserResponse(BaseModel):
    user: PublicUser
