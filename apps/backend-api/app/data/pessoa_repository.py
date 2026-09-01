"""Cadastro de pessoas e tipos.

O identificador e o mesmo no JACAD e no cracha da catraca, entao ele sozinho
resolve o cruzamento: uma passagem chega com o identificador e aqui se descobre
quem e a pessoa e o que a presenca dela significa.

Alunos vem do JACAD e sao reescritos a cada sync. Quem foi cadastrado a mao
(origem MANUAL) nunca e sobrescrito - senao o porteiro cadastrado pela
Secretaria sumiria no proximo sync.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.data.conexao import abrir

CAMPOS_EDITAVEIS = (
    "nome", "tipo_codigo", "email", "curso", "turma_id", "periodo",
    "setor", "cargo", "situacao", "observacao",
)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

async def listar_tipos(incluir_inativos: bool = False) -> List[dict]:
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            select codigo, nome, plural, conta_presenca_em_aula, cor, ordem, ativo,
                   (select count(*) from pessoa p
                     where p.tipo_codigo = t.codigo and p.ativo) as pessoas
            from tipo_pessoa t
            where ($1 or ativo)
            order by ordem, nome
            """,
            incluir_inativos,
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]


async def salvar_tipo(codigo: str, dados: dict) -> dict:
    """Cria ou atualiza um tipo. O codigo e a chave e nao muda."""
    conexao = await abrir()
    try:
        linha = await conexao.fetchrow(
            """
            insert into tipo_pessoa
                (codigo, nome, plural, conta_presenca_em_aula, cor, ordem, ativo)
            values (upper($1), $2, $3, $4, $5, $6, $7)
            on conflict (codigo) do update set
                nome = excluded.nome,
                plural = excluded.plural,
                conta_presenca_em_aula = excluded.conta_presenca_em_aula,
                cor = excluded.cor,
                ordem = excluded.ordem,
                ativo = excluded.ativo
            returning *
            """,
            codigo, dados["nome"], dados["plural"],
            dados.get("conta_presenca_em_aula", False), dados.get("cor"),
            dados.get("ordem", 100), dados.get("ativo", True),
        )
    finally:
        await conexao.close()
    return dict(linha)


# ---------------------------------------------------------------------------
# Pessoas
# ---------------------------------------------------------------------------

async def listar_pessoas(
    tipo: Optional[str] = None,
    busca: Optional[str] = None,
    limite: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    conexao = await abrir()
    try:
        condicoes = ["ativo"]
        parametros: List[Any] = []

        if tipo:
            parametros.append(tipo.upper())
            condicoes.append(f"tipo = ${len(parametros)}")
        if busca:
            parametros.append(f"%{busca.strip().lower()}%")
            n = len(parametros)
            condicoes.append(
                f"(lower(nome) like ${n} or lower(identificador) like ${n}"
                f" or lower(coalesce(turma_id, '')) like ${n}"
                f" or lower(coalesce(setor, '')) like ${n})"
            )

        onde = " and ".join(condicoes)
        total = await conexao.fetchval(
            f"select count(*) from vw_pessoa_completa where {onde}", *parametros
        )
        parametros.extend([limite, offset])
        linhas = await conexao.fetch(
            f"""
            select * from vw_pessoa_completa
            where {onde}
            order by tipo_ordem, nome
            limit ${len(parametros) - 1} offset ${len(parametros)}
            """,
            *parametros,
        )
    finally:
        await conexao.close()
    return {"total": total, "pessoas": [dict(l) for l in linhas]}


async def obter_pessoa(identificador: str) -> Optional[dict]:
    conexao = await abrir()
    try:
        linha = await conexao.fetchrow(
            "select * from vw_pessoa_completa where identificador = $1",
            identificador,
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


async def salvar_pessoa(dados: dict) -> dict:
    conexao = await abrir()
    try:
        linha = await conexao.fetchrow(
            """
            insert into pessoa (identificador, nome, tipo_codigo, email, curso,
                                turma_id, periodo, setor, cargo, situacao,
                                origem, observacao)
            values ($1,$2,upper($3),$4,$5,$6,$7,$8,$9,$10,$11,$12)
            on conflict (identificador) do update set
                nome = excluded.nome,
                tipo_codigo = excluded.tipo_codigo,
                email = excluded.email,
                curso = excluded.curso,
                turma_id = excluded.turma_id,
                periodo = excluded.periodo,
                setor = excluded.setor,
                cargo = excluded.cargo,
                situacao = excluded.situacao,
                observacao = excluded.observacao,
                ativo = true
            returning *
            """,
            dados["identificador"], dados["nome"], dados["tipo_codigo"],
            dados.get("email"), dados.get("curso"), dados.get("turma_id"),
            dados.get("periodo"), dados.get("setor"), dados.get("cargo"),
            dados.get("situacao", "ATIVO"), dados.get("origem", "MANUAL"),
            dados.get("observacao"),
        )
    finally:
        await conexao.close()
    return dict(linha)


async def definir_situacao(identificador: str, ativo: bool) -> Optional[dict]:
    conexao = await abrir()
    try:
        linha = await conexao.fetchrow(
            "update pessoa set ativo = $2 where identificador = $1 returning *",
            identificador, ativo,
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


# ---------------------------------------------------------------------------
# Sincronizacao com o JACAD
# ---------------------------------------------------------------------------

async def sincronizar_do_jacad(por_tipo: Dict[str, List[dict]]) -> Dict[str, Any]:
    """Reescreve as pessoas de origem JACAD a partir do ERP.

    `por_tipo` mapeia o codigo do tipo (ALUNO, PROFESSOR) para os registros ja
    normalizados daquele tipo. Cada registro traz identificador, nome e o que
    fizer sentido para ele - curso/turma/periodo para aluno, setor/cargo para
    docente.

    Duas regras que valem a pena declarar:

    * Quem foi cadastrado a mao (origem MANUAL) fica intocado. O porteiro que a
      Secretaria criou nao pode desaparecer porque o ERP nao o conhece.
    * A desativacao e feita **por tipo**. Varrer todos os JACAD de uma vez faria
      uma sincronizacao so de alunos desativar o corpo docente inteiro.
    """
    tipos = {t: lista for t, lista in por_tipo.items() if lista}
    if not tipos:
        return {"recebidos": 0, "gravados": 0, "desativados": 0, "por_tipo": {}}

    detalhe: Dict[str, Dict[str, int]] = {}

    conexao = await abrir()
    try:
        async with conexao.transaction():
            for tipo, pessoas in tipos.items():
                registros = [
                    (
                        r["identificador"], r["nome"], tipo, r.get("email"),
                        r.get("curso"), r.get("turma_id"), r.get("turma_nome"),
                        r.get("periodo"), r.get("setor"), r.get("cargo"),
                        r.get("situacao", "ATIVO"),
                    )
                    for r in pessoas
                ]
                await conexao.executemany(
                    """
                    insert into pessoa (identificador, nome, tipo_codigo, email,
                                        curso, turma_id, turma_nome, periodo,
                                        setor, cargo, situacao, origem, ativo,
                                        sincronizado_em)
                    values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'JACAD',true,now())
                    on conflict (identificador) do update set
                        nome = excluded.nome,
                        tipo_codigo = excluded.tipo_codigo,
                        email = excluded.email,
                        curso = excluded.curso,
                        turma_id = excluded.turma_id,
                        turma_nome = excluded.turma_nome,
                        periodo = excluded.periodo,
                        setor = excluded.setor,
                        cargo = excluded.cargo,
                        situacao = excluded.situacao,
                        ativo = true,
                        sincronizado_em = now(),
                        atualizado_em = now()
                    where pessoa.origem = 'JACAD'
                    """,
                    registros,
                )

                # Quem sumiu do ERP e desativado, nao apagado: pode haver
                # historico de presenca apontando para ele.
                #
                # A contagem sai de um CTE porque `fetchval` sobre
                # `update ... returning 1` devolveria o 1 da primeira linha, e
                # nao quantas foram alteradas - o numero reportado aqui era
                # sempre 0 ou 1.
                desativados = await conexao.fetchval(
                    """
                    with alterados as (
                        update pessoa
                           set ativo = false, atualizado_em = now()
                         where origem = 'JACAD' and ativo and tipo_codigo = $1
                           and identificador <> all($2::text[])
                        returning 1
                    )
                    select count(*) from alterados
                    """,
                    tipo,
                    [r["identificador"] for r in pessoas],
                )

                gravados = await conexao.fetchval(
                    """
                    select count(*) from pessoa
                     where origem = 'JACAD' and ativo and tipo_codigo = $1
                    """,
                    tipo,
                )

                detalhe[tipo] = {
                    "recebidos": len(pessoas),
                    "gravados": gravados or 0,
                    "desativados": desativados or 0,
                }
    finally:
        await conexao.close()

    return {
        "recebidos": sum(d["recebidos"] for d in detalhe.values()),
        "gravados": sum(d["gravados"] for d in detalhe.values()),
        "desativados": sum(d["desativados"] for d in detalhe.values()),
        "por_tipo": detalhe,
    }


async def resumo_por_tipo(no_campus: Optional[List[str]] = None) -> List[dict]:
    """Cadastrados e presentes por tipo.

    A contagem de presentes e feita no banco, cruzando com a lista de
    identificadores que estao no campus. Contar em Python exigiria trazer
    todas as pessoas e erraria assim que a paginacao cortasse a lista.
    """
    identificadores = list(no_campus or [])
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            select t.codigo, t.nome, t.plural, t.cor, t.ordem,
                   t.conta_presenca_em_aula,
                   count(p.id) filter (where p.ativo) as ativos,
                   count(p.id) filter (
                       where p.ativo and p.identificador = any($1::text[])
                   ) as no_campus
            from tipo_pessoa t
            left join pessoa p on p.tipo_codigo = t.codigo
            where t.ativo
            group by t.codigo, t.nome, t.plural, t.cor, t.ordem,
                     t.conta_presenca_em_aula
            order by t.ordem
            """,
            identificadores,
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]


async def contar_no_campus(identificadores: List[str]) -> int:
    """Quantos dos identificadores presentes existem no cadastro ativo."""
    if not identificadores:
        return 0
    conexao = await abrir()
    try:
        return await conexao.fetchval(
            "select count(*) from pessoa where ativo and identificador = any($1::text[])",
            list(identificadores),
        )
    finally:
        await conexao.close()


# ---------------------------------------------------------------------------
# Parametros operacionais
# ---------------------------------------------------------------------------

async def listar_parametros() -> List[dict]:
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            select chave, valor, tipo, categoria, rotulo, descricao, unidade,
                   minimo, maximo, ordem, atualizado_por, atualizado_em
            from parametro
            order by categoria, ordem, chave
            """
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]


async def gravar_parametro(chave: str, valor: Optional[str], autor: str) -> dict:
    """Grava o valor e registra quem mudou. Valor nulo devolve ao ambiente."""
    conexao = await abrir()
    try:
        async with conexao.transaction():
            antes = await conexao.fetchval(
                "select valor from parametro where chave = $1", chave
            )
            linha = await conexao.fetchrow(
                """
                update parametro
                   set valor = $2, atualizado_por = $3, atualizado_em = now()
                 where chave = $1
                returning *
                """,
                chave, valor, autor,
            )
            if linha is None:
                raise ValueError(f"Parametro desconhecido: {chave!r}")
            await conexao.execute(
                """
                insert into parametro_auditoria
                    (chave, valor_antes, valor_depois, usuario_nome)
                values ($1, $2, $3, $4)
                """,
                chave, antes, valor, autor,
            )
    finally:
        await conexao.close()
    return dict(linha)


async def historico_parametro(chave: str, limite: int = 20) -> List[dict]:
    conexao = await abrir()
    try:
        linhas = await conexao.fetch(
            """
            select valor_antes, valor_depois, usuario_nome, criado_em
            from parametro_auditoria
            where chave = $1 order by criado_em desc limit $2
            """,
            chave, limite,
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]
