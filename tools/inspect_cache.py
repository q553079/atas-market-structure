from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/market_structure.db")


def main() -> None:
    print(f"db={DB_PATH.resolve()} exists={DB_PATH.exists()}")
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Sanity check for JSON1 extension.
    try:
        value = cur.execute("select json_extract('{\"a\": 1}', '$.a') as v").fetchone()["v"]
        print("json_extract_ok=", value)
    except Exception as exc:  # noqa: BLE001
        print("json_extract_ok=false error=", exc)

    tables = [row["name"] for row in cur.execute("select name from sqlite_master where type='table' order by name").fetchall()]
    print("tables=", tables)

    total_ing = cur.execute("select count(*) as c from ingestions").fetchone()["c"]
    print("ingestions_total=", total_ing)

    kinds = [
        "replay_workbench_snapshot",
        "adapter_continuous_state",
        "adapter_history_bars",
        "adapter_history_footprint",
        "replay_operator_entry",
        "replay_manual_region",
    ]
    for kind in kinds:
        c = cur.execute("select count(*) as c from ingestions where ingestion_kind=?", (kind,)).fetchone()["c"]
        print(f"count[{kind}]={c}")

    # Latest N replay snapshots (cache keys)
    rows = cur.execute(
        """
        select ingestion_id, stored_at, observed_payload_json
        from ingestions
        where ingestion_kind='replay_workbench_snapshot'
        order by stored_at desc
        limit 10
        """
    ).fetchall()

    print("\nlatest_replay_workbench_snapshot=")
    for row in rows:
        payload = json.loads(row["observed_payload_json"])
        print(
            "-",
            row["stored_at"],
            row["ingestion_id"],
            "cache_key=", payload.get("cache_key"),
            "symbol=", (payload.get("instrument") or {}).get("symbol"),
            "tf=", payload.get("display_timeframe"),
            "status=", ((payload.get("verification_state") or {}).get("status")),
        )

    # Sample an older record to test the 500-limit hypothesis.
    # If there are lots of snapshots, take record at offset 1200.
    total_replay = cur.execute("select count(*) as c from ingestions where ingestion_kind='replay_workbench_snapshot'").fetchone()["c"]
    print("\nreplay_workbench_snapshot_total=", total_replay)
    if total_replay > 1200:
        row = cur.execute(
            """
            select ingestion_id, stored_at, observed_payload_json
            from ingestions
            where ingestion_kind='replay_workbench_snapshot'
            order by stored_at desc
            limit 1 offset 1200
            """
        ).fetchone()
        if row is not None:
            payload = json.loads(row["observed_payload_json"])
            print("\nolder_sample=")
            print(
                "-",
                row["stored_at"],
                row["ingestion_id"],
                "cache_key=", payload.get("cache_key"),
                "symbol=", (payload.get("instrument") or {}).get("symbol"),
                "tf=", payload.get("display_timeframe"),
            )

    conn.close()


if __name__ == "__main__":
    main()
