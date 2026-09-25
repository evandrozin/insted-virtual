import React, { useEffect, useRef, useState } from 'react';
import { useSessao } from '../hooks/useSessao';
import {
  buscarConfigLogin,
  redefinirSenha,
  solicitarCodigoSenha,
} from '../lib/api';

/**
 * Entrada para administrar o cadastro.
 *
 * O painel de leitura nao passa por aqui: esta tela existe para autorizar a
 * edicao. Alem do login, atende a recuperacao de senha por codigo enviado no
 * e-mail cadastrado.
 */
type Etapa = 'LOGIN' | 'PEDIR_CODIGO' | 'TROCAR_SENHA';

export const Login: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const entrar = useSessao((s) => s.entrar);
  const entrando = useSessao((s) => s.entrando);
  const erro = useSessao((s) => s.erro);
  const limparErro = useSessao((s) => s.limparErro);

  const [etapa, setEtapa] = useState<Etapa>('LOGIN');
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [codigo, setCodigo] = useState('');
  const [novaSenha, setNovaSenha] = useState('');
  const [aviso, setAviso] = useState<string | null>(null);
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [resetDisponivel, setResetDisponivel] = useState(false);

  const campoEmail = useRef<HTMLInputElement>(null);

  useEffect(() => {
    campoEmail.current?.focus();
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [aoFechar]);

  useEffect(() => {
    // Sem SMTP no servidor nao ha como enviar codigo: o link nao aparece, em
    // vez de levar a pessoa por tres telas ate um erro.
    buscarConfigLogin()
      .then((c) => setResetDisponivel(Boolean(c.reset_por_email)))
      .catch(() => setResetDisponivel(false));
  }, []);

  function irPara(nova: Etapa) {
    setEtapa(nova);
    setErroLocal(null);
    setAviso(null);
    if (erro) limparErro();
  }

  async function enviarLogin(e: React.FormEvent) {
    e.preventDefault();
    if (await entrar(email, senha)) aoFechar();
  }

  async function enviarPedido(e: React.FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setErroLocal(null);
    try {
      const r = await solicitarCodigoSenha(email);
      setAviso(r.mensagem);
      setEtapa('TROCAR_SENHA');
    } catch (err) {
      setErroLocal(err instanceof Error ? err.message : String(err));
    } finally {
      setOcupado(false);
    }
  }

  async function enviarNovaSenha(e: React.FormEvent) {
    e.preventDefault();
    if (novaSenha.length < 8) {
      setErroLocal('A senha precisa ter ao menos 8 caracteres.');
      return;
    }
    setOcupado(true);
    setErroLocal(null);
    try {
      await redefinirSenha(email, codigo, novaSenha);
      // Volta para o login com a senha ja preenchida: quem acabou de
      // escolher a senha nao deve ter que digita-la de novo na tela seguinte.
      setSenha(novaSenha);
      setCodigo('');
      setNovaSenha('');
      setEtapa('LOGIN');
      setAviso('Senha alterada. Entre com ela agora.');
    } catch (err) {
      setErroLocal(err instanceof Error ? err.message : String(err));
    } finally {
      setOcupado(false);
    }
  }

  const mensagemErro = erroLocal ?? erro;

  return (
    <>
      <div className="drawer-backdrop" style={{ zIndex: 60 }} onClick={aoFechar} />

      {etapa === 'LOGIN' && (
        <form className="login" onSubmit={enviarLogin}>
          <button type="button" className="drawer-close" onClick={aoFechar}>
            ×
          </button>
          <h3>Entrar para editar</h3>
          <p className="login-sub">
            O painel é aberto. A conta é necessária apenas para alterar o
            cadastro de salas.
          </p>

          <label>
            E-mail
            <input
              ref={campoEmail}
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (erro) limparErro();
                setErroLocal(null);
              }}
            />
          </label>

          <label>
            Senha
            <input
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => {
                setSenha(e.target.value);
                if (erro) limparErro();
                setErroLocal(null);
              }}
            />
          </label>

          {aviso && <div className="form-aviso">{aviso}</div>}
          {mensagemErro && <div className="form-erro">{mensagemErro}</div>}

          <button type="submit" className="botao-primario" disabled={entrando}>
            {entrando ? 'Entrando…' : 'Entrar'}
          </button>

          {resetDisponivel && (
            <button
              type="button"
              className="link-discreto"
              onClick={() => irPara('PEDIR_CODIGO')}
            >
              Esqueci minha senha
            </button>
          )}
        </form>
      )}

      {etapa === 'PEDIR_CODIGO' && (
        <form className="login" onSubmit={enviarPedido}>
          <button type="button" className="drawer-close" onClick={aoFechar}>
            ×
          </button>
          <h3>Redefinir senha</h3>
          <p className="login-sub">
            Enviamos um código de 6 dígitos para o e-mail cadastrado. Ele vale
            por alguns minutos e só pode ser usado uma vez.
          </p>

          <label>
            E-mail cadastrado
            <input
              type="email"
              autoComplete="username"
              required
              autoFocus
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setErroLocal(null);
              }}
            />
          </label>

          {mensagemErro && <div className="form-erro">{mensagemErro}</div>}

          <button type="submit" className="botao-primario" disabled={ocupado}>
            {ocupado ? 'Enviando…' : 'Enviar código'}
          </button>

          <button
            type="button"
            className="link-discreto"
            onClick={() => irPara('LOGIN')}
          >
            Voltar ao login
          </button>
        </form>
      )}

      {etapa === 'TROCAR_SENHA' && (
        <form className="login" onSubmit={enviarNovaSenha}>
          <button type="button" className="drawer-close" onClick={aoFechar}>
            ×
          </button>
          <h3>Digite o código</h3>
          {aviso && <p className="login-sub">{aviso}</p>}

          <label>
            Código de 6 dígitos
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={6}
              required
              autoFocus
              value={codigo}
              onChange={(e) => {
                setCodigo(e.target.value.replace(/\D/g, ''));
                setErroLocal(null);
              }}
            />
          </label>

          <label>
            Nova senha (mín. 8 caracteres)
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              value={novaSenha}
              onChange={(e) => {
                setNovaSenha(e.target.value);
                setErroLocal(null);
              }}
            />
          </label>

          {mensagemErro && <div className="form-erro">{mensagemErro}</div>}

          <button type="submit" className="botao-primario" disabled={ocupado}>
            {ocupado ? 'Salvando…' : 'Redefinir senha'}
          </button>

          <button
            type="button"
            className="link-discreto"
            onClick={() => irPara('PEDIR_CODIGO')}
          >
            Não recebi o código
          </button>
        </form>
      )}
    </>
  );
};
