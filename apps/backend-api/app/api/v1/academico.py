"""Endpoints de consulta ao espelho local do ERP JACAD."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core import clock
from app.services.campus_state import estado
from app.services.store import obter_store

router = APIRouter(tags=["academico"])


@router.get("/academico/turmas")
async def listar_turmas() -> dict:
    return {
        "turmas": [
            {
                "id": t.id, "nome": t.nome, "curso": t.curso,
                "periodo": t.periodo, "matriculados": len(t.alunos_ra),
            }
            for t in sorted(estado.turmas.values(), key=lambda t: t.id)
        ]
    }


@router.get("/academico/grade")
async def listar_grade(
    dia: Optional[int] = Query(None, ge=0, le=6, description="0=segunda"),
    sala_id: Optional[str] = None,
    turma_id: Optional[str] = None,
) -> dict:
    dia_alvo = clock.agora().weekday() if dia is None else dia
    aulas = [
        a for a in estado.aulas.values()
        if a.dia_semana == dia_alvo
        and (sala_id is None or a.sala_id == sala_id)
        and (turma_id is None or a.turma_id == turma_id)
    ]
    aulas.sort(key=lambda a: (a.hora_inicio, a.sala_id))

    return {
        "dia_semana": dia_alvo,
        "aulas": [
            {
                "id": a.id, "turma_id": a.turma_id, "disciplina": a.disciplina,
                "professor": a.professor, "sala_id": a.sala_id,
                "sala_nome": estado.salas[a.sala_id].nome,
                "inicio": a.hora_inicio.strftime("%H:%M"),
                "fim": a.hora_fim.strftime("%H:%M"),
                "em_andamento": a.id in estado.aulas_ativas,
            }
            for a in aulas
        ],
    }


@router.get("/academico/turmas/{turma_id}")
async def detalhar_turma(turma_id: str) -> dict:
    turma = estado.turmas.get(turma_id)
    if turma is None:
        raise HTTPException(404, f"Turma nao encontrada: {turma_id}")

    no_campus = await obter_store().alunos_no_campus()
    return {
        "turma": {
            "id": turma.id, "nome": turma.nome,
            "curso": turma.curso, "periodo": turma.periodo,
        },
        "alunos": [
            {
                "ra": ra,
                "nome": estado.alunos[ra].nome,
                "no_campus": ra in no_campus,
            }
            for ra in turma.alunos_ra if ra in estado.alunos
        ],
    }
