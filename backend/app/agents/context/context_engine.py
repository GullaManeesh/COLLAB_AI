"""Authorized retrieval of workspace chat and document evidence."""

from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import HTTPException

from app.agents.context.source_resolver import resolve_document_reference
from app.database.mongodb import get_database
from app.services.chat_service import get_workspace_for_member
from app.services.document_service import search_workspace_chunks
from app.services.embedding_service import EmbeddingModelUnavailableError
from app.config.settings import settings

MAX_CHAT_SCAN = 40
MAX_CHAT_SOURCES = 8
MAX_DOCUMENT_SOURCES = 6
MAX_DOCUMENT_CANDIDATES = 1500
MAX_SOURCE_CHARS = 2400
MAX_TOTAL_CONTEXT_CHARS = 18000
MAX_WHOLE_DOCUMENT_CHUNKS = settings.SUMMARIZER_MAX_DOCUMENT_CHUNKS
_PROJECT_CONTEXT = re.compile(
    r"\b(?:our|this|the)\s+(?:collabai\s+)?(?:project|implementation|roadmap|system)\b|"
    r"\bcollabai\s+(?:project|implementation|roadmap|system)\b|"
    r"\bproject\s+(?:plan|roadmap|implementation)\b",
    re.I,
)
_TEAM_DECISION = re.compile(
    r"\b(?:we|our\s+team|this\s+project|our\s+project|the\s+project)\s+"
    r"(?:have\s+)?(?:plan(?:s)?(?:\s+to)?|intend(?:s)?\s+to|will|are\s+"
    r"(?:including|implementing|building)|selected|decided|chosen|include(?:s)?|"
    r"use(?:s|d)?|implement(?:ed|ing)?|build(?:s|ing)?|complete(?:d)?|"
    r"in\s+progress)\b|"
    r"\b(?:implementation\s+plan|project\s+roadmap|selected\s+for\s+implementation|"
    r"planned\s+for\s+(?:the\s+)?project|implemented\s+in\s+(?:the\s+)?project|"
    r"in\s+progress\s+(?:on|for)\s+(?:the\s+)?project)\b",
    re.I,
)
_PLAN_STATUS = re.compile(
    r"\b(?:planned|in\s+progress|implemented|completed)\b",
    re.I,
)
_RELATED_WORK = re.compile(
    r"\b(?:related\s+work|prior\s+work|literature\s+review|background|existing\s+approaches|"
    r"survey\s+of\s+(?:existing|prior|related))\b",
    re.I,
)


def _project_source_role(source: dict) -> str:
    """Classify evidence for plan questions without promoting research mentions to decisions."""
    title = source.get("title") or ""
    text = source.get("text") or ""
    normalized_title = re.sub(r"[_-]+", " ", title)
    combined = f"{normalized_title}\n{text}"
    is_chat_decision = source.get("source_type") == "chat_message"
    has_project_anchor = bool(_PROJECT_CONTEXT.search(combined))
    title_is_plan = bool(re.search(
        r"\b(?:project|collabai)\b.{0,60}\b(?:plan|roadmap|implementation|architecture|decision)\b",
        normalized_title,
        re.I,
    ))
    has_decision = bool(_TEAM_DECISION.search(text)) or (
        title_is_plan and bool(_PLAN_STATUS.search(text))
    )
    is_related_work = bool(_RELATED_WORK.search(combined))
    if has_decision and (is_chat_decision or has_project_anchor) and not is_related_work:
        return "project_decision"
    if is_related_work:
        return "related_work"
    return "general_context"


def select_project_plan_sources(sources: list[dict]) -> list[dict]:
    """Only explicit project decisions/status evidence can answer project-plan questions."""
    return [
        {**source, "evidence_role": "project_decision"}
        for source in sources
        if _project_source_role(source) == "project_decision"
    ]


def _timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _source_from_chunk(chunk: dict) -> dict:
    return {
        "citation_id": f"doc:{chunk['chunk_id']}",
        "source_type": "document",
        "source_id": chunk["document_id"],
        "chunk_id": chunk["chunk_id"],
        "title": chunk.get("filename") or "Workspace document",
        "created_at": _timestamp(chunk.get("created_at")),
        "page": chunk.get("page"),
        "score": chunk.get("score"),
        "text": " ".join((chunk.get("text") or "").split())[:MAX_SOURCE_CHARS],
    }


class ContextEngine:
    async def sources_are_current(self, *, workspace_id: str, user: dict, sources: list[dict]) -> bool:
        workspace = await get_workspace_for_member(workspace_id, user)
        db = get_database()
        document_sources = [source for source in sources if source.get("source_type") == "document"]
        if document_sources:
            document_ids = {ObjectId(source["source_id"]) for source in document_sources if ObjectId.is_valid(source.get("source_id", ""))}
            documents = [doc async for doc in db.documents.find({
                "workspace_id": workspace["_id"], "_id": {"$in": list(document_ids)}, "status": "ready",
            }, {"_id": 1})]
            live_ids = {str(doc["_id"]) for doc in documents}
            if live_ids != {source["source_id"] for source in document_sources}:
                return False
            chunk_ids = {ObjectId(source["chunk_id"]) for source in document_sources if ObjectId.is_valid(source.get("chunk_id", ""))}
            chunks = [chunk async for chunk in db.chunks.find({
                "workspace_id": workspace["_id"], "document_id": {"$in": list(document_ids)}, "_id": {"$in": list(chunk_ids)},
            }, {"_id": 1})]
            if {str(chunk["_id"]) for chunk in chunks} != {source["chunk_id"] for source in document_sources}:
                return False
        chat_sources = [source for source in sources if source.get("source_type") == "chat_message"]
        if chat_sources:
            message_ids = [ObjectId(source["source_id"]) for source in chat_sources if ObjectId.is_valid(source.get("source_id", ""))]
            records = [message async for message in db.messages.find({
                "workspace_id": workspace["_id"], "_id": {"$in": message_ids}, "message_type": {"$ne": "private"},
            }, {"_id": 1})]
            if {str(item["_id"]) for item in records} != {source["source_id"] for source in chat_sources}:
                return False
        return True

    async def retrieve(self, *, workspace_id: str, user: dict, query: str, operation: str, document_reference: str | None = None, exclude_message_id: ObjectId | None = None) -> dict:
        workspace = await get_workspace_for_member(workspace_id, user)
        db = get_database()
        resolution_request = document_reference or query
        resolution = await resolve_document_reference(workspace_id, user, resolution_request, already_extracted=bool(document_reference))
        if not resolution.explicit and operation != "whole_document_summary" and re.search(r"\b(?:the|a|an|this|that)?\s*(?:document|file|paper|report)\b", query, re.I):
            candidates = [doc async for doc in db.documents.find(
                {"workspace_id": workspace["_id"], "status": "ready"},
                {"_id": 1, "filename": 1, "status": 1, "chunk_count": 1},
            ).limit(3)]
            if len(candidates) > 1:
                return {"sources": [], "message": "This request refers to a document, but more than one ready document is available. Please include its exact file name.", "status": "document_ambiguous", "complete": False, "limitations": ["The target document is ambiguous."]}
            if len(candidates) == 1:
                resolution.document = candidates[0]
            else:
                return {"sources": [], "message": "I couldn't find a ready document in this workspace for that request.", "status": "document_not_found", "complete": False, "limitations": ["No ready documents are available."]}
        # A no-reference whole-document request can only be inferred when exactly one
        # ready document exists; multiple candidates require an explicit choice.
        if operation == "whole_document_summary" and not resolution.explicit and not resolution.message:
            docs = [doc async for doc in db.documents.find(
                {"workspace_id": workspace["_id"], "status": "ready"},
                {"_id": 1, "filename": 1, "status": 1, "chunk_count": 1},
            ).limit(3)]
            if len(docs) == 1:
                resolution.document = docs[0]
            elif len(docs) > 1:
                return {"sources": [], "message": "This workspace has multiple documents. Please include the exact document name you want summarized.", "status": "document_ambiguous", "complete": False, "limitations": ["The target document is ambiguous."]}
            else:
                return {"sources": [], "message": "I couldn't find a ready document in this workspace to summarize.", "status": "insufficient_evidence", "complete": False, "limitations": ["No ready documents are available."]}
        if resolution.message:
            return {"sources": [], "message": resolution.message, "status": resolution.status, "complete": False, "limitations": [resolution.message]}

        if operation == "whole_document_summary" and resolution.document:
            document = resolution.document
            doc_id = document["_id"]
            expected = int(document.get("chunk_count", 0) or 0)
            cursor = db.chunks.find(
                {"workspace_id": workspace["_id"], "document_id": doc_id},
                {"_id": 1, "document_id": 1, "filename": 1, "chunk_index": 1, "text": 1, "page": 1, "created_at": 1},
            ).sort([("chunk_index", 1), ("_id", 1)]).limit(MAX_WHOLE_DOCUMENT_CHUNKS + 1)
            chunks = [chunk async for chunk in cursor]
            if not chunks:
                return {"sources": [], "document": document, "message": f"'{document.get('filename', 'That document')}' has no currently indexed content available. It may have been deleted or indexing may have failed.", "status": "document_unavailable", "complete": False, "limitations": ["No indexed chunks are available."]}
            complete = expected > 0 and len(chunks) == expected and len(chunks) <= MAX_WHOLE_DOCUMENT_CHUNKS and [c.get("chunk_index") for c in chunks] == list(range(expected))
            chunks = chunks[:MAX_WHOLE_DOCUMENT_CHUNKS]
            sources = [_source_from_chunk({**chunk, "chunk_id": str(chunk["_id"]), "document_id": str(doc_id)}) for chunk in chunks]
            limitations = [] if complete else ["The document has missing, incomplete, or more indexed chunks than this request can safely process."]
            return {"sources": sources, "document": document, "status": "ready" if sources else "insufficient_evidence", "complete": complete, "limitations": limitations}

        sources = []
        ready_filter = {"workspace_id": workspace["_id"], "status": "ready"}
        if resolution.document:
            ready_filter["_id"] = resolution.document["_id"]
        ready_documents = await db.documents.count_documents(ready_filter)
        if ready_documents:
            try:
                found = await search_workspace_chunks(
                    workspace_id=workspace_id,
                    query=query or "workspace summary",
                    limit=MAX_DOCUMENT_SOURCES * 3 if operation == "project_plan_question" else MAX_DOCUMENT_SOURCES,
                    user=user,
                    max_candidates=MAX_DOCUMENT_CANDIDATES,
                    document_id=str(resolution.document["_id"]) if resolution.document else None,
                )
            except EmbeddingModelUnavailableError as exc:
                raise HTTPException(status_code=503, detail="Workspace document retrieval is temporarily unavailable because the local embedding model is not ready.") from exc
            selected = found["results"]
            if operation == "project_plan_question":
                selected = [
                    item for item in selected
                    if _project_source_role({
                        "source_type": "document",
                        "title": item.get("filename") or "Workspace document",
                        "text": item.get("text") or "",
                    }) == "project_decision"
                ]
            # Include adjacent passages for context, but keep the result bounded and
            # restricted to the same ready document records as semantic search.
            if selected:
                primary = selected[:max(1, MAX_DOCUMENT_SOURCES - 2)]
                ids = {ObjectId(item["document_id"]) for item in selected}
                neighbors = []
                for item in primary[:2]:
                    index = item.get("chunk_index", 0)
                    neighbors.extend([index - 1, index + 1])
                if neighbors:
                    adjacent = [chunk async for chunk in db.chunks.find({
                        "workspace_id": workspace["_id"], "document_id": {"$in": list(ids)},
                        "chunk_index": {"$in": neighbors},
                    }, {"_id": 1, "document_id": 1, "filename": 1, "chunk_index": 1, "text": 1, "page": 1, "created_at": 1})
                    .limit(MAX_DOCUMENT_SOURCES * 2)]
                    selected_ids = {item["chunk_id"] for item in primary}
                    adjacent_sources = [{
                        "chunk_id": str(chunk["_id"]), "document_id": str(chunk["document_id"]),
                        "filename": chunk.get("filename"), "chunk_index": chunk.get("chunk_index", 0),
                        "text": chunk.get("text", ""), "page": chunk.get("page"), "created_at": chunk.get("created_at"),
                        "score": 0.0,
                    } for chunk in adjacent if str(chunk["_id"]) not in selected_ids]
                    selected = primary + adjacent_sources[:MAX_DOCUMENT_SOURCES - len(primary)]
                else:
                    selected = primary
            seen = set()
            for chunk in selected:
                source = _source_from_chunk(chunk)
                key = source["text"].casefold()
                if source["text"] and key not in seen:
                    seen.add(key)
                    sources.append(source)

        query_tokens = {token for token in __import__("re").findall(r"[\w'-]{3,}", query.casefold())}
        if operation == "project_plan_question":
            query_tokens.update({
                "project", "plan", "planned", "selected", "decision", "implementation",
                "implemented", "progress", "completed", "roadmap", "agent", "agents",
                "decided", "chosen", "include", "including", "component", "components",
            })
        cursor = db.messages.find(
            {"workspace_id": workspace["_id"], "message_type": {"$ne": "private"}, **({"_id": {"$ne": exclude_message_id}} if exclude_message_id else {})},
            {"_id": 1, "sender_name": 1, "content": 1, "created_at": 1},
        ).sort([("created_at", -1), ("_id", -1)]).limit(
            MAX_CHAT_SCAN * 2 if operation == "project_plan_question" else MAX_CHAT_SCAN
        )
        chat = [message async for message in cursor]
        ranked = []
        for message in chat:
            text = " ".join((message.get("content") or "").split())
            tokens = {token for token in __import__("re").findall(r"[\w'-]{3,}", text.casefold())}
            score = len(query_tokens & tokens) / max(len(query_tokens | tokens), 1)
            if not query_tokens or score > 0:
                ranked.append((score, message, text))
        if operation == "project_plan_question":
            ranked.sort(key=lambda row: (
                _project_source_role({
                    "source_type": "chat_message",
                    "title": row[1].get("sender_name") or "Workspace member",
                    "text": row[2],
                }) == "project_decision",
                row[0],
                row[1].get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
            ), reverse=True)
        else:
            ranked.sort(key=lambda row: (row[0], row[1].get("created_at") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        for score, message, text in ranked[:MAX_CHAT_SOURCES]:
            sources.append({
                "citation_id": f"chat:{message['_id']}", "source_type": "chat_message", "source_id": str(message["_id"]),
                "title": message.get("sender_name") or "Workspace member", "created_at": _timestamp(message.get("created_at")),
                "score": round(score, 4), "text": text[:MAX_SOURCE_CHARS],
            })
        if operation == "project_plan_question":
            sources = select_project_plan_sources(sources)
            if not sources:
                message = (
                    "I couldn't find an explicit project plan or implementation-status decision in this workspace. "
                    "Research-paper related work can describe external frameworks, but it doesn't establish what this "
                    "project selected or implemented. Share the project plan or a team decision and I can summarize it."
                )
                return {
                    "sources": [], "document": resolution.document, "message": message,
                    "status": "project_plan_not_found", "complete": False,
                    "limitations": ["No authoritative project-plan source was found in this workspace."],
                }

        bounded, total = [], 0
        for source in sources:
            remaining = MAX_TOTAL_CONTEXT_CHARS - total
            if remaining <= 0:
                break
            source["text"] = source["text"][:remaining]
            if source["text"]:
                bounded.append(source)
                total += len(source["text"])
        return {"sources": bounded, "document": resolution.document, "status": "ready" if bounded else "insufficient_evidence", "complete": None, "limitations": []}
