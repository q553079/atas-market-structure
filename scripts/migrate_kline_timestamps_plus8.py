#!/usr/bin/env python3
"""
Fix mis-shifted adapter K-line timestamps by adding a fixed UTC offset.

Scope (safe-by-default):
- chart_candles rows for one symbol up to that symbol's latest history-bar end
- ingestions.observed_payload_json for:
  - adapter_history_bars
  - adapter_history_footprint
  - replay_workbench_snapshot

Only selected timestamp keys are shifted to avoid touching true UTC fields like
`emitted_at` / `stored_at`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ISO_INSTANT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

SHIFT_KEYS = {
    "started_at",
    "ended_at",
    "window_start",
    "window_end",
    "observed_window_start",
    "observed_window_end",
    "requested_window_start",
    "requested_window_end",
    "actual_window_start",
    "actual_window_end",
    "history_coverage_start",
    "history_coverage_end",
    "latest_loaded_bar_started_at",
    "prev_ended_at",
    "next_started_at",
    "range_start",
    "range_end",
}

HISTORY_KINDS = ("adapter_history_bars", "adapter_history_footprint")
JSON_MIGRATE_KINDS = ("adapter_history_bars", "adapter_history_footprint", "replay_workbench_snapshot")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _format_like_original(dt: datetime, original: str) -> str:
    if original.endswith("Z"):
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    return dt.isoformat(timespec="seconds")


def _shift_iso(value: str, *, add_hours: int) -> tuple[str, bool]:
    if not isinstance(value, str) or not ISO_INSTANT_RE.match(value):
        return value, False
    shifted = _parse_utc(value) + timedelta(hours=add_hours)
    return _format_like_original(shifted, value), True


def _shift_selected_keys(value: Any, *, add_hours: int) -> tuple[Any, int]:
    changes = 0
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in SHIFT_KEYS and isinstance(item, str):
                new_item, changed = _shift_iso(item, add_hours=add_hours)
                out[key] = new_item
                changes += 1 if changed else 0
                continue
            nested, cnt = _shift_selected_keys(item, add_hours=add_hours)
            out[key] = nested
            changes += cnt
        return out, changes
    if isinstance(value, list):
        out_list: list[Any] = []
        for item in value:
            nested, cnt = _shift_selected_keys(item, add_hours=add_hours)
            out_list.append(nested)
            changes += cnt
        return out_list, changes
    return value, 0


def _backup_db(db_path: Path) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_suffix(db_path.suffix + f".bak-{stamp}")
    shutil.copy2(db_path, backup)
    return backup


def _find_symbol_history_cutoff(conn: sqlite3.Connection, symbol: str) -> str | None:
    cur = conn.execute(
        """
        SELECT observed_payload_json
        FROM ingestions
        WHERE instrument_symbol = ?
          AND ingestion_kind IN (?, ?)
        """,
        (symbol, *HISTORY_KINDS),
    )
    latest: datetime | None = None
    for (payload_json,) in cur.fetchall():
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue
        value = payload.get("observed_window_end")
        if not isinstance(value, str) or not ISO_INSTANT_RE.match(value):
            continue
        dt = _parse_utc(value)
        if latest is None or dt > latest:
            latest = dt
    return None if latest is None else latest.isoformat(timespec="seconds")


def migrate_chart_candles(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    add_hours: int,
    dry_run: bool,
) -> tuple[int, int, str | None]:
    cutoff_iso = _find_symbol_history_cutoff(conn, symbol)
    if cutoff_iso is None:
        print(f"[chart] no history cutoff found for symbol={symbol}, skip")
        return 0, 0, None

    rows = conn.execute(
        """
        SELECT symbol, timeframe, started_at, ended_at, open, high, low, close, volume, tick_volume, delta, updated_at
        FROM chart_candles
        WHERE symbol = ?
          AND started_at <= ?
        ORDER BY timeframe, started_at
        """,
        (symbol, cutoff_iso),
    ).fetchall()

    shifted_rows: list[tuple[Any, ...]] = []
    shifted_count = 0
    for row in rows:
        started_new, changed1 = _shift_iso(row[2], add_hours=add_hours)
        ended_new, changed2 = _shift_iso(row[3], add_hours=add_hours)
        shifted_count += (1 if changed1 else 0) + (1 if changed2 else 0)
        shifted_rows.append(
            (
                row[0],
                row[1],
                started_new,
                ended_new,
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
            )
        )

    if not dry_run and rows:
        conn.execute(
            """
            DELETE FROM chart_candles
            WHERE symbol = ?
              AND started_at <= ?
            """,
            (symbol, cutoff_iso),
        )
        conn.executemany(
            """
            INSERT INTO chart_candles
            (symbol, timeframe, started_at, ended_at, open, high, low, close, volume, tick_volume, delta, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            shifted_rows,
        )

    print(
        f"[chart] symbol={symbol} cutoff={cutoff_iso} rows_scanned={len(rows)} "
        f"rows_rewritten={len(rows)} iso_values_shifted={shifted_count}"
    )
    return len(rows), shifted_count, cutoff_iso


def migrate_ingestion_json(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    add_hours: int,
    dry_run: bool,
) -> tuple[int, int]:
    rows = conn.execute(
        """
        SELECT ingestion_id, ingestion_kind, observed_payload_json
        FROM ingestions
        WHERE instrument_symbol = ?
          AND ingestion_kind IN (?, ?, ?)
        ORDER BY stored_at
        """,
        (symbol, *JSON_MIGRATE_KINDS),
    ).fetchall()

    updated = 0
    shifted_values = 0
    for ingestion_id, ingestion_kind, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            print(f"[skip] {ingestion_id} invalid JSON", file=sys.stderr)
            continue

        patched, changed = _shift_selected_keys(payload, add_hours=add_hours)
        shifted_values += changed
        if changed == 0:
            continue

        if not dry_run:
            conn.execute(
                "UPDATE ingestions SET observed_payload_json = ? WHERE ingestion_id = ?",
                (json.dumps(patched, ensure_ascii=True, separators=(",", ":")), ingestion_id),
            )
        updated += 1
        print(f"[ingestion] {ingestion_id} kind={ingestion_kind} iso_values_shifted={changed}")

    print(
        f"[ingestion] symbol={symbol} rows_scanned={len(rows)} rows_updated={updated} "
        f"iso_values_shifted={shifted_values}"
    )
    return updated, shifted_values


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix mis-shifted K-line timestamps (+8h by default).")
    parser.add_argument("--db", type=Path, default=Path("data/market_structure.db"))
    parser.add_argument("--symbol", type=str, default="GC")
    parser.add_argument("--add-hours", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.exists():
        print(f"db not found: {db_path}", file=sys.stderr)
        return 1

    symbol = args.symbol.upper().strip()

    if not args.dry_run and not args.no_backup:
        backup = _backup_db(db_path)
        print(f"backup: {backup}")

    conn = sqlite3.connect(db_path, timeout=120.0)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        migrate_chart_candles(
            conn,
            symbol=symbol,
            add_hours=args.add_hours,
            dry_run=args.dry_run,
        )
        migrate_ingestion_json(
            conn,
            symbol=symbol,
            add_hours=args.add_hours,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            conn.rollback()
            print("dry-run complete (rolled back)")
        else:
            conn.commit()
            print("migration complete")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
