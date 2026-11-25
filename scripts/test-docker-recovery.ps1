param([switch]$Run)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Create .venv and install backend/requirements-dev.txt first.' }
$mode = if ($Run) { '--run' } else { '--check' }
& $nexusPython (Join-Path $PSScriptRoot 'run_docker_recovery_drill.py') $mode
exit $LASTEXITCODE
