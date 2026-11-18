$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
python -m venv .venv
Check-Exit
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Check-Exit
Push-Location frontend
npm.cmd ci
Check-Exit
npm.cmd run build
Check-Exit
Pop-Location
Set-Location backend
& ..\.venv\Scripts\python.exe -m nexus.cli init
Check-Exit
& ..\.venv\Scripts\python.exe -m nexus.local @args
Check-Exit
