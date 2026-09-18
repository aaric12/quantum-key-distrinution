"""WebSocket support for streaming live QKD run updates to the frontend."""

from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Tracks connected sockets per channel (e.g. a QKD run id)."""

    def __init__(self) -> None:
        self.active: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        self.active[channel].add(ws)

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        self.active[channel].discard(ws)
        if not self.active[channel]:
            del self.active[channel]

    async def broadcast(self, channel: str, message: str) -> None:
        for ws in list(self.active.get(channel, ())):
            await ws.send_text(message)


manager = ConnectionManager()


@router.websocket("/ws/{channel}")
async def ws_endpoint(ws: WebSocket, channel: str) -> None:
    await manager.connect(channel, ws)
    try:
        while True:
            text = await ws.receive_text()
            # Echo for now; replace with protocol run events later.
            await manager.broadcast(channel, f"{channel}: {text}")
    except WebSocketDisconnect:
        manager.disconnect(channel, ws)
