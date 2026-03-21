#!/usr/bin/env python3
"""
Migrate China wall-clock timestamps that were stored with a UTC suffix.

The ATAS adapter reported Beijing time with a Z suffix, e.g.
``...T12:59:59Z`` when the wall-clock was actually 12:59 Beijing.
The true UTC instant is 8 hours LATER (e.g. 20:59 UTC).

This script ADDS a configurable offset (default 8 hours) to every
full ISO-8601 instant string in JSON columns.

Usage
-----
Dry-run::

    python scripts/migrate_mislabeled_cst_as_utc.py --db data/market_structure.db --dry-run

Apply (+8 hours)::

    python scripts/migrate_mislabeled_cst_as_utc.py --db data/market_structure.db

Also fix chat_sessions::

    python scripts/migrate_mislabeled_cst_as_utc.py --db data/market_structure.db --fix-chat-sessions
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

# Matches a full ISO-8601 instant: date + time (HH:MM:SS) + optional microseconds + Z or numeric tz
_ISO_INSTANT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})$"
)


def _parse_utc(s: str) -> datetime:
    s2 = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s2).astimezone(UTC)


def _format_like_original(dt: datetime, original: str) -> str:
    use_z = original.endswith("Z")
    body = dt.isoformat(timespec="seconds")
    if use_z:
        return body.replace("+00:00", "Z")
    return body


def _shift(s: str, add_hours: int) -> tuple[str, bool]:
    if not isinstance(s, str) or not _ISO_INSTANT.match(s):
        return s, False
    dt = _parse_utc(s) + timedelta(hours=add_hours)
    return _format_like_original(dt, s), True


def _walk(value: Any, add_hours: int) -> tuple[Any, int]:
    changes = 0
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            nv, c = _walk(v, add_hours)
            changes += c
            out[k] = nv
        return out, changes
    if isinstance(value, list):
        out_list = []
        for item in value:
            nv, c = _walk(item, add_hours)
            changes += c
            out_list.append(nv)
        return out_list, changes
    if isinstance(value, str):
        ns, changed = _shift(value, add_hours)
        if changed:
            return ns, changes + 1
        return value, changes
    return value, changes


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    bak = db_path.with_suffix(db_path.suffix + f".bak-{stamp}")
    shutil.copy2(db_path, bak)
    return bak


def migrate_ingestions(
    conn: sqlite3.Connection,
    *,
    add_hours: int,
    dry_run: bool,
    stored_at_before: str | None,
) -> int:
    clauses = ["(ingestion_kind = 'replay_workbench_snapshot' OR observed_payload_json LIKE '%candles%')"]
    params: list[str] = []
    if stored_at_before:
        clauses.append("stored_at < ?")
        params.append(stored_at_before)
    where = " AND ".join(clauses)
    cur = conn.execute(
        f"SELECT ingestion_id, observed_payload_json, stored_at FROM ingestions WHERE {where}",
        params,
    )
    rows = cur.fetchall()
    total_changes = 0
    updated = 0
    for ingestion_id, payload_json, stored_at in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as e:
            print(f"[skip] {ingestion_id}: invalid JSON ({e})", file=sys.stderr)
            continue
        new_payload, n = _walk(payload, add_hours)
        total_changes += n
        if n == 0:
            continue
        new_json = json.dumps(new_payload, separators=(",", ":"), ensure_ascii=True)
        if not dry_run:
            conn.execute(
                "UPDATE ingestions SET observed_payload_json = ? WHERE ingestion_id = ?",
                (new_json, ingestion_id),
            )
        updated += 1
        print(f"ingestions {ingestion_id} stored_at={stored_at} iso_strings_adjusted={n}")
    print(f"-- ingestions: rows_scanned={len(rows)} rows_updated={updated} iso_strings_adjusted={total_changes}")
    return updated


def migrate_chat_sessions(
    conn: sqlite3.Connection,
    *,
    add_hours: int,
    dry_run: bool,
) -> int:
    cur = conn.execute("SELECT session_id, window_range_json FROM chat_sessions")
    rows = cur.fetchall()
    updated = 0
    total_changes = 0
    for session_id, wr_json in rows:
        try:
            wr = json.loads(wr_json)
        except json.JSONDecodeError:
            continue
        new_wr, n = _walk(wr, add_hours)
        total_changes += n
        if n == 0:
            continue
        new_json = json.dumps(new_wr, separators=(",", ":"), ensure_ascii=True)
        if not dry_run:
            conn.execute(
                "UPDATE chat_sessions SET window_range_json = ? WHERE session_id = ?",
                (new_json, session_id),
            )
        updated += 1
        print(f"chat_sessions {session_id} iso_strings_adjusted={n}")
    print(f"-- chat_sessions: rows_scanned={len(rows)} rows_updated={updated} iso_strings_adjusted={total_changes}")
    return updated


def main() -> int:
    p = argparse.ArgumentParser(
        description="Add hours to UTC-labelled instant strings that are actually China wall-clock times."
    )
    p.add_argument("--db", type=Path, default=Path("data/market_structure.db"))
    p.add_argument(
        "--add-hours",
        type=int,
        default=8,
        help="Hours to ADD to each instant (default: 8 — CST mislabeled as UTC needs +8 to become true UTC).",
    )
    p.add_argument("--dry-run", action="store_true", help="Scan and report only; do not write.")
    p.add_argument(
        "--stored-at-before",
        type=str,
        default=None,
        help="Only ingestions with stored_at < this ISO string (e.g. 2026-03-21T00:00:00+00:00).",
    )
    p.add_argument("--fix-chat-sessions", action="store_true", help="Also adjust chat_sessions.window_range_json.")
    p.add_argument("--no-backup", action="store_true", help="Skip creating a .bak copy (not recommended).")
    args = p.parse_args()

    db_path = args.db.resolve()
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    if not args.dry_run and not args.no_backup:
        bak = _backup(db_path)
        print(f"Backup written: {bak}")

    conn = sqlite3.connect(db_path, timeout=60.0)
    try:
        migrate_ingestions(
            conn,
            add_hours=args.add_hours,
            dry_run=args.dry_run,
            stored_at_before=args.stored_at_before,
        )
        if args.fix_chat_sessions:
            migrate_chat_sessions(conn, add_hours=args.add_hours, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    if args.dry_run:
        print("Dry-run complete (no writes). Re-run without --dry-run to apply.")
    else:
        print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
