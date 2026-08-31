import React, { useState } from 'react';
import { ErroApi, gravarParametro } from '../lib/api';
import { useSessao } from '../hooks/useSessao';
import type { Parametro } from '../lib/types';

const TITULO: Record<string, string> = {
  PRESENCA: 'Regras de presença',
  INTEGRACAO: 'Integrações',
  SISTEMA: 'Sistema',
};

/**
 * Ajuste dos parametros operacionais.
 *
 * Cada linha mostra o valor efetivo e de onde ele vem. Gravar guarda no banco
 * e passa a valer na hora; limpar o campo devolve o parametro a variavel de
 * ambiente, que continua sendo o padrao do deploy.
 */
export const Parametros: React.FC<{
  itens: Parametro[];
  aoMudar: () => void;
}> = ({ itens, aoMudar }) => {
  const token = useSessao((s) => s.token);
  const podeEditar = useSessao((s) => Boolean(s.usuario?.pode_editar));
  const expirar = useSessao((s) => s.expirar);

  const [rascunho, setRascunho] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const porCategoria = itens.reduce<Record<string, Parametro[]>>((acc, p) => {
    (acc[p.categoria] ??= []).push(p);
    return acc;
  }, {});

  async function gravar(p: Parametro, valor: string | null) {
    if (!token) return;
    setSalvando(p.chave);
    setAviso(null);
    try {
      const r = await gravarParametro(p.chave, valor, token);
      setRascunho((d) => {
        const { [p.chave]: _, ...resto } = d;
        return resto;
      });
      setAviso(
        `${p.rotulo}: ${r.origem === 'banco' ? `ajustado para ${r.valor_efetivo}` : 'devolvido ao valor do ambiente'}` +
        (r.exige_reinicio ? ' — exige reiniciar o servidor para valer.' : '.'),
      );
      aoMudar();
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        expirar();
        setAviso('Sua sessão expirou. Entre novamente.');
      } else {
        setAviso(e instanceof Error ? e.message : 'Falha ao gravar.');
      }
    }
    setSalvando(null);
  }

  return (
    <>
      {aviso && <div className="cadastro-aviso">{aviso}</div>}

      {Object.entries(porCategoria).map(([categoria, lista]) => (
        <section className="config-bloco" key={categoria}>
          <h3>{TITULO[categoria] ?? categoria}</h3>

          <table className="tabela-parametros">
            <tbody>
              {lista.map((p) => {
                const emEdicao = rascunho[p.chave];
                const atual =
                  emEdicao !== undefined
                    ? emEdicao
                    : p.valor ?? String(p.valor_efetivo ?? '');
                const alterado = emEdicao !== undefined && emEdicao !== (p.valor ?? '');

                return (
                  <tr key={p.chave}>
                    <td className="param-rotulo">
                      <b>{p.rotulo}</b>
                      {p.descricao && <span>{p.descricao}</span>}
                      <em>
                        vem {p.origem === 'banco' ? 'do banco' : 'do ambiente'}
                        {p.atualizado_por && ` · alterado por ${p.atualizado_por}`}
                        {p.exige_reinicio && ' · exige reinício'}
                      </em>
                    </td>

                    <td className="param-controle">
                      {p.tipo === 'BOOLEANO' ? (
                        <label className="caixa-marcar">
                          <input
                            type="checkbox"
                            disabled={!podeEditar || salvando === p.chave}
                            checked={
                              atual === 'true' || atual === 'True' ||
                              (atual === '' && p.valor_efetivo === true)
                            }
                            onChange={(e) =>
                              gravar(p, e.target.checked ? 'true' : 'false')
                            }
                          />
                          {p.valor_efetivo ? 'ligado' : 'desligado'}
                        </label>
                      ) : (
                        <>
                          <input
                            type={p.tipo === 'INTEIRO' ? 'number' : 'text'}
                            value={atual}
                            disabled={!podeEditar || salvando === p.chave}
                            min={p.minimo ?? undefined}
                            max={p.maximo ?? undefined}
                            placeholder={String(p.valor_efetivo ?? '')}
                            onChange={(e) =>
                              setRascunho((d) => ({ ...d, [p.chave]: e.target.value }))
                            }
                          />
                          {p.unidade && <span className="param-unidade">{p.unidade}</span>}
                        </>
                      )}
                    </td>

                    <td className="param-acoes">
                      {podeEditar && p.tipo !== 'BOOLEANO' && (
                        <>
                          {alterado && (
                            <button
                              className="botao-linha"
                              disabled={salvando === p.chave}
                              onClick={() => gravar(p, atual)}
                            >
                              {salvando === p.chave ? '…' : 'Salvar'}
                            </button>
                          )}
                          {p.origem === 'banco' && !alterado && (
                            <button
                              className="botao-linha"
                              title="Voltar a usar a variável de ambiente"
                              disabled={salvando === p.chave}
                              onClick={() => gravar(p, null)}
                            >
                              Restaurar
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ))}

      {!podeEditar && (
        <p className="config-nota">
          Entre com uma conta de administração para ajustar estes valores.
        </p>
      )}

      <p className="config-nota">
        O valor gravado aqui vence a variável de ambiente. Limpar um campo e
        salvar devolve o parâmetro ao ambiente, que continua sendo o padrão do
        deploy. <b>Chaves de API e credenciais não passam por aqui</b> — ficam
        só em variável de ambiente.
      </p>
    </>
  );
};
