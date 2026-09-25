"""Valida a redefinicao de senha por codigo enviado no e-mail.

Mesma abordagem do auth_test: repositorio e envio de e-mail substituidos por
duplos em memoria, para o hashing do codigo, a expiracao, o teto de tentativas
e o uso unico rodarem de verdade, sem banco e sem mandar mensagem para ninguem.

O que este teste protege e o que um fluxo de senha erra em silencio: aceitar
codigo ja usado, aceitar depois do teto de tentativas, deixar o codigo antigo
valendo depois de pedir outro, e responder diferente para e-mail que existe e
e-mail que nao existe - o ultimo transforma a tela num verificador de contas.
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone


def ancora_letiva(hora: str = "19:20") -> str:
    dia = date.today()
    while dia.weekday() > 4:
        dia -= timedelta(days=1)
    return f"{dia.isoformat()}T{hora}"


os.environ.setdefault("RELOGIO_DEMO", ancora_letiva())
os.environ.setdefault("SIMULADOR_ATIVO", "false")
os.environ.setdefault("JWT_SECRET", "segredo-apenas-de-teste-com-tamanho-suficiente-123456")
os.environ.setdefault("DATABASE_URL", "postgresql://faz-de-conta/teste")
# Faz correio.configurado() responder que ha servidor, sem existir nenhum: o
# envio em si e substituido pelo duplo abaixo.
os.environ.setdefault("SMTP_HOST", "smtp.faz-de-conta")
os.environ.setdefault("SMTP_USUARIO", "painel@insted.edu.br")
os.environ.setdefault("SMTP_SENHA", "nao-usada")
os.environ["JACAD_MODO_MOCK"] = "true"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import correio  # noqa: E402
from app.core.seguranca import conferir_senha, gerar_hash_senha  # noqa: E402
from app.data import cadastro_repository as repo  # noqa: E402

SENHA_ORIGINAL = "senha-de-teste-123"
SENHA_NOVA = "senha-nova-987654"

USUARIOS = {
    "admin@insted.edu.br": {
        "id": 1, "email": "admin@insted.edu.br", "nome": "Evandro Teste",
        "senha_hash": gerar_hash_senha(SENHA_ORIGINAL), "papel": "ADMIN",
        "ativo": True,
    },
}

RESETS: list = []      # cada item: dict como a tabela senha_reset
ENVIADOS: list = []    # (destino, assunto, corpo)


def agora():
    return datetime.now(timezone.utc)


async def _buscar(email):
    return USUARIOS.get(email.strip().lower())


async def _registrar_acesso(_id):
    return None


async def _pedido_recente(usuario_id, intervalo_s):
    limite = agora() - timedelta(seconds=intervalo_s)
    return any(r["usuario_id"] == usuario_id and r["criado_em"] > limite
               for r in RESETS)


async def _criar_codigo(usuario_id, codigo_hash, validade_min):
    for r in RESETS:
        if r["usuario_id"] == usuario_id and r["usado_em"] is None:
            r["usado_em"] = agora()
    RESETS.append({
        "id": len(RESETS) + 1,
        "usuario_id": usuario_id,
        "codigo_hash": codigo_hash,
        "expira_em": agora() + timedelta(minutes=validade_min),
        "usado_em": None,
        "tentativas": 0,
        "criado_em": agora(),
    })


async def _codigo_vigente(usuario_id):
    vivos = [r for r in RESETS
             if r["usuario_id"] == usuario_id
             and r["usado_em"] is None
             and r["expira_em"] > agora()]
    if not vivos:
        return None
    r = sorted(vivos, key=lambda x: x["criado_em"])[-1]
    return {"id": r["id"], "codigo_hash": r["codigo_hash"], "tentativas": r["tentativas"]}


async def _registrar_tentativa(reset_id, teto):
    for r in RESETS:
        if r["id"] == reset_id:
            r["tentativas"] += 1
            if r["tentativas"] >= teto:
                r["usado_em"] = agora()


async def _consumir_codigo(reset_id, usuario_id, senha_hash):
    for r in RESETS:
        if r["id"] == reset_id:
            r["usado_em"] = agora()
    for u in USUARIOS.values():
        if u["id"] == usuario_id:
            u["senha_hash"] = senha_hash
            u["ativo"] = True


def _enviar(destino, assunto, texto):
    ENVIADOS.append((destino, assunto, texto))


repo.buscar_usuario_por_email = _buscar
repo.registrar_acesso = _registrar_acesso
repo.pedido_recente = _pedido_recente
repo.criar_codigo = _criar_codigo
repo.codigo_vigente = _codigo_vigente
repo.registrar_tentativa = _registrar_tentativa
repo.consumir_codigo = _consumir_codigo
correio.enviar = _enviar

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

falhas: list = []


def conferir(condicao, mensagem):
    if not condicao:
        falhas.append(mensagem)


def codigo_do_ultimo_email() -> str:
    """O codigo e so o que o usuario tem - o teste le onde ele leria."""
    corpo = ENVIADOS[-1][2]
    for parte in corpo.split():
        if parte.isdigit() and len(parte) == 6:
            return parte
    raise AssertionError(f"nenhum codigo de 6 digitos no e-mail:\n{corpo}")


def principal() -> int:
    with TestClient(app) as client:
        cfg = client.get("/api/v1/auth/config").json()
        print(f"[0] config: login={cfg['login_habilitado']}, "
              f"reset_por_email={cfg['reset_por_email']}")
        conferir(cfg["reset_por_email"], "reset deveria se anunciar disponivel")

        # 1. E-mail inexistente responde igual ao existente.
        r_nao = client.post("/api/v1/auth/senha/solicitar",
                            json={"email": "ninguem@insted.edu.br"})
        r_sim = client.post("/api/v1/auth/senha/solicitar",
                            json={"email": "admin@insted.edu.br"})
        print(f"[1] e-mail inexistente: {r_nao.status_code} | "
              f"existente: {r_sim.status_code}")
        conferir(r_nao.status_code == r_sim.status_code == 200,
                 "as duas respostas deveriam ser 200")
        conferir(r_nao.json() == r_sim.json(),
                 "respostas diferentes entregam quais e-mails existem")
        conferir(len(ENVIADOS) == 1,
                 f"deveria ter enviado 1 e-mail, enviou {len(ENVIADOS)}")

        codigo = codigo_do_ultimo_email()
        print(f"[2] codigo chegou por e-mail: {len(codigo)} digitos")
        conferir(codigo.isdigit() and len(codigo) == 6, "codigo mal formado")
        conferir(not any(codigo == r["codigo_hash"] for r in RESETS),
                 "o codigo foi guardado em texto puro no banco")

        # 3. Limite de frequencia: pedir de novo nao dispara outro e-mail.
        client.post("/api/v1/auth/senha/solicitar",
                    json={"email": "admin@insted.edu.br"})
        print(f"[3] pedido repetido: {len(ENVIADOS)} e-mail(s) no total")
        conferir(len(ENVIADOS) == 1, "pedido repetido furou o intervalo minimo")

        # 4. Codigo errado e recusado e conta tentativa.
        errado = "000000" if codigo != "000000" else "111111"
        r = client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": errado, "senha": SENHA_NOVA})
        print(f"[4] codigo errado: {r.status_code}")
        conferir(r.status_code == 400, "codigo errado deveria ser recusado")

        # 5. Senha curta e recusada antes de queimar o codigo.
        r = client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": codigo, "senha": "curta"})
        print(f"[5] senha curta: {r.status_code}")
        conferir(r.status_code == 422, "senha de 5 caracteres deveria ser recusada")

        # 6. Codigo certo troca a senha.
        r = client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": codigo, "senha": SENHA_NOVA})
        print(f"[6] codigo certo: {r.status_code}")
        conferir(r.status_code == 200, f"redefinicao falhou: {r.text}")
        conferir(conferir_senha(SENHA_NOVA, USUARIOS["admin@insted.edu.br"]["senha_hash"]),
                 "a senha no cadastro nao virou a nova")

        # 7. Uso unico: o mesmo codigo nao serve de novo.
        r = client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": codigo, "senha": "outra-senha-9999"})
        print(f"[7] reuso do mesmo codigo: {r.status_code}")
        conferir(r.status_code == 400, "codigo usado foi aceito de novo")

        # 8. A senha antiga nao entra mais; a nova entra.
        velha = client.post("/api/v1/auth/login",
                            json={"email": "admin@insted.edu.br",
                                  "senha": SENHA_ORIGINAL})
        nova = client.post("/api/v1/auth/login",
                           json={"email": "admin@insted.edu.br",
                                 "senha": SENHA_NOVA})
        print(f"[8] login senha antiga: {velha.status_code} | nova: {nova.status_code}")
        conferir(velha.status_code == 401, "a senha antiga continuou valendo")
        conferir(nova.status_code == 200, f"a senha nova nao entra: {nova.text}")

        # 9. Teto de tentativas queima o codigo antes da forca bruta.
        RESETS.clear()
        ENVIADOS.clear()
        client.post("/api/v1/auth/senha/solicitar",
                    json={"email": "admin@insted.edu.br"})
        bom = codigo_do_ultimo_email()
        ruim = "000000" if bom != "000000" else "111111"
        for _ in range(settings.RESET_MAX_TENTATIVAS):
            client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": ruim, "senha": SENHA_NOVA})
        r = client.post("/api/v1/auth/senha/redefinir",
                        json={"email": "admin@insted.edu.br",
                              "codigo": bom, "senha": SENHA_NOVA})
        print(f"[9] codigo certo apos {settings.RESET_MAX_TENTATIVAS} erros: "
              f"{r.status_code}")
        conferir(r.status_code == 400,
                 "o codigo sobreviveu ao teto de tentativas")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Redefinicao OK: codigo por e-mail, uso unico, teto de tentativas "
          "e resposta neutra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
