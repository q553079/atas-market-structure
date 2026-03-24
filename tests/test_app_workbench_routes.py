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

def test_adapter_history_bars_ingestion_and_replay_builder_prefers_atas_history() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")

    history_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )

    assert history_response.status_code == 201
    history_body = json.loads(history_response.body)
    assert history_body["message_type"] == "history_bars"
    assert history_body["summary"]["history_bar_count"] == 6
    assert history_body["summary"]["history_bar_timeframe"] == "1m"

    build_request = {
        "cache_key": "NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "5m",
        "window_start": "2026-03-17T08:55:00Z",
        "window_end": "2026-03-17T09:00:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert build_response.status_code == 200
    build_body = json.loads(build_response.body)
    assert build_body["action"] == "built_from_atas_history"
    assert build_body["summary"]["display_timeframe"] == "5m"
    assert build_body["summary"]["candle_count"] == 2
    assert build_body["core_snapshot"]["display_timeframe"] == "5m"
    assert len(build_body["core_snapshot"]["candles"]) == 2

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_ingestion_body = json.loads(replay_ingestion_response.body)
    assert replay_ingestion_body["observed_payload"]["acquisition_mode"] == "atas_fetch"
    assert replay_ingestion_body["observed_payload"]["raw_features"]["history_source"] == "adapter_history_bars"
    assert replay_ingestion_body["observed_payload"]["candles"][0]["open"] == 21498.0

def test_history_payload_matching_accepts_legacy_generic_chart_instance_id_for_canonical_request() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["instrument"]["root_symbol"] = "NQ"
    history_payload["instrument"]["contract_symbol"] = "NQH6"
    history_payload["instrument"]["venue"] = "CME"
    history_payload["instrument"]["currency"] = "USD"
    history_payload["display_timeframe"] = "1m"
    history_payload["bar_timeframe"] = "1m"
    history_payload["source"]["chart_instance_id"] = "Chart"
    history_payload["observed_window_start"] = "2026-03-17T08:55:00Z"
    history_payload["observed_window_end"] = "2026-03-17T09:00:59Z"
    history_payload["emitted_at"] = "2026-03-17T09:02:00Z"

    application._repository.save_ingestion(
        ingestion_id=f"ing-{uuid4().hex}",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id=history_payload["message_id"],
        instrument_symbol="NQ",
        observed_payload=history_payload,
        stored_at=datetime(2026, 3, 17, 9, 2, tzinfo=UTC),
    )

    matched_payloads = application._replay_workbench_service._collect_matching_history_payloads(
        ReplayWorkbenchBuildRequest(
            cache_key="NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z",
            instrument_symbol="NQ",
            display_timeframe="5m",
            window_start="2026-03-17T08:55:00Z",
            window_end="2026-03-17T09:00:59Z",
            chart_instance_id="chart-NQH6-1m-CME-USD",
            force_rebuild=True,
            min_continuous_messages=10,
        )
    )

    assert len(matched_payloads) == 1
    assert matched_payloads[0].source.chart_instance_id == "Chart"

def test_replay_builder_merges_history_payloads_across_chart_instances() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")

    first_payload = copy.deepcopy(history_payload)
    first_payload["message_id"] = "collector-history-merge-01"
    first_payload["emitted_at"] = "2026-03-17T09:06:00Z"
    first_payload["instrument"]["symbol"] = "NQ"
    first_payload["source"]["instrument_symbol"] = "NQ"
    first_payload["source"]["chart_instance_id"] = "NQ-chart-old"
    first_payload["bar_timeframe"] = "1m"
    first_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    first_payload["observed_window_end"] = "2026-03-17T09:05:59Z"
    for index, bar in enumerate(first_payload["bars"]):
        minute = index
        bar["started_at"] = f"2026-03-17T09:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-17T09:{minute:02d}:59Z"

    second_payload = copy.deepcopy(history_payload)
    second_payload["message_id"] = "collector-history-merge-02"
    second_payload["emitted_at"] = "2026-03-17T09:12:00Z"
    second_payload["instrument"]["symbol"] = "NQ"
    second_payload["source"]["instrument_symbol"] = "NQ"
    second_payload["source"]["chart_instance_id"] = "NQ-chart-new"
    second_payload["bar_timeframe"] = "1m"
    second_payload["observed_window_start"] = "2026-03-17T09:06:00Z"
    second_payload["observed_window_end"] = "2026-03-17T09:11:59Z"
    for index, bar in enumerate(second_payload["bars"]):
        minute = 6 + index
        bar["started_at"] = f"2026-03-17T09:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-17T09:{minute:02d}:59Z"

    first_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(first_payload).encode("utf-8"),
    )
    assert first_response.status_code == 201
    second_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(second_payload).encode("utf-8"),
    )
    assert second_response.status_code == 201

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T09:00:00Z|2026-03-17T09:11:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T09:00:00Z",
        "window_end": "2026-03-17T09:11:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert build_response.status_code == 200
    build_body = json.loads(build_response.body)
    assert build_body["action"] == "built_from_atas_history"
    assert len(build_body["core_snapshot"]["candles"]) == 12
    assert build_body["core_snapshot"]["candles"][0]["started_at"] == "2026-03-17T09:00:00Z"
    assert build_body["core_snapshot"]["candles"][-1]["started_at"] == "2026-03-17T09:11:00Z"
    assert build_body["core_snapshot"]["raw_features"]["history_payload_count"] == 2
    assert build_body["core_snapshot"]["raw_features"]["history_bar_count"] == 12
    assert build_body["core_snapshot"]["raw_features"]["history_coverage_start"] == "2026-03-17T09:00:00Z"
    assert build_body["core_snapshot"]["raw_features"]["history_coverage_end"] == "2026-03-17T09:11:59Z"

def test_replay_workbench_builder_overlays_latest_continuous_candles_on_history() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )
    assert history_response.status_code == 201

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    overlay_prices = [21505.5, 21507.25]
    base_time = datetime.fromisoformat("2026-03-17T09:01:00+00:00")
    for index, price in enumerate(overlay_prices):
        payload = json.loads(json.dumps(continuous_payload))
        emitted_at = base_time + timedelta(minutes=index)
        payload["message_id"] = f"adapter-msg-overlay-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-03d4a876"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = price
        payload["price_state"]["local_range_low"] = min(overlay_prices)
        payload["price_state"]["local_range_high"] = max(overlay_prices)
        continuous_response = application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )
        assert continuous_response.status_code == 201

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T08:55:00Z|2026-03-17T09:02:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T08:55:00Z",
        "window_end": "2026-03-17T09:02:59Z",
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
    assert build_body["action"] == "built_from_atas_history"

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_ingestion_body = json.loads(replay_ingestion_response.body)
    observed_payload = replay_ingestion_body["observed_payload"]
    candles = observed_payload["candles"]
    assert candles[-1]["started_at"] == "2026-03-17T09:02:00Z"
    assert candles[-1]["ended_at"] == "2026-03-17T09:02:59Z"
    assert candles[-1]["close"] == 21507.25
    assert observed_payload["window_end"] == "2026-03-17T09:02:59Z"
    assert observed_payload["raw_features"]["continuous_overlay_candle_count"] >= 2

def test_replay_builder_cache_hit_skips_history_refresh_scan() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )

    build_request = {
        "cache_key": "NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "5m",
        "window_start": "2026-03-17T08:55:00Z",
        "window_end": "2026-03-17T09:00:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    first_build = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert first_build.status_code == 200
    first_payload = json.loads(first_build.body)

    service = application._replay_workbench_service

    def fail_collect(*args, **kwargs):
        raise AssertionError("cache hit should not rescan history payloads")

    service._collect_matching_history_payloads = fail_collect
    build_request["force_rebuild"] = False
    cached_build = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert cached_build.status_code == 200
    cached_payload = json.loads(cached_build.body)
    assert cached_payload["action"] == "cache_hit"
    assert cached_payload["ingestion_id"] == first_payload["ingestion_id"]

def test_replay_builder_ignores_zero_activity_heartbeat_overlay() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    heartbeat_price = 21625.0
    for index in range(2):
        payload = copy.deepcopy(continuous_payload)
        emitted_at = datetime.fromisoformat("2026-03-17T09:10:00+00:00") + timedelta(minutes=index)
        payload["message_id"] = f"adapter-msg-heartbeat-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-heartbeat-main"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = heartbeat_price
        payload["trade_summary"]["trade_count"] = 0
        payload["trade_summary"]["volume"] = 0
        payload["trade_summary"]["aggressive_buy_volume"] = 0
        payload["trade_summary"]["aggressive_sell_volume"] = 0
        payload["trade_summary"]["net_delta"] = 0
        response = application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )
        assert response.status_code == 201

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T08:55:00Z|2026-03-17T09:11:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T08:55:00Z",
        "window_end": "2026-03-17T09:11:59Z",
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
    assert build_body["action"] == "built_from_atas_history"
    assert build_body["core_snapshot"]["window_end"] == "2026-03-17T09:00:59Z"
    assert build_body["core_snapshot"]["candles"][-1]["started_at"] == "2026-03-17T09:00:00Z"
    assert build_body["core_snapshot"]["raw_features"]["continuous_overlay_candle_count"] == 0
    assert build_body["core_snapshot"]["raw_features"]["candle_gap_fill_bar_count"] == 0

def test_replay_builder_preserves_full_core_snapshot_window_for_large_local_history() -> None:
    application = build_application()
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    base_time = datetime.fromisoformat("2026-03-17T00:00:00+00:00")

    for index in range(650):
        payload = copy.deepcopy(continuous_payload)
        emitted_at = base_time + timedelta(minutes=index)
        price = 21000 + index * 0.25
        payload["message_id"] = f"adapter-msg-trim-{index:04d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-trim-main"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = price
        payload["price_state"]["local_range_low"] = price - 2
        payload["price_state"]["local_range_high"] = price + 2
        response = application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )
        assert response.status_code == 201

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T00:00:00Z|2026-03-17T10:49:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T00:00:00Z",
        "window_end": "2026-03-17T10:49:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 1,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert build_response.status_code == 200
    payload = json.loads(build_response.body)
    assert payload["action"] == "built_from_local_history"
    assert payload["core_snapshot"] is not None
    assert len(payload["core_snapshot"]["candles"]) >= 650
    assert payload["core_snapshot"]["raw_features"]["initial_window_applied"] is False
    assert payload["core_snapshot"]["raw_features"]["initial_window_bar_limit"] == 180
    assert payload["core_snapshot"]["raw_features"]["total_candle_count"] >= 650
    assert payload["core_snapshot"]["raw_features"]["deferred_history_available"] is False


    application = build_application()
    history_bars_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_footprint_payload = load_json_fixture("atas_adapter.history_footprint.sample.json")

    history_bars_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_bars_payload).encode("utf-8"),
    )
    assert history_bars_response.status_code == 201

    history_footprint_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-footprint",
        json.dumps(history_footprint_payload).encode("utf-8"),
    )

    assert history_footprint_response.status_code == 201
    history_footprint_body = json.loads(history_footprint_response.body)
    assert history_footprint_body["message_type"] == "history_footprint"
    assert history_footprint_body["summary"]["history_footprint_bar_count"] == 2
    assert history_footprint_body["summary"]["history_footprint_timeframe"] == "1m"
    assert history_footprint_body["summary"]["history_footprint_chunk_index"] == 0
    assert history_footprint_body["summary"]["history_footprint_chunk_count"] == 1

    build_request = {
        "cache_key": "NQ|1m|2026-03-17T08:59:00Z|2026-03-17T09:00:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T08:59:00Z",
        "window_end": "2026-03-17T09:00:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert build_response.status_code == 200
    build_body = json.loads(build_response.body)
    assert build_body["action"] == "built_from_atas_history"

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_ingestion_body = json.loads(replay_ingestion_response.body)
    raw_features = replay_ingestion_body["observed_payload"]["raw_features"]
    assert raw_features["history_footprint_available"] is True
    assert raw_features["history_footprint_digest"]["bar_count"] == 2
    assert raw_features["history_footprint_digest"]["price_level_count"] == 10
    assert len(raw_features["history_footprint_digest"]["repeated_price_levels"]) >= 1

def test_replay_workbench_snapshot_is_stored() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["replay_snapshot_id"] == "replay-20260317-nq-europe-01"
    assert payload["summary"]["instrument_symbol"] == "NQ"
    assert payload["summary"]["display_timeframe"] == "5m"
    assert payload["summary"]["acquisition_mode"] == "cache_reuse"
    assert payload["summary"]["verification_status"] == "durable"
    assert payload["summary"]["verification_count"] == 3
    assert payload["summary"]["locked_until_manual_reset"] is True
    assert payload["summary"]["fetch_only_when_missing"] is True
    assert payload["summary"]["max_verifications_per_day"] == 1
    assert payload["summary"]["verification_passes_to_lock"] == 3
    assert payload["summary"]["candle_count"] == 2
    assert payload["summary"]["event_annotation_count"] == 2
    assert payload["summary"]["focus_region_count"] == 1
    assert payload["summary"]["strategy_candidate_count"] == 1
    assert payload["summary"]["has_ai_briefing"] is True

    ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert ingestion_response.status_code == 200
    ingestion_payload = json.loads(ingestion_response.body)
    assert ingestion_payload["ingestion_kind"] == "replay_workbench_snapshot"
    assert ingestion_payload["observed_payload"]["replay_snapshot_id"] == "replay-20260317-nq-europe-01"
    assert ingestion_payload["observed_payload"]["cache_key"] == "NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z"
    assert ingestion_payload["observed_payload"]["acquisition_mode"] == "cache_reuse"
    assert ingestion_payload["observed_payload"]["verification_state"]["status"] == "durable"
    assert ingestion_payload["observed_payload"]["verification_state"]["verification_count"] == 3
    assert ingestion_payload["observed_payload"]["strategy_candidates"][0]["strategy_id"] == "pattern-nq-replenished-bid-launchpad"

def test_replay_workbench_cache_lookup_and_invalidation() -> None:
    application = build_application()
    application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )

    lookup_response = application.dispatch(
        "GET",
        "/api/v1/workbench/replay-cache?cache_key=NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z",
    )
    assert lookup_response.status_code == 200
    lookup_payload = json.loads(lookup_response.body)
    assert lookup_payload["cache_key"] == "NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z"
    assert lookup_payload["record"]["verification_state"]["status"] == "durable"
    assert lookup_payload["auto_fetch_allowed"] is False
    assert lookup_payload["verification_due_now"] is False

    invalidation_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-cache/invalidate",
        json.dumps(
            {
                "cache_key": "NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z",
                "invalidation_reason": "operator found mismatched historical footprint window",
            }
        ).encode("utf-8"),
    )
    assert invalidation_response.status_code == 200
    invalidation_payload = json.loads(invalidation_response.body)
    assert invalidation_payload["cache_key"] == "NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z"
    assert invalidation_payload["verification_status"] == "invalidated"
    assert invalidation_payload["locked_until_manual_reset"] is False
    lookup_after_response = application.dispatch(
        "GET",
        "/api/v1/workbench/replay-cache?cache_key=NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z",
    )
    assert lookup_after_response.status_code == 200
    lookup_after_payload = json.loads(lookup_after_response.body)
    assert lookup_after_payload["record"]["verification_state"]["status"] == "invalidated"
    assert lookup_after_payload["record"]["verification_state"]["invalidation_reason"] == "operator found mismatched historical footprint window"

def test_replay_cache_rebuild_latest_invalidates_old_cache_and_uses_latest_history() -> None:
    application = build_application()
    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")

    first_history_payload = json.loads(json.dumps(history_payload))
    first_history_payload["message_id"] = "collector-history-rebuild-01"
    first_history_payload["emitted_at"] = "2026-03-17T09:01:00Z"
    first_history_payload["source"]["chart_instance_id"] = "NQ-03d4a876"
    first_history_payload["bars"][0]["open"] = 21498.0
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(first_history_payload).encode("utf-8"),
    )

    build_request = {
        "cache_key": "NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "5m",
        "window_start": "2026-03-17T08:55:00Z",
        "window_end": "2026-03-17T09:00:59Z",
        "force_rebuild": True,
        "min_continuous_messages": 10,
    }
    first_build_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert first_build_response.status_code == 200
    first_build_payload = json.loads(first_build_response.body)

    second_history_payload = json.loads(json.dumps(history_payload))
    second_history_payload["message_id"] = "collector-history-rebuild-02"
    second_history_payload["emitted_at"] = "2026-03-17T09:05:00Z"
    second_history_payload["source"]["chart_instance_id"] = "NQ-03d4a876"
    second_history_payload["bars"][0]["open"] = 21470.0
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(second_history_payload).encode("utf-8"),
    )

    rebuild_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-cache/rebuild-latest",
        json.dumps(
            {
                "cache_key": "NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z",
                "instrument_symbol": "NQ",
                "display_timeframe": "5m",
                "window_start": "2026-03-17T08:55:00Z",
                "window_end": "2026-03-17T09:00:59Z",
                "invalidation_reason": "atas bug fixed; rebuild from latest sync",
            }
        ).encode("utf-8"),
    )

    assert rebuild_response.status_code == 200
    rebuild_payload = json.loads(rebuild_response.body)
    assert rebuild_payload["cache_key"] == "NQ|5m|2026-03-17T08:55:00Z|2026-03-17T09:00:59Z"
    assert rebuild_payload["invalidated_existing_cache"] is True
    assert rebuild_payload["invalidation_result"]["verification_status"] == "invalidated"
    assert rebuild_payload["build_result"]["action"] == "built_from_atas_history"
    assert rebuild_payload["build_result"]["ingestion_id"] != first_build_payload["ingestion_id"]

    old_replay_ingestion_response = application.dispatch(
        "GET",
        f"/api/v1/ingestions/{first_build_payload['ingestion_id']}",
    )
    assert old_replay_ingestion_response.status_code == 200
    old_replay_ingestion_payload = json.loads(old_replay_ingestion_response.body)
    assert old_replay_ingestion_payload["observed_payload"]["verification_state"]["status"] == "invalidated"
    assert (
        old_replay_ingestion_payload["observed_payload"]["verification_state"]["invalidation_reason"]
        == "atas bug fixed; rebuild from latest sync"
    )

    rebuilt_replay_ingestion_response = application.dispatch(
        "GET",
        f"/api/v1/ingestions/{rebuild_payload['build_result']['ingestion_id']}",
    )
    assert rebuilt_replay_ingestion_response.status_code == 200
    rebuilt_replay_ingestion_payload = json.loads(rebuilt_replay_ingestion_response.body)
    assert rebuilt_replay_ingestion_payload["observed_payload"]["candles"][0]["open"] == 21470.0
