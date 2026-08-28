import React from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { horaCurta } from '../../lib/theme';
import type { EventoCatraca } from '../../lib/types';

const CORES_SITUACAO: Record<string, { bg: string; fg: string; texto: string }> = {
  PRESENTE: { bg: 'rgba(0,201,183,.18)', fg: '#00C9B7', texto: 'presente' },
  ATRASADO: { bg: 'rgba(245,158,11,.18)', fg: '#F59E0B', texto: 'atrasado' },
  EVADIDO: { bg: 'rgba(168,85,247,.18)', fg: '#A855F7', texto: 'evadiu' },
  SAIDA_FIM_AULA: { bg: 'rgba(139,148,158,.16)', fg: '#8b949e', texto: 'saída' },
  SAIU: { bg: 'rgba(139,148,158,.16)', fg: '#8b949e', texto: 'saída' },
  NO_CAMPUS: { bg: 'rgba(59,130,246,.18)', fg: '#3B82F6', texto: 'no campus' },
  PRE_CAMPUS: { bg: 'rgba(59,130,246,.18)', fg: '#3B82F6', texto: 'no campus' },
  RA_DESCONHECIDO: { bg: 'rgba(239,68,68,.18)', fg: '#EF4444', texto: 'RA inválido' },
};

function primeiroENome(nome: string | null): string {
  if (!nome) return 'RA não identificado';
  const partes = nome.split(' ');
  return partes.length > 1 ? `${partes[0]} ${partes[partes.length - 1]}` : partes[0];
}

/** Esteira de passagens de catraca em tempo real, no rodape do painel. */
export const EventTicker: React.FC = () => {
  const eventos = useCampus3D((s) => s.eventos);

  return (
    <footer className="ticker">
      <div className="ticker-label">
        <span className="live-dot" style={{ background: 'var(--insted-primary)' }} />
        Catracas
      </div>

      <div className="ticker-track">
        {eventos.length === 0 && (
          <span style={{ fontSize: 12, color: 'var(--insted-text-muted)' }}>
            Aguardando passagens…
          </span>
        )}

        {eventos.slice(0, 14).map((e: EventoCatraca) => {
          const estilo = CORES_SITUACAO[e.situacao] ?? CORES_SITUACAO.NO_CAMPUS;
          return (
            <div key={e.id} className="ticker-item">
              <span
                className="ticker-badge"
                style={{ background: estilo.bg, color: estilo.fg }}
              >
                {estilo.texto}
              </span>
              <span className="ticker-time">{horaCurta(e.timestamp)}</span>
              <span className="ticker-name">{primeiroENome(e.nome)}</span>
              {e.sala_nome && <span className="ticker-where">→ {e.sala_nome}</span>}
            </div>
          );
        })}
      </div>
    </footer>
  );
};
