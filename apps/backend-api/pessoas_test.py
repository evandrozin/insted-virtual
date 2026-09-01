"""Espelho local do cadastro de pessoas: alunos e professores do JACAD.

E contra esta base que a conferencia com a catraca e feita, entao o que se
valida aqui e menos "gravou?" e mais "gravou sem estragar o resto?".

Usa o banco configurado no .env e devolve a base ao estado espelhado no fim.
"""
import asyncio
import os
import sys

os.environ["JACAD_MODO_MOCK"] = "true"  # nao fala com o ERP real
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import parametros  # noqa: F401,E402  carrega o .env
from app.core.config import settings  # noqa: E402
from app.data import pessoa_repository as repo  # noqa: E402
from app.data.conexao import abrir  # noqa: E402
from app.services.cadastro_pessoas import espelhar  # noqa: E402
from app.services.jacad_client import obter_client  # noqa: E402


async def ativos_por_tipo() -> dict:
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """select tipo_codigo, count(*) filter (where ativo) ativos
                 from pessoa where origem = 'JACAD' group by 1"""
        )
        return {l["tipo_codigo"]: l["ativos"] for l in linhas}
    finally:
        await conexao.close()


async def principal() -> int:
    falhas = []

    if not settings.DATABASE_URL:
        print("Sem DATABASE_URL: este teste exige banco.")
        return 0

    client = obter_client()
    alunos = client.listar_alunos()
    professores = client.listar_professores()
    print(f"[1] JACAD oferece {len(alunos)} alunos e {len(professores)} professores")

    # Professor sem matricula nao teria como ser reconhecido na catraca.
    sem_matricula = [p for p in professores if not (p.matricula or "").strip()]
    if sem_matricula:
        falhas.append(f"{len(sem_matricula)} professor(es) sem matricula")

    espelho = await espelhar()
    print(f"[2] espelhado: {espelho['por_tipo']}")
    if not espelho.get("aplicado"):
        falhas.append("espelho nao aplicado com DATABASE_URL definida")
        return relatar(falhas)

    antes = await ativos_por_tipo()
    print(f"[3] ativos no banco: {antes}")
    if antes.get("PROFESSOR", 0) != len(professores):
        falhas.append("professores no banco divergem do ERP")

    # Uma pessoa criada a mao nao pode sumir porque o ERP nao a conhece.
    conexao = await abrir()
    try:
        await conexao.execute(
            """insert into pessoa (identificador, nome, tipo_codigo, origem, ativo)
               values ('PORTARIA-01', 'Porteiro de Teste', 'FUNCIONARIO', 'MANUAL', true)
               on conflict (identificador) do update set ativo = true"""
        )
    finally:
        await conexao.close()

    # Sincronizar SO alunos nao pode desativar o corpo docente.
    dois = [
        {"identificador": a.ra, "nome": a.nome, "curso": a.curso,
         "turma_id": a.turma_id, "periodo": a.periodo}
        for a in alunos[:2]
    ]
    parcial = await repo.sincronizar_do_jacad({"ALUNO": dois})
    depois = await ativos_por_tipo()
    print(f"[4] apos sync so de alunos (2 de {len(alunos)}): {depois}")

    if depois.get("PROFESSOR", 0) != antes.get("PROFESSOR", 0):
        falhas.append("sincronizar alunos desativou professores")
    if depois.get("ALUNO", 0) != 2:
        falhas.append(f"esperava 2 alunos ativos, veio {depois.get('ALUNO')}")

    esperado = antes.get("ALUNO", 0) - 2
    print(f"[5] desativados reportados: {parcial['desativados']} (esperado {esperado})")
    if parcial["desativados"] != esperado:
        falhas.append(
            f"contagem de desativados errada: {parcial['desativados']} != {esperado}"
        )

    conexao = await abrir()
    try:
        manual = await conexao.fetchrow(
            "select ativo from pessoa where identificador = 'PORTARIA-01'"
        )
        print(f"[6] cadastro manual apos o sync: ativo={manual['ativo']}")
        if not manual["ativo"]:
            falhas.append("sincronizacao desativou pessoa de origem MANUAL")
    finally:
        await conexao.close()

    # Devolve a base ao estado completo.
    final = await espelhar()
    restaurado = await ativos_por_tipo()
    print(f"[7] base restaurada: {restaurado}")
    if restaurado.get("ALUNO", 0) != len(alunos):
        falhas.append("a base nao voltou ao total de alunos do ERP")

    conexao = await abrir()
    try:
        await conexao.execute("delete from pessoa where identificador = 'PORTARIA-01'")
    finally:
        await conexao.close()

    return relatar(falhas)


def relatar(falhas) -> int:
    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Pessoas OK: alunos e professores espelhados, sem dano cruzado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
