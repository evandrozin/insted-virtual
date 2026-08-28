# Insted Virtual Campus — Controle de Presença em Tempo Real

Maquete virtual 3D do campus do **Insted Centro Universitário** ligada ao fluxo
real de catracas e à grade horária do **JACAD**. Cada carteira da maquete
representa um aluno concreto; a cor da carteira muda no instante em que ele
passa na catraca.

> **Pergunta que o sistema responde para a diretoria:**
> *"Neste momento, quem deveria estar em aula, quem está, onde, e o que precisa
> da minha atenção?"*

---

## 1. Como funciona

O motor cruza três fontes e projeta o resultado em uma única visão:

| Fonte | O que traz | Frequência |
|---|---|---|
| **JACAD** (ERP acadêmico) | matrículas, turmas, grade horária, professor, sala | sync a cada 15 min |
| **Catracas** | passagens de entrada/saída por RA | evento a evento (tempo real) |
| **Maquete 3D** | topologia dos 4 pavimentos, 63 ambientes e 2.742 lugares | estático (seed) |

### Ciclo de vida de uma carteira

```
        45 min antes da aula          passagem na catraca         fim da aula
LIVRE ──────────────────────► RESERVADA ──────────────────► OCUPADA ──────────► LIVRE
(verde)                        (azul)                        (cyan Insted)
                                                                  │
                                        saiu do campus antes do fim│
                                                                  ▼
                                                          volta a RESERVADA
                                                          (aluno marcado EVADIDO)
```

Se a turma excede a capacidade da sala, o excedente vira
`ALERT_SOBRELOTACAO` (vermelho) — a diretoria **vê** o problema em vez de
receber um erro silencioso.

### Estados de presença do aluno

| Status | Quando ocorre |
|---|---|
| `AGUARDANDO` | aula aberta, aluno ainda não passou na catraca |
| `PRESENTE` | entrou até a tolerância (padrão: 15 min após o início) |
| `ATRASADO` | entrou depois da tolerância, com a aula em curso |
| `AUSENTE` | passou a tolerância sem nenhuma passagem registrada |
| `EVADIDO` | entrou e deixou o campus faltando mais de 10 min para o fim |

---

## 2. Como rodar

Pré-requisitos: **Python 3.11+** e **Node 18+**.

### Backend

```bash
cd apps/backend-api
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API em `http://127.0.0.1:8000` · documentação interativa em `/docs`.

### Frontend

```bash
cd apps/web-3d-frontend
npm install
npm run dev
```

Painel em `http://127.0.0.1:5173` (o Vite já faz proxy de `/api` e `/ws`).

### Modo apresentação

Uma demonstração às 9h da manhã mostraria o campus vazio. Para ancorar o
relógio da aplicação em um horário letivo e acelerar o tempo:

```bash
RELOGIO_DEMO=19:10 SIMULADOR_FATOR_TEMPO=8 python -m uvicorn app.main:app --port 8000
```

`SIMULADOR_FATOR_TEMPO=8` faz 8 minutos passarem por segundo — a sala enche na
frente da diretoria. Com `1` (padrão) o fluxo acontece em tempo real.

---

## 3. Ligando nas catracas de verdade

O simulador existe só para desenvolvimento e demonstração. Desligue com
`SIMULADOR_ATIVO=false` e aponte a controladora de acesso para um dos dois
canais — o processamento é idêntico nos dois:

**Webhook HTTP** (uma passagem por chamada):

```http
POST /api/v1/catracas/evento
Content-Type: application/json

{ "ra": "20260199", "catraca_id": "CATRACA_PRINCIPAL_A", "direcao": "ENTRADA" }
```

**WebSocket** (fluxo contínuo, menor latência):

```
ws://<host>/ws/catracas
→ { "ra": "20260199", "catraca_id": "CATRACA_PRINCIPAL_A", "direcao": "ENTRADA" }
```

Se a controladora ficar sem rede, o buffer acumulado pode ser reenviado de uma
vez em `POST /api/v1/catracas/lote`, preservando os `timestamp` originais.

### Ligando no JACAD de verdade

Preencha `JACAD_BASE_URL` e `JACAD_TOKEN` e mude `JACAD_MODO_MOCK=false`.
`JacadRestClient` (em `app/services/jacad_client.py`) já implementa o mesmo
contrato do mock — o motor de presença não muda. Os *paths* e o mapeamento de
campos estão concentrados nesse arquivo e devem ser ajustados ao contrato do
tenant Insted.

---

## 4. Endpoints principais

| Método | Rota | Uso |
|---|---|---|
| `GET` | `/api/v1/maquete` | topologia + status de todas as carteiras |
| `GET` | `/api/v1/dashboard` | KPIs, ocupação, série do dia, alertas, ranking |
| `GET` | `/api/v1/salas/{id}` | chamada nominal da aula em andamento |
| `GET` | `/api/v1/alunos/{ra}` | onde o aluno está agora + aulas do dia |
| `GET` | `/api/v1/alunos?q=` | busca por RA ou nome |
| `GET` | `/api/v1/academico/grade` | grade horária do dia |
| `POST` | `/api/v1/catracas/evento` | ingestão de passagem |
| `POST` | `/api/v1/alocacao/realocar` | mover turma de sala (resolver sobrelotação) |
| `WS` | `/ws/campus` | snapshot inicial + deltas em tempo real |
| `WS` | `/ws/catracas` | ingestão contínua da controladora |

### Protocolo do `/ws/campus`

No *handshake* o servidor envia `SNAPSHOT_INICIAL` (maquete completa +
dashboard). Depois disso trafegam apenas incrementos:

- `EVENTO_CATRACA` — a passagem + os deltas de carteira que ela provocou;
- `DASHBOARD_TICK` — KPIs recalculados (a cada 5 s);
- `REALOCACAO` — nova maquete após uma turma mudar de sala.

Um painel de diretoria fica dias aberto em telão, então o cliente reconecta
sozinho com *backoff* exponencial (1 s → 15 s).

---

## 5. Estrutura

```
apps/
├── backend-api/                     FastAPI + motor de presença
│   ├── app/
│   │   ├── api/
│   │   │   ├── index.py             entry point das Vercel Functions
│   │   │   └── v1/
│   │   │       ├── academico.py     espelho do JACAD
│   │   │       ├── alocacao.py      realocação manual de turmas
│   │   │       ├── catracas.py      ingestão de passagens
│   │   │       ├── cron.py          reconciliação disparada por Vercel Cron
│   │   │       ├── presenca.py      leitura: maquete, dashboard, drill-down
│   │   │       └── ws.py            WebSockets (/ws/campus, /ws/catracas)
│   │   ├── core/
│   │   │   ├── config.py            configuração por ambiente
│   │   │   └── clock.py             relógio real ou ancorado (demo)
│   │   ├── models/                  campus, academico, dashboard, enums
│   │   ├── services/
│   │   │   ├── presence_engine.py   ◄ núcleo: cruza grade × catraca × maquete
│   │   │   ├── allocation_engine.py alocação de alunos nas carteiras
│   │   │   ├── campus_state.py      estado único do processo
│   │   │   ├── dashboard_service.py projeção de leitura da diretoria
│   │   │   ├── jacad_client.py      adapter do ERP (REST | mock)
│   │   │   ├── realtime.py          hub de broadcast + relay do pub/sub
│   │   │   └── store/               estado compartilhado (memória | Redis)
│   │   │       ├── base.py          contrato EstadoStore
│   │   │       ├── memoria.py       instância única (padrão)
│   │   │       └── redis_store.py   várias instâncias / serverless
│   │   ├── data/campus_seed.py      planta real: 4 pavimentos, 63 ambientes
│   │   └── simulator/               gerador de fluxo de catracas
│   ├── smoke_test.py                fluxo ponta a ponta (memória)
│   ├── redis_test.py                store Redis + pub/sub entre instâncias
│   ├── redis_e2e_test.py            app completa sobre Redis
│   └── vercel.json                  maxDuration e crons
└── web-3d-frontend/                 React + Three.js + painel
    └── src/
        ├── components/
        │   ├── Canvas3D.tsx         cena, câmera, modos de visão
        │   ├── ChairNode.tsx        carteira (individual e instanciada)
        │   ├── RoomNode.tsx         sala: laje, paredes, rótulo, pulso
        │   ├── CatracaNode.tsx      torniquete com pulso a cada passagem
        │   ├── FloorMap.tsx         trilho de pavimentos com mini-indicador
        │   └── ControlPanel/        KPIs, curva, alertas, rankings, drawer
        ├── hooks/
        │   ├── useCampus3D.ts       store (zustand) + aplicação de deltas
        │   └── useSocket.ts         conexão com reconexão automática
        └── lib/                     tipos, tema Insted, cliente HTTP
```

---

## 6. Notas de implementação

**Por que o status das carteiras vive fora da árvore da maquete.**
A geometria muda raramente; o status muda a cada passagem. O front mantém um
dicionário plano `cadeira_id → status`, então aplicar um delta é O(1) e não
re-cria a árvore de pavimentos/salas.

**Por que as carteiras são instanciadas.**
São 2.742 carteiras. Renderizadas como *meshes* individuais seriam ~8.200 objetos.
Com `Instances` do drei, o campus inteiro sai em 3 *draw calls*.

**Por que sobrelotação não lança exceção.**
Turma maior que a sala é um fato operacional que a diretoria precisa ver e
resolver (há inclusive um endpoint de realocação), não um erro de programa.

**Deduplicação de eventos.**
Um painel pode manter mais de uma conexão viva (reconexão, StrictMode em dev).
O store descarta eventos com `id` já conhecido.

---

## 7. Deploy

### Estado compartilhado

Sem `REDIS_URL` o sistema roda em memória, em instância única — é o padrão e o
modo de desenvolvimento. Com `REDIS_URL` definido, presenças, campus, feed,
alertas, série e contadores passam ao Redis, e o broadcast entre instâncias
usa pub/sub. **A regra de negócio não muda**: os dois caminhos são validados
pelo mesmo roteiro de testes e produzem resultado idêntico.

Nem tudo precisou ir para o Redis. Topologia (vem do seed), espelho do JACAD
(vem do sync), alocação de carteiras (função pura da ordem das cadeiras e da
lista da turma) e janela de aulas (derivada do relógio) são **determinísticos**:
cada instância os reconstrói igual. Só o que muda a cada passagem é compartilhado.

### Vercel

O painel e a API vão em **dois projetos** do mesmo repositório.

**1. Painel (frontend)** — funciona sem configurar nada: o `vercel.json` e o
`package.json` na raiz já dizem como construir (`npm run build`) e o que
publicar (`apps/web-3d-frontend/dist`). Basta importar o repositório.

Depois que a API existir, aponte o painel para ela:

```
VITE_API_URL = https://SEU-BACKEND.vercel.app/api/v1
VITE_WS_URL  = wss://SEU-BACKEND.vercel.app/ws/campus
```

Sem essas variáveis o painel sobe, mas mostra *"Sem conexão com o motor de
ocupação"* com o endereço que tentou — é o comportamento esperado antes da API
estar no ar.

**2. API (backend)** — um segundo projeto, do mesmo repositório, com:

| Campo | Valor |
|---|---|
| Root Directory | `apps/backend-api` |
| Framework | FastAPI (detectado automaticamente) |

A Vercel encontra sozinha a instância `app` em `app/main.py`; o `vercel.json`
de lá só ajusta `maxDuration` e os crons. Variáveis:

```
REDIS_URL       = (injetada pela integração Redis do Marketplace)
CORS_ORIGINS    = https://SEU-PAINEL.vercel.app
SIMULADOR_ATIVO = false
CRON_SECRET     = (um valor aleatório qualquer)
JACAD_MODO_MOCK = false          # quando o ERP estiver ligado
JACAD_BASE_URL  = ...
JACAD_TOKEN     = ...
```

Três pontos de atenção:

- **`REDIS_URL` é obrigatório na Vercel.** Sem ele cada instância fica com um
  estado próprio: os painéis mostrariam números diferentes e uma passagem lida
  numa instância não chegaria à outra.
- **A conexão cai no `maxDuration`** (Hobby 300 s; Pro 800 s, o valor do
  `vercel.json`). O painel reconecta sozinho com *backoff* e recebe o snapshot
  inteiro no handshake, então o usuário não percebe.
- **O cron de 1 em 1 minuto exige plano Pro.** No Hobby o agendamento é diário,
  e a reconciliação — que abre e encerra aulas pela grade — ficaria parada entre
  as execuções. Nesse caso prefira a alternativa abaixo.

### Alternativa com processo contínuo

Render, Railway ou um container: nada precisa mudar. Sem `REDIS_URL` o
`LOOP_INTERNO` cuida da reconciliação a cada 5 s e o simulador funciona, o que
mantém o modo de apresentação intacto.

---

## 8. Verificação

```bash
cd apps/backend-api
python smoke_test.py
```

Valida a cadeia completa: carga do JACAD → abertura de aulas pela grade →
passagem na catraca promovendo a carteira a `OCUPADA` → rastreio do aluno na
maquete → saída caracterizando evasão → KPIs → handshake do WebSocket →
realocação de turma.

Para o caminho com estado compartilhado (usa `fakeredis`, não precisa de servidor):

```bash
pip install fakeredis && python redis_test.py && python redis_e2e_test.py
```

O primeiro valida o store e o pub/sub entre duas instâncias; o segundo sobe a
aplicação inteira sobre Redis e repete o fluxo do smoke, provando que o
resultado é idêntico ao modo memória. Ambos aceitam `REDIS_URL` para rodar
contra um servidor real.

```bash
cd apps/web-3d-frontend
npx tsc --noEmit && npm run build
```

---

## 9. Limitações conhecidas

- **Estado volátil.** Com Redis o estado sobrevive ao reinício da API e é
  compartilhado entre instâncias, mas as chaves expiram em 20 h: é o estado do
  dia letivo, não histórico. Para relatórios de frequência ao longo do semestre
  ainda falta persistir os `RegistroPresenca` encerrados em Postgres.
- **Comparativo com o dia anterior.** O campo `taxa_presenca_variacao` já
  circula na API, mas o `baseline_ontem` só será preenchido quando houver
  histórico persistido — hoje ele exibe `— vs ontem`.
- **Layout das salas.** As posições em `campus_seed.py` são uma aproximação
  fiel em número de salas, pavimentos e racks, porém as medidas devem ser
  conferidas contra a planta oficial antes da entrega final.
- **Sem autenticação.** O painel é aberto. Antes de expor fora da rede interna,
  colocar SSO institucional na frente.
