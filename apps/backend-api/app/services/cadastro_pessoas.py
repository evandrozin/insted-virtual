"""Espelho local do cadastro de pessoas do JACAD.

Existe para que a conferencia com a catraca nao dependa do ERP estar de pe. A
catraca entrega um identificador de cracha; quem ele e, a que turma pertence e
se esta ativo sai da base local, que este modulo mantem atualizada.

O identificador e a chave do cruzamento nos dois lados: RA para aluno,
matricula funcional para docente. Um professor sem matricula no ERP nao entra
aqui - nao ha por onde reconhece-lo na catraca.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.core import clock
from app.core.config import settings
from app.models.academico import AlunoModel, ProfessorModel, TurmaModel
from app.services.jacad_client import obter_client


def _alunos(
    alunos: Iterable[AlunoModel], turmas: Iterable[TurmaModel] = ()
) -> List[dict]:
    """Normaliza alunos, resolvendo o nome curto da turma.

    O codigo da turma sozinho ("ADM-3") nao diz nada a quem le a listagem; o
    ERP tem um nome reduzido para isso. Quando ele nao vem, fica nulo e a tela
    volta a mostrar o codigo - melhor que inventar um rotulo.
    """
    curto = {t.id: t.nome_reduzido for t in turmas if t.nome_reduzido}
    return [
        {
            "identificador": a.ra,
            "nome": a.nome,
            "curso": a.curso,
            "turma_id": a.turma_id,
            "turma_nome": curto.get(a.turma_id),
            "periodo": a.periodo,
            "situacao": a.situacao,
        }
        for a in alunos
    ]


def _professores(professores: Iterable[ProfessorModel]) -> List[dict]:
    # Sem matricula nao ha cruzamento possivel: descartar aqui e melhor que
    # gravar uma pessoa que a catraca nunca vai reconhecer.
    return [
        {
            "identificador": p.matricula,
            "nome": p.nome,
            "email": p.email,
            "setor": p.setor,
            "cargo": p.cargo,
            "situacao": p.situacao,
        }
        for p in professores
        if p.matricula and p.matricula.strip()
    ]


async def espelhar() -> Dict[str, Any]:
    """Traz alunos e professores do ERP para a base local.

    Sem DATABASE_URL nao ha onde espelhar. Nao e erro: o sistema continua
    rodando com os dados em memoria, so nao guarda a base para conferencia.
    """
    if not settings.DATABASE_URL:
        return {"aplicado": False, "motivo": "sem DATABASE_URL"}

    from app.data import pessoa_repository as repo

    client = obter_client()
    resumo = await repo.sincronizar_do_jacad(
        {
            "ALUNO": _alunos(client.listar_alunos(), client.listar_turmas()),
            "PROFESSOR": _professores(client.listar_professores()),
        }
    )
    resumo["aplicado"] = True
    resumo["sincronizado_em"] = clock.agora().isoformat()
    return resumo
