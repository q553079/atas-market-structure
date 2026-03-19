$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repoRoot "logs\\server.pid"

function Get-Port8080OwningPid {
    $line = netstat -ano -p tcp | Select-String "127.0.0.1:8080|0.0.0.0:8080|\[::\]:8080" | Select-Object -First 1
    if (-not $line) {
        return $null
    }
    $parts = ($line.Line -replace "\s+", " ").Trim().Split(" ")
    if ($parts.Length -lt 5) {
        return $null
    }
    return $parts[-1]
}

function Stop-ServerProcess {
    param(
        [string]$PidValue
    )
    if (-not $PidValue) {
        return $false
    }
    if ([int]$PidValue -le 0) {
        return $false
    }
    $process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $PidValue -Force
        Write-Host "Stopped server PID $PidValue"
        return $true
    }
    return $false
}

if (-not (Test-Path $pidFile)) {
    $portPid = Get-Port8080OwningPid
    if (Stop-ServerProcess -PidValue $portPid) {
        exit 0
    }
    Write-Host "No PID file found."
    exit 0
}

$pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pidValue) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "PID file was empty."
    exit 0
}

if (-not (Stop-ServerProcess -PidValue $pidValue)) {
    Write-Host "Process $pidValue not found."
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue

$fallbackPortPid = Get-Port8080OwningPid
if ($fallbackPortPid -and $fallbackPortPid -ne $pidValue) {
    Stop-ServerProcess -PidValue $fallbackPortPid | Out-Null
}
