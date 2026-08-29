import React, { useEffect, useState } from 'react';
import { useCampus3D } from '../../hooks/useCampus3D';
import { INSTED } from '../../lib/theme';
import marcaInsted from '../../assets/insted-marca.png';

/**
 * Simbolo institucional (orbitas), recortado da arte oficial
 * "Insted_Logo_Temp_horizontal". A arte original e grafite; a versao usada
 * aqui e clara, para o header escuro do painel.
 */
const MarcaInsted: React.FC = () => (
  <img className="brand-mark" src={marcaInsted} alt="Insted" draggable={false} />
);

export const Header: React.FC<{ aoAbrirCadastro?: () => void }> = ({
  aoAbrirCadastro,
}) => {
  const conectado = useCampus3D((s) => s.conectado);
  const servidorEm = useCampus3D((s) => s.servidorEm);
  const modoRelogio = useCampus3D((s) => s.modoRelogio);
  const dashboard = useCampus3D((s) => s.dashboard);

  // Interpola o relogio localmente entre os ticks do servidor (5s).
  const [agora, setAgora] = useState<Date>(new Date());
  useEffect(() => {
    if (!servidorEm) return;
    const base = new Date(servidorEm).getTime();
    const t0 = Date.now();
    const id = window.setInterval(() => {
      setAgora(new Date(base + (Date.now() - t0)));
    }, 1000);
    setAgora(new Date(base));
    return () => window.clearInterval(id);
  }, [servidorEm]);

  const data = agora.toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
  });

  return (
    <header className="top-bar">
      <div className="brand" style={{ color: INSTED.textLight }}>
        <MarcaInsted />
        <div className="brand-text">
          <div className="brand-name">
            inst<span className="accent">ed.</span>
          </div>
          <div className="brand-sub">Centro Universitário</div>
        </div>
      </div>

      <div className="top-divider" />

      <div className="top-title">
        Controle de Presença em Tempo Real
        <small>
          Maquete Virtual 3D · catracas + JACAD
          {modoRelogio && modoRelogio !== 'tempo real' ? ` · relógio ${modoRelogio}` : ''}
        </small>
      </div>

      <div className="top-spacer" />

      {dashboard && (
        <div className="top-title" style={{ textAlign: 'right' }}>
          {dashboard.kpis.alunos_no_campus.toLocaleString('pt-BR')} no campus
          <small>
            {dashboard.kpis.salas_em_aula} salas em aula · {dashboard.kpis.catracas_online}/
            {dashboard.kpis.catracas_total} catracas
          </small>
        </div>
      )}

      {aoAbrirCadastro && (
        <button
          className="botao-cadastro"
          onClick={aoAbrirCadastro}
          title="Cadastro de salas: prédio, andar, nome e capacidade"
        >
          Cadastro
        </button>
      )}

      <span className={`live-pill ${conectado ? 'on' : 'off'}`}>
        <i className="live-dot" />
        {conectado ? 'ao vivo' : 'reconectando'}
      </span>

      <div className="clock">
        {agora.toLocaleTimeString('pt-BR', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}
        <small>{data}</small>
      </div>
    </header>
  );
};
