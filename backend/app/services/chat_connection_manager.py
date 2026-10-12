
import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ChatConnectionManager:
    """Manage active team-chat WebSocket connections per workspace."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, workspace_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[workspace_id].add(websocket)
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

    @staticmethod
    async def _send_one(websocket: WebSocket, event: dict) -> None:
        await websocket.send_json(event)


chat_manager = ChatConnectionManager()
