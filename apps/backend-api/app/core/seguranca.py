"""Senhas e tokens de sessao.

Hashing com `hashlib.scrypt`, da biblioteca padrao: evita dependencia nativa
que precisaria compilar no deploy serverless, e scrypt e adequado para senhas
(custo de memoria alto, resistente a GPU).

Formato guardado no banco:
    scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings

# Parametros de custo. n=2**14 leva ~50ms por verificacao numa CPU modesta:
# suficiente contra forca bruta, sem pesar no login.
_N = 2 ** 14
_R = 8
_P = 1
_TAMANHO_CHAVE = 32
_TAMANHO_SALT = 16


def gerar_hash_senha(senha: str) -> str:
    if len(senha) < 8:
        raise ValueError("A senha precisa ter ao menos 8 caracteres.")
    salt = os.urandom(_TAMANHO_SALT)
    chave = hashlib.scrypt(
        senha.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_TAMANHO_CHAVE
    )
    return "$".join([
        "scrypt", str(_N), str(_R), str(_P),
        base64.b64encode(salt).decode(),
        base64.b64encode(chave).decode(),
    ])


def conferir_senha(senha: str, guardado: str) -> bool:
    """Compara em tempo constante. Nunca levanta por hash malformado."""
    try:
        algoritmo, n, r, p, salt_b64, hash_b64 = guardado.split("$")
        if algoritmo != "scrypt":
            return False
        chave = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
            dklen=len(base64.b64decode(hash_b64)),
        )
        return hmac.compare_digest(chave, base64.b64decode(hash_b64))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Token de sessao
# ---------------------------------------------------------------------------

# HS256 usa HMAC-SHA256: chave menor que 32 bytes enfraquece a assinatura.
TAMANHO_MINIMO_SEGREDO = 32


def _segredo() -> str:
    if not settings.JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET nao configurado: defina a variavel para habilitar o login."
        )
    if len(settings.JWT_SECRET) < TAMANHO_MINIMO_SEGREDO:
        raise RuntimeError(
            f"JWT_SECRET curto demais ({len(settings.JWT_SECRET)} caracteres). "
            f"Use ao menos {TAMANHO_MINIMO_SEGREDO}; gere um com "
            f"`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
        )
    return settings.JWT_SECRET


def login_habilitado() -> bool:
    """O login so funciona com um segredo forte configurado."""
    return len(settings.JWT_SECRET) >= TAMANHO_MINIMO_SEGREDO


def emitir_token(usuario_id: int, email: str, papel: str) -> str:
    import jwt

    agora = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario_id),
            "email": email,
            "papel": papel,
            "iat": agora,
            "exp": agora + timedelta(hours=settings.SESSAO_HORAS),
        },
        _segredo(),
        algorithm="HS256",
    )


def ler_token(token: str) -> Optional[dict]:
    """Devolve o conteudo do token, ou None se invalido/expirado."""
    import jwt

    try:
        return jwt.decode(token, _segredo(), algorithms=["HS256"])
    except Exception:
        return None


def gerar_segredo() -> str:
    """Ajuda para gerar um JWT_SECRET forte."""
    return secrets.token_urlsafe(48)
