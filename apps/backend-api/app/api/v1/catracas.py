"""Ingestao de eventos de catraca: webhook HTTP e canal WebSocket."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.core import clock
from app.models.academico import EventoCatraca
from app.services.campus_state import estado
from app.services.presence_engine import motor
from app.services.realtime import manager

router = APIRouter(tags=["catracas"])


async def _ingerir(evento: EventoCatraca) -> dict:
    if evento.timestamp is None:
        evento.timestamp = clock.agora()
    resultado = motor.processar_evento(evento)
    await manager.broadcast(resultado)
    return resultado


@router.post("/catracas/evento")
async def receber_evento(evento: EventoCatraca) -> dict:
    """Webhook chamado pelo controlador de acesso a cada passagem."""
    if evento.catraca_id not in estado.catracas:
        raise HTTPException(404, f"Catraca desconhecida: {evento.catraca_id}")
    return await _ingerir(evento)


@router.post("/catracas/lote")
async def receber_lote(eventos: List[EventoCatraca]) -> dict:
    """Reprocessamento em lote apos queda de rede da controladora."""
    processados = 0
    for evento in eventos:
        if evento.catraca_id in estado.catracas:
            await _ingerir(evento)
            processados += 1
    return {"recebidos": len(eventos), "processados": processados}


@router.get("/catracas")
async def listar_catracas() -> dict:
    return {
        "catracas": [c.model_dump() for c in estado.catracas.values()],
        "total_entradas": estado.total_entradas,
        "total_saidas": estado.total_saidas,
    }
