import React from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { corPorTaxa } from '../../lib/theme';
import type { OcupacaoSala } from '../../lib/types';

interface Props {
  salas: OcupacaoSala[];
}

/**
 * Salas em aula ordenadas pela pior presenca. E a lista que a diretoria usa
 * para agir: clicar leva direto a chamada nominal daquela sala.
 */
export const RoomRanking: React.FC<Props> = ({ salas }) => {
  const abrirSala = useCampus3D((s) => s.abrirSala);
  const emAula = salas.filter((s) => s.em_aula);

  return (
    <div className="panel-card">
      <div className="section-title">
        Salas em aula · atenção primeiro
        <span className="count">{emAula.length}</span>
      </div>

      {emAula.length === 0 ? (
        <div className="empty-state">Nenhuma aula em andamento neste horário.</div>
      ) : (
        emAula.slice(0, 8).map((s) => {
          const presentes = s.presentes + s.atrasados;
          const taxa = s.esperados ? (100 * presentes) / s.esperados : 0;
          const cor = corPorTaxa(taxa);

          return (
            <div key={s.sala_id} className="room-row" onClick={() => abrirSala(s.sala_id)}>
              <div>
                <div className="room-name">{s.sala_nome}</div>
                <div className="room-meta">
                  {s.disciplina} · {s.turma_id} · {s.inicio}–{s.fim}
                </div>
              </div>
              <div>
                <div className="room-rate" style={{ color: cor }}>
                  {taxa.toFixed(0)}%
                </div>
                <div className="room-count">
                  {presentes}/{s.esperados}
                  {s.atrasados > 0 && ` · ${s.atrasados} atr.`}
                </div>
              </div>
              <div className="room-bar">
                <i style={{ width: `${Math.min(100, taxa)}%`, background: cor }} />
              </div>
            </div>
          );
        })
      )}
    </div>
  );
};
