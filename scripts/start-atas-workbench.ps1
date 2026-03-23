param(
    [string]$AtasExePath = $env:ATAS_EXE_PATH,
    [switch]$SkipDeploy,
    [switch]$SkipBrowser,
    [switch]$SkipAtas,
    [int]$HealthTimeoutSeconds = 30,
    [int]$AdapterTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$healthUrl = "http://127.0.0.1:8080/health"
$workbenchUrl = "http://127.0.0.1:8080/workbench/replay"
$databasePath = Join-Path $repoRoot "data\market_structure.db"
$startedAt = [DateTimeOffset]::UtcNow.ToString("o")

function Wait-ForHealth {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Wait-ForAdapterTraffic {
    param(
        [string]$DbPath,
        [string]$SinceIso,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Path $DbPath)) {
            Start-Sleep -Seconds 2
            continue
        }

        $result = @"
import json
import sqlite3
import sys

db_path = r"$DbPath"
since_iso = r"$SinceIso"
connection = sqlite3.connect(db_path)
connection.row_factory = sqlite3.Row
row = connection.execute(
    '''
    SELECT instrument_symbol, observed_payload_json, stored_at
    FROM ingestions
    WHERE ingestion_kind = 'adapter_continuous_state'
      AND stored_at > ?
    ORDER BY stored_at DESC
    LIMIT 1
    ''',
    (since_iso,),
).fetchone()
if row is None:
    sys.exit(1)
payload = json.loads(row["observed_payload_json"])
print(json.dumps({
    "instrument_symbol": row["instrument_symbol"],
    "chart_instance_id": payload.get("source", {}).get("chart_instance_id"),
    "adapter_version": payload.get("source", {}).get("adapter_version"),
    "stored_at": row["stored_at"],
}, ensure_ascii=True))
"@ | python -

        if ($LASTEXITCODE -eq 0 -and $result) {
            return $result
        }

        Start-Sleep -Seconds 2
    }

    return $null
}

if (-not $SkipDeploy) {
    & (Join-Path $PSScriptRoot "deploy-collector.ps1") -Build -WaitForAtasExit
}

& (Join-Path $PSScriptRoot "stop-service.ps1")
& (Join-Path $PSScriptRoot "start-service-background.ps1")

if (-not (Wait-ForHealth -Url $healthUrl -TimeoutSeconds $HealthTimeoutSeconds)) {
    throw "Workbench backend did not become healthy within $HealthTimeoutSeconds seconds."
}

Write-Host "Backend healthy at $healthUrl"

if (-not $SkipBrowser) {
    Start-Process $workbenchUrl | Out-Null
    Write-Host "Opened replay workbench in the default browser."
}

if (-not $SkipAtas) {
    if ($AtasExePath -and (Test-Path $AtasExePath)) {
        Start-Process -FilePath $AtasExePath | Out-Null
        Write-Host "Started ATAS: $AtasExePath"
    }
    else {
        Write-Host "ATAS exe path is not configured. Set ATAS_EXE_PATH or pass -AtasExePath to auto-start ATAS."
    }
}

$traffic = Wait-ForAdapterTraffic -DbPath $databasePath -SinceIso $startedAt -TimeoutSeconds $AdapterTimeoutSeconds
if ($traffic) {
    Write-Host "Adapter traffic detected: $traffic"
}
else {
    Write-Host "No fresh adapter traffic detected within $AdapterTimeoutSeconds seconds."
}
