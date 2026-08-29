import React, { useEffect, useRef, useState } from 'react';
import { useSessao } from '../hooks/useSessao';

/**
 * Entrada para administrar o cadastro.
 *
 * O painel de leitura nao passa por aqui: esta tela existe para autorizar a
 * edicao, e por isso e aberta a partir do proprio cadastro.
 */
export const Login: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const entrar = useSessao((s) => s.entrar);
  const entrando = useSessao((s) => s.entrando);
  const erro = useSessao((s) => s.erro);
  const limparErro = useSessao((s) => s.limparErro);

  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const campoEmail = useRef<HTMLInputElement>(null);

  useEffect(() => {
    campoEmail.current?.focus();
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [aoFechar]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (await entrar(email, senha)) aoFechar();
  }

  return (
    <>
      <div className="drawer-backdrop" style={{ zIndex: 60 }} onClick={aoFechar} />
      <form className="login" onSubmit={enviar}>
        <button type="button" className="drawer-close" onClick={aoFechar}>
          ×
        </button>
        <h3>Entrar para editar</h3>
        <p className="login-sub">
          O painel é aberto. A conta é necessária apenas para alterar o cadastro
          de salas.
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
            }}
          />
        </label>

        {erro && <div className="form-erro">{erro}</div>}

        <button type="submit" className="botao-primario" disabled={entrando}>
          {entrando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </>
  );
};
