<#
.SINOPSE
    Replica as marcacoes novas das catracas para o Postgres do Insted Virtual.

.DESCRICAO
    Roda no servidor do controle de acesso, agendado no SQL Server Agent. Le a
    marca dagua no destino, busca na origem so o que entrou depois dela e grava.

    Nao escreve nada na origem. Em especial, nao toca em MAR_EXPORTADA nem em
    MAR_EXPORTADA_WS: essas colunas sao do fornecedor, usadas nas integracoes
    dele, e mexer nelas quebra o que ja funciona - num sistema diferente, semanas
    depois, sem ligacao obvia com isto aqui.

.PRE_REQUISITOS
    Npgsql.dll acessivel ao PowerShell. Uma vez, no servidor:

        # baixe o pacote e extraia o DLL para C:\ferramentas\Npgsql
        nuget install Npgsql -Version 8.0.3 -OutputDirectory C:\temp\npgsql
        # ou baixe de https://www.nuget.org/packages/Npgsql (o .nupkg e um .zip)

    Ajuste $DllNpgsql abaixo para o caminho onde ficou.

.CREDENCIAIS
    Vem do ambiente, nunca do arquivo - este script fica versionado no Git.
    Defina como variaveis de ambiente de MAQUINA (nao de usuario, senao o SQL
    Agent nao enxerga):

        [Environment]::SetEnvironmentVariable('PGHOST','aws-0-sa-east-1.pooler.supabase.com','Machine')
        [Environment]::SetEnvironmentVariable('PGUSER','postgres.vbmdwkwakssenpvtumvg','Machine')
        [Environment]::SetEnvironmentVariable('PGPASSWORD','...','Machine')

    Reinicie o servico do SQL Agent depois de definir.
#>

$ErrorActionPreference = 'Stop'

# --- configuracao -----------------------------------------------------------
$DllNpgsql   = 'C:\ferramentas\Npgsql\Npgsql.dll'
$OrigemSql   = 'Server=10.25.0.81,1433;Database=ACESSOTA;Integrated Security=true;TrustServerCertificate=true'
$DestinoHost = $env:PGHOST
$DestinoUser = $env:PGUSER
$DestinoSenha = $env:PGPASSWORD
$DestinoBase = 'postgres'
$DestinoPorta = 5432

# Recuo aplicado a marca dagua. Cobre transacoes que ainda nao tinham commitado
# quando a execucao anterior leu: elas so ficam visiveis depois, e sem a
# sobreposicao passariam batido. Repetir linha nao custa nada - a chave primaria
# descarta.
$RecuoMinutos = 10

# Teto por execucao. Na primeira carga a tabela tem anos de historico; sem limite
# o job tentaria trazer tudo de uma vez, estouraria o tempo e nunca terminaria.
# Com teto ele avanca aos poucos, execucao a execucao, ate alcancar o presente.
$MaxPorExecucao = 20000

# --- inicio -----------------------------------------------------------------
if (-not $DestinoSenha) {
    throw 'PGPASSWORD nao definida no ambiente da maquina. Veja o cabecalho.'
}
Add-Type -Path $DllNpgsql

$conexaoPg = "Host=$DestinoHost;Port=$DestinoPorta;Database=$DestinoBase;" +
             "Username=$DestinoUser;Password=$DestinoSenha;SSL Mode=Require;" +
             "Trust Server Certificate=true;Timeout=30;Command Timeout=120"

$pg = New-Object Npgsql.NpgsqlConnection($conexaoPg)
$pg.Open()

try {
    # 1. Marca dagua: o proprio destino responde ate onde ja chegou. Nao ha
    #    estado guardado em arquivo para dessincronizar.
    $cmd = $pg.CreateCommand()
    $cmd.CommandText = @'
select coalesce(max(mar_datahorainc), timestamp '2000-01-01')
  from catraca.gac_marcacao
'@
    $marca = [datetime]$cmd.ExecuteScalar()
    $desde = $marca.AddMinutes(-$RecuoMinutos)
    Write-Output ("[{0:HH:mm:ss}] marca d'agua {1:yyyy-MM-dd HH:mm:ss}, lendo desde {2:yyyy-MM-dd HH:mm:ss}" -f (Get-Date), $marca, $desde)

    # 2. Origem: so o que entrou depois. O filtro e por MAR_DATAHORAINC, hora de
    #    insercao, e nao por MAR_DATAHORA, hora da passagem - catraca que ficou
    #    offline grava depois com a hora original, e essas linhas entrariam com
    #    data anterior a marca, invisiveis para sempre.
    $sql = New-Object System.Data.SqlClient.SqlConnection($OrigemSql)
    $sql.Open()
    try {
        $consulta = $sql.CreateCommand()
        $consulta.CommandTimeout = 120
        $consulta.CommandText = @"
SELECT TOP ($MaxPorExecucao)
       MAR_ID, MAR_TERMINAL, MAR_PESSOA, MAR_DATAHORA, MAR_FUNCAO,
       MAR_STATUS, MAR_STATUSBASICO, MAR_CRACHA, MAR_SENTIDO,
       MAR_TIPO, MAR_ORIGEM, MAR_DATAHORAINC
  FROM ACESSOTA.TELESSVR.GAC_MARCACAO
 WHERE MAR_DATAHORAINC > @desde
 ORDER BY MAR_DATAHORAINC
"@
        $p = $consulta.Parameters.Add('@desde', [System.Data.SqlDbType]::DateTime)
        $p.Value = $desde

        $tabela = New-Object System.Data.DataTable
        (New-Object System.Data.SqlClient.SqlDataAdapter($consulta)).Fill($tabela) | Out-Null
    }
    finally { $sql.Close() }

    if ($tabela.Rows.Count -eq 0) {
        Write-Output ("[{0:HH:mm:ss}] nada novo" -f (Get-Date))
        exit 0
    }

    # 3. Destino, numa transacao so. ON CONFLICT DO NOTHING e o que torna o job
    #    seguro de repetir: se cair no meio, rodar de novo nao duplica, e as
    #    linhas da sobreposicao sao descartadas em silencio.
    $tx = $pg.BeginTransaction()
    $ins = $pg.CreateCommand()
    $ins.Transaction = $tx
    $ins.CommandText = @'
insert into catraca.gac_marcacao
    (mar_id, mar_terminal, mar_pessoa, mar_datahora, mar_funcao,
     mar_status, mar_statusbasico, mar_cracha, mar_sentido,
     mar_tipo, mar_origem, mar_datahorainc)
values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
on conflict (mar_id) do nothing
'@
    1..12 | ForEach-Object { $ins.Parameters.Add((New-Object Npgsql.NpgsqlParameter)) | Out-Null }
    $ins.Prepare()

    $gravadas = 0
    foreach ($linha in $tabela.Rows) {
        for ($i = 0; $i -lt 12; $i++) {
            $valor = $linha[$i]
            $ins.Parameters[$i].Value = if ($valor -is [System.DBNull]) { [DBNull]::Value } else { $valor }
        }
        $gravadas += $ins.ExecuteNonQuery()
    }
    $tx.Commit()

    $ultima = $tabela.Rows[$tabela.Rows.Count - 1]['MAR_DATAHORAINC']
    Write-Output ("[{0:HH:mm:ss}] lidas {1}, gravadas {2} (o resto ja existia). Ate {3:yyyy-MM-dd HH:mm:ss}" -f (Get-Date), $tabela.Rows.Count, $gravadas, $ultima)

    # Atingiu o teto: ha mais para tras. Avisa para quem le o log saber que a
    # proxima execucao ainda esta correndo atras do presente.
    if ($tabela.Rows.Count -ge $MaxPorExecucao) {
        Write-Output ("[{0:HH:mm:ss}] teto de {1} atingido; ha mais na fila" -f (Get-Date), $MaxPorExecucao)
    }
}
finally {
    $pg.Close()
}
