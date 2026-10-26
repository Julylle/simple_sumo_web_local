# Run from a normal PowerShell window; administrator privileges are not required.
param([string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This launcher requires Windows.' }

$backendDir = Join-Path $PSScriptRoot 'backend'
$logDir = Join-Path $PSScriptRoot 'logs'
. (Join-Path $backendDir 'scripts\load-database-env.ps1')

# Respect the same spool location as database.collector. Never delete its lock.
$spoolDir = $env:RAW_SPOOL_DIR
if ([string]::IsNullOrWhiteSpace($spoolDir)) {
    $spoolDir = Join-Path $backendDir 'raw_spool'
} elseif (-not [IO.Path]::IsPathRooted($spoolDir)) {
    $spoolDir = Join-Path $backendDir $spoolDir
}
$lockPath = Join-Path $spoolDir 'collector.lock'
if (Test-Path -LiteralPath $lockPath) {
    $lockStream = $null
    try {
        $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::Open,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        $lockStream.Lock(0, 1)
        $lockStream.Unlock(0, 1)
    } catch {
        Write-Warning 'Collector lock is in use or cannot be checked. Nothing started; the existing collector is untouched.'
        Write-Host "Lock: $lockPath"
        return
    } finally {
        if ($null -ne $lockStream) { $lockStream.Dispose() }
    }
}
# The collector also acquires this lock itself, covering concurrent launchers.
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    if ($env:CONDA_DEFAULT_ENV -eq 'sumo_web' -and $env:CONDA_PREFIX) {
        $PythonPath = Join-Path $env:CONDA_PREFIX 'python.exe'
    } else {
        throw 'Activate conda environment sumo_web first, or pass -PythonPath with its full python.exe path.'
    }
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable not found: $PythonPath"
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
# Separate logs per launch: never truncate logs belonging to an existing process.
$launchId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$stdout = Join-Path $logDir "collector_$launchId.log"
$stderr = Join-Path $logDir "collector_$launchId.error.log"
$collectorProcess = Start-Process -FilePath $PythonPath `
    -ArgumentList '-u -m database.collector' `
    -WorkingDirectory $backendDir -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Start-Sleep -Seconds 2
$collectorProcess.Refresh()
if ($collectorProcess.HasExited) {
    Write-Host "Collector exited. Inspect: $stderr"
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 20 }
    throw 'Background collector did not remain running.'
}
Write-Host "Background collector started. PID: $($collectorProcess.Id)"
Write-Host "Log: $stderr"
Write-Host "Output: $stdout"
Write-Host 'Confirm raw data: stored ... in the log. You may close this terminal; logout/reboot will not restart the collector.'
