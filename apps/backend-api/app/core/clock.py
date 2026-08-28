"""Relogio da aplicacao.

Em producao devolve a hora real. Para apresentacoes a diretoria e possivel
ancorar o relogio em um horario letivo (RELOGIO_DEMO=19:10) e opcionalmente
acelerar a passagem do tempo (SIMULADOR_FATOR_TEMPO=60 => 1 min por segundo),
garantindo que a maquete sempre tenha aulas em andamento na hora da demo.
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
    _inicio_virtual = datetime.combine(
        _inicio_real.date(), time(int(_h), int(_m))
    )


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
