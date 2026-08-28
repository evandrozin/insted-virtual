"""Ponto de entrada das Vercel Functions.

A Vercel serve o objeto ASGI exportado deste arquivo. Todo o roteamento
continua sendo do FastAPI: veja `vercel.json` para o rewrite que manda
qualquer caminho para ca.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401
