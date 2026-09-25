"""Testa o envio de e-mail sem precisar publicar nada.

Existe por economia de tempo: sem ele, cada tentativa de acertar a configuracao
custa um deploy, um pedido de codigo pelo painel e uma consulta ao log da
plataforma. Aqui o erro aparece em dois segundos, com o texto que o provedor
devolveu.

Testa o caminho que estiver configurado - Resend por HTTPS, ou SMTP.

Uso:
    python testar_email.py                        # confere a configuracao
    python testar_email.py fulano@insted.edu.br   # envia de verdade

Nenhuma credencial e impressa - so o diagnostico.
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import correio  # noqa: E402
from app.core.config import settings  # noqa: E402

# Erros conhecidos, com o que fazer. A mensagem crua do provedor e precisa mas
# nao diz a acao; sem esta traducao, "535 5.7.8" manda qualquer um conferir a
# senha - que e justamente o que nao adianta no Google.
PISTAS = [
    ("network is unreachable",
     "Porta SMTP bloqueada na saida. O Render bloqueia 25, 465 e 587 no plano "
     "free: use RESEND_API_KEY, que fala HTTPS na 443."),
    ("domain is not verified",
     "Resend: o dominio do remetente nao esta verificado. Verifique em "
     "resend.com/domains, ou use onboarding@resend.dev para testar."),
    ("invalid `from` field",
     "Resend: o remetente precisa pertencer a um dominio verificado."),
    ("api key is invalid",
     "Resend: RESEND_API_KEY incorreta. Gere outra em resend.com/api-keys."),
    ("you can only send testing emails to your own email",
     "Resend sem dominio verificado so entrega no e-mail do dono da conta. "
     "Verifique o dominio para enviar a qualquer destinatario."),
    ("smtpclientauthentication is disabled",
     "Microsoft 365 com autenticacao basica desligada. So o administrador do "
     "tenant reabilita SMTP AUTH para essa caixa."),
    ("username and password not accepted",
     "Google: a senha normal da conta nao vale. Gere uma Senha de app em "
     "myaccount.google.com/apppasswords e use os 16 caracteres, sem espacos."),
    ("application-specific password required",
     "Google: a conta tem verificacao em duas etapas e exige Senha de app."),
    ("sender address rejected",
     "O remetente nao bate com a caixa autenticada."),
    ("must issue a starttls command",
     "O servidor exige TLS. Com porta 587 use SMTP_SSL=false; com 465, true."),
    ("wrong version number",
     "TLS trocado: porta 465 pede SMTP_SSL=true, porta 587 pede false."),
]

ASSUNTO = "Teste de envio - Painel Insted"
CORPO = "Se voce recebeu isto, o envio do painel esta funcionando.\n"


def explicar(erro: Exception) -> str:
    texto = str(erro).lower()
    for marca, dica in PISTAS:
        if marca in texto:
            return dica
    return "Sem pista conhecida para este erro - leia a mensagem acima."


def _falhar(erro: Exception) -> int:
    print(f"\nFALHOU: {type(erro).__name__}: {erro}")
    print(f"\n-> {explicar(erro)}")
    return 1


def _resend(destino: Optional[str]) -> int:
    print(f"Remetente : {correio.remetente()}")
    print(f"Chave     : {len(settings.RESEND_API_KEY)} caracteres")
    print()

    # O Resend nao tem etapa de "so autenticar": a chave so e exercitada no
    # envio. Sem destino nao ha o que testar de verdade.
    if not destino:
        print("Configuracao completa. Para testar o envio de fato:")
        print("    python testar_email.py voce@exemplo.com")
        return 0

    try:
        correio.enviar(destino, ASSUNTO, CORPO)
    except Exception as erro:
        return _falhar(erro)

    print(f"envio: ok para {destino}")
    print("\nResend OK.")
    return 0


def _smtp(destino: Optional[str]) -> int:
    print(f"Servidor  : {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"Modo      : {'TLS direto' if settings.SMTP_SSL else 'STARTTLS'}")
    print(f"Usuario   : {settings.SMTP_USUARIO}")
    print(f"Remetente : {correio.remetente()}")
    # Nao imprime a senha. O tamanho basta para pegar o engano mais comum do
    # Google: colar os 16 caracteres com os espacos que a tela mostra.
    aviso = ""
    if " " in settings.SMTP_SENHA or len(settings.SMTP_SENHA) != 16:
        aviso = " - o Google usa 16, sem espacos"
    print(f"Senha     : {len(settings.SMTP_SENHA)} caracteres{aviso}")
    print()

    contexto = ssl.create_default_context()
    try:
        if settings.SMTP_SSL:
            servidor = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, context=contexto, timeout=20
            )
        else:
            servidor = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        with servidor:
            print("conexao: ok")
            if not settings.SMTP_SSL:
                servidor.starttls(context=contexto)
                print("starttls: ok")
            servidor.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
            print("autenticacao: ok")
            if destino:
                servidor.send_message(correio._montar(destino, ASSUNTO, CORPO))
                print(f"envio: ok para {destino}")
    except Exception as erro:
        return _falhar(erro)

    if destino:
        print("\nSMTP OK.")
    else:
        print("\nSMTP OK. Rode de novo com um e-mail no fim para enviar de verdade.")
    return 0


def principal() -> int:
    falta = correio.diagnostico()
    if falta:
        print(f"Configuracao incompleta: {falta}.")
        return 1

    destino = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"Provedor  : {correio.provedor()}")

    return _resend(destino) if correio.provedor() == "resend" else _smtp(destino)


if __name__ == "__main__":
    raise SystemExit(principal())
