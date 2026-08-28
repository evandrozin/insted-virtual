"""Configuracao central da API do Motor de Ocupacao Insted."""
import os
from typing import List


def _bool(chave: str, padrao: bool) -> bool:
    return os.getenv(chave, str(padrao)).strip().lower() in {"1", "true", "yes", "sim"}


def _int(chave: str, padrao: int) -> int:
    try:
        return int(os.getenv(chave, padrao))
    except (TypeError, ValueError):
        return padrao


class Settings:
    PROJECT_NAME: str = "Insted Virtual Campus - Motor de Ocupacao"
    API_V1_PREFIX: str = "/api/v1"

    # --- Integracao ERP JACAD ---------------------------------------------
    JACAD_BASE_URL: str = os.getenv("JACAD_BASE_URL", "")
    JACAD_TOKEN: str = os.getenv("JACAD_TOKEN", "")
    # Sem credenciais reais o adapter cai no dataset sintetico determinstico.
    JACAD_MODO_MOCK: bool = _bool("JACAD_MODO_MOCK", True)
    JACAD_SYNC_INTERVAL_S: int = _int("JACAD_SYNC_INTERVAL_S", 900)

    # --- Regras de presenca -----------------------------------------------
    TOLERANCIA_ATRASO_MIN: int = _int("TOLERANCIA_ATRASO_MIN", 15)
    JANELA_CHEGADA_ANTECIPADA_MIN: int = _int("JANELA_CHEGADA_ANTECIPADA_MIN", 45)
    LIMIAR_BAIXA_PRESENCA: int = _int("LIMIAR_BAIXA_PRESENCA", 60)
    CATRACA_TIMEOUT_S: int = _int("CATRACA_TIMEOUT_S", 900)

    # --- Estado compartilhado ---------------------------------------------
    # Vazio => estado em memoria (instancia unica, comportamento padrao).
    # Definido => estado e broadcast via Redis, permitindo varias instancias
    # e deploy serverless (Vercel Functions).
    REDIS_URL: str = os.getenv("REDIS_URL", "") or os.getenv("KV_URL", "")

    # Protege o endpoint de cron que dispara a reconciliacao.
    CRON_SECRET: str = os.getenv("CRON_SECRET", "")

    # Loops de fundo (reconciliacao + resync do JACAD). Em serverless nao ha
    # processo entre requisicoes: desligue e use o Vercel Cron.
    LOOP_INTERNO: bool = _bool("LOOP_INTERNO", not bool(os.getenv("VERCEL")))

    # --- Tempo real --------------------------------------------------------
    TICK_DASHBOARD_S: int = _int("TICK_DASHBOARD_S", 5)
    SIMULADOR_ATIVO: bool = _bool("SIMULADOR_ATIVO", True)
    SIMULADOR_INTERVALO_MS: int = _int("SIMULADOR_INTERVALO_MS", 700)
    # Acelera o relogio da demo (1 = tempo real, 60 = 1 min/segundo).
    SIMULADOR_FATOR_TEMPO: int = _int("SIMULADOR_FATOR_TEMPO", 1)

    CORS_ORIGINS: List[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")

    MAX_EVENTOS_FEED: int = _int("MAX_EVENTOS_FEED", 60)
    MAX_ALERTAS: int = _int("MAX_ALERTAS", 40)


settings = Settings()
