"""Projecao local da maquete e espelho do ERP.

Esta classe NAO guarda mais estado compartilhado. O que vive aqui e o que
cada instancia consegue reconstruir sozinha, de forma identica as demais:

* Topologia (pavimentos, salas, cadeiras, catracas) - vem do seed.
* Espelho do JACAD (alunos, turmas, grade) - vem do sync periodico.
* Status das cadeiras - projecao local, mantida em dia pelos deltas que
  circulam no canal de tempo real e reconstruida no boot por `reidratar`.

Presencas, quem esta no campus, feed, alertas, serie e contadores ficam no
EstadoStore (memoria ou Redis).
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Dict, List, Optional, Set

from app.core import clock
from app.data.campus_seed import construir_catracas, construir_pavimentos
from app.models.academico import AlunoModel, AulaModel, TurmaModel
from app.models.campus import CadeiraModel, CatracaModel, PavimentoModel, SalaModel
from app.models.enums import Pavimento, StatusCadeira


class CampusState:
    def __init__(self) -> None:
        self.lock = threading.RLock()

        # --- Topologia fisica (deterministica) -----------------------------
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

        # --- Espelho do JACAD ----------------------------------------------
        self.alunos: Dict[str, AlunoModel] = {}
        self.turmas: Dict[str, TurmaModel] = {}
        self.aulas: Dict[str, AulaModel] = {}
        self.aulas_por_sala: Dict[str, List[AulaModel]] = {}
        self.aulas_por_turma: Dict[str, List[AulaModel]] = {}
        self.ultima_sync_jacad: Optional[datetime] = None

        # --- Cache local de aulas abertas (espelha o store) -----------------
        self.aulas_ativas: Set[str] = set()

        # --- Indice cadeira <-> aluno (projecao local) ----------------------
        self.cadeira_por_aluno: Dict[str, str] = {}

    # -- troca da topologia -------------------------------------------------
    def carregar_topologia(self, pavimentos: List[PavimentoModel]) -> None:
        """Substitui a planta vinda do seed pela do cadastro em banco."""
        with self.lock:
            self.pavimentos = pavimentos
            self.salas = {}
            self.cadeiras = {}
            for pav in pavimentos:
                for sala in pav.salas:
                    self.salas[sala.id] = sala
                    for cadeira in sala.cadeiras:
                        self.cadeiras[cadeira.id] = cadeira
            self.cadeira_por_aluno = {}

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

            validas = [a for a in aulas if a.sala_id in self.salas]
            self.aulas = {a.id: a for a in validas}

            self.aulas_por_sala = {}
            self.aulas_por_turma = {}
            for aula in validas:
                self.aulas_por_sala.setdefault(aula.sala_id, []).append(aula)
                self.aulas_por_turma.setdefault(aula.turma_id, []).append(aula)

            self.ultima_sync_jacad = clock.agora()

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

    # -- projecao das cadeiras ---------------------------------------------
    def aplicar_delta(self, delta: dict) -> None:
        """Aplica na projecao local um delta vindo do canal de tempo real.

        E o que mantem as instancias com a mesma leitura da maquete sem
        precisar reler o estado compartilhado a cada mensagem.
        """
        cadeira = self.cadeiras.get(delta.get("cadeira_id", ""))
        if cadeira is None:
            return
        with self.lock:
            cadeira.status = StatusCadeira(delta["status"])
            cadeira.aluno_ra = delta.get("aluno_ra")
            cadeira.aluno_nome = delta.get("aluno_nome")
            if cadeira.aluno_ra:
                self.cadeira_por_aluno[cadeira.aluno_ra] = cadeira.id

    def aplicar_deltas(self, deltas: List[dict]) -> None:
        for delta in deltas or []:
            self.aplicar_delta(delta)

    def limpar_sala(self, sala_id: str) -> None:
        sala = self.salas.get(sala_id)
        if sala is None:
            return
        with self.lock:
            for cadeira in sala.cadeiras:
                if cadeira.aluno_ra:
                    self.cadeira_por_aluno.pop(cadeira.aluno_ra, None)
                cadeira.liberar()

    def atualizar_catracas(self, estado_catracas: Dict[str, dict]) -> None:
        """Reflete no modelo local os contadores vindos do store."""
        with self.lock:
            for cid, info in estado_catracas.items():
                catraca = self.catracas.get(cid)
                if catraca is None:
                    continue
                catraca.online = bool(info.get("online", True))
                catraca.ultimo_evento_em = info.get("ultimo_evento_em")
                catraca.total_entradas_hoje = int(info.get("entradas", 0))
                catraca.total_saidas_hoje = int(info.get("saidas", 0))


# Instancia unica do processo.
estado = CampusState()
