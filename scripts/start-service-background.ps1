$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logsDir = Join-Path $repoRoot "logs"
$dataDir = Join-Path $repoRoot "data"
$pidFile = Join-Path $logsDir "server.pid"
$stdoutFile = Join-Path $logsDir "server.out.log"
$stderrFile = Join-Path $logsDir "server.err.log"
$localEnvFile = Join-Path $repoRoot ".env.local.ps1"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$env:PYTHONPATH = Join-Path $repoRoot "src"

if (Test-Path $localEnvFile) {
    . $localEnvFile
}

$existingPid = $null
if (Test-Path $pidFile) {
    $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
}

try {
    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8080 -State Listen -ErrorAction Stop | Select-Object -First 1
    if ($listener) {
        Write-Host "Port 8080 is already listening. Reusing the existing server."
        exit 0
    }
}
catch {
}

if ($existingPid) {
    $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Write-Host "Server already running with PID $existingPid"
        exit 0
    }
}

$process = Start-Process `
    -FilePath "python" `
    -ArgumentList "-m", "atas_market_structure.server" `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile `
    -PassThru

$process.Id | Set-Content $pidFile -Encoding ascii
Write-Host "Started server with PID $($process.Id)"
