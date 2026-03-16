$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repoRoot "logs\\server.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found."
    exit 0
}

$pidValue = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pidValue) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "PID file was empty."
    exit 0
}

$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $pidValue -Force
    Write-Host "Stopped server PID $pidValue"
}
else {
    Write-Host "Process $pidValue not found."
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
