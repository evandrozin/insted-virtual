"""Abertura de conexao com o Postgres.

Centralizado por causa de uma armadilha do Supabase: a "Transaction pooler"
(porta 6543) e um PgBouncer em modo transacao, que nao suporta prepared
statements nomeados. O asyncpg usa prepared statements por padrao, entao a
conexao abre e a primeira consulta falha com um erro pouco obvio
("prepared statement ... does not exist").

Detectamos o pooler pela porta/host e desligamos o cache de statements.
Direct connection e Session pooler seguem com o cache ligado.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.core.config import settings


def via_pooler_transacional(dsn: str) -> bool:
    try:
        alvo = urlparse(dsn)
    except ValueError:
        return False
    return alvo.port == 6543


def diagnosticar(dsn: str) -> str | None:
    """Devolve o que ha de errado com a DSN, ou None se estiver plausivel.

    Os erros aqui sao os que acontecem de verdade ao copiar do painel do
    Supabase, e o erro cru do driver nao ajuda a identificar nenhum deles.
    """
    if not dsn:
        return "DATABASE_URL vazio."

    if "=" in dsn.split("://", 1)[0]:
        nome = dsn.split("=", 1)[0]
        return (
            f"o valor comeca com {nome!r}: o nome da variavel foi colado junto. "
            "Cole apenas o que vem depois do sinal de igual."
        )

    if dsn.startswith(("http://", "https://")):
        return (
            "isso e a URL da API REST do Supabase, nao a do Postgres. "
            "No painel Connect, use a aba de conexao Postgres "
            "(Session pooler para rodar local, Transaction pooler para a "
            "Vercel) - o valor comeca com postgresql://."
        )

    if not dsn.startswith(("postgresql://", "postgres://")):
        return "a DSN precisa comecar com postgresql://."

    if "YOUR-PASSWORD" in dsn.upper() or "[SUA-SENHA]" in dsn.upper():
        return "a senha nao foi substituida: troque [YOUR-PASSWORD] pela senha real."

    if "@" not in dsn:
        return "falta usuario e senha antes do @ do host."

    return None


async def abrir(dsn: str | None = None, timeout: float = 15):
    """Conexao pronta para uso, com os ajustes do pooler quando necessario."""
    import asyncpg

    dsn = dsn or settings.DATABASE_URL
    problema = diagnosticar(dsn)
    if problema:
        raise RuntimeError(f"DATABASE_URL invalida: {problema}")

    extras = {}
    if via_pooler_transacional(dsn):
        # Sem cache de prepared statements o asyncpg conversa com o PgBouncer.
        extras["statement_cache_size"] = 0

    return await asyncpg.connect(dsn, timeout=timeout, **extras)


def descrever(dsn: str) -> str:
    """Resumo sem senha, para log."""
    if not dsn:
        return "nao configurado"
    problema = diagnosticar(dsn)
    if problema:
        return f"INVALIDA - {problema}"
    try:
        alvo = urlparse(dsn)
        modo = "pooler transacional" if alvo.port == 6543 else "conexao direta"
        return f"{alvo.hostname}:{alvo.port or 5432} ({modo})"
    except ValueError:
        return "url invalida"
