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

## Onde se instala: SQL Server Agent

> **No servidor do Insted esta seção não se aplica.** O controle de acesso roda
> em **SQL Server 2019 Express** (`15.0.2000.5`), instância `ACESSO`, e Express
> não tem Agent — `SQLAgent$ACESSO` existe, mas `Stopped` e `Disabled`, sem
> como habilitar. Vá para [Sem SQL Server Agent](#sem-sql-server-agent-agendador-de-tarefas).
> Esta seção vale para qualquer outra instalação, com Standard ou superior.

Dois scripts: [`scripts/replicar-catracas.ps1`](../scripts/replicar-catracas.ps1)
é o que copia, e [`scripts/instalar-job-catracas.ps1`](../scripts/instalar-job-catracas.ps1)
é o que cria o job que o chama de 3 em 3 minutos. Nada disso se faz no SSMS.

**Antes**, uma vez no servidor, instale o **driver ODBC do PostgreSQL**
(psqlODBC), 64 bits — um MSI:
<https://www.postgresql.org/ftp/odbc/versions/msi/>

Escolhido em vez do Npgsql de propósito. O Npgsql 8 só publica build para
.NET moderno, e o `powershell.exe` do Windows roda sobre .NET Framework: a
biblioteca carrega e falha por assembly incompatível. Versões antigas do
Npgsql funcionariam, mas arrastam meia dúzia de DLLs de dependência. O
`System.Data.Odbc` já faz parte do .NET Framework — nada para resolver.

O instalador confere o driver, mas não baixa o MSI sozinho: puxar e executar um
instalador da internet sem ninguém olhando não é coisa que um script de setup
deva fazer calado.

**Depois**, num PowerShell **como Administrador**, no servidor do controle de
acesso:

```powershell
cd <caminho-do-repositorio>\scripts
.\instalar-job-catracas.ps1 -PgHost aws-0-sa-east-1.pooler.supabase.com -PgUser postgres.<ref-do-projeto>
```

A senha é pedida no terminal como `SecureString` — não entra na linha de
comando, então não fica no histórico do shell nem em log de sessão.

Ele faz, em ordem: exige elevação; confere o driver ODBC; testa a conexão com o
Postgres consultando `catraca.gac_marcacao`, o que valida de uma vez
credencial, rede, SSL e se o `db/catraca.sql` já foi aplicado; grava `PGHOST`,
`PGUSER` e `PGPASSWORD` como variáveis **de máquina** — as de usuário o serviço
do Agent não enxerga; **sobe o Agent** e o marca como início automático; cria o
job com passo `CmdExec` e agenda de 3 em 3 minutos; e dispara a primeira
execução, relatando como ela terminou.

A ordem importa e custou uma tentativa para aparecer: `sp_add_jobserver`
notifica o Agent no instante em que o job é criado, então com o serviço parado
a criação falha em *"SQLServerAgent is not currently running so it cannot be
notified of this action"* — e o job fica meio criado. Subir o serviço antes
também resolve o outro lado: ele lê o ambiente ao iniciar, e uma variável
gravada com ele já rodando só valeria depois de um reinício.

**Rodar de novo é seguro** — ele apaga o job e recria com a definição do
arquivo. É a razão de existir: um job criado à mão meses atrás, com outro
caminho ou outra agenda, é o tipo de divergência que ninguém percebe até a
replicação parar. Sem argumentos ele reaproveita as credenciais já gravadas,
então reinstalar depois de editar o script de replicação é um comando só:

```powershell
.\instalar-job-catracas.ps1
```

Parâmetros que valem saber: `-IntervaloMinutos` (padrão 3), `-NomeJob`,
`-ServidorSql` (instância nomeada: `.\INSTANCIA`), `-CaminhoScript` e
`-NaoIniciar`, que instala sem disparar a primeira execução — útil quando se
sabe que a carga inicial é longa e se prefere acompanhá-la pelo histórico.

A primeira execução traz o histórico em blocos de 20 mil — o teto existe para
não estourar o tempo tentando carregar anos de uma vez. Repita até o log parar
de avisar que há fila.

A conta de serviço do Agent precisa ler `GAC_MARCACAO` e alcançar a internet na
porta 5432. É por isso que o instalador dispara a primeira execução em vez de
se contentar com o teste de conexão: o passo roda sob a conta do serviço, não
sob a de quem instalou, e é só ali que falta de permissão ou de saída aparece.

> A senha do Postgres fica em variável de máquina, em texto claro — qualquer
> administrador local lê. É o que o `replicar-catracas.ps1` espera; enquanto
> for assim, use um usuário de banco só para esta replicação, com escrita
> apenas no schema `catraca`.

### O que ele monta, para conferir no SSMS

| Onde | Valor | Por quê |
|---|---|---|
| Step, tipo | `Operating system (CmdExec)` | o host de PowerShell do Agent é restrito e costuma falhar em cmdlets de sistema como o `Get-OdbcDriver` |
| Step, comando | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<caminho>\replicar-catracas.ps1"` | — |
| Step → Advanced | `Include step output in history` (`@flags = 32`) | sem isso, quando algo falha o histórico mostra apenas "o passo falhou", sem a mensagem que diz por quê |
| Schedule | diário, a cada 3 minutos, das 00:00:00 às 23:59:59 | a latência da replicação é a latência do painel |

## Sem SQL Server Agent: Agendador de Tarefas

**É o caminho do Insted.** Medido no servidor: `Express Edition (64-bit) |
15.0.2000.5`, instância `ACESSO`, `SQLAgent$ACESSO` em `Stopped` / `Disabled`.

O SQL Server **Express não tem Agent**. O serviço até aparece instalado, como
`SQLAgent$<instância>`, mas sempre `Stopped` e `Disabled`, e não há como
habilitá-lo — não é configuração, é limitação da edição. Para saber em qual
caso você está:

```powershell
Get-Service SQLSERVERAGENT, 'SQLAgent$*' -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType
```

`Disabled` é a assinatura do Express. Confirme a edição antes de concluir:

```powershell
$cn = New-Object System.Data.SqlClient.SqlConnection('Server=.;Database=master;Integrated Security=true;TrustServerCertificate=true')
$cn.Open(); $cmd = $cn.CreateCommand()
$cmd.CommandText = "select cast(serverproperty('Edition') as nvarchar(128)) + ' | ' + cast(serverproperty('ProductVersion') as nvarchar(128))"
$cmd.ExecuteScalar(); $cn.Close()
```

Sendo Express, o relógio passa a ser o Agendador de Tarefas do Windows.
[`scripts/instalar-tarefa-catracas.ps1`](../scripts/instalar-tarefa-catracas.ps1)
faz o mesmo que o outro instalador — as mesmas conferências, a mesma primeira
execução de prova:

```powershell
.\instalar-tarefa-catracas.ps1 -PgHost aws-0-sa-east-1.pooler.supabase.com -PgUser postgres.<ref-do-projeto> -IntervaloMinutos 5
```

Também vale escolher este caminho mesmo havendo Agent: agendar fora do SQL
Server evita alterar a configuração de um servidor de terceiro em produção.

Duas diferenças que não são cosméticas:

**O log é responsabilidade nossa.** O Agent guarda a saída do passo no
histórico do job; o Agendador descarta tudo que o processo escreve. Por isso a
ação roda via `cmd.exe` com `>> log 2>&1`, e o arquivo fica em
`replicacao.log`, ao lado do script (`-CaminhoLog` muda). Sem ele, uma falha às
3 da manhã não deixa rastro nenhum.

**A conta importa mais.** O `replicar-catracas.ps1` conecta na origem com
`Integrated Security=true`. O padrão é `NT AUTHORITY\SYSTEM` — não pede senha,
não expira, roda com ninguém logado — mas ele chega ao SQL Server como a conta
de máquina (`DOMÍNIO\SERVIDOR$`), e desde o SQL Server 2012 isso não vem com
acesso por padrão. Se a primeira execução falhar em *Login failed*, passe
`-Conta DOMINIO\conta-de-servico` com uma conta que já leia o `ACESSOTA`; o
instalador pede a senha no terminal.

Por que `-Once` com repetição e não `-Daily`: repetição por minuto só existe
nessa forma no Agendador. O instalador lê o gatilho de volta depois de
registrar e avisa se a repetição indefinida não tiver grudado — em versões
antigas do Windows isso falha em silêncio, e a tarefa rodaria **uma vez só**.

Conferir depois, sem abrir o Agendador:

```powershell
Get-ScheduledTaskInfo -TaskName 'Insted Virtual - Replicar catracas' | Select-Object LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult` igual a `0` é sucesso.

### Dando acesso à origem para a conta da tarefa

`Login failed for user 'NT AUTHORITY\SYSTEM'` na primeira execução é o caso
comum, e não tem a ver com o Postgres: a tarefa roda sob SYSTEM, e o Windows a
apresenta ao SQL Server como essa conta, que desde o SQL Server 2012 não vem
com acesso por padrão.

A saída preferível é **dar leitura a SYSTEM nas duas tabelas** — a tarefa
continua sem senha guardada em lugar nenhum, que é a vantagem de rodar como
SYSTEM. Como o `replicar-catracas.ps1` só lê da origem, `SELECT` nas duas
tabelas basta; `db_datareader` daria acesso à base inteira do fornecedor sem
necessidade.

Num PowerShell como Administrador, no servidor:

```powershell
$cn = New-Object System.Data.SqlClient.SqlConnection('Server=.;Database=ACESSOTA;Integrated Security=true;TrustServerCertificate=true')
$cn.Open(); $cmd = $cn.CreateCommand()
$cmd.CommandText = @'
if not exists (select 1 from sys.server_principals where name = 'NT AUTHORITY\SYSTEM')
    create login [NT AUTHORITY\SYSTEM] from windows;
if not exists (select 1 from sys.database_principals where name = 'NT AUTHORITY\SYSTEM')
    create user [NT AUTHORITY\SYSTEM] for login [NT AUTHORITY\SYSTEM];
grant select on TELESSVR.GAC_MARCACAO to [NT AUTHORITY\SYSTEM];
grant select on TELESSVR.GAC_PESSOA   to [NT AUTHORITY\SYSTEM];
'@
$cmd.ExecuteNonQuery(); $cn.Close()
```

É idempotente e só concede leitura — não altera nada do controle de acesso.
Quem roda precisa ser `sysadmin` na instância.

Depois, rode o instalador de novo. Ele recria a tarefa e dispara a execução:

```powershell
.\instalar-tarefa-catracas.ps1 -IntervaloMinutos 5
```

**A alternativa**, se a política da instituição não permitir conceder acesso a
SYSTEM: use uma conta de serviço que já leia o `ACESSOTA`.

```powershell
.\instalar-tarefa-catracas.ps1 -IntervaloMinutos 5 -Conta DOMINIO\conta-de-servico
```

O instalador pede a senha no terminal e a entrega ao Agendador, que a guarda no
cofre do Windows. O custo é que **troca de senha quebra a tarefa em silêncio** —
ela passa a falhar a cada ciclo, e só o log mostra. Por isso a primeira opção é
preferível.

## A chave de casamento: CPF, preenchido até 12 posições

O `pes_matricula` do crachá passou a ser cadastrado com **CPF**, não mais com o
RA. O cruzamento com o cadastro acadêmico acompanha: compara o CPF do JaCad,
vindo de `GET /api/v2/academico/alunos`, e cai no RA quando não há CPF.

Os dois lados são normalizados por `catraca.chave12()`: só dígitos, preenchido
com zeros à esquerda até 12 posições.

**A regra anterior tirava os zeros à esquerda, e isso era destrutivo.** Servia
para RA, mas CPF que começa com zero perderia o primeiro dígito e nunca
casaria. Preencher não descarta nada, e é como o crachá já guarda o número:
`001010002874` é o RA 1010002874; `001234567890` é o CPF 01234567890.

O `right()` antes do `lpad` não é enfeite: `lpad` **trunca pela esquerda**
quando o valor excede o tamanho, então um valor de 13 dígitos viraria os 12
primeiros em vez dos 12 últimos.

### Por que o casamento usa LATERAL e não OR

A forma óbvia — `on (cpf = crachá or ra = crachá)` — não usa índice nenhum. O
planejador vira um nested loop com filtro, avaliando `chave12` nos dois lados
de cada par. Medido em produção, para **um** dia: 3.346.736 linhas descartadas,
**8.892 ms**.

Com `join lateral` de dois `select` unidos por `union all`, cada ramo é uma
igualdade sobre expressão indexada: **25 ms**, 355× mais rápido. O alimentador
lê a cada 30 segundos, então a diferença é entre funcionar e não funcionar.

O `limit 1` do lateral resolve também um problema de correção: um crachá pode
casar pelo CPF de uma pessoa e pelo RA de outra, e a passagem viraria dois
eventos. A prioridade fica com o CPF, que é o cadastro novo.

### Estado da migração

Medido em 25/09/2026, sobre os 2.434 crachás replicados, validando os dígitos
verificadores: **398 são CPF válido, 2.032 não são** — ainda RA. Por isso o
casamento aceita as duas chaves em vez de trocar de uma vez: trocar deixaria
84% das pessoas sem reconhecimento enquanto o recadastramento não terminasse.

Quando ele terminar, dá para simplificar para CPF apenas — e a consulta acima
diz quando: é quando `cpf_valido` alcançar o total.

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
