import asyncio

from app.agents.base import Agent
from app.agents.context.context_engine import ContextEngine
from app.agents.context.evidence import assess_evidence
from app.agents.registry import register_agent
from app.agents.summarizer.prompts import build_map_messages, build_messages
from app.agents.summarizer.schemas import SummaryResult
from app.agents.summarizer.strategies import interpret_request, response_format, validate_output
from app.config.settings import settings
from app.services.groq_service import complete

CHUNKS_PER_SECTION = settings.SUMMARIZER_CHUNKS_PER_SECTION
MAX_MAP_SECTIONS = (settings.SUMMARIZER_MAX_DOCUMENT_CHUNKS + CHUNKS_PER_SECTION - 1) // CHUNKS_PER_SECTION
MAP_CONCURRENCY = settings.SUMMARIZER_MAP_CONCURRENCY
OVERALL_DEADLINE_SECONDS = settings.SUMMARIZER_DEADLINE_SECONDS


class SummarizerAgent(Agent):
    agent_type = "summarizer"

    def __init__(self, context_engine=None, completion=complete):
        self.context_engine = context_engine or ContextEngine()
        self.completion = completion

    async def execute(self, *, workspace_id: str, user: dict, content: str, exclude_message_id=None) -> SummaryResult:
        intent = interpret_request(content)
        context = await self.context_engine.retrieve(
            workspace_id=workspace_id, user=user, query=intent.question, operation=intent.operation.value,
            document_reference=intent.document_reference, exclude_message_id=exclude_message_id,
        )
        sources = context["sources"]
        if context.get("message"):
            return SummaryResult(
                summary=context["message"], assessment="insufficient_evidence", explanation=context["message"],
                coverage="unknown", limitations=context.get("limitations", []), status=context.get("status", "clarification"),
            )
        if not sources:
            message = "I couldn't find sufficient information about this request in authorized workspace documents or team chat. Try specifying another document or a more precise topic."
            return SummaryResult(summary=message, assessment="insufficient_evidence", explanation=message, limitations=["No relevant source passages were found."])
        if hasattr(self.context_engine, "sources_are_current") and not await self.context_engine.sources_are_current(workspace_id=workspace_id, user=user, sources=sources):
            message = "The source content changed while I was preparing this answer. Please retry so I can use the current workspace data."
            return SummaryResult(summary=message, assessment="insufficient_evidence", explanation=message, limitations=["One or more retrieved sources are no longer available."])
        if intent.operation.value == "whole_document_summary" and context.get("document"):
            summary, citations, completion = await self._whole_document(intent, sources, complete=context.get("complete") is True)
        else:
            completion = await self.completion(build_messages(intent, sources), response_format=response_format(settings.GROQ_MODEL))
            summary, citations = validate_output(completion.content, sources)
        if hasattr(self.context_engine, "sources_are_current") and not await self.context_engine.sources_are_current(workspace_id=workspace_id, user=user, sources=sources):
            message = "The source content changed while I was preparing this answer. Please retry so I can use the current workspace data."
            return SummaryResult(summary=message, assessment="insufficient_evidence", explanation=message, limitations=["One or more retrieved sources are no longer available."])
        assessment = assess_evidence(sources, citations, complete=context.get("complete"), limitations=context.get("limitations"))
        return SummaryResult(
            summary=summary, sources=citations, assessment=assessment.assessment, explanation=assessment.explanation,
            coverage=assessment.coverage, limitations=assessment.limitations, completion=completion,
        )

    async def _whole_document(self, intent, sources, *, complete: bool):
        source_by_id = {s["citation_id"]: s for s in sources}
        if len(sources) <= CHUNKS_PER_SECTION:
            async with asyncio.timeout(OVERALL_DEADLINE_SECONDS):
                result = await self.completion(
                    build_messages(intent, sources, whole_document=True, coverage_complete=complete),
                    response_format=response_format(settings.GROQ_MODEL),
                    max_completion_tokens=1800,
                )
            summary, citations = validate_output(result.content, sources)
            return summary, citations, result
        sections = [sources[i:i + CHUNKS_PER_SECTION] for i in range(0, len(sources), CHUNKS_PER_SECTION)]
        if len(sections) > MAX_MAP_SECTIONS:
            sections = sections[:MAX_MAP_SECTIONS]
        semaphore = asyncio.Semaphore(MAP_CONCURRENCY)

        async def map_section(section):
            async with semaphore:
                async with asyncio.timeout(OVERALL_DEADLINE_SECONDS):
                    result = await self.completion(build_map_messages(intent, section), max_completion_tokens=350, response_format=response_format(settings.GROQ_MODEL))
            parsed, refs = validate_output(result.content, section)
            by_public_id = {(source.get("chunk_id") or source.get("source_id")): source["citation_id"] for source in section}
            original_ids = [by_public_id.get(ref.get("chunk_id") or ref.get("source_id")) for ref in refs]
            return {"summary": parsed[:300], "source_ids": [item for item in original_ids if item]}, result

        # One outer deadline bounds the full map and synthesis workflow.
        async with asyncio.timeout(OVERALL_DEADLINE_SECONDS):
            mapped = await asyncio.gather(*(map_section(section) for section in sections))
            map_notes = [item[0] for item in mapped]
            notes_as_sources = [{
                "citation_id": source_id, "source_type": source_by_id[source_id]["source_type"],
                "title": source_by_id[source_id]["title"], "text": note["summary"][:300],
                "source_id": source_by_id[source_id].get("source_id"), "chunk_id": source_by_id[source_id].get("chunk_id"),
                "page": source_by_id[source_id].get("page"), "score": source_by_id[source_id].get("score"),
            } for note in map_notes for source_id in note["source_ids"] if source_id in source_by_id]
            # Keep the reducer input bounded and allow it to cite only original chunk IDs.
            notes_as_sources = _dedupe_sources(notes_as_sources)[:54]
            bounded_notes = []
            note_chars = 0
            for note in notes_as_sources:
                remaining = settings.SUMMARIZER_REDUCE_CONTEXT_CHARS - note_chars
                if remaining <= 0:
                    break
                note["text"] = note["text"][:min(300, remaining)]
                if note["text"]:
                    bounded_notes.append(note)
                    note_chars += len(note["text"])
            notes_as_sources = bounded_notes
            final = await self.completion(build_messages(intent, notes_as_sources, whole_document=True, coverage_complete=complete), response_format=response_format(settings.GROQ_MODEL), max_completion_tokens=1800)
            summary, citations = validate_output(final.content, notes_as_sources)
        return summary, citations, final


def _dedupe_sources(sources):
    output, seen = [], set()
    for source in sources:
        if source["citation_id"] not in seen:
            output.append(source)
            seen.add(source["citation_id"])
    return output


summarizer_agent = SummarizerAgent()
register_agent(summarizer_agent)
