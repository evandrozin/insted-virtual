-- Espelho parcial do cadastro de pessoas do controle de acesso.
--
-- Origem: SQL Server ACESSOTA.TELESSVR.GAC_PESSOA. Existe para uma coisa so:
-- traduzir GAC_MARCACAO.MAR_PESSOA (id interno da catraca) para a matricula, e
-- dai para pessoa.identificador do nosso cadastro. Sem esta ponte, as 14.936
-- marcacoes nao dizem quem passou.
--
-- PARCIAL DE PROPOSITO. A origem tem 160 colunas; aqui vao 8.
--
-- O que ficou de fora, e por que:
--
--   PES_FOTO, PES_FOTOFACE, PES_FOTODOC1, PES_FOTODOC2, PES_OBS
--       Colunas `image`: retrato e biometria facial. Tirar isso de dentro do
--       predio para uma nuvem e decisao de quem responde pelos dados da
--       instituicao, nao efeito colateral de uma integracao de presenca.
--   PES_CPF, PES_RG, PES_PIS, PES_PASSAPORTE, PES_DATANASC
--       Documentos. Nao entram no cruzamento enquanto a matricula servir. Se um
--       dia a matricula falhar, o CPF e o plano B - e ai a decisao e consciente.
--   PES_ENDERECO, PES_CEP, PES_TELEFONE1/2, PES_CELULAR, PES_CONTATO...
--       Contato e domicilio. O painel mostra ocupacao de sala; nada disso o
--       ajuda a fazer isso.
--   PES_SENHA, PES_LOGIN_AD, PES_LOGINPGA
--       Credenciais. Nunca.
--   As ~100 colunas de jornada, grupo de acesso, refeitorio, leito hospitalar e
--       sincronizacao com equipamento sao do dominio do fornecedor.
--
-- Idempotente: pode rodar de novo sem apagar dado.

create table if not exists catraca.gac_pessoa (
    pes_id          bigint primary key,
    pes_nome        varchar(255),
    pes_matricula   varchar(20),
    pes_status      char(1),
    pes_visitante   char(1),
    tippes_id       bigint,
    pes_setor       varchar(255),
    pes_cargo       varchar(255),
    replicado_em    timestamp not null default now()
);

comment on table catraca.gac_pessoa is
    'Recorte do cadastro do controle de acesso, so o necessario para traduzir '
    'MAR_PESSOA em matricula. Ver o cabecalho de db/catraca_pessoa.sql para o '
    'que foi deixado de fora e por que.';
comment on column catraca.gac_pessoa.pes_id is
    'Chave que MAR_PESSOA referencia.';
comment on column catraca.gac_pessoa.pes_matricula is
    'Candidata a casar com pessoa.identificador (o RA do JaCad).';

-- O cruzamento acontece por matricula, ignorando maiusculas: a origem compara
-- assim (Latin1_General_CI_AS) e o Postgres nao.
-- O indice acompanha a forma usada na juncao: sem os zeros a esquerda.
create index if not exists idx_pes_matricula_normalizada
    on catraca.gac_pessoa (ltrim(trim(pes_matricula), '0'));
create index if not exists idx_pes_status on catraca.gac_pessoa (pes_status);

alter table catraca.gac_pessoa enable row level security;

-- Quem passou, com nome e matricula resolvidos. Existe para o backend nao ter
-- que repetir a juncao em toda consulta, e para deixar num lugar so as duas
-- regras que se descobriu por medicao:
--
--   mar_statusbasico = '1' e passagem autorizada. Sem esse filtro entrariam as
--   1.840 tentativas que a catraca barrou.
--
--   mar_sentido: '0' entrada, '1' saida, '2' recusa. Confirmado pelo padrao do
--   dia - '0' foi o primeiro evento 5.919 vezes contra 685, e '1' o ultimo
--   4.232 vezes; os picos batem com a chegada do noturno as 18h e a saida as 21h.
create or replace view catraca.vw_passagem
with (security_invoker = on) as
select
    m.mar_id,
    m.mar_datahora                                    as momento,
    m.mar_terminal                                    as terminal,
    -- Da marcacao, nao do join: a pessoa e identificada na propria passagem, e
    -- tirar isso do cadastro faria a contagem de presentes zerar enquanto
    -- gac_pessoa nao estivesse replicada - campus cheio parecendo vazio.
    m.mar_pessoa                                      as pes_id,
    p.pes_nome                                        as nome_na_catraca,
    p.pes_matricula                                   as matricula_bruta,
    -- O cracha guarda o identificador preenchido com zeros a esquerda ate 12
    -- caracteres: "001010002874" e o RA 1010002874. Comparar sem tirar os zeros
    -- nao casa nada - foram 0 de 2.306 antes disto, e 1.378 depois.
    --
    -- Nem toda matricula e RA: ~115 tem 11 digitos e sao CPF, de funcionarios e
    -- professores, que o JaCad identifica de outro jeito. Elas ficam sem
    -- correspondencia, e e o esperado.
    nullif(ltrim(trim(p.pes_matricula), '0'), '')     as matricula,
    case m.mar_sentido
        when '0' then 'ENTRADA'
        when '1' then 'SAIDA'
        else 'RECUSA'
    end                                               as sentido,
    m.mar_status                                      as codigo_status
from catraca.gac_marcacao m
left join catraca.gac_pessoa p on p.pes_id = m.mar_pessoa
where m.mar_statusbasico = '1';
