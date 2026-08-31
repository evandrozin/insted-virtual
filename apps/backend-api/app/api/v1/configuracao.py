"""Configuracao e cadastro de pessoas.

A tela de Configuracao mostra *situacao* das integracoes - URL, modo, ultimo
sync, teste de conexao - e nunca a chave. Os segredos continuam em variavel de
ambiente: quem tiver acesso ao painel ou ao banco nao leva o token do ERP.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core import clock
from app.core.config import settings
from app.data import pessoa_repository as pessoas
from app.api.v1.cadastro import requer_edicao, usuario_atual
from app.services.campus_state import estado
from app.services.store import obter_store

router = APIRouter(tags=["configuracao"])


def _mascarar(valor: str) -> str:
    """Confirma que a chave existe sem revela-la."""
    if not valor:
        return ""
    return f"…{valor[-4:]}" if len(valor) > 4 else "…"


def _exige_banco() -> None:
    if not settings.DATABASE_URL:
        raise HTTPException(
            503, "Cadastro em banco nao configurado: defina DATABASE_URL."
        )


# ---------------------------------------------------------------------------
# Situacao das integracoes
# ---------------------------------------------------------------------------

@router.get("/config/integracoes")
async def integracoes() -> dict:
    """Situacao de cada integracao. Nenhum segredo sai daqui."""
    store = obter_store()
    catracas = await store.estado_catracas()
    contadores = await store.contadores()

    online = sum(
        1 for c in estado.catracas
        if catracas.get(c, {}).get("online", True)
    )

    return {
        "jacad": {
            "modo": "simulado" if settings.JACAD_MODO_MOCK else "integrado",
            "base_url": settings.JACAD_BASE_URL or None,
            "chave_configurada": bool(settings.JACAD_TOKEN),
            "chave": _mascarar(settings.JACAD_TOKEN),
            "intervalo_sync_min": round(settings.JACAD_SYNC_INTERVAL_S / 60),
            "ultima_sync": (
                estado.ultima_sync_jacad.isoformat()
                if estado.ultima_sync_jacad else None
            ),
            "alunos": len(estado.alunos),
            "turmas": len(estado.turmas),
            "aulas": len(estado.aulas),
        },
        "catracas": {
            "modo": "simulado" if settings.SIMULADOR_ATIVO else "integrado",
            "total": len(estado.catracas),
            "online": online,
            "entradas_hoje": contadores["entradas"],
            "saidas_hoje": contadores["saidas"],
            "webhook": "POST /api/v1/catracas/evento",
            "websocket": "/ws/catracas",
            "lote": "POST /api/v1/catracas/lote",
            "identificador": "O cracha usa o mesmo RA/matricula do JACAD.",
        },
        "data_hora": {
            "fuso": clock.fuso(),
            "agora": clock.agora().isoformat(),
            "modo": clock.descricao(),
            "em_demonstracao": clock.em_modo_demo(),
        },
        "infraestrutura": {
            "estado_compartilhado": store.nome,
            "banco_configurado": bool(settings.DATABASE_URL),
            "login_disponivel": bool(settings.JWT_SECRET),
            "loop_interno": settings.LOOP_INTERNO,
        },
        "regras": {
            "tolerancia_atraso_min": settings.TOLERANCIA_ATRASO_MIN,
            "janela_chegada_min": settings.JANELA_CHEGADA_ANTECIPADA_MIN,
            "limiar_baixa_presenca": settings.LIMIAR_BAIXA_PRESENCA,
            "catraca_timeout_s": settings.CATRACA_TIMEOUT_S,
        },
    }


@router.post("/config/testar/jacad")
async def testar_jacad(usuario: dict = Depends(requer_edicao)) -> dict:
    """Bate no ERP e conta o que voltou, sem gravar nada."""
    from app.services.jacad_client import obter_client

    try:
        client = obter_client()
        alunos = client.listar_alunos()
        turmas = client.listar_turmas()
        aulas = client.listar_grade_horaria()
    except Exception as erro:
        return {
            "ok": False,
            "modo": "simulado" if settings.JACAD_MODO_MOCK else "integrado",
            "erro": str(erro),
        }

    return {
        "ok": True,
        "modo": "simulado" if settings.JACAD_MODO_MOCK else "integrado",
        "alunos": len(alunos),
        "turmas": len(turmas),
        "aulas": len(aulas),
        "amostra": [
            {"identificador": a.ra, "nome": a.nome, "curso": a.curso}
            for a in alunos[:3]
        ],
    }


# ---------------------------------------------------------------------------
# Tipos de pessoa
# ---------------------------------------------------------------------------

class TipoEntrada(BaseModel):
    nome: str = Field(..., min_length=2, max_length=40)
    plural: str = Field(..., min_length=2, max_length=40)
    conta_presenca_em_aula: bool = False
    cor: Optional[str] = None
    ordem: int = Field(100, ge=0, le=999)
    ativo: bool = True

    @field_validator("cor")
    @classmethod
    def _cor_hex(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        v = v.strip()
        if not (v.startswith("#") and len(v) in (4, 7)):
            raise ValueError("Cor deve ser hexadecimal, como #00C9B7.")
        return v


@router.get("/pessoas/tipos")
async def listar_tipos(incluir_inativos: bool = False) -> dict:
    _exige_banco()
    return {"tipos": await pessoas.listar_tipos(incluir_inativos)}


@router.put("/pessoas/tipos/{codigo}")
async def salvar_tipo(
    codigo: str, entrada: TipoEntrada, usuario: dict = Depends(requer_edicao)
) -> dict:
    _exige_banco()
    return {"tipo": await pessoas.salvar_tipo(codigo, entrada.model_dump())}


# ---------------------------------------------------------------------------
# Pessoas
# ---------------------------------------------------------------------------

class PessoaEntrada(BaseModel):
    identificador: str = Field(..., min_length=1, max_length=40)
    nome: str = Field(..., min_length=2, max_length=120)
    tipo_codigo: str
    email: Optional[str] = None
    curso: Optional[str] = None
    turma_id: Optional[str] = None
    periodo: Optional[int] = Field(None, ge=1, le=20)
    setor: Optional[str] = None
    cargo: Optional[str] = None
    situacao: str = "ATIVO"
    observacao: Optional[str] = None


@router.get("/pessoas")
async def listar(
    tipo: Optional[str] = None,
    q: Optional[str] = Query(None, description="Nome, identificador, turma ou setor"),
    limite: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    _exige_banco()
    resultado = await pessoas.listar_pessoas(tipo, q, limite, offset)

    # Quem esta no predio agora, cruzando com o conjunto do estado partilhado.
    no_campus = await obter_store().alunos_no_campus()
    for p in resultado["pessoas"]:
        p["no_campus"] = p["identificador"] in no_campus

    resultado["no_campus_agora"] = len(no_campus)
    return resultado


@router.get("/pessoas/resumo")
async def resumo() -> dict:
    """Quantos de cada tipo, e quantos estao no predio agora."""
    _exige_banco()
    no_campus = await obter_store().alunos_no_campus()
    tipos = await pessoas.resumo_por_tipo()

    presentes_por_tipo = {}
    if no_campus:
        detalhe = await pessoas.listar_pessoas(limite=1000)
        for p in detalhe["pessoas"]:
            if p["identificador"] in no_campus:
                presentes_por_tipo[p["tipo"]] = presentes_por_tipo.get(p["tipo"], 0) + 1

    for t in tipos:
        t["no_campus"] = presentes_por_tipo.get(t["codigo"], 0)

    return {"tipos": tipos, "no_campus_agora": len(no_campus)}


@router.put("/pessoas/{identificador}")
async def salvar(
    identificador: str,
    entrada: PessoaEntrada,
    usuario: dict = Depends(requer_edicao),
) -> dict:
    _exige_banco()
    dados = entrada.model_dump()
    dados["identificador"] = identificador
    dados["origem"] = "MANUAL"
    return {"pessoa": await pessoas.salvar_pessoa(dados)}


@router.delete("/pessoas/{identificador}")
async def desativar(
    identificador: str, usuario: dict = Depends(requer_edicao)
) -> dict:
    _exige_banco()
    pessoa = await pessoas.definir_situacao(identificador, False)
    if pessoa is None:
        raise HTTPException(404, f"Pessoa nao encontrada: {identificador}")
    return {"pessoa": {"identificador": identificador, "ativo": False}}


@router.post("/pessoas/sincronizar")
async def sincronizar(usuario: dict = Depends(requer_edicao)) -> dict:
    """Traz do JACAD para o cadastro local. Nao toca em quem foi criado a mao."""
    _exige_banco()
    from app.services.jacad_client import obter_client

    alunos = [a.model_dump() for a in obter_client().listar_alunos()]
    resumo = await pessoas.sincronizar_do_jacad(alunos)
    resumo["sincronizado_em"] = clock.agora().isoformat()
    return resumo
