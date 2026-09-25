"""Testa as credenciais de SMTP sem precisar publicar nada.

Existe por economia de tempo: sem ele, cada tentativa de acertar a configuracao
de e-mail custa um deploy, um pedido de codigo pelo painel e uma consulta ao
log da plataforma. Aqui o erro aparece em dois segundos, com o texto que o
servidor de e-mail devolveu.

Uso (as variaveis podem vir do .env, do ambiente ou da linha de comando):

    python testar_email.py                    # so conecta e autentica
    python testar_email.py fulano@insted.edu.br   # envia mensagem de teste

Nenhuma senha e impressa - so o diagnostico.
"""
import os
import smtplib
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import correio  # noqa: E402
from app.core.config import settings  # noqa: E402

# Erros conhecidos do Google e da Microsoft, com o que fazer. A mensagem crua do
# servidor e precisa mas nao diz a acao; sem esta traducao, "535 5.7.8" manda
# qualquer um conferir a senha - que e justamente o que nao adianta no Google.
PISTAS = [
    ("smtpclientauthentication is disabled",
     "Microsoft 365 com autenticacao basica desligada. So o administrador do "
     "tenant reabilita SMTP AUTH para essa caixa."),
    ("username and password not accepted",
     "Google: a senha normal da conta nao vale. Gere uma Senha de app em "
     "myaccount.google.com/apppasswords (exige verificacao em duas etapas) e "
     "use os 16 caracteres, sem espacos."),
    ("application-specific password required",
     "Google: a conta tem verificacao em duas etapas e exige Senha de app."),
    ("invalid credentials",
     "Usuario ou senha recusados. No Google, confirme que e a Senha de app."),
    ("sender address rejected",
     "O remetente nao bate com a caixa autenticada. Deixe SMTP_REMETENTE vazio "
     "ou igual a SMTP_USUARIO."),
    ("must issue a starttls command",
     "O servidor exige TLS. Com porta 587 deixe SMTP_SSL=false; com 465, true."),
    ("wrong version number",
     "TLS trocado: porta 465 pede SMTP_SSL=true, porta 587 pede false."),
]


def explicar(erro: Exception) -> str:
    texto = str(erro).lower()
    for marca, dica in PISTAS:
        if marca in texto:
            return dica
    return "Sem pista conhecida para este erro - leia a mensagem do servidor acima."


def principal() -> int:
    falta = correio.diagnostico()
    if falta:
        print(f"Configuracao incompleta: {falta}.")
        print("Defina SMTP_HOST, SMTP_USUARIO e SMTP_SENHA no ambiente ou no .env.")
        return 1

    destino = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"Servidor  : {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"Modo      : {'TLS direto' if settings.SMTP_SSL else 'STARTTLS'}")
    print(f"Usuario   : {settings.SMTP_USUARIO}")
    print(f"Remetente : {correio.remetente()}")
    # Nao imprime a senha. O tamanho basta para pegar o engano mais comum do
    # Google: colar os 16 caracteres com os espacos que a tela mostra.
    print(f"Senha     : {len(settings.SMTP_SENHA)} caracteres"
          + (" - o Google usa 16, sem espacos"
             if " " in settings.SMTP_SENHA or len(settings.SMTP_SENHA) != 16
             else ""))
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
                msg = correio._montar(
                    destino,
                    "Teste de envio - Painel Insted",
                    "Se voce recebeu isto, o SMTP do painel esta funcionando.\n",
                )
                servidor.send_message(msg)
                print(f"envio: ok para {destino}")
    except Exception as erro:
        print(f"\nFALHOU: {type(erro).__name__}: {erro}")
        print(f"\n-> {explicar(erro)}")
        return 1

    print("\nSMTP OK." + ("" if destino
                          else " Rode de novo com um e-mail no fim para enviar de verdade."))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
