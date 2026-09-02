# Replicação das marcações das catracas

O controle de acesso roda em SQL Server na rede interna (`10.25.0.81`). O backend
roda no Render, fora dela — não há rota até esse endereço. Por isso a integração
é por **cópia**: um job no SQL Server empurra as marcações para
`catraca.gac_marcacao` no Postgres, e o backend só lê de lá.

## Marca d'água: use `MAR_DATAHORAINC`, não `MAR_DATAHORA`

O job precisa saber de onde continuar. A tentação é filtrar por `MAR_DATAHORA`,
mas essa é a hora **em que a pessoa passou** — e uma catraca que ficou offline
grava as passagens depois, com a hora original. Filtrando por ela, essas
marcações entram no banco com data anterior à última já copiada e o job nunca as
vê.

`MAR_DATAHORAINC` é a hora em que a linha **foi inserida**, e essa só cresce.

Não é preciso guardar a marca d'água em lugar nenhum: ela é o que já chegou.

```sql
-- no Postgres
select coalesce(max(mar_datahorainc), '2000-01-01') from catraca.gac_marcacao;
```

Recue 10 minutos dessa marca a cada execução. A sobreposição cobre transações
que ainda não tinham committado na leitura anterior, e não duplica nada porque
`MAR_ID` é chave primária — ver o `on conflict` abaixo.

## Não use `MAR_EXPORTADA` nem `MAR_EXPORTADA_WS`

Essas duas colunas existem e parecem feitas para isto. **São do fornecedor.** O
sistema de controle de acesso as usa para marcar o que ele já exportou nas
integrações dele; escrever nelas quebra essas integrações, e o estrago aparece
semanas depois, em outro sistema, sem ligação óbvia com o que fizemos aqui.

A marca d'água por `MAR_DATAHORAINC` não escreve nada na origem — o job só lê.

## A consulta na origem

```sql
DECLARE @desde datetime = /* marca d'água do Postgres, menos 10 minutos */;

SELECT  MAR_ID, MAR_TERMINAL, MAR_PESSOA, MAR_DATAHORA, MAR_FUNCAO,
        MAR_STATUS, MAR_STATUSBASICO, MAR_CRACHA, MAR_SENTIDO,
        MAR_TIPO, MAR_ORIGEM, MAR_DATAHORAINC
FROM    ACESSOTA.TELESSVR.GAC_MARCACAO
WHERE   MAR_DATAHORAINC > @desde
ORDER BY MAR_DATAHORAINC;
```

São 12 das 39 colunas — as que dizem quem passou, quando, por onde e em que
sentido. As outras 27 são de refeitório, veículo, temperatura e imagem: a tabela
destino as tem, e nada impede mandá-las, mas elas não entram em nada que o painel
faça e só engordam a transferência.

## A gravação no destino

```sql
INSERT INTO catraca.gac_marcacao
    (mar_id, mar_terminal, mar_pessoa, mar_datahora, mar_funcao,
     mar_status, mar_statusbasico, mar_cracha, mar_sentido,
     mar_tipo, mar_origem, mar_datahorainc)
VALUES (...)
ON CONFLICT (mar_id) DO NOTHING;
```

O `ON CONFLICT DO NOTHING` é o que torna o job seguro de repetir. Se ele cair no
meio, rodar de novo não duplica; se a sobreposição de 10 minutos trouxer linhas
já copiadas, elas são descartadas em silêncio.

## Frequência

O painel reconcilia a cada tick, mas só enxerga o que chegou ao Postgres. **A
latência da replicação é a latência do painel**: um job de 5 em 5 minutos faz o
aluno aparecer na maquete até 5 minutos depois de passar na catraca.

Para acompanhamento em tempo real, de 1 em 1 minuto. O volume é pequeno —
1.500 alunos geram alguns milhares de marcações por dia, e cada execução carrega
só o que entrou desde a anterior.

## Como executar

Três caminhos, em ordem de preferência:

1. **SQL Agent Job com PowerShell** (`Npgsql`). É o mais direto: um script lê a
   marca d'água no Postgres, consulta o SQL Server e grava. Sem componente extra
   no servidor além do driver.
2. **SSIS**, se a instituição já mantém pacotes — mesma lógica, com o custo de
   manter o pacote.
3. **Linked Server via ODBC para PostgreSQL**. Funciona, mas exige instalar e
   configurar o driver ODBC no servidor de banco, e falhas de rede viram erro de
   transação distribuída, que é ruim de diagnosticar.

## Uma observação sobre o dado

Isto tira do prédio o registro de circulação de pessoas — quem entrou, quando e
por onde. O cadastro de alunos já está no Supabase, então não é uma mudança de
natureza, mas circulação é mais sensível que matrícula. A tabela está com RLS
habilitada e sem política, o que bloqueia leitura pela API REST gerada; o acesso
é só pela conexão direta do backend.
