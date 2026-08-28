<#
    Sobe backend + frontend do Insted Virtual Campus em duas janelas.

    Uso:
      .\start-dev.ps1                 # tempo real
      .\start-dev.ps1 -Demo 19:10     # relogio ancorado num horario letivo
      .\start-dev.ps1 -Demo 19:10 -Fator 8   # + tempo acelerado (8 min/s)
#>
param(
    [string]$Demo = "",
    [int]$Fator = 1
)

$raiz = $PSScriptRoot
$env:RELOGIO_DEMO = $Demo
$env:SIMULADOR_FATOR_TEMPO = $Fator

Write-Host "Insted Virtual Campus" -ForegroundColor Cyan
if ($Demo) {
    Write-Host "  relogio ancorado em $Demo (fator ${Fator}x)" -ForegroundColor DarkGray
} else {
    Write-Host "  relogio em tempo real" -ForegroundColor DarkGray
}

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$raiz\apps\backend-api'; " +
    "`$env:RELOGIO_DEMO='$Demo'; `$env:SIMULADOR_FATOR_TEMPO='$Fator'; " +
    "python -m uvicorn app.main:app --reload --port 8000"
)

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$raiz\apps\web-3d-frontend'; npm run dev"
)

Write-Host ""
Write-Host "  API     http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  Painel  http://127.0.0.1:5173"      -ForegroundColor Green
