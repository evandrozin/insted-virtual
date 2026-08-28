import React from 'react';
import { Canvas3D } from './components/Canvas3D';
import { FloorMap } from './components/FloorMap';
import { ControlPanel, EventTicker, Header, RoomDrawer } from './components/ControlPanel';
import { useCampus3D } from './hooks/useCampus3D';
import { useSocket } from './hooks/useSocket';
import { COR_CADEIRA } from './lib/theme';

const LEGENDA: Array<[string, string]> = [
  ['Livre', COR_CADEIRA.LIVRE],
  ['Alocada (JACAD)', COR_CADEIRA.RESERVADA],
  ['Presente (catraca)', COR_CADEIRA.OCUPADA],
  ['Sobrelotacao', COR_CADEIRA.ALERT_SOBRELOTACAO],
];

export default function App() {
  useSocket();

  const maquete = useCampus3D((s) => s.maquete);
  const modoVisao = useCampus3D((s) => s.modoVisao);
  const setModoVisao = useCampus3D((s) => s.setModoVisao);
  const pavimentoSelecionado = useCampus3D((s) => s.pavimentoSelecionado);
  const selecionarPavimento = useCampus3D((s) => s.selecionarPavimento);

  if (!maquete) {
    return (
      <div className="boot-screen">
        <div className="boot-ring" />
        <div className="boot-text">Carregando a maquete virtual do campus...</div>
      </div>
    );
  }

  const nomePavimento =
    maquete.pavimentos.find((p) => p.id === pavimentoSelecionado)?.nome ?? '';

  return (
    <div className="app-shell">
      <Header />

      <div className="app-body">
        <FloorMap />

        <main className="viewport">
          <Canvas3D />

          <div className="viewport-overlay">
            <div className="overlay-row">
              <div className="view-toggle">
                <button
                  className={modoVisao === 'CAMPUS' ? 'active' : ''}
                  onClick={() => setModoVisao('CAMPUS')}
                >
                  Campus completo
                </button>
                <button
                  className={modoVisao === 'PAVIMENTO' ? 'active' : ''}
                  onClick={() => selecionarPavimento(pavimentoSelecionado)}
                >
                  {modoVisao === 'PAVIMENTO' ? nomePavimento : 'Pavimento'}
                </button>
              </div>

              <div className="viewport-hint">
                arraste para girar · scroll para zoom · clique numa sala para a chamada
              </div>
            </div>

            <div className="overlay-row">
              <div className="legend">
                {LEGENDA.map(([rotulo, cor]) => (
                  <span key={rotulo} className="legend-item">
                    <i className="legend-swatch" style={{ background: cor }} />
                    {rotulo}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </main>

        <ControlPanel />
      </div>

      <EventTicker />
      <RoomDrawer />
    </div>
  );
}
