import sqlite3

conn = sqlite3.connect('data/market_structure.db')
cur = conn.cursor()
cur.execute("""
SELECT stored_at,
       json_extract(observed_payload_json, '$.source.adapter_version') AS adapter_version,
       instrument_symbol
FROM ingestions
WHERE ingestion_kind='adapter_continuous_state'
ORDER BY stored_at DESC
LIMIT 10
""")
rows = cur.fetchall()
print('latest adapter_continuous_state:')
for r in rows:
    print(r)
conn.close()
