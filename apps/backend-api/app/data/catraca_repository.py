"""Leitura do espelho das catracas.

O controle de acesso fica em SQL Server na rede interna, inalcancavel daqui; um
job replica as marcacoes para `catraca.gac_marcacao` e o cadastro para
`catraca.gac_pessoa`. Este modulo so le - ver docs/catracas-replicacao.md.

O significado dos campos foi levantado por medicao sobre 14.936 passagens reais,
porque o fornecedor nao documenta: a view `catraca.vw_passagem` ja aplica o
filtro de passagem autorizada e traduz o sentido.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.data.conexao import abrir

# Quanto tempo depois da entrada a pessoa deixa de contar como presente sem ter
# registrado saida.
#
# Nao e detalhe: das 7.515 entradas medidas, so 5.581 tem saida correspondente.
# A catraca de saida nem sempre exige cracha, entao ~1.900 pessoas "entraram e
# nunca sairam". Sem uma janela, elas ficariam dentro da instituicao para sempre.
# 18 horas cobre o dia letivo mais folga e zera antes do turno seguinte.
JANELA_PRESENCA_H = 18


async def presentes_agora(momento: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Quem esta dentro: ultima passagem na janela foi entrada.

    Traz a matricula da catraca e, quando ela casa com o cadastro academico, o
    nome e o tipo de la. Sem casar, devolve o nome que a propria catraca tem -
    e melhor mostrar "fulano, nao identificado no JaCad" do que omitir alguem
    que esta fisicamente no predio.
    """
    agora = momento or datetime.now()
    desde = agora - timedelta(hours=JANELA_PRESENCA_H)

    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            with ultima as (
                select distinct on (v.pes_id)
                       v.pes_id, v.momento, v.sentido, v.matricula,
                       v.nome_na_catraca, v.terminal
                  from catraca.vw_passagem v
                 where v.pes_id is not null
                   and v.momento between $1 and $2
                 order by v.pes_id, v.momento desc
            )
            select u.pes_id, u.momento as desde, u.matricula, u.terminal,
                   u.nome_na_catraca,
                   p.identificador, p.nome as nome_cadastro,
                   p.tipo_codigo, p.curso, p.turma_nome
              from ultima u
              left join pessoa p
                     on upper(p.identificador) = upper(trim(u.matricula))
                    and p.origem = 'JACAD' and p.ativo
             where u.sentido = 'ENTRADA'
             order by u.momento desc
            """,
            desde,
            agora,
        )
    finally:
        await conexao.close()

    return [
        {
            "pes_id": l["pes_id"],
            "identificador": l["identificador"] or (l["matricula"] or "").strip() or None,
            "nome": l["nome_cadastro"] or l["nome_na_catraca"] or "(sem nome)",
            "tipo": l["tipo_codigo"],
            "curso": l["curso"],
            "turma": l["turma_nome"],
            "desde": l["desde"].isoformat(),
            "terminal": l["terminal"],
            # Falso quando a catraca conhece a pessoa e o cadastro academico
            # nao: ela esta no predio, mas nao entra na chamada de nenhuma aula.
            "identificado": l["identificador"] is not None,
        }
        for l in linhas
    ]


async def resumo_presenca(momento: Optional[datetime] = None) -> Dict[str, Any]:
    """Contagem por tipo, para o painel nao precisar trazer a lista inteira."""
    pessoas = await presentes_agora(momento)
    por_tipo: Dict[str, int] = {}
    for p in pessoas:
        chave = p["tipo"] or "NAO_IDENTIFICADO"
        por_tipo[chave] = por_tipo.get(chave, 0) + 1
    return {
        "total": len(pessoas),
        "identificados": sum(1 for p in pessoas if p["identificado"]),
        "por_tipo": por_tipo,
        "janela_horas": JANELA_PRESENCA_H,
    }


async def passagens_desde(marca: datetime, limite: int = 5000) -> List[Dict[str, Any]]:
    """Passagens autorizadas posteriores a `marca`, em ordem cronologica.

    Alimenta o motor de presenca. So devolve quem tem matricula que casa com o
    cadastro academico: o motor trabalha por RA, e evento sem RA nao tem aula a
    que pertencer.
    """
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            select v.mar_id, v.momento, v.sentido, v.terminal,
                   p.identificador
              from catraca.vw_passagem v
              join pessoa p
                on upper(p.identificador) = upper(trim(v.matricula))
               and p.origem = 'JACAD' and p.ativo
             where v.momento > $1
               and v.sentido in ('ENTRADA', 'SAIDA')
             order by v.momento
             limit $2
            """,
            marca,
            limite,
        )
    finally:
        await conexao.close()

    return [
        {
            "mar_id": str(l["mar_id"]),
            "ra": l["identificador"],
            "momento": l["momento"],
            "entrada": l["sentido"] == "ENTRADA",
            "terminal": l["terminal"],
        }
        for l in linhas
    ]


async def ultima_marcacao() -> Optional[datetime]:
    """Momento da passagem mais recente que chegou pela replicacao.

    Serve para o painel dizer ha quanto tempo o job nao traz nada - replicacao
    parada e indistinguivel de campus vazio, olhando so a contagem.
    """
    conexao = await abrir()
    try:
        return await conexao.fetchval(
            "select max(mar_datahora) from catraca.gac_marcacao"
        )
    finally:
        await conexao.close()


async def disponivel() -> bool:
    """Ha dados replicados para trabalhar."""
    conexao = await abrir()
    try:
        return bool(await conexao.fetchval(
            "select 1 from catraca.gac_marcacao limit 1"
        ))
    finally:
        await conexao.close()


async def identificadores_presentes(momento: Optional[datetime] = None) -> List[str]:
    """So os identificadores de quem esta dentro e casa com o cadastro.

    Versao enxuta de `presentes_agora` para quem so precisa do conjunto - o
    painel cruza isso com o cadastro do lado do banco e nao quer a lista inteira
    trafegando.
    """
    agora = momento or datetime.now()
    desde = agora - timedelta(hours=JANELA_PRESENCA_H)

    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            with ultima as (
                select distinct on (v.pes_id)
                       v.pes_id, v.sentido, v.matricula
                  from catraca.vw_passagem v
                 where v.pes_id is not null
                   and v.momento between $1 and $2
                 order by v.pes_id, v.momento desc
            )
            select distinct upper(trim(u.matricula)) as identificador
              from ultima u
             where u.sentido = 'ENTRADA'
               and u.matricula is not null and trim(u.matricula) <> ''
            """,
            desde,
            agora,
        )
    finally:
        await conexao.close()
    return [l["identificador"] for l in linhas]
