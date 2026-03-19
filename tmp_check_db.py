import sqlite3, json
from datetime import datetime
conn = sqlite3.connect("data/market_structure.db")
cur = conn.cursor()

# 1. Latest continuous_state
cur.execute("""
    SELECT stored_at,
           json_extract(observed_payload_json, '$.source.adapter_version'),
           json_extract(observed_payload_json, '$.price_state.last_price')
    FROM ingestions
    WHERE ingestion_kind = 'adapter_continuous_state' AND instrument_symbol = 'NQ'
    ORDER BY stored_at DESC LIMIT 5
""")
print("=== Latest continuous_state ===")
for row in cur.fetchall():
    print(row)

# 2. Latest history_bars
cur.execute("""
    SELECT stored_at,
           json_extract(observed_payload_json, '$.source.adapter_version'),
           json_extract(observed_payload_json, '$.bar_count')
    FROM ingestions
    WHERE ingestion_kind = 'adapter_history_bars' AND instrument_symbol = 'NQ'
    ORDER BY stored_at DESC LIMIT 3
""")
print("\n=== Latest history_bars ===")
for row in cur.fetchall():
    print(row)

# 3. Time gaps in last 200 records
cur.execute("""
    SELECT stored_at
    FROM ingestions
    WHERE ingestion_kind = 'adapter_continuous_state' AND instrument_symbol = 'NQ'
    ORDER BY stored_at DESC LIMIT 200
""")
rows = [r[0] for r in cur.fetchall()]
print(f"\n=== Gap check (last {len(rows)} records) ===")
gaps = 0
for i in range(1, len(rows)):
    t1 = datetime.fromisoformat(rows[i-1].replace('+00:00',''))
    t2 = datetime.fromisoformat(rows[i].replace('+00:00',''))
    gap = (t1 - t2).total_seconds()
    if gap > 5:
        gaps += 1
        if gap > 30:
            print(f"  GAP {gap:.0f}s: {rows[i]} -> {rows[i-1]}")
print(f"Total gaps >5s: {gaps}")
conn.close()
