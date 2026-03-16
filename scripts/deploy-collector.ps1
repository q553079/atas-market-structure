param(
    [switch]$WaitForAtasExit,
    [int]$PollSeconds = 2
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $repoRoot "src-csharp\AtasMarketStructure.Adapter\bin\Debug\net10.0"
$targetDir = Join-Path $env:APPDATA "ATAS\Indicators"

$files = @(
    "AtasMarketStructure.Adapter.dll",
    "AtasMarketStructure.Adapter.deps.json"
)

if ($WaitForAtasExit) {
    while (Get-Process -Name "OFT.Platform" -ErrorAction SilentlyContinue) {
        Write-Host "ATAS is still running. Waiting $PollSeconds second(s)..."
        Start-Sleep -Seconds $PollSeconds
    }
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

foreach ($file in $files) {
    $sourcePath = Join-Path $buildDir $file
    $targetPath = Join-Path $targetDir $file

    if (-not (Test-Path $sourcePath)) {
        throw "Build artifact not found: $sourcePath"
    }

    Copy-Item -Path $sourcePath -Destination $targetPath -Force
}

Get-ChildItem $targetDir -Filter "AtasMarketStructure.Adapter.*" |
    Select-Object Name, Length, LastWriteTime
