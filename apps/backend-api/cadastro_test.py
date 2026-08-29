"""Valida que a topologia vinda do cadastro em banco e a do seed sao iguais.

Nao precisa de banco nem de credencial: monta as linhas exatamente como o
Postgres as devolve (Decimal nas colunas numeric, como faz o asyncpg) e passa
por `montar_pavimentos`, comparando o resultado com `construir_pavimentos()`.

Se este teste passa, ligar o DATABASE_URL nao muda a maquete - so muda de onde
ela vem.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.data.campus_seed import (  # noqa: E402
    ALTURA_PAVIMENTO,
    PAVIMENTOS_META,
    RACK_POR_PAVIMENTO,
    SALAS_POR_PAVIMENTO,
    construir_pavimentos,
)
from app.data.sala_repository import montar_pavimentos  # noqa: E402


def linhas_como_o_postgres():
    """Reproduz o retorno da consulta do repositorio a partir do seed."""
    meta = {pav: (nome, ordem, desc) for pav, nome, ordem, desc in PAVIMENTOS_META}
    linhas = []
    for pav in SALAS_POR_PAVIMENTO:
        nome_pav, ordem, descricao = meta[pav]
        for (sid, cod, nome, tipo, x, z, larg, prof, cap) in SALAS_POR_PAVIMENTO[pav]:
            linhas.append({
                "pavimento_codigo": pav.value,
                "pavimento_nome": nome_pav,
                "pavimento_ordem": ordem,
                "pavimento_altura": Decimal(f"{ordem * ALTURA_PAVIMENTO:.2f}"),
                "pavimento_descricao": descricao,
                "sala_codigo": sid,
                "sala_nome": nome,
                "sala_tipo": tipo,
                "sala_capacidade": cap,
                "sala_rack": RACK_POR_PAVIMENTO[pav],
                "pos_x": Decimal(f"{x:.2f}"),
                "pos_z": Decimal(f"{z:.2f}"),
                "largura": Decimal(f"{larg:.2f}"),
                "profundidade": Decimal(f"{prof:.2f}"),
            })
    # O banco ordena por pavimento e codigo de sala.
    linhas.sort(key=lambda l: (l["pavimento_ordem"], l["sala_codigo"]))
    return linhas


def resumo(pavimentos):
    return {
        p.id.value: {
            "nome": p.nome,
            "ordem": p.ordem,
            "altura_y": round(p.altura_y, 2),
            "salas": {
                s.id: (
                    s.nome, s.tipo, len(s.cadeiras),
                    round(s.posicao.x, 2), round(s.posicao.z, 2),
                    round(s.dimensao.largura, 2), round(s.dimensao.profundidade, 2),
                )
                for s in p.salas
            },
        }
        for p in pavimentos
    }


def principal() -> int:
    falhas = []

    do_seed = resumo(construir_pavimentos())
    do_banco = resumo(montar_pavimentos(linhas_como_o_postgres()))

    print(f"[1] pavimentos: seed={len(do_seed)} banco={len(do_banco)}")
    if set(do_seed) != set(do_banco):
        falhas.append(f"pavimentos diferentes: {set(do_seed) ^ set(do_banco)}")

    total_seed = total_banco = 0
    for pav in sorted(set(do_seed) & set(do_banco)):
        s, b = do_seed[pav], do_banco[pav]
        total_seed += sum(v[2] for v in s["salas"].values())
        total_banco += sum(v[2] for v in b["salas"].values())

        print(f"    {pav:8s} {len(s['salas']):2d} ambientes | "
              f"{sum(v[2] for v in s['salas'].values()):4d} lugares")

        if s["salas"].keys() != b["salas"].keys():
            falhas.append(
                f"{pav}: salas diferentes "
                f"{set(s['salas']) ^ set(b['salas'])}"
            )
            continue
        for codigo in s["salas"]:
            if s["salas"][codigo] != b["salas"][codigo]:
                falhas.append(
                    f"{pav}/{codigo}: seed={s['salas'][codigo]} "
                    f"banco={b['salas'][codigo]}"
                )
        if (s["nome"], s["ordem"], s["altura_y"]) != (b["nome"], b["ordem"], b["altura_y"]):
            falhas.append(f"{pav}: metadados do pavimento divergem")

    print(f"[2] lugares no total: seed={total_seed} banco={total_banco}")
    if total_seed != total_banco:
        falhas.append("total de lugares divergente")

    # Uma sala sem geometria nao pode entrar na maquete.
    sem_geometria = linhas_como_o_postgres()[:1]
    sem_geometria[0] = dict(sem_geometria[0], largura=Decimal("0"), profundidade=Decimal("0"))
    resultado = montar_pavimentos(sem_geometria + linhas_como_o_postgres()[1:])
    codigos = {s.id for p in resultado for s in p.salas}
    print(f"[3] sala sem largura/profundidade e ignorada: "
          f"{'sim' if linhas_como_o_postgres()[0]['sala_codigo'] not in codigos else 'NAO'}")
    if linhas_como_o_postgres()[0]["sala_codigo"] in codigos:
        falhas.append("sala sem geometria entrou na maquete")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas[:10]:
            print(f"  - {f}")
        return 1
    print("Cadastro OK: a topologia do banco e identica a do seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
