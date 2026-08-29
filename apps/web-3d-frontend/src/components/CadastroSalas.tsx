import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { buscarCadastroSalas, desativarSala, ErroApi, reativarSala } from '../lib/api';
import { useCampus3D } from '../hooks/useCampus3D';
import { useSessao } from '../hooks/useSessao';
import { Login } from './Login';
import { SalaFormulario } from './SalaFormulario';
import type { RespostaCadastro, SalaCadastro } from '../lib/types';

/**
 * Cadastro fisico do campus: predio, andar, sala, tipo e capacidade.
 *
 * Le do Postgres quando ha banco configurado, e da planta em uso quando nao ha
 * - a resposta diz qual foi a origem, para nao restar duvida sobre o que esta
 * sendo mostrado.
 */
export const CadastroSalas: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const [dados, setDados] = useState<RespostaCadastro | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState('');
  const [pavimento, setPavimento] = useState('TODOS');
  const abrirSala = useCampus3D((s) => s.abrirSala);

  const token = useSessao((s) => s.token);
  const usuario = useSessao((s) => s.usuario);
  const loginHabilitado = useSessao((s) => s.loginHabilitado);
  const carregarConfig = useSessao((s) => s.carregarConfig);
  const sair = useSessao((s) => s.sair);
  const expirar = useSessao((s) => s.expirar);

  const [loginAberto, setLoginAberto] = useState(false);
  const [editando, setEditando] = useState<SalaCadastro | null>(null);
  const [criando, setCriando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const podeEditar = Boolean(usuario?.pode_editar) && dados?.origem === 'banco';

  const recarregar = useCallback(() => {
    buscarCadastroSalas()
      .then(setDados)
      .catch((e) => setErro(String(e)));
  }, []);

  useEffect(() => {
    let cancelado = false;
    buscarCadastroSalas()
      .then((r) => !cancelado && setDados(r))
      .catch((e) => !cancelado && setErro(String(e)));
    carregarConfig();
    return () => {
      cancelado = true;
    };
  }, [carregarConfig]);

  async function alternarSituacao(sala: SalaCadastro) {
    if (!token) return;
    const acao = sala.ativa ? 'desativar' : 'reativar';
    if (sala.ativa && !window.confirm(
      `Desativar ${sala.codigo}? Ela sai da maquete, mas o registro e o ` +
      `histórico são preservados.`)) return;
    try {
      await (sala.ativa ? desativarSala : reativarSala)(sala.codigo, token);
      setAviso(`${sala.codigo} ${sala.ativa ? 'desativada' : 'reativada'}.`);
      recarregar();
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        expirar();
        setAviso('Sua sessão expirou. Entre novamente.');
      } else {
        setAviso(`Não foi possível ${acao}: ${e instanceof Error ? e.message : e}`);
      }
    }
  }

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [aoFechar]);

  const pavimentos = useMemo(() => {
    const vistos = new Map<string, number>();
    for (const s of dados?.salas ?? []) vistos.set(s.pavimento, s.pavimento_ordem);
    return [...vistos.entries()].sort((a, b) => a[1] - b[1]).map(([nome]) => nome);
  }, [dados]);

  const filtradas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return (dados?.salas ?? []).filter((s) => {
      if (pavimento !== 'TODOS' && s.pavimento !== pavimento) return false;
      if (!termo) return true;
      return [s.codigo, s.sala, s.tipo, s.codigo_planta, s.codigo_ensalamento]
        .filter(Boolean)
        .some((c) => String(c).toLowerCase().includes(termo));
    });
  }, [dados, busca, pavimento]);

  const totais = useMemo(() => {
    const lugares = filtradas.reduce((soma, s) => soma + s.capacidade, 0);
    const semEnsalamento = filtradas.filter((s) => !s.codigo_ensalamento).length;
    return { ambientes: filtradas.length, lugares, semEnsalamento };
  }, [filtradas]);

  const rotuloOrigem: Record<string, string> = {
    banco: 'cadastro em banco',
    seed: 'planta (sem banco configurado)',
    banco_indisponivel: 'banco indisponível',
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={aoFechar} />
      <section className="cadastro">
        <header className="cadastro-head">
          <button className="drawer-close" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
          <h2>Cadastro de salas</h2>
          <p>
            {dados
              ? `${dados.salas.length} ambientes · origem: ${rotuloOrigem[dados.origem] ?? dados.origem}`
              : 'Carregando…'}
            {dados?.erro && <span className="cadastro-erro"> — {dados.erro}</span>}
          </p>

          <div className="cadastro-acoes">
            {usuario ? (
              <>
                <span className="cadastro-quem">
                  {usuario.nome} · <b>{usuario.papel}</b>
                </span>
                {podeEditar && (
                  <button className="botao-primario" onClick={() => setCriando(true)}>
                    + Nova sala
                  </button>
                )}
                <button className="botao-secundario" onClick={sair}>Sair</button>
              </>
            ) : (
              loginHabilitado && (
                <button className="botao-secundario" onClick={() => setLoginAberto(true)}>
                  Entrar para editar
                </button>
              )
            )}
          </div>

          {aviso && <div className="cadastro-aviso">{aviso}</div>}

          {usuario && !podeEditar && dados?.origem !== 'banco' && (
            <div className="cadastro-aviso">
              A edição exige o cadastro em banco. Esta instalação está lendo da
              planta (sem <code>DATABASE_URL</code>).
            </div>
          )}

          <div className="cadastro-filtros">
            <input
              className="cadastro-busca"
              placeholder="Buscar por código, nome ou tipo…"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
            <select value={pavimento} onChange={(e) => setPavimento(e.target.value)}>
              <option value="TODOS">Todos os pavimentos</option>
              {pavimentos.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          <div className="cadastro-totais">
            <span>
              <b>{totais.ambientes}</b> ambientes
            </span>
            <span>
              <b>{totais.lugares.toLocaleString('pt-BR')}</b> lugares
            </span>
            {totais.semEnsalamento > 0 && (
              <span className="pendente">
                <b>{totais.semEnsalamento}</b> sem código de ensalamento
              </span>
            )}
          </div>
        </header>

        <div className="cadastro-corpo">
          {erro && <div className="empty-state">Não foi possível ler o cadastro: {erro}</div>}
          {!erro && !dados && <div className="empty-state">Carregando cadastro…</div>}
          {dados && filtradas.length === 0 && (
            <div className="empty-state">Nenhuma sala corresponde ao filtro.</div>
          )}

          {filtradas.length > 0 && (
            <table className="cadastro-tabela">
              <thead>
                <tr>
                  <th>Prédio</th>
                  <th>Andar</th>
                  <th>Código</th>
                  <th>Sala</th>
                  <th>Tipo</th>
                  <th className="num">Capacidade</th>
                  <th>Ensalamento</th>
                  <th>Rack</th>
                  {podeEditar && <th className="acoes">Ações</th>}
                </tr>
              </thead>
              <tbody>
                {filtradas.map((s: SalaCadastro) => (
                  <tr
                    key={s.codigo}
                    className={s.ativa ? '' : 'inativa'}
                    onClick={() => {
                      abrirSala(s.codigo);
                      aoFechar();
                    }}
                    title="Abrir a chamada desta sala"
                  >
                    <td className="muted">{s.predio}</td>
                    <td>{s.pavimento}</td>
                    <td className="mono">{s.codigo}</td>
                    <td>{s.sala}</td>
                    <td>
                      <span className="tag-tipo">{s.tipo}</span>
                    </td>
                    <td className="num">{s.capacidade || '—'}</td>
                    <td className="mono">
                      {s.codigo_ensalamento ?? <span className="pendente">a definir</span>}
                    </td>
                    <td className="muted mono">{s.rack_id ?? '—'}</td>
                    {podeEditar && (
                      <td className="acoes" onClick={(e) => e.stopPropagation()}>
                        <button className="botao-linha" onClick={() => setEditando(s)}>
                          Editar
                        </button>
                        <button
                          className={`botao-linha ${s.ativa ? 'perigo' : ''}`}
                          onClick={() => alternarSituacao(s)}
                        >
                          {s.ativa ? 'Desativar' : 'Reativar'}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {loginAberto && <Login aoFechar={() => setLoginAberto(false)} />}

      {(criando || editando) && (
        <SalaFormulario
          sala={editando}
          pavimentoCodigo={undefined}
          aoFechar={() => {
            setCriando(false);
            setEditando(null);
          }}
          aoSalvar={() => {
            setCriando(false);
            setEditando(null);
            setAviso('Cadastro atualizado. A maquete já reflete a mudança.');
            recarregar();
          }}
        />
      )}
    </>
  );
};
