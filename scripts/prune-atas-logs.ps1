param(
    [string]$LogPath = "C:\Users\666\AppData\Roaming\ATAS\Logs",
    [int]$RetentionHours = 24,
    [int]$MaxTotalSizeMB = 256,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $LogPath)) {
    Write-Host "ATAS log path not found: $LogPath"
    exit 0
}

$cutoff = (Get-Date).AddHours(-$RetentionHours)
$files = Get-ChildItem -LiteralPath $LogPath -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff }

if (-not $files) {
    Write-Host "No ATAS log files older than $RetentionHours hours under $LogPath"
}
else {
    $reclaimBytes = ($files | Measure-Object -Property Length -Sum).Sum
    Write-Host ("Pruning {0} file(s) older than {1} hours, reclaiming about {2:N2} GB from {3}" -f $files.Count, $RetentionHours, ($reclaimBytes / 1GB), $LogPath)

    foreach ($file in $files) {
        if ($WhatIf) {
            Write-Host "Would remove $($file.FullName)"
            continue
        }

        Remove-Item -LiteralPath $file.FullName -Force
    }
}

$remainingFiles = Get-ChildItem -LiteralPath $LogPath -File -Recurse -Force -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime
$currentBytes = ($remainingFiles | Measure-Object -Property Length -Sum).Sum
$maxBytes = $MaxTotalSizeMB * 1MB

if ($currentBytes -gt $maxBytes) {
    Write-Host ("ATAS logs still use {0:N2} MB, above cap {1} MB. Removing oldest files." -f ($currentBytes / 1MB), $MaxTotalSizeMB)

    foreach ($file in $remainingFiles) {
        if ($currentBytes -le $maxBytes) {
            break
        }

        if ($WhatIf) {
            Write-Host "Would remove for size cap $($file.FullName)"
        }
        else {
            Remove-Item -LiteralPath $file.FullName -Force
        }

        $currentBytes -= $file.Length
    }
}

$dirs = Get-ChildItem -LiteralPath $LogPath -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending

foreach ($dir in $dirs) {
    $hasChildren = Get-ChildItem -LiteralPath $dir.FullName -Force -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $hasChildren) {
        if ($WhatIf) {
            Write-Host "Would remove empty directory $($dir.FullName)"
        }
        else {
            Remove-Item -LiteralPath $dir.FullName -Force
        }
    }
}

if (-not $WhatIf) {
    Write-Host ("ATAS log pruning completed. Current size is about {0:N2} MB." -f ($currentBytes / 1MB))
}
