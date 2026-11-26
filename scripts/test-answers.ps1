param([switch]$LocalOllama, [string]$Model = 'qwen3:8b')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
$drillArgs = @((Join-Path $PSScriptRoot 'run_synthetic_answer_drill.py'))
if ($LocalOllama) { $drillArgs += @('--local-ollama', '--model', $Model) }
& $nexusPython @drillArgs
exit $LASTEXITCODE
