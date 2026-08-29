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


def _interpretar_ancora(valor: str, hoje: datetime) -> Optional[datetime]:
    """Aceita "19:10" (hoje nesse horario) ou uma data ISO completa.

    A forma com data existe porque a grade so tem aula de segunda a sexta:
    ancorar so a hora num sabado mostraria o campus vazio.
    """
    valor = valor.strip()
    if not valor:
        return None
    if ":" in valor and "-" not in valor and "T" not in valor:
        h, m = (valor.split(":") + ["0"])[:2]
        return datetime.combine(hoje.date(), time(int(h), int(m)))
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        print(f"[relogio] RELOGIO_DEMO invalido: {valor!r}; usando hora real")
        return None


if _ANCORA_CONFIG:
    _inicio_virtual = _interpretar_ancora(_ANCORA_CONFIG, _inicio_real)


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
    if _inicio_virtual is None:
        return f"demo (fator {_FATOR}x)"
    dias = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    ancora = f"{dias[_inicio_virtual.weekday()]} {_inicio_virtual.strftime('%d/%m %H:%M')}"
    return f"demo (ancora {ancora}, fator {_FATOR}x)"
