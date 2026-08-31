import React, { useEffect, useState } from 'react';
import { buscarIntegracoes, buscarParametros, ErroApi, testarJacad } from '../lib/api';
import { Parametros } from './Parametros';
import { useSessao } from '../hooks/useSessao';
import { hhmm } from '../lib/theme';
import type { Integracoes, Parametro } from '../lib/types';

/**
 * Situacao das integracoes.
 *
 * Nao edita credencial: as chaves ficam em variavel de ambiente e aqui so
 * aparece se existem, mascaradas. Quem tiver acesso ao painel nao leva o token
 * do ERP. O que a tela oferece e diagnostico - o que esta ligado, quando
 * sincronizou pela ultima vez, e um teste de conexao.
 */
export const Configuracao: React.FC<{ aoFechar: () => void }> = ({ aoFechar }) => {
  const [dados, setDados] = useState<Integracoes | null>(null);
  const [parametros, setParametros] = useState<Parametro[]>([]);
  const [aba, setAba] = useState<'situacao' | 'ajustes'>('situacao');
  const [erro, setErro] = useState<string | null>(null);
  const [teste, setTeste] = useState<string | null>(null);
  const [testando, setTestando] = useState(false);

  const token = useSessao((s) => s.token);
  const podeEditar = useSessao((s) => Boolean(s.usuario?.pode_editar));
  const expirar = useSessao((s) => s.expirar);

  useEffect(() => {
    let cancelado = false;
    const carregar = () => {
      buscarIntegracoes()
        .then((d) => !cancelado && setDados(d))
        .catch((e) => !cancelado && setErro(String(e)));
      buscarParametros()
        .then((d) => !cancelado && setParametros(d.parametros))
        .catch(() => { /* sem banco: a aba de ajustes fica vazia */ });
    };
    carregar();
    // O relogio e as catracas mudam sozinhos; a tela acompanha.
    const id = window.setInterval(carregar, 10_000);
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

  async function rodarTeste() {
    if (!token) return;
    setTestando(true);
    setTeste(null);
    try {
      const r = await testarJacad(token);
      setTeste(
        r.ok
          ? `Respondeu em modo ${r.modo}: ${r.alunos} alunos, ${r.turmas} turmas, ${r.aulas} aulas.`
          : `Falhou: ${r.erro}`,
      );
    } catch (e) {
      if (e instanceof ErroApi && e.status === 401) {
        expirar();
        setTeste('Sua sessão expirou. Entre novamente.');
      } else {
        setTeste(e instanceof Error ? e.message : 'Falha no teste.');
      }
    }
    setTestando(false);
  }

  const Selo: React.FC<{ ok: boolean; sim: string; nao: string }> = ({ ok, sim, nao }) => (
    <span className={`selo ${ok ? 'ok' : 'alerta'}`}>{ok ? sim : nao}</span>
  );

  return (
    <>
      <div className="drawer-backdrop" onClick={aoFechar} />
      <section className="cadastro">
        <header className="cadastro-head">
          <button className="drawer-close" onClick={aoFechar} aria-label="Fechar">
            ×
          </button>
          <h2>Configuração</h2>
          <p>
            Situação das integrações e ajustes operacionais. As chaves de API
            ficam em variável de ambiente e não passam por aqui.
          </p>

          <div className="view-toggle" style={{ marginTop: 14 }}>
            <button
              className={aba === 'situacao' ? 'active' : ''}
              onClick={() => setAba('situacao')}
            >
              Situação
            </button>
            <button
              className={aba === 'ajustes' ? 'active' : ''}
              onClick={() => setAba('ajustes')}
            >
              Ajustes {parametros.length > 0 && `(${parametros.length})`}
            </button>
          </div>
        </header>

        <div className="cadastro-corpo config-corpo">
          {erro && <div className="empty-state">Não foi possível ler: {erro}</div>}
          {!erro && !dados && <div className="empty-state">Carregando…</div>}

          {aba === 'ajustes' && (
            parametros.length > 0 ? (
              <Parametros
                itens={parametros}
                aoMudar={() => {
                  buscarParametros().then((d) => setParametros(d.parametros));
                  buscarIntegracoes().then(setDados);
                }}
              />
            ) : (
              <div className="empty-state">
                Os ajustes exigem o cadastro em banco. Sem <code>DATABASE_URL</code>,
                os valores vêm apenas das variáveis de ambiente.
              </div>
            )
          )}

          {aba === 'situacao' && dados && (
            <>
              <section className="config-bloco">
                <h3>
                  JACAD <Selo ok={dados.jacad.modo === 'integrado'} sim="integrado" nao="simulado" />
                </h3>
                <dl>
                  <dt>Endereço</dt>
                  <dd>{dados.jacad.base_url ?? <i>não configurado</i>}</dd>
                  <dt>Chave</dt>
                  <dd>
                    {dados.jacad.chave_configurada
                      ? <code>{dados.jacad.chave}</code>
                      : <i>não configurada</i>}
                  </dd>
                  <dt>Sincroniza</dt>
                  <dd>a cada {dados.jacad.intervalo_sync_min} min</dd>
                  <dt>Última sincronização</dt>
                  <dd>{dados.jacad.ultima_sync ? hhmm(dados.jacad.ultima_sync) : '—'}</dd>
                  <dt>Trouxe</dt>
                  <dd>
                    {dados.jacad.alunos.toLocaleString('pt-BR')} alunos ·{' '}
                    {dados.jacad.turmas} turmas · {dados.jacad.aulas} aulas
                  </dd>
                </dl>
                {podeEditar && (
                  <div className="config-acao">
                    <button className="botao-secundario" onClick={rodarTeste} disabled={testando}>
                      {testando ? 'Testando…' : 'Testar conexão'}
                    </button>
                    {teste && <span className="config-resultado">{teste}</span>}
                  </div>
                )}
                {dados.jacad.modo === 'simulado' && (
                  <p className="config-nota">
                    Em modo simulado os dados vêm de um conjunto sintético. Para
                    integrar, defina <code>JACAD_BASE_URL</code>,{' '}
                    <code>JACAD_TOKEN</code> e <code>JACAD_MODO_MOCK=false</code>.
                  </p>
                )}
              </section>

              <section className="config-bloco">
                <h3>
                  Catracas{' '}
                  <Selo ok={dados.catracas.modo === 'integrado'} sim="integrado" nao="simulado" />
                </h3>
                <dl>
                  <dt>Equipamentos</dt>
                  <dd>
                    {dados.catracas.online} de {dados.catracas.total} respondendo
                  </dd>
                  <dt>Hoje</dt>
                  <dd>
                    {dados.catracas.entradas_hoje} entradas ·{' '}
                    {dados.catracas.saidas_hoje} saídas
                  </dd>
                  <dt>Identificador</dt>
                  <dd>{dados.catracas.identificador}</dd>
                  <dt>Como enviar</dt>
                  <dd>
                    <code>{dados.catracas.webhook}</code>
                    <br />
                    <code>{dados.catracas.websocket}</code> (fluxo contínuo)
                    <br />
                    <code>{dados.catracas.lote}</code> (reenvio após queda)
                  </dd>
                </dl>
                {dados.catracas.modo === 'simulado' && (
                  <p className="config-nota">
                    O simulador está gerando as passagens. Em produção use{' '}
                    <code>SIMULADOR_ATIVO=false</code> e aponte a controladora
                    para um dos canais acima.
                  </p>
                )}
              </section>

              <section className="config-bloco">
                <h3>
                  Data e hora{' '}
                  {dados.data_hora.em_demonstracao && (
                    <span className="selo alerta">demonstração</span>
                  )}
                </h3>
                <dl>
                  <dt>Fuso</dt>
                  <dd>{dados.data_hora.fuso}</dd>
                  <dt>Relógio do sistema</dt>
                  <dd>{new Date(dados.data_hora.agora).toLocaleString('pt-BR')}</dd>
                  <dt>Modo</dt>
                  <dd>{dados.data_hora.modo}</dd>
                </dl>
                <p className="config-nota">
                  A grade horária é hora de parede local. O fuso vem de{' '}
                  <code>TIMEZONE</code> — sem ele, um servidor em UTC procuraria
                  as aulas quatro horas fora do lugar.
                </p>
              </section>

              <section className="config-bloco">
                <h3>Infraestrutura</h3>
                <dl>
                  <dt>Estado compartilhado</dt>
                  <dd>
                    {dados.infraestrutura.estado_compartilhado}
                    {dados.infraestrutura.estado_compartilhado === 'memoria' && (
                      <span className="selo alerta">instância única</span>
                    )}
                  </dd>
                  <dt>Cadastro em banco</dt>
                  <dd>
                    <Selo ok={dados.infraestrutura.banco_configurado} sim="ligado" nao="usando a planta" />
                  </dd>
                  <dt>Login</dt>
                  <dd>
                    <Selo ok={dados.infraestrutura.login_disponivel} sim="disponível" nao="desligado" />
                  </dd>
                  <dt>Reconciliação</dt>
                  <dd>
                    {dados.infraestrutura.loop_interno
                      ? 'loop interno do processo'
                      : 'por cron externo'}
                  </dd>
                </dl>
              </section>

              <section className="config-bloco">
                <h3>Regras de presença</h3>
                <dl>
                  <dt>Tolerância de atraso</dt>
                  <dd>{dados.regras.tolerancia_atraso_min} min após o início</dd>
                  <dt>Janela de chegada</dt>
                  <dd>{dados.regras.janela_chegada_min} min antes da aula</dd>
                  <dt>Alerta de baixa presença</dt>
                  <dd>abaixo de {dados.regras.limiar_baixa_presenca}%</dd>
                  <dt>Catraca sem sinal</dt>
                  <dd>após {Math.round(dados.regras.catraca_timeout_s / 60)} min</dd>
                </dl>
                <p className="config-nota">
                  Ajustáveis na aba <b>Ajustes</b>. Mudá-las altera como a
                  presença é classificada, então toda alteração fica registrada
                  com autor.
                </p>
              </section>
            </>
          )}
        </div>
      </section>
    </>
  );
};
