$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
& $nexusPython (Join-Path $PSScriptRoot 'run_business_reference_example.py')
exit $LASTEXITCODE
