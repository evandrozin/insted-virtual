/** Tokens da identidade Insted expostos ao TypeScript e ao Three.js. */
import type { Severidade, StatusCadeira, StatusPresenca } from './types';

export const INSTED = {
  primary: '#00C9B7',
  primaryHover: '#00B4A2',
  dark: '#0d1117',
  darkCard: '#161b22',
  border: '#30363d',
  textLight: '#e6edf3',
  textMuted: '#8b949e',
} as const;

export const COR_CADEIRA: Record<StatusCadeira, string> = {
  LIVRE: '#10B981',
  RESERVADA: '#3B82F6',
  OCUPADA: '#00C9B7',
  ALERT_SOBRELOTACAO: '#EF4444',
};

export const COR_PRESENCA: Record<StatusPresenca, string> = {
  AGUARDANDO: '#8b949e',
  PRESENTE: '#00C9B7',
  ATRASADO: '#F59E0B',
  AUSENTE: '#EF4444',
  EVADIDO: '#A855F7',
};

export const ROTULO_PRESENCA: Record<StatusPresenca, string> = {
  AGUARDANDO: 'Aguardando',
  PRESENTE: 'Presente',
  ATRASADO: 'Atrasado',
  AUSENTE: 'Ausente',
  EVADIDO: 'Evadiu',
};

export const COR_SEVERIDADE: Record<Severidade, string> = {
  INFO: '#3B82F6',
  ATENCAO: '#F59E0B',
  CRITICO: '#EF4444',
};

export const ROTULO_PAVIMENTO: Record<string, string> = {
  TERREO: 'T',
  PAV_1: '1',
  PAV_2: '2',
  TERRACO: '3',
};

/** Verde -> ambar -> vermelho conforme a taxa de presenca cai. */
export function corPorTaxa(taxa: number): string {
  if (taxa >= 80) return INSTED.primary;
  if (taxa >= 60) return '#10B981';
  if (taxa >= 40) return '#F59E0B';
  return '#EF4444';
}

export function horaCurta(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function hhmm(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
