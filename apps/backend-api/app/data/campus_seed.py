"""Topologia real do campus Insted, extraida das plantas Sigma (rev. 05/2025).

Fonte por pavimento:
    TERREO  -> 4_6.pdf (Terreo)          PAV_1 -> 1_6.pdf (Primeiro Pavimento)
    PAV_2   -> 2_6.pdf (Segundo Pavimento)  TERRACO -> 3_6.pdf (Terraco)

Extraido da prancha (dado real): pavimento, codigo da sala, capacidade e
posicao relativa do ambiente. As pranchas estao em escala 1/125; as
coordenadas foram convertidas para metros e centradas na origem, com X para
leste e Z para o sul, reproduzindo a implantacao em L do predio.

Derivado: largura/profundidade de cada sala, obtidas por particao do grid de
rotulos e conferidas contra as areas impressas quando a prancha as traz.

O codigo do ensalamento (01A/01B/01C ...) e mantido a parte, em
CODIGO_ENSALAMENTO, porque a planta numera SALA 01..20 por pavimento e a
Secretaria usa o sufixo A/B/C. Preencher conforme a lista da Secretaria.
"""
from typing import Dict, List, Optional, Tuple

from app.models.campus import (
    CadeiraModel,
    CatracaModel,
    Dimensao3D,
    PavimentoModel,
    Posicao3D,
    SalaModel,
)
from app.models.enums import Pavimento

ALTURA_PAVIMENTO = 4.2

PAVIMENTOS_META: List[Tuple[Pavimento, str, int, str]] = [
    (Pavimento.TERREO, "Terreo", 0,
     "Secretaria, biblioteca, teatro (auditorio 314), 2 laboratorios e salas 01-09"),
    (Pavimento.PAV_1, "1o Pavimento", 1,
     "16 salas de aula, laboratorio de informatica, 2 auditorios e multiuso"),
    (Pavimento.PAV_2, "2o Pavimento", 2,
     "20 salas de aula, 2 laboratorios, sala de estudos, diretoria e CPD"),
    (Pavimento.TERRACO, "3o Pavimento / Terraco", 3,
     "Administrativo: diretoria, coordenacao, professores, coworking e cantinas"),
]

# (id, codigo na planta, nome, tipo, x, z, largura, profundidade, capacidade)
SALAS_POR_PAVIMENTO: Dict[Pavimento, List[tuple]] = {
    Pavimento.TERREO: [
        ("T_AUDITORIO_314_LUGARES", "AUDITÓRIO (314 LUGARES)", "Auditório (314 Lugares)", "TEATRO",
         -32.34, -19.84, 12.17, 13.23, 314),
        ("T_BIBLIOTECA", "BIBLIOTECA", "Biblioteca", "BIBLIOTECA",
         -32.25, 27.46, 12.02, 11.09, 0),
        ("T_LOBBY_AUDITORIO", "LOBBY AUDITÓRIO", "Lobby Auditório", "CIRCULACAO",
         -26.91, -4.69, 11.0, 11.0, 0),
        ("T_RECEPCAO_SECRETARIA", "RECEPÇÃO SECRETARIA", "Recepção Secretaria", "SECRETARIA",
         -31.59, 15.85, 7.79, 7.78, 0),
        ("ST_01", "SALA 01", "Sala 01 (Terreo)", "AULA",
         -19.0, 15.85, 9.18, 9.14, 40),
        ("ST_02", "SALA 02", "Sala 02 (Terreo)", "AULA",
         -11.13, 21.14, 6.52, 8.13, 49),
        ("ST_03", "SALA 03", "Sala 03 (Terreo)", "AULA",
         -5.71, 20.96, 6.51, 8.14, 49),
        ("ST_04", "SALA 04", "Sala 04 (Terreo)", "AULA",
         1.19, 17.69, 4.3, 11.36, 48),
        ("ST_05", "SALA 05 - LAB. INFORMÁTICA", "Sala 05 - Lab. Informática (Terreo)", "LABORATORIO",
         4.85, 13.48, 5.14, 16.68, 60),
        ("ST_06", "SALA 06 - LAB. INFORMÁTICA", "Sala 06 - Lab. Informática (Terreo)", "LABORATORIO",
         4.85, 27.47, 5.14, 16.68, 60),
        ("ST_07", "SALA 07", "Sala 07 (Terreo)", "AULA",
         1.15, 29.09, 4.3, 11.36, 48),
        ("ST_08", "SALA 08", "Sala 08 (Terreo)", "AULA",
         -5.61, 27.57, 6.29, 8.43, 49),
        ("ST_09", "SALA 09", "Sala 09 (Terreo)", "AULA",
         -10.66, 27.73, 6.3, 8.41, 49),
    ],
    Pavimento.PAV_1: [
        ("1_AUDITORIO_01_93_LUGARE", "AUDITÓRIO 01 - 93 LUGARES", "Auditório 01 - 93 Lugares", "AUDITORIO",
         21.66, 31.91, 13.23, 12.17, 93),
        ("1_AUDITORIO_02_91_LUGARE", "AUDITÓRIO 02 - 91 LUGARES", "Auditório 02 - 91 Lugares", "AUDITORIO",
         2.29, 32.79, 13.23, 13.23, 91),
        ("1_MULTIUSO", "MULTIUSO", "Multiuso", "MULTIUSO",
         -18.64, 19.9, 12.17, 6.99, 30),
        ("S1_01", "SALA 01", "Sala 01 (1o Pav)", "AULA",
         -19.8, -44.84, 8.53, 9.39, 40),
        ("S1_02", "SALA 02", "Sala 02 (1o Pav)", "AULA",
         -19.87, -34.39, 8.47, 8.89, 60),
        ("S1_03", "SALA 03", "Sala 03 (1o Pav)", "AULA",
         -19.9, -24.73, 8.42, 8.89, 60),
        ("S1_04", "SALA 04", "Sala 04 (1o Pav)", "AULA",
         -19.82, -14.97, 8.27, 9.04, 60),
        ("S1_05", "SALA 05", "Sala 05 (1o Pav)", "AULA",
         -19.84, 12.3, 8.62, 6.99, 35),
        ("S1_06", "SALA 06", "Sala 06 (1o Pav)", "AULA",
         -5.05, 10.43, 7.93, 12.17, 49),
        ("S1_07", "SALA 07", "Sala 07 (1o Pav)", "AULA",
         3.57, 9.94, 7.93, 13.23, 49),
        ("S1_08", "SALA 08", "Sala 08 (1o Pav)", "AULA",
         12.5, 7.5, 8.47, 12.17, 48),
        ("S1_09", "SALA 09", "Sala 09 (1o Pav)", "AULA",
         15.92, 12.86, 13.23, 12.17, 56),
        ("S1_10", "SALA 10", "Sala 10 (1o Pav)", "AULA",
         -31.35, 36.12, 13.23, 11.67, 45),
        ("S1_11", "SALA 11", "Sala 11 (1o Pav)", "AULA",
         -30.87, 23.58, 12.17, 11.38, 40),
        ("S1_12", "SALA 12", "Sala 12 (1o Pav)", "AULA",
         -29.21, 11.21, 8.62, 11.38, 36),
        ("S1_13", "SALA 13", "Sala 13 (1o Pav)", "AULA",
         -28.81, -14.82, 8.27, 8.88, 54),
        ("S1_14", "SALA 14", "Sala 14 (1o Pav)", "AULA",
         -29.05, -24.45, 8.42, 8.84, 54),
        ("S1_15", "SALA 15", "Sala 15 (1o Pav)", "AULA",
         -29.07, -34.06, 8.47, 8.84, 54),
        ("S1_16", "SALA 16", "Sala 16 (1o Pav)", "AULA",
         -29.07, -45.02, 8.53, 9.69, 40),
    ],
    Pavimento.PAV_2: [
        ("2_CPD", "CPD", "Cpd", "CPD",
         -19.98, 17.1, 12.17, 9.38, 0),
        ("S2_01", "SALA 01", "Sala 01 (2o Pav)", "AULA",
         -19.86, -46.66, 8.65, 9.39, 40),
        ("S2_02", "SALA 02", "Sala 02 (2o Pav)", "AULA",
         -19.91, -36.2, 8.57, 8.89, 60),
        ("S2_03", "SALA 03", "Sala 03 (2o Pav)", "AULA",
         -19.95, -26.54, 8.51, 8.89, 60),
        ("S2_04", "SALA 04", "Sala 04 (2o Pav)", "AULA",
         -19.98, -16.78, 8.57, 9.04, 60),
        ("S2_05", "SALA 05", "Sala 05 (2o Pav)", "AULA",
         -14.48, 6.91, 8.4, 9.38, 50),
        ("S2_06", "SALA 06", "Sala 06 (2o Pav)", "AULA",
         -4.71, 8.16, 7.15, 13.23, 49),
        ("S2_07", "SALA 07", "Sala 07 (2o Pav)", "AULA",
         3.05, 8.16, 7.15, 13.23, 49),
        ("S2_08", "SALA 08", "Sala 08 (2o Pav)", "AULA",
         11.32, 7.82, 7.99, 13.23, 48),
        ("S2_09", "SALA 09", "Sala 09 (2o Pav)", "AULA",
         20.45, 9.67, 8.73, 13.23, 32),
        ("S2_10", "SALA 10", "Sala 10 (2o Pav)", "AULA",
         19.57, 31.91, 7.39, 13.23, 40),
        ("S2_11", "SALA 11", "Sala 11 (2o Pav)", "AULA",
         11.54, 32.57, 7.39, 13.23, 48),
        ("S2_12", "SALA 12", "Sala 12 (2o Pav)", "AULA",
         2.93, 31.73, 6.76, 13.23, 49),
        ("S2_13", "SALA 13", "Sala 13 (2o Pav)", "AULA",
         -4.41, 31.36, 6.76, 13.23, 49),
        ("S2_14", "SALA 14", "Sala 14 (2o Pav)", "AULA",
         -31.27, 33.63, 13.23, 9.78, 45),
        ("S2_15", "SALA 15", "Sala 15 (2o Pav)", "AULA",
         -30.75, 23.01, 12.17, 9.78, 45),
        ("S2_16", "SALA 16", "Sala 16 (2o Pav)", "AULA",
         -31.27, 11.77, 13.23, 10.17, 45),
        ("S2_17", "SALA 17", "Sala 17 (2o Pav)", "AULA",
         -29.3, -16.75, 8.57, 8.48, 54),
        ("S2_18", "SALA 18", "Sala 18 (2o Pav)", "AULA",
         -29.2, -25.97, 8.51, 8.48, 35),
        ("S2_19", "SALA 19", "Sala 19 (2o Pav)", "AULA",
         -29.23, -36.01, 8.57, 9.0, 54),
        ("S2_20", "SALA 20", "Sala 20 (2o Pav)", "AULA",
         -29.27, -46.63, 8.65, 9.53, 40),
        ("2_SALA_DE_ESTUDOS", "SALA DE ESTUDOS", "Sala De Estudos (2o Pav)", "ESTUDO",
         -14.0, -6.74, 13.23, 11.55, 30),
        ("2_SALA_DIRETORIA_E_REUNI", "SALA DIRETORIA E REUNIÃO", "Sala Diretoria E Reunião (2o Pav)", "ADMIN",
         -34.9, -5.69, 13.23, 11.63, 0),
    ],
    Pavimento.TERRACO: [
        ("3_ATENDIMENTOS", "ATENDIMENTOS", "Atendimentos", "ADMIN",
         2.67, 10.15, 3.97, 12.17, 0),
        ("3_COWORKING", "COWORKING", "Coworking", "COWORKING",
         19.21, 10.59, 3.97, 12.17, 0),
        ("3_NUCLEO", "NÚCLEO", "Núcleo", "ADMIN",
         -8.38, 8.29, 8.21, 12.17, 0),
        ("S3_01", "SALA 01", "Sala 01 (Terraco)", "AULA",
         3.31, 10.07, 3.97, 12.17, 0),
        ("S3_02", "SALA 02", "Sala 02 (Terraco)", "AULA",
         19.96, 10.47, 3.97, 12.17, 0),
        ("3_SALA_COORDENADORES", "SALA COORDENADORES", "Sala Coordenadores (Terraco)", "ADMIN",
         -20.68, -28.55, 12.17, 9.21, 0),
        ("3_SALA_DIRETORIA", "SALA DIRETORIA", "Sala Diretoria (Terraco)", "ADMIN",
         -20.32, -38.56, 12.17, 9.21, 0),
        ("3_SALA_PROFESSORES", "SALA PROFESSORES", "Sala Professores (Terraco)", "ADMIN",
         -17.61, -17.43, 12.17, 11.1, 0),
    ],
}

RACK_POR_PAVIMENTO: Dict[Pavimento, str] = {
    Pavimento.TERREO: "RACK_4/5/6",
    Pavimento.PAV_1: "RACK_2",
    Pavimento.PAV_2: "RACK_1",
    Pavimento.TERRACO: "RACK_3",
}

# Preencher com a lista da Secretaria (planta -> ensalamento).
# Convencao observada no Controle de Ensalamento: sufixo A = Terreo,
# B = 1o Pavimento, C = 2o Pavimento.
CODIGO_ENSALAMENTO: Dict[str, str] = {
    # "S1_01": "01B",
}

# Catracas do terreo (Proposta 4466.0). Posicoes no eixo da recepcao.
CATRACAS_META: List[tuple] = [
    ("CATRACA_PRINCIPAL_A", "Catraca Principal A", -30.0, 26.0),
    ("CATRACA_PRINCIPAL_B", "Catraca Principal B", -28.0, 26.0),
    ("CATRACA_PRINCIPAL_C", "Catraca Principal C", -26.0, 26.0),
    ("CATRACA_SECRETARIA", "Catraca Secretaria", -31.5, 21.0),
    ("CATRACA_ESTACIONAMENTO", "Catraca Estacionamento", 10.0, 40.0),
]


def _gerar_cadeiras(sala_id: str, pavimento: Pavimento, ox: float, oz: float,
                    largura: float, profundidade: float, capacidade: int,
                    y: float) -> List[CadeiraModel]:
    """Distribui `capacidade` carteiras em grade, respeitando o retangulo real."""
    if capacidade <= 0:
        return []

    margem = 1.0
    util_x = max(largura - 2 * margem, 1.0)
    util_z = max(profundidade - 2 * margem, 1.0)

    # Escolhe a grade cuja proporcao mais se aproxima da sala.
    melhor, erro_min = (1, capacidade), float("inf")
    for colunas in range(1, capacidade + 1):
        fileiras = -(-capacidade // colunas)
        if colunas > util_x / 0.75 or fileiras > util_z / 0.85:
            continue
        erro = abs((util_x / colunas) - (util_z / fileiras))
        if erro < erro_min:
            melhor, erro_min = (colunas, fileiras), erro

    colunas, fileiras = melhor
    passo_x = util_x / max(colunas - 1, 1) if colunas > 1 else 0
    passo_z = util_z / max(fileiras - 1, 1) if fileiras > 1 else 0

    cadeiras: List[CadeiraModel] = []
    for f in range(fileiras):
        for c in range(colunas):
            indice = f * colunas + c
            if indice >= capacidade:
                break
            x = ox + margem + (c * passo_x if colunas > 1 else util_x / 2)
            z = oz + margem + (f * passo_z if fileiras > 1 else util_z / 2)
            cadeiras.append(
                CadeiraModel(
                    id=f"{sala_id}_CAD_{indice + 1:02d}",
                    sala_id=sala_id,
                    pavimento=pavimento,
                    posicao=Posicao3D(x=round(x, 3), y=y, z=round(z, 3)),
                    fileira=f,
                    coluna=c,
                )
            )
    return cadeiras


def construir_pavimentos() -> List[PavimentoModel]:
    pavimentos: List[PavimentoModel] = []

    for pav_id, nome, ordem, descricao in PAVIMENTOS_META:
        y = ordem * ALTURA_PAVIMENTO
        salas: List[SalaModel] = []

        for (sid, cod, snome, tipo, ox, oz, larg, prof, cap) in SALAS_POR_PAVIMENTO[pav_id]:
            cadeiras = _gerar_cadeiras(sid, pav_id, ox, oz, larg, prof, cap, y)
            salas.append(
                SalaModel(
                    id=sid,
                    nome=snome,
                    pavimento=pav_id,
                    tipo=tipo,
                    capacidade=len(cadeiras),
                    posicao=Posicao3D(x=ox, y=y, z=oz),
                    dimensao=Dimensao3D(largura=larg, altura=3.2, profundidade=prof),
                    rack_id=RACK_POR_PAVIMENTO[pav_id],
                    cadeiras=cadeiras,
                )
            )

        pavimentos.append(
            PavimentoModel(
                id=pav_id, nome=nome, ordem=ordem, altura_y=y,
                descricao=descricao, salas=salas,
            )
        )

    return pavimentos


def construir_catracas() -> List[CatracaModel]:
    return [
        CatracaModel(
            id=cid, nome=nome, pavimento=Pavimento.TERREO,
            posicao=Posicao3D(x=x, y=0.0, z=z),
        )
        for cid, nome, x, z in CATRACAS_META
    ]


def codigo_ensalamento(sala_id: str) -> Optional[str]:
    """Codigo usado pela Secretaria (ex.: 01B) para uma sala da planta."""
    return CODIGO_ENSALAMENTO.get(sala_id)
