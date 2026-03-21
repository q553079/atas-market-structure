$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repoRoot "logs\\server.pid"
$localEnvFile = Join-Path $repoRoot ".env.local.ps1"
$dotenvFile = Join-Path $repoRoot ".env"

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

$serverPort = if ($env:ATAS_MS_PORT) { [int]$env:ATAS_MS_PORT } else { 8080 }

function Get-ServicePortOwningPid {
    try {
        $listener = Get-NetTCPConnection -LocalPort $serverPort -State Listen -ErrorAction Stop | Select-Object -First 1
        if (-not $listener) {
            return $null
        }
        return $listener.OwningProcess
    }
    catch {
        return $null
    }
}

function Get-ServerProcessPid {
    $serverProcess = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -like "*-m atas_market_structure.server*"
        } |
        Sort-Object CreationDate -Descending |
        Select-Object -First 1

    if (-not $serverProcess) {
        return $null
    }

    return $serverProcess.ProcessId
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
    $processPid = Get-ServerProcessPid
    if (Stop-ServerProcess -PidValue $processPid) {
        exit 0
    }
    $portPid = Get-ServicePortOwningPid
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

$fallbackProcessPid = Get-ServerProcessPid
if ($fallbackProcessPid -and $fallbackProcessPid -ne $pidValue) {
    Stop-ServerProcess -PidValue $fallbackProcessPid | Out-Null
}

$fallbackPortPid = Get-ServicePortOwningPid
if ($fallbackPortPid -and $fallbackPortPid -ne $pidValue -and $fallbackPortPid -ne $fallbackProcessPid) {
    Stop-ServerProcess -PidValue $fallbackPortPid | Out-Null
}
