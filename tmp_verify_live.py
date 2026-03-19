import json
import sqlite3
import urllib.request
from datetime import datetime, timezone

DB_PATH = "data/market_structure.db"
SYMBOL = "NQ"
LIVE_STATUS_URL = f"http://127.0.0.1:8080/api/v1/workbench/live-status?instrument_symbol={SYMBOL}"


def utcnow():
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime:
    # Accept 'Z' and '+00:00'
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


print("=== live-status ===")
try:
    with urllib.request.urlopen(LIVE_STATUS_URL, timeout=5) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
except Exception as e:
    print("live-status request failed:", repr(e))
    payload = None

print("\n=== latest adapter_continuous_state (db) ===")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute(
    """
    SELECT stored_at,
           json_extract(observed_payload_json, '$.source.adapter_version') AS adapter_version,
           json_extract(observed_payload_json, '$.source.chart_instance_id') AS chart_instance_id,
           json_extract(observed_payload_json, '$.price_state.last_price') AS last_price
    FROM ingestions
    WHERE ingestion_kind='adapter_continuous_state' AND instrument_symbol=?
    ORDER BY stored_at DESC
    LIMIT 1
    """,
    (SYMBOL,),
)
row = cur.fetchone()
if not row:
    print("No continuous_state rows for", SYMBOL)
else:
    stored_at, version, chart_id, last_price = row
    t = parse_iso(stored_at)
    age = (utcnow() - t).total_seconds()
    print({
        "stored_at": stored_at,
        "age_seconds": round(age, 3),
        "adapter_version": version,
        "chart_instance_id": chart_id,
        "last_price": last_price,
    })

conn.close()
