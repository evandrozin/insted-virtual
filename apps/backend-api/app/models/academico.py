"""Modelos do dominio academico espelhando o ERP JACAD."""
from datetime import datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import DirecaoCatraca, StatusPresenca


class AlunoModel(BaseModel):
    ra: str = Field(..., description="Registro Academico (chave do JACAD e da catraca)")
    nome: str
    curso: str
    turma_id: str
    periodo: int = 1
    situacao: str = "ATIVO"
    foto_url: Optional[str] = None


class ProfessorModel(BaseModel):
    """Docente vindo do ERP.

    `matricula` e o mesmo identificador que o cracha apresenta na catraca - e
    o que permite conferir quem esta no campus contra a base do JACAD. Sem ele
    o professor existe so como nome na grade, e nao da para cruzar nada.
    """

    matricula: str = Field(..., description="Matricula funcional (chave do cruzamento)")
    nome: str
    email: Optional[str] = None
    setor: Optional[str] = Field(None, description="Departamento ou area")
    cargo: Optional[str] = None
    situacao: str = "ATIVO"


class TurmaModel(BaseModel):
    id: str
    nome: str
    # Nome curto da turma no ERP ("ADM 3P"). E o rotulo que cabe numa coluna de
    # listagem; o nome completo nao cabe.
    nome_reduzido: Optional[str] = None
    curso: str
    periodo: int
    alunos_ra: List[str] = Field(default_factory=list)


class AulaModel(BaseModel):
    """Uma ocorrencia da grade horaria: turma x disciplina x sala x janela de tempo."""

    id: str
    turma_id: str
    disciplina: str
    professor: str
    # Nulo quando o ERP nao informa a matricula do docente: a aula continua
    # valendo, mas esse professor nao entra no cruzamento com a catraca.
    professor_matricula: Optional[str] = None
    sala_id: str
    dia_semana: int = Field(..., ge=0, le=6, description="0=segunda ... 6=domingo")
    hora_inicio: time
    hora_fim: time

    def em_andamento(self, agora: datetime) -> bool:
        return (
            agora.weekday() == self.dia_semana
            and self.hora_inicio <= agora.time() <= self.hora_fim
        )

    def janela_de_chegada(self, agora: datetime) -> bool:
        """Aluno pode ser vinculado a aula ate 45min antes do inicio."""
        if agora.weekday() != self.dia_semana:
            return False
        minutos_ate_inicio = (
            self.hora_inicio.hour * 60 + self.hora_inicio.minute
        ) - (agora.hour * 60 + agora.minute)
        return -_duracao_min(self) <= minutos_ate_inicio <= 45


def _duracao_min(aula: "AulaModel") -> int:
    return (aula.hora_fim.hour * 60 + aula.hora_fim.minute) - (
        aula.hora_inicio.hour * 60 + aula.hora_inicio.minute
    )


class EventoCatraca(BaseModel):
    """Payload cru recebido do controlador de acesso."""

    ra: str
    catraca_id: str
    direcao: DirecaoCatraca = DirecaoCatraca.ENTRADA
    timestamp: Optional[datetime] = None


class RegistroPresenca(BaseModel):
    """Estado consolidado de um aluno em uma aula especifica."""

    aula_id: str
    aluno_ra: str
    aluno_nome: str
    turma_id: str
    sala_id: str
    disciplina: str
    status: StatusPresenca = StatusPresenca.AGUARDANDO
    cadeira_id: Optional[str] = None
    entrada_em: Optional[datetime] = None
    saida_em: Optional[datetime] = None
    atraso_minutos: int = 0
    catraca_origem: Optional[str] = None
