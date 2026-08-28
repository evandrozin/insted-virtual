import React from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { COR_SEVERIDADE, hhmm } from '../../lib/theme';
import type { Alerta } from '../../lib/types';

interface Props {
  alertas: Alerta[];
}

/** Fila de excecoes operacionais: sobrelotacao, sala vazia, evasao, catraca off. */
export const AlertFeed: React.FC<Props> = ({ alertas }) => {
  const abrirSala = useCampus3D((s) => s.abrirSala);

  return (
    <div className="panel-card">
      <div className="section-title">
        Alertas operacionais
        <span className="count">{alertas.length}</span>
      </div>

      {alertas.length === 0 ? (
        <div className="empty-state">Nenhuma ocorrencia. Operacao dentro do esperado.</div>
      ) : (
        alertas.slice(0, 7).map((a) => (
          <div
            key={a.id}
            className="alert-row"
            style={{ cursor: a.sala_id ? 'pointer' : 'default' }}
            onClick={() => a.sala_id && abrirSala(a.sala_id)}
          >
            <i className="alert-bar" style={{ background: COR_SEVERIDADE[a.severidade] }} />
            <div className="alert-body">
              <div className="alert-title">{a.titulo}</div>
              <div className="alert-detail">{a.detalhe}</div>
            </div>
            <div className="alert-time">{hhmm(a.criado_em)}</div>
          </div>
        ))
      )}
    </div>
  );
};
