
import asyncio
import logging
from collections import defaultdict

from bson import ObjectId
from fastapi import WebSocket

from app.database.mongodb import get_database

logger = logging.getLogger(__name__)


class ChatConnectionManager:
    """Manage active team-chat WebSocket connections per workspace."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._connection_users: dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()

    async def connect(self, workspace_id: str, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[workspace_id].add(websocket)
            self._connection_users[websocket] = str(user_id)
        print(
            f"[CHAT] Connected workspace={workspace_id} "
            f"connections={len(self._connections[workspace_id])}"
        )

    async def disconnect(
        self,
        workspace_id: str,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            connections = self._connections.get(workspace_id)
            if connections is not None:
                connections.discard(websocket)
                self._connection_users.pop(websocket, None)
                if not connections:
                    self._connections.pop(workspace_id, None)
        remaining = len(self._connections.get(workspace_id, set()))
        print(
            f"[CHAT] Disconnected workspace={workspace_id} "
            f"remaining={remaining}"
        )

    async def broadcast(self, workspace_id: str, event: dict) -> None:
        async with self._lock:
            connections = list(self._connections.get(workspace_id, set()))

        if not connections:
            print(f"[CHAT] Broadcasting workspace={workspace_id} recipients=0 (no connections)")
            return

        print(f"[CHAT] Broadcasting workspace={workspace_id} recipients={len(connections)}")

        results = await asyncio.gather(
            *(self._send_one(websocket, event) for websocket in connections),
            return_exceptions=True,
        )

        for websocket, result in zip(connections, results):
            if isinstance(result, Exception):
                print(f"[CHAT] Broadcast send failed workspace={workspace_id}: {result}")
                await self.disconnect(workspace_id, websocket)

    async def broadcast_authorized(self, workspace_id: str, event: dict) -> None:
        """Recheck current workspace membership before agent-event delivery."""
        try:
            workspace_oid = ObjectId(workspace_id)
        except Exception:
            return
        try:
            workspace = await get_database().workspaces.find_one(
                {"_id": workspace_oid},
                {"owner_id": 1, "members.user_id": 1},
            )
        except Exception as exc:
            # Fail closed on delivery, but don't convert a transient notification
            # failure into a failed persisted chat/agent operation.
            logger.warning("Authorized chat delivery skipped workspace=%s cause=%s", workspace_id, type(exc).__name__)
            return
        if workspace is None:
            return
        authorized_ids = {str(workspace.get("owner_id"))}
        authorized_ids.update(str(member.get("user_id")) for member in workspace.get("members", []))
        async with self._lock:
            connections = [
                socket for socket in self._connections.get(workspace_id, set())
                if self._connection_users.get(socket) in authorized_ids
            ]
        results = await asyncio.gather(
            *(self._send_one(websocket, event) for websocket in connections),
            return_exceptions=True,
        )
        for websocket, result in zip(connections, results):
            if isinstance(result, Exception):
                await self.disconnect(workspace_id, websocket)

    @staticmethod
    async def _send_one(websocket: WebSocket, event: dict) -> None:
        await websocket.send_json(event)


chat_manager = ChatConnectionManager()
