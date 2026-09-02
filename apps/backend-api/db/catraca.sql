-- Espelho da tabela de marcacoes do controle de acesso (catracas).
--
-- Origem: SQL Server ACESSOTA.TELESSVR.GAC_MARCACAO, no servidor 10.25.0.81.
-- Aqui ela e destino de replicacao: o backend le, nao escreve. Fica em schema
-- proprio de proposito - e dado de outro sistema, com convencoes de outro
-- fornecedor, e misturar com as tabelas do dominio faria alguem daqui a um ano
-- se perguntar o que MAR_TAG faz no nosso modelo.
--
-- Idempotente: pode rodar de novo sem apagar dado.
--
-- Traducoes de tipo que o Postgres exige, e o motivo de cada uma:
--
--   uniqueidentifier      -> uuid
--   newsequentialid()     -> gen_random_uuid()
--        O sequencial do SQL Server existe para nao fragmentar o indice
--        clusterizado, coisa que o Postgres nao tem. Aqui o valor so precisa
--        ser unico, e de todo modo ele vem preenchido da origem.
--   numeric(18,0)         -> bigint
--        E inteiro disfarcado: 18 digitos cabem nos 19 do bigint. Como bigint
--        indexa e compara melhor, e como MAR_PESSOA entra em junucao, vale a
--        troca. Se algum dia aparecer valor com casa decimal, a carga acusa.
--   money                 -> numeric(19,4)
--        O `money` do Postgres depende de lc_monetary do servidor: o mesmo
--        numero lido em outra sessao pode virar outro valor.
--   Latin1_General_CI_AS  -> (sem equivalente direto)
--        A origem compara texto ignorando maiusculas; o Postgres nao. Quem
--        casar MAR_CRACHA com o RA precisa normalizar dos dois lados - ver o
--        indice em upper(MAR_CRACHA) no fim do arquivo.

create schema if not exists catraca;

create table if not exists catraca.gac_marcacao (
    mar_id                    uuid primary key default gen_random_uuid(),
    mar_terminal              bigint,
    mar_pessoa                bigint,
    mar_datahora              timestamp,
    mar_funcao                bigint,
    mar_status                varchar(2),
    mar_statusbasico          char(1),
    mar_cracha                varchar(20),
    mar_end_ip                varchar(15),
    mar_codfnc                varchar(2),
    mar_sentido               char(1),
    mar_tipo                  char(1),
    mar_origem                char(1),
    mar_refeicao              bigint,
    mar_onoff                 char(1),
    mar_veiculo               bigint,
    mar_exportada             char(1) default '0',
    mar_planta                bigint,
    mar_quantidade            numeric(6,3),
    mar_preco                 numeric(19,4),
    mar_valortotal            numeric(19,4),
    mar_produto               bigint,
    mar_pro_tipopreco         char(1),
    mar_descricao             varchar(255),
    mar_tag                   varchar(255),
    mar_datahorainc           timestamp default now(),
    mar_placa                 varchar(10),
    mar_idimagem              bigint,
    mar_ticket                varchar(20),
    mar_temperatura           varchar(5),
    mar_usamascara            char(1),
    mar_centrocusto           bigint,
    mar_valortotaloriginal    numeric(19,4),
    mar_valorsubsidio         numeric(19,4),
    mar_exportada_ws          char(1) default '0',
    mar_ocupacao              bigint,
    mar_tipo_id               char(1),
    mar_usuario               bigint,
    mar_empresa               bigint
);

comment on table catraca.gac_marcacao is
    'Marcacoes das catracas, replicadas do SQL Server do controle de acesso. '
    'Somente leitura para esta aplicacao.';
comment on column catraca.gac_marcacao.mar_pessoa is
    'Id interno da pessoa NO CONTROLE DE ACESSO - nao e o RA do JaCad.';
comment on column catraca.gac_marcacao.mar_cracha is
    'Numero do cracha. E o candidato a chave de cruzamento com pessoa.identificador.';
comment on column catraca.gac_marcacao.mar_sentido is
    'Sentido da passagem (entrada/saida). Valores a confirmar com o fornecedor.';

-- Os cinco indices da origem, mantidos com os mesmos criterios.
create index if not exists idx_mar_datahora  on catraca.gac_marcacao (mar_datahora);
create index if not exists idx_mar_exportada on catraca.gac_marcacao (mar_exportada);
create index if not exists idx_mar_pessoa    on catraca.gac_marcacao (mar_pessoa);
create index if not exists idx_mar_status    on catraca.gac_marcacao (mar_status);
create index if not exists idx_mar_terminal  on catraca.gac_marcacao (mar_terminal);

-- Indices que a origem nao tem porque nao faz estas perguntas.
--
-- O painel pergunta "quem passou desde tal hora" a cada reconciliacao. Sem o
-- indice composto, o filtro por data pega o indice e o resto vira varredura,
-- que numa tabela de marcacoes cresce sem parar.
create index if not exists idx_mar_datahora_cracha
    on catraca.gac_marcacao (mar_datahora desc, mar_cracha);

-- A origem compara texto ignorando maiusculas; o Postgres nao. Este indice
-- deixa o cruzamento com o cadastro funcionar sem varrer a tabela.
create index if not exists idx_mar_cracha_normalizado
    on catraca.gac_marcacao (upper(mar_cracha));

-- Mesma politica das demais tabelas: o backend acessa por conexao direta, que
-- nao passa por RLS. Habilitar sem politicas bloqueia leitura anonima pelas
-- APIs REST geradas - e aqui ha dado de circulacao de pessoas.
alter table catraca.gac_marcacao enable row level security;
