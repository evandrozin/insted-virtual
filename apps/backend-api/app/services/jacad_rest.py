"""Cliente REST do JaCad, escrito sobre o contrato real do tenant.

Ver docs/jacad-api.md para o levantamento. Os pontos que mais surpreendem:

* A chave do .env nao e o token de acesso. Troca-se em POST /auth/token, com a
  chave no header `token`, e usa-se o token da resposta no `Authorization` -
  sem "Bearer". A troca vale ate `expiresIn` e e refeita sozinha.
* Nao existe endpoint de professores. Eles vem das disciplinas de cada turma.
* /alunos nao sabe quem esta ativo; isso sai de /matriculas.
* O horario traz `dataAula` (data real, nao dia da semana) e fatias de ~50 min.
  Uma aula das 19:00 as 22:30 chega como varias linhas, que sao reagrupadas
  aqui no bloco que o aluno reconhece como "a aula".
"""
from __future__ import annotations

import time as _time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from app.models.academico import AlunoModel, AulaModel, ProfessorModel, TurmaModel

PAGINA_MAX = 500

# Intervalo entre fatias que ainda conta como a mesma aula. As fatias tem 50 min
# de aula e ate 20 de intervalo; acima disso e outro bloco, e juntar esconderia
# o intervalo do aluno.
FOLGA_ENTRE_FATIAS = timedelta(minutes=25)


class ErroJacad(RuntimeError):
    pass


class JacadRestClient:
    """Consome a API do JaCad. Um cliente por processo; renova o token sozinho."""

    def __init__(
        self,
        base_url: str,
        chave: str,
        timeout: float = 60.0,
        periodo_letivo: Optional[int] = None,
        unidade_fisica: Optional[str] = "Insted",
        id_org: int = 0,
    ) -> None:
        import httpx

        # O OpenAPI declara o servidor sem /api, e os caminhos ja o trazem;
        # deixar o /api na base duplicaria o prefixo.
        base = base_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]

        self._http = httpx.Client(base_url=base, timeout=timeout)
        self._chave = chave
        self._token: Optional[str] = None
        self._expira_em: float = 0.0
        self._periodo = periodo_letivo
        self._nome_periodo: Optional[str] = None
        self._unidade = unidade_fisica
        self._id_org = id_org
        self._cache_turmas: List[dict] = []

    # -- autenticacao -------------------------------------------------------
    def _autorizacao(self) -> Dict[str, str]:
        # 60 s de margem: renovar em cima da expiracao daria 401 no meio de uma
        # sincronizacao longa.
        if not self._token or _time.time() > self._expira_em - 60:
            self._trocar_token()
        return {"Authorization": self._token or "", "Accept": "application/json"}

    def _trocar_token(self) -> None:
        r = self._http.post("/api/v1/auth/token", headers={"token": self._chave})
        if r.status_code != 200:
            raise ErroJacad(
                f"troca de token recusada (HTTP {r.status_code}): {r.text[:200]}"
            )
        corpo = r.json()
        self._token = corpo.get("token")
        if not self._token:
            raise ErroJacad("resposta da autenticacao veio sem token")
        # expiresIn e epoch em milissegundos, nao duracao.
        self._expira_em = float(corpo.get("expiresIn", 0)) / 1000.0

    # -- transporte ---------------------------------------------------------
    def _pagina(self, caminho: str, **filtros) -> Dict[str, Any]:
        r = self._http.get(caminho, headers=self._autorizacao(), params=filtros)
        if r.status_code != 200:
            raise ErroJacad(f"GET {caminho} -> HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def _todos(self, caminho: str, **filtros) -> List[dict]:
        """Percorre a paginacao ate juntar tudo."""
        itens: List[dict] = []
        pagina = 0
        while True:
            corpo = self._pagina(
                caminho, pageSize=PAGINA_MAX, currentPage=pagina, **filtros
            )
            lote = corpo.get("elements") or []
            itens.extend(lote)
            total = (corpo.get("page") or {}).get("totalElements", len(itens))
            if not lote or len(itens) >= total:
                return itens
            pagina += 1

    # -- periodo letivo -----------------------------------------------------
    def periodo_letivo(self) -> int:
        """Periodo corrente, perguntado ao proprio ERP.

        O JaCad marca o periodo vigente com `periodoAtual` e classifica o tipo
        em `tipo`. Usar esses dois campos e melhor que inferir pelo nome: a
        instituicao mantem em paralelo periodos de Pos, Cursos Livres e PROVERT,
        todos ABERTOS, que nao sao a graduacao presencial da maquete.
        """
        if self._periodo:
            return self._periodo

        abertos = self._todos(
            "/api/v1/academico/periodos-letivos/",
            idOrg=self._id_org,
            situacao="ABERTO",
        )
        graduacao = [
            p for p in abertos if p.get("tipo") == "GRADUACAO_SEMESTRAL"
        ] or abertos

        atuais = [p for p in graduacao if p.get("periodoAtual")]
        if not atuais:
            # Sem a marcacao, cai para o periodo que contem hoje.
            hoje = date.today().isoformat()
            atuais = [
                p for p in graduacao
                if (p.get("dataInicio") or "9999") <= hoje <= (p.get("dataTermino") or "0000")
            ]
        if not atuais:
            raise ErroJacad(
                "nenhum periodo letivo vigente encontrado; "
                "defina JACAD_PERIODO_LETIVO"
            )

        escolhido = max(atuais, key=lambda p: p.get("dataInicio") or "")
        self._periodo = escolhido["idPeriodoLetivo"]
        self._nome_periodo = escolhido.get("descricao")
        return self._periodo

    @property
    def nome_periodo(self) -> Optional[str]:
        return self._nome_periodo

    # -- contrato -----------------------------------------------------------
    def listar_alunos(self) -> List[AlunoModel]:
        """Alunos com matricula ATIVA no periodo corrente.

        /alunos traz o cadastro historico inteiro sem dizer quem esta ativo;
        quem responde isso e /matriculas.
        """
        matriculas = self._todos(
            "/api/v1/academico/matriculas",
            statusMatricula="ATIVA",
            idPeriodoLetivo=self.periodo_letivo(),
        )
        alunos: Dict[str, AlunoModel] = {}
        for m in matriculas:
            if self._unidade and m.get("unidadeFisica") != self._unidade:
                continue
            ra = str(m.get("ra") or "").strip()
            if not ra:
                continue  # sem RA a catraca nao teria como reconhece-lo
            alunos[ra] = AlunoModel(
                ra=ra,
                nome=m.get("aluno") or "(sem nome)",
                curso=m.get("curso") or "Nao informado",
                turma_id=str(m.get("idTurma") or "SEM-TURMA"),
                periodo=1,
                situacao="ATIVO",
            )
        return list(alunos.values())

    def _turmas_cruas(self) -> List[dict]:
        if not self._cache_turmas:
            self._cache_turmas = self._todos(
                "/api/v1/academico/turmas",
                turmaIdPeriodoLetivo=self.periodo_letivo(),
                turmaStatus="ATIVA",
            )
        return self._cache_turmas

    def _presenciais(self) -> List[dict]:
        return [
            t
            for t in self._turmas_cruas()
            if not self._unidade or t.get("turmaUnidadeFisica") == self._unidade
        ]

    def listar_turmas(self) -> List[TurmaModel]:
        return [
            TurmaModel(
                id=str(t["idTurma"]),
                nome=t.get("turmaNome") or str(t["idTurma"]),
                nome_reduzido=t.get("turmaNomeRed"),
                curso=t.get("turmaCurso") or "Nao informado",
                periodo=_periodo_da_turma(t.get("turmaPeriodoItem")),
                alunos_ra=[],
            )
            for t in self._presenciais()
        ]

    def _disciplinas(self) -> List[dict]:
        """Disciplinas das turmas presenciais, cada uma com a turma de origem."""
        saida: List[dict] = []
        for t in self._presenciais():
            for d in self._todos(
                f"/api/v1/academico/turmas/{t['idTurma']}/disciplinas"
            ):
                d["_turma"] = t
                saida.append(d)
        return saida

    def listar_professores(self) -> List[ProfessorModel]:
        """Corpo docente do periodo.

        A API nao tem endpoint de professores: eles aparecem como idProfessor e
        professor nas disciplinas da turma. `idProfessor` e a chave estavel - se
        o cracha da catraca usar outro identificador, e aqui que se ajusta.
        """
        vistos: Dict[int, ProfessorModel] = {}
        for d in self._disciplinas():
            pid = d.get("idProfessor")
            if not pid or pid in vistos:
                continue
            vistos[pid] = ProfessorModel(
                matricula=str(pid),
                nome=(d.get("professor") or "").strip() or f"Professor {pid}",
                setor=(d.get("_turma") or {}).get("turmaCurso"),
                cargo="Docente",
            )
        return list(vistos.values())

    def listar_grade_horaria(self) -> List[AulaModel]:
        """Aulas do periodo, com sala e professor, reagrupando as fatias."""
        fatias: Dict[tuple, List[dict]] = defaultdict(list)
        for d in self._disciplinas():
            for h in self._todos(
                f"/api/v1/academico/disciplinas/{d['idDisciplinaProfessor']}/horarios"
            ):
                if not h.get("dataAula") or not h.get("sala"):
                    continue
                chave = (
                    d["idDisciplinaProfessor"],
                    h["dataAula"],
                    str(h.get("sala")).strip(),
                    str(d["_turma"]["idTurma"]),
                )
                fatias[chave].append(h)

        aulas: List[AulaModel] = []
        for (idp, data_aula, sala, turma_id), lote in fatias.items():
            lote.sort(key=lambda h: h["horaInicio"])
            dia = date.fromisoformat(data_aula)
            primeiro = lote[0]
            for ordem, (inicio, fim) in enumerate(_blocos(lote)):
                aulas.append(
                    AulaModel(
                        id=f"JAC_{idp}_{data_aula}_{ordem}",
                        turma_id=turma_id,
                        disciplina=primeiro.get("disciplina") or "Disciplina",
                        professor=(primeiro.get("professor") or "").strip()
                        or "A definir",
                        professor_matricula=(
                            str(primeiro["idProfessor"])
                            if primeiro.get("idProfessor")
                            else None
                        ),
                        sala_id=sala,
                        dia_semana=dia.weekday(),
                        hora_inicio=inicio,
                        hora_fim=fim,
                    )
                )
        return aulas


def _periodo_da_turma(bruto: Any) -> int:
    """Le o numero do periodo de textos como "1o Semestre".

    O ERP devolve o rotulo por extenso, nao um inteiro; e o rotulo varia entre
    cursos ("1o Semestre", "2o Periodo"). So o numero da frente interessa.
    """
    if isinstance(bruto, int):
        return max(1, bruto)
    digitos = ""
    for c in str(bruto or ""):
        if c.isdigit():
            digitos += c
        elif digitos:
            break
    return int(digitos) if digitos else 1


def _hora(marca: str) -> datetime:
    """Le "1970-01-01T19:00:00-0300" ignorando a data-carimbo de 1970."""
    return datetime.fromisoformat(marca).replace(tzinfo=None)


def _blocos(fatias: Iterable[dict]):
    """Junta fatias contiguas num unico bloco (inicio, fim)."""
    inicio = fim = None
    for f in fatias:
        i, t = _hora(f["horaInicio"]), _hora(f["horaTermino"])
        if inicio is None:
            inicio, fim = i, t
        elif i - fim <= FOLGA_ENTRE_FATIAS:
            fim = max(fim, t)
        else:
            yield inicio.time(), fim.time()
            inicio, fim = i, t
    if inicio is not None:
        yield inicio.time(), fim.time()
