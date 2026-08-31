-- ===========================================================================
-- Insted Virtual Campus - banco completo
--
-- Recria tudo do zero em qualquer PostgreSQL 15+: Supabase, Neon / Vercel
-- Postgres, Railway ou uma instancia local. Nao usa nada especifico de
-- provedor.
--
-- Uso:
--   psql "$DATABASE_URL" -f db/schema.sql
-- ou cole no editor SQL do provedor.
--
-- Idempotente: rodar de novo nao duplica nada nem sobrescreve edicoes feitas.
-- Gerado a partir de app/data/campus_seed.py (plantas Sigma rev. 05/2025).
-- ===========================================================================

-- --------------------------------------------------------- campus fisico

create table if not exists predio (
    id            smallint generated always as identity primary key,
    codigo        text not null unique,
    nome          text not null,
    endereco      text,
    ativo         boolean not null default true,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create table if not exists pavimento (
    id            smallint generated always as identity primary key,
    predio_id     smallint not null references predio (id) on delete cascade,
    codigo        text not null,
    nome          text not null,
    ordem         smallint not null,
    altura_y      numeric(6, 2) not null default 0,
    descricao     text,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    constraint pavimento_codigo_por_predio unique (predio_id, codigo),
    constraint pavimento_ordem_por_predio unique (predio_id, ordem)
);

comment on column pavimento.ordem is
    'Terreo = 0, sobe a cada andar. Define o empilhamento na maquete.';

create table if not exists sala (
    id                 integer generated always as identity primary key,
    pavimento_id       smallint not null references pavimento (id) on delete cascade,
    codigo             text not null unique,
    codigo_planta      text,
    codigo_ensalamento text,
    nome               text not null,
    tipo               text not null,
    capacidade         smallint not null default 0,
    rack_id            text,
    ativa              boolean not null default true,
    -- Geometria da maquete, em metros, origem no centro do predio
    pos_x              numeric(8, 2),
    pos_z              numeric(8, 2),
    largura            numeric(8, 2),
    profundidade       numeric(8, 2),
    observacao         text,
    criado_em          timestamptz not null default now(),
    atualizado_em      timestamptz not null default now(),

    constraint sala_capacidade_nao_negativa check (capacidade >= 0),
    constraint sala_tipo_conhecido check (tipo in (
        'AULA', 'LABORATORIO', 'AUDITORIO', 'TEATRO', 'MULTIUSO', 'ESTUDO',
        'BIBLIOTECA', 'SECRETARIA', 'ADMIN', 'CPD', 'CIRCULACAO',
        'COWORKING', 'APOIO'
    ))
);

comment on column sala.codigo is
    'Chave usada pelo motor de presenca e pela maquete (ex.: S1_08).';
comment on column sala.codigo_ensalamento is
    'Codigo da Secretaria (01A/01B/01C). A preencher.';

create index if not exists sala_por_pavimento on sala (pavimento_id);
create index if not exists sala_por_tipo on sala (tipo) where ativa;
create index if not exists sala_por_ensalamento on sala (codigo_ensalamento)
    where codigo_ensalamento is not null;

-- ------------------------------------------------------------- pessoas

create table if not exists tipo_pessoa (
    codigo                 text primary key,
    nome                   text not null,
    plural                 text not null,
    conta_presenca_em_aula boolean not null default false,
    cor                    text,
    ordem                  smallint not null default 100,
    ativo                  boolean not null default true,
    criado_em              timestamptz not null default now(),
    atualizado_em          timestamptz not null default now(),

    constraint tipo_pessoa_codigo_maiusculo check (codigo = upper(codigo))
);

comment on column tipo_pessoa.conta_presenca_em_aula is
    'Verdadeiro para quem ocupa carteira em aula. Falso para quem apenas '
    'circula no campus (funcionario, terceirizado, visitante).';

create table if not exists pessoa (
    id              integer generated always as identity primary key,
    identificador   text not null unique,
    nome            text not null,
    tipo_codigo     text not null references tipo_pessoa (codigo),
    email           text,
    curso           text,
    turma_id        text,
    periodo         smallint,
    setor           text,
    cargo           text,
    situacao        text not null default 'ATIVO',
    origem          text not null default 'JACAD',
    ativo           boolean not null default true,
    sincronizado_em timestamptz,
    observacao      text,
    criado_em       timestamptz not null default now(),
    atualizado_em   timestamptz not null default now(),

    constraint pessoa_origem_valida check (origem in ('JACAD', 'CATRACA', 'MANUAL')),
    constraint pessoa_periodo_plausivel check (periodo is null or periodo between 1 and 20)
);

comment on column pessoa.identificador is
    'RA / matricula. E a chave do cruzamento: o cracha da catraca usa o mesmo.';
comment on column pessoa.origem is
    'De onde o registro veio. JACAD e reescrito a cada sync; MANUAL nao.';

create index if not exists pessoa_por_tipo on pessoa (tipo_codigo) where ativo;
create index if not exists pessoa_por_turma on pessoa (turma_id) where turma_id is not null;
create index if not exists pessoa_por_nome on pessoa (lower(nome));

-- ------------------------------------------------------------- acesso

-- Senha em hash scrypt. Crie a primeira conta com `python criar_usuario.py`,
-- nunca por INSERT.
create table if not exists usuario (
    id            integer generated always as identity primary key,
    email         text not null unique,
    nome          text not null,
    senha_hash    text not null,
    papel         text not null default 'LEITURA',
    ativo         boolean not null default true,
    ultimo_acesso timestamptz,
    criado_em     timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),

    constraint usuario_papel_valido
        check (papel in ('ADMIN', 'SECRETARIA', 'LEITURA')),
    constraint usuario_email_minusculo check (email = lower(email))
);

create index if not exists usuario_ativo on usuario (email) where ativo;

create table if not exists sala_auditoria (
    id           bigint generated always as identity primary key,
    sala_codigo  text not null,
    acao         text not null,
    usuario_id   integer references usuario (id) on delete set null,
    usuario_nome text,
    antes        jsonb,
    depois       jsonb,
    criado_em    timestamptz not null default now(),

    constraint sala_auditoria_acao_valida
        check (acao in ('CRIACAO', 'EDICAO', 'DESATIVACAO', 'REATIVACAO'))
);

create index if not exists sala_auditoria_por_sala
    on sala_auditoria (sala_codigo, criado_em desc);

-- --------------------------------------------------------- parametros

-- Fora daqui de proposito: DATABASE_URL, JWT_SECRET, REDIS_URL e JACAD_TOKEN.
-- Os tres primeiros sao necessarios antes de existir conexao com o banco;
-- o ultimo e segredo que nao deve ser legivel por quem abre o painel.
create table if not exists parametro (
    chave          text primary key,
    valor          text,
    tipo           text not null,
    categoria      text not null,
    rotulo         text not null,
    descricao      text,
    unidade        text,
    minimo         numeric,
    maximo         numeric,
    ordem          smallint not null default 100,
    atualizado_por text,
    atualizado_em  timestamptz,
    criado_em      timestamptz not null default now(),

    constraint parametro_tipo_valido check (tipo in ('INTEIRO', 'BOOLEANO', 'TEXTO')),
    constraint parametro_chave_maiuscula check (chave = upper(chave))
);

comment on column parametro.valor is
    'Nulo = nao definido aqui; vale a variavel de ambiente ou o padrao.';

create table if not exists parametro_auditoria (
    id           bigint generated always as identity primary key,
    chave        text not null,
    valor_antes  text,
    valor_depois text,
    usuario_nome text,
    criado_em    timestamptz not null default now()
);

create index if not exists parametro_auditoria_por_chave
    on parametro_auditoria (chave, criado_em desc);

-- ------------------------------------------------------ gatilhos e views

create or replace function toca_atualizado_em()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.atualizado_em := now();
    return new;
end;
$$;

drop trigger if exists predio_atualizado on predio;
create trigger predio_atualizado before update on predio
    for each row execute function toca_atualizado_em();

drop trigger if exists pavimento_atualizado on pavimento;
create trigger pavimento_atualizado before update on pavimento
    for each row execute function toca_atualizado_em();

drop trigger if exists sala_atualizada on sala;
create trigger sala_atualizada before update on sala
    for each row execute function toca_atualizado_em();

drop trigger if exists usuario_atualizado on usuario;
create trigger usuario_atualizado before update on usuario
    for each row execute function toca_atualizado_em();

drop trigger if exists tipo_pessoa_atualizado on tipo_pessoa;
create trigger tipo_pessoa_atualizado before update on tipo_pessoa
    for each row execute function toca_atualizado_em();

drop trigger if exists pessoa_atualizada on pessoa;
create trigger pessoa_atualizada before update on pessoa
    for each row execute function toca_atualizado_em();

-- security_invoker: sem isso a view roda com os privilegios de quem a criou e
-- ignora o RLS de quem consulta, abrindo o que as tabelas fecham.
create or replace view vw_sala_completa
with (security_invoker = on) as
select
    s.id, s.codigo, s.codigo_planta, s.codigo_ensalamento,
    s.nome as sala, s.tipo, s.capacidade, s.rack_id, s.ativa,
    s.pos_x, s.pos_z, s.largura, s.profundidade,
    p.codigo  as pavimento_codigo,
    p.nome    as pavimento,
    p.ordem   as pavimento_ordem,
    p.altura_y,
    pr.codigo as predio_codigo,
    pr.nome   as predio
from sala s
join pavimento p on p.id = s.pavimento_id
join predio pr on pr.id = p.predio_id;

create or replace view vw_pessoa_completa
with (security_invoker = on) as
select
    p.id, p.identificador, p.nome, p.email, p.curso, p.turma_id, p.periodo,
    p.setor, p.cargo, p.situacao, p.origem, p.ativo, p.sincronizado_em,
    t.codigo as tipo,
    t.nome   as tipo_nome,
    t.plural as tipo_plural,
    t.conta_presenca_em_aula,
    t.cor    as tipo_cor,
    t.ordem  as tipo_ordem
from pessoa p
join tipo_pessoa t on t.codigo = p.tipo_codigo;

-- O backend acessa por conexao direta, que nao passa por RLS. Habilitar sem
-- politicas bloqueia leitura anonima pelas APIs REST geradas.
alter table predio              enable row level security;
alter table pavimento           enable row level security;
alter table sala                enable row level security;
alter table tipo_pessoa         enable row level security;
alter table pessoa              enable row level security;
alter table usuario             enable row level security;
alter table sala_auditoria      enable row level security;
alter table parametro           enable row level security;
alter table parametro_auditoria enable row level security;

-- ---------------------------------------------------------- carga inicial

insert into predio (codigo, nome)
values ('SEDE', 'Campus Sede')
on conflict (codigo) do nothing;

insert into tipo_pessoa (codigo, nome, plural, conta_presenca_em_aula, cor, ordem)
values
    ('ALUNO',        'Aluno',        'Alunos',        true,  '#00C9B7', 10),
    ('PROFESSOR',    'Professor',    'Professores',   false, '#3B82F6', 20),
    ('FUNCIONARIO',  'Funcionario',  'Funcionarios',  false, '#F59E0B', 30),
    ('TERCEIRIZADO', 'Terceirizado', 'Terceirizados', false, '#8b949e', 40),
    ('VISITANTE',    'Visitante',    'Visitantes',    false, '#A855F7', 50)
on conflict (codigo) do nothing;

insert into parametro (chave, tipo, categoria, rotulo, descricao, unidade,
                       minimo, maximo, ordem) values
    ('TOLERANCIA_ATRASO_MIN', 'INTEIRO', 'PRESENCA', 'Tolerancia de atraso',
     'Entrada ate este tempo apos o inicio ainda conta como PRESENTE.',
     'minutos', 0, 120, 10),
    ('JANELA_CHEGADA_ANTECIPADA_MIN', 'INTEIRO', 'PRESENCA', 'Janela de chegada',
     'Quanto antes do inicio a aula abre e as carteiras ficam reservadas.',
     'minutos', 0, 240, 20),
    ('LIMIAR_BAIXA_PRESENCA', 'INTEIRO', 'PRESENCA', 'Alerta de baixa presenca',
     'Abaixo desta taxa a sala entra em alerta para a diretoria.',
     '%', 0, 100, 30),
    ('CATRACA_TIMEOUT_S', 'INTEIRO', 'PRESENCA', 'Catraca sem sinal',
     'Tempo sem passagem para considerar o equipamento fora do ar.',
     'segundos', 60, 7200, 40),
    ('JACAD_BASE_URL', 'TEXTO', 'INTEGRACAO', 'Endereco do JACAD',
     'URL base da API do ERP. Vazio mantem o modo simulado.',
     null, null, null, 10),
    ('JACAD_MODO_MOCK', 'BOOLEANO', 'INTEGRACAO', 'Usar dados simulados do JACAD',
     'Ligado usa o conjunto sintetico. Desligue com o ERP acessivel.',
     null, null, null, 20),
    ('JACAD_SYNC_INTERVAL_S', 'INTEIRO', 'INTEGRACAO', 'Intervalo de sincronizacao',
     'De quanto em quanto tempo o ERP e relido.',
     'segundos', 60, 86400, 30),
    ('SIMULADOR_ATIVO', 'BOOLEANO', 'INTEGRACAO', 'Simulador de catracas',
     'Gera passagens a partir da grade. Desligue em producao.',
     null, null, null, 40),
    ('TIMEZONE', 'TEXTO', 'SISTEMA', 'Fuso do campus',
     'A grade e hora de parede local. Exige reinicio para valer.',
     null, null, null, 10),
    ('TICK_DASHBOARD_S', 'INTEIRO', 'SISTEMA', 'Atualizacao do painel',
     'Periodo do recalculo dos indicadores enviado aos paineis.',
     'segundos', 1, 300, 20),
    ('MAX_EVENTOS_FEED', 'INTEIRO', 'SISTEMA', 'Passagens no feed',
     'Quantas passagens recentes o painel guarda.',
     'eventos', 10, 500, 30)
on conflict (chave) do nothing;


insert into pavimento (predio_id, codigo, nome, ordem, altura_y, descricao)
select pr.id, v.codigo, v.nome, v.ordem, v.altura_y, v.descricao
from predio pr, (values
    ('TERREO', 'Terreo', 0::smallint, 0.00, 'Secretaria, biblioteca, teatro (auditorio 314), 2 laboratorios e salas 01-09'),
    ('PAV_1', '1o Pavimento', 1, 4.20, '16 salas de aula, laboratorio de informatica, 2 auditorios e multiuso'),
    ('PAV_2', '2o Pavimento', 2, 8.40, '20 salas de aula, 2 laboratorios, sala de estudos, diretoria e CPD'),
    ('TERRACO', '3o Pavimento / Terraco', 3, 12.60, 'Administrativo: diretoria, coordenacao, professores, coworking e cantinas')
) as v(codigo, nome, ordem, altura_y, descricao)
where pr.codigo = 'SEDE'
on conflict (predio_id, codigo) do nothing;

insert into sala (pavimento_id, codigo, codigo_planta, nome, tipo,
                  capacidade, rack_id, pos_x, pos_z, largura, profundidade)
select p.id, v.codigo, v.codigo_planta, v.nome, v.tipo,
       v.capacidade, v.rack_id, v.pos_x, v.pos_z, v.largura, v.profundidade
from pavimento p
join predio pr on pr.id = p.predio_id and pr.codigo = 'SEDE',
(values
    ('TERREO', 'T_AUDITORIO_314_LUGARES', 'AUDITÓRIO (314 LUGARES)', 'Auditório (314 Lugares)', 'TEATRO', 314::smallint, 'RACK_4/5/6', -32.34, -19.84, 12.17, 13.23),
    ('TERREO', 'T_BIBLIOTECA', 'BIBLIOTECA', 'Biblioteca', 'BIBLIOTECA', 0, 'RACK_4/5/6', -32.25, 27.46, 12.02, 11.09),
    ('TERREO', 'T_LOBBY_AUDITORIO', 'LOBBY AUDITÓRIO', 'Lobby Auditório', 'CIRCULACAO', 0, 'RACK_4/5/6', -26.91, -4.69, 11.0, 11.0),
    ('TERREO', 'T_RECEPCAO_SECRETARIA', 'RECEPÇÃO SECRETARIA', 'Recepção Secretaria', 'SECRETARIA', 0, 'RACK_4/5/6', -31.59, 15.85, 7.79, 7.78),
    ('TERREO', 'ST_01', 'SALA 01', 'Sala 01 (Terreo)', 'AULA', 40, 'RACK_4/5/6', -19.0, 15.85, 9.18, 9.14),
    ('TERREO', 'ST_02', 'SALA 02', 'Sala 02 (Terreo)', 'AULA', 49, 'RACK_4/5/6', -11.13, 21.14, 6.52, 8.13),
    ('TERREO', 'ST_03', 'SALA 03', 'Sala 03 (Terreo)', 'AULA', 49, 'RACK_4/5/6', -5.71, 20.96, 6.51, 8.14),
    ('TERREO', 'ST_04', 'SALA 04', 'Sala 04 (Terreo)', 'AULA', 48, 'RACK_4/5/6', 1.19, 17.69, 4.3, 11.36),
    ('TERREO', 'ST_05', 'SALA 05 - LAB. INFORMÁTICA', 'Sala 05 - Lab. Informática (Terreo)', 'LABORATORIO', 60, 'RACK_4/5/6', 4.85, 13.48, 5.14, 16.68),
    ('TERREO', 'ST_06', 'SALA 06 - LAB. INFORMÁTICA', 'Sala 06 - Lab. Informática (Terreo)', 'LABORATORIO', 60, 'RACK_4/5/6', 4.85, 27.47, 5.14, 16.68),
    ('TERREO', 'ST_07', 'SALA 07', 'Sala 07 (Terreo)', 'AULA', 48, 'RACK_4/5/6', 1.15, 29.09, 4.3, 11.36),
    ('TERREO', 'ST_08', 'SALA 08', 'Sala 08 (Terreo)', 'AULA', 49, 'RACK_4/5/6', -5.61, 27.57, 6.29, 8.43),
    ('TERREO', 'ST_09', 'SALA 09', 'Sala 09 (Terreo)', 'AULA', 49, 'RACK_4/5/6', -10.66, 27.73, 6.3, 8.41),
    ('PAV_1', '1_AUDITORIO_01_93_LUGARE', 'AUDITÓRIO 01 - 93 LUGARES', 'Auditório 01 - 93 Lugares', 'AUDITORIO', 93, 'RACK_2', 21.66, 31.91, 13.23, 12.17),
    ('PAV_1', '1_AUDITORIO_02_91_LUGARE', 'AUDITÓRIO 02 - 91 LUGARES', 'Auditório 02 - 91 Lugares', 'AUDITORIO', 91, 'RACK_2', 2.29, 32.79, 13.23, 13.23),
    ('PAV_1', '1_MULTIUSO', 'MULTIUSO', 'Multiuso', 'MULTIUSO', 30, 'RACK_2', -18.64, 19.9, 12.17, 6.99),
    ('PAV_1', 'S1_01', 'SALA 01', 'Sala 01 (1o Pav)', 'AULA', 40, 'RACK_2', -19.8, -44.84, 8.53, 9.39),
    ('PAV_1', 'S1_02', 'SALA 02', 'Sala 02 (1o Pav)', 'AULA', 60, 'RACK_2', -19.87, -34.39, 8.47, 8.89),
    ('PAV_1', 'S1_03', 'SALA 03', 'Sala 03 (1o Pav)', 'AULA', 60, 'RACK_2', -19.9, -24.73, 8.42, 8.89),
    ('PAV_1', 'S1_04', 'SALA 04', 'Sala 04 (1o Pav)', 'AULA', 60, 'RACK_2', -19.82, -14.97, 8.27, 9.04),
    ('PAV_1', 'S1_05', 'SALA 05', 'Sala 05 (1o Pav)', 'AULA', 35, 'RACK_2', -19.84, 12.3, 8.62, 6.99),
    ('PAV_1', 'S1_06', 'SALA 06', 'Sala 06 (1o Pav)', 'AULA', 49, 'RACK_2', -5.05, 10.43, 7.93, 12.17),
    ('PAV_1', 'S1_07', 'SALA 07', 'Sala 07 (1o Pav)', 'AULA', 49, 'RACK_2', 3.57, 9.94, 7.93, 13.23),
    ('PAV_1', 'S1_08', 'SALA 08', 'Sala 08 (1o Pav)', 'AULA', 48, 'RACK_2', 12.5, 7.5, 8.47, 12.17),
    ('PAV_1', 'S1_09', 'SALA 09', 'Sala 09 (1o Pav)', 'AULA', 56, 'RACK_2', 15.92, 12.86, 13.23, 12.17),
    ('PAV_1', 'S1_10', 'SALA 10', 'Sala 10 (1o Pav)', 'AULA', 45, 'RACK_2', -31.35, 36.12, 13.23, 11.67),
    ('PAV_1', 'S1_11', 'SALA 11', 'Sala 11 (1o Pav)', 'AULA', 40, 'RACK_2', -30.87, 23.58, 12.17, 11.38),
    ('PAV_1', 'S1_12', 'SALA 12', 'Sala 12 (1o Pav)', 'AULA', 36, 'RACK_2', -29.21, 11.21, 8.62, 11.38),
    ('PAV_1', 'S1_13', 'SALA 13', 'Sala 13 (1o Pav)', 'AULA', 54, 'RACK_2', -28.81, -14.82, 8.27, 8.88),
    ('PAV_1', 'S1_14', 'SALA 14', 'Sala 14 (1o Pav)', 'AULA', 54, 'RACK_2', -29.05, -24.45, 8.42, 8.84),
    ('PAV_1', 'S1_15', 'SALA 15', 'Sala 15 (1o Pav)', 'AULA', 54, 'RACK_2', -29.07, -34.06, 8.47, 8.84),
    ('PAV_1', 'S1_16', 'SALA 16', 'Sala 16 (1o Pav)', 'AULA', 40, 'RACK_2', -29.07, -45.02, 8.53, 9.69),
    ('PAV_2', '2_CPD', 'CPD', 'Cpd', 'CPD', 0, 'RACK_1', -19.98, 17.1, 12.17, 9.38),
    ('PAV_2', 'S2_01', 'SALA 01', 'Sala 01 (2o Pav)', 'AULA', 40, 'RACK_1', -19.86, -46.66, 8.65, 9.39),
    ('PAV_2', 'S2_02', 'SALA 02', 'Sala 02 (2o Pav)', 'AULA', 60, 'RACK_1', -19.91, -36.2, 8.57, 8.89),
    ('PAV_2', 'S2_03', 'SALA 03', 'Sala 03 (2o Pav)', 'AULA', 60, 'RACK_1', -19.95, -26.54, 8.51, 8.89),
    ('PAV_2', 'S2_04', 'SALA 04', 'Sala 04 (2o Pav)', 'AULA', 60, 'RACK_1', -19.98, -16.78, 8.57, 9.04),
    ('PAV_2', 'S2_05', 'SALA 05', 'Sala 05 (2o Pav)', 'AULA', 50, 'RACK_1', -14.48, 6.91, 8.4, 9.38),
    ('PAV_2', 'S2_06', 'SALA 06', 'Sala 06 (2o Pav)', 'AULA', 49, 'RACK_1', -4.71, 8.16, 7.15, 13.23),
    ('PAV_2', 'S2_07', 'SALA 07', 'Sala 07 (2o Pav)', 'AULA', 49, 'RACK_1', 3.05, 8.16, 7.15, 13.23),
    ('PAV_2', 'S2_08', 'SALA 08', 'Sala 08 (2o Pav)', 'AULA', 48, 'RACK_1', 11.32, 7.82, 7.99, 13.23),
    ('PAV_2', 'S2_09', 'SALA 09', 'Sala 09 (2o Pav)', 'AULA', 32, 'RACK_1', 20.45, 9.67, 8.73, 13.23),
    ('PAV_2', 'S2_10', 'SALA 10', 'Sala 10 (2o Pav)', 'AULA', 40, 'RACK_1', 19.57, 31.91, 7.39, 13.23),
    ('PAV_2', 'S2_11', 'SALA 11', 'Sala 11 (2o Pav)', 'AULA', 48, 'RACK_1', 11.54, 32.57, 7.39, 13.23),
    ('PAV_2', 'S2_12', 'SALA 12', 'Sala 12 (2o Pav)', 'AULA', 49, 'RACK_1', 2.93, 31.73, 6.76, 13.23),
    ('PAV_2', 'S2_13', 'SALA 13', 'Sala 13 (2o Pav)', 'AULA', 49, 'RACK_1', -4.41, 31.36, 6.76, 13.23),
    ('PAV_2', 'S2_14', 'SALA 14', 'Sala 14 (2o Pav)', 'AULA', 45, 'RACK_1', -31.27, 33.63, 13.23, 9.78),
    ('PAV_2', 'S2_15', 'SALA 15', 'Sala 15 (2o Pav)', 'AULA', 45, 'RACK_1', -30.75, 23.01, 12.17, 9.78),
    ('PAV_2', 'S2_16', 'SALA 16', 'Sala 16 (2o Pav)', 'AULA', 45, 'RACK_1', -31.27, 11.77, 13.23, 10.17),
    ('PAV_2', 'S2_17', 'SALA 17', 'Sala 17 (2o Pav)', 'AULA', 54, 'RACK_1', -29.3, -16.75, 8.57, 8.48),
    ('PAV_2', 'S2_18', 'SALA 18', 'Sala 18 (2o Pav)', 'AULA', 35, 'RACK_1', -29.2, -25.97, 8.51, 8.48),
    ('PAV_2', 'S2_19', 'SALA 19', 'Sala 19 (2o Pav)', 'AULA', 54, 'RACK_1', -29.23, -36.01, 8.57, 9.0),
    ('PAV_2', 'S2_20', 'SALA 20', 'Sala 20 (2o Pav)', 'AULA', 40, 'RACK_1', -29.27, -46.63, 8.65, 9.53),
    ('PAV_2', '2_SALA_DE_ESTUDOS', 'SALA DE ESTUDOS', 'Sala De Estudos (2o Pav)', 'ESTUDO', 30, 'RACK_1', -14.0, -6.74, 13.23, 11.55),
    ('PAV_2', '2_SALA_DIRETORIA_E_REUNI', 'SALA DIRETORIA E REUNIÃO', 'Sala Diretoria E Reunião (2o Pav)', 'ADMIN', 0, 'RACK_1', -34.9, -5.69, 13.23, 11.63),
    ('TERRACO', '3_ATENDIMENTOS', 'ATENDIMENTOS', 'Atendimentos', 'ADMIN', 0, 'RACK_3', 2.67, 10.15, 3.97, 12.17),
    ('TERRACO', '3_COWORKING', 'COWORKING', 'Coworking', 'COWORKING', 0, 'RACK_3', 19.21, 10.59, 3.97, 12.17),
    ('TERRACO', '3_NUCLEO', 'NÚCLEO', 'Núcleo', 'ADMIN', 0, 'RACK_3', -8.38, 8.29, 8.21, 12.17),
    ('TERRACO', 'S3_01', 'SALA 01', 'Sala 01 (Terraco)', 'AULA', 0, 'RACK_3', 3.31, 10.07, 3.97, 12.17),
    ('TERRACO', 'S3_02', 'SALA 02', 'Sala 02 (Terraco)', 'AULA', 0, 'RACK_3', 19.96, 10.47, 3.97, 12.17),
    ('TERRACO', '3_SALA_COORDENADORES', 'SALA COORDENADORES', 'Sala Coordenadores (Terraco)', 'ADMIN', 0, 'RACK_3', -20.68, -28.55, 12.17, 9.21),
    ('TERRACO', '3_SALA_DIRETORIA', 'SALA DIRETORIA', 'Sala Diretoria (Terraco)', 'ADMIN', 0, 'RACK_3', -20.32, -38.56, 12.17, 9.21),
    ('TERRACO', '3_SALA_PROFESSORES', 'SALA PROFESSORES', 'Sala Professores (Terraco)', 'ADMIN', 0, 'RACK_3', -17.61, -17.43, 12.17, 11.1)
) as v(pav, codigo, codigo_planta, nome, tipo, capacidade, rack_id,
       pos_x, pos_z, largura, profundidade)
where p.codigo = v.pav
on conflict (codigo) do nothing;

-- Conferencia: 1 predio, 4 pavimentos, 63 salas, 2742 lugares, 5 tipos,
-- 11 parametros no catalogo.
select
    (select count(*) from predio)      as predios,
    (select count(*) from pavimento)   as pavimentos,
    (select count(*) from sala)        as salas,
    (select sum(capacidade) from sala) as lugares,
    (select count(*) from tipo_pessoa) as tipos_pessoa,
    (select count(*) from parametro)   as parametros;
