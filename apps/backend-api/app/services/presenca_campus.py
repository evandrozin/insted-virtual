"""Quem esta no predio agora, vindo da melhor fonte disponivel.

Existem duas: as catracas replicadas e o estado interno alimentado pelo
simulador. A escolha nao e configuravel de proposito - havendo marcacao real, e
ela que vale. Um sistema que mostra numero simulado quando existe numero real
seria pior que um que nao mostra nada.
"""
from __future__ import annotations

from typing import List, Tuple

from app.core.config import settings
from app.services.store import obter_store


async def identificadores_no_campus() -> Tuple[List[str], str]:
    """Devolve (identificadores, fonte). `fonte` e "catracas" ou "simulador"."""
    if settings.DATABASE_URL:
        try:
            from app.data import catraca_repository as catracas

            if await catracas.disponivel():
                return await catracas.identificadores_presentes(), "catracas"
        except Exception as erro:
            # Espelho fora do ar nao pode derrubar a tela: cai para o interno e
            # deixa registro de por que o numero mudou de origem.
            print(f"[presenca] espelho das catracas indisponivel ({erro}); usando o interno")

    return sorted(await obter_store().alunos_no_campus()), "simulador"
