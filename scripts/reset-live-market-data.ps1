param(
    [switch]$Vacuum
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dbPath = Join-Path $repoRoot "data\market_structure.db"
$backupDir = Join-Path $repoRoot "data\backups"

if (-not (Test-Path -LiteralPath $dbPath)) {
    throw "SQLite database not found: $dbPath"
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupDir ("market_structure.pre_reset.{0}.db" -f $timestamp)
Copy-Item -LiteralPath $dbPath -Destination $backupPath -Force
Write-Host "Backed up database to $backupPath"

$pythonScript = @'
from pathlib import Path
import sqlite3

db_path = Path(r"__DB_PATH__")
vacuum = "__VACUUM__" == "1"

conn = sqlite3.connect(db_path)
try:
    cur = conn.cursor()
    before = {}
    for table in ("ingestions", "atas_chart_bars_raw", "chart_candles"):
        before[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    cur.execute("BEGIN")
    cur.execute("DELETE FROM ingestions")
    cur.execute("DELETE FROM atas_chart_bars_raw")
    cur.execute("DELETE FROM chart_candles")
    conn.commit()

    after = {}
    for table in ("ingestions", "atas_chart_bars_raw", "chart_candles"):
        after[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    if vacuum:
        cur.execute("VACUUM")

    for table in ("ingestions", "atas_chart_bars_raw", "chart_candles"):
        print(f"{table}: {before[table]} -> {after[table]}")
finally:
    conn.close()
'@

$escapedDbPath = $dbPath.Replace("\", "\\")
$pythonScript = $pythonScript.Replace("__DB_PATH__", $escapedDbPath)
$pythonScript = $pythonScript.Replace("__VACUUM__", $(if ($Vacuum) { "1" } else { "0" }))

$pythonScript | python -
