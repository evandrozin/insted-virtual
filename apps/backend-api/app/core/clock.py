"""Relogio da aplicacao.

Em producao devolve a hora real. Para apresentacoes a diretoria e possivel
ancorar o relogio em um horario letivo (RELOGIO_DEMO=19:10) e acelerar a
passagem do tempo (SIMULADOR_FATOR_TEMPO=4), garantindo que a maquete sempre
tenha aulas em andamento na hora da demo.

Com varias instancias, a ancora precisa ser a mesma em todas - senao cada
cold start recomecaria a contagem e os painels mostrariam horas diferentes.
Por isso `inicializar` negocia a ancora no EstadoStore (o primeiro a chegar
define, os demais herdam) e a guarda localmente. Assim `agora()` continua
sincrono e sem custo, no caminho quente.
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Optional

_ANCORA_CONFIG: Optional[str] = os.getenv("RELOGIO_DEMO", "").strip() or None
_FATOR: int = max(1, int(os.getenv("SIMULADOR_FATOR_TEMPO", "1")))

_inicio_real: datetime = datetime.now()
_inicio_virtual: Optional[datetime] = None

if _ANCORA_CONFIG:
    _h, _m = (_ANCORA_CONFIG.split(":") + ["0"])[:2]
    _inicio_virtual = datetime.combine(_inicio_real.date(), time(int(_h), int(_m)))


async def inicializar(store) -> None:
    """Alinha a ancora do relogio entre as instancias.

    Sem modo demo nao ha o que combinar: todas usam a hora real.
    """
    global _inicio_real, _inicio_virtual

    if _inicio_virtual is None and _FATOR == 1:
        return

    # Grava a origem (instante real + instante virtual) como uma unica marca.
    marca = f"{_inicio_real.isoformat()}|{(_inicio_virtual or _inicio_real).isoformat()}"
    await store.definir_ancora_relogio(marca)

    combinada = await store.ancora_relogio()
    if not combinada or "|" not in combinada:
        return

    real_iso, virtual_iso = combinada.split("|", 1)
    try:
        _inicio_real = datetime.fromisoformat(real_iso)
        _inicio_virtual = datetime.fromisoformat(virtual_iso)
    except ValueError:
        pass


def agora() -> datetime:
    if _inicio_virtual is None and _FATOR == 1:
        return datetime.now()

    decorrido = datetime.now() - _inicio_real
    base = _inicio_virtual or _inicio_real
    return base + timedelta(seconds=decorrido.total_seconds() * _FATOR)


def em_modo_demo() -> bool:
    return _inicio_virtual is not None or _FATOR > 1


def descricao() -> str:
    if not em_modo_demo():
        return "tempo real"
    ancora = _inicio_virtual.strftime("%H:%M") if _inicio_virtual else "agora"
    return f"demo (ancora {ancora}, fator {_FATOR}x)"
