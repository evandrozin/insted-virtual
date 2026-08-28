import React from 'react';
import { useCampus3D } from '../hooks/useCampus3D';
import { ROTULO_PAVIMENTO, corPorTaxa } from '../lib/theme';

/**
 * Trilho de pavimentos (Terreo -> Terraco). Alem de navegar, cada botao
 * funciona como um mini-indicador: a barra inferior e a taxa de presenca
 * daquele andar agora.
 */
export const FloorMap: React.FC = () => {
  const maquete = useCampus3D((s) => s.maquete);
  const dashboard = useCampus3D((s) => s.dashboard);
  const modoVisao = useCampus3D((s) => s.modoVisao);
  const selecionado = useCampus3D((s) => s.pavimentoSelecionado);
  const selecionarPavimento = useCampus3D((s) => s.selecionarPavimento);
  const setModoVisao = useCampus3D((s) => s.setModoVisao);

  if (!maquete) return <aside className="floor-rail" />;

  const porPavimento = Object.fromEntries(
    (dashboard?.ocupacao_pavimentos ?? []).map((p) => [p.pavimento, p]),
  );

  // Do terraco para o terreo: a pilha na tela espelha o predio real.
  const ordenados = [...maquete.pavimentos].sort((a, b) => b.ordem - a.ordem);

  return (
    <aside className="floor-rail">
      <div className="rail-label">Pavimento</div>

      {ordenados.map((pav) => {
        const info = porPavimento[pav.id];
        const taxa = info?.taxa_presenca ?? 0;
        const ativo = modoVisao === 'PAVIMENTO' && selecionado === pav.id;

        return (
          <button
            key={pav.id}
            className={`floor-btn ${ativo ? 'active' : ''}`}
            onClick={() => selecionarPavimento(pav.id)}
            title={`${pav.nome} — ${pav.descricao}`}
          >
            <div className="floor-btn-code">{ROTULO_PAVIMENTO[pav.id] ?? pav.ordem}</div>
            <div className="floor-btn-rate">
              {info?.salas_em_aula ? `${taxa.toFixed(0)}%` : '—'}
            </div>
            <i
              className="floor-btn-bar"
              style={{
                width: `${Math.min(100, taxa)}%`,
                background: info?.salas_em_aula ? corPorTaxa(taxa) : 'transparent',
              }}
            />
          </button>
        );
      })}

      <button
        className={`floor-btn ${modoVisao === 'CAMPUS' ? 'active' : ''}`}
        onClick={() => setModoVisao('CAMPUS')}
        title="Visao geral do campus (4 pavimentos)"
        style={{ marginTop: 6 }}
      >
        <div className="floor-btn-code" style={{ fontSize: 12 }}>
          ALL
        </div>
        <div className="floor-btn-rate">campus</div>
      </button>
    </aside>
  );
};
