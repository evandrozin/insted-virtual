import React from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { KpiCards } from './KpiCards';
import { PresenceChart } from './PresenceChart';
import { RoomRanking } from './RoomRanking';
import { CourseRanking } from './CourseRanking';
import { AlertFeed } from './AlertFeed';

/** Coluna direita do painel: leitura executiva do campus em tempo real. */
export const ControlPanel: React.FC = () => {
  const dashboard = useCampus3D((s) => s.dashboard);

  if (!dashboard) {
    return (
      <aside className="sidebar">
        <div className="empty-state">Sincronizando com o motor de ocupacao...</div>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <KpiCards kpis={dashboard.kpis} />
      <PresenceChart serie={dashboard.serie_presenca} />
      <AlertFeed alertas={dashboard.alertas} />
      <RoomRanking salas={dashboard.ocupacao_salas} />
      <CourseRanking cursos={dashboard.ranking_cursos} />
    </aside>
  );
};

export { Header } from './Header';
export { EventTicker } from './EventTicker';
export { RoomDrawer } from './RoomDrawer';
