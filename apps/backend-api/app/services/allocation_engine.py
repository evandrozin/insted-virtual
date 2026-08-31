"""Motor de alocacao de alunos nas carteiras da maquete 3D.

Regras:
* A alocacao acontece quando a aula entra na janela de chegada (RESERVADA/azul).
* A passagem na catraca promove a carteira para OCUPADA (cyan Insted).
* Se a turma excede a capacidade da sala, o excedente vira ALERT_SOBRELOTACAO
  em vez de estourar excecao - a diretoria precisa ver o problema, nao um erro.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from app.core import clock

from app.models.campus import CadeiraModel, SalaModel
from app.models.enums import StatusCadeira


class EngineAlocacaoInsted:
    """Opera sobre as carteiras de uma unica sala."""

    def __init__(self, cadeiras_sala: List[CadeiraModel]) -> None:
        self.cadeiras = cadeiras_sala

    # -- consultas ----------------------------------------------------------
    @property
    def livres(self) -> List[CadeiraModel]:
        return [c for c in self.cadeiras if c.status == StatusCadeira.LIVRE]

    def cadeira_do_aluno(self, aluno_ra: str) -> Optional[CadeiraModel]:
        for cadeira in self.cadeiras:
            if cadeira.aluno_ra == aluno_ra:
                return cadeira
        return None

    # -- operacoes ----------------------------------------------------------
    def alocar_turma(self, lista_alunos: List[Dict[str, str]]) -> Dict[str, CadeiraModel]:
        """Distribui os matriculados da turma nas carteiras disponiveis.

        Preenche da frente para o fundo (a ordem do seed ja e fileira/coluna),
        o que deixa a maquete visualmente coerente com uma sala real.
        """
        disponiveis = self.livres
        alocacoes: Dict[str, CadeiraModel] = {}
        excedentes: List[Dict[str, str]] = []

        for indice, aluno in enumerate(lista_alunos):
            if indice >= len(disponiveis):
                excedentes.append(aluno)
                continue

            cadeira = disponiveis[indice]
            cadeira.status = StatusCadeira.RESERVADA
            cadeira.aluno_ra = aluno["ra"]
            cadeira.aluno_nome = aluno["nome"]
            alocacoes[aluno["ra"]] = cadeira

        if excedentes:
            self._marcar_sobrelotacao(len(excedentes))

        return alocacoes

    def registrar_entrada_catraca(
        self, aluno_ra: str, momento: Optional[datetime] = None
    ) -> Optional[CadeiraModel]:
        """RESERVADA -> OCUPADA quando a catraca detecta a passagem do aluno."""
        cadeira = self.cadeira_do_aluno(aluno_ra)
        if cadeira is None:
            # Aluno sem reserva previa (troca de sala, ouvinte): pega a 1a livre.
            disponiveis = self.livres
            if not disponiveis:
                self._marcar_sobrelotacao(1)
                return None
            cadeira = disponiveis[0]
            cadeira.aluno_ra = aluno_ra

        cadeira.status = StatusCadeira.OCUPADA
        cadeira.ocupada_em = (momento or clock.agora()).isoformat()
        return cadeira

    def registrar_saida_catraca(self, aluno_ra: str) -> Optional[CadeiraModel]:
        """Aluno deixou o campus: a carteira volta a RESERVADA (aula em curso)."""
        cadeira = self.cadeira_do_aluno(aluno_ra)
        if cadeira is None:
            return None
        cadeira.status = StatusCadeira.RESERVADA
        cadeira.ocupada_em = None
        return cadeira

    def liberar_sala(self) -> int:
        """Fim da aula: devolve todas as carteiras para LIVRE."""
        liberadas = 0
        for cadeira in self.cadeiras:
            if cadeira.status != StatusCadeira.LIVRE:
                cadeira.liberar()
                liberadas += 1
        return liberadas

    # -- interno ------------------------------------------------------------
    def _marcar_sobrelotacao(self, quantidade: int) -> None:
        """Pinta as ultimas carteiras de vermelho para sinalizar excesso."""
        alvo = [c for c in reversed(self.cadeiras)][:quantidade]
        for cadeira in alvo:
            cadeira.status = StatusCadeira.ALERT_SOBRELOTACAO


def engine_da_sala(sala: SalaModel) -> EngineAlocacaoInsted:
    return EngineAlocacaoInsted(sala.cadeiras)
