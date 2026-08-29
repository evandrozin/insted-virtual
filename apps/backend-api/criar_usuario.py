"""Cria a primeira conta de administracao do cadastro.

A senha e digitada aqui e vira hash scrypt antes de tocar o banco: ela nao
aparece em log, em historico de comando nem em nenhum arquivo.

Uso:
    DATABASE_URL=... python criar_usuario.py
"""
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402
from app.core.seguranca import gerar_hash_senha, gerar_segredo  # noqa: E402
from app.data import cadastro_repository as repo  # noqa: E402

PAPEIS = ("ADMIN", "SECRETARIA", "LEITURA")


async def principal() -> int:
    if not settings.DATABASE_URL:
        print("DATABASE_URL nao configurado.")
        print("Pegue a URI em Supabase > Settings > Database > Connection string.")
        return 1

    print("Criacao de usuario do cadastro Insted\n")

    email = input("E-mail: ").strip().lower()
    if "@" not in email:
        print("E-mail invalido.")
        return 1

    if await repo.buscar_usuario_por_email(email):
        print(f"Ja existe usuario ativo com {email}.")
        return 1

    nome = input("Nome: ").strip()
    if len(nome) < 2:
        print("Informe o nome.")
        return 1

    print(f"Papel {PAPEIS} - ADMIN e SECRETARIA editam, LEITURA so consulta.")
    papel = (input("Papel [ADMIN]: ").strip().upper() or "ADMIN")
    if papel not in PAPEIS:
        print(f"Papel invalido: {papel}")
        return 1

    senha = getpass.getpass("Senha (min. 8 caracteres): ")
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas nao conferem.")
        return 1

    try:
        senha_hash = gerar_hash_senha(senha)
    except ValueError as erro:
        print(erro)
        return 1

    usuario = await repo.criar_usuario(email, nome, senha_hash, papel)
    print(f"\nCriado: {usuario['nome']} <{usuario['email']}> como {usuario['papel']}.")

    if not settings.JWT_SECRET:
        print("\nFalta o JWT_SECRET para o login funcionar. Use este valor:")
        print(f"  JWT_SECRET={gerar_segredo()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
