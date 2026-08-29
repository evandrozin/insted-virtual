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


async def abrir(dsn: str | None = None, timeout: float = 15):
    """Conexao pronta para uso, com os ajustes do pooler quando necessario."""
    import asyncpg

    dsn = dsn or settings.DATABASE_URL
    if not dsn:
        raise RuntimeError("DATABASE_URL nao configurado.")

    extras = {}
    if via_pooler_transacional(dsn):
        # Sem cache de prepared statements o asyncpg conversa com o PgBouncer.
        extras["statement_cache_size"] = 0

    return await asyncpg.connect(dsn, timeout=timeout, **extras)


def descrever(dsn: str) -> str:
    """Resumo sem senha, para log."""
    if not dsn:
        return "nao configurado"
    try:
        alvo = urlparse(dsn)
        modo = "pooler transacional" if alvo.port == 6543 else "conexao direta"
        return f"{alvo.hostname}:{alvo.port or 5432} ({modo})"
    except ValueError:
        return "url invalida"
