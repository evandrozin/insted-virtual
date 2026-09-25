<#
.SINOPSE
    Instala (ou reinstala) o job do SQL Server Agent que replica as catracas.

.DESCRICAO
    Faz de uma vez o que o docs/catracas-replicacao.md mandava fazer a mao no
    SSMS: confere o driver ODBC, grava as credenciais como variaveis de maquina,
    reinicia o Agent para ele reler o ambiente, cria o job com o passo CmdExec e
    a agenda de minuto em minuto, e roda uma vez para provar que funciona.

    E idempotente: rodar de novo apaga o job e recria com esta definicao. E de
    proposito - um job criado a mao meses atras, com outro caminho ou outra
    agenda, e exatamente o tipo de divergencia que ninguem percebe ate a
    replicacao parar. Aqui o arquivo e a verdade.

.EXEMPLO
    Primeira instalacao (pede a senha no terminal):

        .\instalar-job-catracas.ps1 -PgHost aws-0-sa-east-1.pooler.supabase.com `
                                    -PgUser postgres.vbmdwkwakssenpvtumvg

    Reinstalar depois de editar o replicar-catracas.ps1 (reaproveita as
    credenciais ja gravadas, nao pergunta nada):

        .\instalar-job-catracas.ps1

.PRE_REQUISITOS
    - Rodar como Administrador: variavel de maquina e reinicio de servico pedem
      elevacao.
    - Driver ODBC do PostgreSQL (psqlODBC) 64 bits. O script confere e diz onde
      baixar se faltar - nao instala sozinho de proposito: baixar e executar um
      MSI da internet sem ninguem olhando nao e coisa para um script de setup
      fazer calado.
    - Rodar NO SERVIDOR do controle de acesso, o mesmo que hospeda o SQL Server
      Agent. O job aponta para um caminho de arquivo local.

.SEGURANCA
    A senha do Postgres vira variavel de ambiente de maquina, em texto claro -
    qualquer administrador local le. E o mecanismo que o replicar-catracas.ps1
    ja espera; trocar por algo melhor (conta gerenciada, Credential Manager,
    proxy do Agent com credencial propria) mexe nos dois arquivos. Enquanto for
    assim, use um usuario de banco so para esta replicacao, com permissao de
    escrita apenas no schema `catraca`.
#>
[CmdletBinding()]
param(
    # Sem valor, cai na variavel de maquina ja existente; sem ela, pergunta.
    [string]       $PgHost,
    [string]       $PgUser,
    [securestring] $PgPassword,

    [string] $PgDatabase = 'postgres',
    [int]    $PgPorta    = 5432,

    # 3 minutos e o padrao do docs/catracas-replicacao.md. A latencia do painel
    # e a latencia daqui: o aluno aparece na maquete ate um ciclo depois de
    # passar na catraca.
    [ValidateRange(1, 60)]
    [int] $IntervaloMinutos = 3,

    [string] $NomeJob     = 'Insted Virtual - Replicar catracas',
    [string] $ServidorSql = '.',

    # Por padrao, o replicar-catracas.ps1 que esta ao lado deste arquivo.
    [string] $CaminhoScript,

    # Nao dispara a primeira execucao. Util quando se sabe que a carga inicial
    # e longa e se prefere acompanha-la pelo historico do Agent.
    [switch] $NaoIniciar
)

$ErrorActionPreference = 'Stop'

function Registrar($mensagem) {
    Write-Output ("[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $mensagem)
}

function ExecutarSql($texto, $parametros = @{}, $timeout = 120) {
    $cn = New-Object System.Data.SqlClient.SqlConnection(
        "Server=$ServidorSql;Database=msdb;Integrated Security=true;TrustServerCertificate=true")
    $cn.Open()
    try {
        $cmd = $cn.CreateCommand()
        $cmd.CommandTimeout = $timeout
        $cmd.CommandText = $texto
        foreach ($chave in $parametros.Keys) {
            [void]$cmd.Parameters.AddWithValue($chave, $parametros[$chave])
        }
        return $cmd.ExecuteScalar()
    }
    finally { $cn.Close() }
}

function TextoDe($valor) {
    if ($null -eq $valor -or $valor -is [System.DBNull]) { return '' }
    return [string]$valor
}

function ValorDeMaquina($nome) {
    return [Environment]::GetEnvironmentVariable($nome, 'Machine')
}

function TextoSeguro($segura) {
    # SecureString -> texto, liberando o buffer nao gerenciado em seguida.
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try   { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# --- 1. elevacao ------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw ('Rode como Administrador: gravar variavel de maquina e reiniciar o ' +
           'servico do Agent exigem elevacao.')
}

# --- 2. o script de replicacao existe? --------------------------------------
if (-not $CaminhoScript) {
    $CaminhoScript = Join-Path $PSScriptRoot 'replicar-catracas.ps1'
}
$CaminhoScript = [System.IO.Path]::GetFullPath($CaminhoScript)
if (-not (Test-Path -LiteralPath $CaminhoScript -PathType Leaf)) {
    throw "Script de replicacao nao encontrado em $CaminhoScript."
}
Registrar "script de replicacao: $CaminhoScript"

# O caminho vai para dentro do job. Se o repositorio estiver numa pasta de
# usuario, a conta de servico do Agent - que e outra - pode nao enxergar.
if ($CaminhoScript -like "$env:SystemDrive\Users\*") {
    Write-Warning ("O script esta sob $env:SystemDrive\Users. A conta de servico " +
                   "do Agent costuma nao ter acesso ai - prefira algo como " +
                   "$env:SystemDrive\Insted\scripts.")
}

# --- 3. driver ODBC ---------------------------------------------------------
$driver = (Get-OdbcDriver -Platform 64-bit -ErrorAction SilentlyContinue |
           Where-Object Name -like 'PostgreSQL*Unicode*' |
           Select-Object -First 1).Name
if (-not $driver) {
    throw ("Driver ODBC do PostgreSQL (64 bits) nao encontrado. Instale o " +
           "psqlODBC e rode de novo: " +
           "https://www.postgresql.org/ftp/odbc/versions/msi/")
}
Registrar "driver ODBC: $driver"

# --- 4. credenciais ---------------------------------------------------------
# Ausente na linha de comando, vale o que ja esta na maquina: reinstalar depois
# de editar o script de replicacao nao deve obrigar a redigitar a senha.
if (-not $PgHost) { $PgHost = ValorDeMaquina 'PGHOST' }
if (-not $PgUser) { $PgUser = ValorDeMaquina 'PGUSER' }
if (-not $PgHost) { $PgHost = Read-Host 'PGHOST (host do Postgres)' }
if (-not $PgUser) { $PgUser = Read-Host 'PGUSER (usuario do Postgres)' }

if ($PgPassword) {
    $senha = TextoSeguro $PgPassword
}
elseif (ValorDeMaquina 'PGPASSWORD') {
    $senha = ValorDeMaquina 'PGPASSWORD'
    Registrar 'PGPASSWORD: reaproveitando a que ja estava na maquina'
}
else {
    $senha = TextoSeguro (Read-Host 'PGPASSWORD (senha do Postgres)' -AsSecureString)
}
if (-not $senha) { throw 'PGPASSWORD vazia.' }

# --- 5. o destino responde? -------------------------------------------------
# Falhar aqui, com o operador na frente do terminal, vale muito mais que um job
# que so vai falhar as 3 da manha. Consultar a tabela de destino confere de uma
# vez credencial, rede, SSL e se o db/catraca.sql ja foi aplicado.
$conexaoPg = "Driver={$driver};Server=$PgHost;Port=$PgPorta;Database=$PgDatabase;" +
             "Uid=$PgUser;Pwd=$senha;SSLmode=require;UseServerSidePrepare=0;"
$pg = New-Object System.Data.Odbc.OdbcConnection($conexaoPg)
try {
    $pg.Open()
    $cmd = $pg.CreateCommand()
    $cmd.CommandText = 'select count(*) from catraca.gac_marcacao'
    $jaGravadas = [int64]$cmd.ExecuteScalar()
    Registrar ("destino ok: {0} em {1}, {2} marcacao(oes) ja replicada(s)" -f
               $PgDatabase, $PgHost, $jaGravadas)
}
catch {
    throw ("Nao consegui consultar catraca.gac_marcacao em $PgHost. " +
           "Confira credenciais, rede na porta $PgPorta e se o " +
           "apps/backend-api/db/catraca.sql ja foi aplicado. Erro: " +
           $_.Exception.Message)
}
finally { $pg.Close() }

# --- 6. variaveis de maquina ------------------------------------------------
# De maquina, nao de usuario: o servico do Agent roda com outra conta e nao
# enxerga as do usuario logado.
$mudou = $false
foreach ($par in @(@{ n = 'PGHOST';     v = $PgHost },
                   @{ n = 'PGUSER';     v = $PgUser },
                   @{ n = 'PGPASSWORD'; v = $senha })) {
    if ((ValorDeMaquina $par.n) -ne $par.v) {
        [Environment]::SetEnvironmentVariable($par.n, $par.v, 'Machine')
        $mudou = $true
    }
}
if ($mudou) { Registrar 'variaveis de maquina gravadas' }
else        { Registrar 'variaveis de maquina ja estavam corretas' }

# --- 7. qual servico do Agent -----------------------------------------------
$instancia = TextoDe (ExecutarSql "select cast(serverproperty('InstanceName') as nvarchar(128))")
if ($instancia) { $servicoAgent = "SQLAgent`$$instancia" }
else            { $servicoAgent = 'SQLSERVERAGENT' }

$servico = Get-Service -Name $servicoAgent -ErrorAction SilentlyContinue
if (-not $servico) {
    throw ("Servico $servicoAgent nao encontrado. Este script precisa rodar no " +
           "servidor que hospeda o SQL Server Agent.")
}

# --- 8. Agent de pe, com o ambiente novo, ANTES de criar o job --------------
# Antes e nao depois: sp_add_jobserver notifica o Agent no momento da criacao,
# e com o servico parado ela falha em "SQLServerAgent is not currently running
# so it cannot be notified of this action" - com o job ficando meio criado.
#
# O servico tambem le o ambiente ao iniciar. Variavel gravada com ele rodando
# so vale depois do reinicio; sem isso o job falha em "PGHOST nao esta
# definida", com tudo aparentemente configurado.

# Desabilitado nao inicia, e a mensagem do Start-Service nao diz por que. No
# SQL Server Express o servico ate existe, mas Agent nao e suportado nessa
# edicao - la o caminho e o Agendador de Tarefas do Windows.
if ($servico.StartType -eq 'Disabled') {
    $edicao = TextoDe (ExecutarSql "select cast(serverproperty('Edition') as nvarchar(128))")
    if ($edicao -like '*Express*') {
        throw ("$servicoAgent esta desabilitado e a edicao e '$edicao': o SQL " +
               "Server Agent nao roda no Express. Agende o " +
               "replicar-catracas.ps1 pelo Agendador de Tarefas do Windows.")
    }
    Set-Service -Name $servicoAgent -StartupType Automatic
    Registrar "$servicoAgent estava desabilitado; habilitado"
    $servico = Get-Service -Name $servicoAgent
}

if ($servico.Status -ne 'Running') {
    Registrar "servico $servicoAgent parado; iniciando"
    Start-Service -Name $servicoAgent
}
elseif ($mudou) {
    Registrar "reiniciando $servicoAgent para reler o ambiente"
    Restart-Service -Name $servicoAgent -Force
}
(Get-Service -Name $servicoAgent).WaitForStatus('Running', [TimeSpan]::FromSeconds(60))

# O servico aceita conexao antes de estar pronto para receber comandos; sem
# esta espera a criacao do job logo abaixo bate na mesma mensagem de servico
# parado.
#
# Em try/catch porque a DMV exige VIEW SERVER STATE: sem essa permissao a
# consulta falha, e deixar o erro subir abortaria o script. Sem poder
# consultar, a espera fixa resolve.
foreach ($tentativa in 1..15) {
    try {
        $pronto = [int](ExecutarSql "select case when exists (select 1 from sys.dm_exec_sessions where program_name like 'SQLAgent%') then 1 else 0 end")
    }
    catch {
        Start-Sleep -Seconds 5
        break
    }
    if ($pronto) { break }
    Start-Sleep -Seconds 2
}

# Garante que ele suba sozinho junto com o servidor - um job perfeito num Agent
# em modo manual nao replica nada depois do proximo reboot.
if ((Get-Service -Name $servicoAgent).StartType -ne 'Automatic') {
    Set-Service -Name $servicoAgent -StartupType Automatic
    Registrar "$servicoAgent passou a iniciar automaticamente"
}
Registrar "$servicoAgent em execucao"

# --- 9. job -----------------------------------------------------------------
$comando = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$CaminhoScript`""

$tsql = @'
set nocount on;

if exists (select 1 from msdb.dbo.sysjobs where name = @nome)
begin
    -- Parar antes de apagar: sp_delete_job recusa job em execucao, e uma
    -- reinstalacao no meio de um ciclo e justamente quando isso acontece.
    begin try
        exec msdb.dbo.sp_stop_job @job_name = @nome;
    end try
    begin catch
    end catch;

    exec msdb.dbo.sp_delete_job @job_name = @nome, @delete_unused_schedule = 1;
end

exec msdb.dbo.sp_add_job
     @job_name    = @nome,
     @enabled     = 1,
     @description = @descricao;

-- CmdExec, nao o subsistema PowerShell: o host de PowerShell do Agent e
-- restrito e falha em cmdlets de sistema como o Get-OdbcDriver.
-- @flags = 32 grava toda a saida do passo no historico; sem isso uma falha
-- aparece como "o passo falhou", sem a mensagem que diz por que.
exec msdb.dbo.sp_add_jobstep
     @job_name          = @nome,
     @step_name         = N'Replicar marcacoes',
     @subsystem         = N'CmdExec',
     @command           = @comando,
     @flags             = 32,
     @on_success_action = 1,
     @on_fail_action    = 2,
     @retry_attempts    = 0;

-- freq_type 4 = diario; freq_subday_type 4 = a cada N minutos, das 00:00:00
-- as 23:59:59.
exec msdb.dbo.sp_add_jobschedule
     @job_name             = @nome,
     @name                 = @agenda,
     @enabled              = 1,
     @freq_type            = 4,
     @freq_interval        = 1,
     @freq_subday_type     = 4,
     @freq_subday_interval = @intervalo,
     @active_start_time    = 000000,
     @active_end_time      = 235959;

exec msdb.dbo.sp_add_jobserver @job_name = @nome, @server_name = N'(local)';
'@

$existia = [int](ExecutarSql 'select count(*) from msdb.dbo.sysjobs where name = @nome' @{ '@nome' = $NomeJob })

[void](ExecutarSql $tsql @{
    '@nome'      = $NomeJob
    '@comando'   = $comando
    '@agenda'    = "A cada $IntervaloMinutos minuto(s)"
    '@intervalo' = $IntervaloMinutos
    '@descricao' = ('Replica GAC_MARCACAO e GAC_PESSOA do controle de acesso ' +
                    'para o Postgres do Insted Virtual. Instalado por ' +
                    'scripts/instalar-job-catracas.ps1 - edite la, nao aqui.')
})
if ($existia) { $verbo = 'recriado' } else { $verbo = 'criado' }
Registrar ("job '{0}' {1}, a cada {2} minuto(s)" -f $NomeJob, $verbo, $IntervaloMinutos)

# --- 10. primeira execucao --------------------------------------------------
# E o unico teste que vale: o passo roda sob a conta de servico do Agent, nao
# sob a de quem instalou. Acesso ao GAC_MARCACAO e saida para a internet na
# 5432 sao dela, e so aqui isso aparece.
if ($NaoIniciar) {
    Registrar 'primeira execucao nao disparada (-NaoIniciar)'
    Registrar 'instalacao concluida'
    return
}

Registrar 'disparando a primeira execucao'
try {
    [void](ExecutarSql 'exec msdb.dbo.sp_start_job @job_name = @nome' @{ '@nome' = $NomeJob })
}
catch {
    # O job existe e a agenda vale: ele roda sozinho no proximo ciclo. Falhar o
    # script aqui faria parecer que a instalacao nao pegou.
    Write-Warning ("Job instalado, mas nao consegui dispara-lo agora: " +
                   $_.Exception.Message)
    Registrar "ele roda sozinho no proximo ciclo (ate $IntervaloMinutos minuto(s))"
    return
}

$sqlEmExecucao = @'
select case when exists (
           select 1
             from msdb.dbo.sysjobactivity a
             join msdb.dbo.sysjobs j on j.job_id = a.job_id
            where j.name = @nome
              -- So a sessao atual do Agent. Um reinicio deixa para tras linhas
              -- com start preenchido e stop nulo, de execucoes que morreram
              -- junto com o servico - sem este filtro a espera abaixo giraria
              -- ate estourar por causa de um ciclo de semanas atras.
              and a.session_id = (select max(session_id) from msdb.dbo.syssessions)
              and a.start_execution_date is not null
              and a.stop_execution_date is null
       ) then 1 else 0 end
'@

# A carga inicial vem em blocos de 20 mil e pode passar de um minuto. Estourar
# a espera nao e erro: o job segue, e o historico conta o resto.
$limite = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $limite) {
    if ([int](ExecutarSql $sqlEmExecucao @{ '@nome' = $NomeJob }) -eq 0) { break }
    Start-Sleep -Seconds 3
}

$sqlHistorico = @'
-- isnull no message: concatenar com NULL zeraria a linha inteira, e o status
-- viria vazio como se a execucao nem tivesse acontecido.
select top 1 cast(h.run_status as nvarchar(2)) + '|' + isnull(h.message, '')
  from msdb.dbo.sysjobhistory h
  join msdb.dbo.sysjobs j on j.job_id = h.job_id
 where j.name = @nome and h.step_id = 1
 order by h.instance_id desc
'@
$historico = TextoDe (ExecutarSql $sqlHistorico @{ '@nome' = $NomeJob })

if (-not $historico) {
    Write-Warning ("A execucao ainda nao terminou. Acompanhe em SQL Server " +
                   "Agent > Jobs > '$NomeJob' > View History.")
    return
}

$status   = $historico.Split('|')[0]
$mensagem = $historico.Substring($historico.IndexOf('|') + 1)

if ($status -eq '1') {
    Registrar 'primeira execucao concluida com sucesso'
    Registrar $mensagem
    Registrar "pronto: a replicacao se mantem sozinha a cada $IntervaloMinutos minuto(s)"
}
else {
    Registrar 'a primeira execucao falhou. O job esta instalado; corrija e rode de novo.'
    Registrar $mensagem
    throw 'Job instalado, mas a primeira execucao falhou - veja a mensagem acima.'
}
