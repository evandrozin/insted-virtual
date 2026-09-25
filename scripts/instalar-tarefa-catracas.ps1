<#
.SINOPSE
    Instala (ou reinstala) a tarefa do Agendador do Windows que replica as
    catracas. Alternativa ao instalar-job-catracas.ps1 para quando nao ha SQL
    Server Agent.

.DESCRICAO
    Mesmo trabalho do instalador do SQL Server Agent - mesmas conferencias,
    mesmas credenciais, mesma primeira execucao de prova - mas o relogio e o
    Agendador de Tarefas em vez do Agent.

    Existe porque o SQL Server Express nao tem Agent: o servico ate aparece
    instalado, `SQLAgent$<instancia>`, sempre Stopped e Disabled, e nao ha como
    habilita-lo. Tambem serve quando ha Agent mas nao se quer mexer na
    configuracao de um servidor de terceiro em producao.

    E idempotente: rodar de novo apaga a tarefa e recria com esta definicao.

.EXEMPLO
        .\instalar-tarefa-catracas.ps1 -PgHost aws-0-sa-east-1.pooler.supabase.com -PgUser postgres.<ref> -IntervaloMinutos 5

    Reinstalar reaproveitando as credenciais ja gravadas:

        .\instalar-tarefa-catracas.ps1 -IntervaloMinutos 5

.CONTA
    Por padrao a tarefa roda como `NT AUTHORITY\SYSTEM`: nao pede senha, nao
    expira e roda com ninguem logado.

    O porem: o replicar-catracas.ps1 conecta na origem com
    `Integrated Security=true`, entao SYSTEM precisa de login no SQL Server -
    ele chega la como a conta de maquina (`DOMINIO\SERVIDOR$`), e desde o SQL
    Server 2012 isso nao vem com acesso por padrao. Se a primeira execucao
    falhar em "Login failed", passe `-Conta DOMINIO\conta-de-servico` com uma
    conta que ja leia o ACESSOTA.

.SEGURANCA
    Igual ao outro instalador: a senha do Postgres vira variavel de ambiente de
    maquina, em texto claro. Use um usuario de banco so para esta replicacao,
    com escrita apenas no schema `catraca`.
#>
[CmdletBinding()]
param(
    [string]       $PgHost,
    [string]       $PgUser,
    [securestring] $PgPassword,

    [string] $PgDatabase = 'postgres',
    [int]    $PgPorta    = 5432,

    [ValidateRange(1, 60)]
    [int] $IntervaloMinutos = 5,

    [string] $NomeTarefa = 'Insted Virtual - Replicar catracas',

    # Por padrao, o replicar-catracas.ps1 que esta ao lado deste arquivo.
    [string] $CaminhoScript,

    # O Agendador nao guarda a saida do processo em lugar nenhum - ao contrario
    # do Agent, que tem historico do passo. Sem este arquivo, uma falha as 3 da
    # manha nao deixa rastro.
    [string] $CaminhoLog,

    [string]       $Conta = 'NT AUTHORITY\SYSTEM',
    [securestring] $SenhaConta,

    [switch] $NaoIniciar
)

$ErrorActionPreference = 'Stop'

function Registrar($mensagem) {
    Write-Output ("[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $mensagem)
}

function ValorDeMaquina($nome) {
    return [Environment]::GetEnvironmentVariable($nome, 'Machine')
}

function TextoSeguro($segura) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try   { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# --- 1. elevacao ------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw ('Rode como Administrador: gravar variavel de maquina e registrar ' +
           'tarefa que roda como SYSTEM exigem elevacao.')
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

if ($CaminhoScript -like "$env:SystemDrive\Users\*") {
    Write-Warning ("O script esta sob $env:SystemDrive\Users. SYSTEM e contas " +
                   "de servico costumam nao ter acesso ai - prefira algo como " +
                   "$env:SystemDrive\Catracas.")
}

if (-not $CaminhoLog) {
    $CaminhoLog = Join-Path (Split-Path $CaminhoScript) 'replicacao.log'
}
New-Item -ItemType Directory -Force -Path (Split-Path $CaminhoLog) | Out-Null

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

# --- 6. a origem responde? --------------------------------------------------
# A string de conexao sai do proprio replicar-catracas.ps1, em vez de repetida
# aqui: duas copias divergem, e a que estiver errada so aparece em producao.
#
# Este teste roda como quem instala, nao como a conta da tarefa - serve para
# pegar servidor fora do ar ou nome errado. Permissao da conta da tarefa e
# outra coisa, e so a primeira execucao mostra.
$origem = (Select-String -Path $CaminhoScript -Pattern "^\s*\`$OrigemSql\s*=\s*'(.+)'" |
           Select-Object -First 1).Matches.Groups[1].Value
if (-not $origem) {
    Write-Warning "Nao consegui ler `$OrigemSql do script; pulando o teste da origem."
}
else {
    try {
        $sql = New-Object System.Data.SqlClient.SqlConnection($origem)
        $sql.Open()
        try {
            $c = $sql.CreateCommand()
            $c.CommandTimeout = 60
            $c.CommandText = 'select count(*) from ACESSOTA.TELESSVR.GAC_MARCACAO'
            Registrar ("origem ok: {0} marcacao(oes) no controle de acesso" -f $c.ExecuteScalar())
        }
        finally { $sql.Close() }
    }
    catch {
        Write-Warning ("Nao consegui ler a origem com a sua conta: " +
                       $_.Exception.Message)
    }
}

# --- 7. variaveis de maquina ------------------------------------------------
# De maquina porque a tarefa roda com outra conta - de usuario ela nao enxerga.
# SYSTEM e contas de servico leem as de maquina normalmente.
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

# --- 8. a tarefa ------------------------------------------------------------
# Via cmd.exe para poder redirecionar. O Agendador nao tem campo de log, e a
# acao sozinha descartaria tudo que o script escreve; `>>` com `2>&1` guarda
# saida e erro no mesmo arquivo, em ordem.
#
# cmd.exe em vez de canalizar para Tee-Object dentro do PowerShell porque o
# replicar-catracas.ps1 chama `exit 0` quando nao ha novidade, e `exit` no meio
# de um pipeline encerra o processo antes de o Tee fechar o arquivo.
$argumento = ('/c powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" >> "{1}" 2>&1' -f
              $CaminhoScript, $CaminhoLog)

$acao = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $argumento

# -Once com repeticao, e nao -Daily: repeticao por minuto so existe nessa
# forma. Sem -RepetitionDuration a repeticao e indefinida no Windows 8/2012 em
# diante - conferido logo abaixo, porque em versao antiga isso nao gruda.
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
               -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)

# IgnoreNew: a carga inicial vem em blocos de 20 mil e pode passar do intervalo.
# Sem isso as execucoes empilhariam, varias copiando a mesma faixa ao mesmo
# tempo - nao corrompe nada, porque o ON CONFLICT descarta, mas castiga o banco
# a toa.
#
# StartWhenAvailable: servidor que dormiu ou estava desligado na hora marcada
# roda assim que puder, em vez de so no proximo ciclo.
$config = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
              -StartWhenAvailable `
              -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$existia = [bool](Get-ScheduledTask -TaskName $NomeTarefa -ErrorAction SilentlyContinue)

$registro = @{
    TaskName = $NomeTarefa
    Action   = $acao
    Trigger  = $gatilho
    Settings = $config
    Force    = $true
    User     = $Conta
    RunLevel = 'Highest'
    Description = ('Replica GAC_MARCACAO e GAC_PESSOA do controle de acesso ' +
                   'para o Postgres do Insted Virtual. Instalado por ' +
                   'scripts/instalar-tarefa-catracas.ps1 - edite la, nao aqui.')
}
# Conta de dominio exige senha; SYSTEM e as outras contas internas nao tem uma.
if ($SenhaConta) {
    $registro['Password'] = TextoSeguro $SenhaConta
}
elseif ($Conta -notmatch '^(NT AUTHORITY\\|BUILTIN\\)') {
    $registro['Password'] = TextoSeguro (Read-Host "Senha de $Conta" -AsSecureString)
}

[void](Register-ScheduledTask @registro)
if ($existia) { $verbo = 'recriada' } else { $verbo = 'criada' }
Registrar ("tarefa '{0}' {1}, como {2}" -f $NomeTarefa, $verbo, $Conta)
Registrar "log em $CaminhoLog"

# A repeticao indefinida nem sempre gruda em versoes antigas do Agendador. Ler
# de volta custa nada e evita descobrir dentro de um mes que rodou uma vez so.
$repeticao = (Get-ScheduledTask -TaskName $NomeTarefa).Triggers[0].Repetition
if (-not $repeticao -or -not $repeticao.Interval) {
    Write-Warning ("A repeticao nao ficou registrada. Abra o Agendador de " +
                   "Tarefas, em '$NomeTarefa' > Disparadores > Editar, e marque " +
                   "'Repetir a tarefa a cada $IntervaloMinutos minutos' com " +
                   "duracao 'Indefinidamente'.")
}
else {
    Registrar "repeticao registrada: $($repeticao.Interval)"
}

# --- 9. primeira execucao ---------------------------------------------------
# E o unico teste que vale: a tarefa roda sob $Conta, nao sob quem instalou.
# Acesso ao GAC_MARCACAO e saida para a internet na 5432 sao dela.
if ($NaoIniciar) {
    Registrar 'primeira execucao nao disparada (-NaoIniciar)'
    return
}

Registrar 'disparando a primeira execucao'
$tamanhoAntes = if (Test-Path -LiteralPath $CaminhoLog) { (Get-Item -LiteralPath $CaminhoLog).Length } else { 0 }
Start-ScheduledTask -TaskName $NomeTarefa

# A carga inicial vem em blocos de 20 mil e pode passar de um minuto. Estourar
# a espera nao e erro: a tarefa segue, e o log conta o resto.
$limite = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $limite) {
    if ((Get-ScheduledTask -TaskName $NomeTarefa).State -ne 'Running') { break }
    Start-Sleep -Seconds 3
}

$info = Get-ScheduledTaskInfo -TaskName $NomeTarefa
if ((Get-ScheduledTask -TaskName $NomeTarefa).State -eq 'Running') {
    Write-Warning "A execucao ainda nao terminou. Acompanhe o log: $CaminhoLog"
    return
}

# So o que esta execucao escreveu - o log e append e pode ter meses de historico.
$saida = ''
if (Test-Path -LiteralPath $CaminhoLog) {
    $fluxo = [System.IO.File]::Open($CaminhoLog, 'Open', 'Read', 'ReadWrite')
    try {
        [void]$fluxo.Seek($tamanhoAntes, 'Begin')
        $leitor = New-Object System.IO.StreamReader($fluxo)
        $saida = $leitor.ReadToEnd().Trim()
    }
    finally { $fluxo.Close() }
}
if ($saida) { $saida -split "`r?`n" | ForEach-Object { Registrar $_ } }

if ($info.LastTaskResult -eq 0) {
    Registrar 'primeira execucao concluida com sucesso'
    Registrar "pronto: a replicacao se mantem sozinha a cada $IntervaloMinutos minuto(s)"
}
else {
    Registrar ("a tarefa terminou com codigo {0}. Ela esta instalada; corrija e rode de novo." -f $info.LastTaskResult)

    # A falha mais provavel, e a que menos se parece com a sua causa: a tarefa
    # roda sob outra conta, e o Windows a autentica no SQL Server como ela. Sem
    # este aviso, o operador reve credencial do Postgres - que nao tem nada a
    # ver - porque a mensagem so fala em "login failed".
    if ($saida -match 'Login failed|Cannot open database') {
        Registrar ''
        Registrar "A conta '$Conta' nao tem acesso ao SQL Server de origem. Duas saidas:"
        Registrar "  1) dar leitura a ela no ACESSOTA - ver docs/catracas-replicacao.md;"
        Registrar "  2) reinstalar com -Conta DOMINIO\conta-que-ja-le-o-ACESSOTA."
    }
    elseif (-not $saida) {
        Registrar "Sem saida no log - se o codigo for 2147942401 ou parecido, e a conta $Conta sem permissao de ler o proprio script."
    }
    throw 'Tarefa instalada, mas a primeira execucao falhou - veja a saida acima.'
}
