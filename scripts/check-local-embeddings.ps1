param([switch]$RunLocal, [string]$Model = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
$embeddingArgs = @((Join-Path $PSScriptRoot 'check_local_embeddings.py'))
if ($RunLocal) { $embeddingArgs += @('--run-local', '--model', $Model) }
& $nexusPython @embeddingArgs
exit $LASTEXITCODE
