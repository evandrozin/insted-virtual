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

.PRE_REQUISITO
    Driver ODBC do PostgreSQL (psqlODBC), 64 bits. Um MSI, uma vez:

        https://www.postgresql.org/ftp/odbc/versions/msi/

    Escolhido em vez do Npgsql de proposito. O Npgsql 8 so tem build para .NET
    moderno, e o powershell.exe do Windows roda sobre .NET Framework - a
    biblioteca carrega e falha por assembly incompativel. Versoes antigas do
    Npgsql funcionariam, mas arrastam meia duzia de DLLs de dependencia. O ODBC
    ja vem com System.Data.Odbc, que faz parte do .NET Framework.

.CREDENCIAIS
    Vem do ambiente, nunca do arquivo - este script fica versionado no Git.
    Defina em Propriedades do Sistema > Variaveis de Ambiente, na caixa de baixo
    (System variables). A de cima e do usuario logado, e o servico do Agent roda
    com outra conta - nao enxerga:

        PGHOST      aws-0-sa-east-1.pooler.supabase.com
        PGUSER      postgres.<ref-do-projeto>
        PGPASSWORD  ...

    Reinicie o servico do SQL Server Agent depois de definir.
#>

$ErrorActionPreference = 'Stop'

# --- configuracao -----------------------------------------------------------
$OrigemSql    = 'Server=10.25.0.81,1433;Database=ACESSOTA;Integrated Security=true;TrustServerCertificate=true'
$DestinoBase  = 'postgres'
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

# Linhas por INSERT. Cada comando e uma ida e volta ate o Supabase; uma por linha
# levaria horas na carga inicial.
#
# 50 e nao 200: o protocolo do Postgres aceita 65.535 parametros, mas o psqlODBC
# nao chega la. Com 200 linhas (2.400 parametros) ele trunca a lista de tipos que
# monta internamente e o servidor recebe 'timestam' em vez de 'timestamp'. Com 50
# sao 600 parametros, dentro do que o driver aguenta.
$LinhasPorLote = 50

# Coluna e o tipo para o qual o valor e convertido no destino.
#
# Todo parametro vai como texto, com cast explicito no SQL. Parece rodeio, mas
# tira do driver a tarefa de mapear tipo - que e justamente onde ele falhava - e
# de paso elimina a conversao de data dependente de locale: a formatacao ISO e
# feita aqui, nao pelo ODBC.
$Campos = @(
    @{ nome = 'mar_id';           tipo = 'uuid' },
    @{ nome = 'mar_terminal';     tipo = 'bigint' },
    @{ nome = 'mar_pessoa';       tipo = 'bigint' },
    @{ nome = 'mar_datahora';     tipo = 'timestamp' },
    @{ nome = 'mar_funcao';       tipo = 'bigint' },
    @{ nome = 'mar_status';       tipo = 'text' },
    @{ nome = 'mar_statusbasico'; tipo = 'text' },
    @{ nome = 'mar_cracha';       tipo = 'text' },
    @{ nome = 'mar_sentido';      tipo = 'text' },
    @{ nome = 'mar_tipo';         tipo = 'text' },
    @{ nome = 'mar_origem';       tipo = 'text' },
    @{ nome = 'mar_datahorainc';  tipo = 'timestamp' }
)
$Colunas = $Campos | ForEach-Object { $_.nome }

function ConverterParaTexto($valor) {
    # Texto que o Postgres consegue converter, ou DBNull.
    if ($null -eq $valor -or $valor -is [System.DBNull]) { return [DBNull]::Value }
    if ($valor -is [datetime]) { return $valor.ToString('yyyy-MM-dd HH:mm:ss.fff') }
    if ($valor -is [guid])     { return $valor.ToString() }
    return [System.Convert]::ToString($valor, [System.Globalization.CultureInfo]::InvariantCulture)
}

# --- pre-requisitos ---------------------------------------------------------
$driver = (Get-OdbcDriver -Platform 64-bit -ErrorAction SilentlyContinue |
           Where-Object Name -like 'PostgreSQL*Unicode*' |
           Select-Object -First 1).Name
if (-not $driver) {
    throw ("Driver ODBC do PostgreSQL (64 bits) nao encontrado. " +
           "Instale o psqlODBC: https://www.postgresql.org/ftp/odbc/versions/msi/")
}

foreach ($v in 'PGHOST','PGUSER','PGPASSWORD') {
    if (-not (Get-Item "env:$v" -ErrorAction SilentlyContinue).Value) {
        throw ("$v nao esta definida. Defina em System variables (caixa de baixo) " +
               "e reinicie o servico do SQL Server Agent. Veja o cabecalho.")
    }
}

# UseServerSidePrepare=0: com prepare no servidor o driver monta uma lista de
# tipos por parametro, e e ai que ele trunca em comandos grandes. Sem isso o
# comando vai inteiro, com os casts explicitos fazendo o trabalho.
$conexaoPg = "Driver={$driver};Server=$($env:PGHOST);Port=$DestinoPorta;" +
             "Database=$DestinoBase;Uid=$($env:PGUSER);Pwd=$($env:PGPASSWORD);" +
             "SSLmode=require;UseServerSidePrepare=0;"

function Registrar($mensagem) {
    Write-Output ("[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $mensagem)
}

# --- inicio -----------------------------------------------------------------
$pg = New-Object System.Data.Odbc.OdbcConnection($conexaoPg)
$pg.Open()

try {
    # 1. Marca dagua: o proprio destino responde ate onde ja chegou. Nao ha
    #    estado guardado em arquivo para dessincronizar.
    $cmd = $pg.CreateCommand()
    $cmd.CommandText = "select coalesce(max(mar_datahorainc), timestamp '2000-01-01') from catraca.gac_marcacao"
    $marca = [datetime]$cmd.ExecuteScalar()
    $desde = $marca.AddMinutes(-$RecuoMinutos)
    Registrar ("marca d'agua {0:yyyy-MM-dd HH:mm:ss}; lendo desde {1:yyyy-MM-dd HH:mm:ss}" -f $marca, $desde)

    # 2. Origem: so o que entrou depois. O filtro e por MAR_DATAHORAINC, hora de
    #    insercao, e nao por MAR_DATAHORA, hora da passagem - catraca que ficou
    #    offline grava depois com a hora original, e essas linhas entrariam com
    #    data anterior a marca, invisiveis para sempre.
    $sql = New-Object System.Data.SqlClient.SqlConnection($OrigemSql)
    $sql.Open()
    try {
        $consulta = $sql.CreateCommand()
        $consulta.CommandTimeout = 300
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
        Registrar 'nada novo'
        exit 0
    }

    # 3. Destino, em lotes, numa transacao so. ON CONFLICT DO NOTHING e o que
    #    torna o job seguro de repetir: se cair no meio, rodar de novo nao
    #    duplica, e as linhas da sobreposicao somem em silencio.
    $tx = $pg.BeginTransaction()
    $gravadas = 0
    try {
        for ($inicio = 0; $inicio -lt $tabela.Rows.Count; $inicio += $LinhasPorLote) {
            $fim = [Math]::Min($inicio + $LinhasPorLote, $tabela.Rows.Count) - 1
            $lote = $inicio..$fim

            # Cada valor entra como texto com cast explicito - ver o comentario
            # em $Campos sobre por que nao se deixa o driver mapear os tipos.
            $marcadores = '(' + (($Campos | ForEach-Object { "cast(? as $($_.tipo))" }) -join ',') + ')'
            $grupos = $lote | ForEach-Object { $marcadores }

            $ins = $pg.CreateCommand()
            $ins.Transaction = $tx
            $ins.CommandTimeout = 300
            $ins.CommandText = "insert into catraca.gac_marcacao (" +
                               ($Colunas -join ',') + ") values " + ($grupos -join ',') +
                               " on conflict (mar_id) do nothing"

            foreach ($i in $lote) {
                foreach ($c in 0..($Campos.Count - 1)) {
                    # O ODBC ignora o nome e usa a ordem; o nome so aparece em
                    # mensagem de erro.
                    $p = $ins.Parameters.Add("p$($i)_$c", [System.Data.Odbc.OdbcType]::VarChar)
                    $p.Value = ConverterParaTexto $tabela.Rows[$i][$c]
                }
            }
            $gravadas += $ins.ExecuteNonQuery()
        }
        $tx.Commit()
    }
    catch {
        $tx.Rollback()
        throw
    }

    $ultima = $tabela.Rows[$tabela.Rows.Count - 1]['MAR_DATAHORAINC']
    Registrar ("lidas {0}, gravadas {1} (o resto ja existia). Ate {2:yyyy-MM-dd HH:mm:ss}" -f $tabela.Rows.Count, $gravadas, $ultima)

    # Atingiu o teto: ha mais para tras. Avisa para quem le o log saber que a
    # proxima execucao ainda esta correndo atras do presente.
    if ($tabela.Rows.Count -ge $MaxPorExecucao) {
        Registrar ("teto de {0} atingido; ha mais na fila" -f $MaxPorExecucao)
    }
}
finally {
    $pg.Close()
}
