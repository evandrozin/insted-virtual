import React from 'react';
import type { RankingCurso } from '../../lib/types';

interface Props {
  cursos: RankingCurso[];
}

/** Presenca consolidada por curso no horario corrente. */
export const CourseRanking: React.FC<Props> = ({ cursos }) => (
  <div className="panel-card">
    <div className="section-title">
      Presenca por curso
      <span className="count">{cursos.length}</span>
    </div>

    {cursos.length === 0 ? (
      <div className="empty-state">Sem aulas em andamento.</div>
    ) : (
      cursos.map((c) => (
        <div key={c.curso} className="course-row">
          <div className="course-track">
            <i style={{ width: `${Math.min(100, c.taxa)}%` }} />
            <span>
              {c.curso} · {c.presentes}/{c.esperados}
            </span>
          </div>
          <div className="course-pct">{c.taxa.toFixed(0)}%</div>
        </div>
      ))
    )}
  </div>
);
