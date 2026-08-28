"""Operacoes manuais sobre o motor de alocacao (uso da coordenacao)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.allocation_engine import EngineAlocacaoInsted
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.realtime import difundir
from app.services.store import obter_store

router = APIRouter(tags=["alocacao"])


class RealocacaoRequest(BaseModel):
    turma_id: str
    sala_destino_id: str


@router.get("/alocacao/salas/{sala_id}/mapa")
async def mapa_de_cadeiras(sala_id: str) -> dict:
    sala = estado.sala(sala_id)
    if sala is None:
        raise HTTPException(404, f"Sala nao encontrada: {sala_id}")

    return {
        "sala_id": sala.id,
        "nome": sala.nome,
        "capacidade": sala.capacidade,
        "ocupadas": sala.ocupadas,
        "reservadas": sala.reservadas,
        "cadeiras": [
            {
                "id": c.id, "fileira": c.fileira, "coluna": c.coluna,
                "status": c.status.value, "aluno_ra": c.aluno_ra,
                "aluno_nome": c.aluno_nome, "posicao": c.posicao.model_dump(),
            }
            for c in sala.cadeiras
        ],
    }


@router.post("/alocacao/realocar")
async def realocar_turma(payload: RealocacaoRequest) -> dict:
    """Move a turma para outra sala (ex.: resolver uma sobrelotacao)."""
    turma = estado.turmas.get(payload.turma_id)
    destino = estado.sala(payload.sala_destino_id)
    if turma is None:
        raise HTTPException(404, f"Turma nao encontrada: {payload.turma_id}")
    if destino is None:
        raise HTTPException(404, f"Sala nao encontrada: {payload.sala_destino_id}")

    store = obter_store()
    aula = next(
        (
            estado.aulas[aid] for aid in list(estado.aulas_ativas)
            if aid in estado.aulas and estado.aulas[aid].turma_id == payload.turma_id
        ),
        None,
    )
    if aula is None:
        raise HTTPException(409, "A turma nao possui aula ativa no momento.")

    origem = estado.sala(aula.sala_id)
    if origem is not None:
        estado.limpar_sala(origem.id)

    matriculados = [
        {"ra": ra, "nome": estado.alunos[ra].nome}
        for ra in turma.alunos_ra if ra in estado.alunos
    ]
    estado.limpar_sala(destino.id)
    alocacoes = EngineAlocacaoInsted(destino.cadeiras).alocar_turma(matriculados)

    aula.sala_id = destino.id
    for registro in await store.presencas_da_aula(aula.id):
        registro.sala_id = destino.id
        cadeira = alocacoes.get(registro.aluno_ra)
        registro.cadeira_id = cadeira.id if cadeira else None
        if cadeira:
            estado.cadeira_por_aluno[registro.aluno_ra] = cadeira.id
        await store.atualizar_presenca(registro)

    await difundir(
        {
            "tipo": "REALOCACAO",
            "turma_id": payload.turma_id,
            "sala_origem": origem.id if origem else None,
            "sala_destino": destino.id,
            "maquete": servico_dashboard.maquete(),
        }
    )

    return {
        "turma_id": payload.turma_id,
        "sala_origem": origem.id if origem else None,
        "sala_destino": destino.id,
        "alocados": len(alocacoes),
        "sem_carteira": len(matriculados) - len(alocacoes),
    }


@router.get("/alocacao/salas-disponiveis")
async def salas_disponiveis(minimo: int = 0) -> dict:
    """Salas letivas sem aula ativa, ordenadas por capacidade."""
    em_uso = {
        estado.aulas[aid].sala_id
        for aid in list(estado.aulas_ativas) if aid in estado.aulas
    }
    livres = [
        {
            "id": s.id, "nome": s.nome, "pavimento": s.pavimento.value,
            "tipo": s.tipo, "capacidade": s.capacidade,
        }
        for s in estado.salas.values()
        if s.id not in em_uso and s.capacidade >= minimo and s.capacidade > 0
    ]
    livres.sort(key=lambda s: s["capacidade"], reverse=True)
    return {"salas": livres}
