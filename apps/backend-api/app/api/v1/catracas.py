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


@router.get("/catracas/presentes")
async def presentes(detalhado: bool = True) -> dict:
    """Quem esta na instituicao agora, segundo as catracas.

    Vem do espelho replicado, nao do motor de presenca: aqui e circulacao no
    predio - inclusive de quem nao tem aula agora - e nao ocupacao de sala.
    """
    from app.core.config import settings

    if not settings.DATABASE_URL:
        raise HTTPException(
            503, "Sem DATABASE_URL: a leitura das catracas exige o banco."
        )

    from app.data import catraca_repository as repo

    if not await repo.disponivel():
        raise HTTPException(
            503,
            "Nenhuma marcacao replicada ainda. Verifique o job de replicacao "
            "no SQL Server (ver docs/catracas-replicacao.md).",
        )

    agora = clock.agora()
    resumo = await repo.resumo_presenca(agora)
    ultima = await repo.ultima_marcacao()

    # Replicacao parada e campus vazio dao a mesma contagem: zero. A diferenca
    # so aparece olhando quando foi a ultima marcacao a chegar - por isso ela
    # sai junto, e nao num endpoint de diagnostico que ninguem consulta.
    atraso_min = None
    if ultima:
        atraso_min = max(0, int((agora - ultima).total_seconds() // 60))

    corpo = {
        **resumo,
        "momento": agora.isoformat(),
        "ultima_marcacao": ultima.isoformat() if ultima else None,
        "atraso_replicacao_min": atraso_min,
    }
    if detalhado:
        corpo["pessoas"] = await repo.presentes_agora(agora)
    return corpo


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
