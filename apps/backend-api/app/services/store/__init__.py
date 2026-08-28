"""Selecao do repositorio de estado.

Sem REDIS_URL o sistema opera em memoria, com o mesmo comportamento de antes.
Com REDIS_URL definido, o estado passa a ser compartilhado entre instancias.
"""
from __future__ import annotations

from app.core.config import settings
from app.services.store.base import CANAL_EVENTOS, EstadoStore
from app.services.store.memoria import MemoriaStore

_store: EstadoStore | None = None


def obter_store() -> EstadoStore:
    """Devolve o store do processo, criando-o na primeira chamada."""
    global _store
    if _store is None:
        if settings.REDIS_URL:
            from app.services.store.redis_store import RedisStore

            _store = RedisStore(settings.REDIS_URL)
        else:
            _store = MemoriaStore()
    return _store


def definir_store(store: EstadoStore) -> None:
    """Troca o store. Usado em testes."""
    global _store
    _store = store


__all__ = ["CANAL_EVENTOS", "EstadoStore", "MemoriaStore", "obter_store", "definir_store"]
