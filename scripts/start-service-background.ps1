param(
    [switch]$ForceRestart,
    [switch]$SkipCollectorDeploy,
    [switch]$WaitForAtasExitBeforeDeploy,
    [switch]$SkipDatabaseStart
)

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

$serverHost = if ($env:ATAS_MS_HOST) { $env:ATAS_MS_HOST } else { "127.0.0.1" }
$serverPort = if ($env:ATAS_MS_PORT) { [int]$env:ATAS_MS_PORT } else { 8080 }
$probeHost = if ($serverHost -in @("0.0.0.0", "::", "[::]")) { "127.0.0.1" } else { $serverHost }
$storageMode = if ($env:ATAS_MS_STORAGE_MODE) { $env:ATAS_MS_STORAGE_MODE } else { "clickhouse" }

if (-not $env:OPENAI_API_KEY) {
    Write-Warning "OPENAI_API_KEY is not set. AI endpoints may be unavailable."
}
else {
    Write-Host "AI provider: $($env:ATAS_MS_AI_PROVIDER) / model: $($env:ATAS_MS_AI_MODEL)"
}
Write-Host "Server bind: $serverHost`:$serverPort"
Write-Host "Storage mode: $storageMode"

if (-not $SkipCollectorDeploy) {
    $deployScript = Join-Path $PSScriptRoot "deploy-collector.ps1"
    if (-not (Test-Path -LiteralPath $deployScript)) {
        throw "Collector deploy script not found: $deployScript"
    }

    if ($WaitForAtasExitBeforeDeploy) {
        & $deployScript -Build -WaitForAtasExit
    }
    else {
        & $deployScript -Build -SkipIfAtasRunning
    }
}

if (-not $SkipDatabaseStart) {
    $databaseBootstrapScript = Join-Path $PSScriptRoot "ensure-clickhouse.ps1"
    if (-not (Test-Path -LiteralPath $databaseBootstrapScript)) {
        throw "ClickHouse bootstrap script not found: $databaseBootstrapScript"
    }

    try {
        & $databaseBootstrapScript
    }
    catch {
        Write-Warning ("ClickHouse bootstrap failed. Continuing with degraded-mode startup. Error: {0}" -f $_.Exception.Message)
    }
}

function Test-WorkbenchRoute {
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://${probeHost}:${serverPort}/workbench/replay" -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-ServiceListener {
    try {
        $listeners = Get-NetTCPConnection -LocalPort $serverPort -State Listen -ErrorAction Stop
        if (-not $listeners) {
            return $null
        }

        $scopedListener = $listeners |
            Where-Object { $_.LocalAddress -eq $probeHost } |
            Select-Object -First 1
        if ($scopedListener) {
            return $scopedListener
        }

        if ($serverHost -in @("0.0.0.0", "::", "[::]")) {
            return $listeners |
                Where-Object { $_.LocalAddress -in @("0.0.0.0", "::", "[::]") } |
                Select-Object -First 1
        }

        return $null
    }
    catch {
        return $null
    }
}

function Get-ServicePortOwningPid {
    $listener = Get-ServiceListener
    if (-not $listener) {
        return $null
    }

    return $listener.OwningProcess
}

function Get-ServerProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -like "*-m atas_market_structure.server*"
        } |
        Sort-Object CreationDate -Descending |
        Select-Object -First 1
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
    $listener = Get-ServiceListener
    if ($listener) {
        if (Test-WorkbenchRoute) {
            Write-Host "Port $serverPort is already serving the current replay workbench. Reusing the existing server."
            exit 0
        }
        Write-Host "Port $serverPort is occupied by a stale or incompatible service. Restarting it."
    }
}

if ($existingPid) {
    $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
        Stop-ExistingServerProcess -PidValue $existingPid
    }
}

$portPid = Get-ServicePortOwningPid
if ($portPid) {
    Stop-ExistingServerProcess -PidValue $portPid
}

$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$launchStartedAt = Get-Date
$process = Start-Process `
    -FilePath $pythonExecutable `
    -ArgumentList "-m", "atas_market_structure.server" `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutFile `
    -RedirectStandardError $stderrFile `
    -PassThru

$resolvedPid = $null
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    Start-Sleep -Milliseconds 500
    $candidate = Get-ServerProcess
    if ($candidate -and ([datetime]$candidate.CreationDate) -ge $launchStartedAt.AddSeconds(-2)) {
        $resolvedPid = $candidate.ProcessId
        break
    }
}

if (-not $resolvedPid) {
    $resolvedPid = $process.Id
}

$resolvedPid | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Host "Started server with PID $resolvedPid"
