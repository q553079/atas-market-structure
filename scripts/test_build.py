"""Test the pre-aggregate build path."""
import json
import urllib.request
from datetime import datetime, timedelta, UTC

url = "http://localhost:8080/api/v1/workbench/replay-builder/build"
now = datetime.now(tz=UTC)
payload = {
    "cache_key": f"NQ|1m|auto_test|{now.strftime('%Y%m%d%H%M%S')}",
    "instrument_symbol": "NQ",
    "display_timeframe": "1m",
    "window_start": (now - timedelta(days=1)).isoformat(),
    "window_end": now.isoformat(),
    "force_rebuild": True,
    "min_continuous_messages": 1,
}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        candles = result.get("core_snapshot", {}).get("candles", [])
        history_source = result.get("core_snapshot", {}).get("raw_features", {}).get("history_source", "unknown")
        print(f"Candles: {len(candles)}")
        print(f"History source: {history_source}")
        print(f"Action: {result.get('action')}")
        print(f"Reason: {result.get('reason', '')[:100]}")
        if candles:
            c = candles[-1]
            print(f"Last candle: {c['started_at']} O={c['open']} H={c['high']} L={c['low']} C={c['close']}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
