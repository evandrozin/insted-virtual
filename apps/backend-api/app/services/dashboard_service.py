"""Projecao de leitura do painel da Diretoria.

Le a topologia local e as presencas do EstadoStore para montar KPIs, ocupacao
por sala/pavimento, serie intradiaria, ranking por curso e alertas.
Nao muta estado.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from app.core import clock
from app.models.dashboard import (
    KPIsDiretoria,
    OcupacaoPavimento,
    OcupacaoSala,
    SerieTemporalPonto,
    SnapshotDiretoria,
)
from app.models.enums import StatusPresenca
from app.services.campus_state import CampusState, estado
from app.services.store import obter_store

_EM_AULA = (StatusPresenca.PRESENTE, StatusPresenca.ATRASADO)


class ServicoDashboard:
    def __init__(self, state: CampusState) -> None:
        self.state = state

    @property
    def store(self):
        return obter_store()

    # ------------------------------------------------------------------
    async def ocupacao_salas(self, agora: datetime) -> List[OcupacaoSala]:
        aula_por_sala = {}
        for aula_id in list(self.state.aulas_ativas):
            aula = self.state.aulas.get(aula_id)
            if aula and aula.em_andamento(agora):
                aula_por_sala[aula.sala_id] = aula

        # Uma leitura por aula em andamento, nao por sala.
        registros_por_aula = {
            aula.id: await self.store.presencas_da_aula(aula.id)
            for aula in aula_por_sala.values()
        }

        resultado: List[OcupacaoSala] = []
        for sala in self.state.salas.values():
            if sala.capacidade == 0:
                continue

            item = OcupacaoSala(
                sala_id=sala.id,
                sala_nome=sala.nome,
                pavimento=sala.pavimento,
                capacidade=sala.capacidade,
            )

            aula = aula_por_sala.get(sala.id)
            if aula is not None:
                registros = registros_por_aula.get(aula.id, [])
                item.aula_id = aula.id
                item.disciplina = aula.disciplina
                item.professor = aula.professor
                item.turma_id = aula.turma_id
                item.inicio = aula.hora_inicio.strftime("%H:%M")
                item.fim = aula.hora_fim.strftime("%H:%M")
                item.em_aula = True
                item.esperados = len(registros)
                item.presentes = sum(
                    1 for r in registros if r.status == StatusPresenca.PRESENTE
                )
                item.atrasados = sum(
                    1 for r in registros if r.status == StatusPresenca.ATRASADO
                )
                item.ausentes = sum(
                    1 for r in registros if r.status == StatusPresenca.AUSENTE
                )
                item.evadidos = sum(
                    1 for r in registros if r.status == StatusPresenca.EVADIDO
                )

            resultado.append(item)

        resultado.sort(key=lambda s: (not s.em_aula, s.taxa_presenca))
        return resultado

    # ------------------------------------------------------------------
    def ocupacao_pavimentos(self, salas: List[OcupacaoSala]) -> List[OcupacaoPavimento]:
        agrupado: Dict[str, OcupacaoPavimento] = {}
        for pav in self.state.pavimentos:
            agrupado[pav.id.value] = OcupacaoPavimento(
                pavimento=pav.id, nome=pav.nome, capacidade=0,
                presentes=0, esperados=0, salas_em_aula=0, taxa_presenca=0.0,
            )

        for sala in salas:
            alvo = agrupado[sala.pavimento.value]
            alvo.capacidade += sala.capacidade
            alvo.esperados += sala.esperados
            alvo.presentes += sala.presentes + sala.atrasados
            alvo.salas_em_aula += 1 if sala.em_aula else 0

        for alvo in agrupado.values():
            alvo.taxa_presenca = (
                round(100 * alvo.presentes / alvo.esperados, 1) if alvo.esperados else 0.0
            )

        return sorted(
            agrupado.values(),
            key=lambda p: next(
                x.ordem for x in self.state.pavimentos if x.id == p.pavimento
            ),
        )

    # ------------------------------------------------------------------
    async def kpis(self, agora: datetime, salas: List[OcupacaoSala]) -> KPIsDiretoria:
        esperados = sum(s.esperados for s in salas)
        presentes = sum(s.presentes for s in salas)
        atrasados = sum(s.atrasados for s in salas)
        ausentes = sum(s.ausentes for s in salas)
        evadidos = sum(s.evadidos for s in salas)
        em_aula = presentes + atrasados

        taxa = round(100 * em_aula / esperados, 1) if esperados else 0.0

        limite_fluxo = agora - timedelta(hours=1)
        eventos = await self.store.feed(limite=200)
        fluxo = sum(
            1 for e in eventos
            if datetime.fromisoformat(e["timestamp"]) >= limite_fluxo
        )

        capacidade = self.state.capacidade_total()
        catracas = await self.store.estado_catracas()
        total_catracas = len(self.state.catracas)
        # Catraca sem nenhuma passagem ainda conta como online.
        offline = sum(1 for info in catracas.values() if not info.get("online", True))

        return KPIsDiretoria(
            atualizado_em=agora,
            alunos_no_campus=await self.store.total_no_campus(),
            alunos_esperados_agora=esperados,
            presentes_em_aula=em_aula,
            taxa_presenca_geral=taxa,
            taxa_presenca_variacao=0.0,
            atrasados=atrasados,
            ausentes=ausentes,
            evasao_em_aula=evadidos,
            salas_em_aula=sum(1 for s in salas if s.em_aula),
            salas_ociosas=sum(1 for s in salas if not s.em_aula),
            capacidade_total=capacidade,
            taxa_ocupacao_campus=(
                round(100 * em_aula / capacidade, 1) if capacidade else 0.0
            ),
            catracas_online=total_catracas - offline,
            catracas_total=total_catracas,
            fluxo_ultima_hora=fluxo,
        )

    # ------------------------------------------------------------------
    async def ranking_cursos(self, agora: datetime) -> List[dict]:
        acumulado: Dict[str, Dict[str, int]] = {}

        for aula_id in list(self.state.aulas_ativas):
            aula = self.state.aulas.get(aula_id)
            if aula is None or not aula.em_andamento(agora):
                continue
            turma = self.state.turmas.get(aula.turma_id)
            if turma is None:
                continue
            bucket = acumulado.setdefault(
                turma.curso, {"esperados": 0, "presentes": 0, "atrasados": 0}
            )
            for registro in await self.store.presencas_da_aula(aula_id):
                bucket["esperados"] += 1
                if registro.status == StatusPresenca.PRESENTE:
                    bucket["presentes"] += 1
                elif registro.status == StatusPresenca.ATRASADO:
                    bucket["atrasados"] += 1

        linhas = [
            {
                "curso": curso,
                "esperados": v["esperados"],
                "presentes": v["presentes"] + v["atrasados"],
                "atrasados": v["atrasados"],
                "taxa": round(
                    100 * (v["presentes"] + v["atrasados"]) / v["esperados"], 1
                ) if v["esperados"] else 0.0,
            }
            for curso, v in acumulado.items()
        ]
        linhas.sort(key=lambda linha: linha["taxa"], reverse=True)
        return linhas

    # ------------------------------------------------------------------
    async def serie(self) -> List[SerieTemporalPonto]:
        pontos = [SerieTemporalPonto(**p) for p in await self.store.serie()]
        return pontos[-24:]

    # ------------------------------------------------------------------
    async def snapshot(self) -> SnapshotDiretoria:
        agora = clock.agora()
        salas = await self.ocupacao_salas(agora)
        return SnapshotDiretoria(
            kpis=await self.kpis(agora, salas),
            ocupacao_salas=salas,
            ocupacao_pavimentos=self.ocupacao_pavimentos(salas),
            serie_presenca=await self.serie(),
            alertas=await self.store.alertas(limite=20),
            ranking_cursos=await self.ranking_cursos(agora),
        )

    # ------------------------------------------------------------------
    def maquete(self) -> dict:
        """Topologia + status atual das carteiras (projecao local)."""
        with self.state.lock:
            return {
                "pavimentos": [
                    {
                        "id": pav.id.value,
                        "nome": pav.nome,
                        "ordem": pav.ordem,
                        "altura_y": pav.altura_y,
                        "descricao": pav.descricao,
                        "salas": [
                            {
                                "id": s.id,
                                "nome": s.nome,
                                "tipo": s.tipo,
                                "capacidade": s.capacidade,
                                "rack_id": s.rack_id,
                                "posicao": s.posicao.model_dump(),
                                "dimensao": s.dimensao.model_dump(),
                                "cadeiras": [
                                    {
                                        "id": c.id,
                                        "sala_id": c.sala_id,
                                        "posicao": c.posicao.model_dump(),
                                        "status": c.status.value,
                                        "aluno_ra": c.aluno_ra,
                                        "aluno_nome": c.aluno_nome,
                                    }
                                    for c in s.cadeiras
                                ],
                            }
                            for s in pav.salas
                        ],
                    }
                    for pav in self.state.pavimentos
                ],
                "catracas": [
                    {
                        "id": c.id, "nome": c.nome, "pavimento": c.pavimento.value,
                        "posicao": c.posicao.model_dump(), "online": c.online,
                        "entradas": c.total_entradas_hoje, "saidas": c.total_saidas_hoje,
                    }
                    for c in self.state.catracas.values()
                ],
            }


servico_dashboard = ServicoDashboard(estado)
