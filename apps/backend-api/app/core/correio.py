"""Envio de e-mail: Resend (HTTPS) ou SMTP.

Existe para um proposito so: entregar o codigo de redefinicao de senha. Nao e
servico de notificacao - se um dia precisar mandar relatorio ou alerta, vale
revisar, porque nenhum dos dois caminhos aqui foi pensado para volume.

Por que dois caminhos, e por que o Resend virou o padrao:

    O primeiro desenho era so SMTP, pela instituicao ja ter servidor de e-mail
    e o codigo sair de um @insted.edu.br sem dependencia nova. Em producao
    apareceu `OSError: [Errno 101] Network is unreachable` na porta 587 - o
    Render bloqueia saida nas portas SMTP (25, 465 e 587) nos servicos do plano
    free. Nao e credencial: o pacote nao sai da maquina.

    O Resend fala HTTPS na 443, que nenhuma plataforma bloqueia, e usa o httpx
    que o projeto ja tem. O remetente continua institucional desde que o
    dominio esteja verificado no painel do Resend.

    O SMTP fica porque continua sendo o caminho certo em qualquer host que nao
    bloqueie a porta - instancia paga do Render, container proprio, servidor da
    propria instituicao. Quem manda e a configuracao: com RESEND_API_KEY vai
    por HTTPS, senao cai no SMTP.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

import httpx

from app.core.config import settings

RESEND_URL = "https://api.resend.com/emails"

# Ultimo resultado de envio, para a tela de Configuracao poder mostrar.
#
# A resposta do endpoint publico e neutra de proposito - dizer "nao consegui
# enviar" confirmaria que a conta existe. Mas quem administra precisa ver a
# falha em algum lugar, e o log da plataforma nao e lugar que se consulte no
# meio de um atendimento.
_ultimo_erro: Optional[str] = None
_ultimo_envio: Optional[str] = None


def ultimo_resultado() -> dict:
    return {"erro": _ultimo_erro, "enviado_em": _ultimo_envio}


def provedor() -> Optional[str]:
    """Qual caminho esta configurado. None = nenhum."""
    if settings.RESEND_API_KEY:
        return "resend"
    if settings.SMTP_HOST and settings.SMTP_USUARIO:
        return "smtp"
    return None


def configurado() -> bool:
    return provedor() is not None


def remetente() -> str:
    """Endereco que aparece no "De:".

    EMAIL_REMETENTE e o nome novo, valido para os dois provedores. SMTP_USUARIO
    continua servindo de padrao para quem ja configurou so o SMTP - nesse caso
    o remetente e a propria caixa autenticada, que e o que o servidor exige.
    """
    return (
        settings.EMAIL_REMETENTE
        or settings.SMTP_REMETENTE
        or settings.SMTP_USUARIO
    )


def diagnostico() -> Optional[str]:
    """O que falta para o envio funcionar, ou None se esta pronto."""
    escolhido = provedor()
    if escolhido is None:
        return "defina RESEND_API_KEY (recomendado) ou SMTP_HOST e SMTP_USUARIO"
    if escolhido == "resend" and not remetente():
        return "EMAIL_REMETENTE nao definido"
    if escolhido == "smtp" and not settings.SMTP_SENHA:
        return "SMTP_SENHA nao definida"
    return None


def _montar(destino: str, assunto: str, texto: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = remetente()
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(texto)
    return msg


def _enviar_resend(destino: str, assunto: str, texto: str) -> None:
    resposta = httpx.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": remetente(),
            "to": [destino],
            "subject": assunto,
            # Texto puro, sem "html": ver o comentario em texto_codigo sobre
            # link clicavel em e-mail de senha.
            "text": texto,
        },
        timeout=20,
    )
    if resposta.status_code >= 400:
        # A mensagem do Resend e especifica ("The insted.edu.br domain is not
        # verified") e e ela que aparece na tela de Configuracao. Um
        # raise_for_status devolveria so o codigo HTTP.
        try:
            corpo = resposta.json()
            detalhe = corpo.get("message") or corpo.get("name") or resposta.text
        except Exception:
            detalhe = resposta.text
        raise RuntimeError(f"Resend HTTP {resposta.status_code}: {detalhe}")


def _enviar_smtp(destino: str, assunto: str, texto: str) -> None:
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


def enviar(destino: str, assunto: str, texto: str) -> None:
    """Manda a mensagem pelo provedor configurado. Levanta em qualquer falha.

    Bloqueante de proposito: e uma chamada por pedido de redefinicao, e pedido
    de redefinicao e raro. Quem chamar de dentro do event loop deve usar
    `asyncio.to_thread`, senao prende as outras conexoes durante a ida e volta.
    """
    global _ultimo_erro, _ultimo_envio

    falta = diagnostico()
    if falta:
        raise RuntimeError(f"Envio de e-mail nao configurado: {falta}.")

    try:
        if provedor() == "resend":
            _enviar_resend(destino, assunto, texto)
        else:
            _enviar_smtp(destino, assunto, texto)
    except Exception as erro:
        # Guarda e repassa: quem chamou decide o que responder ao usuario, e a
        # tela de Configuracao passa a ter o motivo.
        _ultimo_erro = f"{type(erro).__name__}: {erro}"
        raise

    _ultimo_erro = None
    _ultimo_envio = datetime.now(timezone.utc).isoformat(timespec="seconds")


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
