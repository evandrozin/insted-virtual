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

1. Instale o **driver ODBC do PostgreSQL** (psqlODBC), 64 bits — um MSI:
   <https://www.postgresql.org/ftp/odbc/versions/msi/>

   Escolhido em vez do Npgsql de propósito. O Npgsql 8 só publica build para
   .NET moderno, e o `powershell.exe` do Windows roda sobre .NET Framework: a
   biblioteca carrega e falha por assembly incompatível. Versões antigas do
   Npgsql funcionariam, mas arrastam meia dúzia de DLLs de dependência. O
   `System.Data.Odbc` já faz parte do .NET Framework — nada para resolver.

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
  restrito e costuma falhar em cmdlets de sistema como o `Get-OdbcDriver`.

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

## O que os campos significam

Levantado por medição sobre 14.936 marcações reais de 19/08 a 02/09/2026 — o
fornecedor não documentou nada disso.

### `MAR_SENTIDO`: 0 é entrada, 1 é saída, 2 é recusa

O `2` não é direção: **todas** as 1.745 ocorrências dele têm
`MAR_STATUSBASICO = '0'`, ou seja, passagem negada.

Entre `0` e `1`, o que decide são dois padrões que não deixam dúvida:

| | 1º evento do dia | último do dia |
|---|---|---|
| `0` | **5.919** | 2.372 |
| `1` | 685 | **4.232** |

E a distribuição por hora desenha o campus: `0` explode às 18h (3.217) e 19h,
quando o noturno chega, e às 7h para o matutino; `1` concentra-se às 20h e 21h
(1.927), quando as aulas terminam.

### `MAR_STATUSBASICO` é o filtro de passagem válida

`'1'` autorizado (13.096), `'0'` negado (1.840). Corresponde exatamente a
`MAR_STATUS = '01'`; os demais códigos — `20`, `22`, `86`, `46`, `45` — são
variedades de recusa. **Contar sem filtrar por `MAR_STATUSBASICO = '1'` colocaria
no campus quem a catraca barrou.**

### `MAR_CRACHA` está vazio: a chave é `MAR_PESSOA`

Só dois valores distintos em 14.936 linhas: 11.864 em branco e 3.072 com
`000000000000`. Este sistema não usa o campo.

Quem identifica é `MAR_PESSOA`, preenchido em 14.258 linhas, com **1.606 pessoas
distintas** na faixa 1..2277 — próximo dos 1.591 do nosso cadastro (1.505 alunos
+ 86 professores). É um id interno do controle de acesso, não o RA: falta a
tabela de pessoas do `ACESSOTA` para fazer o de-para.

### `MAR_FUNCAO`, `MAR_TIPO` e `MAR_ORIGEM` não servem para nada aqui

Valor único em toda a base (`-1`, `0` e `0`). Não distinguem coisa alguma.

### Terminais

Cinco, com volumes bem distintos: `3` (6.551), `2` (3.696), `1` (2.732),
`5` (1.016) e `4` (941). Ainda falta saber qual id corresponde a qual catraca
física — a maquete posiciona cinco, e hoje é estimativa.
