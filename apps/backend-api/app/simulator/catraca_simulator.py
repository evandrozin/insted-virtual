"""Simulador de fluxo de catracas.

Serve para desenvolvimento e para a demonstracao a diretoria enquanto a
integracao fisica com a controladora de acesso nao esta publicada. Ele NAO
inventa presenca: parte da grade horaria real vinda do JACAD e sorteia, para
cada matriculado, um horario de chegada plausivel - inclusive faltas, atrasos
e evasao no meio da aula.

Desligue com SIMULADOR_ATIVO=false para operar apenas com catracas reais.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from app.core import clock
from app.core.config import settings
from app.models.academico import EventoCatraca
from app.models.enums import DirecaoCatraca
from app.services.campus_state import estado
from app.services.presence_engine import motor
from app.services.realtime import difundir
from app.services.store import obter_store

# Distribuicao de comportamento por aluno.
P_FALTA = 0.11          # nao aparece
P_ATRASO = 0.14         # chega depois da tolerancia
P_EVASAO = 0.05         # entra e sai antes do fim da aula

CATRACAS_ENTRADA = [
    ("CATRACA_PRINCIPAL_A", 0.30),
    ("CATRACA_PRINCIPAL_B", 0.26),
    ("CATRACA_PRINCIPAL_C", 0.22),
    ("CATRACA_ESTACIONAMENTO", 0.14),
    ("CATRACA_BLOCO_B", 0.08),
]


def _sortear_catraca(rng: random.Random) -> str:
    ponto = rng.random()
    acumulado = 0.0
    for catraca_id, peso in CATRACAS_ENTRADA:
        acumulado += peso
        if ponto <= acumulado:
            return catraca_id
    return CATRACAS_ENTRADA[0][0]


class SimuladorCatracas:
    def __init__(self, seed: int = 7) -> None:
        self._rng = random.Random(seed)
        # (momento, ra, catraca_id, direcao)
        self._agenda: List[Tuple[datetime, str, str, DirecaoCatraca]] = []
        self._aulas_planejadas: set[str] = set()
        self._rodando = False

    # ------------------------------------------------------------------
    def planejar_aulas_abertas(self, agora: datetime) -> None:
        """Para cada aula recem-aberta, sorteia as chegadas dos matriculados."""
        rng = self._rng

        for aula_id in list(estado.aulas_ativas):
            if aula_id in self._aulas_planejadas:
                continue
            self._aulas_planejadas.add(aula_id)

            aula = estado.aulas[aula_id]
            turma = estado.turmas.get(aula.turma_id)
            if turma is None:
                continue

            inicio = datetime.combine(agora.date(), aula.hora_inicio)
            fim = datetime.combine(agora.date(), aula.hora_fim)

            for ra in turma.alunos_ra:
                if ra not in estado.alunos:
                    continue

                dado = rng.random()
                if dado < P_FALTA:
                    continue  # ausente: nenhuma passagem sera gerada

                if dado < P_FALTA + P_ATRASO:
                    # Chega entre 16 e 45 min apos o inicio.
                    chegada = inicio + timedelta(minutes=rng.randint(16, 45))
                else:
                    # Chega entre 30 min antes e 12 min depois do inicio.
                    chegada = inicio + timedelta(minutes=rng.randint(-30, 12))

                if chegada >= fim:
                    continue

                catraca = _sortear_catraca(rng)
                self._agenda.append((chegada, ra, catraca, DirecaoCatraca.ENTRADA))

                if rng.random() < P_EVASAO:
                    minutos_restantes = int((fim - chegada).total_seconds() // 60)
                    if minutos_restantes > 25:
                        saida = chegada + timedelta(
                            minutes=rng.randint(15, minutos_restantes - 12)
                        )
                        self._agenda.append(
                            (saida, ra, catraca, DirecaoCatraca.SAIDA)
                        )

        self._agenda.sort(key=lambda item: item[0])

    # ------------------------------------------------------------------
    def _vencidos(self, agora: datetime) -> List[Tuple[datetime, str, str, DirecaoCatraca]]:
        prontos = [item for item in self._agenda if item[0] <= agora]
        if prontos:
            self._agenda = [item for item in self._agenda if item[0] > agora]
        return prontos

    async def rodar(self) -> None:
        """Loop principal: dispara as passagens agendadas conforme o relogio."""
        self._rodando = True
        intervalo = settings.SIMULADOR_INTERVALO_MS / 1000
        # A rajada acompanha a aceleracao do relogio: em tempo real bastam
        # poucas passagens por tick, mas a 30x a fila precisa vazar mais rapido.
        rajada = max(6, 4 * settings.SIMULADOR_FATOR_TEMPO)
        # Em tempo real espacamos as passagens para a maquete animar bonito;
        # acelerado, o espacamento sai do caminho.
        espacamento = 0.05 if settings.SIMULADOR_FATOR_TEMPO == 1 else 0.0

        while self._rodando:
            try:
                agora = clock.agora()
                self.planejar_aulas_abertas(agora)

                store = obter_store()
                for momento, ra, catraca, direcao in self._vencidos(agora)[:rajada]:
                    if direcao == DirecaoCatraca.ENTRADA and await store.esta_no_campus(ra):
                        continue  # ja esta no campus (aulas consecutivas)

                    resultado = await motor.processar_evento(
                        EventoCatraca(
                            ra=ra, catraca_id=catraca,
                            direcao=direcao, timestamp=agora,
                        )
                    )
                    await difundir(resultado)
                    if espacamento:
                        await asyncio.sleep(espacamento)

            except asyncio.CancelledError:
                raise
            except Exception as erro:  # o simulador nunca derruba a API
                print(f"[simulador] erro ignorado: {erro}")

            await asyncio.sleep(intervalo)

    def parar(self) -> None:
        self._rodando = False

    # ------------------------------------------------------------------
    async def semear_campus(self, agora: datetime, proporcao: float = 0.55) -> int:
        """Popula o campus no boot para a maquete nao abrir vazia."""
        self.planejar_aulas_abertas(agora)
        store = obter_store()
        disparados = 0

        atrasados = [item for item in self._agenda if item[0] <= agora]
        self._agenda = [item for item in self._agenda if item[0] > agora]

        for momento, ra, catraca, direcao in atrasados:
            if direcao == DirecaoCatraca.ENTRADA and self._rng.random() > proporcao:
                continue
            if direcao == DirecaoCatraca.ENTRADA and await store.esta_no_campus(ra):
                continue
            await motor.processar_evento(
                EventoCatraca(ra=ra, catraca_id=catraca,
                              direcao=direcao, timestamp=momento)
            )
            disparados += 1

        return disparados


simulador = SimuladorCatracas()
