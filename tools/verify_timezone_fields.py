from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TIMEZONE_FIELDS = [
    "chart_display_timezone_mode",
    "chart_display_timezone_name",
    "chart_display_utc_offset_minutes",
    "instrument_timezone_value",
    "instrument_timezone_source",
    "collector_local_timezone_name",
    "collector_local_utc_offset_minutes",
    "timestamp_basis",
    "timezone_capture_confidence",
]


def _print_field_check(scope: str, payload: dict[str, Any]) -> None:
    print(scope)
    missing = []
    for field in TIMEZONE_FIELDS:
        value = payload.get(field)
        status = "OK" if value not in (None, "") else "WARN"
        print(f"  {field}: {status} value={value!r}")
        if status == "WARN":
            missing.append(field)
    if missing:
        print(f"  summary: missing_or_empty={', '.join(missing)}")
    else:
        print("  summary: all timezone audit fields present")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect timezone-related fields in an adapter payload JSON file.")
    parser.add_argument("payload_path", help="Path to a JSON payload sample.")
    args = parser.parse_args()

    payload = json.loads(Path(args.payload_path).read_text(encoding="utf-8"))
    source = payload.get("source") or {}
    time_context = payload.get("time_context") or {}
    bars = payload.get("bars") or []

    print("Payload")
    print(f"  message_type: {payload.get('message_type')}")
    print(f"  instrument.symbol: {(payload.get('instrument') or {}).get('symbol')}")
    print(f"  source.chart_instance_id: {source.get('chart_instance_id')!r}")

    _print_field_check("Source", source)
    if time_context:
        _print_field_check("TimeContext", time_context)
    else:
        print("TimeContext")
        print("  summary: missing block")

    print("UTC Primary Times")
    utc_ok = True
    for field in ("observed_window_start", "observed_window_end"):
        value = payload.get(field)
        has_utc = isinstance(value, str) and (value.endswith("Z") or value.endswith("+00:00"))
        print(f"  {field}: {'OK' if has_utc else 'WARN'} value={value!r}")
        utc_ok = utc_ok and has_utc

    if bars:
        first_bar = bars[0]
        for field in ("started_at", "ended_at", "bar_timestamp_utc"):
            value = first_bar.get(field)
            has_utc = value is None or (isinstance(value, str) and (value.endswith("Z") or value.endswith("+00:00")))
            print(f"  bars[0].{field}: {'OK' if has_utc else 'WARN'} value={value!r}")
            utc_ok = utc_ok and has_utc
    else:
        print("  bars: WARN value=[]")
        utc_ok = False

    print("Result")
    if utc_ok:
        print("  status: UTC_PRIMARY_TIMES_PRESENT")
    else:
        print("  status: WARNINGS_PRESENT")
        print("  note: review missing timezone audit fields or non-UTC primary timestamps above")


if __name__ == "__main__":
    main()
