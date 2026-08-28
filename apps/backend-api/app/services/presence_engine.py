"""Motor de presenca em tempo real.

Cruza tres fontes:
  1. Grade horaria e matriculas do JACAD  (quem deveria estar, onde e quando)
  2. Passagens de catraca                 (quem efetivamente entrou/saiu)
  3. Topologia da maquete 3D              (qual carteira representa esse aluno)

e produz o estado consolidado que alimenta a maquete e o painel da diretoria.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.core import clock
from app.core.config import settings
from app.models.academico import AulaModel, EventoCatraca, RegistroPresenca
from app.models.dashboard import Alerta
from app.models.enums import (
    DirecaoCatraca,
    SeveridadeAlerta,
    StatusCadeira,
    StatusPresenca,
    TipoAlerta,
)
from app.services.allocation_engine import EngineAlocacaoInsted
from app.services.campus_state import CampusState, estado
from app.services.jacad_client import obter_client

TOLERANCIA = timedelta(minutes=settings.TOLERANCIA_ATRASO_MIN)
JANELA_CHEGADA = timedelta(minutes=settings.JANELA_CHEGADA_ANTECIPADA_MIN)


def _dt_na_data(base: datetime, hora) -> datetime:
    return datetime.combine(base.date(), hora)


class MotorPresenca:
    def __init__(self, state: CampusState) -> None:
        self.state = state

    # ------------------------------------------------------------------
    # Sincronizacao com o ERP
    # ------------------------------------------------------------------
    def sincronizar_jacad(self) -> dict:
        client = obter_client()
        alunos = client.listar_alunos()
        turmas = client.listar_turmas()
        aulas = client.listar_grade_horaria()
        self.state.carregar_academico(alunos, turmas, aulas)
        return {
            "alunos": len(alunos),
            "turmas": len(turmas),
            "aulas": len(aulas),
            "sincronizado_em": self.state.ultima_sync_jacad.isoformat(),
        }

    # ------------------------------------------------------------------
    # Ciclo de vida das aulas
    # ------------------------------------------------------------------
    def _aulas_da_janela(self, agora: datetime) -> List[AulaModel]:
        """Aulas que devem estar abertas: em andamento ou aceitando chegadas."""
        dia = agora.weekday()
        abertas: List[AulaModel] = []
        for aula in self.state.aulas.values():
            if aula.dia_semana != dia:
                continue
            inicio = _dt_na_data(agora, aula.hora_inicio)
            fim = _dt_na_data(agora, aula.hora_fim)
            if inicio - JANELA_CHEGADA <= agora <= fim:
                abertas.append(aula)
        return abertas

    def reconciliar(self, agora: Optional[datetime] = None) -> List[dict]:
        """Abre aulas novas, encerra as vencidas e promove ausencias.

        Devolve a lista de deltas de carteira para o broadcast incremental.
        """
        agora = agora or clock.agora()
        deltas: List[dict] = []

        with self.state.lock:
            esperadas = {a.id for a in self._aulas_da_janela(agora)}

            for aula_id in esperadas - self.state.aulas_ativas:
                deltas.extend(self._abrir_aula(self.state.aulas[aula_id], agora))

            for aula_id in list(self.state.aulas_ativas - esperadas):
                deltas.extend(self._encerrar_aula(self.state.aulas[aula_id], agora))

            deltas.extend(self._marcar_ausencias(agora))
            self._avaliar_alertas(agora)
            self._amostrar_serie(agora)

        return deltas

    def _abrir_aula(self, aula: AulaModel, agora: datetime) -> List[dict]:
        """Cria os registros de presenca e reserva as carteiras (azul)."""
        sala = self.state.sala(aula.sala_id)
        turma = self.state.turmas.get(aula.turma_id)
        if sala is None or turma is None:
            return []

        matriculados = [
            {"ra": ra, "nome": self.state.alunos[ra].nome}
            for ra in turma.alunos_ra
            if ra in self.state.alunos
        ]

        engine = EngineAlocacaoInsted(sala.cadeiras)
        alocacoes = engine.alocar_turma(matriculados)

        for aluno in matriculados:
            ra = aluno["ra"]
            cadeira = alocacoes.get(ra)
            self.state.presencas[(aula.id, ra)] = RegistroPresenca(
                aula_id=aula.id,
                aluno_ra=ra,
                aluno_nome=aluno["nome"],
                turma_id=aula.turma_id,
                sala_id=aula.sala_id,
                disciplina=aula.disciplina,
                status=StatusPresenca.AGUARDANDO,
                cadeira_id=cadeira.id if cadeira else None,
            )
            if cadeira:
                self.state.cadeira_por_aluno[ra] = cadeira.id

        self.state.aulas_ativas.add(aula.id)

        # Alunos ja dentro do campus entram direto como presentes.
        deltas: List[dict] = []
        for aluno in matriculados:
            if aluno["ra"] in self.state.alunos_no_campus:
                delta = self._promover_para_ocupada(aula, aluno["ra"], agora, "PRE_CAMPUS")
                if delta:
                    deltas.append(delta)

        deltas.extend(self._delta_sala(sala.id))
        return deltas

    def _encerrar_aula(self, aula: AulaModel, agora: datetime) -> List[dict]:
        sala = self.state.sala(aula.sala_id)
        if sala is None:
            return []

        for registro in self.state.presencas_da_aula(aula.id):
            if registro.status == StatusPresenca.AGUARDANDO:
                registro.status = StatusPresenca.AUSENTE
            self.state.cadeira_por_aluno.pop(registro.aluno_ra, None)

        EngineAlocacaoInsted(sala.cadeiras).liberar_sala()
        self.state.aulas_ativas.discard(aula.id)
        self.state.limpar_dedupe_alertas([f"{aula.id}:"])
        return self._delta_sala(sala.id)

    def _marcar_ausencias(self, agora: datetime) -> List[dict]:
        """Passada a tolerancia, quem nao chegou deixa de estar AGUARDANDO."""
        deltas: List[dict] = []
        for aula_id in self.state.aulas_ativas:
            aula = self.state.aulas[aula_id]
            limite = _dt_na_data(agora, aula.hora_inicio) + TOLERANCIA
            if agora < limite:
                continue
            for registro in self.state.presencas_da_aula(aula_id):
                if registro.status == StatusPresenca.AGUARDANDO:
                    registro.status = StatusPresenca.AUSENTE
        return deltas

    # ------------------------------------------------------------------
    # Eventos de catraca
    # ------------------------------------------------------------------
    def processar_evento(self, evento: EventoCatraca) -> dict:
        """Caminho quente. Devolve o pacote pronto para broadcast."""
        agora = evento.timestamp or clock.agora()

        with self.state.lock:
            catraca = self.state.catracas.get(evento.catraca_id)
            if catraca:
                catraca.online = True
                catraca.ultimo_evento_em = agora.isoformat()
                if evento.direcao == DirecaoCatraca.ENTRADA:
                    catraca.total_entradas_hoje += 1
                else:
                    catraca.total_saidas_hoje += 1

            aluno = self.state.alunos.get(evento.ra)
            if aluno is None:
                self._alerta(
                    TipoAlerta.RA_DESCONHECIDO,
                    SeveridadeAlerta.ATENCAO,
                    "RA nao localizado no JACAD",
                    f"RA {evento.ra} passou em {evento.catraca_id} sem matricula ativa.",
                    agora,
                    dedupe=f"ra_desconhecido:{evento.ra}",
                )
                pacote = self._pacote_evento(evento, agora, None, None, "RA_DESCONHECIDO")
                self.state.registrar_evento_feed(pacote)
                return {"tipo": "EVENTO_CATRACA", "evento": pacote, "deltas": []}

            if evento.direcao == DirecaoCatraca.ENTRADA:
                return self._tratar_entrada(evento, aluno, agora)
            return self._tratar_saida(evento, aluno, agora)

    def _tratar_entrada(self, evento, aluno, agora: datetime) -> dict:
        self.state.alunos_no_campus.add(aluno.ra)
        self.state.total_entradas += 1

        aula = self._aula_alvo(aluno.ra, agora)
        deltas: List[dict] = []
        situacao = "NO_CAMPUS"

        if aula is not None:
            delta = self._promover_para_ocupada(aula, aluno.ra, agora, evento.catraca_id)
            registro = self.state.presencas.get((aula.id, aluno.ra))
            situacao = registro.status.value if registro else "NO_CAMPUS"
            if delta:
                deltas.append(delta)

        pacote = self._pacote_evento(evento, agora, aluno, aula, situacao)
        self.state.registrar_evento_feed(pacote)
        return {"tipo": "EVENTO_CATRACA", "evento": pacote, "deltas": deltas}

    def _tratar_saida(self, evento, aluno, agora: datetime) -> dict:
        self.state.alunos_no_campus.discard(aluno.ra)
        self.state.total_saidas += 1

        aula = self._aula_alvo(aluno.ra, agora, apenas_em_andamento=True)
        deltas: List[dict] = []
        situacao = "SAIU"

        if aula is not None:
            registro = self.state.presencas.get((aula.id, aluno.ra))
            fim = _dt_na_data(agora, aula.hora_fim)
            restante = (fim - agora).total_seconds() / 60

            if registro and registro.status in (
                StatusPresenca.PRESENTE,
                StatusPresenca.ATRASADO,
            ):
                registro.saida_em = agora
                # Sair faltando mais de 10 min para o fim caracteriza evasao.
                if restante > 10:
                    registro.status = StatusPresenca.EVADIDO
                    situacao = StatusPresenca.EVADIDO.value

                    sala = self.state.sala(aula.sala_id)
                    if sala:
                        cadeira = EngineAlocacaoInsted(
                            sala.cadeiras
                        ).registrar_saida_catraca(aluno.ra)
                        if cadeira:
                            deltas.append(self._delta_cadeira(cadeira))
                else:
                    situacao = "SAIDA_FIM_AULA"

        self.state.cadeira_por_aluno.pop(aluno.ra, None)
        pacote = self._pacote_evento(evento, agora, aluno, aula, situacao)
        self.state.registrar_evento_feed(pacote)
        return {"tipo": "EVENTO_CATRACA", "evento": pacote, "deltas": deltas}

    def _promover_para_ocupada(
        self, aula: AulaModel, ra: str, agora: datetime, catraca_id: str
    ) -> Optional[dict]:
        registro = self.state.presencas.get((aula.id, ra))
        if registro is None:
            return None

        inicio = _dt_na_data(agora, aula.hora_inicio)
        atraso = int(max(0, (agora - inicio).total_seconds() // 60))

        registro.entrada_em = agora
        registro.catraca_origem = catraca_id
        registro.atraso_minutos = atraso
        registro.status = (
            StatusPresenca.ATRASADO
            if agora > inicio + TOLERANCIA
            else StatusPresenca.PRESENTE
        )

        sala = self.state.sala(aula.sala_id)
        if sala is None:
            return None

        cadeira = EngineAlocacaoInsted(sala.cadeiras).registrar_entrada_catraca(ra, agora)
        if cadeira is None:
            return None

        cadeira.aluno_nome = registro.aluno_nome
        registro.cadeira_id = cadeira.id
        self.state.cadeira_por_aluno[ra] = cadeira.id
        return self._delta_cadeira(cadeira)

    def _aula_alvo(
        self, ra: str, agora: datetime, apenas_em_andamento: bool = False
    ) -> Optional[AulaModel]:
        """Resolve em qual aula ativa esse RA deve ser contabilizado."""
        candidatas: List[Tuple[int, AulaModel]] = []
        for aula in self.state.aulas_do_aluno(ra):
            if aula.id not in self.state.aulas_ativas:
                continue
            inicio = _dt_na_data(agora, aula.hora_inicio)
            fim = _dt_na_data(agora, aula.hora_fim)
            em_andamento = inicio <= agora <= fim
            if apenas_em_andamento and not em_andamento:
                continue
            # Aula em curso tem prioridade sobre a proxima da grade.
            candidatas.append((0 if em_andamento else 1, aula))

        if not candidatas:
            return None
        candidatas.sort(key=lambda par: (par[0], par[1].hora_inicio))
        return candidatas[0][1]

    # ------------------------------------------------------------------
    # Alertas
    # ------------------------------------------------------------------
    def _alerta(
        self,
        tipo: TipoAlerta,
        severidade: SeveridadeAlerta,
        titulo: str,
        detalhe: str,
        agora: datetime,
        sala_id: Optional[str] = None,
        dedupe: Optional[str] = None,
    ) -> None:
        alerta = Alerta(
            id=str(uuid.uuid4()),
            tipo=tipo,
            severidade=severidade,
            titulo=titulo,
            detalhe=detalhe,
            sala_id=sala_id,
            pavimento=self.state.pavimento_da_sala(sala_id) if sala_id else None,
            criado_em=agora,
        )
        self.state.registrar_alerta(alerta, dedupe)

    def _avaliar_alertas(self, agora: datetime) -> None:
        for aula_id in self.state.aulas_ativas:
            aula = self.state.aulas[aula_id]
            sala = self.state.sala(aula.sala_id)
            if sala is None:
                continue

            inicio = _dt_na_data(agora, aula.hora_inicio)
            if agora < inicio + TOLERANCIA:
                continue  # so avalia depois da tolerancia de entrada

            registros = self.state.presencas_da_aula(aula_id)
            if not registros:
                continue

            presentes = sum(
                1 for r in registros
                if r.status in (StatusPresenca.PRESENTE, StatusPresenca.ATRASADO)
            )
            evadidos = sum(1 for r in registros if r.status == StatusPresenca.EVADIDO)
            esperados = len(registros)
            taxa = 100 * presentes / esperados if esperados else 0

            if presentes > sala.capacidade:
                self._alerta(
                    TipoAlerta.SOBRELOTACAO, SeveridadeAlerta.CRITICO,
                    f"Sobrelotacao em {sala.nome}",
                    f"{presentes} presentes para {sala.capacidade} carteiras "
                    f"({aula.disciplina} / {aula.turma_id}).",
                    agora, sala.id, dedupe=f"{aula_id}:sobrelotacao",
                )
            elif presentes == 0:
                self._alerta(
                    TipoAlerta.SALA_VAZIA, SeveridadeAlerta.CRITICO,
                    f"Aula sem alunos em {sala.nome}",
                    f"{aula.disciplina} com {aula.professor}: nenhum dos "
                    f"{esperados} matriculados registrou entrada.",
                    agora, sala.id, dedupe=f"{aula_id}:vazia",
                )
            elif taxa < settings.LIMIAR_BAIXA_PRESENCA:
                self._alerta(
                    TipoAlerta.BAIXA_PRESENCA, SeveridadeAlerta.ATENCAO,
                    f"Presenca de {taxa:.0f}% em {sala.nome}",
                    f"{presentes} de {esperados} em {aula.disciplina} "
                    f"({aula.turma_id}, {aula.professor}).",
                    agora, sala.id, dedupe=f"{aula_id}:baixa",
                )

            if evadidos >= 3:
                self._alerta(
                    TipoAlerta.EVASAO_AULA, SeveridadeAlerta.ATENCAO,
                    f"Evasao durante a aula em {sala.nome}",
                    f"{evadidos} alunos deixaram o campus antes do fim de "
                    f"{aula.disciplina}.",
                    agora, sala.id, dedupe=f"{aula_id}:evasao:{evadidos // 3}",
                )

        self._avaliar_catracas(agora)

    def _avaliar_catracas(self, agora: datetime) -> None:
        limite = timedelta(seconds=settings.CATRACA_TIMEOUT_S)
        for catraca in self.state.catracas.values():
            if not catraca.ultimo_evento_em:
                continue
            ultimo = datetime.fromisoformat(catraca.ultimo_evento_em)
            if agora - ultimo > limite:
                catraca.online = False
                self._alerta(
                    TipoAlerta.CATRACA_OFFLINE, SeveridadeAlerta.CRITICO,
                    f"{catraca.nome} sem comunicacao",
                    f"Nenhuma passagem registrada desde {ultimo.strftime('%H:%M')}.",
                    agora, dedupe=f"catraca_off:{catraca.id}:{ultimo.strftime('%H%M')}",
                )

    # ------------------------------------------------------------------
    # Serie temporal
    # ------------------------------------------------------------------
    def _amostrar_serie(self, agora: datetime) -> None:
        """Agrega presenca em janelas de 30 minutos para o grafico da diretoria."""
        minuto = 0 if agora.minute < 30 else 30
        chave = f"{agora.hour:02d}:{minuto:02d}"

        esperados = 0
        presentes = 0
        for aula_id in self.state.aulas_ativas:
            aula = self.state.aulas[aula_id]
            if not aula.em_andamento(agora):
                continue
            registros = self.state.presencas_da_aula(aula_id)
            esperados += len(registros)
            presentes += sum(
                1 for r in registros
                if r.status in (StatusPresenca.PRESENTE, StatusPresenca.ATRASADO)
            )

        self.state.serie_presenca[chave] = {
            "hora": chave,
            "presentes": presentes,
            "esperados": esperados,
            "taxa": round(100 * presentes / esperados, 1) if esperados else 0.0,
        }

    # ------------------------------------------------------------------
    # Deltas de renderizacao
    # ------------------------------------------------------------------
    def _delta_cadeira(self, cadeira) -> dict:
        return {
            "cadeira_id": cadeira.id,
            "sala_id": cadeira.sala_id,
            "status": cadeira.status.value,
            "aluno_ra": cadeira.aluno_ra,
            "aluno_nome": cadeira.aluno_nome,
        }

    def _delta_sala(self, sala_id: str) -> List[dict]:
        sala = self.state.sala(sala_id)
        if sala is None:
            return []
        return [self._delta_cadeira(c) for c in sala.cadeiras]

    def _pacote_evento(self, evento, agora, aluno, aula, situacao: str) -> dict:
        sala = self.state.sala(aula.sala_id) if aula else None
        return {
            "id": str(uuid.uuid4()),
            "ra": evento.ra,
            "nome": aluno.nome if aluno else None,
            "curso": aluno.curso if aluno else None,
            "turma_id": aluno.turma_id if aluno else None,
            "catraca_id": evento.catraca_id,
            "direcao": evento.direcao.value,
            "situacao": situacao,
            "sala_id": sala.id if sala else None,
            "sala_nome": sala.nome if sala else None,
            "disciplina": aula.disciplina if aula else None,
            "timestamp": agora.isoformat(),
        }


motor = MotorPresenca(estado)
