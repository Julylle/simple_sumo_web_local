param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$backendDir = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $backendDir 'runtime'
$pythonPath = Join-Path $runtimeDir 'sumo-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create backend/runtime/sumo-venv and install backend/requirements-sumo.txt first.'
}
$healthUrl = "http://127.0.0.1:$Port/api/sumo/health"
try { $health = Invoke-RestMethod $healthUrl -TimeoutSec 2 } catch { $health = $null }
if ($health.service -eq 'windows-sumo') { Write-Output "SUMO service already running: $healthUrl"; exit 0 }
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'sumo_server:app', '--host', '127.0.0.1', '--port', "$Port", '--workers', '1') -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeDir 'sumo-service.out.log') -RedirectStandardError (Join-Path $runtimeDir 'sumo-service.err.log') -PassThru
$process.Id | Set-Content (Join-Path $runtimeDir 'sumo-service.pid')
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    try { $health = Invoke-RestMethod $healthUrl -TimeoutSec 2 } catch { $health = $null }
    if ($health.service -eq 'windows-sumo') {
        Write-Output "Windows SUMO service ready: $healthUrl (launcher PID $($process.Id))"
        exit 0
    }
}
throw "SUMO service did not become ready. See $runtimeDir/sumo-service.err.log."
