from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8080"
PAYLOAD = {
    "cache_key": "NQ|15m|2026-03-11T00:13:00.000Z|2026-03-18T00:13:00.000Z",
    "instrument_symbol": "NQ",
    "display_timeframe": "15m",
    "window_start": "2026-03-11T00:13:00.000Z",
    "window_end": "2026-03-18T00:13:00.000Z",
    "chart_instance_id": None,
    "force_rebuild": True,
    "min_continuous_messages": 10,
}


def fetch_json(url: str, data: dict | None = None) -> dict:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req) as resp:
        print("status", resp.status, url)
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    build = fetch_json(f"{BASE}/api/v1/workbench/replay-builder/build", PAYLOAD)
    print("build keys", sorted(build.keys()))
    print("action", build.get("action"))
    print("reason", build.get("reason"))
    print("ingestion_id", build.get("ingestion_id"))
    print("summary", build.get("summary"))
    ingestion_id = build.get("ingestion_id")
    if ingestion_id:
        ingestion = fetch_json(f"{BASE}/api/v1/ingestions/{ingestion_id}")
        payload = ingestion.get("observed_payload") or {}
        candles = payload.get("candles") or []
        print("snapshot cache_key", payload.get("cache_key"))
        print("snapshot tf", payload.get("display_timeframe"))
        print("snapshot candles", len(candles))
        if candles:
            print("first candle", candles[0])
            print("last candle", candles[-1])
        else:
            print("raw_features", payload.get("raw_features"))


if __name__ == "__main__":
    main()
