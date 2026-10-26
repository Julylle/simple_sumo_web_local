# Stop only a Python process running the database.collector module.
[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateRange(1, 2147483647)][int]$CollectorProcessId)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This script requires Windows.' }

function Test-CollectorProcess($ProcessInfo) {
    return ($null -ne $ProcessInfo -and
        $ProcessInfo.Name -match '^python(w)?\.exe$' -and
        $ProcessInfo.CommandLine -match '(?:^|\s)-m\s+["'']?database\.collector["'']?(?=\s|$)')
}

$candidates = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object { Test-CollectorProcess $_ })
if ($PSBoundParameters.ContainsKey('CollectorProcessId')) {
    $candidates = @($candidates | Where-Object { $_.ProcessId -eq $CollectorProcessId })
    if ($candidates.Count -eq 0) {
        throw "PID $CollectorProcessId is not a visible database.collector process. Nothing stopped."
    }
}
if ($candidates.Count -eq 0) {
    Write-Host 'No visible database.collector process found. Nothing stopped.'
    return
}
if ($candidates.Count -gt 1) {
    $candidates | Select-Object ProcessId, CreationDate, CommandLine | Format-List | Out-Host
    throw 'Multiple collectors found. Select one using .\stopCollector.ps1 -CollectorProcessId <PID>. Nothing stopped.'
}
$selected = $candidates[0]
$targetId = [int]$selected.ProcessId
if (-not $PSCmdlet.ShouldProcess("database.collector PID $targetId", 'Stop process')) { return }

# Recheck identity immediately before stopping, rather than trusting a stale PID.
$current = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId"
if ($null -eq $current) {
    Write-Host "Collector PID $targetId has already exited."
    return
}
if (-not (Test-CollectorProcess $current) -or $current.CreationDate -ne $selected.CreationDate) {
    throw "PID $targetId changed identity. Nothing stopped."
}
$targetProcess = Get-Process -Id $targetId
try {
    Stop-Process -InputObject $targetProcess -ErrorAction Stop
    if (-not $targetProcess.WaitForExit(5000)) {
        throw "Collector PID $targetId has not exited within 5 seconds."
    }
    Write-Host "Collector PID $targetId stopped."
    Write-Host 'Existing database records and spool files were retained. Do not delete collector.lock.'
} finally {
    $targetProcess.Dispose()
}
