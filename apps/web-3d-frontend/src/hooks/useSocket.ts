/**
 * Conexao em tempo real com o Motor de Ocupacao.
 *
 * Faz reconexao com backoff exponencial: um painel de diretoria costuma ficar
 * dias aberto em um telao, entao a queda de rede precisa se resolver sozinha.
 */
import { useEffect, useRef } from 'react';
import { useCampus3D } from './useCampus3D';
import type { MensagemSocket } from '../lib/types';

const RECONEXAO_MIN_MS = 1000;
const RECONEXAO_MAX_MS = 15000;

function urlSocket(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const base = import.meta.env.VITE_WS_URL;
  if (base) return base;
  return `${proto}://${window.location.host}/ws/campus`;
}

export function useSocket() {
  const socketRef = useRef<WebSocket | null>(null);
  const tentativaRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const vivoRef = useRef(true);

  useEffect(() => {
    vivoRef.current = true;

    const conectar = () => {
      if (!vivoRef.current) return;

      const ws = new WebSocket(urlSocket());
      socketRef.current = ws;

      ws.onopen = () => {
        tentativaRef.current = 0;
        useCampus3D.getState().setConectado(true);
      };

      ws.onmessage = (raw) => {
        let msg: MensagemSocket;
        try {
          msg = JSON.parse(raw.data);
        } catch {
          return;
        }

        const store = useCampus3D.getState();
        switch (msg.tipo) {
          case 'SNAPSHOT_INICIAL':
            store.aplicarSnapshot(
              msg.maquete,
              msg.dashboard,
              msg.eventos,
              msg.modo_relogio,
              msg.servidor_em,
            );
            break;
          case 'DASHBOARD_TICK':
            store.aplicarTick(msg.dashboard, msg.deltas, msg.servidor_em);
            break;
          case 'EVENTO_CATRACA':
            store.aplicarEvento(msg.evento, msg.deltas);
            break;
          case 'REALOCACAO':
            store.aplicarMaquete(msg.maquete);
            break;
          case 'MAQUETE_ATUALIZADA':
            // Alguem editou o cadastro: a planta mudou sob os pes do painel.
            store.aplicarMaquete(msg.maquete);
            break;
          default:
            break;
        }
      };

      const reagendar = () => {
        useCampus3D.getState().setConectado(false);
        if (!vivoRef.current) return;

        const espera = Math.min(
          RECONEXAO_MIN_MS * 2 ** tentativaRef.current,
          RECONEXAO_MAX_MS,
        );
        tentativaRef.current += 1;
        timerRef.current = window.setTimeout(conectar, espera);
      };

      ws.onclose = reagendar;
      ws.onerror = () => ws.close();
    };

    conectar();

    return () => {
      vivoRef.current = false;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      socketRef.current?.close();
    };
  }, []);

  /** Solicita uma recarga completa do dashboard. */
  const refresh = () => {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ acao: 'REFRESH' }));
    }
  };

  return { refresh };
}
