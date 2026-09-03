import React, { useEffect, useMemo, useState } from 'react';
import { buscarPresentes } from '../lib/api';
import type { Presentes as PresentesDados } from '../lib/types';

const ROTULO_TIPO: Record<string, string> = {
  ALUNO: 'Alunos',
  PROFESSOR: 'Professores',
  FUNCIONARIO: 'Funcionários',
  NAO_IDENTIFICADO: 'Não identificados',
};

/**
 * Quem esta na instituicao agora, segundo as catracas.
 *
 * Diferente da maquete: aqui e circulacao no predio, inclusive de quem nao tem
 * aula neste horario. A maquete mostra ocupacao de sala; esta tela mostra
 * presenca fisica.
 */
export const Presentes: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const [dados, setDados] = useState<PresentesDados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [busca, setBusca] = useState('');
  const [tipo, setTipo] = useState<string>('');

  useEffect(() => {
    let cancelado = false;
    const carregar = () =>
      buscarPresentes()
        .then((d) => !cancelado && (setDados(d), setErro(null)))
        .catch((e) => !cancelado && setErro(e instanceof Error ? e.message : String(e)));
    carregar();
    // A catraca nao avisa: e preciso perguntar. 30 s acompanha a entrada sem
    // martelar o banco.
    const id = window.setInterval(carregar, 30_000);
    return () => {
      cancelado = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [aoFechar]);

  const lista = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return (dados?.pessoas ?? []).filter((p) => {
      if (tipo && (p.tipo ?? 'NAO_IDENTIFICADO') !== tipo) return false;
      if (!termo) return true;
      return (
        p.nome.toLowerCase().includes(termo) ||
        (p.identificador ?? '').toLowerCase().includes(termo) ||
        (p.turma ?? '').toLowerCase().includes(termo)
      );
    });
  }, [dados, busca, tipo]);

  const hora = (iso: string) => iso.slice(11, 16);

  // Replicacao parada e campus vazio dao a mesma contagem. So o atraso separa
  // os dois casos, entao ele fica visivel em vez de escondido num diagnostico.
  const atraso = dados?.atraso_replicacao_min ?? null;
  const desatualizado = atraso !== null && atraso > 10;

  return (
    <>
      <div className="drawer-backdrop" onClick={aoFechar} />
      <section className="cadastro">
        <header className="cadastro-head">
          <button className="drawer-close" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
          <h2>Na instituição agora</h2>
          <p>
            Quem passou pela catraca e ainda não registrou saída. Considera as
            últimas {dados?.janela_horas ?? 18} horas.
          </p>

          {erro && <div className="empty-state">Não foi possível ler: {erro}</div>}

          {dados && (
            <>
              <div className="pessoas-cartoes">
                <button
                  className={`cartao-tipo ${tipo === '' ? 'ativo' : ''}`}
                  onClick={() => setTipo('')}
                >
                  <b>{dados.total.toLocaleString('pt-BR')}</b>
                  <span>Todos</span>
                </button>
                {Object.entries(dados.por_tipo)
                  .sort((a, b) => b[1] - a[1])
                  .map(([codigo, n]) => (
                    <button
                      key={codigo}
                      className={`cartao-tipo ${tipo === codigo ? 'ativo' : ''}`}
                      onClick={() => setTipo(tipo === codigo ? '' : codigo)}
                    >
                      <b>{n.toLocaleString('pt-BR')}</b>
                      <span>{ROTULO_TIPO[codigo] ?? codigo}</span>
                    </button>
                  ))}
              </div>

              <div className="config-acao" style={{ marginTop: 12 }}>
                <input
                  className="campo-busca"
                  placeholder="Buscar por nome, matrícula ou turma…"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </div>

              <p className={`config-nota ${desatualizado ? 'alerta' : ''}`}>
                {dados.ultima_marcacao
                  ? `Última passagem registrada às ${hora(dados.ultima_marcacao)}` +
                    (atraso !== null ? ` — há ${atraso} min.` : '.')
                  : 'Nenhuma passagem replicada ainda.'}
                {desatualizado &&
                  ' A replicação pode estar parada: um campus vazio e um job parado' +
                    ' produzem a mesma contagem.'}
                {dados.identificados < dados.total && (
                  <>
                    {' '}
                    {(dados.total - dados.identificados).toLocaleString('pt-BR')} pessoa(s)
                    dentro sem correspondência no cadastro acadêmico.
                  </>
                )}
              </p>
            </>
          )}
        </header>

        <div className="cadastro-corpo">
          {!dados && !erro && <div className="empty-state">Carregando…</div>}

          {dados && lista.length === 0 && (
            <div className="empty-state">
              {dados.total === 0
                ? 'Ninguém na instituição neste momento.'
                : 'Nenhuma pessoa corresponde ao filtro.'}
            </div>
          )}

          {lista.length > 0 && (
            <table className="tabela-pessoas">
              <thead>
                <tr>
                  <th>Identificador</th>
                  <th>Nome</th>
                  <th>Tipo</th>
                  <th>Turma / Curso</th>
                  <th>Entrou</th>
                  <th>Catraca</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((p) => (
                  <tr key={p.pes_id} className={p.identificado ? '' : 'linha-alerta'}>
                    <td>
                      <code>{p.identificador ?? '—'}</code>
                    </td>
                    <td>{p.nome}</td>
                    <td>
                      {p.tipo ? (
                        <span className="selo">{ROTULO_TIPO[p.tipo] ?? p.tipo}</span>
                      ) : (
                        <span
                          className="selo alerta"
                          title="Passou na catraca mas não está no cadastro do JaCad"
                        >
                          sem cadastro
                        </span>
                      )}
                    </td>
                    <td className="muted">{p.turma ?? p.curso ?? '—'}</td>
                    <td>{hora(p.desde)}</td>
                    <td className="muted">{p.terminal ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </>
  );
};
