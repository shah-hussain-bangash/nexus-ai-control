param([int]$Port = 62346)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
& $nexusPython (Join-Path $PSScriptRoot 'check_local_pilot.py') --port $Port
exit $LASTEXITCODE
