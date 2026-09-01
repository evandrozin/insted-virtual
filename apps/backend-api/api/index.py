"""Ponto de entrada das Vercel Functions.

O runtime Python da Vercel promove a funcao os arquivos dentro de `api/`. A
chave `functions` do vercel.json apenas configura arquivos que ja sao funcao -
ela nao transforma um caminho qualquer em entrypoint. Por isso apontar direto
para `app/main.py` nao basta, e o rewrite do vercel.json manda todos os
caminhos para ca; o roteamento em si continua sendo do FastAPI.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401
