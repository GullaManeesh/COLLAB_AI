"""Resolve explicit document references only inside the caller's workspace."""

import re
from dataclasses import dataclass

from bson import ObjectId

from app.database.mongodb import get_database
from app.services.chat_service import get_workspace_for_member


@dataclass
class DocumentResolution:
    document: dict | None = None
    message: str | None = None
    status: str = "resolved"
    explicit: bool = False


def _reference_from_text(text: str, *, already_extracted: bool = False) -> str | None:
    filename = re.search(r"[\w .()'_-]+\.(?:pdf|docx?|txt|md)\b", text, re.I)
    if filename:
        return filename.group(0).strip()
    quoted = re.search(r"[\"'“](.{2,160}?)[\"'”]", text)
    if quoted:
        return quoted.group(1).strip()
    named = re.search(r"\b(?:document|file|paper)\s+(?:named|called|titled)\s+(.+?)(?=[?.!,;]|$)", text, re.I)
    if named:
        value = named.group(1).strip().strip("\"'“”")
        value = re.sub(r"\b(?:about|on|for|that|which)\b.*$", "", value, flags=re.I).strip()
        return value or None
    if already_extracted and len(text.split()) <= 8:
        # Caller may have already extracted a reference such as “CollabAI paper”.
        return text.strip().strip("\"'“”")
    return None


async def resolve_document_reference(workspace_id: str, user: dict, request: str, documents: list[dict] | None = None, *, already_extracted: bool = False) -> DocumentResolution:
    workspace = await get_workspace_for_member(workspace_id, user)
    db = get_database()
    id_matches = re.findall(r"(?<![0-9a-f])[0-9a-f]{24}(?![0-9a-f])", request, re.I)
    if documents is None:
        if id_matches:
            document = await db.documents.find_one(
                {"_id": ObjectId(id_matches[0]), "workspace_id": workspace["_id"]},
                {"_id": 1, "filename": 1, "status": 1, "chunk_count": 1, "embedding_model": 1},
            )
            documents = [document] if document else []
        else:
            documents = [doc async for doc in db.documents.find(
                {"workspace_id": workspace["_id"]},
                {"_id": 1, "filename": 1, "status": 1, "chunk_count": 1, "embedding_model": 1},
            ).limit(500)]

    reference = _reference_from_text(request, already_extracted=already_extracted)
    # Exact workspace document titles and IDs are authoritative; never search globally.
    if id_matches:
        matches = [doc for doc in documents if str(doc.get("_id", "")).lower() == id_matches[0].lower()]
        reference = id_matches[0]
    else:
        normalized = request.casefold()
        exact_titles = [doc for doc in documents if doc.get("filename") and doc["filename"].casefold() in normalized]
        if exact_titles:
            longest = max(len(doc["filename"]) for doc in exact_titles)
            matches = [doc for doc in exact_titles if len(doc["filename"]) == longest]
            reference = matches[0]["filename"] if len(matches) == 1 else reference
        elif reference:
            ref = reference.casefold().strip()
            matches = [doc for doc in documents if doc.get("filename", "").casefold().strip() == ref]
            if not matches:
                # Allow a clear stem reference (e.g. “CollabAI paper” for CollabAI.pdf),
                # but require substantial token overlap to avoid guessing from topic words.
                ref_tokens = {t for t in re.findall(r"[a-z0-9]+", ref) if t not in {"document", "file", "paper"}}
                ranked = []
                for doc in documents:
                    title = doc.get("filename", "")
                    title_tokens = {t for t in re.findall(r"[a-z0-9]+", title.casefold()) if t not in {"document", "file", "paper"}}
                    overlap = len(ref_tokens & title_tokens)
                    if overlap and overlap / max(len(ref_tokens), len(title_tokens), 1) >= 0.5:
                        ranked.append((overlap, title, doc))
                if ranked:
                    best = max(item[0] for item in ranked)
                    matches = [item[2] for item in ranked if item[0] == best]
                else:
                    matches = []
        else:
            matches = []

    explicit = bool(reference) or bool(matches)
    if not explicit:
        return DocumentResolution(explicit=False)
    if not matches:
        return DocumentResolution(
            message=f"I couldn't find a document matching '{reference}' in this workspace. Check the document name or choose a document from the workspace.",
            status="document_not_found", explicit=True,
        )
    if len(matches) > 1:
        names = ", ".join(sorted(doc.get("filename", "document") for doc in matches[:5]))
        return DocumentResolution(
            message=f"I found multiple documents matching '{reference}': {names}. Please mention the exact file name.",
            status="document_ambiguous", explicit=True,
        )
    document = matches[0]
    if document.get("status") != "ready":
        return DocumentResolution(
            document=document,
            message=f"'{document.get('filename', 'That document')}' is still being indexed or could not be indexed. Try again after its status is ready.",
            status="document_unavailable", explicit=True,
        )
    return DocumentResolution(document=document, explicit=True)
