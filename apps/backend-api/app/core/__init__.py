"""Nucleo da aplicacao.

Carrega o `.env` aqui, e nao em config.py, porque `clock.py` le o ambiente no
momento da importacao: se o .env so fosse lido junto com o config, quem
importasse o clock primeiro veria as variaveis vazias.
"""
import os
from pathlib import Path


def _carregar_env() -> None:
    arquivo = Path(__file__).resolve().parents[2] / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        # Aspas sao conveniencia de edicao, nao fazem parte do valor.
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        # Ambiente ja definido vence: em producao o painel da plataforma manda.
        os.environ.setdefault(chave, valor)


_carregar_env()
