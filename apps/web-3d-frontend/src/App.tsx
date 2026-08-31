import React, { useEffect, useState } from 'react';
import { Canvas3D } from './components/Canvas3D';
import { CadastroSalas } from './components/CadastroSalas';
import { Configuracao } from './components/Configuracao';
import { Pessoas } from './components/Pessoas';
import type { Painel } from './components/MenuGestao';
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

/**
 * Tela inicial. Se o motor de ocupacao nao responder em alguns segundos,
 * troca o spinner por um diagnostico: sem backend o painel ficaria girando
 * para sempre, sem dizer o que esta faltando.
 */
function TelaDeBoot() {
  const conectado = useCampus3D((s) => s.conectado);
  const [demorou, setDemorou] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setDemorou(true), 6000);
    return () => window.clearTimeout(id);
  }, []);

  const destino =
    import.meta.env.VITE_WS_URL ??
    `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/campus`;

  if (!demorou || conectado) {
    return (
      <div className="boot-screen">
        <div className="boot-ring" />
        <div className="boot-text">Carregando a maquete virtual do campus...</div>
      </div>
    );
  }

  return (
    <div className="boot-screen">
      <div className="boot-alerta">
        <h1>Sem conexao com o motor de ocupacao</h1>
        <p>
          O painel esta no ar, mas nao conseguiu abrir o canal de tempo real em{' '}
          <code>{destino}</code>.
        </p>
        <p>
          Verifique se a API esta publicada e se as variaveis{' '}
          <code>VITE_API_URL</code> e <code>VITE_WS_URL</code> apontam para o
          dominio dela.
        </p>
        <span className="boot-tentando">
          <i className="boot-ring pequeno" /> tentando reconectar...
        </span>
      </div>
    </div>
  );
}

export default function App() {
  useSocket();
  const [painel, setPainel] = useState<Painel | null>(null);

  const maquete = useCampus3D((s) => s.maquete);
  const modoVisao = useCampus3D((s) => s.modoVisao);
  const setModoVisao = useCampus3D((s) => s.setModoVisao);
  const pavimentoSelecionado = useCampus3D((s) => s.pavimentoSelecionado);
  const selecionarPavimento = useCampus3D((s) => s.selecionarPavimento);

  if (!maquete) {
    return <TelaDeBoot />;
  }

  const nomePavimento =
    maquete.pavimentos.find((p) => p.id === pavimentoSelecionado)?.nome ?? '';

  return (
    <div className="app-shell">
      <Header aoAbrirPainel={setPainel} />

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
      {painel === 'SALAS' && <CadastroSalas aoFechar={() => setPainel(null)} />}
      {painel === 'PESSOAS' && <Pessoas aoFechar={() => setPainel(null)} />}
      {painel === 'CONFIGURACAO' && <Configuracao aoFechar={() => setPainel(null)} />}
    </div>
  );
}
