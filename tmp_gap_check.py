import sqlite3, json
from datetime import datetime, timezone

conn = sqlite3.connect("data/market_structure.db")
cur = conn.cursor()

# Check history bars coverage around the gap (UTC 16:00 - 19:00 on 03/17)
cur.execute("""
    SELECT stored_at, 
           json_extract(observed_payload_json, '$.bar_timeframe'),
           json_extract(observed_payload_json, '$.observed_window_start'),
           json_extract(observed_payload_json, '$.observed_window_end')
    FROM ingestions
    WHERE ingestion_kind = 'adapter_history_bars' AND instrument_symbol = 'NQ'
    ORDER BY stored_at DESC LIMIT 5
""")
print("=== Latest history_bars ingestions ===")
for row in cur.fetchall():
    print(row)

# Check continuous_state around the gap
cur.execute("""
    SELECT stored_at,
           json_extract(observed_payload_json, '$.price_state.last_price')
    FROM ingestions
    WHERE ingestion_kind = 'adapter_continuous_state' 
      AND instrument_symbol = 'NQ'
      AND stored_at >= '2026-03-17T15:50:00'
      AND stored_at <= '2026-03-17T19:10:00'
    ORDER BY stored_at
""")
rows = cur.fetchall()
print(f"\n=== continuous_state around gap (15:50-19:10 UTC) ===")
print(f"Total records: {len(rows)}")
if rows:
    print(f"First: {rows[0]}")
    print(f"Last:  {rows[-1]}")
    # Find the gap
    for i in range(1, len(rows)):
        t1 = datetime.fromisoformat(rows[i-1][0].replace('+00:00',''))
        t2 = datetime.fromisoformat(rows[i][0].replace('+00:00',''))
        gap = (t2 - t1).total_seconds()
        if gap > 60:
            print(f"  GAP {gap/60:.1f}min: {rows[i-1][0]} -> {rows[i][0]}")

# Check latest data (after 0.10.4 deploy)
cur.execute("""
    SELECT stored_at,
           json_extract(observed_payload_json, '$.source.adapter_version'),
           json_extract(observed_payload_json, '$.price_state.last_price')
    FROM ingestions
    WHERE ingestion_kind = 'adapter_continuous_state' AND instrument_symbol = 'NQ'
    ORDER BY stored_at DESC LIMIT 3
""")
print("\n=== Latest continuous_state (check 0.10.4) ===")
for row in cur.fetchall():
    print(row)

conn.close()
