"""Parametros operacionais, resolvidos em tres camadas.

    valor no banco  >  variavel de ambiente  >  padrao do codigo

Assim um deploy pode continuar mandando tudo por ambiente, e o banco so entra
quando alguem ajusta pela tela. Um parametro com valor nulo no banco significa
"nao definido aqui" - nao significa zero.

Os valores ficam num cache em memoria porque sao lidos no caminho quente (a
cada passagem de catraca). O cache e recarregado no boot, apos cada edicao e
periodicamente, para uma instancia enxergar o que outra mudou.

Fora daqui de proposito: DATABASE_URL, JWT_SECRET, REDIS_URL e JACAD_TOKEN.
Os tres primeiros sao necessarios antes de existir conexao com o banco; o
ultimo e segredo que nao deve ser legivel por quem abre o painel.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import settings

# Padroes do codigo: valem quando nem o banco nem o ambiente dizem nada.
PADROES: Dict[str, Any] = {
    "TOLERANCIA_ATRASO_MIN": settings.TOLERANCIA_ATRASO_MIN,
    "JANELA_CHEGADA_ANTECIPADA_MIN": settings.JANELA_CHEGADA_ANTECIPADA_MIN,
    "LIMIAR_BAIXA_PRESENCA": settings.LIMIAR_BAIXA_PRESENCA,
    "CATRACA_TIMEOUT_S": settings.CATRACA_TIMEOUT_S,
    "JACAD_BASE_URL": settings.JACAD_BASE_URL,
    "JACAD_MODO_MOCK": settings.JACAD_MODO_MOCK,
    "JACAD_SYNC_INTERVAL_S": settings.JACAD_SYNC_INTERVAL_S,
    "SIMULADOR_ATIVO": settings.SIMULADOR_ATIVO,
    "TIMEZONE": settings.TIMEZONE,
    "TICK_DASHBOARD_S": settings.TICK_DASHBOARD_S,
    "MAX_EVENTOS_FEED": settings.MAX_EVENTOS_FEED,
}

# Mudancas que so valem apos reiniciar o processo.
EXIGEM_REINICIO = {"TIMEZONE", "SIMULADOR_ATIVO", "MAX_EVENTOS_FEED"}

_cache: Dict[str, Any] = {}


def _converter(valor: Optional[str], tipo: str) -> Any:
    if valor is None or valor == "":
        return None
    if tipo == "INTEIRO":
        try:
            return int(valor)
        except ValueError:
            return None
    if tipo == "BOOLEANO":
        return valor.strip().lower() in {"1", "true", "yes", "sim"}
    return valor


async def recarregar() -> int:
    """Le o banco para o cache. Sem banco, o cache fica vazio e valem os padroes."""
    global _cache

    if not settings.DATABASE_URL:
        _cache = {}
        return 0

    from app.data.conexao import abrir

    try:
        conexao = await abrir()
    except Exception as erro:
        print(f"[parametros] banco indisponivel ({erro}); usando o ambiente")
        return 0

    try:
        linhas = await conexao.fetch("select chave, valor, tipo from parametro")
    finally:
        await conexao.close()

    novo: Dict[str, Any] = {}
    for linha in linhas:
        convertido = _converter(linha["valor"], linha["tipo"])
        if convertido is not None:
            novo[linha["chave"]] = convertido

    _cache = novo
    return len(novo)


def obter(chave: str) -> Any:
    """Valor efetivo: banco, senao ambiente/padrao."""
    if chave in _cache:
        return _cache[chave]
    return PADROES.get(chave)


def origem(chave: str) -> str:
    return "banco" if chave in _cache else "ambiente"


# -- atalhos usados no caminho quente ---------------------------------------

def tolerancia_atraso_min() -> int:
    return int(obter("TOLERANCIA_ATRASO_MIN"))


def janela_chegada_min() -> int:
    return int(obter("JANELA_CHEGADA_ANTECIPADA_MIN"))


def limiar_baixa_presenca() -> int:
    return int(obter("LIMIAR_BAIXA_PRESENCA"))


def catraca_timeout_s() -> int:
    return int(obter("CATRACA_TIMEOUT_S"))


def jacad_modo_mock() -> bool:
    return bool(obter("JACAD_MODO_MOCK"))


def jacad_base_url() -> str:
    return obter("JACAD_BASE_URL") or ""


def jacad_sync_interval_s() -> int:
    return int(obter("JACAD_SYNC_INTERVAL_S"))


def simulador_ativo() -> bool:
    return bool(obter("SIMULADOR_ATIVO"))


def tick_catracas_s() -> int:
    """Intervalo de leitura do espelho das catracas.

    Nao adianta ser menor que o job de replicacao no SQL Server: o dado so
    aparece aqui depois que ele empurra.
    """
    return int(obter("TICK_CATRACAS_S") or 30)


def tick_dashboard_s() -> int:
    return int(obter("TICK_DASHBOARD_S"))
