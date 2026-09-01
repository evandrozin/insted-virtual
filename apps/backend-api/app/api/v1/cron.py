"""Reconciliacao disparada externamente.

Em serverless nao existe processo de fundo entre requisicoes: o loop que abre
e encerra aulas pela grade precisa ser chamado de fora. Este endpoint e o alvo
do Vercel Cron (ver vercel.json).

Em deploy com processo continuo o loop interno segue rodando e este endpoint
fica apenas como gatilho manual.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core import clock
from app.core.config import settings
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor
from app.services.realtime import difundir

router = APIRouter(tags=["infra"])


def _autorizar(authorization: str | None) -> None:
    """O Vercel Cron envia `Authorization: Bearer $CRON_SECRET`."""
    if not settings.CRON_SECRET:
        return  # sem segredo configurado, o endpoint fica aberto (dev)
    esperado = f"Bearer {settings.CRON_SECRET}"
    if authorization != esperado:
        raise HTTPException(401, "Chamada de cron nao autorizada.")


@router.post("/cron/reconciliar")
@router.get("/cron/reconciliar")
async def reconciliar(authorization: str | None = Header(default=None)) -> dict:
    _autorizar(authorization)

    deltas = await motor.reconciliar()
    dashboard = await servico_dashboard.snapshot()

    payload = {
        "tipo": "DASHBOARD_TICK",
        "servidor_em": clock.agora(),
        "dashboard": dashboard,
    }
    if deltas:
        payload["deltas"] = deltas
    await difundir(payload)

    return {
        "reconciliado_em": clock.agora().isoformat(),
        "aulas_ativas": len(estado.aulas_ativas),
        "deltas": len(deltas),
        "presentes_em_aula": dashboard.kpis.presentes_em_aula,
    }


@router.post("/cron/sync-jacad")
@router.get("/cron/sync-jacad")
async def sync_jacad(authorization: str | None = Header(default=None)) -> dict:
    _autorizar(authorization)
    resumo = motor.sincronizar_jacad()

    # Alem da memoria, atualiza a base local de pessoas: e contra ela que a
    # conferencia com a catraca e feita, entao ela nao pode envelhecer.
    from app.services.cadastro_pessoas import espelhar

    resumo["cadastro"] = await espelhar()
    await motor.reconciliar()
    return resumo
