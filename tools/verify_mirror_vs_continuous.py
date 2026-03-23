from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def _get_json(base_url: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    url = f"{base_url.rstrip('/')}{path}?{query}"
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def _first_last(items: list[dict[str, Any]], start_key: str, end_key: str) -> tuple[str | None, str | None]:
    if not items:
        return None, None
    return items[0].get(start_key), items[-1].get(end_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare raw mirror-bars with derived continuous-bars.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Application base URL.")
    parser.add_argument("--chart-instance-id", default=None, help="Optional chart_instance_id for mirror-bars.")
    parser.add_argument("--contract-symbol", required=True, help="Concrete contract symbol for mirror-bars.")
    parser.add_argument("--root-symbol", required=True, help="Root symbol for continuous-bars.")
    parser.add_argument("--timeframe", required=True, help="Timeframe, for example 1m.")
    parser.add_argument("--window-start-utc", required=True, help="Inclusive UTC window start.")
    parser.add_argument("--window-end-utc", required=True, help="Inclusive UTC window end.")
    parser.add_argument("--roll-mode", default="by_contract_start", help="Continuous roll_mode.")
    parser.add_argument("--adjustment-mode", default="none", help="Continuous adjustment_mode.")
    parser.add_argument("--limit", type=int, default=5000, help="Max rows to request.")
    parser.add_argument(
        "--include-contract-markers",
        action="store_true",
        help="Ask continuous-bars to include contract boundary markers.",
    )
    args = parser.parse_args()

    mirror = _get_json(
        args.base_url,
        "/api/v1/chart/mirror-bars",
        {
            "chart_instance_id": args.chart_instance_id,
            "contract_symbol": args.contract_symbol,
            "timeframe": args.timeframe,
            "window_start_utc": args.window_start_utc,
            "window_end_utc": args.window_end_utc,
            "limit": args.limit,
        },
    )
    continuous = _get_json(
        args.base_url,
        "/api/v1/chart/continuous-bars",
        {
            "root_symbol": args.root_symbol,
            "timeframe": args.timeframe,
            "roll_mode": args.roll_mode,
            "adjustment_mode": args.adjustment_mode,
            "window_start_utc": args.window_start_utc,
            "window_end_utc": args.window_end_utc,
            "limit": args.limit,
            "include_contract_markers": str(args.include_contract_markers).lower(),
        },
    )

    mirror_first, mirror_last = _first_last(mirror.get("bars", []), "started_at_utc", "ended_at_utc")
    cont_first, cont_last = _first_last(continuous.get("candles", []), "started_at_utc", "ended_at_utc")

    print("Mirror")
    print(f"  contract_symbol: {mirror.get('contract_symbol')}")
    print(f"  count: {mirror.get('count')}")
    print(f"  first/last: {mirror_first} -> {mirror_last}")

    print("Continuous")
    print(f"  root_symbol: {continuous.get('root_symbol')}")
    print(f"  roll_mode: {continuous.get('roll_mode')}")
    print(f"  adjustment_mode: {continuous.get('adjustment_mode')}")
    print(f"  count: {continuous.get('count')}")
    print(f"  first/last: {cont_first} -> {cont_last}")
    print("  contract_segments:")
    for segment in continuous.get("contract_segments", []):
        print(
            "   - "
            f"{segment.get('contract_symbol')} "
            f"{segment.get('segment_start_utc')} -> {segment.get('segment_end_utc')} "
            f"reason={segment.get('roll_reason')} bars={segment.get('source_bar_count')}"
        )

    continuous_contracts = {
        candle.get("source_contract_symbol")
        for candle in continuous.get("candles", [])
        if candle.get("source_contract_symbol")
    }
    confusion_reasons: list[str] = []
    if not continuous.get("contract_segments"):
        confusion_reasons.append("continuous response has no contract_segments")
    if mirror.get("bars") and continuous.get("candles") and mirror.get("bars") == continuous.get("candles"):
        confusion_reasons.append("continuous candles are byte-for-byte identical to mirror raw rows")
    if len(continuous_contracts) > 1 and len(continuous.get("contract_segments", [])) <= 1:
        confusion_reasons.append("multiple source contracts detected but contract_segments did not explain them")

    if confusion_reasons:
        print("Result")
        print("  status: POSSIBLE_CONFUSION")
        for item in confusion_reasons:
            print(f"  reason: {item}")
    else:
        print("Result")
        print("  status: SEPARATED")
        print(f"  mirror_contracts: {args.contract_symbol}")
        print(f"  continuous_contracts: {', '.join(sorted(continuous_contracts)) or 'none'}")


if __name__ == "__main__":
    main()
