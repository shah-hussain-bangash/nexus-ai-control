param([switch]$Watch)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
function Run-Git {
    & git -c "safe.directory=$($root.Replace('\','/'))" @args
    if ($LASTEXITCODE -ne 0) { throw 'GitHub sync stopped. Read the Git message above, resolve it, and rerun this command.' }
}
function Publish-Changes {
    $unmerged = Run-Git ls-files --unmerged
    if ($unmerged) { throw 'Resolve the existing merge conflicts before syncing.' }
    Run-Git add --all
    & git -c "safe.directory=$($root.Replace('\','/'))" diff --cached --quiet
    $difference = $LASTEXITCODE
    if ($difference -eq 1) {
        Run-Git commit -m "Update NEXUS source ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))"
    } elseif ($difference -ne 0) { throw 'Could not inspect source changes.' }
    Run-Git push --set-upstream origin HEAD
    Write-Host "GitHub is up to date ($(Get-Date -Format 'HH:mm:ss'))."
}
Push-Location $root
$lock = $null
try {
    $gitDir = (Run-Git rev-parse --absolute-git-dir | Out-String).Trim()
    try {
        $lock = [System.IO.File]::Open((Join-Path $gitDir 'nexus-sync.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { throw 'Another NEXUS sync process is running. Use its terminal or stop it first.' }
    $remote = (Run-Git remote get-url origin | Out-String).Trim()
    Write-Host "Syncing source to $remote"
    Publish-Changes
    if ($Watch) {
        Write-Host 'Auto-sync is ON. Save your source files in Cursor. After 5 quiet seconds, changes are committed and uploaded.'
        Write-Host 'Keep this terminal open. Ctrl+C stops auto-sync. Ignored passwords and local data stay on this computer.'
        $previous = ''
        $changedAt = Get-Date
        while ($true) {
            Start-Sleep -Seconds 2
            $status = (Run-Git status --porcelain=v1 | Out-String)
            $fingerprint = $status
            if ($status.Trim()) {
                $stamps = foreach ($file in (Run-Git -c core.quotepath=false ls-files --cached --others --exclude-standard)) {
                    if (Test-Path -LiteralPath $file -PathType Leaf) {
                        $item = Get-Item -LiteralPath $file
                        "$file $($item.Length) $($item.LastWriteTimeUtc.Ticks)"
                    }
                }
                $fingerprint += ($stamps -join "`n")
            }
            if ($fingerprint -ne $previous) { $previous = $fingerprint; $changedAt = Get-Date }
            elseif ($status.Trim() -and ((Get-Date) - $changedAt).TotalSeconds -ge 5) {
                Publish-Changes
                $previous = ''
            }
        }
    }
} finally {
    if ($lock) { $lock.Dispose() }
    Pop-Location
}
