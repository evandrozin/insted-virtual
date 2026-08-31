import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  buscarPessoas, buscarResumoPessoas, desativarPessoa, ErroApi,
  salvarPessoa, sincronizarPessoas,
} from '../lib/api';
import { useSessao } from '../hooks/useSessao';
import type { Pessoa, PessoaEntrada, ResumoPessoas, TipoPessoa } from '../lib/types';

const POR_PAGINA = 100;

/**
 * Quem circula no campus e quem esta dentro agora.
 *
 * O cruzamento e direto porque o cracha usa o mesmo identificador do JACAD:
 * a coluna "no campus" e o conjunto de passagens registradas hoje batido
 * contra o cadastro.
 */
export const Pessoas: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const [resumo, setResumo] = useState<ResumoPessoas | null>(null);
  const [lista, setLista] = useState<Pessoa[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(0);
  const [tipo, setTipo] = useState('TODOS');
  const [busca, setBusca] = useState('');
  const [soNoCampus, setSoNoCampus] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [editando, setEditando] = useState<Pessoa | 'nova' | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const token = useSessao((s) => s.token);
  const podeEditar = useSessao((s) => Boolean(s.usuario?.pode_editar));
  const expirar = useSessao((s) => s.expirar);

  const carregar = useCallback(async () => {
    try {
      const [r, l] = await Promise.all([
        buscarResumoPessoas(),
        buscarPessoas({
          tipo: tipo === 'TODOS' ? undefined : tipo,
          q: busca.trim() || undefined,
          limite: POR_PAGINA,
          offset: pagina * POR_PAGINA,
        }),
      ]);
      setResumo(r);
      setLista(l.pessoas);
      setTotal(l.total);
      setErro(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e));
    }
  }, [tipo, busca, pagina]);

  useEffect(() => {
    const id = window.setTimeout(carregar, busca ? 350 : 0);
    return () => window.clearTimeout(id);
  }, [carregar, busca]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [aoFechar]);

  const tipos: TipoPessoa[] = resumo?.tipos ?? [];
  const visiveis = useMemo(
    () => (soNoCampus ? lista.filter((p) => p.no_campus) : lista),
    [lista, soNoCampus],
  );

  async function comSessao(acao: () => Promise<void>, sucesso: string) {
    if (!token) return;
    setOcupado(true);
    try {
      await acao();
      setAviso(sucesso);
      await carregar();
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        expirar();
        setAviso('Sua sessão expirou. Entre novamente.');
      } else {
        setAviso(e instanceof Error ? e.message : 'Falha na operação.');
      }
    }
    setOcupado(false);
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={aoFechar} />
      <section className="cadastro">
        <header className="cadastro-head">
          <button className="drawer-close" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
          <h2>Pessoas</h2>
          <p>
            {resumo
              ? `${resumo.no_campus_agora.toLocaleString('pt-BR')} na instituição neste momento`
              : 'Carregando…'}
            {resumo && resumo.sem_cadastro > 0 && (
              <span className="cadastro-erro">
                {' '}— {resumo.sem_cadastro} passagem(ns) de identificador não cadastrado
              </span>
            )}
          </p>

          <div className="cadastro-acoes">
            {podeEditar && (
              <>
                <button className="botao-primario" onClick={() => setEditando('nova')}>
                  + Nova pessoa
                </button>
                <button
                  className="botao-secundario"
                  disabled={ocupado}
                  onClick={() =>
                    comSessao(
                      async () => {
                        const r = await sincronizarPessoas(token!);
                        setAviso(
                          `JACAD: ${r.recebidos} recebidos, ${r.gravados} no cadastro` +
                          (r.desativados ? `, ${r.desativados} desativados` : '') + '.',
                        );
                      },
                      'Sincronizado com o JACAD.',
                    )
                  }
                >
                  Sincronizar do JACAD
                </button>
              </>
            )}
          </div>

          {aviso && <div className="cadastro-aviso">{aviso}</div>}

          <div className="tipos-resumo">
            <button
              className={`tipo-cartao ${tipo === 'TODOS' ? 'ativo' : ''}`}
              onClick={() => { setTipo('TODOS'); setPagina(0); }}
            >
              <b>{tipos.reduce((s, t) => s + (t.ativos ?? 0), 0).toLocaleString('pt-BR')}</b>
              <span>Todos</span>
              <i>{tipos.reduce((s, t) => s + (t.no_campus ?? 0), 0)} dentro</i>
            </button>
            {tipos.map((t) => (
              <button
                key={t.codigo}
                className={`tipo-cartao ${tipo === t.codigo ? 'ativo' : ''}`}
                onClick={() => { setTipo(t.codigo); setPagina(0); }}
                style={{ borderTopColor: t.cor ?? undefined }}
              >
                <b>{(t.ativos ?? 0).toLocaleString('pt-BR')}</b>
                <span>{t.plural}</span>
                <i style={{ color: t.cor ?? undefined }}>{t.no_campus ?? 0} dentro</i>
              </button>
            ))}
          </div>

          <div className="cadastro-filtros">
            <input
              className="cadastro-busca"
              placeholder="Buscar por nome, identificador, turma ou setor…"
              value={busca}
              onChange={(e) => { setBusca(e.target.value); setPagina(0); }}
            />
            <label className="caixa-marcar">
              <input
                type="checkbox"
                checked={soNoCampus}
                onChange={(e) => setSoNoCampus(e.target.checked)}
              />
              Só quem está dentro
            </label>
          </div>

          <div className="cadastro-totais">
            <span><b>{total.toLocaleString('pt-BR')}</b> no filtro</span>
            <span>mostrando <b>{visiveis.length}</b></span>
            {total > POR_PAGINA && (
              <span className="paginacao">
                <button
                  className="botao-linha"
                  disabled={pagina === 0}
                  onClick={() => setPagina((p) => Math.max(0, p - 1))}
                >
                  ‹ anterior
                </button>
                página {pagina + 1} de {Math.ceil(total / POR_PAGINA)}
                <button
                  className="botao-linha"
                  disabled={(pagina + 1) * POR_PAGINA >= total}
                  onClick={() => setPagina((p) => p + 1)}
                >
                  próxima ›
                </button>
              </span>
            )}
          </div>
        </header>

        <div className="cadastro-corpo">
          {erro && <div className="empty-state">Não foi possível ler: {erro}</div>}
          {!erro && visiveis.length === 0 && (
            <div className="empty-state">
              {soNoCampus
                ? 'Ninguém deste filtro está na instituição agora.'
                : 'Nenhuma pessoa corresponde ao filtro.'}
            </div>
          )}

          {visiveis.length > 0 && (
            <table className="cadastro-tabela">
              <thead>
                <tr>
                  <th>Identificador</th>
                  <th>Nome</th>
                  <th>Tipo</th>
                  <th>Turma / Setor</th>
                  <th>Origem</th>
                  <th>Agora</th>
                  {podeEditar && <th className="acoes">Ações</th>}
                </tr>
              </thead>
              <tbody>
                {visiveis.map((p) => (
                  <tr key={p.identificador}>
                    <td className="mono">{p.identificador}</td>
                    <td>{p.nome}</td>
                    <td>
                      <span
                        className="tag-tipo"
                        style={p.tipo_cor ? {
                          color: p.tipo_cor, background: `${p.tipo_cor}1f`,
                        } : undefined}
                      >
                        {p.tipo_nome}
                      </span>
                    </td>
                    <td className="muted">{p.turma_id ?? p.setor ?? '—'}</td>
                    <td className="muted mono">{p.origem}</td>
                    <td>
                      {p.no_campus
                        ? <span className="selo ok">dentro</span>
                        : <span className="muted">fora</span>}
                    </td>
                    {podeEditar && (
                      <td className="acoes">
                        <button className="botao-linha" onClick={() => setEditando(p)}>
                          Editar
                        </button>
                        <button
                          className="botao-linha perigo"
                          disabled={ocupado}
                          onClick={() => {
                            if (!window.confirm(
                              `Desativar ${p.nome}? O registro e o histórico são preservados.`,
                            )) return;
                            comSessao(
                              async () => {
                                await desativarPessoa(p.identificador, token!);
                              },
                              `${p.nome} desativada.`,
                            );
                          }}
                        >
                          Desativar
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

      {editando && (
        <PessoaFormulario
          pessoa={editando === 'nova' ? null : editando}
          tipos={tipos}
          aoFechar={() => setEditando(null)}
          aoSalvar={async (dados) => {
            await comSessao(
              () => salvarPessoa(dados.identificador, dados, token!).then(() => undefined),
              'Cadastro atualizado.',
            );
            setEditando(null);
          }}
        />
      )}
    </>
  );
};

/* ------------------------------------------------------------------ */

const PessoaFormulario: React.FC<{
  pessoa: Pessoa | null;
  tipos: TipoPessoa[];
  aoFechar: () => void;
  aoSalvar: (dados: PessoaEntrada) => Promise<void>;
}> = ({ pessoa, tipos, aoFechar, aoSalvar }) => {
  const editando = pessoa !== null;
  const [form, setForm] = useState<PessoaEntrada>({
    identificador: pessoa?.identificador ?? '',
    nome: pessoa?.nome ?? '',
    tipo_codigo: pessoa?.tipo ?? tipos.find((t) => !t.conta_presenca_em_aula)?.codigo ?? 'FUNCIONARIO',
    email: pessoa?.email ?? '',
    curso: pessoa?.curso ?? '',
    turma_id: pessoa?.turma_id ?? '',
    periodo: pessoa?.periodo ?? null,
    setor: pessoa?.setor ?? '',
    cargo: pessoa?.cargo ?? '',
  });
  const [salvando, setSalvando] = useState(false);

  const tipoEscolhido = tipos.find((t) => t.codigo === form.tipo_codigo);
  const ehAluno = Boolean(tipoEscolhido?.conta_presenca_em_aula);
  const campo = (k: keyof PessoaEntrada, v: unknown) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <>
      <div className="drawer-backdrop" style={{ zIndex: 60 }} onClick={aoFechar} />
      <form
        className="form-sala"
        onSubmit={async (e) => {
          e.preventDefault();
          setSalvando(true);
          await aoSalvar(form);
          setSalvando(false);
        }}
      >
        <header>
          <h3>{editando ? `Editar ${pessoa!.identificador}` : 'Nova pessoa'}</h3>
          <button type="button" className="drawer-close" onClick={aoFechar}>×</button>
        </header>

        <div className="form-corpo">
          <div className="form-linha">
            <label>
              Identificador
              <input
                value={form.identificador}
                disabled={editando}
                required
                placeholder="RA ou matrícula"
                onChange={(e) => campo('identificador', e.target.value.trim())}
              />
              <small>O mesmo do crachá na catraca.</small>
            </label>
            <label>
              Tipo
              <select
                value={form.tipo_codigo}
                onChange={(e) => campo('tipo_codigo', e.target.value)}
              >
                {tipos.map((t) => (
                  <option key={t.codigo} value={t.codigo}>{t.nome}</option>
                ))}
              </select>
            </label>
          </div>

          <label>
            Nome
            <input
              value={form.nome}
              required
              onChange={(e) => campo('nome', e.target.value)}
            />
          </label>

          <label>
            E-mail
            <input
              type="email"
              value={form.email ?? ''}
              onChange={(e) => campo('email', e.target.value)}
            />
          </label>

          {ehAluno ? (
            <div className="form-linha">
              <label>
                Curso
                <input value={form.curso ?? ''} onChange={(e) => campo('curso', e.target.value)} />
              </label>
              <label>
                Turma
                <input value={form.turma_id ?? ''} onChange={(e) => campo('turma_id', e.target.value)} />
              </label>
            </div>
          ) : (
            <div className="form-linha">
              <label>
                Setor
                <input value={form.setor ?? ''} onChange={(e) => campo('setor', e.target.value)} />
              </label>
              <label>
                Cargo
                <input value={form.cargo ?? ''} onChange={(e) => campo('cargo', e.target.value)} />
              </label>
            </div>
          )}

          <p className="form-nota">
            {ehAluno
              ? 'Este tipo ocupa carteira em aula: a presença é medida contra a grade horária.'
              : 'Este tipo não tem aula: a presença é apenas estar na instituição.'}
            {editando && pessoa?.origem === 'JACAD' && (
              <>
                {' '}Atenção: este registro veio do JACAD. Salvar aqui o converte
                para cadastro manual, e ele deixa de ser atualizado pelo sync.
              </>
            )}
          </p>
        </div>

        <footer>
          <button type="button" className="botao-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="botao-primario" disabled={salvando}>
            {salvando ? 'Salvando…' : editando ? 'Salvar' : 'Criar'}
          </button>
        </footer>
      </form>
    </>
  );
};
