"""Adapter de integracao com o ERP academico JACAD.

Duas implementacoes intercambiaveis:

* ``JacadRestClient``  - consome a API REST do JACAD (requer JACAD_BASE_URL/TOKEN).
* ``JacadMockClient``  - dataset sintetico deterministico, usado em demonstracao
  e desenvolvimento. Mantem exatamente o mesmo contrato do client real, entao a
  troca e transparente para o motor de presenca.
"""
from __future__ import annotations

import random
from datetime import time
from typing import List, Protocol, Set

from app.core import parametros
from app.core.config import settings
from app.data.campus_seed import SALAS_POR_PAVIMENTO
from app.models.academico import AlunoModel, AulaModel, ProfessorModel, TurmaModel
from app.models.enums import Pavimento

# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------


class JacadClient(Protocol):
    def listar_alunos(self) -> List[AlunoModel]: ...
    def listar_professores(self) -> List[ProfessorModel]: ...
    def listar_turmas(self) -> List[TurmaModel]: ...
    def listar_grade_horaria(self) -> List[AulaModel]: ...


# ---------------------------------------------------------------------------
# Dataset sintetico
# ---------------------------------------------------------------------------

CURSOS = [
    ("ADM", "Administracao", ["Teoria Geral da Administracao", "Marketing Estrategico",
                              "Gestao Financeira", "Comportamento Organizacional"]),
    ("DIR", "Direito", ["Direito Constitucional", "Direito Penal I",
                        "Processo Civil", "Hermeneutica Juridica"]),
    ("ENF", "Enfermagem", ["Anatomia Humana", "Semiologia", "Saude Coletiva",
                           "Farmacologia Aplicada"]),
    ("ESW", "Engenharia de Software", ["Estrutura de Dados", "Arquitetura de Software",
                                       "Banco de Dados", "Engenharia de Requisitos"]),
    ("PED", "Pedagogia", ["Didatica", "Psicologia da Educacao",
                          "Alfabetizacao e Letramento", "Politicas Educacionais"]),
    ("CCO", "Ciencias Contabeis", ["Contabilidade Geral", "Auditoria",
                                   "Controladoria", "Analise de Custos"]),
    ("PSI", "Psicologia", ["Psicopatologia", "Psicologia do Desenvolvimento",
                           "Tecnicas de Entrevista", "Neurociencias"]),
    ("SIN", "Sistemas de Informacao", ["Redes de Computadores", "Sistemas Operacionais",
                                       "Inteligencia Artificial", "Seguranca da Informacao"]),
]

NOMES = [
    "Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique",
    "Isabela", "Joao", "Karina", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro",
    "Quezia", "Rafael", "Sofia", "Thiago", "Ursula", "Vitor", "Wesley", "Yasmin",
    "Amanda", "Caio", "Debora", "Emerson", "Fabiana", "Gustavo", "Helena", "Igor",
]
SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves",
    "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho",
    "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa",
]
# (nome, area). A matricula e derivada da posicao, entao e estavel entre
# execucoes - o mesmo docente mantem o identificador que a catraca leria.
PROFESSORES = [
    ("Adriana Mendes",  "Administracao"),
    ("Carlos Tavares",  "Direito"),
    ("Denise Rocha",    "Enfermagem"),
    ("Eduardo Prado",   "Engenharia de Software"),
    ("Fernanda Luz",    "Pedagogia"),
    ("Gilberto Nunes",  "Ciencias Contabeis"),
    ("Helena Vasques",  "Psicologia"),
    ("Ivan Portela",    "Sistemas de Informacao"),
    ("Juliana Sa",      "Direito"),
    ("Leonardo Brito",  "Engenharia de Software"),
    ("Marcia Antunes",  "Pedagogia"),
    ("Otavio Ramos",    "Administracao"),
]

# Prefixo 3 para nao colidir com o RA de aluno, que comeca em 2026.
def _matricula_docente(indice: int) -> str:
    return f"3{indice + 1:07d}"

# Corpo discente ativo em 2026.2, informado pela Secretaria. Trocar este numero
# e o suficiente para o conjunto sintetico refletir o semestre corrente - as
# turmas se ajustam sozinhas. Quando o ERP real entrar, nada disso e usado.
TOTAL_ALUNOS = 1732
PERIODOS_POR_CURSO = 6
# Piso por turma: mais periodos e melhor que turmas gigantes, que nao caberiam
# nas salas reais (30 a 40 lugares) e encheriam a maquete de sobrelotacao
# inventada.
MENOR_TURMA = 20

# Blocos de horario praticados no campus (matutino, vespertino e noturno).
BLOCOS = [
    (time(8, 0), time(9, 40)),
    (time(9, 55), time(11, 35)),
    (time(13, 30), time(15, 10)),
    (time(19, 0), time(20, 40)),
    (time(20, 50), time(22, 30)),
]

# Somente ambientes que efetivamente recebem turmas.
TIPOS_LETIVOS = {"AULA", "LABORATORIO", "AUDITORIO", "TEATRO", "MULTIUSO"}


def _salas_letivas() -> List[str]:
    """Salas de aula reais da planta, na ordem dos pavimentos.

    A tupla do seed e (id, cod_planta, nome, tipo, x, z, largura, prof, cap).
    """
    salas: List[str] = []
    for pav in (Pavimento.TERREO, Pavimento.PAV_1, Pavimento.PAV_2, Pavimento.TERRACO):
        for linha in SALAS_POR_PAVIMENTO[pav]:
            sid, tipo, capacidade = linha[0], linha[3], linha[8]
            if tipo in TIPOS_LETIVOS and capacidade > 0:
                salas.append(sid)
    return salas


class JacadMockClient:
    """Gera um corpo discente e uma grade horaria estaveis entre execucoes."""

    def __init__(self, seed: int = 20260828) -> None:
        self._rng = random.Random(seed)
        self._turmas: List[TurmaModel] = []
        self._alunos: List[AlunoModel] = []
        self._professores: List[ProfessorModel] = [
            ProfessorModel(
                matricula=_matricula_docente(i),
                nome=f"Prof. {nome}",
                email=f"{nome.split()[0].lower()}.{nome.split()[-1].lower()}@insted.edu.br",
                setor=area,
                cargo="Docente",
            )
            for i, (nome, area) in enumerate(PROFESSORES)
        ]
        self._aulas: List[AulaModel] = []
        self._construir()

    # -- construcao ---------------------------------------------------------
    def _construir(self) -> None:
        rng = self._rng
        ra_seq = 20260000

        planejadas = [
            (sigla, curso, periodo)
            for sigla, curso, _disciplinas in CURSOS
            for periodo in range(1, PERIODOS_POR_CURSO + 1)
        ]
        tamanhos = self._repartir(TOTAL_ALUNOS, len(planejadas))

        for (sigla, curso, periodo), qtd in zip(planejadas, tamanhos):
            turma_id = f"{sigla}-{periodo}"
            alunos_ra: List[str] = []

            for _ in range(qtd):
                ra_seq += 1
                ra = str(ra_seq)
                nome = f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"
                self._alunos.append(
                    AlunoModel(ra=ra, nome=nome, curso=curso,
                               turma_id=turma_id, periodo=periodo)
                )
                alunos_ra.append(ra)

            self._turmas.append(
                TurmaModel(
                    id=turma_id,
                    nome=f"{curso} - {periodo}o periodo",
                    nome_reduzido=f"{sigla} {periodo}P",
                    curso=curso,
                    periodo=periodo,
                    alunos_ra=alunos_ra,
                )
            )

        self._montar_grade()

    def _repartir(self, total: int, turmas: int) -> List[int]:
        """Reparte `total` alunos entre `turmas`, com variacao e soma exata.

        As turmas variam de tamanho como variam na pratica, mas a soma precisa
        fechar no total: e o numero que a diretoria confere contra o ERP, e uma
        aproximacao "mais ou menos 30" desmoralizaria a tela.
        """
        rng = self._rng
        base = [rng.randint(28, 44) for _ in range(turmas)]
        fator = total / sum(base)
        tamanhos = [max(MENOR_TURMA, round(b * fator)) for b in base]

        # A escala arredonda para cima e para baixo; a sobra e distribuida de
        # uma em uma, sem deixar turma abaixo do minimo.
        resto = total - sum(tamanhos)
        i = 0
        while resto:
            passo = 1 if resto > 0 else -1
            alvo = i % turmas
            if tamanhos[alvo] + passo >= MENOR_TURMA:
                tamanhos[alvo] += passo
                resto -= passo
            i += 1
        return tamanhos

    def _montar_grade(self) -> None:
        """Aloca cada turma em salas/blocos sem colisao de sala no mesmo horario."""
        rng = self._rng
        salas = _salas_letivas()
        aula_seq = 0

        for dia in range(0, 5):  # segunda a sexta
            for bloco_idx, (inicio, fim) in enumerate(BLOCOS):
                ocupadas: Set[str] = set()
                # Manha atende periodos 1-2, tarde e esparsa, noite atende todos.
                candidatas = [
                    t for t in self._turmas
                    if (bloco_idx <= 1 and t.periodo <= 2)
                    or (bloco_idx == 2 and rng.random() < 0.35)
                    or (bloco_idx >= 3)
                ]
                rng.shuffle(candidatas)

                for turma in candidatas:
                    livres = [s for s in salas if s not in ocupadas]
                    if not livres:
                        break
                    # 12% das janelas ficam sem aula: a grade real tem buracos.
                    if rng.random() < 0.12:
                        continue

                    sala_id = rng.choice(livres)
                    ocupadas.add(sala_id)
                    disciplinas = next(
                        d for s, _c, d in CURSOS if turma.id.startswith(s + "-")
                    )
                    aula_seq += 1
                    # A ordem dos sorteios importa: o dataset e deterministico
                    # por semente, e inverter disciplina e docente aqui muda a
                    # grade inteira.
                    disciplina = rng.choice(disciplinas)
                    docente = rng.choice(self._professores)

                    self._aulas.append(
                        AulaModel(
                            id=f"AULA_{aula_seq:05d}",
                            turma_id=turma.id,
                            disciplina=disciplina,
                            professor=docente.nome,
                            professor_matricula=docente.matricula,
                            sala_id=sala_id,
                            dia_semana=dia,
                            hora_inicio=inicio,
                            hora_fim=fim,
                        )
                    )

    # -- contrato -----------------------------------------------------------
    def listar_alunos(self) -> List[AlunoModel]:
        return list(self._alunos)

    def listar_professores(self) -> List[ProfessorModel]:
        return list(self._professores)

    def listar_turmas(self) -> List[TurmaModel]:
        return list(self._turmas)

    def listar_grade_horaria(self) -> List[AulaModel]:
        return list(self._aulas)


# ---------------------------------------------------------------------------
# Client REST real
# ---------------------------------------------------------------------------


class JacadRestClient:
    """Consome a API do JACAD. Ajuste os paths conforme o contrato do tenant."""

    def __init__(self, base_url: str, token: str, timeout: float = 20.0) -> None:
        import httpx  # import tardio: so necessario no modo integrado

        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json"},
            timeout=timeout,
        )

    def _get(self, path: str) -> list:
        resposta = self._http.get(path)
        resposta.raise_for_status()
        corpo = resposta.json()
        return corpo.get("data", corpo) if isinstance(corpo, dict) else corpo

    def listar_alunos(self) -> List[AlunoModel]:
        return [
            AlunoModel(
                ra=str(item["registroAcademico"]),
                nome=item["nome"],
                curso=item.get("curso", {}).get("nome", "Nao informado"),
                turma_id=str(item.get("turma", {}).get("codigo", "SEM-TURMA")),
                periodo=int(item.get("periodo", 1)),
                situacao=item.get("situacao", "ATIVO"),
            )
            for item in self._get("/academico/alunos?situacao=ATIVO")
        ]

    def listar_professores(self) -> List[ProfessorModel]:
        """Corpo docente ativo.

        `matricula` e o campo que precisa bater com o cracha da catraca. Se o
        tenant expuser outro nome para ele, e aqui que se ajusta.
        """
        return [
            ProfessorModel(
                matricula=str(item.get("matricula") or item.get("registroFuncional")),
                nome=item["nome"],
                email=item.get("email"),
                setor=item.get("departamento", {}).get("nome")
                if isinstance(item.get("departamento"), dict)
                else item.get("departamento"),
                cargo=item.get("cargo", "Docente"),
                situacao=item.get("situacao", "ATIVO"),
            )
            for item in self._get("/academico/professores?situacao=ATIVO")
        ]

    def listar_turmas(self) -> List[TurmaModel]:
        return [
            TurmaModel(
                id=str(item["codigo"]),
                nome=item["nome"],
                curso=item.get("curso", {}).get("nome", "Nao informado"),
                periodo=int(item.get("periodo", 1)),
                alunos_ra=[str(ra) for ra in item.get("alunos", [])],
            )
            for item in self._get("/academico/turmas")
        ]

    def listar_grade_horaria(self) -> List[AulaModel]:
        return [
            AulaModel(
                id=str(item["id"]),
                turma_id=str(item["turmaCodigo"]),
                disciplina=item["disciplina"],
                professor=item.get("professor", "A definir"),
                professor_matricula=(
                    str(item["professorMatricula"])
                    if item.get("professorMatricula") else None
                ),
                sala_id=str(item["salaCodigo"]),
                dia_semana=int(item["diaSemana"]),
                hora_inicio=time.fromisoformat(item["horaInicio"]),
                hora_fim=time.fromisoformat(item["horaFim"]),
            )
            for item in self._get("/academico/grade-horaria")
        ]


def obter_client() -> JacadClient:
    # O endereco e o modo podem vir do banco; o token continua so no ambiente.
    base_url = parametros.jacad_base_url()
    if parametros.jacad_modo_mock() or not base_url:
        return JacadMockClient()
    return JacadRestClient(base_url, settings.JACAD_TOKEN)
