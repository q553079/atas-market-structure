param(
    [switch]$ValidateOnly,
    [switch]$Background,
    [switch]$SkipCollectorDeploy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$srcPath = Join-Path $repoRoot 'src'
$env:PYTHONPATH = $srcPath

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
        if (-not $line) {
            return
        }
        if ($line.StartsWith('#')) {
            return
        }

        $parts = $line -split '=', 2
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

$dotenvPath = Join-Path $repoRoot '.env'
$localEnvPs1 = Join-Path $repoRoot '.env.local.ps1'

Import-KeyValueEnvFile -Path $dotenvPath
if (Test-Path -LiteralPath $localEnvPs1) {
    . $localEnvPs1
}

$provider = if ($env:ATAS_MS_AI_PROVIDER) { $env:ATAS_MS_AI_PROVIDER } else { 'default' }
$model = if ($env:ATAS_MS_AI_MODEL) { $env:ATAS_MS_AI_MODEL } else { 'default' }
$pythonCmd = 'python -m atas_market_structure.server'

Write-Host ('Repo root : {0}' -f $repoRoot)
Write-Host ('PYTHONPATH: {0}' -f $env:PYTHONPATH)
Write-Host ('AI provider: {0}' -f $provider)
Write-Host ('AI model   : {0}' -f $model)

if (-not $env:OPENAI_API_KEY) {
    Write-Warning 'OPENAI_API_KEY is not set. AI chat/review endpoints may be unavailable.'
}

if ($ValidateOnly) {
    Write-Host 'Validation successful.'
    return
}

if (-not $SkipCollectorDeploy -and -not $Background) {
    $deployScript = Join-Path $PSScriptRoot 'deploy-collector.ps1'
    if (-not (Test-Path -LiteralPath $deployScript)) {
        throw "Collector deploy script not found: $deployScript"
    }

    & $deployScript -Build -SkipIfAtasRunning
}

if ($Background) {
    $backgroundScript = Join-Path $PSScriptRoot 'start-service-background.ps1'
    if (-not (Test-Path -LiteralPath $backgroundScript)) {
        throw "Background script not found: $backgroundScript"
    }
    & $backgroundScript -SkipCollectorDeploy:$SkipCollectorDeploy
    Write-Host 'Server start requested in background.'
    return
}

Push-Location $repoRoot
try {
    & python -m atas_market_structure.server
}
finally {
    Pop-Location
}
