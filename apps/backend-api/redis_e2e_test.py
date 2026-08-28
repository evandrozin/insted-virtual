"""Sobe a aplicacao completa com o estado em Redis e repete o fluxo do smoke.

Prova que a migracao nao mudou o comportamento: os mesmos passos do
smoke_test.py devem produzir o mesmo resultado com o estado fora do processo.

Sem REDIS_URL usa fakeredis; com REDIS_URL usa o servidor real.
"""
import asyncio
import os
import sys

os.environ.setdefault("RELOGIO_DEMO", "19:20")
os.environ.setdefault("SIMULADOR_ATIVO", "false")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.store import definir_store  # noqa: E402
from app.services.store.redis_store import RedisStore  # noqa: E402

URL_REAL = os.getenv("REDIS_URL", "")


class RedisStoreDeTeste(RedisStore):
    """RedisStore apontado para fakeredis quando nao ha servidor real."""

    async def iniciar(self) -> None:
        if URL_REAL:
            await super().iniciar()
            return
        import fakeredis.aioredis

        self._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        await self._redis.ping()
        await self._redis.flushdb()


definir_store(RedisStoreDeTeste(URL_REAL or "redis://localhost:6379/0"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def principal() -> int:
    falhas = []
    print(f"Backend: {'Redis real' if URL_REAL else 'fakeredis (em processo)'}\n")

    with TestClient(app) as client:
        status = client.get("/api/v1/status").json()
        print(f"[0] estado compartilhado: {status['estado_compartilhado']}")
        if status["estado_compartilhado"] != "redis":
            falhas.append("a app nao subiu com o store Redis")
        print(f"[1] status: {status['alunos']} alunos, "
              f"{status['aulas_ativas']} aulas ativas, "
              f"{status['cadeiras']} cadeiras")
        if status["aulas_ativas"] == 0:
            falhas.append("nenhuma aula ativa as 19:20")

        grade = client.get("/api/v1/academico/grade").json()
        ativa = next(a for a in grade["aulas"] if a["em_andamento"])
        detalhe = client.get(f"/api/v1/salas/{ativa['sala_id']}").json()
        chamada = detalhe["chamada"]
        print(f"[2] {ativa['disciplina']} em {ativa['sala_nome']}: "
              f"{len(chamada)} matriculados")
        if not chamada:
            falhas.append("chamada vazia (presencas nao chegaram ao Redis)")

        alvo = chamada[0]
        entrada = client.post(
            "/api/v1/catracas/evento",
            json={"ra": alvo["ra"], "catraca_id": "CATRACA_PRINCIPAL_A",
                  "direcao": "ENTRADA"},
        ).json()
        print(f"[3] catraca: {entrada['evento']['nome']} -> "
              f"{entrada['evento']['situacao']} "
              f"({len(entrada['deltas'])} delta(s))")
        if entrada["evento"]["situacao"] not in ("PRESENTE", "ATRASADO"):
            falhas.append(f"situacao inesperada: {entrada['evento']['situacao']}")

        rastreio = client.get(f"/api/v1/alunos/{alvo['ra']}").json()
        print(f"[4] rastreio: no_campus={rastreio['no_campus']}, "
              f"local={rastreio['localizacao']['cadeira_id'] if rastreio['localizacao'] else None}")
        if not rastreio["no_campus"]:
            falhas.append("aluno nao ficou marcado no campus")

        saida = client.post(
            "/api/v1/catracas/evento",
            json={"ra": alvo["ra"], "catraca_id": "CATRACA_PRINCIPAL_A",
                  "direcao": "SAIDA"},
        ).json()
        print(f"[5] saida: {saida['evento']['situacao']}")
        if saida["evento"]["situacao"] != "EVADIDO":
            falhas.append("saida no meio da aula nao gerou EVADIDO")

        dash = client.get("/api/v1/dashboard").json()
        k = dash["kpis"]
        print(f"[6] KPIs: {k['presentes_em_aula']}/{k['alunos_esperados_agora']} "
              f"presentes, {k['salas_em_aula']} salas, "
              f"{k['evasao_em_aula']} evasoes, {len(dash['alertas'])} alertas")
        if k["alunos_esperados_agora"] == 0:
            falhas.append("dashboard sem alunos esperados")

        with client.websocket_connect("/ws/campus") as ws:
            inicial = ws.receive_json()
            cadeiras = sum(
                len(s["cadeiras"])
                for p in inicial["maquete"]["pavimentos"] for s in p["salas"]
            )
            print(f"[7] websocket: {inicial['tipo']}, {cadeiras} cadeiras")
            if inicial["tipo"] != "SNAPSHOT_INICIAL":
                falhas.append("handshake sem snapshot inicial")

        cron = client.post("/api/v1/cron/reconciliar").json()
        print(f"[8] cron: {cron['aulas_ativas']} aulas ativas, "
              f"{cron['presentes_em_aula']} presentes")
        if cron["aulas_ativas"] == 0:
            falhas.append("cron nao encontrou aulas ativas")

        feed = client.get("/api/v1/dashboard/eventos?limite=5").json()["eventos"]
        print(f"[9] feed no Redis: {len(feed)} eventos")
        if len(feed) < 2:
            falhas.append("feed nao persistiu no Redis")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("E2E com Redis OK: mesmo comportamento do modo memoria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
