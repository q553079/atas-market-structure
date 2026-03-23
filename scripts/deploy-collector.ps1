param(
    [switch]$Build,
    [switch]$WaitForAtasExit,
    [switch]$SkipIfAtasRunning,
    [string]$Configuration = "Debug",
    [int]$PollSeconds = 2
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $repoRoot "src-csharp\AtasMarketStructure.Adapter\AtasMarketStructure.Adapter.csproj"
$buildDir = Join-Path $repoRoot ("src-csharp\AtasMarketStructure.Adapter\bin\{0}\net10.0" -f $Configuration)
$targetDir = Join-Path $env:APPDATA "ATAS\Indicators"

$files = @(
    "AtasMarketStructure.Adapter.dll",
    "AtasMarketStructure.Adapter.deps.json"
)

if ($WaitForAtasExit -and $SkipIfAtasRunning) {
    throw "Use either -WaitForAtasExit or -SkipIfAtasRunning, not both."
}

if ($Build) {
    Write-Host "Building collector project ($Configuration)..."
    & dotnet build $projectPath -c $Configuration
    if ($LASTEXITCODE -ne 0) {
        throw "Collector build failed with exit code $LASTEXITCODE."
    }
}

if ($WaitForAtasExit) {
    while (Get-Process -Name "OFT.Platform" -ErrorAction SilentlyContinue) {
        Write-Host "ATAS is still running. Waiting $PollSeconds second(s)..."
        Start-Sleep -Seconds $PollSeconds
    }
}
elseif ($SkipIfAtasRunning -and (Get-Process -Name "OFT.Platform" -ErrorAction SilentlyContinue)) {
    Write-Warning "ATAS is still running. Collector deploy skipped so the backend start does not block."
    return
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

foreach ($file in $files) {
    $sourcePath = Join-Path $buildDir $file
    $targetPath = Join-Path $targetDir $file

    if (-not (Test-Path $sourcePath)) {
        throw "Build artifact not found: $sourcePath"
    }

    Write-Host "Deploying $file -> $targetPath"
    Copy-Item -Path $sourcePath -Destination $targetPath -Force
}

Get-ChildItem $targetDir -Filter "AtasMarketStructure.Adapter.*" |
    Select-Object Name, Length, LastWriteTime
