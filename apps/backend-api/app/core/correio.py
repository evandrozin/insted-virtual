"""Envio de e-mail por SMTP.

Existe para um proposito so: entregar o codigo de redefinicao de senha. Nao e
um servico de notificacao - se um dia precisar mandar relatorio ou alerta, vale
revisar a escolha, porque SMTP sincrono nao serve para volume.

Usa `smtplib` da biblioteca padrao. Uma API de terceiro (Resend, SendGrid) seria
mais simples de operar, mas traria dependencia nova, chave nova para guardar e
um remetente que nao e @insted.edu.br - e um e-mail de redefinicao de senha
vindo de dominio estranho e exatamente o que se ensina a desconfiar.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from app.core.config import settings


def configurado() -> bool:
    """Ha servidor de e-mail para usar."""
    return bool(settings.SMTP_HOST and settings.SMTP_USUARIO)


def remetente() -> str:
    return settings.SMTP_REMETENTE or settings.SMTP_USUARIO


def _montar(destino: str, assunto: str, texto: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = remetente()
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(texto)
    return msg


def enviar(destino: str, assunto: str, texto: str) -> None:
    """Manda a mensagem. Levanta em qualquer falha - quem chama decide.

    Bloqueante de proposito: e uma conexao SMTP por pedido de redefinicao, e
    pedido de redefinicao e raro. Quem chamar de dentro do event loop deve usar
    `asyncio.to_thread`, senao prende as outras conexoes durante o handshake.
    """
    if not configurado():
        raise RuntimeError(
            "SMTP nao configurado: defina SMTP_HOST, SMTP_USUARIO e SMTP_SENHA."
        )

    msg = _montar(destino, assunto, texto)
    contexto = ssl.create_default_context()

    if settings.SMTP_SSL:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, context=contexto, timeout=20
        ) as servidor:
            servidor.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
            servidor.send_message(msg)
        return

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as servidor:
        servidor.starttls(context=contexto)
        servidor.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
        servidor.send_message(msg)


def texto_codigo(nome: str, codigo: str, validade_min: int) -> str:
    """Mensagem do codigo de redefinicao.

    Texto puro, sem HTML nem link. Um link clicavel num e-mail de senha treina
    o usuario a clicar em link de e-mail de senha, que e o vetor de phishing
    mais comum que existe. Aqui ele digita o codigo na tela que ja estava
    aberta - nao ha para onde ser levado.
    """
    primeiro = (nome or "").split(" ")[0] or "Ola"
    return (
        f"{primeiro},\n\n"
        f"Seu codigo para redefinir a senha do painel Insted:\n\n"
        f"    {codigo}\n\n"
        f"Ele vale por {validade_min} minutos e so pode ser usado uma vez.\n"
        f"Digite-o na tela de redefinicao que voce ja tem aberta.\n\n"
        f"Se nao foi voce que pediu, ignore esta mensagem: nada muda enquanto "
        f"o codigo nao for usado.\n\n"
        f"-- \nPainel de Presenca - Insted Centro Universitario\n"
    )


def diagnostico() -> Optional[str]:
    """O que falta para o envio funcionar, ou None se esta pronto."""
    if not settings.SMTP_HOST:
        return "SMTP_HOST nao definido"
    if not settings.SMTP_USUARIO:
        return "SMTP_USUARIO nao definido"
    if not settings.SMTP_SENHA:
        return "SMTP_SENHA nao definida"
    return None
