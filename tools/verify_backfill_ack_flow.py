from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a minimal backfill-command -> backfill-ack verification flow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Application base URL.")
    parser.add_argument("--instrument-symbol", required=True, help="Instrument symbol used for the request.")
    parser.add_argument("--contract-symbol", default=None, help="Optional contract_symbol.")
    parser.add_argument("--root-symbol", default=None, help="Optional root_symbol.")
    parser.add_argument("--chart-instance-id", required=True, help="Chart instance used to poll and acknowledge.")
    parser.add_argument("--display-timeframe", default="1m", help="Display timeframe for the repair request.")
    parser.add_argument("--window-start-utc", required=True, help="Inclusive UTC window start.")
    parser.add_argument("--window-end-utc", required=True, help="Inclusive UTC window end.")
    parser.add_argument("--request-history-footprint", action="store_true", help="Also request footprint resend.")
    args = parser.parse_args()

    request_payload = {
        "cache_key": f"{args.instrument_symbol}|{args.display_timeframe}|{args.window_start_utc}|{args.window_end_utc}",
        "instrument_symbol": args.instrument_symbol,
        "contract_symbol": args.contract_symbol,
        "root_symbol": args.root_symbol,
        "display_timeframe": args.display_timeframe,
        "window_start": args.window_start_utc,
        "window_end": args.window_end_utc,
        "chart_instance_id": args.chart_instance_id,
        "reason": "verify_backfill_ack_flow",
        "request_history_bars": True,
        "request_history_footprint": args.request_history_footprint,
        "missing_segments": [],
        "requested_ranges": [],
    }
    create = _http_json(
        "POST",
        f"{args.base_url.rstrip('/')}/api/v1/workbench/atas-backfill-requests",
        request_payload,
    )
    request_id = create["request"]["request_id"]

    poll_query = urlencode(
        {
            "instrument_symbol": args.instrument_symbol,
            "chart_instance_id": args.chart_instance_id,
            "contract_symbol": args.contract_symbol,
            "root_symbol": args.root_symbol,
        }
    )
    dispatch = _http_json(
        "GET",
        f"{args.base_url.rstrip('/')}/api/v1/adapter/backfill-command?{poll_query}",
    )
    ack_payload = {
        "request_id": request_id,
        "cache_key": request_payload["cache_key"],
        "instrument_symbol": args.instrument_symbol,
        "chart_instance_id": args.chart_instance_id,
        "acknowledged_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "acknowledged_history_bars": True,
        "acknowledged_history_footprint": args.request_history_footprint,
        "latest_loaded_bar_started_at": args.window_end_utc,
        "note": "verify_backfill_ack_flow",
    }
    ack = _http_json(
        "POST",
        f"{args.base_url.rstrip('/')}/api/v1/adapter/backfill-ack",
        ack_payload,
    )

    print("Dispatch")
    print(f"  request_id: {dispatch.get('request', {}).get('request_id')}")
    print(f"  instrument_symbol: {dispatch.get('request', {}).get('instrument_symbol')}")
    print(f"  contract_symbol: {dispatch.get('request', {}).get('contract_symbol')}")
    print(f"  root_symbol: {dispatch.get('request', {}).get('root_symbol')}")
    print(f"  chart_instance_id: {dispatch.get('request', {}).get('chart_instance_id')}")

    print("Ack")
    request_state = ack.get("request", {})
    print(f"  status: {request_state.get('status')}")
    print(f"  acknowledged_chart_instance_id: {request_state.get('acknowledged_chart_instance_id')}")
    print(f"  acknowledged_history_bars: {request_state.get('acknowledged_history_bars')}")
    print(f"  acknowledged_history_footprint: {request_state.get('acknowledged_history_footprint')}")
    print(f"  latest_loaded_bar_started_at: {request_state.get('latest_loaded_bar_started_at')}")
    print(f"  target_contract_symbol: {request_state.get('target_contract_symbol')}")
    print(f"  target_root_symbol: {request_state.get('target_root_symbol')}")


if __name__ == "__main__":
    main()
