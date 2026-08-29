"""Insted Virtual Campus - API do Motor de Ocupacao e Presenca em Tempo Real."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    academico, alocacao, cadastro, catracas, cron, presenca, ws
)
from app.core import clock
from app.core.config import settings
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor
from app.services.realtime import difundir, iniciar_relay, manager
from app.services.store import obter_store

_tarefas: list[asyncio.Task] = []


async def _loop_reconciliacao() -> None:
    """Bate a grade horaria contra o relogio e empurra o tick do dashboard.

    Em serverless este loop nao sobrevive entre requisicoes: use o Vercel Cron
    apontando para /api/v1/cron/reconciliar.
    """
    while True:
        try:
            deltas = await motor.reconciliar()
            payload = {
                "tipo": "DASHBOARD_TICK",
                "servidor_em": clock.agora(),
                "dashboard": await servico_dashboard.snapshot(),
            }
            if deltas:
                payload["deltas"] = deltas
            await difundir(payload)
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
    store = obter_store()
    await store.iniciar()
    print(f"[boot] estado compartilhado: {store.nome}")

    await clock.inicializar(store)
    print(f"[boot] relogio: {clock.descricao()}")

    await _carregar_topologia()

    resumo = motor.sincronizar_jacad()
    print(f"[boot] JACAD carregado: {resumo}")

    # Entrega ao painel local tudo que circula no canal (proprio ou de outra
    # instancia); e o que mantem a projecao das carteiras alinhada.
    await iniciar_relay()
    await _assinar_deltas()

    recuperadas = await motor.reidratar()
    if recuperadas:
        print(f"[boot] reidratou {recuperadas} presencas do estado compartilhado")

    await motor.reconciliar()

    if settings.SIMULADOR_ATIVO:
        from app.simulator.catraca_simulator import simulador

        semeados = await simulador.semear_campus(clock.agora())
        print(f"[boot] simulador semeou {semeados} passagens")
        _tarefas.append(asyncio.create_task(simulador.rodar()))

    if settings.LOOP_INTERNO:
        _tarefas.append(asyncio.create_task(_loop_reconciliacao()))
        _tarefas.append(asyncio.create_task(_loop_sync_jacad()))
    else:
        print("[boot] loops internos desligados: use /api/v1/cron/reconciliar")

    yield

    for tarefa in _tarefas:
        tarefa.cancel()
    await asyncio.gather(*_tarefas, return_exceptions=True)
    await store.encerrar()


async def _carregar_topologia() -> None:
    """Le o cadastro de salas do Postgres, se houver banco configurado.

    Sem DATABASE_URL - ou se o banco falhar - segue valendo o seed extraido
    das plantas, que ja esta carregado. Um cadastro fora do ar nao pode
    derrubar o painel da diretoria.
    """
    if not settings.DATABASE_URL:
        print("[boot] topologia: seed das plantas (sem DATABASE_URL)")
        return

    from app.data.sala_repository import carregar_topologia

    try:
        pavimentos = await carregar_topologia(
            settings.DATABASE_URL, settings.PREDIO_CODIGO
        )
    except Exception as erro:
        print(f"[boot] topologia: falha no cadastro ({erro}); usando o seed")
        return

    estado.carregar_topologia(pavimentos)
    ambientes = sum(len(p.salas) for p in pavimentos)
    print(
        f"[boot] topologia: cadastro em banco - {len(pavimentos)} pavimentos, "
        f"{ambientes} ambientes, {estado.capacidade_total()} lugares"
    )


async def _assinar_deltas() -> None:
    """Aplica na projecao local os deltas publicados por qualquer instancia."""

    async def aplicar(payload) -> None:
        if isinstance(payload, dict) and payload.get("deltas"):
            estado.aplicar_deltas(payload["deltas"])

    await obter_store().assinar(aplicar)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Controle de presenca em tempo real do Insted Centro Universitario: "
        "cruza a grade horaria do JACAD com as passagens de catraca e projeta "
        "o resultado na maquete virtual 3D."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    presenca.router, catracas.router, academico.router, alocacao.router,
    cron.router, cadastro.router,
):
    app.include_router(router, prefix=settings.API_V1_PREFIX)

# WebSockets ficam fora do prefixo versionado para simplificar o client.
app.include_router(ws.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {
        "status": "ok",
        "servico": settings.PROJECT_NAME,
        "relogio": clock.agora().isoformat(),
        "estado": obter_store().nome,
        "simulador": settings.SIMULADOR_ATIVO,
        "paineis_conectados": manager.total,
    }
