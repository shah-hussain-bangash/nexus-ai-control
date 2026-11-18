param(
    [ValidateSet('Setup', 'Run', 'Build', 'Test', 'Account')]
    [string]$Action = 'Run',
    [ValidateRange(0, 65535)]
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv\Scripts\python.exe'
function Check-Exit {
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE). Read the error above." }
}
Push-Location $root
try {
    if ($Action -eq 'Setup') {
        if (-not (Test-Path -LiteralPath $python)) {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                & py -3 -m venv .venv
            } elseif (Get-Command python -ErrorAction SilentlyContinue) {
                & python -m venv .venv
            } else { throw 'Install Python, then reopen Cursor and run Setup again.' }
            Check-Exit
        }
        & $python -m pip install -r backend/requirements.txt
        Check-Exit
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js, then reopen Cursor.' }
        Push-Location frontend
        try {
            & npm.cmd ci
            Check-Exit
            & npm.cmd run build
            Check-Exit
        } finally { Pop-Location }
        Push-Location backend
        try {
            & $python -m nexus.cli init
            Check-Exit
        } finally { Pop-Location }
        Write-Host 'Setup complete. Save any generated login password above. Run npm start.'
    } elseif ($Action -eq 'Account') {
        if (-not (Test-Path -LiteralPath $python)) { throw 'Run npm run setup first.' }
        & $python scripts/set_local_account.py
        Check-Exit
    } elseif ($Action -eq 'Build') {
        Push-Location frontend
        try { & npm.cmd run build; Check-Exit } finally { Pop-Location }
    } else {
        if (-not (Test-Path -LiteralPath $python)) { throw 'Run npm run setup first.' }
        if ($Action -eq 'Run') {
            Push-Location backend
            try {
                if ($PSBoundParameters.ContainsKey('Port')) {
                    & $python -m nexus.local --port $Port
                } else {
                    & $python -m nexus.local
                }
                Check-Exit
            } finally { Pop-Location }
        } else {
            & $python -m pip install -r backend/requirements-dev.txt
            Check-Exit
            Push-Location backend
            try { & $python -m pytest; Check-Exit } finally { Pop-Location }
            Push-Location frontend
            try { & npm.cmd test; Check-Exit } finally { Pop-Location }
        }
    }
} finally { Pop-Location }
