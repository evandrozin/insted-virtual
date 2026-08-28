"""Canal WebSocket consumido pela maquete 3D e pelo painel da diretoria."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import clock
from app.models.academico import EventoCatraca
from app.services.campus_state import estado
from app.services.dashboard_service import servico_dashboard
from app.services.presence_engine import motor
from app.services.realtime import difundir, manager
from app.services.store import obter_store

router = APIRouter(tags=["tempo-real"])


@router.websocket("/ws/campus")
async def websocket_campus(websocket: WebSocket) -> None:
    """No handshake envia a carga completa; depois recebe apenas deltas."""
    await manager.connect(websocket)
    try:
        await manager.send_personal(
            websocket,
            {
                "tipo": "SNAPSHOT_INICIAL",
                "servidor_em": clock.agora(),
                "modo_relogio": clock.descricao(),
                "maquete": servico_dashboard.maquete(),
                "dashboard": await servico_dashboard.snapshot(),
                "eventos": await obter_store().feed(30),
            },
        )

        while True:
            # O painel pode pedir um refresh completo a qualquer momento.
            mensagem = await websocket.receive_json()
            if mensagem.get("acao") == "REFRESH":
                await manager.send_personal(
                    websocket,
                    {
                        "tipo": "DASHBOARD_TICK",
                        "dashboard": await servico_dashboard.snapshot(),
                    },
                )
            elif mensagem.get("acao") == "PING":
                await manager.send_personal(websocket, {"tipo": "PONG"})

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


@router.websocket("/ws/catracas")
async def websocket_catracas(websocket: WebSocket) -> None:
    """Canal de ingestao usado pela controladora de acesso.

    Recebe:  {"event": "CATRACA_PASSAGE", "ra": "20260199",
              "catraca_id": "CATRACA_PRINCIPAL_A", "direcao": "ENTRADA"}
    O pacote consolidado e transmitido a todos os paineis conectados.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            try:
                evento = EventoCatraca(
                    ra=str(data["ra"]),
                    catraca_id=data.get("catraca_id", "CATRACA_PRINCIPAL_A"),
                    direcao=data.get("direcao", "ENTRADA"),
                    timestamp=clock.agora(),
                )
            except (KeyError, ValueError) as erro:
                await manager.send_personal(
                    websocket, {"tipo": "ERRO", "detalhe": str(erro)}
                )
                continue

            await difundir(await motor.processar_evento(evento))

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
