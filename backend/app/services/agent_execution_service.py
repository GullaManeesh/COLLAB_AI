import logging
import asyncio
import time
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.agents import SummarizerRequest
from app.agents.registry import get_agent
from app.agents.summarizer.strategies import interpret_request
from app.agents.context.context_engine import ContextEngine
from app.services.chat_connection_manager import chat_manager
from app.services.chat_service import save_agent_message, save_team_message, get_workspace_for_member
from app.services.groq_service import GroqConfigurationError, GroqProviderError

logger = logging.getLogger(__name__)
STALE_RUN_AFTER = timedelta(minutes=5)
RATE_LIMIT_WINDOW = timedelta(minutes=10)
RATE_LIMIT_MAX_RUNS = 5


def _run_payload(run: dict, request_message: dict | None = None, agent_message: dict | None = None) -> dict:
    return {
        "run_id": str(run.get("_id", run.get("run_id"))),
        "status": run["status"],
        "request_message": request_message,
        "agent_message": agent_message,
    }


async def recover_stale_agent_runs() -> int:
    """Close interrupted synchronous runs after a bounded safety window."""
    db = get_database()
    cutoff = datetime.now(timezone.utc) - STALE_RUN_AFTER
    result = await db.agent_runs.update_many(
        {"status": {"$in": ["pending", "running"]}, "started_at": {"$lt": cutoff}},
        {"$set": {
            "status": "failed",
            "error_category": "execution_interrupted",
            "completed_at": datetime.now(timezone.utc),
        }},
    )
    return result.modified_count


async def execute_summarizer_request(
    workspace_id: str,
    payload: SummarizerRequest,
    user: dict,
):
    # Validate the explicit command and request scope before creating a run record.
    interpret_request(payload.content)
    workspace = await get_workspace_for_member(workspace_id, user)
    db = get_database()
    now = datetime.now(timezone.utc)
    run = {
        "workspace_id": workspace["_id"],
        "requesting_user_id": user["_id"],
        "agent_type": "summarizer",
        "client_request_id": payload.client_request_id,
        "status": "pending",
        "model": settings.GROQ_MODEL,
        "created_at": now,
        "started_at": now,
        "completed_at": None,
        "source_refs": [],
    }
    try:
        inserted = await db.agent_runs.insert_one(run)
        run["_id"] = inserted.inserted_id
    except DuplicateKeyError:
        existing = await db.agent_runs.find_one({
            "workspace_id": workspace["_id"],
            "requesting_user_id": user["_id"],
            "client_request_id": payload.client_request_id,
        })
        if existing is None:
            raise HTTPException(status_code=409, detail="This summarization request is already being processed.")
        started_at = existing.get("started_at")
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if existing.get("status") in {"pending", "running"} and started_at and started_at < datetime.now(timezone.utc) - STALE_RUN_AFTER:
            await db.agent_runs.update_one(
                {"_id": existing["_id"], "status": {"$in": ["pending", "running"]}},
                {"$set": {"status": "failed", "error_category": "execution_interrupted", "completed_at": datetime.now(timezone.utc)}},
            )
            raise HTTPException(status_code=409, detail="The previous summarization was interrupted. Submit it again.")
        if existing.get("status") == "succeeded" and existing.get("response_message_id"):
            if existing.get("source_refs") and not await ContextEngine().sources_are_current(
                workspace_id=workspace_id, user=user, sources=existing["source_refs"]
            ):
                raise HTTPException(status_code=409, detail="The earlier response used source content that is no longer available. Submit a new request using the current workspace documents.")
            agent_message = await db.messages.find_one({"_id": existing["response_message_id"], "workspace_id": workspace["_id"]})
            request_message = None
            if existing.get("request_message_id"):
                request_message = await db.messages.find_one({"_id": existing["request_message_id"], "workspace_id": workspace["_id"]})
            from app.services.chat_service import serialize_message
            return _run_payload(
                existing,
                serialize_message(request_message) if request_message else None,
                serialize_message(agent_message) if agent_message else None,
            )
        if existing.get("status") == "failed":
            raise HTTPException(status_code=409, detail="This request already failed. Send it again to retry.")
        request_message = None
        if existing.get("request_message_id"):
            request_message = await db.messages.find_one({"_id": existing["request_message_id"], "workspace_id": workspace["_id"]})
        from app.services.chat_service import serialize_message
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=_run_payload(existing, serialize_message(request_message) if request_message else None),
        )

    bucket_seconds = int(RATE_LIMIT_WINDOW.total_seconds())
    bucket = int(now.timestamp()) // bucket_seconds
    rate_key = f"{workspace['_id']}:{user['_id']}:{bucket}"
    window_end = datetime.fromtimestamp((bucket + 1) * bucket_seconds, tz=timezone.utc)
    try:
        await db.agent_rate_limits.update_one(
            {"_id": rate_key},
            {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": window_end}},
            upsert=True,
        )
        rate_record = await db.agent_rate_limits.find_one({"_id": rate_key}, {"count": 1})
    except Exception as exc:
        await db.agent_runs.update_one(
            {"_id": run["_id"], "status": "pending"},
            {"$set": {"status": "failed", "error_category": "rate_limit_storage", "completed_at": datetime.now(timezone.utc)}},
        )
        logger.warning("Summarizer rate check unavailable run_id=%s cause=%s", run["_id"], type(exc).__name__)
        raise HTTPException(status_code=503, detail="Summarizer is temporarily unavailable. Please retry shortly.") from exc
    if rate_record and rate_record.get("count", 0) > RATE_LIMIT_MAX_RUNS:
        await db.agent_runs.update_one(
            {"_id": run["_id"], "status": "pending"},
            {"$set": {"status": "failed", "error_category": "rate_limited", "completed_at": datetime.now(timezone.utc)}},
        )
        raise HTTPException(status_code=429, detail="Summarizer rate limit reached. Please wait a few minutes and try again.")

    await db.agent_runs.update_one({"_id": run["_id"], "status": "pending"}, {"$set": {"status": "running"}})
    event_base = {
        "type": "agent.run",
        "workspace_id": workspace_id,
        "run_id": str(run["_id"]),
        "client_request_id": payload.client_request_id,
        "agent_type": "summarizer",
    }
    started = time.monotonic()
    request_message = None
    try:
        await chat_manager.broadcast_authorized(workspace_id, {**event_base, "status": "running"})
        request_message = await save_team_message(
            workspace_id,
            user,
            payload.content,
            client_message_id=payload.client_request_id,
            authorized_delivery=True,
        )
        request_message_id = ObjectId(request_message["id"])
        await db.agent_runs.update_one({"_id": run["_id"]}, {"$set": {"request_message_id": request_message_id}})

        result = await get_agent("summarizer").execute(
            workspace_id=workspace_id,
            user=user,
            content=payload.content,
            exclude_message_id=request_message_id,
        )
        # Recheck access before persistence and delivery. A removed requester must
        # not trigger or publish a workspace-wide answer.
        await get_workspace_for_member(workspace_id, user)
        agent_message = await save_agent_message(
            workspace_id,
            user,
            result.summary,
            agent_type="summarizer",
            sources=result.sources,
            assessment=result.assessment,
            explanation=result.explanation,
            coverage=result.coverage,
            limitations=result.limitations,
        )
        completed_at = datetime.now(timezone.utc)
        update = {
            "status": "succeeded",
            "completed_at": completed_at,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "source_refs": result.sources,
            "response_message_id": ObjectId(agent_message["id"]),
            "model": result.completion.model if result.completion else settings.GROQ_MODEL,
            "assessment": result.assessment,
            "coverage": result.coverage,
        }
        if result.completion:
            update["prompt_tokens"] = result.completion.prompt_tokens
            update["completion_tokens"] = result.completion.completion_tokens
        await db.agent_runs.update_one({"_id": run["_id"], "status": "running"}, {"$set": update})
        await chat_manager.broadcast_authorized(
            workspace_id,
            {**event_base, "status": "succeeded", "message_id": agent_message["id"]},
        )
        return _run_payload(run, request_message, agent_message) | {"status": "succeeded"}
    except asyncio.CancelledError:
        await db.agent_runs.update_one(
            {"_id": run["_id"], "status": {"$in": ["pending", "running"]}},
            {"$set": {
                "status": "failed",
                "error_category": "request_cancelled",
                "completed_at": datetime.now(timezone.utc),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }},
        )
        raise
    except Exception as exc:
        category = "internal_error"
        http_status = 500
        detail = "Summarization failed. Please try again."
        if isinstance(exc, GroqConfigurationError):
            category, http_status, detail = "provider_configuration", 503, str(exc)
        elif isinstance(exc, GroqProviderError):
            category = exc.category
            http_status = 504 if category == "provider_timeout" else 503 if exc.retryable or category == "provider_configuration" else 502
            detail = str(exc)
        elif isinstance(exc, TimeoutError):
            category, http_status, detail = "execution_deadline", 504, "Summarization reached its processing deadline. No complete response was saved; please retry with a smaller scope."
        elif isinstance(exc, HTTPException):
            category = "workspace_access" if exc.status_code in {403, 404} else "context_unavailable"
            http_status = exc.status_code
            detail = str(exc.detail)
        logger.warning("Summarizer run failed run_id=%s category=%s", run["_id"], category)
        completed_at = datetime.now(timezone.utc)
        await db.agent_runs.update_one(
            {"_id": run["_id"], "status": {"$in": ["pending", "running"]}},
            {"$set": {
                "status": "failed",
                "error_category": category,
                "completed_at": completed_at,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }},
        )
        await chat_manager.broadcast_authorized(
            workspace_id,
            {**event_base, "status": "failed", "error_category": category, "message": detail},
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=http_status, detail=detail) from exc
