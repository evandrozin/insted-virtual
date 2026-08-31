import React, { useEffect, useRef, useState } from 'react';
import { useSessao } from '../hooks/useSessao';

export type Painel = 'SALAS' | 'PESSOAS' | 'CONFIGURACAO';

const ITENS: Array<{ id: Painel; rotulo: string; descricao: string }> = [
  { id: 'SALAS', rotulo: 'Salas', descricao: 'Prédio, andar, capacidade e geometria' },
  { id: 'PESSOAS', rotulo: 'Pessoas', descricao: 'Alunos, professores e quem está dentro' },
  { id: 'CONFIGURACAO', rotulo: 'Configuração', descricao: 'Integrações, fuso e regras' },
];

/** Entrada para as telas de gestão, fora do fluxo de leitura do painel. */
export const MenuGestao: React.FC<{ aoEscolher: (p: Painel) => void }> = ({
  aoEscolher,
}) => {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const usuario = useSessao((s) => s.usuario);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) {
        setAberto(false);
      }
    };
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setAberto(false);
    document.addEventListener('mousedown', fora);
    window.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', fora);
      window.removeEventListener('keydown', esc);
    };
  }, [aberto]);

  return (
    <div className="menu-gestao" ref={caixa}>
      <button className="botao-cadastro" onClick={() => setAberto((v) => !v)}>
        Gestão {aberto ? '▴' : '▾'}
      </button>

      {aberto && (
        <div className="menu-lista">
          {ITENS.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                aoEscolher(item.id);
                setAberto(false);
              }}
            >
              <b>{item.rotulo}</b>
              <span>{item.descricao}</span>
            </button>
          ))}
          {usuario && (
            <div className="menu-rodape">
              {usuario.nome} · <b>{usuario.papel}</b>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
