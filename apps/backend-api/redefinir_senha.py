"""Redefine a senha de uma conta existente do cadastro.

Companheiro do criar_usuario.py, para o caso em que a conta existe e a senha se
perdeu. Ele recusa e-mail repetido - protecao certa contra duplicar conta por
engano -, entao sem este script a unica saida era UPDATE na mao no banco. E
quem faz isso precisa gerar o hash scrypt por fora; na pratica alguem acaba
gravando a senha em texto puro na coluna, e o login inteiro para de funcionar
sem dizer por que.

A senha e digitada aqui e vira hash antes de tocar o banco: nao aparece em log,
em historico de comando nem em arquivo nenhum.

Uso:
    DATABASE_URL=... python redefinir_senha.py
    DATABASE_URL=... python redefinir_senha.py --listar
"""
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402
from app.core.seguranca import gerar_hash_senha, gerar_segredo  # noqa: E402
from app.data import cadastro_repository as repo  # noqa: E402


async def _listar() -> int:
    usuarios = await repo.listar_usuarios()
    if not usuarios:
        print("Nenhuma conta cadastrada. Use criar_usuario.py.")
        return 1

    print(f"{'E-mail':<38} {'Nome':<24} {'Papel':<11} Ativa  Ultimo acesso")
    for u in usuarios:
        acesso = u["ultimo_acesso"].strftime("%d/%m/%Y %H:%M") if u["ultimo_acesso"] else "nunca"
        print(
            f"{u['email']:<38} {u['nome']:<24} {u['papel']:<11} "
            f"{'sim' if u['ativo'] else 'nao':<6} {acesso}"
        )
    return 0


async def principal() -> int:
    if not settings.DATABASE_URL:
        print("DATABASE_URL nao configurado.")
        print("No Supabase, a connection string fica no botao Connect do topo.")
        return 1

    if "--listar" in sys.argv:
        return await _listar()

    print("Redefinicao de senha do cadastro Insted\n")

    # Listar antes de perguntar: quem esqueceu a senha costuma nao lembrar
    # tambem com qual e-mail criou a conta.
    await _listar()
    print()

    email = input("E-mail da conta: ").strip().lower()
    if not email:
        print("Informe o e-mail.")
        return 1

    senha = getpass.getpass("Nova senha (min. 8 caracteres): ")
    if senha != getpass.getpass("Repita a senha: "):
        print("As senhas nao conferem.")
        return 1

    try:
        senha_hash = gerar_hash_senha(senha)
    except ValueError as erro:
        print(erro)
        return 1

    usuario = await repo.redefinir_senha(email, senha_hash)
    if usuario is None:
        print(f"Nao existe conta com {email}. Confira a lista acima.")
        return 1

    print(f"\nSenha redefinida: {usuario['nome']} <{usuario['email']}> "
          f"como {usuario['papel']}.")

    # Sem o segredo o login recusa qualquer senha, inclusive a que acabou de
    # ser definida - e a mensagem nao aponta para ca.
    if not settings.JWT_SECRET:
        print("\nFalta o JWT_SECRET para o login funcionar. Use este valor:")
        print(f"  JWT_SECRET={gerar_segredo()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
