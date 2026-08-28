/**
 * Copia o build do painel para `dist/` na raiz.
 *
 * A Vercel procura o diretorio de saida em `dist` por padrao. Entregar ali
 * faz o deploy funcionar tanto com a configuracao explicita do vercel.json
 * quanto com o padrao da plataforma - sem depender de qual das duas vence.
 */
import { cpSync, existsSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const origem = resolve(raiz, 'apps/web-3d-frontend/dist');
const destino = resolve(raiz, 'dist');

if (!existsSync(origem)) {
  console.error(`[build] nao encontrei o build do painel em ${origem}`);
  process.exit(1);
}

rmSync(destino, { recursive: true, force: true });
cpSync(origem, destino, { recursive: true });
console.log(`[build] painel copiado para ${destino}`);
