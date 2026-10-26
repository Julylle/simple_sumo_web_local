# Dot-source this script before starting the backend or the collector:
# . .\backend\scripts\load-database-env.ps1
param([string]$Path = (Join-Path $PSScriptRoot '..\database\.env'))
$ErrorActionPreference = 'Stop'
foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
    $text = $line.Trim()
    if (!$text -or $text.StartsWith('#')) { continue }
    $parts = $text.Split('=', 2)
    if ($parts.Length -ne 2 -or $parts[0] -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw 'Invalid .env entry. Use KEY=value, one entry per line.'
    }
    $value = $parts[1].Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($parts[0], $value, 'Process')
}
Write-Host 'Database settings loaded into this PowerShell session.'
