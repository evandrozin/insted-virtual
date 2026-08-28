"""Estado central em memoria da maquete e da operacao academica.

Toda leitura do dashboard e toda escrita vinda das catracas passam por aqui.
Os indices sao construidos uma unica vez no boot para que o caminho quente
(evento de catraca -> atualizacao de cadeira -> broadcast) seja O(1).
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional, Set

from app.core.config import settings
from app.data.campus_seed import construir_catracas, construir_pavimentos
from app.models.academico import AlunoModel, AulaModel, RegistroPresenca, TurmaModel
from app.models.campus import CadeiraModel, CatracaModel, PavimentoModel, SalaModel
from app.models.dashboard import Alerta
from app.models.enums import Pavimento


class CampusState:
    """Fonte unica de verdade do processo. Protegida por lock reentrante."""

    def __init__(self) -> None:
        self.lock = threading.RLock()

        # --- Topologia fisica ---------------------------------------------
        self.pavimentos: List[PavimentoModel] = construir_pavimentos()
        self.catracas: Dict[str, CatracaModel] = {
            c.id: c for c in construir_catracas()
        }

        self.salas: Dict[str, SalaModel] = {}
        self.cadeiras: Dict[str, CadeiraModel] = {}
        for pav in self.pavimentos:
            for sala in pav.salas:
                self.salas[sala.id] = sala
                for cadeira in sala.cadeiras:
                    self.cadeiras[cadeira.id] = cadeira

        # --- Dominio academico (JACAD) -------------------------------------
        self.alunos: Dict[str, AlunoModel] = {}
        self.turmas: Dict[str, TurmaModel] = {}
        self.aulas: Dict[str, AulaModel] = {}
        self.aulas_por_sala: Dict[str, List[AulaModel]] = {}
        self.aulas_por_turma: Dict[str, List[AulaModel]] = {}
        self.ultima_sync_jacad: Optional[datetime] = None

        # --- Operacao em tempo real ----------------------------------------
        # chave: (aula_id, ra)
        self.presencas: Dict[tuple, RegistroPresenca] = {}
        self.aulas_ativas: Set[str] = set()
        self.alunos_no_campus: Set[str] = set()
        self.cadeira_por_aluno: Dict[str, str] = {}

        self.feed_eventos: Deque[dict] = deque(maxlen=settings.MAX_EVENTOS_FEED)
        self.alertas: Deque[Alerta] = deque(maxlen=settings.MAX_ALERTAS)
        self.alertas_emitidos: Set[str] = set()

        # Historico intradiario para o grafico da diretoria: hora -> metricas.
        self.serie_presenca: Dict[str, dict] = {}
        # Baseline do dia anterior por hora, para a variacao percentual.
        self.baseline_ontem: Dict[str, float] = {}

        self.total_entradas: int = 0
        self.total_saidas: int = 0

    # -- carga do ERP -------------------------------------------------------
    def carregar_academico(
        self,
        alunos: List[AlunoModel],
        turmas: List[TurmaModel],
        aulas: List[AulaModel],
    ) -> None:
        with self.lock:
            self.alunos = {a.ra: a for a in alunos}
            self.turmas = {t.id: t for t in turmas}

            # Ignora aulas apontando para salas inexistentes na maquete.
            validas = [a for a in aulas if a.sala_id in self.salas]
            self.aulas = {a.id: a for a in validas}

            self.aulas_por_sala = {}
            self.aulas_por_turma = {}
            for aula in validas:
                self.aulas_por_sala.setdefault(aula.sala_id, []).append(aula)
                self.aulas_por_turma.setdefault(aula.turma_id, []).append(aula)

            self.ultima_sync_jacad = datetime.now()

    # -- consultas ----------------------------------------------------------
    def sala(self, sala_id: str) -> Optional[SalaModel]:
        return self.salas.get(sala_id)

    def pavimento_da_sala(self, sala_id: str) -> Optional[Pavimento]:
        sala = self.salas.get(sala_id)
        return sala.pavimento if sala else None

    def capacidade_total(self) -> int:
        return len(self.cadeiras)

    def aulas_do_aluno(self, ra: str) -> List[AulaModel]:
        aluno = self.alunos.get(ra)
        if not aluno:
            return []
        return self.aulas_por_turma.get(aluno.turma_id, [])

    def presencas_da_aula(self, aula_id: str) -> List[RegistroPresenca]:
        return [r for (aid, _ra), r in self.presencas.items() if aid == aula_id]

    # -- feed ---------------------------------------------------------------
    def registrar_evento_feed(self, evento: dict) -> None:
        self.feed_eventos.appendleft(evento)

    def registrar_alerta(self, alerta: Alerta, chave_dedupe: Optional[str] = None) -> bool:
        """Adiciona o alerta; devolve False se ja havia sido emitido nesta janela."""
        chave = chave_dedupe or alerta.id
        if chave in self.alertas_emitidos:
            return False
        self.alertas_emitidos.add(chave)
        self.alertas.appendleft(alerta)
        return True

    def limpar_dedupe_alertas(self, prefixos: List[str]) -> None:
        """Libera chaves de alerta quando a condicao que as gerou deixa de existir."""
        for chave in list(self.alertas_emitidos):
            if any(chave.startswith(p) for p in prefixos):
                self.alertas_emitidos.discard(chave)


# Instancia unica do processo.
estado = CampusState()
