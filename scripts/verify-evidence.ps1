param(
    [Parameter(Position=0, Mandatory=$true)]
    [string]$ReportPath,
    [string]$Workspace,
    [string]$Account,
    [string]$Environment
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$nexusPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nexusPython)) { throw 'Run npm run setup first.' }
# Preserve the caller's directory when resolving a relative report path.
$report = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ReportPath)
$nexusArguments = @((Join-Path $PSScriptRoot 'verify_supplier_evidence.py'), $report)
if ($Workspace) { $nexusArguments += @('--workspace', $Workspace) }
if ($Account) { $nexusArguments += @('--account', $Account) }
if ($Environment) { $nexusArguments += @('--environment', $Environment) }
& $nexusPython @nexusArguments
exit $LASTEXITCODE
