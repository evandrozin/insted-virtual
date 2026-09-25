"""Escrita e leitura do cadastro: usuarios, salas e trilha de auditoria.

Toda alteracao de sala grava em `sala_auditoria` quem fez, quando e o que
mudou. Uma capacidade que muda no meio do semestre precisa ter autor.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.config import settings

CAMPOS_EDITAVEIS = (
    "nome", "tipo", "capacidade", "codigo_planta", "codigo_ensalamento",
    "rack_id", "pos_x", "pos_z", "largura", "profundidade", "observacao",
)


async def _conectar():
    from app.data.conexao import abrir

    return await abrir()


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

async def buscar_usuario_por_email(email: str) -> Optional[dict]:
    conexao = await _conectar()
    try:
        linha = await conexao.fetchrow(
            """
            select id, email, nome, senha_hash, papel, ativo
            from usuario
            where email = lower($1) and ativo
            """,
            email.strip(),
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


async def registrar_acesso(usuario_id: int) -> None:
    conexao = await _conectar()
    try:
        await conexao.execute(
            "update usuario set ultimo_acesso = now() where id = $1", usuario_id
        )
    finally:
        await conexao.close()


async def criar_usuario(email: str, nome: str, senha_hash: str, papel: str) -> dict:
    conexao = await _conectar()
    try:
        linha = await conexao.fetchrow(
            """
            insert into usuario (email, nome, senha_hash, papel)
            values (lower($1), $2, $3, $4)
            returning id, email, nome, papel, ativo
            """,
            email.strip(), nome.strip(), senha_hash, papel,
        )
    finally:
        await conexao.close()
    return dict(linha)


async def redefinir_senha(email: str, senha_hash: str) -> Optional[dict]:
    """Troca a senha de quem ja existe. Devolve None se o e-mail nao existir.

    Separado de `criar_usuario` de proposito: criar recusa e-mail repetido, que
    e a protecao certa contra duplicar conta por engano. Sem esta funcao, senha
    esquecida so se resolvia com UPDATE na mao - e quem faz isso precisa gerar
    o hash scrypt por fora, o que na pratica leva alguem a gravar senha em
    texto puro na coluna e derrubar o login inteiro.

    Reativa a conta junto: conta desativada com senha nova continuaria sem
    conseguir entrar, e o motivo nao apareceria em lugar nenhum.
    """
    conexao = await _conectar()
    try:
        linha = await conexao.fetchrow(
            """
            update usuario
               set senha_hash = $2, ativo = true, atualizado_em = now()
             where email = lower($1)
            returning id, email, nome, papel, ativo
            """,
            email.strip(), senha_hash,
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


async def listar_usuarios() -> List[dict]:
    conexao = await _conectar()
    try:
        linhas = await conexao.fetch(
            """
            select id, email, nome, papel, ativo, ultimo_acesso, criado_em
            from usuario order by nome
            """
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]


# ---------------------------------------------------------------------------
# Redefinicao de senha
# ---------------------------------------------------------------------------

async def pedido_recente(usuario_id: int, intervalo_s: int) -> bool:
    """Ja houve pedido para este usuario dentro do intervalo.

    Sem isso, quem souber um e-mail valido dispara mensagem sem limite e
    transforma a redefinicao num jeito de encher a caixa de entrada de alguem.
    """
    conexao = await _conectar()
    try:
        return bool(await conexao.fetchval(
            """
            select 1 from senha_reset
             where usuario_id = $1
               and criado_em > now() - make_interval(secs => $2)
             limit 1
            """,
            usuario_id, intervalo_s,
        ))
    finally:
        await conexao.close()


async def criar_codigo(usuario_id: int, codigo_hash: str, validade_min: int) -> None:
    """Guarda o codigo novo e invalida os anteriores do mesmo usuario.

    Invalidar antes de inserir e o que faz "pedi outro codigo" significar o que
    o usuario espera: o que chegou por ultimo e o unico que funciona. Sem isso
    todos os codigos do dia continuariam valendo ate expirar.
    """
    conexao = await _conectar()
    try:
        async with conexao.transaction():
            await conexao.execute(
                """
                update senha_reset set usado_em = now()
                 where usuario_id = $1 and usado_em is null
                """,
                usuario_id,
            )
            await conexao.execute(
                """
                insert into senha_reset (usuario_id, codigo_hash, expira_em)
                values ($1, $2, now() + make_interval(mins => $3))
                """,
                usuario_id, codigo_hash, validade_min,
            )
    finally:
        await conexao.close()


async def codigo_vigente(usuario_id: int) -> Optional[dict]:
    """O codigo ainda utilizavel deste usuario, se houver."""
    conexao = await _conectar()
    try:
        linha = await conexao.fetchrow(
            """
            select id, codigo_hash, tentativas
              from senha_reset
             where usuario_id = $1
               and usado_em is null
               and expira_em > now()
             order by criado_em desc
             limit 1
            """,
            usuario_id,
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


async def registrar_tentativa(reset_id: int, teto: int) -> None:
    """Conta a tentativa errada e queima o codigo ao bater o teto."""
    conexao = await _conectar()
    try:
        await conexao.execute(
            """
            update senha_reset
               set tentativas = tentativas + 1,
                   usado_em = case when tentativas + 1 >= $2 then now() else null end
             where id = $1
            """,
            reset_id, teto,
        )
    finally:
        await conexao.close()


async def consumir_codigo(reset_id: int, usuario_id: int, senha_hash: str) -> None:
    """Marca o codigo como usado e troca a senha, numa transacao so.

    Juntas de proposito: se a troca falhasse depois de marcar o codigo, o
    usuario ficaria sem senha nova e sem codigo para tentar de novo.
    """
    conexao = await _conectar()
    try:
        async with conexao.transaction():
            await conexao.execute(
                "update senha_reset set usado_em = now() where id = $1", reset_id
            )
            await conexao.execute(
                """
                update usuario
                   set senha_hash = $2, ativo = true, atualizado_em = now()
                 where id = $1
                """,
                usuario_id, senha_hash,
            )
    finally:
        await conexao.close()


# ---------------------------------------------------------------------------
# Salas
# ---------------------------------------------------------------------------

async def obter_sala(codigo: str) -> Optional[dict]:
    conexao = await _conectar()
    try:
        linha = await conexao.fetchrow(
            """
            select s.*, p.codigo as pavimento_codigo
            from sala s join pavimento p on p.id = s.pavimento_id
            where s.codigo = $1
            """,
            codigo,
        )
    finally:
        await conexao.close()
    return dict(linha) if linha else None


def _serializavel(registro: Optional[dict]) -> Optional[dict]:
    """Converte Decimal/datetime para algo que cabe em jsonb."""
    if registro is None:
        return None
    saida: Dict[str, Any] = {}
    for chave, valor in registro.items():
        if hasattr(valor, "isoformat"):
            saida[chave] = valor.isoformat()
        elif hasattr(valor, "quantize"):
            saida[chave] = float(valor)
        else:
            saida[chave] = valor
    return saida


async def criar_sala(dados: dict, autor: dict) -> dict:
    conexao = await _conectar()
    try:
        async with conexao.transaction():
            pavimento_id = await conexao.fetchval(
                """
                select p.id from pavimento p
                join predio pr on pr.id = p.predio_id
                where p.codigo = $1 and pr.codigo = $2
                """,
                dados["pavimento_codigo"], settings.PREDIO_CODIGO,
            )
            if pavimento_id is None:
                raise ValueError(
                    f"Pavimento desconhecido: {dados['pavimento_codigo']!r}"
                )

            linha = await conexao.fetchrow(
                """
                insert into sala (
                    pavimento_id, codigo, codigo_planta, codigo_ensalamento,
                    nome, tipo, capacidade, rack_id,
                    pos_x, pos_z, largura, profundidade, observacao
                ) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                returning *
                """,
                pavimento_id, dados["codigo"], dados.get("codigo_planta"),
                dados.get("codigo_ensalamento"), dados["nome"], dados["tipo"],
                dados.get("capacidade", 0), dados.get("rack_id"),
                dados.get("pos_x"), dados.get("pos_z"),
                dados.get("largura"), dados.get("profundidade"),
                dados.get("observacao"),
            )
            await _auditar(conexao, dados["codigo"], "CRIACAO", autor,
                           None, _serializavel(dict(linha)))
    finally:
        await conexao.close()
    return dict(linha)


async def atualizar_sala(codigo: str, mudancas: dict, autor: dict) -> dict:
    campos = {k: v for k, v in mudancas.items() if k in CAMPOS_EDITAVEIS}
    if not campos:
        raise ValueError("Nenhum campo editavel informado.")

    conexao = await _conectar()
    try:
        async with conexao.transaction():
            antes = await conexao.fetchrow("select * from sala where codigo = $1", codigo)
            if antes is None:
                raise ValueError(f"Sala nao encontrada: {codigo!r}")

            atribuicoes = ", ".join(
                f"{campo} = ${i + 2}" for i, campo in enumerate(campos)
            )
            depois = await conexao.fetchrow(
                f"update sala set {atribuicoes} where codigo = $1 returning *",
                codigo, *campos.values(),
            )
            await _auditar(conexao, codigo, "EDICAO", autor,
                           _serializavel(dict(antes)), _serializavel(dict(depois)))
    finally:
        await conexao.close()
    return dict(depois)


async def definir_situacao_sala(codigo: str, ativa: bool, autor: dict) -> dict:
    """Desativa em vez de apagar: a sala pode estar referenciada na grade."""
    conexao = await _conectar()
    try:
        async with conexao.transaction():
            antes = await conexao.fetchrow("select * from sala where codigo = $1", codigo)
            if antes is None:
                raise ValueError(f"Sala nao encontrada: {codigo!r}")
            depois = await conexao.fetchrow(
                "update sala set ativa = $2 where codigo = $1 returning *",
                codigo, ativa,
            )
            await _auditar(
                conexao, codigo, "REATIVACAO" if ativa else "DESATIVACAO",
                autor, _serializavel(dict(antes)), _serializavel(dict(depois)),
            )
    finally:
        await conexao.close()
    return dict(depois)


async def historico_da_sala(codigo: str, limite: int = 20) -> List[dict]:
    conexao = await _conectar()
    try:
        linhas = await conexao.fetch(
            """
            select acao, usuario_nome, antes, depois, criado_em
            from sala_auditoria
            where sala_codigo = $1
            order by criado_em desc
            limit $2
            """,
            codigo, limite,
        )
    finally:
        await conexao.close()
    return [dict(l) for l in linhas]


async def _auditar(conexao, codigo: str, acao: str, autor: dict,
                   antes: Optional[dict], depois: Optional[dict]) -> None:
    await conexao.execute(
        """
        insert into sala_auditoria
            (sala_codigo, acao, usuario_id, usuario_nome, antes, depois)
        values ($1, $2, $3, $4, $5, $6)
        """,
        codigo, acao, autor.get("id"), autor.get("nome"),
        json.dumps(antes) if antes else None,
        json.dumps(depois) if depois else None,
    )
