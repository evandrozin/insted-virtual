"""Hub de tempo real.

Cada instancia mantem suas proprias conexoes WebSocket. Toda mensagem sai pelo
store (`publicar`), que a devolve a *todas* as instancias - inclusive a que
publicou - e o relay abaixo a entrega aos painels locais.

Em memoria o caminho e direto; com Redis ele passa pelo canal pub/sub, e o
painel ligado na instancia A recebe a passagem lida na instancia B.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, List

from fastapi import WebSocket


def json_seguro(payload: Any) -> str:
    """Serializa datetime/Enum/Pydantic/set sem estourar no json padrao."""
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
        await websocket.send_text(json_seguro(message))

    async def broadcast(self, message: Any) -> None:
        """Entrega apenas as conexoes desta instancia.

        Para alcancar todas as instancias use `difundir`.
        """
        if not self.active_connections:
            return

        texto = message if isinstance(message, str) else json_seguro(message)
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


async def difundir(payload: Any) -> None:
    """Envia para os painels de todas as instancias."""
    from app.services.store import obter_store

    await obter_store().publicar(payload)


async def iniciar_relay() -> None:
    """Liga o canal do store as conexoes locais. Chamado no boot."""
    from app.services.store import obter_store

    async def entregar(payload: Any) -> None:
        await manager.broadcast(payload)

    await obter_store().assinar(entregar)
