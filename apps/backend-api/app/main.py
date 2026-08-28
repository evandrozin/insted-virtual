"""Insted Virtual Campus - API do Motor de Ocupacao e Presenca em Tempo Real."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import academico, alocacao, catracas, presenca, ws
from app.core import clock
from app.core.config import settings
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor
from app.services.realtime import manager

_tarefas: list[asyncio.Task] = []


async def _loop_reconciliacao() -> None:
    """Bate a grade horaria contra o relogio e empurra o tick do dashboard."""
    while True:
        try:
            deltas = motor.reconciliar()
            payload = {
                "tipo": "DASHBOARD_TICK",
                "servidor_em": clock.agora(),
                "dashboard": servico_dashboard.snapshot(),
            }
            if deltas:
                payload["deltas"] = deltas
            await manager.broadcast(payload)
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(f"[reconciliacao] erro ignorado: {erro}")

        await asyncio.sleep(settings.TICK_DASHBOARD_S)


async def _loop_sync_jacad() -> None:
    while True:
        await asyncio.sleep(settings.JACAD_SYNC_INTERVAL_S)
        try:
            resumo = motor.sincronizar_jacad()
            print(f"[jacad] resync: {resumo}")
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(f"[jacad] falha no resync: {erro}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    resumo = motor.sincronizar_jacad()
    print(f"[boot] JACAD carregado: {resumo}")
    print(f"[boot] relogio: {clock.descricao()}")

    motor.reconciliar()

    if settings.SIMULADOR_ATIVO:
        from app.simulator.catraca_simulator import simulador

        semeados = simulador.semear_campus(clock.agora())
        print(f"[boot] simulador semeou {semeados} passagens")
        _tarefas.append(asyncio.create_task(simulador.rodar()))

    _tarefas.append(asyncio.create_task(_loop_reconciliacao()))
    _tarefas.append(asyncio.create_task(_loop_sync_jacad()))

    yield

    for tarefa in _tarefas:
        tarefa.cancel()
    await asyncio.gather(*_tarefas, return_exceptions=True)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Controle de presenca em tempo real do Insted Centro Universitario: "
        "cruza a grade horaria do JACAD com as passagens de catraca e projeta "
        "o resultado na maquete virtual 3D."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (presenca.router, catracas.router, academico.router, alocacao.router):
    app.include_router(router, prefix=settings.API_V1_PREFIX)

# WebSockets ficam fora do prefixo versionado para simplificar o client.
app.include_router(ws.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {
        "status": "ok",
        "servico": settings.PROJECT_NAME,
        "relogio": clock.agora().isoformat(),
        "simulador": settings.SIMULADOR_ATIVO,
        "paineis_conectados": manager.total,
    }
