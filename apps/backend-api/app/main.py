"""Insted Virtual Campus - API do Motor de Ocupacao e Presenca em Tempo Real."""
from __future__ import annotations

import asyncio
import traceback
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    academico, alocacao, cadastro, catracas, configuracao, cron, presenca, ws
)
from app.core import clock, parametros
from app.core.config import settings
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor
from app.services.realtime import difundir, iniciar_relay, manager
from app.services.store import obter_store

VERSAO = "2.0.0"

_tarefas: list[asyncio.Task] = []

# Falhas da partida ficam registradas aqui e aparecem no /health, em vez de
# derrubar o processo. Na Vercel uma excecao no lifespan vira
# FUNCTION_INVOCATION_FAILED: 500 sem corpo, sem dizer o que quebrou, em todas
# as rotas - inclusive no /health, justo quem existe para responder isso. Um
# painel degradado que aponta o problema vale mais que um 500 mudo.
_falhas_boot: list[dict] = []

# A grade do ERP real custa alguns minutos - uma chamada por disciplina. Prender
# o boot nela faria o health check da plataforma derrubar o deploy antes de o
# app existir. Entao ela carrega em segundo plano, e este dicionario deixa o
# /health e o painel dizerem em que pe esta, em vez de mostrar campus vazio sem
# explicacao.
_grade: dict = {"estado": "pendente", "aulas": 0, "erro": None, "concluida_em": None}


@contextmanager
def _etapa(nome: str):
    """Isola uma etapa da partida: se cair, anota e deixa o resto subir."""
    try:
        yield
    except Exception as erro:
        _falhas_boot.append({"etapa": nome, "erro": f"{type(erro).__name__}: {erro}"})
        print(f"[boot] FALHA em {nome}: {type(erro).__name__}: {erro}")
        traceback.print_exc()


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

        await asyncio.sleep(parametros.tick_dashboard_s())


async def _loop_catracas() -> None:
    """Traz as passagens replicadas para dentro do motor de presenca.

    Substitui o simulador quando ha catraca de verdade. A cadencia acompanha o
    job de replicacao: adiantar nao traz nada, porque o dado so aparece aqui
    depois que o SQL Server o empurra.
    """
    from app.services.catraca_feed import alimentador

    while True:
        try:
            resumo = await alimentador.ciclo()
            if resumo["passagens"]:
                print(f"[catracas] {resumo['passagens']} passagem(ns) processada(s)")
                await difundir({
                    "tipo": "DASHBOARD_TICK",
                    "servidor_em": clock.agora(),
                    "dashboard": await servico_dashboard.snapshot(),
                    **({"deltas": resumo["deltas"]} if resumo["deltas"] else {}),
                })
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            alimentador.erro = f"{type(erro).__name__}: {erro}"
            print(f"[catracas] falha no ciclo: {alimentador.erro}")

        await asyncio.sleep(parametros.tick_catracas_s())


async def _loop_sync_jacad() -> None:
    while True:
        await asyncio.sleep(parametros.jacad_sync_interval_s())
        try:
            resumo = await asyncio.to_thread(motor.sincronizar_jacad, True)
            _grade.update(estado="pronta", aulas=resumo["aulas"],
                          concluida_em=clock.agora().isoformat())
            from app.services.cadastro_pessoas import espelhar

            resumo["cadastro"] = await espelhar()
            print(f"[jacad] resync: {resumo}")
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(f"[jacad] falha no resync: {erro}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = obter_store()

    with _etapa("estado compartilhado"):
        await store.iniciar()
        print(f"[boot] estado compartilhado: {store.nome}")

    with _etapa("relogio"):
        await clock.inicializar(store)
        print(f"[boot] relogio: {clock.descricao()}")

    with _etapa("parametros"):
        carregados = await parametros.recarregar()
        print(f"[boot] parametros vindos do banco: {carregados}")

    with _etapa("topologia"):
        await _carregar_topologia()

    with _etapa("JACAD"):
        # Sem a grade, e fora do event loop: o client e sincrono, e chama-lo
        # aqui direto travaria todas as conexoes durante a consulta.
        resumo = await asyncio.to_thread(motor.sincronizar_jacad, False)
        print(f"[boot] JACAD carregado: {resumo}")

    # Etapa propria: o espelho do cadastro depende do banco, e uma falha nele
    # nao pode impedir o campus de aparecer na tela.
    with _etapa("espelho de pessoas"):
        from app.services.cadastro_pessoas import espelhar

        espelho = await espelhar()
        if espelho.get("aplicado"):
            print(f"[boot] pessoas espelhadas: {espelho['por_tipo']}")
        else:
            print(f"[boot] pessoas nao espelhadas: {espelho.get('motivo')}")

    # Entrega ao painel local tudo que circula no canal (proprio ou de outra
    # instancia); e o que mantem a projecao das carteiras alinhada.
    with _etapa("relay de tempo real"):
        await iniciar_relay()
        await _assinar_deltas()

    with _etapa("reidratacao"):
        recuperadas = await motor.reidratar()
        if recuperadas:
            print(f"[boot] reidratou {recuperadas} presencas do estado compartilhado")

    with _etapa("reconciliacao inicial"):
        await motor.reconciliar()

    if settings.SIMULADOR_ATIVO:
        with _etapa("simulador"):
            from app.simulator.catraca_simulator import simulador

            semeados = await simulador.semear_campus(clock.agora())
            print(f"[boot] simulador semeou {semeados} passagens")
            _tarefas.append(asyncio.create_task(simulador.rodar()))

    _tarefas.append(asyncio.create_task(_carregar_grade()))

    if _falhas_boot:
        print(f"[boot] subiu com {len(_falhas_boot)} etapa(s) com falha; "
              f"veja /health")

    # As catracas alimentam o motor quando o simulador esta desligado e ha
    # espelho replicado. Ligar os dois juntos misturaria passagem real com
    # inventada no mesmo painel.
    if not settings.SIMULADOR_ATIVO and settings.DATABASE_URL:
        _tarefas.append(asyncio.create_task(_loop_catracas()))
        print("[boot] passagens vindas das catracas replicadas")

    if settings.LOOP_INTERNO:
        _tarefas.append(asyncio.create_task(_loop_reconciliacao()))
        _tarefas.append(asyncio.create_task(_loop_sync_jacad()))
    else:
        print("[boot] loops internos desligados: use /api/v1/cron/reconciliar")

    yield

    for tarefa in _tarefas:
        tarefa.cancel()
    await asyncio.gather(*_tarefas, return_exceptions=True)
    with _etapa("encerramento"):
        await store.encerrar()


async def _carregar_grade() -> None:
    """Monta a grade horaria em segundo plano e avisa o painel quando chega."""
    _grade["estado"] = "carregando"
    try:
        resumo = await asyncio.to_thread(motor.sincronizar_jacad, True)
        _grade.update(
            estado="pronta",
            aulas=resumo["aulas"],
            erro=None,
            concluida_em=clock.agora().isoformat(),
        )
        print(f"[grade] carregada: {resumo['aulas']} aulas")

        # Com a grade na mao as aulas em andamento precisam abrir agora, senao
        # o painel so reagiria no proximo tick.
        deltas = await motor.reconciliar()
        await difundir({
            "tipo": "DASHBOARD_TICK",
            "servidor_em": clock.agora(),
            "dashboard": await servico_dashboard.snapshot(),
            **({"deltas": deltas} if deltas else {}),
        })
    except asyncio.CancelledError:
        raise
    except Exception as erro:
        _grade.update(estado="falhou", erro=f"{type(erro).__name__}: {erro}")
        print(f"[grade] falhou: {type(erro).__name__}: {erro}")


async def _carregar_topologia() -> None:
    """Le o cadastro de salas do Postgres, se houver banco configurado.

    Sem DATABASE_URL - ou se o banco falhar - segue valendo o seed extraido
    das plantas, que ja esta carregado. Um cadastro fora do ar nao pode
    derrubar o painel da diretoria.
    """
    if not settings.DATABASE_URL:
        print("[boot] topologia: seed das plantas (sem DATABASE_URL)")
        return

    from app.data.conexao import descrever
    from app.data.sala_repository import carregar_topologia

    print(f"[boot] banco: {descrever(settings.DATABASE_URL)}")

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
    version=VERSAO,
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
    cron.router, cadastro.router, configuracao.router,
):
    app.include_router(router, prefix=settings.API_V1_PREFIX)

# WebSockets ficam fora do prefixo versionado para simplificar o client.
app.include_router(ws.router)



def _contar_endpoints() -> int:
    """Numero de operacoes servidas, entrando nos roteadores incluidos.

    `len(app.routes)` nao serve: a partir do Starlette 1.6 cada include_router
    vira um unico objeto agregador em vez de espalhar as rotas na lista. O
    numero despencaria de 43 para 13 sem nada ter sido perdido - justo o
    oposto do que este campo deve indicar.
    """
    vistas: set[tuple[str, str]] = set()

    def andar(rotas) -> None:
        for rota in rotas:
            interno = getattr(rota, "original_router", None)
            if interno is not None:
                andar(interno.routes)
                continue
            caminho = getattr(rota, "path", None)
            if caminho:
                for metodo in getattr(rota, "methods", None) or {"WS"}:
                    vistas.add((metodo, caminho))

    andar(app.routes)
    return len(vistas)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    """Saude e identidade do build.

    `versao` e `commit` existem para conferir qual codigo esta no ar sem ter
    que deduzir pelas rotas - foi assim que descobrimos que a Vercel servia um
    build de tres dias antes. Prefira os dois a `rotas`, que so diz quantas
    operacoes existem e pode coincidir entre builds diferentes.
    """
    import os

    commit = os.getenv("VERCEL_GIT_COMMIT_SHA", "")
    return {
        # "degradado" quando alguma etapa da partida caiu: o app serve, mas
        # com menos do que deveria. Dizer "ok" ai esconderia justamente o que
        # este endpoint existe para mostrar.
        "status": "degradado" if _falhas_boot else "ok",
        "servico": settings.PROJECT_NAME,
        "versao": VERSAO,
        "commit": commit[:7] if commit else "local",
        "rotas": _contar_endpoints(),
        "relogio": clock.agora().isoformat(),
        "fuso": clock.fuso(),
        "estado": obter_store().nome,
        "banco": bool(settings.DATABASE_URL),
        "simulador": parametros.simulador_ativo(),
        "falhas_boot": _falhas_boot,
        "grade": dict(_grade),
        "paineis_conectados": manager.total,
    }
