$ForceRestart = $false
if ($args -contains "-ForceRestart") {
    $ForceRestart = $true
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logsDir = Join-Path $repoRoot "logs"
$dataDir = Join-Path $repoRoot "data"
$pidFile = Join-Path $logsDir "server.pid"
$stdoutFile = Join-Path $logsDir "server.out.log"
$stderrFile = Join-Path $logsDir "server.err.log"
$localEnvFile = Join-Path $repoRoot ".env.local.ps1"
$dotenvFile = Join-Path $repoRoot ".env"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$env:PYTHONPATH = Join-Path $repoRoot "src"

function Import-KeyValueEnvFile {
    param(
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Length -ne 2) {
            return
        }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path ("Env:{0}" -f $key) -Value $value
    }
}

Import-KeyValueEnvFile -Path $dotenvFile
if (Test-Path -LiteralPath $localEnvFile) {
    . $localEnvFile
}

if (-not $env:OPENAI_API_KEY) {
    Write-Warning "OPENAI_API_KEY is not set. AI endpoints may be unavailable."
}
else {
    Write-Host "AI provider: $($env:ATAS_MS_AI_PROVIDER) / model: $($env:ATAS_MS_AI_MODEL)"
}

function Test-WorkbenchRoute {
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8080/workbench/replay" -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-Port8080OwningPid {
    $line = netstat -ano -p tcp | Select-String '127.0.0.1:8080|0.0.0.0:8080|\[::\]:8080' | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    $parts = ($line.Line -replace "\s+", " ").Trim().Split(" ")
    if ($parts.Length -lt 5) {
        return $null
    }

    return $parts[-1]
}

function Stop-ExistingServerProcess {
    param(
        [string]$PidValue
    )

    if (-not $PidValue) {
        return
    }
    if ([int]$PidValue -le 0) {
        return
    }

    $process = Get-Process -Id $PidValue -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $PidValue -Force
        Write-Host "Stopped stale server process $PidValue"
    }
}

$existingPid = $null
if (Test-Path -LiteralPath $pidFile) {
    $existingPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $ForceRestart) {
    try {
        $listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction Stop | Select-Object -First 1
        if ($listener) {
            if (Test-WorkbenchRoute) {
                Write-Host "Port 8080 is already serving the current replay workbench. Reusing the existing server."
                exit 0
            }
            Write-Host "Port 8080 is occupied by a stale or incompatible service. Restarting it."
        }
    }
    catch {
    }
}

if ($existingPid) {
    $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Stop-ExistingServerProcess -PidValue $existingPid
    }
}

$portPid = Get-Port8080OwningPid
if ($portPid) {
    Stop-ExistingServerProcess -PidValue $portPid
}

$process = Start-Process `
    -FilePath "python" `
    -ArgumentList "-m", "atas_market_structure.server" `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile `
    -PassThru

$process.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Host "Started server with PID $($process.Id)"
