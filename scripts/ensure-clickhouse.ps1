param(
    [int]$DockerReadyTimeoutSeconds = 120,
    [int]$ClickHouseReadyTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dockerComposeFile = Join-Path $repoRoot "docker-compose.yml"
$dotenvFile = Join-Path $repoRoot ".env"
$localEnvFile = Join-Path $repoRoot ".env.local.ps1"
$dockerDesktopExe = Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"

function Import-KeyValueEnvFile {
    param(
        [Parameter(Mandatory = $true)]
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

function Test-DockerDaemon {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerExecutable
    )

    try {
        $serverVersion = & $DockerExecutable info --format "{{.ServerVersion}}" 2>$null
        return -not [string]::IsNullOrWhiteSpace(($serverVersion | Out-String))
    }
    catch {
        return $false
    }
}

function Wait-ForDockerDaemon {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DockerExecutable,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerDaemon -DockerExecutable $DockerExecutable) {
            return $true
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

function Test-ClickHousePing {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://{0}:{1}/ping" -f $HostName, $Port) -TimeoutSec 3
        return $response.StatusCode -eq 200 -and $response.Content.Trim() -eq "Ok."
    }
    catch {
        return $false
    }
}

function Wait-ForClickHouse {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ClickHousePing -HostName $HostName -Port $Port) {
            return $true
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

function Initialize-ClickHouseSchema {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$User,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Password,
        [Parameter(Mandatory = $true)]
        [string]$Database,
        [Parameter(Mandatory = $true)]
        [string]$EnableIngestions
    )

    $env:CLICKHOUSE_HOST = $HostName
    $env:CLICKHOUSE_PORT = [string]$Port
    $env:CLICKHOUSE_USER = $User
    $env:CLICKHOUSE_PASSWORD = $Password
    $env:CLICKHOUSE_DB = $Database
    $env:CLICKHOUSE_ENABLE_INGESTIONS = $EnableIngestions

    $pythonExecutable = (Get-Command python -ErrorAction Stop).Source
    & $pythonExecutable (Join-Path $RepoRoot "scripts\init_clickhouse.py")
}

Import-KeyValueEnvFile -Path $dotenvFile
if (Test-Path -LiteralPath $localEnvFile) {
    . $localEnvFile
}

$storageMode = if ($env:ATAS_MS_STORAGE_MODE) { $env:ATAS_MS_STORAGE_MODE.Trim().ToLowerInvariant() } else { "clickhouse" }
if ($storageMode -in @("sqlite", "sqlite_authoritative", "sqlite-only", "sqlite_only")) {
    Write-Host "Storage mode '$storageMode' does not require ClickHouse startup."
    exit 0
}

$clickhouseHost = if ($env:ATAS_MS_CLICKHOUSE_HOST) {
    $env:ATAS_MS_CLICKHOUSE_HOST.Trim()
}
elseif ($env:CLICKHOUSE_HOST) {
    $env:CLICKHOUSE_HOST.Trim()
}
else {
    "127.0.0.1"
}

$probeHost = if ($clickhouseHost -in @("0.0.0.0", "::", "[::]")) { "127.0.0.1" } else { $clickhouseHost }
$clickhousePort = if ($env:ATAS_MS_CLICKHOUSE_PORT) { [int]$env:ATAS_MS_CLICKHOUSE_PORT } elseif ($env:CLICKHOUSE_PORT) { [int]$env:CLICKHOUSE_PORT } else { 8123 }
$clickhouseUser = if ($env:ATAS_MS_CLICKHOUSE_USER) { $env:ATAS_MS_CLICKHOUSE_USER } elseif ($env:CLICKHOUSE_USER) { $env:CLICKHOUSE_USER } else { "default" }
$clickhousePassword = if ($env:ATAS_MS_CLICKHOUSE_PASSWORD) { $env:ATAS_MS_CLICKHOUSE_PASSWORD } elseif ($env:CLICKHOUSE_PASSWORD) { $env:CLICKHOUSE_PASSWORD } else { "" }
$clickhouseDatabase = if ($env:ATAS_MS_CLICKHOUSE_DATABASE) { $env:ATAS_MS_CLICKHOUSE_DATABASE } elseif ($env:CLICKHOUSE_DB) { $env:CLICKHOUSE_DB } else { "market_data" }
$clickhouseEnableIngestions = if ($env:ATAS_MS_CLICKHOUSE_ENABLE_INGESTIONS) {
    $env:ATAS_MS_CLICKHOUSE_ENABLE_INGESTIONS
}
elseif ($env:CLICKHOUSE_ENABLE_INGESTIONS) {
    $env:CLICKHOUSE_ENABLE_INGESTIONS
}
else {
    "false"
}

if ($probeHost -notin @("127.0.0.1", "localhost")) {
    Write-Host "Configured ClickHouse host is $clickhouseHost. Skipping local Docker bootstrap and probing the configured host directly."
}
else {
    $dockerExecutable = (Get-Command docker -ErrorAction Stop).Source
    if (-not (Test-DockerDaemon -DockerExecutable $dockerExecutable)) {
        $dockerService = Get-Service com.docker.service -ErrorAction SilentlyContinue
        if ($dockerService -and $dockerService.Status -ne "Running") {
            try {
                Write-Host "Starting Docker service..."
                Start-Service -Name $dockerService.Name
            }
            catch {
                Write-Warning ("Unable to start Docker service directly. Trying Docker Desktop instead. Error: {0}" -f $_.Exception.Message)
            }
        }

        $dockerDesktopProcess = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
        if (-not $dockerDesktopProcess -and (Test-Path -LiteralPath $dockerDesktopExe)) {
            Write-Host "Starting Docker Desktop..."
            Start-Process -FilePath $dockerDesktopExe | Out-Null
        }

        if (-not (Wait-ForDockerDaemon -DockerExecutable $dockerExecutable -TimeoutSeconds $DockerReadyTimeoutSeconds)) {
            throw "Docker daemon did not become ready within $DockerReadyTimeoutSeconds seconds."
        }
    }

    if (-not (Test-ClickHousePing -HostName $probeHost -Port $clickhousePort)) {
        Write-Host "Starting ClickHouse container..."
        & $dockerExecutable compose -f $dockerComposeFile up -d clickhouse
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose failed while starting ClickHouse."
        }
    }
}

if (-not (Wait-ForClickHouse -HostName $probeHost -Port $clickhousePort -TimeoutSeconds $ClickHouseReadyTimeoutSeconds)) {
    throw "ClickHouse did not become reachable at http://$probeHost`:$clickhousePort within $ClickHouseReadyTimeoutSeconds seconds."
}

Initialize-ClickHouseSchema `
    -RepoRoot $repoRoot `
    -HostName $probeHost `
    -Port $clickhousePort `
    -User $clickhouseUser `
    -Password $clickhousePassword `
    -Database $clickhouseDatabase `
    -EnableIngestions $clickhouseEnableIngestions

Write-Host "ClickHouse ready at http://$probeHost`:$clickhousePort (db=$clickhouseDatabase)"
