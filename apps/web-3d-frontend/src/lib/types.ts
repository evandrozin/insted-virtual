/** Contratos espelhando os modelos Pydantic do backend. */

export type StatusCadeira =
  | 'LIVRE'
  | 'RESERVADA'
  | 'OCUPADA'
  | 'ALERT_SOBRELOTACAO';

export type StatusPresenca =
  | 'AGUARDANDO'
  | 'PRESENTE'
  | 'ATRASADO'
  | 'AUSENTE'
  | 'EVADIDO';

export type PavimentoId = 'TERREO' | 'PAV_1' | 'PAV_2' | 'TERRACO';

export type Severidade = 'INFO' | 'ATENCAO' | 'CRITICO';

export interface Posicao3D {
  x: number;
  y: number;
  z: number;
}

export interface Cadeira {
  id: string;
  sala_id: string;
  posicao: Posicao3D;
  status: StatusCadeira;
  aluno_ra: string | null;
  aluno_nome: string | null;
}

export interface Sala {
  id: string;
  nome: string;
  tipo: string;
  capacidade: number;
  rack_id: string | null;
  posicao: Posicao3D;
  dimensao: { largura: number; altura: number; profundidade: number };
  cadeiras: Cadeira[];
}

export interface Pavimento {
  id: PavimentoId;
  nome: string;
  ordem: number;
  altura_y: number;
  descricao: string;
  salas: Sala[];
}

export interface Catraca {
  id: string;
  nome: string;
  pavimento: PavimentoId;
  posicao: Posicao3D;
  online: boolean;
  entradas: number;
  saidas: number;
}

export interface Maquete {
  pavimentos: Pavimento[];
  catracas: Catraca[];
}

export interface KPIs {
  atualizado_em: string;
  alunos_no_campus: number;
  alunos_esperados_agora: number;
  presentes_em_aula: number;
  taxa_presenca_geral: number;
  taxa_presenca_variacao: number;
  atrasados: number;
  ausentes: number;
  evasao_em_aula: number;
  salas_em_aula: number;
  salas_ociosas: number;
  capacidade_total: number;
  taxa_ocupacao_campus: number;
  catracas_online: number;
  catracas_total: number;
  fluxo_ultima_hora: number;
}

export interface OcupacaoSala {
  sala_id: string;
  sala_nome: string;
  pavimento: PavimentoId;
  capacidade: number;
  esperados: number;
  presentes: number;
  atrasados: number;
  ausentes: number;
  evadidos: number;
  disciplina: string | null;
  professor: string | null;
  turma_id: string | null;
  aula_id: string | null;
  inicio: string | null;
  fim: string | null;
  em_aula: boolean;
}

export interface OcupacaoPavimento {
  pavimento: PavimentoId;
  nome: string;
  capacidade: number;
  presentes: number;
  esperados: number;
  salas_em_aula: number;
  taxa_presenca: number;
}

export interface Alerta {
  id: string;
  tipo: string;
  severidade: Severidade;
  titulo: string;
  detalhe: string;
  sala_id: string | null;
  pavimento: PavimentoId | null;
  criado_em: string;
}

export interface PontoSerie {
  hora: string;
  presentes: number;
  esperados: number;
  taxa: number;
}

export interface RankingCurso {
  curso: string;
  esperados: number;
  presentes: number;
  atrasados: number;
  taxa: number;
}

export interface Dashboard {
  kpis: KPIs;
  ocupacao_salas: OcupacaoSala[];
  ocupacao_pavimentos: OcupacaoPavimento[];
  serie_presenca: PontoSerie[];
  alertas: Alerta[];
  ranking_cursos: RankingCurso[];
}

export interface EventoCatraca {
  id: string;
  ra: string;
  nome: string | null;
  curso: string | null;
  turma_id: string | null;
  catraca_id: string;
  direcao: 'ENTRADA' | 'SAIDA';
  situacao: string;
  sala_id: string | null;
  sala_nome: string | null;
  disciplina: string | null;
  timestamp: string;
}

export interface DeltaCadeira {
  cadeira_id: string;
  sala_id: string;
  status: StatusCadeira;
  aluno_ra: string | null;
  aluno_nome: string | null;
}

/** Mensagens recebidas pelo WebSocket /ws/campus. */
export type MensagemSocket =
  | {
      tipo: 'SNAPSHOT_INICIAL';
      servidor_em: string;
      modo_relogio: string;
      maquete: Maquete;
      dashboard: Dashboard;
      eventos: EventoCatraca[];
    }
  | { tipo: 'DASHBOARD_TICK'; servidor_em?: string; dashboard: Dashboard; deltas?: DeltaCadeira[] }
  | { tipo: 'EVENTO_CATRACA'; evento: EventoCatraca; deltas: DeltaCadeira[] }
  | { tipo: 'REALOCACAO'; turma_id: string; sala_origem: string | null; sala_destino: string; maquete: Maquete }
  | { tipo: 'PONG' }
  | { tipo: 'ERRO'; detalhe: string };

/** Detalhe de sala (drill-down ao clicar na maquete). */
export interface DetalheSala {
  sala: {
    id: string;
    nome: string;
    tipo: string;
    pavimento: PavimentoId;
    capacidade: number;
    rack_id: string | null;
  };
  aula: {
    id: string;
    disciplina: string;
    professor: string;
    turma_id: string;
    inicio: string;
    fim: string;
  } | null;
  chamada: Array<{
    ra: string;
    nome: string;
    status: StatusPresenca;
    cadeira_id: string | null;
    entrada_em: string | null;
    atraso_minutos: number;
    catraca_origem: string | null;
  }>;
}
