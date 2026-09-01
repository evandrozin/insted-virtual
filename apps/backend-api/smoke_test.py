"""Teste de fumaca: sobe a app em memoria e valida o fluxo ponta a ponta."""
import os
import sys

from datetime import date, timedelta


def ancora_letiva(hora: str = "19:20") -> str:
    """Ultimo dia de semana as `hora`, para o teste nao depender de quando roda.

    A grade do JACAD so tem aula de segunda a sexta: rodar num sabado sem isso
    faria o teste falhar por nao existir aula ativa.
    """
    dia = date.today()
    while dia.weekday() > 4:
        dia -= timedelta(days=1)
    return f"{dia.isoformat()}T{hora}"



# Relogio ancorado num horario letivo para o teste ser deterministico.
os.environ.setdefault("RELOGIO_DEMO", ancora_letiva())
os.environ.setdefault("SIMULADOR_ATIVO", "false")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def principal() -> int:
    falhas = []

    with TestClient(app) as client:
        # 1. Saude e status operacional
        assert client.get("/health").json()["status"] == "ok"
        status = client.get("/api/v1/status").json()
        print(f"[0] estado compartilhado: {status['estado_compartilhado']}")
        print(f"[1] status: {status['alunos']} alunos, "
              f"{status['aulas_cadastradas']} aulas na grade, "
              f"{status['aulas_ativas']} ativas, {status['cadeiras']} cadeiras")
        if status["aulas_ativas"] == 0:
            falhas.append("nenhuma aula ativa as 19:20")

        # 2. Maquete 3D
        maquete = client.get("/api/v1/maquete").json()
        cadeiras = sum(
            len(s["cadeiras"]) for p in maquete["pavimentos"] for s in p["salas"]
        )
        print(f"[2] maquete: {len(maquete['pavimentos'])} pavimentos, "
              f"{cadeiras} cadeiras, {len(maquete['catracas'])} catracas")

        # 3. Uma aula ativa e sua chamada
        grade = client.get("/api/v1/academico/grade").json()
        ativa = next(a for a in grade["aulas"] if a["em_andamento"])
        sala_id = ativa["sala_id"]
        detalhe = client.get(f"/api/v1/salas/{sala_id}").json()
        chamada = detalhe["chamada"]
        print(f"[3] {ativa['disciplina']} em {ativa['sala_nome']} "
              f"({ativa['inicio']}-{ativa['fim']}): {len(chamada)} matriculados")
        if not chamada:
            falhas.append("chamada vazia para aula ativa")

        # 4. Passagem na catraca promove a cadeira para OCUPADA
        #
        # Nem todo matriculado tem carteira: a Multiuso tem 30 lugares e recebe
        # turma de 38: 8 ficam de fora, e quem nao tem carteira nao aparece na
        # maquete - isso e sobrelotacao sendo reportada, nao defeito. Pegar
        # chamada[0] as cegas caia justamente num desses e acusava falha no
        # rastreio.
        com_carteira = [r for r in chamada if r["cadeira_id"]]
        sem_carteira = [r for r in chamada if not r["cadeira_id"]]
        print(f"[3b] carteiras: {len(com_carteira)} reservadas, "
              f"{len(sem_carteira)} sem lugar (sobrelotacao)")
        if not com_carteira:
            # Sem ninguem sentado nao ha o que rastrear: os passos seguintes
            # falhariam em cascata e esconderiam a causa real.
            falhas.append("nenhum matriculado recebeu carteira na aula ativa")
            print()
            print("FALHAS:")
            for f in falhas:
                print(f"  - {f}")
            return 1

        alvo = com_carteira[0]
        resposta = client.post(
            "/api/v1/catracas/evento",
            json={"ra": alvo["ra"], "catraca_id": "CATRACA_PRINCIPAL_A",
                  "direcao": "ENTRADA"},
        ).json()
        evento = resposta["evento"]
        print(f"[4] catraca: {evento['nome']} -> {evento['situacao']} "
              f"em {evento['sala_nome']} ({len(resposta['deltas'])} delta(s))")
        if evento["situacao"] not in ("PRESENTE", "ATRASADO"):
            falhas.append(f"situacao inesperada apos entrada: {evento['situacao']}")

        rastreio = client.get(f"/api/v1/alunos/{alvo['ra']}").json()
        if not rastreio["no_campus"] or not rastreio["localizacao"]:
            falhas.append("aluno nao localizado na maquete apos a entrada")
        else:
            loc = rastreio["localizacao"]
            print(f"[5] rastreio: {loc['cadeira_id']} em {loc['sala_nome']} "
                  f"({loc['pavimento']})")

        # 5. Saida caracteriza evasao (aula ainda longe do fim)
        saida = client.post(
            "/api/v1/catracas/evento",
            json={"ra": alvo["ra"], "catraca_id": "CATRACA_PRINCIPAL_A",
                  "direcao": "SAIDA"},
        ).json()
        print(f"[6] saida: situacao = {saida['evento']['situacao']}")
        if saida["evento"]["situacao"] != "EVADIDO":
            falhas.append("saida no meio da aula nao gerou EVADIDO")

        # 6. Dashboard da diretoria
        dash = client.get("/api/v1/dashboard").json()
        k = dash["kpis"]
        print(f"[7] KPIs: {k['presentes_em_aula']}/{k['alunos_esperados_agora']} "
              f"presentes ({k['taxa_presenca_geral']}%), "
              f"{k['salas_em_aula']} salas em aula, "
              f"{k['atrasados']} atrasados, {k['evasao_em_aula']} evasoes, "
              f"{len(dash['alertas'])} alertas")
        if k["alunos_esperados_agora"] == 0:
            falhas.append("dashboard sem alunos esperados")

        # 7. WebSocket entrega o snapshot inicial
        with client.websocket_connect("/ws/campus") as ws:
            inicial = ws.receive_json()
            print(f"[8] websocket: {inicial['tipo']}, "
                  f"{len(inicial['maquete']['pavimentos'])} pavimentos, "
                  f"relogio {inicial['modo_relogio']}")
            if inicial["tipo"] != "SNAPSHOT_INICIAL":
                falhas.append("handshake do websocket sem snapshot inicial")

        # 8. Reconciliacao por cron (caminho serverless)
        cron = client.post("/api/v1/cron/reconciliar").json()
        print(f"[9] cron: {cron['aulas_ativas']} aulas ativas, "
              f"{cron['deltas']} deltas, "
              f"{cron['presentes_em_aula']} presentes")

        # 9. Realocacao de turma
        livres = client.get("/api/v1/alocacao/salas-disponiveis?minimo=20").json()
        if livres["salas"]:
            destino = livres["salas"][0]["id"]
            realoc = client.post(
                "/api/v1/alocacao/realocar",
                json={"turma_id": ativa["turma_id"], "sala_destino_id": destino},
            ).json()
            print(f"[10] realocacao: {realoc['sala_origem']} -> "
                  f"{realoc['sala_destino']} ({realoc['alocados']} alocados)")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1

    print("Smoke test OK: fluxo JACAD -> catraca -> maquete -> dashboard validado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
