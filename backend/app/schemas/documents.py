
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


EMBEDDING_DIMENSIONS = 384


class DocumentResponse(BaseModel):
    id: str
    workspace_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: int = 0
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class EmbeddingVector(BaseModel):
    """A single normalized embedding vector."""

    values: list[float] = Field(
        min_length=EMBEDDING_DIMENSIONS,
        max_length=EMBEDDING_DIMENSIONS,
    )


class DocumentChunkRecord(BaseModel):
    """Data stored for one extracted text chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    workspace_id: str
    uploader_id: str
    filename: str
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    start_index: int = Field(default=0, ge=0)
    created_at: datetime


class EmbeddedDocumentChunk(DocumentChunkRecord):
    """A text chunk together with its embedding vector."""

    embedding: list[float] = Field(
        min_length=EMBEDDING_DIMENSIONS,
        max_length=EMBEDDING_DIMENSIONS,
    )


class DocumentSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    page: int | None = None
    start_index: int = 0
    score: float | None = None


class DocumentSearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    message: str
