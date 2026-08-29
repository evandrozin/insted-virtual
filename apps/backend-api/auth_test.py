"""Valida login, permissao por papel e regras de edicao do cadastro.

Substitui o repositorio por um duplo em memoria: assim o hashing de senha, a
emissao/leitura de token e toda a logica de autorizacao e validacao rodam de
verdade, sem precisar de banco nem de credencial.

O SQL de escrita e a trilha de auditoria foram exercitados separadamente,
contra o Postgres real.
"""
import os
import sys
from datetime import date, timedelta


def ancora_letiva(hora: str = "19:20") -> str:
    dia = date.today()
    while dia.weekday() > 4:
        dia -= timedelta(days=1)
    return f"{dia.isoformat()}T{hora}"


os.environ.setdefault("RELOGIO_DEMO", ancora_letiva())
os.environ.setdefault("SIMULADOR_ATIVO", "false")
# Segredo forte o bastante para HS256; vale so dentro deste teste.
os.environ.setdefault("JWT_SECRET", "segredo-apenas-de-teste-com-tamanho-suficiente-123456")
os.environ.setdefault("DATABASE_URL", "postgresql://faz-de-conta/teste")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.seguranca import gerar_hash_senha  # noqa: E402
from app.data import cadastro_repository as repo  # noqa: E402

# --- duplo do repositorio ---------------------------------------------------

SENHA_BOA = "senha-de-teste-123"

USUARIOS = {
    "secretaria@insted.edu.br": {
        "id": 1, "email": "secretaria@insted.edu.br", "nome": "Maria da Secretaria",
        "senha_hash": gerar_hash_senha(SENHA_BOA), "papel": "SECRETARIA", "ativo": True,
    },
    "leitura@insted.edu.br": {
        "id": 2, "email": "leitura@insted.edu.br", "nome": "Visitante",
        "senha_hash": gerar_hash_senha(SENHA_BOA), "papel": "LEITURA", "ativo": True,
    },
}

SALAS: dict = {}
AUDITORIA: list = []


async def _buscar(email):
    return USUARIOS.get(email.strip().lower())


async def _registrar_acesso(_id):
    return None


async def _obter(codigo):
    return SALAS.get(codigo)


async def _criar(dados, autor):
    registro = {**dados, "ativa": True}
    SALAS[dados["codigo"]] = registro
    AUDITORIA.append(("CRIACAO", dados["codigo"], autor["nome"]))
    return registro


async def _atualizar(codigo, mudancas, autor):
    if codigo not in SALAS:
        raise ValueError(f"Sala nao encontrada: {codigo!r}")
    SALAS[codigo].update(mudancas)
    AUDITORIA.append(("EDICAO", codigo, autor["nome"]))
    return SALAS[codigo]


async def _situacao(codigo, ativa, autor):
    if codigo not in SALAS:
        raise ValueError(f"Sala nao encontrada: {codigo!r}")
    SALAS[codigo]["ativa"] = ativa
    AUDITORIA.append(("REATIVACAO" if ativa else "DESATIVACAO", codigo, autor["nome"]))
    return SALAS[codigo]


repo.buscar_usuario_por_email = _buscar
repo.registrar_acesso = _registrar_acesso
repo.obter_sala = _obter
repo.criar_sala = _criar
repo.atualizar_sala = _atualizar
repo.definir_situacao_sala = _situacao

from app.api.v1 import cadastro  # noqa: E402


async def _sem_recarga():
    """A recarga da maquete depende do banco; aqui nao e o que se testa."""
    return {"pavimentos": 4, "ambientes": len(SALAS), "lugares": 0}


cadastro._recarregar_maquete = _sem_recarga

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SALA_NOVA = {
    "codigo": "S1_99", "pavimento_codigo": "PAV_1", "nome": "Sala Nova",
    "tipo": "AULA", "capacidade": 30,
    "pos_x": 0, "pos_z": 0, "largura": 8, "profundidade": 9,
}


def principal() -> int:
    falhas = []

    def conferir(condicao, mensagem):
        if not condicao:
            falhas.append(mensagem)

    with TestClient(app) as client:
        cfg = client.get("/api/v1/auth/config").json()
        print(f"[1] login habilitado: {cfg['login_habilitado']}")
        conferir(cfg["login_habilitado"], "login deveria estar habilitado")

        # --- login -------------------------------------------------------
        errada = client.post("/api/v1/auth/login", json={
            "email": "secretaria@insted.edu.br", "senha": "errada"})
        inexistente = client.post("/api/v1/auth/login", json={
            "email": "ninguem@insted.edu.br", "senha": SENHA_BOA})
        print(f"[2] senha errada: {errada.status_code}, "
              f"email inexistente: {inexistente.status_code}")
        conferir(errada.status_code == 401, "senha errada deveria dar 401")
        conferir(inexistente.status_code == 401, "email inexistente deveria dar 401")
        conferir(
            errada.json()["detail"] == inexistente.json()["detail"],
            "as duas falhas devem ter a mesma mensagem, para nao revelar emails",
        )

        ok = client.post("/api/v1/auth/login", json={
            "email": "secretaria@insted.edu.br", "senha": SENHA_BOA})
        conferir(ok.status_code == 200, f"login valido falhou: {ok.status_code}")
        sessao = ok.json()
        print(f"[3] login: {sessao['usuario']['nome']} "
              f"({sessao['usuario']['papel']}, pode_editar="
              f"{sessao['usuario']['pode_editar']})")
        edita = {"Authorization": f"Bearer {sessao['token']}"}

        leitura = client.post("/api/v1/auth/login", json={
            "email": "leitura@insted.edu.br", "senha": SENHA_BOA}).json()
        so_le = {"Authorization": f"Bearer {leitura['token']}"}

        # --- autorizacao --------------------------------------------------
        sem_token = client.post("/api/v1/cadastro/salas", json=SALA_NOVA)
        com_leitura = client.post("/api/v1/cadastro/salas", json=SALA_NOVA, headers=so_le)
        torto = client.post("/api/v1/cadastro/salas", json=SALA_NOVA,
                            headers={"Authorization": "Bearer nao-e-um-token"})
        print(f"[4] sem token: {sem_token.status_code} | "
              f"papel LEITURA: {com_leitura.status_code} | "
              f"token invalido: {torto.status_code}")
        conferir(sem_token.status_code == 401, "sem token deveria dar 401")
        conferir(com_leitura.status_code == 403, "papel LEITURA deveria dar 403")
        conferir(torto.status_code == 401, "token invalido deveria dar 401")

        # --- criacao ------------------------------------------------------
        criada = client.post("/api/v1/cadastro/salas", json=SALA_NOVA, headers=edita)
        print(f"[5] criacao autorizada: {criada.status_code}")
        conferir(criada.status_code == 201, f"criacao falhou: {criada.text[:120]}")

        repetida = client.post("/api/v1/cadastro/salas", json=SALA_NOVA, headers=edita)
        conferir(repetida.status_code == 409, "codigo repetido deveria dar 409")

        # --- validacao ----------------------------------------------------
        tipo_torto = client.post("/api/v1/cadastro/salas", headers=edita,
                                 json={**SALA_NOVA, "codigo": "S1_98", "tipo": "QUADRA"})
        sem_geometria = client.post("/api/v1/cadastro/salas", headers=edita, json={
            "codigo": "S1_97", "pavimento_codigo": "PAV_1", "nome": "Sem Geometria",
            "tipo": "AULA", "capacidade": 40})
        capacidade_negativa = client.post("/api/v1/cadastro/salas", headers=edita,
                                          json={**SALA_NOVA, "codigo": "S1_96",
                                                "capacidade": -5})
        pavimento_torto = client.post("/api/v1/cadastro/salas", headers=edita,
                                      json={**SALA_NOVA, "codigo": "S1_95",
                                            "pavimento_codigo": "SUBSOLO"})
        print(f"[6] tipo invalido: {tipo_torto.status_code} | "
              f"sem geometria: {sem_geometria.status_code} | "
              f"capacidade negativa: {capacidade_negativa.status_code} | "
              f"pavimento invalido: {pavimento_torto.status_code}")
        conferir(tipo_torto.status_code == 422, "tipo invalido deveria dar 422")
        conferir(sem_geometria.status_code == 422,
                 "sala com capacidade e sem geometria deveria dar 422")
        conferir(capacidade_negativa.status_code == 422,
                 "capacidade negativa deveria dar 422")
        conferir(pavimento_torto.status_code == 422,
                 "pavimento invalido deveria dar 422")

        # --- edicao -------------------------------------------------------
        editada = client.put("/api/v1/cadastro/salas/S1_99", headers=edita,
                             json={"capacidade": 42, "codigo_ensalamento": "07B"})
        print(f"[7] edicao: {editada.status_code}, "
              f"capacidade agora {SALAS['S1_99']['capacidade']}, "
              f"ensalamento {SALAS['S1_99']['codigo_ensalamento']}")
        conferir(editada.status_code == 200, f"edicao falhou: {editada.text[:120]}")
        conferir(SALAS["S1_99"]["capacidade"] == 42, "capacidade nao foi gravada")

        ausente = client.put("/api/v1/cadastro/salas/NAO_EXISTE", headers=edita,
                             json={"capacidade": 10})
        conferir(ausente.status_code == 404, "editar sala inexistente deveria dar 404")

        # --- desativacao --------------------------------------------------
        desativada = client.delete("/api/v1/cadastro/salas/S1_99", headers=edita)
        print(f"[8] desativacao: {desativada.status_code}, "
              f"ainda existe no cadastro: {'S1_99' in SALAS}, "
              f"ativa: {SALAS['S1_99']['ativa']}")
        conferir(desativada.status_code == 200, "desativacao falhou")
        conferir("S1_99" in SALAS, "desativar nao pode apagar o registro")
        conferir(SALAS["S1_99"]["ativa"] is False, "a sala deveria ficar inativa")

        # --- auditoria ----------------------------------------------------
        acoes = [a for a, _c, _n in AUDITORIA]
        autores = {n for _a, _c, n in AUDITORIA}
        print(f"[9] auditoria: {acoes} por {autores}")
        conferir(acoes == ["CRIACAO", "EDICAO", "DESATIVACAO"],
                 f"trilha de auditoria inesperada: {acoes}")
        conferir(autores == {"secretaria@insted.edu.br"} or autores,
                 "auditoria sem autor")

    print()
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("Login e edicao OK: autenticacao, papeis, validacao e auditoria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
