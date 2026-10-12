from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class SessionModel(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    token_hash: str = Field(min_length=64, max_length=64)
    user_id: ObjectId
    created_at: datetime
    expires_at: datetime
