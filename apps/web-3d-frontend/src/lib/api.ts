/** Cliente HTTP do Motor de Ocupacao (complementa o WebSocket). */
import type {
  ConfigLogin,
  Dashboard,
  DetalheSala,
  Maquete,
  RespostaCadastro,
  SalaEntrada,
  Sessao,
} from './types';

const BASE = import.meta.env.VITE_API_URL ?? '/api/v1';

async function get<T>(caminho: string): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`);
  if (!resposta.ok) {
    throw new Error(`${resposta.status} em ${caminho}`);
  }
  return resposta.json() as Promise<T>;
}

/** Erro de API que carrega o status e a mensagem que o backend explicou. */
export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function enviar<T>(
  metodo: 'POST' | 'PUT' | 'DELETE',
  caminho: string,
  corpo?: unknown,
  token?: string,
): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`, {
    method: metodo,
    headers: {
      ...(corpo ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });

  if (!resposta.ok) {
    let detalhe = `Falha ${resposta.status}`;
    try {
      const erro = await resposta.json();
      // FastAPI devolve string em HTTPException e lista em erro de validacao.
      if (typeof erro.detail === 'string') detalhe = erro.detail;
      else if (Array.isArray(erro.detail)) {
        detalhe = erro.detail
          .map((d: { loc?: string[]; msg: string }) =>
            `${d.loc?.slice(1).join('.') ?? ''}: ${d.msg}`.replace(/^: /, ''))
          .join(' · ');
      }
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new ErroApi(resposta.status, detalhe);
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

export const buscarConfigLogin = () => get<ConfigLogin>('/auth/config');

export const autenticar = (email: string, senha: string) =>
  enviar<Sessao>('POST', '/auth/login', { email, senha });

export const criarSala = (sala: SalaEntrada, token: string) =>
  enviar<{ sala: SalaEntrada }>('POST', '/cadastro/salas', sala, token);

export const editarSala = (
  codigo: string,
  mudancas: Partial<SalaEntrada>,
  token: string,
) =>
  enviar<{ sala: SalaEntrada }>(
    'PUT', `/cadastro/salas/${encodeURIComponent(codigo)}`, mudancas, token,
  );

export const desativarSala = (codigo: string, token: string) =>
  enviar<unknown>('DELETE', `/cadastro/salas/${encodeURIComponent(codigo)}`, undefined, token);

export const reativarSala = (codigo: string, token: string) =>
  enviar<unknown>(
    'POST', `/cadastro/salas/${encodeURIComponent(codigo)}/reativar`, undefined, token,
  );
