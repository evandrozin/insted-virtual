"""Valida quem aparece na maquete estando no predio fora do horario de aula.

O caso que isto protege: as 17h nao ha aula aberta, mas ha gente no predio.
Antes, essas pessoas contavam em "no campus" e a maquete aparecia vazia - dois
numeros para a mesma pergunta, e o campus cheio parecendo deserto.

Roda com o relogio ancorado as 17:00 de um dia letivo, ERP simulado e estado em
memoria: nao precisa de banco nem de catraca.
"""
import asyncio
import os
import sys
from datetime import date, timedelta


def ancora_letiva(hora: str) -> str:
    dia = date.today()
    while dia.weekday() > 4:
        dia -= timedelta(days=1)
    return f"{dia.isoformat()}T{hora}"


# 17:00: o matutino acabou e o noturno nao comecou - nenhuma aula aberta, que e
# exatamente a janela onde o comportamento novo aparece.
os.environ["RELOGIO_DEMO"] = ancora_letiva("17:00")
os.environ["SIMULADOR_ATIVO"] = "false"
os.environ["JACAD_MODO_MOCK"] = "true"
os.environ.setdefault("TIMEZONE", "America/Campo_Grande")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import clock  # noqa: E402
from app.models.enums import StatusCadeira  # noqa: E402
from app.services.campus_state import estado  # noqa: E402
from app.services.presence_engine import motor  # noqa: E402
from app.services.store import obter_store  # noqa: E402

falhas: list = []


def conferir(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def sentados() -> list:
    return [c for c in estado.cadeiras.values()
            if c.status == StatusCadeira.NO_CAMPUS]


async def principal() -> int:
    store = obter_store()
    await store.iniciar()
    await clock.inicializar(store)
    motor.sincronizar_jacad(True)

    await motor.reconciliar()
    print(f"[0] aulas abertas as 17:00: {len(estado.aulas_ativas)}")
    conferir(not estado.aulas_ativas,
             "o teste perde o sentido com aula aberta as 17:00")
    conferir(not sentados(), "ninguem entrou ainda e ja ha carteira ocupada")

    turma = next(t for t in estado.turmas.values() if len(t.alunos_ra) >= 3)
    alunos = turma.alunos_ra[:3]
    for ra in alunos:
        await store.entrar_campus(ra)
    await motor.reconciliar()

    lugares = sentados()
    print(f"[1] {len(alunos)} no predio -> {len(lugares)} carteira(s) NO_CAMPUS")
    conferir(len(lugares) == len(alunos),
             f"esperava {len(alunos)} carteiras, veio {len(lugares)}")

    # Todos na mesma sala: e a da proxima aula da turma, nao uma qualquer.
    salas = {c.sala_id for c in lugares}
    referencia = motor._aula_referencia(turma.id, clock.agora())
    print(f"[2] sala(s): {salas} | aula de referencia: "
          f"{referencia.sala_id if referencia else None}")
    conferir(len(salas) == 1, f"a turma se espalhou por {len(salas)} salas")
    conferir(referencia is not None and salas == {referencia.sala_id},
             "sentaram em sala diferente da aula de referencia")

    # Idempotencia: reconciliar de novo nao duplica nem move ninguem.
    antes = {c.id: c.aluno_ra for c in lugares}
    await motor.reconciliar()
    depois = {c.id: c.aluno_ra for c in sentados()}
    print(f"[3] apos novo ciclo: {len(depois)} carteira(s), mesmas: {antes == depois}")
    conferir(antes == depois, "o ciclo seguinte remexeu as carteiras")

    # Saida libera a carteira - senao a pessoa fica no predio para sempre.
    await store.sair_campus(alunos[0])
    await motor.reconciliar()
    print(f"[4] apos uma saida: {len(sentados())} carteira(s)")
    conferir(len(sentados()) == len(alunos) - 1,
             "a carteira de quem saiu nao foi liberada")

    # Aluno com aula aberta nao e reposicionado por este mecanismo: a cor de
    # presenca em aula tem de prevalecer.
    ra_restante = [c.aluno_ra for c in sentados()][0]
    conferir(estado.cadeira_por_aluno.get(ra_restante) is not None,
             "quem esta sentado sumiu do indice cadeira_por_aluno")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("No campus OK: sentado na sala da proxima aula, idempotente, "
          "e liberado na saida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
