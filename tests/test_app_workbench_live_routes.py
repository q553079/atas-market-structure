from __future__ import annotations

import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ChartCandle,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiReviewRequest,
    ReplayWorkbenchBuildRequest,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import ApplicationRequestHandler
from atas_market_structure.strategy_library_services import StrategyLibraryService
from tests.test_app_support import (
    FakeReplayChatAssistant,
    FakeReplayReviewer,
    TEST_DB_DIR,
    build_application,
    load_fixture,
    load_json_fixture,
)

def test_replay_live_status_reports_latest_adapter_sync_and_refresh_need() -> None:
    application = build_application()

    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["source"]["instrument_symbol"] = "NQ"
    continuous_payload["source"]["emitted_at"] = "2026-03-17T09:00:10Z"
    continuous_payload["observed_at"] = "2026-03-17T09:00:10Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["source"]["instrument_symbol"] = "NQ"
    history_payload["emitted_at"] = "2026-03-17T09:00:15Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )

    status_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/live-status?instrument_symbol=NQ&replay_ingestion_id={replay_payload['ingestion_id']}",
    )

    assert status_response.status_code == 200
    status_payload = json.loads(status_response.body)
    assert status_payload["instrument_symbol"] == "NQ"
    assert status_payload["latest_continuous_state"]["latest_ingestion_id"] is not None
    assert status_payload["latest_history_bars"]["latest_ingestion_id"] is not None
    assert status_payload["latest_adapter_sync_at"] is not None
    assert status_payload["stream_state"] in {"live", "delayed", "stale"}
    assert status_payload["should_refresh_snapshot"] is True

def test_replay_live_tail_returns_latest_price_and_recent_candles() -> None:
    application = build_application()

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["source"]["instrument_symbol"] = "NQ"
    continuous_payload["source"]["chart_instance_id"] = "NQ-live-tail"
    continuous_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T09:00:01Z"
    continuous_payload["emitted_at"] = "2026-03-17T09:00:01Z"
    continuous_payload["price_state"]["last_price"] = 24843.0
    continuous_payload["price_state"]["best_bid"] = 24842.75
    continuous_payload["price_state"]["best_ask"] = 24843.0

    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    follow_up_payload = copy.deepcopy(continuous_payload)
    follow_up_payload["message_id"] = "adapter-msg-20260317-090002"
    follow_up_payload["observed_window_end"] = "2026-03-17T09:00:02Z"
    follow_up_payload["emitted_at"] = "2026-03-17T09:00:02Z"
    follow_up_payload["price_state"]["last_price"] = 24843.25
    follow_up_payload["price_state"]["best_bid"] = 24843.0
    follow_up_payload["price_state"]["best_ask"] = 24843.25
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(follow_up_payload).encode("utf-8"),
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["instrument_symbol"] == "NQ"
    assert payload["latest_price"] == 24843.25
    assert payload["best_bid"] == 24843.0
    assert payload["best_ask"] == 24843.25
    assert payload["latest_price_source"] == "continuous_state"
    assert payload["best_bid_source"] == "continuous_state"
    assert payload["best_ask_source"] == "continuous_state"
    assert payload["latest_observed_at"].startswith("2026-03-17T09:00:02")
    assert payload["source_message_count"] >= 2
    assert len(payload["candles"]) >= 1
    assert payload["trade_summary"]["volume"] >= 0
    assert isinstance(payload["significant_liquidity"], list)
    assert isinstance(payload["same_price_replenishment"], list)

def test_replay_live_tail_matches_legacy_generic_chart_instance_id_with_canonical_request() -> None:
    application = build_application()

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["instrument"]["root_symbol"] = "NQ"
    continuous_payload["instrument"]["contract_symbol"] = "NQH6"
    continuous_payload["instrument"]["venue"] = "CME"
    continuous_payload["instrument"]["currency"] = "USD"
    continuous_payload["display_timeframe"] = "1m"
    continuous_payload["source"]["chart_instance_id"] = "Chart"
    continuous_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T09:00:01Z"
    continuous_payload["emitted_at"] = "2026-03-17T09:00:01Z"
    continuous_payload["price_state"]["last_price"] = 24843.0
    continuous_payload["price_state"]["best_bid"] = 24842.75
    continuous_payload["price_state"]["best_ask"] = 24843.0

    application._repository.save_ingestion(
        ingestion_id=f"ing-{uuid4().hex}",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id=continuous_payload["message_id"],
        instrument_symbol="NQ",
        observed_payload=continuous_payload,
        stored_at=datetime(2026, 3, 17, 9, 0, 1, tzinfo=UTC),
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&chart_instance_id=chart-NQH6-1m-CME-USD&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["latest_price"] == 24843.0
    assert payload["source_message_count"] >= 1

def test_replay_live_tail_ignores_zero_activity_heartbeats_for_candles() -> None:
    application = build_application()

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["source"]["instrument_symbol"] = "NQ"
    continuous_payload["source"]["chart_instance_id"] = "NQ-live-heartbeat"
    continuous_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T09:00:01Z"
    continuous_payload["emitted_at"] = "2026-03-17T09:00:01Z"
    continuous_payload["price_state"]["last_price"] = 24843.0
    continuous_payload["trade_summary"]["trade_count"] = 0
    continuous_payload["trade_summary"]["volume"] = 0
    continuous_payload["trade_summary"]["aggressive_buy_volume"] = 0
    continuous_payload["trade_summary"]["aggressive_sell_volume"] = 0
    continuous_payload["trade_summary"]["net_delta"] = 0

    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    follow_up_payload = copy.deepcopy(continuous_payload)
    follow_up_payload["message_id"] = "adapter-msg-heartbeat-20260317-090002"
    follow_up_payload["observed_window_end"] = "2026-03-17T09:00:02Z"
    follow_up_payload["emitted_at"] = "2026-03-17T09:00:02Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(follow_up_payload).encode("utf-8"),
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["latest_price"] == 24843.0
    assert payload["source_message_count"] >= 2
    assert payload["candles"] == []

def test_replay_live_tail_falls_back_to_tick_quote_when_continuous_missing(monkeypatch) -> None:
    application = build_application()
    monkeypatch.setattr(
        application._repository,
        "get_latest_tick_quote",
        lambda **kwargs: {
            "observed_at": "2026-03-17T09:00:03Z",
            "last_price": 24843.5,
            "best_bid": 24843.25,
            "best_ask": 24843.5,
            "tick_count": 24,
        },
        raising=False,
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["instrument_symbol"] == "NQ"
    assert payload["latest_price"] == 24843.5
    assert payload["best_bid"] == 24843.25
    assert payload["best_ask"] == 24843.5
    assert payload["latest_price_source"] == "ticks_raw"
    assert payload["best_bid_source"] == "ticks_raw"
    assert payload["best_ask_source"] == "ticks_raw"
    assert payload["latest_observed_at"].startswith("2026-03-17T09:00:03")
    assert payload["source_message_count"] == 0
    assert payload["candles"] == []

def test_replay_live_tail_overlays_recent_continuous_updates_on_chart_candle_base() -> None:
    application = build_application()

    now = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    chart_start = now - timedelta(minutes=160)
    chart_bars = [
        ChartCandle(
            symbol="NQ",
            timeframe=Timeframe.MIN_1,
            started_at=chart_start + timedelta(minutes=index),
            ended_at=chart_start + timedelta(minutes=index + 1),
            source_started_at=chart_start + timedelta(minutes=index),
            open=24000.0 + index,
            high=24001.0 + index,
            low=23999.0 + index,
            close=24000.5 + index,
            volume=20,
            tick_volume=20,
            delta=2,
            updated_at=chart_start + timedelta(minutes=index + 1),
            source_timezone="UTC",
        )
        for index in range(151)
    ]
    application._repository.replace_chart_candles(chart_bars)

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["source"]["instrument_symbol"] = "NQ"
    continuous_payload["source"]["chart_instance_id"] = "NQ-live-tail-overlay"

    for index in range(9):
        observed_at = now - timedelta(minutes=9 - index) + timedelta(seconds=1)
        payload = copy.deepcopy(continuous_payload)
        payload["message_id"] = f"adapter-msg-overlay-{index}"
        payload["observed_window_start"] = (observed_at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = observed_at.isoformat().replace("+00:00", "Z")
        payload["emitted_at"] = observed_at.isoformat().replace("+00:00", "Z")
        payload["price_state"]["last_price"] = 26000.0 + index
        payload["price_state"]["best_bid"] = 25999.75 + index
        payload["price_state"]["best_ask"] = 26000.25 + index
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

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&chart_instance_id=NQ-live-tail-overlay&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["latest_price"] == 26008.0
    assert payload["latest_price_source"] == "continuous_state"
    assert len(payload["candles"]) == 4
    assert payload["candles"][-1]["started_at"] == (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    assert payload["candles"][-1]["close"] == 26008.0
    assert payload["candles"][0]["started_at"] == (now - timedelta(minutes=4)).isoformat().replace("+00:00", "Z")

def test_replay_live_tail_ignores_unrelated_backfill_ack_for_refresh_flags() -> None:
    application = build_application()

    now = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    chart_start = now - timedelta(minutes=12)
    application._repository.replace_chart_candles(
        [
            ChartCandle(
                symbol="NQ",
                timeframe=Timeframe.MIN_1,
                started_at=chart_start + timedelta(minutes=index),
                ended_at=chart_start + timedelta(minutes=index + 1),
                source_started_at=chart_start + timedelta(minutes=index),
                open=24500.0 + index,
                high=24501.0 + index,
                low=24499.0 + index,
                close=24500.5 + index,
                volume=12,
                tick_volume=12,
                delta=1,
                updated_at=chart_start + timedelta(minutes=index + 1),
                source_timezone="UTC",
            )
            for index in range(8)
        ]
    )

    from atas_market_structure.models import (
        AdapterBackfillAcknowledgeRequest,
        ReplayWorkbenchAtasBackfillRequest,
    )

    backfill_request = ReplayWorkbenchAtasBackfillRequest(
        cache_key="NQ|1m|older-window",
        instrument_symbol="NQ",
        contract_symbol="NQ",
        root_symbol="NQ",
        display_timeframe="1m",
        window_start=now - timedelta(days=1, hours=1),
        window_end=now - timedelta(days=1),
        chart_instance_id="NQ-live-tail-refresh",
        missing_segments=[],
        requested_ranges=[],
        reason="test_unrelated_backfill",
        request_history_bars=True,
        request_history_footprint=False,
    )
    accepted = application._replay_workbench_service.request_atas_backfill(backfill_request)
    application._replay_workbench_service.acknowledge_atas_backfill(
        AdapterBackfillAcknowledgeRequest(
            request_id=accepted.request.request_id,
            cache_key=accepted.request.cache_key,
            instrument_symbol="NQ",
            chart_instance_id="NQ-live-tail-refresh",
            acknowledged_at=now,
            acknowledged_history_bars=True,
            acknowledged_history_footprint=False,
        )
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&chart_instance_id=NQ-live-tail-refresh&lookback_bars=4",
    )

    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["latest_backfill_request"] is None
    assert payload["snapshot_refresh_required"] is False

def test_replay_workbench_builder_returns_placeholder_snapshot_when_local_history_is_missing() -> None:
    application = build_application()

    build_request = load_json_fixture("replay_workbench.build_request.sample.json")
    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["action"] == "built_from_local_history"
    assert payload["local_message_count"] == 0
    assert payload["core_snapshot"] is not None
    assert payload["summary"] is not None
    assert payload["summary"]["candle_count"] == 0
    assert payload["integrity"]["status"] == "missing_local_history"
    assert payload["atas_fetch_request"] is None
    assert payload["atas_backfill_request"]["status"] == "pending"
    assert payload["atas_backfill_request"]["requested_ranges"] == [
        {
            "range_start": "2026-03-12T07:00:00Z",
            "range_end": "2026-03-17T02:15:00Z",
        }
    ]

def test_replay_workbench_builder_rebuilds_from_local_history() -> None:
    application = build_application()
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    base_time = datetime.fromisoformat("2026-03-16T14:30:00+00:00")

    for index in range(12):
        payload = json.loads(json.dumps(continuous_payload))
        emitted_at = base_time + timedelta(minutes=index)
        payload["message_id"] = f"adapter-msg-local-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-03d4a876"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = 21520.0 + index
        payload["price_state"]["local_range_low"] = 21520.0
        payload["price_state"]["local_range_high"] = 21531.0
        payload["trade_summary"]["volume"] = 100 + index
        payload["trade_summary"]["net_delta"] = 20 + index
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    build_request = load_json_fixture("replay_workbench.build_request.sample.json")
    build_request["window_start"] = "2026-03-16T14:30:00Z"
    build_request["window_end"] = "2026-03-16T14:41:00Z"
    build_request["cache_key"] = "NQ|5m|2026-03-16T14:30:00Z|2026-03-16T14:41:00Z"
    build_request["min_continuous_messages"] = 5
    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["action"] == "built_from_local_history"
    assert payload["local_message_count"] == 12
    assert payload["summary"]["instrument_symbol"] == "NQ"
    assert payload["summary"]["verification_status"] == "unverified"
    assert payload["summary"]["candle_count"] >= 2
    assert payload["core_snapshot"]["raw_features"]["total_candle_count"] >= payload["summary"]["candle_count"]
    assert payload["core_snapshot"]["raw_features"]["initial_window_bar_limit"] == 576
    assert payload["core_snapshot"]["raw_features"]["deferred_history_available"] is False
    assert payload["cache_record"]["cache_key"] == "NQ|5m|2026-03-16T14:30:00Z|2026-03-16T14:41:00Z"

def test_replay_workbench_builder_fills_missing_candles_with_synthetic_bars() -> None:
    application = build_application()
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")

    # Intentionally skip one minute so the built candles have a gap.
    base_time = datetime.fromisoformat("2026-03-16T14:30:00+00:00")
    minutes = [0, 2, 3]
    for index, minute_offset in enumerate(minutes):
        payload = json.loads(json.dumps(continuous_payload))
        emitted_at = base_time + timedelta(minutes=minute_offset)
        payload["message_id"] = f"adapter-msg-gap-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-gap-test"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = 21520.0 + index
        payload["trade_summary"]["volume"] = 50
        payload["trade_summary"]["net_delta"] = 5
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    build_request = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T14:33:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T14:33:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 1,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert build_response.status_code == 200
    build_body = json.loads(build_response.body)
    assert build_body["action"] == "built_from_local_history"

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_payload = json.loads(replay_ingestion_response.body)["observed_payload"]
    candles = replay_payload["candles"]

    # Expect the missing 14:31 bar to be present as a synthetic flat candle.
    filler = next((c for c in candles if str(c["started_at"]).startswith("2026-03-16T14:31:00")), None)
    assert filler is not None
    assert filler["volume"] == 0
    assert filler["delta"] == 0

    raw = replay_payload.get("raw_features") or {}
    assert raw.get("candle_gap_count", 0) >= 1
    assert raw.get("candle_gap_missing_bar_count", 0) >= 1
    assert raw.get("candle_gap_fill_bar_count", 0) >= 1

def test_replay_workbench_builder_does_not_fill_large_session_breaks() -> None:
    application = build_application()
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")

    base_time = datetime.fromisoformat("2026-03-16T14:30:00+00:00")
    minutes = [0, 35, 36]
    for index, minute_offset in enumerate(minutes):
        payload = copy.deepcopy(continuous_payload)
        emitted_at = base_time + timedelta(minutes=minute_offset)
        payload["message_id"] = f"adapter-msg-large-gap-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-large-gap-test"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = 21540.0 + index
        payload["trade_summary"]["volume"] = 50
        payload["trade_summary"]["net_delta"] = 5
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    build_request = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:06:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:06:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 1,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert build_response.status_code == 200
    build_body = json.loads(build_response.body)
    assert build_body["action"] == "built_from_local_history"

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_payload = json.loads(replay_ingestion_response.body)["observed_payload"]
    candles = replay_payload["candles"]

    assert len(candles) == 3
    assert not any(str(candle["started_at"]).startswith("2026-03-16T14:31:00") for candle in candles)

    raw = replay_payload.get("raw_features") or {}
    assert raw.get("candle_gap_count", 0) >= 1
    assert raw.get("candle_gap_fill_bar_count", 0) == 0
