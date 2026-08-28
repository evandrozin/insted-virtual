"""Modelos espaciais da maquete virtual: pavimento, sala e cadeira."""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Pavimento, StatusCadeira


class Posicao3D(BaseModel):
    x: float
    y: float
    z: float


class Dimensao3D(BaseModel):
    largura: float
    altura: float
    profundidade: float


class CadeiraModel(BaseModel):
    id: str = Field(..., description="ID Unico: SALA_101_CAD_01")
    sala_id: str = Field(..., description="ID da Sala/Departamento")
    pavimento: Pavimento
    posicao: Posicao3D
    fileira: int = 0
    coluna: int = 0
    status: StatusCadeira = StatusCadeira.LIVRE
    aluno_ra: Optional[str] = None
    aluno_nome: Optional[str] = None
    ocupada_em: Optional[str] = None

    def liberar(self) -> None:
        self.status = StatusCadeira.LIVRE
        self.aluno_ra = None
        self.aluno_nome = None
        self.ocupada_em = None


class SalaModel(BaseModel):
    id: str
    nome: str
    pavimento: Pavimento
    tipo: str = Field("AULA", description="AULA | LABORATORIO | MODULAR | ADMIN | CPD")
    capacidade: int
    posicao: Posicao3D = Field(..., description="Canto inferior-esquerdo no grid do pavimento")
    dimensao: Dimensao3D
    rack_id: Optional[str] = None
    cadeiras: List[CadeiraModel] = Field(default_factory=list)

    @property
    def ocupadas(self) -> int:
        return sum(1 for c in self.cadeiras if c.status == StatusCadeira.OCUPADA)

    @property
    def reservadas(self) -> int:
        return sum(1 for c in self.cadeiras if c.status == StatusCadeira.RESERVADA)


class PavimentoModel(BaseModel):
    id: Pavimento
    nome: str
    ordem: int
    altura_y: float
    descricao: str
    salas: List[SalaModel] = Field(default_factory=list)


class CatracaModel(BaseModel):
    id: str
    nome: str
    pavimento: Pavimento
    posicao: Posicao3D
    online: bool = True
    ultimo_evento_em: Optional[str] = None
    total_entradas_hoje: int = 0
    total_saidas_hoje: int = 0
