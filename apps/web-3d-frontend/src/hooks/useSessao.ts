/**
 * Sessao de quem administra o cadastro.
 *
 * O painel de leitura nao exige login: a sessao existe para liberar a edicao.
 * O token fica em localStorage para o operador nao reautenticar a cada
 * recarga; o backend o valida em toda escrita e ele expira sozinho.
 */
import { create } from 'zustand';
import { autenticar, buscarConfigLogin, ErroApi } from '../lib/api';
import type { Usuario } from '../lib/types';

const CHAVE = 'insted.sessao';

interface Guardado {
  token: string;
  usuario: Usuario;
  expira_em: number;
}

function ler(): Guardado | null {
  try {
    const cru = localStorage.getItem(CHAVE);
    if (!cru) return null;
    const dados = JSON.parse(cru) as Guardado;
    if (!dados.token || Date.now() >= dados.expira_em) {
      localStorage.removeItem(CHAVE);
      return null;
    }
    return dados;
  } catch {
    // Modo privado, storage bloqueado ou conteudo corrompido.
    return null;
  }
}

function gravar(dados: Guardado | null) {
  try {
    if (dados) localStorage.setItem(CHAVE, JSON.stringify(dados));
    else localStorage.removeItem(CHAVE);
  } catch {
    /* sem storage: a sessao vale so enquanto a aba estiver aberta */
  }
}

interface SessaoStore {
  token: string | null;
  usuario: Usuario | null;
  loginHabilitado: boolean;
  entrando: boolean;
  erro: string | null;

  carregarConfig: () => Promise<void>;
  entrar: (email: string, senha: string) => Promise<boolean>;
  sair: () => void;
  limparErro: () => void;
  expirar: () => void;
}

const inicial = ler();

export const useSessao = create<SessaoStore>((set) => ({
  token: inicial?.token ?? null,
  usuario: inicial?.usuario ?? null,
  loginHabilitado: false,
  entrando: false,
  erro: null,

  carregarConfig: async () => {
    try {
      const cfg = await buscarConfigLogin();
      set({ loginHabilitado: cfg.login_habilitado });
    } catch {
      set({ loginHabilitado: false });
    }
  },

  entrar: async (email, senha) => {
    set({ entrando: true, erro: null });
    try {
      const sessao = await autenticar(email, senha);
      gravar({
        token: sessao.token,
        usuario: sessao.usuario,
        expira_em: Date.now() + sessao.expira_em_horas * 3600_000,
      });
      set({ token: sessao.token, usuario: sessao.usuario, entrando: false });
      return true;
    } catch (erro) {
      set({
        entrando: false,
        erro:
          erro instanceof ErroApi
            ? erro.message
            : 'Não foi possível falar com o servidor.',
      });
      return false;
    }
  },

  sair: () => {
    gravar(null);
    set({ token: null, usuario: null, erro: null });
  },

  limparErro: () => set({ erro: null }),

  /** Chamado quando o backend recusa o token: a sessao acabou. */
  expirar: () => {
    gravar(null);
    set({
      token: null,
      usuario: null,
      erro: 'Sua sessão expirou. Entre novamente.',
    });
  },
}));

export const podeEditar = (s: SessaoStore) => Boolean(s.usuario?.pode_editar);
