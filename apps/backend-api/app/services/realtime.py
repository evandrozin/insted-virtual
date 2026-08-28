"""Hub de tempo real: gerencia as conexoes WebSocket e o broadcast."""
from __future__ import annotations

import asyncio
import json
from typing import Any, List

from fastapi import WebSocket


def _json_seguro(payload: Any) -> str:
    """Serializa datetime/Enum/Pydantic sem estourar no json padrao."""
    from datetime import date, datetime, time
    from enum import Enum

    from pydantic import BaseModel

    def default(obj):
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, set):
            return list(obj)
        raise TypeError(f"Nao serializavel: {type(obj)}")

    return json.dumps(payload, default=default, ensure_ascii=False)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def send_personal(self, websocket: WebSocket, message: Any) -> None:
        await websocket.send_text(_json_seguro(message))

    async def broadcast(self, message: Any) -> None:
        if not self.active_connections:
            return

        texto = _json_seguro(message)
        async with self._lock:
            alvos = list(self.active_connections)

        mortos: List[WebSocket] = []
        for conexao in alvos:
            try:
                await conexao.send_text(texto)
            except Exception:
                mortos.append(conexao)

        if mortos:
            async with self._lock:
                for conexao in mortos:
                    if conexao in self.active_connections:
                        self.active_connections.remove(conexao)

    @property
    def total(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()
