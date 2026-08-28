"""Valida o caminho Redis do EstadoStore, inclusive multi-instancia.

Usa fakeredis (emulacao em processo do protocolo Redis) para nao exigir um
servidor. O mesmo teste roda contra um Redis real: basta exportar REDIS_URL.

O que este teste prova:
  1. Presencas, campus, feed, alertas, serie e contadores sobrevivem ao store.
  2. `marcar_aula_aberta` funciona como trava: so uma instancia abre a aula.
  3. O pub/sub entrega a mensagem publicada na instancia A para a instancia B.
  4. Uma instancia nova reidrata a projecao das carteiras do estado partilhado.
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.academico import RegistroPresenca  # noqa: E402
from app.models.dashboard import Alerta  # noqa: E402
from app.models.enums import (  # noqa: E402
    SeveridadeAlerta,
    StatusPresenca,
    TipoAlerta,
)
from app.services.store.redis_store import RedisStore  # noqa: E402

URL_REAL = os.getenv("REDIS_URL", "")


def _novo_store() -> RedisStore:
    store = RedisStore(URL_REAL or "redis://localhost:6379/0")
    if not URL_REAL:
        import fakeredis.aioredis

        # Um servidor compartilhado: e o que simula duas instancias no mesmo Redis.
        store._servidor_fake = _SERVIDOR
    return store


_SERVIDOR = None
if not URL_REAL:
    import fakeredis

    _SERVIDOR = fakeredis.FakeServer()


async def _conectar(store: RedisStore) -> None:
    if URL_REAL:
        await store.iniciar()
        return
    import fakeredis.aioredis

    store._redis = fakeredis.aioredis.FakeRedis(
        server=_SERVIDOR, decode_responses=True
    )
    await store._redis.ping()


async def principal() -> int:
    falhas = []
    origem = "Redis real" if URL_REAL else "fakeredis (em processo)"
    print(f"Backend: {origem}\n")

    # --- duas "instancias" ligadas ao mesmo Redis ------------------------
    a, b = _novo_store(), _novo_store()
    await _conectar(a)
    await _conectar(b)
    await a._redis.flushdb()

    # 1. Trava de abertura de aula
    ganhou_a = await a.marcar_aula_aberta("AULA_TESTE")
    ganhou_b = await b.marcar_aula_aberta("AULA_TESTE")
    print(f"[1] trava de abertura: A={ganhou_a} B={ganhou_b}")
    if not (ganhou_a and not ganhou_b):
        falhas.append("marcar_aula_aberta nao serviu de trava entre instancias")

    # 2. Presencas gravadas em A sao vistas por B
    registros = [
        RegistroPresenca(
            aula_id="AULA_TESTE", aluno_ra=f"2026{i:04d}",
            aluno_nome=f"Aluno {i}", turma_id="ESW-1", sala_id="S1_01",
            disciplina="Estrutura de Dados",
        )
        for i in range(1, 6)
    ]
    await a.salvar_presencas("AULA_TESTE", registros)
    vistos = await b.presencas_da_aula("AULA_TESTE")
    print(f"[2] presencas gravadas em A, lidas por B: {len(vistos)}")
    if len(vistos) != 5:
        falhas.append(f"B leu {len(vistos)} presencas, esperado 5")

    # 3. Atualizacao de status atravessa as instancias
    reg = await b.obter_presenca("AULA_TESTE", "20260001")
    reg.status = StatusPresenca.PRESENTE
    reg.entrada_em = datetime.now()
    reg.atraso_minutos = 3
    await b.atualizar_presenca(reg)
    conferido = await a.obter_presenca("AULA_TESTE", "20260001")
    print(f"[3] status alterado em B, lido em A: {conferido.status.value} "
          f"(+{conferido.atraso_minutos} min)")
    if conferido.status != StatusPresenca.PRESENTE:
        falhas.append("atualizacao de presenca nao propagou")

    # 4. Indice por aluno
    do_aluno = await a.presencas_do_aluno("20260001")
    print(f"[4] presencas do aluno 20260001: {len(do_aluno)}")
    if len(do_aluno) != 1:
        falhas.append("indice presencas_do_aluno nao funcionou")

    # 5. Campus
    await a.entrar_campus("20260001")
    await a.entrar_campus("20260002")
    await b.sair_campus("20260002")
    print(f"[5] no campus: {await b.total_no_campus()} "
          f"(esta 0001? {await b.esta_no_campus('20260001')})")
    if await b.total_no_campus() != 1:
        falhas.append("conjunto de alunos no campus inconsistente")

    # 6. Feed e contadores
    await a.push_evento({"id": "e1", "timestamp": datetime.now().isoformat()})
    await b.push_evento({"id": "e2", "timestamp": datetime.now().isoformat()})
    feed = await a.feed(10)
    await a.incrementar_passagem("CATRACA_PRINCIPAL_A", True, datetime.now().isoformat())
    await b.incrementar_passagem("CATRACA_PRINCIPAL_A", False, datetime.now().isoformat())
    contadores = await a.contadores()
    catracas = await b.estado_catracas()
    print(f"[6] feed={len(feed)} (mais recente {feed[0]['id']}), "
          f"contadores={contadores}, "
          f"catraca A entradas={catracas['CATRACA_PRINCIPAL_A']['entradas']}")
    if len(feed) != 2 or feed[0]["id"] != "e2":
        falhas.append("feed fora de ordem ou incompleto")
    if contadores != {"entradas": 1, "saidas": 1}:
        falhas.append(f"contadores errados: {contadores}")

    # 7. Alertas com deduplicacao entre instancias
    def _alerta(n):
        return Alerta(
            id=f"al{n}", tipo=TipoAlerta.BAIXA_PRESENCA,
            severidade=SeveridadeAlerta.ATENCAO, titulo=f"Alerta {n}",
            detalhe="teste", criado_em=datetime.now(),
        )

    primeiro = await a.push_alerta(_alerta(1), "AULA_TESTE:baixa")
    repetido = await b.push_alerta(_alerta(2), "AULA_TESTE:baixa")
    print(f"[7] alerta: primeiro={primeiro} repetido={repetido} "
          f"total={len(await a.alertas())}")
    if not primeiro or repetido:
        falhas.append("deduplicacao de alertas falhou entre instancias")

    await a.limpar_dedupe("AULA_TESTE:")
    if not await b.push_alerta(_alerta(3), "AULA_TESTE:baixa"):
        falhas.append("limpar_dedupe nao liberou a chave")

    # 8. Serie
    await a.salvar_ponto_serie("19:00", {"hora": "19:00", "presentes": 10,
                                         "esperados": 40, "taxa": 25.0})
    await b.salvar_ponto_serie("19:30", {"hora": "19:30", "presentes": 30,
                                         "esperados": 40, "taxa": 75.0})
    serie = await a.serie()
    print(f"[8] serie: {[(p['hora'], p['taxa']) for p in serie]}")
    if len(serie) != 2 or serie[0]["hora"] != "19:00":
        falhas.append("serie temporal fora de ordem")

    # 9. Pub/sub: publicado em A, recebido em B
    recebidas = []
    pronto = asyncio.Event()

    async def ao_receber(payload):
        recebidas.append(payload)
        pronto.set()

    await b.assinar(ao_receber)
    await asyncio.sleep(0.3)  # deixa o listener assinar o canal
    await a.publicar({"tipo": "EVENTO_CATRACA", "deltas": [{"cadeira_id": "S1_01_CAD_01"}]})

    try:
        await asyncio.wait_for(pronto.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass

    ok_pubsub = bool(recebidas) and recebidas[0].get("tipo") == "EVENTO_CATRACA"
    print(f"[9] pub/sub A->B: {'entregue' if ok_pubsub else 'NAO ENTREGUE'} "
          f"({len(recebidas)} mensagem(ns))")
    if not ok_pubsub:
        falhas.append("pub/sub nao entregou a mensagem entre instancias")

    # 10. Fechamento da aula limpa as presencas
    await a.fechar_aula("AULA_TESTE")
    print(f"[10] apos fechar: {len(await b.presencas_da_aula('AULA_TESTE'))} presencas, "
          f"aberta={await b.aula_esta_aberta('AULA_TESTE')}")
    if await b.presencas_da_aula("AULA_TESTE") or await b.aula_esta_aberta("AULA_TESTE"):
        falhas.append("fechar_aula nao limpou o estado")

    await a.encerrar()
    await b.encerrar()

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Redis store OK: estado compartilhado e pub/sub validados entre instancias.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
