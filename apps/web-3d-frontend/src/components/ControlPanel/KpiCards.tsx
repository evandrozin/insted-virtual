import React from 'react';
import type { KPIs } from '../../lib/types';

interface Props {
  kpis: KPIs;
}

function Delta({ valor }: { valor: number }) {
  if (!valor) return <span className="delta flat">— vs ontem</span>;
  const classe = valor > 0 ? 'up' : 'down';
  const seta = valor > 0 ? '▲' : '▼';
  return (
    <span className={`delta ${classe}`}>
      {seta} {Math.abs(valor).toFixed(1)} p.p.
    </span>
  );
}

/**
 * Bloco de indicadores da diretoria. O numero-heroi e a taxa de presenca
 * agora; os cartoes abaixo respondem "por que" essa taxa esta nesse patamar.
 */
export const KpiCards: React.FC<Props> = ({ kpis }) => {
  const ausentesPct = kpis.alunos_esperados_agora
    ? (100 * kpis.ausentes) / kpis.alunos_esperados_agora
    : 0;

  const catracasOk = kpis.catracas_online === kpis.catracas_total;

  return (
    <>
      <div className="kpi-hero">
        <div className="kpi-hero-label">Presença agora</div>
        <div className="kpi-hero-value">
          <b>{kpis.taxa_presenca_geral.toFixed(1)}</b>
          <span>%</span>
          <Delta valor={kpis.taxa_presenca_variacao} />
        </div>
        <div className="kpi-hero-sub">
          {kpis.presentes_em_aula.toLocaleString('pt-BR')} de{' '}
          {kpis.alunos_esperados_agora.toLocaleString('pt-BR')} alunos esperados em{' '}
          {kpis.salas_em_aula} salas em aula
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card good">
          <div className="k-label">No campus</div>
          <div className="k-value">{kpis.alunos_no_campus.toLocaleString('pt-BR')}</div>
          <div className="k-foot">{kpis.fluxo_ultima_hora} passagens/1h</div>
        </div>

        <div className={`kpi-card ${kpis.atrasados > 0 ? 'warn' : ''}`}>
          <div className="k-label">Atrasados</div>
          <div className="k-value">{kpis.atrasados.toLocaleString('pt-BR')}</div>
          <div className="k-foot">após tolerância</div>
        </div>

        <div className={`kpi-card ${ausentesPct > 30 ? 'danger' : ''}`}>
          <div className="k-label">Ausentes</div>
          <div className="k-value">{kpis.ausentes.toLocaleString('pt-BR')}</div>
          <div className="k-foot">{ausentesPct.toFixed(0)}% do esperado</div>
        </div>

        <div className={`kpi-card ${kpis.evasao_em_aula > 0 ? 'danger' : ''}`}>
          <div className="k-label">Evasão em aula</div>
          <div className="k-value">{kpis.evasao_em_aula.toLocaleString('pt-BR')}</div>
          <div className="k-foot">saíram antes do fim</div>
        </div>

        <div className="kpi-card">
          <div className="k-label">Ocupação física</div>
          <div className="k-value">{kpis.taxa_ocupacao_campus.toFixed(0)}%</div>
          <div className="k-foot">
            {kpis.capacidade_total.toLocaleString('pt-BR')} carteiras
          </div>
        </div>

        <div className={`kpi-card ${catracasOk ? '' : 'danger'}`}>
          <div className="k-label">Catracas online</div>
          <div className="k-value">
            {kpis.catracas_online}/{kpis.catracas_total}
          </div>
          <div className="k-foot">{catracasOk ? 'todas ativas' : 'verificar rede'}</div>
        </div>
      </div>
    </>
  );
};
