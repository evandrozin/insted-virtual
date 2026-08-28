import React, { useEffect } from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { COR_PRESENCA, ROTULO_PRESENCA, hhmm } from '../../lib/theme';
import { buscarDetalheSala } from '../../lib/api';
import type { StatusPresenca } from '../../lib/types';

const ORDEM: StatusPresenca[] = ['PRESENTE', 'ATRASADO', 'EVADIDO', 'AUSENTE', 'AGUARDANDO'];

/**
 * Drill-down da sala: a chamada nominal por tras do numero agregado.
 * Aberto ao clicar em uma sala na maquete, no ranking ou em um alerta.
 */
export const RoomDrawer: React.FC = () => {
  const salaFoco = useCampus3D((s) => s.salaFoco);
  const detalhe = useCampus3D((s) => s.detalheSala);
  const carregando = useCampus3D((s) => s.carregandoDetalhe);
  const setDetalhe = useCampus3D((s) => s.setDetalheSala);
  const fechar = useCampus3D((s) => s.fecharSala);
  // Re-busca a chamada a cada tick do dashboard, mantendo o drawer vivo.
  const carimbo = useCampus3D((s) => s.dashboard?.kpis.atualizado_em);

  useEffect(() => {
    if (!salaFoco) return;
    let cancelado = false;
    buscarDetalheSala(salaFoco)
      .then((d) => !cancelado && setDetalhe(d))
      .catch(() => !cancelado && setDetalhe(null));
    return () => {
      cancelado = true;
    };
  }, [salaFoco, carimbo, setDetalhe]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && fechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [fechar]);

  if (!salaFoco) return null;

  const chamada = detalhe?.chamada ?? [];
  const contar = (s: StatusPresenca) => chamada.filter((c) => c.status === s).length;

  const ordenada = [...chamada].sort((a, b) => {
    const d = ORDEM.indexOf(a.status) - ORDEM.indexOf(b.status);
    return d !== 0 ? d : a.nome.localeCompare(b.nome, 'pt-BR');
  });

  return (
    <>
      <div className="drawer-backdrop" onClick={fechar} />
      <aside className="drawer">
        <div className="drawer-head">
          <button className="drawer-close" onClick={fechar} aria-label="Fechar">
            ×
          </button>
          <h2>{detalhe?.sala.nome ?? 'Carregando…'}</h2>
          <p>
            {detalhe?.aula
              ? `${detalhe.aula.disciplina} · ${detalhe.aula.turma_id} · ${detalhe.aula.professor} · ${detalhe.aula.inicio}–${detalhe.aula.fim}`
              : detalhe
                ? `${detalhe.sala.tipo} · ${detalhe.sala.capacidade} lugares · sem aula em andamento`
                : ''}
          </p>
        </div>

        <div className="drawer-stats">
          {(['PRESENTE', 'ATRASADO', 'AUSENTE', 'EVADIDO'] as StatusPresenca[]).map((s) => (
            <div key={s} className="dstat">
              <b style={{ color: COR_PRESENCA[s] }}>{contar(s)}</b>
              <span>{ROTULO_PRESENCA[s]}</span>
            </div>
          ))}
        </div>

        <div className="drawer-list">
          {carregando && <div className="empty-state">Carregando chamada…</div>}

          {!carregando && chamada.length === 0 && (
            <div className="empty-state">
              Sem aula em andamento nesta sala. A chamada aparece quando a próxima
              turma entra na janela de chegada.
            </div>
          )}

          {ordenada.map((aluno) => (
            <div key={aluno.ra} className="student-row">
              <i
                className="student-dot"
                style={{ background: COR_PRESENCA[aluno.status] }}
              />
              <div>
                <div className="student-name">{aluno.nome}</div>
                <div className="student-ra">
                  RA {aluno.ra}
                  {aluno.entrada_em && ` · entrou ${hhmm(aluno.entrada_em)}`}
                  {aluno.atraso_minutos > 0 && ` · +${aluno.atraso_minutos} min`}
                  {aluno.catraca_origem &&
                    ` · ${aluno.catraca_origem.replace('CATRACA_', '').replace(/_/g, ' ').toLowerCase()}`}
                </div>
              </div>
              <span
                className="student-status"
                style={{
                  color: COR_PRESENCA[aluno.status],
                  background: `${COR_PRESENCA[aluno.status]}22`,
                }}
              >
                {ROTULO_PRESENCA[aluno.status]}
              </span>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
};
