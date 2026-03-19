import sqlite3
c = sqlite3.connect("data/market_structure.db").cursor()
c.execute("""
    SELECT stored_at,
           json_extract(observed_payload_json, '$.observed_window_start'),
           json_extract(observed_payload_json, '$.observed_window_end')
    FROM ingestions
    WHERE ingestion_kind='adapter_history_bars'
      AND instrument_symbol='NQ'
      AND stored_at > '2026-03-17T16:45:00'
    ORDER BY stored_at DESC LIMIT 5
""")
rows = c.fetchall()
print(f"history_bars after 16:45 UTC: {len(rows)}")
for r in rows:
    print(r)
