"""Alimenta o motor de presenca com as passagens reais das catracas.

O espelho replicado diz quem esta no predio; o motor diz quem esta em qual
carteira. Este modulo liga os dois: le as passagens novas e as entrega ao motor
como se tivessem chegado pelo webhook, que e o mesmo caminho que o simulador
usava.

Sem ele, com o simulador desligado, o painel mostra as aulas em curso e nenhuma
pessoa sentada - foi o que aconteceu ao desligar a simulacao pela primeira vez.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.core import clock
from app.models.academico import EventoCatraca
from app.models.enums import DirecaoCatraca
from app.services.campus_state import estado

# Terminal do controle de acesso -> catraca da maquete.
#
# ATENCAO: e suposicao. Os cinco terminais existem e os cinco equipamentos da
# planta tambem, mas ninguem confirmou qual e qual. Isso afeta so de qual ponto
# a passagem parece vir no painel - a presenca em si independe. Quando a
# manutencao informar, e aqui que se corrige.
TERMINAL_PARA_CATRACA = {
    1: "CATRACA_PRINCIPAL_A",
    2: "CATRACA_PRINCIPAL_B",
    3: "CATRACA_PRINCIPAL_C",
    4: "CATRACA_SECRETARIA",
    5: "CATRACA_ESTACIONAMENTO",
}


def _catraca_de(terminal: Optional[int]) -> str:
    return TERMINAL_PARA_CATRACA.get(terminal or 0, "CATRACA_PRINCIPAL_A")


class AlimentadorCatracas:
    """Traz as passagens novas e as processa em ordem cronologica."""

    def __init__(self) -> None:
        self._marca: Optional[datetime] = None
        self.processadas = 0
        self.ultima_leitura: Optional[datetime] = None
        self.erro: Optional[str] = None

    def _marca_inicial(self) -> datetime:
        """De onde comecar na primeira execucao.

        Do inicio do dia, e nao do momento presente: quem entrou as 19h precisa
        aparecer sentado as 19h30, senao o painel sobe vazio e so ganha gente na
        proxima passagem - com as aulas em curso mostrando salas desertas.
        """
        agora = clock.agora()
        return agora.replace(hour=0, minute=0, second=0, microsecond=0)

    async def ciclo(self) -> dict:
        """Processa o que chegou desde a ultima vez. Devolve o resumo."""
        from app.data import catraca_repository as catracas

        if self._marca is None:
            self._marca = self._marca_inicial()

        passagens = await catracas.passagens_desde(self._marca)
        deltas: list = []
        for p in passagens:
            evento = EventoCatraca(
                ra=p["ra"],
                catraca_id=_catraca_de(p["terminal"]),
                direcao=DirecaoCatraca.ENTRADA if p["entrada"] else DirecaoCatraca.SAIDA,
                timestamp=p["momento"],
            )
            from app.services.presence_engine import motor

            resultado = await motor.processar_evento(evento)
            # Difundir cada passagem inundaria o painel na carga inicial, que
            # replica o dia inteiro. Os deltas sao acumulados e vao num pacote.
            deltas.extend(resultado.get("deltas") or [])
            self._marca = p["momento"]
            self.processadas += 1

        self.ultima_leitura = clock.agora()
        return {"passagens": len(passagens), "deltas": deltas}


alimentador = AlimentadorCatracas()
