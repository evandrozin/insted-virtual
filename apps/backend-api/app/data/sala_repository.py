"""Leitura da topologia a partir do Postgres.

O cadastro de salas (predio -> pavimento -> sala) e a fonte de verdade quando
`DATABASE_URL` esta definido. Sem ele, o sistema continua usando o seed
extraido das plantas, o que mantem o desenvolvimento local funcionando sem
banco e serve de fallback se o banco estiver fora do ar.

O cadastro guarda tambem a geometria (posicao e dimensao em metros), entao uma
sala criada pela Secretaria aparece na maquete 3D sem precisar de deploy.
"""
from __future__ import annotations

from typing import List, Optional

from app.data.campus_seed import _gerar_cadeiras
from app.models.campus import Dimensao3D, PavimentoModel, Posicao3D, SalaModel
from app.models.enums import Pavimento

CONSULTA = """
select
    p.codigo        as pavimento_codigo,
    p.nome          as pavimento_nome,
    p.ordem         as pavimento_ordem,
    p.altura_y      as pavimento_altura,
    p.descricao     as pavimento_descricao,
    s.codigo        as sala_codigo,
    s.nome          as sala_nome,
    s.tipo          as sala_tipo,
    s.capacidade    as sala_capacidade,
    s.rack_id       as sala_rack,
    s.pos_x, s.pos_z, s.largura, s.profundidade
from sala s
join pavimento p on p.id = s.pavimento_id
join predio pr on pr.id = p.predio_id
where pr.codigo = $1
  and pr.ativo
  and s.ativa
order by p.ordem, s.codigo;
"""


class TopologiaIndisponivel(RuntimeError):
    """O banco nao respondeu ou nao tem cadastro utilizavel."""


async def carregar_topologia(
    dsn: str, predio_codigo: str = "SEDE"
) -> List[PavimentoModel]:
    """Monta os pavimentos a partir do cadastro, gerando as carteiras.

    Devolve exatamente a mesma estrutura de `construir_pavimentos()`, entao o
    resto do sistema nao sabe de onde a topologia veio.
    """
    import asyncpg

    conexao = await asyncpg.connect(dsn, timeout=15)
    try:
        linhas = await conexao.fetch(CONSULTA, predio_codigo)
    finally:
        await conexao.close()

    if not linhas:
        raise TopologiaIndisponivel(
            f"Cadastro vazio para o predio {predio_codigo!r}."
        )

    return montar_pavimentos(linhas)


def montar_pavimentos(linhas) -> List[PavimentoModel]:
    """Converte as linhas do cadastro nos modelos da maquete.

    Separado da consulta para poder ser testado sem banco.
    """
    pavimentos: dict[str, PavimentoModel] = {}

    for linha in linhas:
        codigo_pav = linha["pavimento_codigo"]
        try:
            pav_enum = Pavimento(codigo_pav)
        except ValueError:
            # Pavimento cadastrado que a maquete ainda nao conhece: ignora em
            # vez de derrubar o boot inteiro.
            continue

        pavimento = pavimentos.get(codigo_pav)
        if pavimento is None:
            pavimento = PavimentoModel(
                id=pav_enum,
                nome=linha["pavimento_nome"],
                ordem=int(linha["pavimento_ordem"]),
                altura_y=float(linha["pavimento_altura"] or 0),
                descricao=linha["pavimento_descricao"] or "",
                salas=[],
            )
            pavimentos[codigo_pav] = pavimento

        largura = float(linha["largura"] or 0)
        profundidade = float(linha["profundidade"] or 0)
        pos_x = float(linha["pos_x"] or 0)
        pos_z = float(linha["pos_z"] or 0)
        capacidade = int(linha["sala_capacidade"] or 0)

        if largura <= 0 or profundidade <= 0:
            # Sala sem geometria nao tem como ser desenhada.
            continue

        cadeiras = _gerar_cadeiras(
            linha["sala_codigo"], pav_enum, pos_x, pos_z,
            largura, profundidade, capacidade, pavimento.altura_y,
        )

        pavimento.salas.append(
            SalaModel(
                id=linha["sala_codigo"],
                nome=linha["sala_nome"],
                pavimento=pav_enum,
                tipo=linha["sala_tipo"],
                capacidade=len(cadeiras),
                posicao=Posicao3D(x=pos_x, y=pavimento.altura_y, z=pos_z),
                dimensao=Dimensao3D(
                    largura=largura, altura=3.2, profundidade=profundidade
                ),
                rack_id=linha["sala_rack"],
                cadeiras=cadeiras,
            )
        )

    if not pavimentos:
        raise TopologiaIndisponivel("Nenhum pavimento reconhecido no cadastro.")

    return sorted(pavimentos.values(), key=lambda p: p.ordem)


async def listar_cadastro(dsn: str) -> List[dict]:
    """Cadastro completo, como a Secretaria le: predio, andar, nome, lugares."""
    import asyncpg

    conexao = await asyncpg.connect(dsn, timeout=15)
    try:
        linhas = await conexao.fetch(
            """
            select predio, pavimento, pavimento_ordem, codigo, codigo_planta,
                   codigo_ensalamento, sala, tipo, capacidade, rack_id, ativa
            from vw_sala_completa
            order by pavimento_ordem, codigo
            """
        )
    finally:
        await conexao.close()
    return [dict(linha) for linha in linhas]
