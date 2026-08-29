"""Login e edicao do cadastro de salas.

O painel de leitura continua aberto: um telao na diretoria nao pode exigir
sessao. O login existe para autorizar a *escrita* - criar, editar e desativar
sala - e cada alteracao fica registrada com autor na trilha de auditoria.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core import seguranca
from app.core.config import settings
from app.data import cadastro_repository as repo
from app.models.enums import Pavimento
from app.services.campus_state import estado

router = APIRouter(tags=["cadastro"])

PAPEIS_QUE_EDITAM = {"ADMIN", "SECRETARIA"}

TIPOS_VALIDOS = {
    "AULA", "LABORATORIO", "AUDITORIO", "TEATRO", "MULTIUSO", "ESTUDO",
    "BIBLIOTECA", "SECRETARIA", "ADMIN", "CPD", "CIRCULACAO",
    "COWORKING", "APOIO",
}
# Ambientes que recebem carteiras: so estes precisam de capacidade.
TIPOS_COM_ASSENTO = {"AULA", "LABORATORIO", "AUDITORIO", "TEATRO", "MULTIUSO", "ESTUDO"}


# ---------------------------------------------------------------------------
# Contratos
# ---------------------------------------------------------------------------

class Credenciais(BaseModel):
    email: str
    senha: str


class SalaEntrada(BaseModel):
    codigo: str = Field(..., min_length=2, max_length=40)
    pavimento_codigo: str
    nome: str = Field(..., min_length=2, max_length=120)
    tipo: str
    capacidade: int = Field(0, ge=0, le=1000)
    codigo_planta: Optional[str] = None
    codigo_ensalamento: Optional[str] = None
    rack_id: Optional[str] = None
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    largura: Optional[float] = Field(None, gt=0, le=200)
    profundidade: Optional[float] = Field(None, gt=0, le=200)
    observacao: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_conhecido(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in TIPOS_VALIDOS:
            raise ValueError(f"Tipo invalido. Use um de: {', '.join(sorted(TIPOS_VALIDOS))}")
        return v

    @field_validator("pavimento_codigo")
    @classmethod
    def _pavimento_conhecido(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in {p.value for p in Pavimento}:
            raise ValueError(f"Pavimento invalido: {v}")
        return v


class SalaEdicao(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    tipo: Optional[str] = None
    capacidade: Optional[int] = Field(None, ge=0, le=1000)
    codigo_planta: Optional[str] = None
    codigo_ensalamento: Optional[str] = None
    rack_id: Optional[str] = None
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    largura: Optional[float] = Field(None, gt=0, le=200)
    profundidade: Optional[float] = Field(None, gt=0, le=200)
    observacao: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def _tipo_conhecido(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in TIPOS_VALIDOS:
            raise ValueError(f"Tipo invalido. Use um de: {', '.join(sorted(TIPOS_VALIDOS))}")
        return v


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------

async def usuario_atual(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Faca login para continuar.")

    dados = seguranca.ler_token(authorization.split(" ", 1)[1].strip())
    if dados is None:
        raise HTTPException(401, "Sessao expirada ou invalida. Entre novamente.")

    return {
        "id": int(dados["sub"]),
        "email": dados.get("email", ""),
        "nome": dados.get("email", ""),
        "papel": dados.get("papel", "LEITURA"),
    }


async def requer_edicao(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["papel"] not in PAPEIS_QUE_EDITAM:
        raise HTTPException(
            403, "Seu perfil permite apenas leitura do cadastro."
        )
    return usuario


def _exige_banco() -> None:
    if not settings.DATABASE_URL:
        raise HTTPException(
            503,
            "Cadastro em banco nao configurado: defina DATABASE_URL para editar.",
        )


# ---------------------------------------------------------------------------
# Sessao
# ---------------------------------------------------------------------------

@router.get("/auth/config")
async def config_de_login() -> dict:
    """Diz ao painel se o login esta disponivel nesta instalacao.

    O login autoriza apenas a *escrita* no cadastro. A leitura do painel
    continua aberta - ver a nota sobre isso no README.
    """
    return {
        "login_habilitado": seguranca.login_habilitado() and bool(settings.DATABASE_URL),
    }


@router.post("/auth/login")
async def login(credenciais: Credenciais) -> dict:
    _exige_banco()
    if not seguranca.login_habilitado():
        raise HTTPException(503, "Login indisponivel: JWT_SECRET nao configurado.")

    usuario = await repo.buscar_usuario_por_email(credenciais.email)
    # Mesma resposta para email inexistente e senha errada: nao entrega quais
    # emails existem.
    if usuario is None or not seguranca.conferir_senha(
        credenciais.senha, usuario["senha_hash"]
    ):
        raise HTTPException(401, "E-mail ou senha incorretos.")

    await repo.registrar_acesso(usuario["id"])
    return {
        "token": seguranca.emitir_token(
            usuario["id"], usuario["email"], usuario["papel"]
        ),
        "usuario": {
            "nome": usuario["nome"],
            "email": usuario["email"],
            "papel": usuario["papel"],
            "pode_editar": usuario["papel"] in PAPEIS_QUE_EDITAM,
        },
        "expira_em_horas": settings.SESSAO_HORAS,
    }


@router.get("/auth/eu")
async def quem_sou_eu(usuario: dict = Depends(usuario_atual)) -> dict:
    return {**usuario, "pode_editar": usuario["papel"] in PAPEIS_QUE_EDITAM}


# ---------------------------------------------------------------------------
# Escrita no cadastro
# ---------------------------------------------------------------------------

async def _recarregar_maquete() -> dict:
    """Aplica o cadastro alterado na maquete e avisa os painels."""
    from app.data.sala_repository import carregar_topologia
    from app.services.realtime import difundir
    from app.services.dashboard_service import servico_dashboard

    pavimentos = await carregar_topologia(
        settings.DATABASE_URL, settings.PREDIO_CODIGO
    )
    estado.carregar_topologia(pavimentos)
    await difundir({"tipo": "MAQUETE_ATUALIZADA", "maquete": servico_dashboard.maquete()})
    return {
        "pavimentos": len(pavimentos),
        "ambientes": sum(len(p.salas) for p in pavimentos),
        "lugares": estado.capacidade_total(),
    }


def _conferir_geometria(tipo: str, capacidade: int, largura, profundidade) -> None:
    """Sem geometria a sala existe no cadastro mas some da maquete."""
    if tipo in TIPOS_COM_ASSENTO and capacidade > 0:
        if not largura or not profundidade:
            raise HTTPException(
                422,
                "Sala com capacidade precisa de largura e profundidade, "
                "senao nao ha como desenha-la na maquete.",
            )


@router.post("/cadastro/salas", status_code=201)
async def criar_sala(
    entrada: SalaEntrada, usuario: dict = Depends(requer_edicao)
) -> dict:
    _exige_banco()
    _conferir_geometria(
        entrada.tipo, entrada.capacidade, entrada.largura, entrada.profundidade
    )

    if await repo.obter_sala(entrada.codigo):
        raise HTTPException(409, f"Ja existe uma sala com o codigo {entrada.codigo}.")

    try:
        criada = await repo.criar_sala(entrada.model_dump(), usuario)
    except ValueError as erro:
        raise HTTPException(422, str(erro))

    return {"sala": _limpar(criada), "maquete": await _recarregar_maquete()}


@router.put("/cadastro/salas/{codigo}")
async def editar_sala(
    codigo: str, edicao: SalaEdicao, usuario: dict = Depends(requer_edicao)
) -> dict:
    _exige_banco()
    atual = await repo.obter_sala(codigo)
    if atual is None:
        raise HTTPException(404, f"Sala nao encontrada: {codigo}")

    mudancas = edicao.model_dump(exclude_unset=True)
    _conferir_geometria(
        mudancas.get("tipo", atual["tipo"]),
        mudancas.get("capacidade", atual["capacidade"]),
        mudancas.get("largura", atual["largura"]),
        mudancas.get("profundidade", atual["profundidade"]),
    )

    try:
        atualizada = await repo.atualizar_sala(codigo, mudancas, usuario)
    except ValueError as erro:
        raise HTTPException(422, str(erro))

    return {"sala": _limpar(atualizada), "maquete": await _recarregar_maquete()}


@router.delete("/cadastro/salas/{codigo}")
async def desativar_sala(codigo: str, usuario: dict = Depends(requer_edicao)) -> dict:
    """Desativa: a sala pode estar referenciada na grade horaria."""
    _exige_banco()
    try:
        sala = await repo.definir_situacao_sala(codigo, False, usuario)
    except ValueError as erro:
        raise HTTPException(404, str(erro))
    return {"sala": _limpar(sala), "maquete": await _recarregar_maquete()}


@router.post("/cadastro/salas/{codigo}/reativar")
async def reativar_sala(codigo: str, usuario: dict = Depends(requer_edicao)) -> dict:
    _exige_banco()
    try:
        sala = await repo.definir_situacao_sala(codigo, True, usuario)
    except ValueError as erro:
        raise HTTPException(404, str(erro))
    return {"sala": _limpar(sala), "maquete": await _recarregar_maquete()}


@router.get("/cadastro/salas/{codigo}/historico")
async def historico(codigo: str, usuario: dict = Depends(usuario_atual)) -> dict:
    _exige_banco()
    return {"codigo": codigo, "historico": await repo.historico_da_sala(codigo)}


def _limpar(registro: dict) -> dict:
    """Numeric vira float e datetime vira ISO, para caber no JSON."""
    saida = {}
    for chave, valor in registro.items():
        if hasattr(valor, "isoformat"):
            saida[chave] = valor.isoformat()
        elif hasattr(valor, "quantize"):
            saida[chave] = float(valor)
        else:
            saida[chave] = valor
    return saida
