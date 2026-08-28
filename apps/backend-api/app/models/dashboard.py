"""Modelos de leitura consumidos pelo painel da Diretoria."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Pavimento, SeveridadeAlerta, TipoAlerta


class Alerta(BaseModel):
    id: str
    tipo: TipoAlerta
    severidade: SeveridadeAlerta
    titulo: str
    detalhe: str
    sala_id: Optional[str] = None
    pavimento: Optional[Pavimento] = None
    criado_em: datetime


class OcupacaoSala(BaseModel):
    sala_id: str
    sala_nome: str
    pavimento: Pavimento
    capacidade: int
    esperados: int = 0
    presentes: int = 0
    atrasados: int = 0
    ausentes: int = 0
    evadidos: int = 0
    disciplina: Optional[str] = None
    professor: Optional[str] = None
    turma_id: Optional[str] = None
    aula_id: Optional[str] = None
    inicio: Optional[str] = None
    fim: Optional[str] = None
    em_aula: bool = False

    @property
    def taxa_presenca(self) -> float:
        if not self.esperados:
            return 0.0
        return round(100 * (self.presentes + self.atrasados) / self.esperados, 1)

    @property
    def taxa_ocupacao(self) -> float:
        if not self.capacidade:
            return 0.0
        return round(100 * (self.presentes + self.atrasados) / self.capacidade, 1)


class OcupacaoPavimento(BaseModel):
    pavimento: Pavimento
    nome: str
    capacidade: int
    presentes: int
    esperados: int
    salas_em_aula: int
    taxa_presenca: float


class KPIsDiretoria(BaseModel):
    atualizado_em: datetime
    alunos_no_campus: int
    alunos_esperados_agora: int
    presentes_em_aula: int
    taxa_presenca_geral: float
    taxa_presenca_variacao: float = Field(
        0.0, description="Pontos percentuais vs. mesma hora do dia anterior"
    )
    atrasados: int
    ausentes: int
    evasao_em_aula: int
    salas_em_aula: int
    salas_ociosas: int
    capacidade_total: int
    taxa_ocupacao_campus: float
    catracas_online: int
    catracas_total: int
    fluxo_ultima_hora: int


class SerieTemporalPonto(BaseModel):
    hora: str
    presentes: int
    esperados: int
    taxa: float


class SnapshotDiretoria(BaseModel):
    """Carga completa do dashboard, entregue no handshake do WebSocket."""

    kpis: KPIsDiretoria
    ocupacao_salas: List[OcupacaoSala]
    ocupacao_pavimentos: List[OcupacaoPavimento]
    serie_presenca: List[SerieTemporalPonto]
    alertas: List[Alerta]
    ranking_cursos: List[Dict[str, object]] = Field(default_factory=list)
