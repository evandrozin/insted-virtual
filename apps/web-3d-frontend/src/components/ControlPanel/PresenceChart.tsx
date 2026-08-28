import React, { useMemo } from 'react';
import type { PontoSerie } from '../../lib/types';
import { INSTED } from '../../lib/theme';

interface Props {
  serie: PontoSerie[];
}

const L = 6;
const R = 6;
const T = 8;
const B = 6;
const W = 340;
const H = 108;

/**
 * Curva intradiaria da taxa de presenca (janelas de 30 min).
 * SVG puro: sem dependencia de biblioteca de grafico e sem custo de bundle.
 */
export const PresenceChart: React.FC<Props> = ({ serie }) => {
  const { linha, area, pontos, ultimo } = useMemo(() => {
    if (serie.length === 0) {
      return { linha: '', area: '', pontos: [] as Array<{ x: number; y: number; p: PontoSerie }>, ultimo: null };
    }

    const largura = W - L - R;
    const altura = H - T - B;
    const passo = serie.length > 1 ? largura / (serie.length - 1) : 0;

    const coords = serie.map((p, i) => ({
      x: L + i * passo,
      y: T + altura - (Math.min(100, Math.max(0, p.taxa)) / 100) * altura,
      p,
    }));

    const d = coords
      .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
      .join(' ');

    const areaPath =
      coords.length > 1
        ? `${d} L ${coords[coords.length - 1].x.toFixed(1)} ${H - B} L ${coords[0].x.toFixed(1)} ${H - B} Z`
        : '';

    return { linha: d, area: areaPath, pontos: coords, ultimo: coords[coords.length - 1] };
  }, [serie]);

  if (serie.length === 0) {
    return (
      <div className="chart-card">
        <div className="section-title">Curva de presença — hoje</div>
        <div className="empty-state">Aguardando o primeiro bloco de aulas.</div>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="section-title">
        Curva de presença — hoje
        <span className="count">{serie[serie.length - 1].taxa.toFixed(0)}%</span>
      </div>

      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="grad-presenca" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={INSTED.primary} stopOpacity="0.42" />
            <stop offset="100%" stopColor={INSTED.primary} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Linhas-guia de 25 / 50 / 75% */}
        {[0.25, 0.5, 0.75].map((f) => {
          const y = T + (H - T - B) * (1 - f);
          return (
            <line
              key={f}
              x1={L}
              x2={W - R}
              y1={y}
              y2={y}
              stroke="#30363d"
              strokeWidth="1"
              strokeDasharray="3 4"
              opacity={0.55}
            />
          );
        })}

        {area && <path d={area} fill="url(#grad-presenca)" />}
        {linha && (
          <path
            d={linha}
            fill="none"
            stroke={INSTED.primary}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}

        {pontos.map((c) => (
          <circle key={c.p.hora} cx={c.x} cy={c.y} r="2.2" fill={INSTED.primary} opacity={0.75}>
            <title>{`${c.p.hora} — ${c.p.taxa}% (${c.p.presentes}/${c.p.esperados})`}</title>
          </circle>
        ))}

        {ultimo && (
          <circle cx={ultimo.x} cy={ultimo.y} r="4" fill={INSTED.primary}>
            <animate
              attributeName="opacity"
              values="1;0.35;1"
              dur="1.8s"
              repeatCount="indefinite"
            />
          </circle>
        )}
      </svg>

      <div className="chart-axis">
        <span>{serie[0].hora}</span>
        {serie.length > 2 && <span>{serie[Math.floor(serie.length / 2)].hora}</span>}
        <span>{serie[serie.length - 1].hora}</span>
      </div>
    </div>
  );
};
