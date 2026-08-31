"""Relogio da aplicacao, no fuso do campus.

O servidor pode rodar em qualquer fuso - na Vercel roda em UTC - mas a grade
horaria e escrita em hora de parede local ("aula das 19:00"). Comparar a grade
contra o relogio do servidor faria o sistema procurar aula 4 horas fora do
lugar em Campo Grande.

Por isso `agora()` devolve sempre a hora de parede do campus, sem tzinfo: o
resto do codigo compara `datetime` ingenuo com `time` da grade, e os dois
passam a falar do mesmo fuso.

Para apresentacoes e possivel ancorar o relogio num horario letivo
(RELOGIO_DEMO=2026-08-28T19:10) e acelerar o tempo (SIMULADOR_FATOR_TEMPO=4).
Com varias instancias a ancora e negociada no EstadoStore, senao cada cold
start recomecaria a contagem.
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Campo Grande/MS (UTC-4). Trocavel por ambiente para outra unidade.
FUSO_PADRAO = "America/Campo_Grande"


def _resolver_fuso() -> ZoneInfo:
    nome = os.getenv("TIMEZONE", "").strip() or FUSO_PADRAO
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError):
        print(f"[relogio] fuso desconhecido: {nome!r}; usando {FUSO_PADRAO}")
        return ZoneInfo(FUSO_PADRAO)


_FUSO = _resolver_fuso()
_ANCORA_CONFIG: Optional[str] = os.getenv("RELOGIO_DEMO", "").strip() or None
_FATOR: int = max(1, int(os.getenv("SIMULADOR_FATOR_TEMPO", "1")))


def _relogio_do_campus() -> datetime:
    """Hora de parede em Campo Grande, independente do fuso do servidor."""
    return datetime.now(_FUSO).replace(tzinfo=None)


_inicio_real: datetime = _relogio_do_campus()
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
        return datetime.fromisoformat(valor).replace(tzinfo=None)
    except ValueError:
        print(f"[relogio] RELOGIO_DEMO invalido: {valor!r}; usando hora real")
        return None


if _ANCORA_CONFIG:
    _inicio_virtual = _interpretar_ancora(_ANCORA_CONFIG, _inicio_real)


async def inicializar(store) -> None:
    """Alinha a ancora do relogio entre as instancias.

    Sem modo demo nao ha o que combinar: todas usam a hora real do campus.
    """
    global _inicio_real, _inicio_virtual

    if _inicio_virtual is None and _FATOR == 1:
        return

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
    """Hora de parede do campus, ja com o modo demo aplicado."""
    if _inicio_virtual is None and _FATOR == 1:
        return _relogio_do_campus()

    decorrido = _relogio_do_campus() - _inicio_real
    base = _inicio_virtual or _inicio_real
    return base + timedelta(seconds=decorrido.total_seconds() * _FATOR)


def fuso() -> str:
    return str(_FUSO)


def em_modo_demo() -> bool:
    return _inicio_virtual is not None or _FATOR > 1


def descricao() -> str:
    if not em_modo_demo():
        return f"tempo real ({_FUSO})"
    if _inicio_virtual is None:
        return f"demo (fator {_FATOR}x, {_FUSO})"
    dias = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    ancora = f"{dias[_inicio_virtual.weekday()]} {_inicio_virtual.strftime('%d/%m %H:%M')}"
    return f"demo (ancora {ancora}, fator {_FATOR}x, {_FUSO})"
