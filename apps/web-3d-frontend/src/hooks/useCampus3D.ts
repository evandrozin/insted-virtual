/**
 * Estado global da maquete e do painel.
 *
 * A geometria (maquete) muda raramente; o status das carteiras muda a cada
 * passagem de catraca. Por isso o status vive em um dicionario plano separado:
 * aplicar um delta e O(1) e nao re-cria a arvore de pavimentos/salas.
 */
import { create } from 'zustand';
import type {
  Dashboard,
  DeltaCadeira,
  DetalheSala,
  EventoCatraca,
  Maquete,
  PavimentoId,
  StatusCadeira,
} from '../lib/types';

export type ModoVisao = 'CAMPUS' | 'PAVIMENTO';

interface Ocupante {
  ra: string | null;
  nome: string | null;
}

interface CampusStore {
  // dados
  maquete: Maquete | null;
  dashboard: Dashboard | null;
  eventos: EventoCatraca[];
  statusCadeiras: Record<string, StatusCadeira>;
  ocupantes: Record<string, Ocupante>;

  // conexao
  conectado: boolean;
  modoRelogio: string;
  servidorEm: string | null;
  ultimoPing: number;

  // ui
  modoVisao: ModoVisao;
  pavimentoSelecionado: PavimentoId;
  salaFoco: string | null;
  detalheSala: DetalheSala | null;
  carregandoDetalhe: boolean;
  salaPiscando: Record<string, number>;

  // acoes
  aplicarSnapshot: (m: Maquete, d: Dashboard, ev: EventoCatraca[], relogio: string, servidor: string) => void;
  aplicarTick: (d: Dashboard, deltas?: DeltaCadeira[], servidor?: string) => void;
  aplicarEvento: (ev: EventoCatraca, deltas: DeltaCadeira[]) => void;
  aplicarMaquete: (m: Maquete) => void;
  setConectado: (v: boolean) => void;
  setModoVisao: (v: ModoVisao) => void;
  selecionarPavimento: (p: PavimentoId) => void;
  abrirSala: (salaId: string) => void;
  setDetalheSala: (d: DetalheSala | null) => void;
  fecharSala: () => void;
}

function indexarMaquete(m: Maquete) {
  const status: Record<string, StatusCadeira> = {};
  const ocupantes: Record<string, Ocupante> = {};
  for (const pav of m.pavimentos) {
    for (const sala of pav.salas) {
      for (const c of sala.cadeiras) {
        status[c.id] = c.status;
        ocupantes[c.id] = { ra: c.aluno_ra, nome: c.aluno_nome };
      }
    }
  }
  return { status, ocupantes };
}

function aplicarDeltas(
  base: Record<string, StatusCadeira>,
  ocupBase: Record<string, Ocupante>,
  deltas: DeltaCadeira[],
) {
  const status = { ...base };
  const ocupantes = { ...ocupBase };
  for (const d of deltas) {
    status[d.cadeira_id] = d.status;
    ocupantes[d.cadeira_id] = { ra: d.aluno_ra, nome: d.aluno_nome };
  }
  return { status, ocupantes };
}

export const useCampus3D = create<CampusStore>((set, get) => ({
  maquete: null,
  dashboard: null,
  eventos: [],
  statusCadeiras: {},
  ocupantes: {},

  conectado: false,
  modoRelogio: '',
  servidorEm: null,
  ultimoPing: 0,

  modoVisao: 'CAMPUS',
  pavimentoSelecionado: 'PAV_1',
  salaFoco: null,
  detalheSala: null,
  carregandoDetalhe: false,
  salaPiscando: {},

  aplicarSnapshot: (maquete, dashboard, eventos, modoRelogio, servidorEm) => {
    const { status, ocupantes } = indexarMaquete(maquete);
    set({
      maquete,
      dashboard,
      eventos: eventos.slice(0, 40),
      statusCadeiras: status,
      ocupantes,
      modoRelogio,
      servidorEm,
      conectado: true,
      ultimoPing: Date.now(),
    });
  },

  aplicarTick: (dashboard, deltas, servidorEm) => {
    const s = get();
    const patch: Partial<CampusStore> = {
      dashboard,
      ultimoPing: Date.now(),
      conectado: true,
    };
    if (servidorEm) patch.servidorEm = servidorEm;
    if (deltas?.length) {
      const r = aplicarDeltas(s.statusCadeiras, s.ocupantes, deltas);
      patch.statusCadeiras = r.status;
      patch.ocupantes = r.ocupantes;
    }
    set(patch);
  },

  aplicarEvento: (evento, deltas) => {
    const s = get();

    // O mesmo evento pode chegar duas vezes: o painel mantem mais de uma
    // conexao viva (reconexao, StrictMode em dev) e o broadcast atinge todas.
    if (s.eventos.some((e) => e.id === evento.id)) return;

    const patch: Partial<CampusStore> = {
      eventos: [evento, ...s.eventos].slice(0, 40),
      ultimoPing: Date.now(),
    };
    if (deltas?.length) {
      const r = aplicarDeltas(s.statusCadeiras, s.ocupantes, deltas);
      patch.statusCadeiras = r.status;
      patch.ocupantes = r.ocupantes;
    }
    // Pisca a sala que recebeu a passagem, para o olho acompanhar o movimento.
    if (evento.sala_id) {
      patch.salaPiscando = { ...s.salaPiscando, [evento.sala_id]: Date.now() };
    }
    set(patch);
  },

  aplicarMaquete: (maquete) => {
    const { status, ocupantes } = indexarMaquete(maquete);
    set({ maquete, statusCadeiras: status, ocupantes });
  },

  setConectado: (conectado) => set({ conectado }),
  setModoVisao: (modoVisao) => set({ modoVisao }),

  selecionarPavimento: (pavimentoSelecionado) =>
    set({ pavimentoSelecionado, modoVisao: 'PAVIMENTO' }),

  abrirSala: (salaFoco) => set({ salaFoco, carregandoDetalhe: true, detalheSala: null }),
  setDetalheSala: (detalheSala) => set({ detalheSala, carregandoDetalhe: false }),
  fecharSala: () => set({ salaFoco: null, detalheSala: null, carregandoDetalhe: false }),
}));

/** Seletor memoizavel: ocupacao de uma sala especifica. */
export function useOcupacaoSala(salaId: string | null) {
  return useCampus3D((s) =>
    salaId ? s.dashboard?.ocupacao_salas.find((o) => o.sala_id === salaId) ?? null : null,
  );
}
