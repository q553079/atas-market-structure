from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

from atas_market_structure.live_tail_candle_guardrails import suppress_tail_outlier_candles
from atas_market_structure.models import ChartCandle, ReplayChartBar, Timeframe
from tests.test_app_support import build_application, load_json_fixture


def _replay_bar(
    started_at: datetime,
    *,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: int = 12,
) -> ReplayChartBar:
    return ReplayChartBar(
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=1),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        delta=1,
        bid_volume=5,
        ask_volume=7,
        source_kind="chart_candles",
        is_synthetic=False,
    )


def test_suppress_tail_outlier_candles_repairs_stale_last_bar_without_next_anchor() -> None:
    base = datetime(2026, 3, 30, 1, 0, tzinfo=UTC)
    candles = [
        _replay_bar(base, open_price=4400.0, high_price=4400.8, low_price=4399.6, close_price=4400.5),
        _replay_bar(base + timedelta(minutes=1), open_price=4400.5, high_price=4401.1, low_price=4400.25, close_price=4400.9),
        _replay_bar(base + timedelta(minutes=2), open_price=4400.9, high_price=4434.0, low_price=4399.8, close_price=4401.0),
    ]

    repaired, repaired_count = suppress_tail_outlier_candles(candles, freshness="stale")

    assert repaired_count == 1
    assert repaired[-1].open == candles[-2].close
    assert repaired[-1].high == candles[-2].close
    assert repaired[-1].low == candles[-2].close
    assert repaired[-1].close == candles[-2].close


def test_replay_live_tail_repairs_isolated_overlay_spike_before_returning_candles() -> None:
    application = build_application()

    now = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    chart_bars = [
        ChartCandle(
            symbol="GC",
            timeframe=Timeframe.MIN_1,
            started_at=now - timedelta(minutes=7 - index),
            ended_at=now - timedelta(minutes=6 - index),
            source_started_at=now - timedelta(minutes=7 - index),
            open=4400.0 + (index * 0.5),
            high=4400.75 + (index * 0.5),
            low=4399.5 + (index * 0.5),
            close=4400.25 + (index * 0.5),
            volume=18,
            tick_volume=18,
            delta=2,
            updated_at=now - timedelta(minutes=6 - index),
            source_timezone="UTC",
        )
        for index in range(4)
    ]
    application._repository.replace_chart_candles(chart_bars)

    base_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    base_payload["instrument"]["symbol"] = "GC"
    base_payload["instrument"]["root_symbol"] = "GC"
    base_payload["instrument"]["contract_symbol"] = "GC"
    base_payload["source"]["instrument_symbol"] = "GC"
    base_payload["source"]["chart_instance_id"] = "chart-GC-tail-spike"

    def post_continuous(*, message_id: str, observed_at: datetime, last_price: float, best_bid: float, best_ask: float) -> None:
        payload = copy.deepcopy(base_payload)
        payload["message_id"] = message_id
        payload["observed_window_start"] = (observed_at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = observed_at.isoformat().replace("+00:00", "Z")
        payload["emitted_at"] = observed_at.isoformat().replace("+00:00", "Z")
        payload["price_state"]["last_price"] = last_price
        payload["price_state"]["best_bid"] = best_bid
        payload["price_state"]["best_ask"] = best_ask
        payload["trade_summary"]["trade_count"] = 1
        payload["trade_summary"]["volume"] = 3
        payload["trade_summary"]["aggressive_buy_volume"] = 2
        payload["trade_summary"]["aggressive_sell_volume"] = 1
        payload["trade_summary"]["net_delta"] = 1
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    post_continuous(
        message_id="gc-tail-normal-1",
        observed_at=now - timedelta(minutes=2) + timedelta(seconds=5),
        last_price=4402.0,
        best_bid=4401.75,
        best_ask=4402.25,
    )
    post_continuous(
        message_id="gc-tail-spike",
        observed_at=now - timedelta(minutes=2) + timedelta(seconds=20),
        last_price=4376.0,
        best_bid=4401.75,
        best_ask=4402.25,
    )
    post_continuous(
        message_id="gc-tail-normal-2",
        observed_at=now - timedelta(minutes=2) + timedelta(seconds=45),
        last_price=4402.25,
        best_bid=4402.0,
        best_ask=4402.5,
    )
    post_continuous(
        message_id="gc-tail-follow-1",
        observed_at=now - timedelta(minutes=1) + timedelta(seconds=5),
        last_price=4402.5,
        best_bid=4402.25,
        best_ask=4402.75,
    )
    post_continuous(
        message_id="gc-tail-follow-2",
        observed_at=now - timedelta(minutes=1) + timedelta(seconds=40),
        last_price=4402.75,
        best_bid=4402.5,
        best_ask=4403.0,
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=GC&display_timeframe=1m&chart_instance_id=chart-GC-tail-spike&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    target_started_at = (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    target_bar = next(candle for candle in payload["candles"] if candle["started_at"] == target_started_at)

    assert payload["latest_price"] == 4402.75
    assert target_bar["low"] >= 4401.5
    assert target_bar["high"] <= 4402.75
    assert 4401.5 <= target_bar["close"] <= 4402.75
