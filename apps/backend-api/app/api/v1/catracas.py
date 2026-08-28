"""Ingestao de eventos de catraca (webhook HTTP)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.core import clock
from app.models.academico import EventoCatraca
from app.services.campus_state import estado
from app.services.presence_engine import motor
from app.services.realtime import difundir
from app.services.store import obter_store

router = APIRouter(tags=["catracas"])


async def ingerir(evento: EventoCatraca) -> dict:
    """Processa a passagem e difunde para os painels de todas as instancias."""
    if evento.timestamp is None:
        evento.timestamp = clock.agora()
    resultado = await motor.processar_evento(evento)
    await difundir(resultado)
    return resultado


@router.post("/catracas/evento")
async def receber_evento(evento: EventoCatraca) -> dict:
    """Webhook chamado pelo controlador de acesso a cada passagem."""
    if evento.catraca_id not in estado.catracas:
        raise HTTPException(404, f"Catraca desconhecida: {evento.catraca_id}")
    return await ingerir(evento)


@router.post("/catracas/lote")
async def receber_lote(eventos: List[EventoCatraca]) -> dict:
    """Reprocessamento em lote apos queda de rede da controladora."""
    processados = 0
    for evento in eventos:
        if evento.catraca_id in estado.catracas:
            await ingerir(evento)
            processados += 1
    return {"recebidos": len(eventos), "processados": processados}


@router.get("/catracas")
async def listar_catracas() -> dict:
    store = obter_store()
    estado.atualizar_catracas(await store.estado_catracas())
    contadores = await store.contadores()
    return {
        "catracas": [c.model_dump() for c in estado.catracas.values()],
        "total_entradas": contadores["entradas"],
        "total_saidas": contadores["saidas"],
    }
