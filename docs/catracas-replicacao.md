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

## Onde se cria: SQL Server Agent

O script pronto está em [`scripts/replicar-catracas.ps1`](../scripts/replicar-catracas.ps1).

**Antes**, uma vez no servidor:

1. Coloque o `Npgsql.dll` numa pasta do servidor (o `.nupkg` do NuGet é um
   `.zip`; o DLL está em `lib/net8.0/`). Ajuste `$DllNpgsql` no script para esse
   caminho.
2. Defina as credenciais como variáveis de ambiente **de máquina** — as de
   usuário o serviço do Agent não enxerga:

   ```powershell
   [Environment]::SetEnvironmentVariable('PGHOST','aws-0-sa-east-1.pooler.supabase.com','Machine')
   [Environment]::SetEnvironmentVariable('PGUSER','postgres.vbmdwkwakssenpvtumvg','Machine')
   [Environment]::SetEnvironmentVariable('PGPASSWORD','...','Machine')
   ```

   Reinicie o serviço do SQL Server Agent para ele reler o ambiente.

3. Rode o script à mão uma vez. A primeira execução traz o histórico em blocos
   de 20 mil — o teto existe para não estourar o tempo tentando carregar anos de
   uma vez. Repita até o log parar de avisar que há fila.

**O job**, no SSMS: `SQL Server Agent` → `Jobs` → botão direito → `New Job`.

* **Steps** → `New`: tipo **`Operating system (CmdExec)`**, comando

  ```
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<caminho>\replicar-catracas.ps1"
  ```

  Use `CmdExec`, não o tipo `PowerShell`: o host de PowerShell do Agent é
  restrito e costuma falhar ao carregar assemblies externos como o Npgsql.

* **Schedules** → `New`: recorrente, diariamente, **a cada 3 minutos**, das
  00:00:00 às 23:59:59.

* **Advanced** → marque `Include step output in history`. Sem isso, quando algo
  falhar o histórico mostra apenas "o passo falhou", sem a mensagem que diz por
  quê.

A conta de serviço do Agent precisa ler `GAC_MARCACAO` e alcançar a internet na
porta 5432.

## Por que não mandar direto para a API

O backend tem `/api/v1/catracas/evento` e `/api/v1/catracas/lote`, e o job
poderia postar neles — sem Npgsql, sem driver nenhum. Não é o caminho
recomendado por um motivo prático: **no plano free o serviço do Render hiberna
após ~15 minutos sem acesso**, e a primeira chamada depois disso leva perto de um
minuto ou falha por timeout. Uma passagem perdida assim não volta — não fica
registro em lugar nenhum.

Gravando no Postgres, o dado está guardado independente de o backend estar de pé;
o painel lê quando acordar. Com o plano pago, sem hibernação, o envio direto
passa a ser alternativa razoável — e os dois convivem bem: a API para o tempo
real, a replicação como rede de segurança.

## Uma observação sobre o dado

Isto tira do prédio o registro de circulação de pessoas — quem entrou, quando e
por onde. O cadastro de alunos já está no Supabase, então não é uma mudança de
natureza, mas circulação é mais sensível que matrícula. A tabela está com RLS
habilitada e sem política, o que bloqueia leitura pela API REST gerada; o acesso
é só pela conexão direta do backend.
