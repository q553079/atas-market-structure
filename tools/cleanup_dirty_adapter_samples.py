from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any


@dataclass(frozen=True)
class CleanupSelection:
    raw_ingestion_ids: set[str]
    durable_ingestion_ids: set[str]
    durable_analysis_ids: set[str]
    backup_path: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up and remove dirty adapter samples plus their bridged durable artifacts.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/market_structure.db"),
        help="SQLite database path. Defaults to data/market_structure.db.",
    )
    parser.add_argument(
        "--clean-before-version",
        default="0.8.1-shell",
        help="Remove adapter samples whose adapter_version is older than this version. Default: 0.8.1-shell.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletion. Without this flag, the script only reports what would be removed.",
    )
    return parser.parse_args()


def normalize_version(version: str | None) -> tuple[int, ...]:
    if not version:
        return (0,)

    prefix = version.split("-", 1)[0]
    parts: list[int] = []
    for token in prefix.split("."):
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def select_dirty_rows(connection: sqlite3.Connection, clean_before_version: str) -> CleanupSelection:
    threshold = normalize_version(clean_before_version)
    raw_ingestion_ids: set[str] = set()
    durable_ingestion_ids: set[str] = set()
    durable_analysis_ids: set[str] = set()

    rows = connection.execute(
        """
        SELECT ingestion_id, ingestion_kind, source_snapshot_id, observed_payload_json
        FROM ingestions
        WHERE ingestion_kind IN ('adapter_continuous_state', 'adapter_trigger_burst')
        """,
    ).fetchall()

    bridge_snapshot_ids: set[str] = set()
    for row in rows:
        payload = json.loads(row["observed_payload_json"])
        source = payload.get("source", {})
        instrument = payload.get("instrument", {})
        adapter_version = source.get("adapter_version")
        symbol = instrument.get("symbol")
        message_id = payload.get("message_id")

        is_dirty_version = normalize_version(adapter_version) < threshold
        is_dirty_symbol = symbol in {"BARS", "UNKNOWN", "", None}
        if not is_dirty_version and not is_dirty_symbol:
            continue

        raw_ingestion_ids.add(row["ingestion_id"])
        if message_id:
            bridge_snapshot_ids.add(f"bridge-ms-{message_id}")
            bridge_snapshot_ids.add(f"bridge-evt-{message_id}")

    if bridge_snapshot_ids:
        placeholders = ", ".join("?" for _ in bridge_snapshot_ids)
        durable_rows = connection.execute(
            f"""
            SELECT ingestion_id
            FROM ingestions
            WHERE source_snapshot_id IN ({placeholders})
            """,
            tuple(bridge_snapshot_ids),
        ).fetchall()
        durable_ingestion_ids = {row["ingestion_id"] for row in durable_rows}

    if durable_ingestion_ids:
        placeholders = ", ".join("?" for _ in durable_ingestion_ids)
        analysis_rows = connection.execute(
            f"""
            SELECT analysis_id
            FROM analyses
            WHERE ingestion_id IN ({placeholders})
            """,
            tuple(durable_ingestion_ids),
        ).fetchall()
        durable_analysis_ids = {row["analysis_id"] for row in analysis_rows}

    return CleanupSelection(
        raw_ingestion_ids=raw_ingestion_ids,
        durable_ingestion_ids=durable_ingestion_ids,
        durable_analysis_ids=durable_analysis_ids,
        backup_path=None,
    )


def backup_database(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{db_path.stem}.cleanup-{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def delete_selection(connection: sqlite3.Connection, selection: CleanupSelection) -> dict[str, int]:
    deleted = {"analyses": 0, "durable_ingestions": 0, "raw_ingestions": 0}

    if selection.durable_analysis_ids:
        placeholders = ", ".join("?" for _ in selection.durable_analysis_ids)
        cursor = connection.execute(
            f"DELETE FROM analyses WHERE analysis_id IN ({placeholders})",
            tuple(selection.durable_analysis_ids),
        )
        deleted["analyses"] = cursor.rowcount

    all_ingestion_ids = tuple(selection.raw_ingestion_ids | selection.durable_ingestion_ids)
    if all_ingestion_ids:
        placeholders = ", ".join("?" for _ in all_ingestion_ids)
        cursor = connection.execute(
            f"DELETE FROM ingestions WHERE ingestion_id IN ({placeholders})",
            all_ingestion_ids,
        )
        deleted["raw_ingestions"] = len(selection.raw_ingestion_ids)
        deleted["durable_ingestions"] = max(0, cursor.rowcount - deleted["raw_ingestions"])

    connection.commit()
    return deleted


def main() -> None:
    args = parse_args()
    db_path = args.db_path.resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        selection = select_dirty_rows(connection, args.clean_before_version)
        print(
            json.dumps(
                {
                    "db_path": str(db_path),
                    "clean_before_version": args.clean_before_version,
                    "raw_ingestions": len(selection.raw_ingestion_ids),
                    "durable_ingestions": len(selection.durable_ingestion_ids),
                    "durable_analyses": len(selection.durable_analysis_ids),
                    "sample_raw_ingestions": sorted(selection.raw_ingestion_ids)[:5],
                    "sample_durable_ingestions": sorted(selection.durable_ingestion_ids)[:5],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        if not args.apply:
            return

        backup_path = backup_database(db_path)
        deleted = delete_selection(connection, selection)
        print(
            json.dumps(
                {
                    "applied": True,
                    "backup_path": str(backup_path),
                    "deleted": deleted,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
