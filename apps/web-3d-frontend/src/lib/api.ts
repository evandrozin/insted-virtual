/** Cliente HTTP do Motor de Ocupacao (complementa o WebSocket). */
import type { Dashboard, DetalheSala, Maquete, RespostaCadastro } from './types';

const BASE = import.meta.env.VITE_API_URL ?? '/api/v1';

async function get<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`);
  if (!resposta.ok) {
    throw new Error(`${resposta.status} em ${caminho}`);
  }
  return resposta.json() as Promise<T>;
}

export const buscarMaquete = () => get<Maquete>('/maquete');
export const buscarDashboard = () => get<Dashboard>('/dashboard');
export const buscarCadastroSalas = () =>
  get<RespostaCadastro>('/cadastro/salas');

export const buscarDetalheSala = (salaId: string) =>
  get<DetalheSala>(`/salas/${encodeURIComponent(salaId)}`);

export const buscarAluno = (ra: string) =>
  get<{
    aluno: { ra: string; nome: string; curso: string; turma_id: string };
    no_campus: boolean;
    localizacao: { sala_nome: string; pavimento: string; cadeira_id: string } | null;
  }>(`/alunos/${encodeURIComponent(ra)}`);
