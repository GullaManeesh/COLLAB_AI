
import asyncio
import json

from bson import ObjectId
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi import HTTPException

from app.config.settings import settings
from app.database.mongodb import get_database
from app.middleware.authentication import CurrentUser
from app.middleware.csrf import CsrfProtected
from app.schemas.chat import ChatHistoryResponse, SendMessageRequest
from app.services.auth_service import get_user_from_session_token
from app.services.chat_service import (
    get_chat_history,
    get_workspace_for_member,
    save_team_message,
)
from app.services.chat_connection_manager import chat_manager


router = APIRouter(tags=["Team Chat"])


@router.get(
    "/workspaces/{workspace_id}/messages",
    response_model=ChatHistoryResponse,
)
async def chat_history_route(
    workspace_id: str,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None),
):
    return await get_chat_history(workspace_id, user, limit, before)


@router.post("/workspaces/{workspace_id}/messages")
async def send_message_route(
    workspace_id: str,
    payload: SendMessageRequest,
    user: CurrentUser,
    _: None = CsrfProtected,
):
    try:
        return await save_team_message(workspace_id, user, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.websocket("/ws/workspaces/{workspace_id}/chat")
async def team_chat_websocket(
    websocket: WebSocket,
    workspace_id: str,
):
    session_token = websocket.cookies.get(settings.SESSION_COOKIE_NAME)

    if not session_token:
        await websocket.close(code=1008, reason="Authentication required")
        return

    try:
        user = await get_user_from_session_token(session_token)
    except Exception:
        await websocket.close(code=1011, reason="Authentication service unavailable")
        return

    if user is None:
        await websocket.close(code=1008, reason="Session expired")
        return

    try:
        await get_workspace_for_member(workspace_id, user)
    except HTTPException:
        await websocket.close(code=1008, reason="Workspace access denied")
        return
    except Exception:
        await websocket.close(code=1011, reason="Unable to verify workspace access")
        return

    await chat_manager.connect(workspace_id, websocket, str(user["_id"]))

    try:
        await websocket.send_json({"type": "connected"})

        while True:
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                try:
                    await get_workspace_for_member(workspace_id, user)
                except HTTPException:
                    await websocket.close(code=1008, reason="Workspace access revoked")
                    return
                await websocket.send_json({"type": "ping"})
                continue

            try:
                event = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON event",
                })
                continue

            if isinstance(event, dict) and event.get("type") == "pong":
                continue

            if not isinstance(event, dict) or event.get("type") != "send_message":
                await websocket.send_json({
                    "type": "error",
                    "message": "Unsupported event type",
                })
                continue

            content = event.get("content")
            if not isinstance(content, str):
                await websocket.send_json({
                    "type": "error",
                    "message": "Message content must be text",
                })
                continue

            client_message_id = event.get("client_message_id")
            if (
                client_message_id is not None
                and (
                    not isinstance(client_message_id, str)
                    or len(client_message_id) > 100
                )
            ):
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid client message ID",
                })
                continue

            try:
                await save_team_message(
                    workspace_id=workspace_id,
                    user=user,
                    content=content,
                    client_message_id=client_message_id,
                )
            except ValueError as exc:
                await websocket.send_json({
                    "type": "error",
                    "message": str(exc),
                })
            except HTTPException:
                await websocket.close(code=1008, reason="Workspace access denied")
                return

    except WebSocketDisconnect:
        pass
    finally:
        await chat_manager.disconnect(workspace_id, websocket)
