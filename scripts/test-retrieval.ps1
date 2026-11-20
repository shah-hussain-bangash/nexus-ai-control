$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
& $nexusPython (Join-Path $PSScriptRoot 'run_synthetic_retrieval_drill.py')
exit $LASTEXITCODE
