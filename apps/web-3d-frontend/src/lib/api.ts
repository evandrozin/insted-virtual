/** Cliente HTTP do Motor de Ocupacao (complementa o WebSocket). */
import type {
  ConfigLogin,
  Integracoes,
  Parametro,
  ListaPessoas,
  Pessoa,
  PessoaEntrada,
  ResumoPessoas,
  TipoPessoa,
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

// --- configuracao e pessoas -------------------------------------------------

export const buscarIntegracoes = () => get<Integracoes>('/config/integracoes');

export const testarJacad = (token: string) =>
  enviar<{ ok: boolean; modo: string; alunos?: number; professores?: number;
           professores_sem_matricula?: number; turmas?: number;
           aulas?: number; erro?: string;
           amostra?: Array<{ identificador: string; nome: string; curso: string }> }>(
    'POST', '/config/testar/jacad', undefined, token,
  );

export const buscarResumoPessoas = () => get<ResumoPessoas>('/pessoas/resumo');

export const buscarTiposPessoa = () =>
  get<{ tipos: TipoPessoa[] }>('/pessoas/tipos');

export function buscarPessoas(params: {
  tipo?: string; q?: string; limite?: number; offset?: number;
} = {}) {
  const busca = new URLSearchParams();
  if (params.tipo) busca.set('tipo', params.tipo);
  if (params.q) busca.set('q', params.q);
  busca.set('limite', String(params.limite ?? 100));
  busca.set('offset', String(params.offset ?? 0));
  return get<ListaPessoas>(`/pessoas?${busca}`);
}

export const salvarPessoa = (
  identificador: string, dados: PessoaEntrada, token: string,
) =>
  enviar<{ pessoa: Pessoa }>(
    'PUT', `/pessoas/${encodeURIComponent(identificador)}`, dados, token,
  );

export const desativarPessoa = (identificador: string, token: string) =>
  enviar<unknown>(
    'DELETE', `/pessoas/${encodeURIComponent(identificador)}`, undefined, token,
  );

export const sincronizarPessoas = (token: string) =>
  enviar<{
    recebidos: number; gravados: number; desativados: number;
    // Quebra por tipo: alunos e professores sao sincronizados juntos, mas
    // desativados separadamente, entao o total sozinho esconde o que mudou.
    por_tipo: Record<string, { recebidos: number; gravados: number; desativados: number }>;
    sincronizado_em: string;
  }>(
    'POST', '/pessoas/sincronizar', undefined, token,
  );

export const buscarParametros = () =>
  get<{ parametros: Parametro[] }>('/config/parametros');

export const gravarParametro = (chave: string, valor: string | null, token: string) =>
  enviar<{
    chave: string;
    valor_efetivo: string | number | boolean | null;
    origem: 'banco' | 'ambiente';
    exige_reinicio: boolean;
  }>('PUT', `/config/parametros/${encodeURIComponent(chave)}`, { valor }, token);
