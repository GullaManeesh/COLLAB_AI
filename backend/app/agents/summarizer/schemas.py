from enum import Enum

from pydantic import BaseModel, Field


class SummaryOperation(str, Enum):
    TOPIC = "topic_summary"
    WHOLE_DOCUMENT = "whole_document_summary"
    QUESTION = "question_focused_summary"


class SummaryIntent(BaseModel):
    operation: SummaryOperation
    question: str
    topic: str | None = None
    document_reference: str | None = None


class SummaryOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=4500)
    cited_source_ids: list[str] = Field(default_factory=list, max_length=100)


class SummaryResult(BaseModel):
    summary: str
    sources: list[dict] = Field(default_factory=list)
    assessment: str = "insufficient_evidence"
    explanation: str = ""
    coverage: str = "unknown"
    limitations: list[str] = Field(default_factory=list)
    status: str = "succeeded"
    completion: object | None = None
