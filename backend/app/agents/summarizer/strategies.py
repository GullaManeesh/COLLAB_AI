import json
import re

from fastapi import HTTPException

from app.agents.summarizer.schemas import SummaryIntent, SummaryOperation, SummaryOutput

_WHOLE = re.compile(r"\b(entire|whole|complete|full)\b.{0,80}\b(document|file|paper|report|workspace)\b|\b(entire|whole|complete|full)\b.{0,80}\.(?:pdf|docx?|txt|md)\b|\b(document|file|paper|report)\b.{0,40}\b(entirely|in full|as a whole)\b", re.I)
_PROJECT_PLAN = re.compile(
    r"\b(?:our|this|the)\s+(?:collabai\s+)?(?:project|implementation|roadmap|system)\b|"
    r"\b(?:planned|plan(?:ning)?|selected|decided|implement(?:ed|ing)?|in progress|completed)\b.{0,60}"
    r"\b(?:project|implementation|agents?|components?|features?)\b|"
    r"\b(?:which|what)\b.{0,100}\b(?:agents?|components?|features?)\b.{0,60}"
    r"\b(?:include|including|selected|planned|implement(?:ed|ing)?)\b.{0,60}\b(?:project|implementation|roadmap)\b",
    re.I,
)


def interpret_request(content: str) -> SummaryIntent:
    match = re.match(r"^\s*@summarizer(?:\s+|$)(.*)$", content, flags=re.I | re.S)
    if not match:
        raise HTTPException(status_code=422, detail="Start the message with @summarizer to run this agent.")
    question = match.group(1).strip()
    if not question:
        question = "Summarize relevant workspace context."
    if _WHOLE.search(question):
        operation = SummaryOperation.WHOLE_DOCUMENT
    elif _PROJECT_PLAN.search(question) and not re.search(
        r"\b(?:related\s+work|literature\s+review|prior\s+work|what\s+(?:does|do)\s+(?:the\s+)?(?:paper|study|article)\s+(?:mention|discuss|describe))\b",
        question,
        re.I,
    ):
        operation = SummaryOperation.PROJECT_PLAN
    elif re.match(r"\s*(what|how|why|which|where|when|who|does|do|did|is|are|was|were)\b", question, re.I):
        operation = SummaryOperation.QUESTION
    else:
        operation = SummaryOperation.TOPIC
    topic = question if operation != SummaryOperation.WHOLE_DOCUMENT else None
    reference = extract_document_reference(question)
    return SummaryIntent(operation=operation, question=question, topic=topic, document_reference=reference)


def extract_document_reference(question: str) -> str | None:
    identifier = re.search(r"(?<![0-9a-f])[0-9a-f]{24}(?![0-9a-f])", question, re.I)
    if identifier:
        return identifier.group(0)
    filename = re.search(r"[\w .()'_-]+\.(?:pdf|docx?|txt|md)\b", question, re.I)
    if filename:
        return filename.group(0).strip()
    named = re.search(r"\b(?:document|file|paper|report)\s+(?:named|called|titled)\s+(.+?)(?=[?.!,;]|$)", question, re.I)
    if named:
        return named.group(1).strip().strip("\"'“”")
    contextual = re.search(
        r"\b(?:summarize|in|from|about|on|uploaded)\s+(?:the\s+)?(?:(?:uploaded|entire|whole|full)\s+){0,2}((?:[A-Z0-9][\w.&()'-]*\s+){1,5}(?:paper|report|document|file))\b",
        question,
    )
    return contextual.group(1).strip() if contextual else None


def response_format(model: str) -> dict:
    if model.strip().lower() not in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
        return {"type": "json_object"}
    return {"type": "json_schema", "json_schema": {
        "name": "workspace_summary", "strict": True,
        "schema": {"type": "object", "properties": {
            "summary": {"type": "string"},
            "cited_source_ids": {"type": "array", "items": {"type": "string"}},
        }, "required": ["summary", "cited_source_ids"], "additionalProperties": False},
    }}


def validate_output(content: str, supplied_sources: list[dict]) -> tuple[str, list[dict]]:
    try:
        output = SummaryOutput.model_validate_json(content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The summarizer returned an invalid structured response. Please retry.") from exc
    source_map = {source["citation_id"]: source for source in supplied_sources}
    ids = set(output.cited_source_ids) & set(source_map)
    citations = [source for source in supplied_sources if source["citation_id"] in ids]
    if supplied_sources and not citations:
        raise HTTPException(status_code=502, detail="The summarizer did not cite any supplied sources. Please retry.")
    summary = re.sub(r"\s+([.,;:!?])", r"\1", output.summary.strip())
    # Remove fabricated inline references while retaining all validated metadata from retrieval.
    summary = re.sub(r"\[?(doc|chat):([A-Za-z0-9_-]+)\]?", lambda m: m.group(0) if f"{m.group(1)}:{m.group(2)}" in ids else "", summary)
    summary = re.sub(r"\s+([.,;:!?])", r"\1", summary).strip()
    public_sources = [{key: source[key] for key in ("source_type", "source_id", "chunk_id", "title", "created_at", "page", "score") if key in source} for source in citations]
    return summary[:4500], public_sources
