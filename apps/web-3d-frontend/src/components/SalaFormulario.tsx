import React, { useState } from 'react';
import { criarSala, editarSala, ErroApi } from '../lib/api';
import { useSessao } from '../hooks/useSessao';
import type { SalaCadastro, SalaEntrada } from '../lib/types';

const TIPOS = [
  'AULA', 'LABORATORIO', 'AUDITORIO', 'TEATRO', 'MULTIUSO', 'ESTUDO',
  'BIBLIOTECA', 'SECRETARIA', 'ADMIN', 'CPD', 'CIRCULACAO', 'COWORKING', 'APOIO',
];

const PAVIMENTOS = [
  { codigo: 'TERREO', nome: 'Térreo' },
  { codigo: 'PAV_1', nome: '1º Pavimento' },
  { codigo: 'PAV_2', nome: '2º Pavimento' },
  { codigo: 'TERRACO', nome: 'Terraço' },
];

/** Tipos que recebem carteiras — só eles precisam de geometria. */
const COM_ASSENTO = new Set([
  'AULA', 'LABORATORIO', 'AUDITORIO', 'TEATRO', 'MULTIUSO', 'ESTUDO',
]);

interface Props {
  sala: SalaCadastro | null;   // null = criação
  pavimentoCodigo?: string;
  aoFechar: () => void;
  aoSalvar: () => void;
}

export const SalaFormulario: React.FC<Props> = ({
  sala, pavimentoCodigo, aoFechar, aoSalvar,
}) => {
  const token = useSessao((s) => s.token);
  const expirar = useSessao((s) => s.expirar);
  const editando = sala !== null;

  const [form, setForm] = useState<SalaEntrada>({
    codigo: sala?.codigo ?? '',
    pavimento_codigo: pavimentoCodigo ?? 'PAV_1',
    nome: sala?.sala ?? '',
    tipo: sala?.tipo ?? 'AULA',
    capacidade: sala?.capacidade ?? 0,
    codigo_planta: sala?.codigo_planta ?? '',
    codigo_ensalamento: sala?.codigo_ensalamento ?? '',
    rack_id: sala?.rack_id ?? '',
    pos_x: null,
    pos_z: null,
    largura: null,
    profundidade: null,
  });
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const precisaGeometria = COM_ASSENTO.has(form.tipo) && form.capacidade > 0;

  const campo = (k: keyof SalaEntrada, v: string | number | null) =>
    setForm((f) => ({ ...f, [k]: v }));

  const numero = (v: string) => (v.trim() === '' ? null : Number(v));

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSalvando(true);
    setErro(null);

    // Campos vazios não devem sobrescrever o que já existe com string vazia.
    const limpo = Object.fromEntries(
      Object.entries(form).filter(([, v]) => v !== '' && v !== null),
    ) as unknown as SalaEntrada;

    try {
      if (editando) {
        const { codigo, pavimento_codigo, ...mudancas } = limpo;
        await editarSala(sala!.codigo, mudancas, token);
      } else {
        await criarSala(limpo, token);
      }
      aoSalvar();
    } catch (erroApi) {
      if (erroApi instanceof ErroApi && erroApi.status === 401) {
        expirar();
        setErro('Sua sessão expirou. Entre novamente.');
      } else {
        setErro(erroApi instanceof Error ? erroApi.message : 'Falha ao salvar.');
      }
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="drawer-backdrop" style={{ zIndex: 60 }} onClick={aoFechar} />
      <form className="form-sala" onSubmit={salvar}>
        <header>
          <h3>{editando ? `Editar ${sala!.codigo}` : 'Nova sala'}</h3>
          <button type="button" className="drawer-close" onClick={aoFechar}>
            ×
          </button>
        </header>

        <div className="form-corpo">
          <div className="form-linha">
            <label>
              Código
              <input
                value={form.codigo}
                disabled={editando}
                required
                placeholder="S1_17"
                onChange={(e) => campo('codigo', e.target.value.toUpperCase())}
              />
              {editando && <small>O código identifica a sala e não muda.</small>}
            </label>
            <label>
              Pavimento
              <select
                value={form.pavimento_codigo}
                disabled={editando}
                onChange={(e) => campo('pavimento_codigo', e.target.value)}
              >
                {PAVIMENTOS.map((p) => (
                  <option key={p.codigo} value={p.codigo}>{p.nome}</option>
                ))}
              </select>
            </label>
          </div>

          <label>
            Nome
            <input
              value={form.nome}
              required
              placeholder="Sala 17 (1º Pav)"
              onChange={(e) => campo('nome', e.target.value)}
            />
          </label>

          <div className="form-linha">
            <label>
              Tipo
              <select value={form.tipo} onChange={(e) => campo('tipo', e.target.value)}>
                {TIPOS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              Capacidade
              <input
                type="number" min={0} max={1000}
                value={form.capacidade}
                onChange={(e) => campo('capacidade', Number(e.target.value))}
              />
            </label>
          </div>

          <div className="form-linha">
            <label>
              Código do ensalamento
              <input
                value={form.codigo_ensalamento ?? ''}
                placeholder="07B"
                onChange={(e) => campo('codigo_ensalamento', e.target.value.toUpperCase())}
              />
            </label>
            <label>
              Rack
              <input
                value={form.rack_id ?? ''}
                placeholder="RACK_2"
                onChange={(e) => campo('rack_id', e.target.value.toUpperCase())}
              />
            </label>
          </div>

          <fieldset className={precisaGeometria ? 'obrigatoria' : ''}>
            <legend>
              Geometria na maquete (metros)
              {precisaGeometria && <span className="marca-obrigatoria"> · obrigatória</span>}
            </legend>
            <p className="form-nota">
              Origem no centro do prédio: X cresce para leste, Z para o sul. Sem
              largura e profundidade a sala existe no cadastro mas não é
              desenhada no 3D.
            </p>
            <div className="form-linha quatro">
              <label>
                Posição X
                <input type="number" step="0.01" value={form.pos_x ?? ''}
                       onChange={(e) => campo('pos_x', numero(e.target.value))} />
              </label>
              <label>
                Posição Z
                <input type="number" step="0.01" value={form.pos_z ?? ''}
                       onChange={(e) => campo('pos_z', numero(e.target.value))} />
              </label>
              <label>
                Largura
                <input type="number" step="0.01" min="0.01" value={form.largura ?? ''}
                       onChange={(e) => campo('largura', numero(e.target.value))} />
              </label>
              <label>
                Profundidade
                <input type="number" step="0.01" min="0.01"
                       value={form.profundidade ?? ''}
                       onChange={(e) => campo('profundidade', numero(e.target.value))} />
              </label>
            </div>
          </fieldset>

          {editando && (
            <p className="form-nota">
              Deixar um campo de geometria em branco mantém o valor atual.
            </p>
          )}

          {erro && <div className="form-erro">{erro}</div>}
        </div>

        <footer>
          <button type="button" className="botao-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="botao-primario" disabled={salvando}>
            {salvando ? 'Salvando…' : editando ? 'Salvar alterações' : 'Criar sala'}
          </button>
        </footer>
      </form>
    </>
  );
};
