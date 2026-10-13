from pydantic import BaseModel, Field


class SummarizerRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    client_request_id: str = Field(min_length=8, max_length=100)
