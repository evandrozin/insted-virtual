"""Configuracao e cadastro de pessoas.

A tela de Configuracao mostra *situacao* das integracoes - URL, modo, ultimo
sync, teste de conexao - e nunca a chave. Os segredos continuam em variavel de
ambiente: quem tiver acesso ao painel ou ao banco nao leva o token do ERP.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.core import clock, parametros
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
            "modo": "simulado" if parametros.jacad_modo_mock() else "integrado",
            "base_url": parametros.jacad_base_url() or None,
            "chave_configurada": bool(settings.JACAD_TOKEN),
            "chave": _mascarar(settings.JACAD_TOKEN),
            "intervalo_sync_min": round(parametros.jacad_sync_interval_s() / 60),
            "ultima_sync": (
                estado.ultima_sync_jacad.isoformat()
                if estado.ultima_sync_jacad else None
            ),
            "alunos": len(estado.alunos),
            "turmas": len(estado.turmas),
            "aulas": len(estado.aulas),
        },
        "catracas": {
            "modo": "simulado" if parametros.simulador_ativo() else "integrado",
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
            "tolerancia_atraso_min": parametros.tolerancia_atraso_min(),
            "janela_chegada_min": parametros.janela_chegada_min(),
            "limiar_baixa_presenca": parametros.limiar_baixa_presenca(),
            "catraca_timeout_s": parametros.catraca_timeout_s(),
        },
    }


@router.post("/config/testar/jacad")
async def testar_jacad(usuario: dict = Depends(requer_edicao)) -> dict:
    """Bate no ERP e conta o que voltou, sem gravar nada."""
    from app.services.jacad_client import obter_client

    try:
        client = obter_client()
        alunos = client.listar_alunos()
        professores = client.listar_professores()
        turmas = client.listar_turmas()
        aulas = client.listar_grade_horaria()
    except Exception as erro:
        return {
            "ok": False,
            "modo": "simulado" if parametros.jacad_modo_mock() else "integrado",
            "erro": str(erro),
        }

    return {
        "ok": True,
        "modo": "simulado" if parametros.jacad_modo_mock() else "integrado",
        "alunos": len(alunos),
        "professores": len(professores),
        # Docente sem matricula nao entra no espelho: nao ha como reconhece-lo
        # na catraca. Contar aqui avisa antes de alguem estranhar o numero.
        "professores_sem_matricula": sum(
            1 for p in professores if not (p.matricula or "").strip()
        ),
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
    no_campus = sorted(await obter_store().alunos_no_campus())
    tipos = await pessoas.resumo_por_tipo(no_campus)

    reconhecidos = sum(t["no_campus"] for t in tipos)
    return {
        "tipos": tipos,
        "no_campus_agora": len(no_campus),
        # Passagem cujo identificador nao esta no cadastro: cracha de alguem
        # que o JACAD nao conhece, ou sync pendente.
        "sem_cadastro": len(no_campus) - reconhecidos,
    }


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
    """Traz alunos e professores do JACAD. Nao toca em quem foi criado a mao."""
    _exige_banco()
    from app.services.cadastro_pessoas import espelhar

    return await espelhar()


# ---------------------------------------------------------------------------
# Parametros operacionais
# ---------------------------------------------------------------------------

class ParametroEntrada(BaseModel):
    # Nulo devolve o parametro ao valor do ambiente.
    valor: Optional[str] = None


@router.get("/config/parametros")
async def listar_parametros() -> dict:
    """Catalogo com valor efetivo e de onde ele veio."""
    _exige_banco()
    from app.core import parametros as p

    itens = []
    for linha in await pessoas.listar_parametros():
        chave = linha["chave"]
        itens.append({
            **linha,
            "minimo": float(linha["minimo"]) if linha["minimo"] is not None else None,
            "maximo": float(linha["maximo"]) if linha["maximo"] is not None else None,
            "valor_efetivo": p.obter(chave),
            "origem": p.origem(chave),
            "exige_reinicio": chave in p.EXIGEM_REINICIO,
        })
    return {"parametros": itens}


@router.put("/config/parametros/{chave}")
async def gravar_parametro(
    chave: str, entrada: ParametroEntrada, usuario: dict = Depends(requer_edicao)
) -> dict:
    _exige_banco()
    from app.core import parametros as p

    catalogo = {i["chave"]: i for i in await pessoas.listar_parametros()}
    definicao = catalogo.get(chave.upper())
    if definicao is None:
        raise HTTPException(404, f"Parametro desconhecido: {chave}")

    valor = entrada.valor
    if valor is not None and valor.strip() == "":
        valor = None  # limpar devolve ao ambiente

    if valor is not None:
        tipo = definicao["tipo"]
        if tipo == "INTEIRO":
            try:
                numero = int(valor)
            except ValueError:
                raise HTTPException(422, f"{definicao['rotulo']} precisa ser um numero inteiro.")
            if definicao["minimo"] is not None and numero < definicao["minimo"]:
                raise HTTPException(
                    422, f"{definicao['rotulo']}: minimo {int(definicao['minimo'])}."
                )
            if definicao["maximo"] is not None and numero > definicao["maximo"]:
                raise HTTPException(
                    422, f"{definicao['rotulo']}: maximo {int(definicao['maximo'])}."
                )
            valor = str(numero)
        elif tipo == "BOOLEANO":
            valor = "true" if valor.strip().lower() in {"1", "true", "yes", "sim"} else "false"

    await pessoas.gravar_parametro(chave.upper(), valor, usuario.get("nome") or usuario["email"])
    carregados = await p.recarregar()

    return {
        "chave": chave.upper(),
        "valor_efetivo": p.obter(chave.upper()),
        "origem": p.origem(chave.upper()),
        "exige_reinicio": chave.upper() in p.EXIGEM_REINICIO,
        "parametros_no_banco": carregados,
    }


@router.get("/config/parametros/{chave}/historico")
async def historico_parametro(chave: str, usuario: dict = Depends(usuario_atual)) -> dict:
    _exige_banco()
    return {"chave": chave.upper(), "historico": await pessoas.historico_parametro(chave.upper())}
