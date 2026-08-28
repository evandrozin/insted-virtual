"""Endpoints de leitura: maquete 3D, dashboard da diretoria e drill-down."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core import clock
from app.models.dashboard import SnapshotDiretoria
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor

router = APIRouter(tags=["presenca"])


@router.get("/maquete")
async def obter_maquete() -> dict:
    """Topologia completa dos 4 pavimentos + status atual das carteiras."""
    return servico_dashboard.maquete()


@router.get("/dashboard", response_model=SnapshotDiretoria)
async def obter_dashboard() -> SnapshotDiretoria:
    """Carga unica do painel da diretoria."""
    return servico_dashboard.snapshot()


@router.get("/dashboard/eventos")
async def feed_eventos(limite: int = Query(30, ge=1, le=200)) -> dict:
    return {"eventos": list(estado.feed_eventos)[:limite]}


@router.get("/salas/{sala_id}")
async def detalhar_sala(sala_id: str) -> dict:
    """Chamada disparada ao clicar em uma sala/carteira na maquete."""
    sala = estado.sala(sala_id)
    if sala is None:
        raise HTTPException(404, f"Sala nao encontrada: {sala_id}")

    agora = clock.agora()
    with estado.lock:
        aula = next(
            (
                estado.aulas[aid] for aid in estado.aulas_ativas
                if estado.aulas[aid].sala_id == sala_id
                and estado.aulas[aid].em_andamento(agora)
            ),
            None,
        )
        registros = estado.presencas_da_aula(aula.id) if aula else []

        return {
            "sala": {
                "id": sala.id, "nome": sala.nome, "tipo": sala.tipo,
                "pavimento": sala.pavimento.value, "capacidade": sala.capacidade,
                "rack_id": sala.rack_id,
            },
            "aula": (
                {
                    "id": aula.id, "disciplina": aula.disciplina,
                    "professor": aula.professor, "turma_id": aula.turma_id,
                    "inicio": aula.hora_inicio.strftime("%H:%M"),
                    "fim": aula.hora_fim.strftime("%H:%M"),
                }
                if aula else None
            ),
            "chamada": sorted(
                (
                    {
                        "ra": r.aluno_ra,
                        "nome": r.aluno_nome,
                        "status": r.status.value,
                        "cadeira_id": r.cadeira_id,
                        "entrada_em": r.entrada_em.isoformat() if r.entrada_em else None,
                        "atraso_minutos": r.atraso_minutos,
                        "catraca_origem": r.catraca_origem,
                    }
                    for r in registros
                ),
                key=lambda item: (item["status"], item["nome"]),
            ),
        }


@router.get("/alunos/{ra}")
async def rastrear_aluno(ra: str) -> dict:
    """Onde o aluno esta agora e qual o historico do dia."""
    aluno = estado.alunos.get(ra)
    if aluno is None:
        raise HTTPException(404, f"RA nao encontrado no JACAD: {ra}")

    with estado.lock:
        registros = [r for (_a, r_ra), r in estado.presencas.items() if r_ra == ra]
        cadeira_id = estado.cadeira_por_aluno.get(ra)
        cadeira = estado.cadeiras.get(cadeira_id) if cadeira_id else None

        return {
            "aluno": aluno.model_dump(),
            "no_campus": ra in estado.alunos_no_campus,
            "localizacao": (
                {
                    "cadeira_id": cadeira.id,
                    "sala_id": cadeira.sala_id,
                    "sala_nome": estado.salas[cadeira.sala_id].nome,
                    "pavimento": cadeira.pavimento.value,
                    "posicao": cadeira.posicao.model_dump(),
                }
                if cadeira else None
            ),
            "aulas_do_dia": [
                {
                    "aula_id": r.aula_id, "disciplina": r.disciplina,
                    "sala_id": r.sala_id, "status": r.status.value,
                    "atraso_minutos": r.atraso_minutos,
                    "entrada_em": r.entrada_em.isoformat() if r.entrada_em else None,
                }
                for r in registros
            ],
        }


@router.get("/alunos")
async def buscar_alunos(
    q: str = Query(..., min_length=2, description="RA ou trecho do nome"),
    limite: int = Query(15, ge=1, le=50),
) -> dict:
    termo = q.strip().lower()
    with estado.lock:
        achados = [
            {
                "ra": a.ra, "nome": a.nome, "curso": a.curso,
                "turma_id": a.turma_id,
                "no_campus": a.ra in estado.alunos_no_campus,
            }
            for a in estado.alunos.values()
            if termo in a.ra or termo in a.nome.lower()
        ]
    return {"total": len(achados), "resultados": achados[:limite]}


@router.post("/sync/jacad")
async def sincronizar_jacad() -> dict:
    """Recarrega matriculas e grade horaria a partir do ERP."""
    resumo = motor.sincronizar_jacad()
    motor.reconciliar()
    return resumo


@router.get("/status")
async def status_operacional() -> dict:
    from app.services.realtime import manager

    return {
        "relogio": clock.agora().isoformat(),
        "modo_relogio": clock.descricao(),
        "ultima_sync_jacad": (
            estado.ultima_sync_jacad.isoformat() if estado.ultima_sync_jacad else None
        ),
        "alunos": len(estado.alunos),
        "aulas_cadastradas": len(estado.aulas),
        "aulas_ativas": len(estado.aulas_ativas),
        "cadeiras": estado.capacidade_total(),
        "paineis_conectados": manager.total,
    }
