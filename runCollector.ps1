$ErrorActionPreference = "Stop"

# Resolve paths relative to this script
$projectDir = $PSScriptRoot
$backendDir = Join-Path $projectDir "backend"
$logDir = Join-Path $projectDir "logs"
$condaExe = "C:\ProgramData\miniconda3\Scripts\conda.exe"

# Load database and OPC UA settings
. (Join-Path $backendDir "scripts\load-database-env.ps1")

# Create the log directory
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Wait for the collector so Task Scheduler can track its lifetime
$collector = Start-Process `
    -FilePath $condaExe `
    -ArgumentList "run --no-capture-output -n sumo_web python -u -m database.collector" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput "$logDir\collector.log" `
    -RedirectStandardError "$logDir\collector_error.log" `
    -Wait `
    -PassThru

# Report the collector exit code to Task Scheduler
exit $collector.ExitCode