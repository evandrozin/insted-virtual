"""Enumeracoes de dominio do Motor de Ocupacao Insted."""
from enum import Enum


class StatusCadeira(str, Enum):
    LIVRE = "LIVRE"
    RESERVADA = "RESERVADA"
    OCUPADA = "OCUPADA"
    ALERT_SOBRELOTACAO = "ALERT_SOBRELOTACAO"


class StatusPresenca(str, Enum):
    """Ciclo de vida da presenca de um aluno em uma aula."""

    AGUARDANDO = "AGUARDANDO"      # Aula ainda nao comecou / aluno nao passou na catraca
    PRESENTE = "PRESENTE"          # Entrou dentro da tolerancia
    ATRASADO = "ATRASADO"          # Entrou depois da tolerancia, mas dentro da aula
    AUSENTE = "AUSENTE"            # Aula em andamento/encerrada sem registro de entrada
    EVADIDO = "EVADIDO"            # Registrou entrada e saiu do campus antes do fim da aula


class DirecaoCatraca(str, Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class Pavimento(str, Enum):
    TERREO = "TERREO"
    PAV_1 = "PAV_1"
    PAV_2 = "PAV_2"
    TERRACO = "TERRACO"


class SeveridadeAlerta(str, Enum):
    INFO = "INFO"
    ATENCAO = "ATENCAO"
    CRITICO = "CRITICO"


class TipoAlerta(str, Enum):
    SOBRELOTACAO = "SOBRELOTACAO"
    BAIXA_PRESENCA = "BAIXA_PRESENCA"
    SALA_VAZIA = "SALA_VAZIA"
    EVASAO_AULA = "EVASAO_AULA"
    PICO_ATRASO = "PICO_ATRASO"
    CATRACA_OFFLINE = "CATRACA_OFFLINE"
    RA_DESCONHECIDO = "RA_DESCONHECIDO"
