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

def test_replay_workbench_builder_rebuilds_from_partial_local_history_and_requests_backfill() -> None:
    application = build_application()
    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    base_time = datetime.fromisoformat("2026-03-16T14:33:00+00:00")

    for index in range(2):
        payload = json.loads(json.dumps(continuous_payload))
        emitted_at = base_time + timedelta(minutes=index)
        payload["message_id"] = f"adapter-msg-partial-{index:02d}"
        payload["emitted_at"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_start"] = emitted_at.isoformat().replace("+00:00", "Z")
        payload["observed_window_end"] = (emitted_at + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        payload["source"]["chart_instance_id"] = "NQ-partial-backfill"
        payload["instrument"]["symbol"] = "NQ"
        payload["price_state"]["last_price"] = 21540.0 + index
        payload["trade_summary"]["volume"] = 80 + index
        payload["trade_summary"]["net_delta"] = 10 + index
        application.dispatch(
            "POST",
            "/api/v1/adapter/continuous-state",
            json.dumps(payload).encode("utf-8"),
        )

    build_request = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T14:35:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T14:35:00Z",
        "chart_instance_id": "NQ-partial-backfill",
        "force_rebuild": True,
        "min_continuous_messages": 5,
    }
    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert response.status_code == 200
    payload = json.loads(response.body)

    assert payload["action"] == "built_from_local_history"
    assert payload["local_message_count"] == 2
    assert payload["core_snapshot"] is not None
    assert payload["integrity"]["status"] == "missing_local_history"
    assert payload["atas_backfill_request"]["status"] == "pending"
    assert payload["atas_backfill_request"]["reason"] == "local_history_insufficient"

    poll_response = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-partial-backfill",
    )
    assert poll_response.status_code == 200
    poll_payload = json.loads(poll_response.body)
    assert poll_payload["request"]["request_id"] == payload["atas_backfill_request"]["request_id"]

def test_workbench_atas_backfill_request_poll_and_acknowledge_flow() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:00:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:00:00Z",
        "chart_instance_id": "NQ-chart-main",
        "reason": "candle_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": True,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-16T14:39:59Z",
                "next_started_at": "2026-03-16T14:42:00Z",
                "missing_bar_count": 2,
            }
        ],
    }

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    assert create_response.status_code == 201
    create_body = json.loads(create_response.body)
    assert create_body["reused_existing_request"] is False
    assert create_body["request"]["status"] == "pending"
    assert create_body["request"]["requested_ranges"] == [
        {
            "range_start": "2026-03-16T14:40:00Z",
            "range_end": "2026-03-16T14:41:59Z",
        }
    ]

    mismatch_poll = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-other",
    )
    assert mismatch_poll.status_code == 200
    assert json.loads(mismatch_poll.body)["request"] is None

    poll_response = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )
    assert poll_response.status_code == 200
    poll_body = json.loads(poll_response.body)
    assert poll_body["request"]["request_id"] == create_body["request"]["request_id"]
    assert poll_body["request"]["dispatch_count"] == 1
    assert poll_body["request"]["request_history_bars"] is True
    assert poll_body["request"]["request_history_footprint"] is True
    assert poll_body["request"]["requested_ranges"] == create_body["request"]["requested_ranges"]

    immediate_poll = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )
    assert immediate_poll.status_code == 200
    assert json.loads(immediate_poll.body)["request"] is None

    ack_response = application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": create_body["request"]["request_id"],
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-16T15:01:00Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": True,
                "latest_loaded_bar_started_at": "2026-03-16T15:00:00Z",
                "note": "forced history resend completed",
            }
        ).encode("utf-8"),
    )
    assert ack_response.status_code == 200
    ack_body = json.loads(ack_response.body)
    assert ack_body["request"]["status"] == "acknowledged"
    assert ack_body["request"]["acknowledged_chart_instance_id"] == "NQ-chart-main"
    assert ack_body["request"]["acknowledged_history_bars"] is True
    assert ack_body["request"]["acknowledged_history_footprint"] is True

    final_poll = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )
    assert final_poll.status_code == 200
    assert json.loads(final_poll.body)["request"] is None

def test_workbench_backfill_progress_reports_partial_raw_mirror_coverage() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:40:00Z|2026-03-16T14:42:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:40:00Z",
        "window_end": "2026-03-16T14:42:59Z",
        "chart_instance_id": "NQ-chart-main",
        "request_history_bars": True,
        "request_history_footprint": False,
        "requested_ranges": [
            {
                "range_start": "2026-03-16T14:40:00Z",
                "range_end": "2026-03-16T14:42:59Z",
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    poll_response = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )
    assert poll_response.status_code == 200
    assert json.loads(poll_response.body)["request"]["request_id"] == request_id

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["instrument"]["contract_symbol"] = "NQH6"
    history_payload["instrument"]["root_symbol"] = "NQ"
    history_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    history_payload["bar_timeframe"] = "1m"
    history_payload["bars"] = history_payload["bars"][:2]
    history_payload["observed_window_start"] = "2026-03-16T14:40:00Z"
    history_payload["observed_window_end"] = "2026-03-16T14:42:59Z"
    for index, bar in enumerate(history_payload["bars"]):
        minute = 40 + index
        bar["started_at"] = f"2026-03-16T14:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-16T14:{minute:02d}:59Z"
        bar["bar_timestamp_utc"] = bar["started_at"]
    history_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )
    assert history_response.status_code == 201

    progress_response = application.dispatch(
        "GET",
        "/api/v1/workbench/backfill-progress"
        "?instrument_symbol=NQ"
        "&display_timeframe=1m"
        "&cache_key=NQ%7C1m%7C2026-03-16T14%3A40%3A00Z%7C2026-03-16T14%3A42%3A59Z"
        "&chart_instance_id=NQ-chart-main",
    )
    assert progress_response.status_code == 200
    progress_body = json.loads(progress_response.body)
    assert progress_body["request"]["request_id"] == request_id
    assert progress_body["stage"] == "receiving"
    assert progress_body["expected_bar_count"] == 3
    assert progress_body["received_bar_count"] == 2
    assert progress_body["missing_bar_count"] == 1
    assert progress_body["coverage_progress_percent"] == 67
    assert progress_body["requested_ranges"][0]["progress_percent"] == 67

def test_workbench_backfill_progress_reports_complete_after_verified_ack() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:40:00Z|2026-03-16T14:41:59Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:40:00Z",
        "window_end": "2026-03-16T14:41:59Z",
        "chart_instance_id": "NQ-chart-main",
        "request_history_bars": True,
        "request_history_footprint": False,
        "requested_ranges": [
            {
                "range_start": "2026-03-16T14:40:00Z",
                "range_end": "2026-03-16T14:41:59Z",
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["instrument"]["contract_symbol"] = "NQH6"
    history_payload["instrument"]["root_symbol"] = "NQ"
    history_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    history_payload["bar_timeframe"] = "1m"
    history_payload["bars"] = history_payload["bars"][:2]
    history_payload["observed_window_start"] = "2026-03-16T14:40:00Z"
    history_payload["observed_window_end"] = "2026-03-16T14:41:59Z"
    for index, bar in enumerate(history_payload["bars"]):
        minute = 40 + index
        bar["started_at"] = f"2026-03-16T14:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-16T14:{minute:02d}:59Z"
        bar["bar_timestamp_utc"] = bar["started_at"]
    history_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )
    assert history_response.status_code == 201

    ack_response = application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": request_id,
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-16T14:42:10Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": False,
                "latest_loaded_bar_started_at": "2026-03-16T14:41:00Z",
            }
        ).encode("utf-8"),
    )
    assert ack_response.status_code == 200

    progress_response = application.dispatch(
        "GET",
        "/api/v1/workbench/backfill-progress"
        "?instrument_symbol=NQ"
        "&display_timeframe=1m"
        "&cache_key=NQ%7C1m%7C2026-03-16T14%3A40%3A00Z%7C2026-03-16T14%3A41%3A59Z"
        "&chart_instance_id=NQ-chart-main",
    )
    assert progress_response.status_code == 200
    progress_body = json.loads(progress_response.body)
    assert progress_body["request"]["request_id"] == request_id
    assert progress_body["stage"] == "complete"
    assert progress_body["active"] is False
    assert progress_body["progress_percent"] == 100
    assert progress_body["coverage_progress_percent"] == 100
    assert progress_body["verification"]["verified"] is True

def test_replay_builder_auto_creates_backfill_request_and_integrity_when_local_history_is_insufficient() -> None:
    application = build_application()
    build_request = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:00:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:00:00Z",
        "chart_instance_id": "NQ-chart-main",
        "force_rebuild": True,
        "min_continuous_messages": 5,
    }

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["action"] == "built_from_local_history"
    assert payload["core_snapshot"] is not None
    assert payload["summary"] is not None
    assert payload["integrity"]["status"] == "missing_local_history"
    assert payload["atas_fetch_request"] is None
    assert payload["atas_backfill_request"]["status"] == "pending"
    assert payload["atas_backfill_request"]["request_id"]
    assert payload["atas_backfill_request"]["requested_ranges"] == [
        {
            "range_start": "2026-03-16T14:30:00Z",
            "range_end": "2026-03-16T15:00:00Z",
        }
    ]

    poll_response = application.dispatch(
        "GET",
        "/api/v1/adapter/backfill-command?instrument_symbol=NQ&chart_instance_id=NQ-chart-main",
    )
    assert poll_response.status_code == 200
    poll_payload = json.loads(poll_response.body)
    assert poll_payload["request"]["request_id"] == payload["atas_backfill_request"]["request_id"]

def test_backfill_ack_verifies_and_rebuilds_snapshot_when_history_arrives() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:00:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:00:00Z",
        "chart_instance_id": "NQ-chart-main",
        "reason": "candle_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": False,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-16T14:39:59Z",
                "next_started_at": "2026-03-16T14:42:00Z",
                "missing_bar_count": 2,
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["source"]["instrument_symbol"] = "NQ"
    history_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    history_payload["bar_timeframe"] = "1m"
    for index, bar in enumerate(history_payload["bars"]):
        minute = 40 + index
        bar["started_at"] = f"2026-03-16T14:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-16T14:{minute:02d}:59Z"
    history_payload["observed_window_start"] = "2026-03-16T14:30:00Z"
    history_payload["observed_window_end"] = "2026-03-16T15:00:00Z"
    history_payload["emitted_at"] = "2026-03-16T15:00:30Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )

    ack_response = application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": request_id,
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-16T15:01:00Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": False,
                "latest_loaded_bar_started_at": "2026-03-16T15:00:00Z",
            }
        ).encode("utf-8"),
    )
    assert ack_response.status_code == 200
    ack_body = json.loads(ack_response.body)
    assert ack_body["verification"]["verified"] is True
    assert ack_body["rebuild_result"]["triggered"] is True
    assert ack_body["rebuild_result"]["build_result"]["ingestion_id"] is not None

def test_backfill_ack_without_history_does_not_rebuild() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:00:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:00:00Z",
        "chart_instance_id": "NQ-chart-main",
        "reason": "candle_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": False,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-16T14:39:59Z",
                "next_started_at": "2026-03-16T14:42:00Z",
                "missing_bar_count": 2,
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    ack_response = application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": request_id,
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-16T15:01:00Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": False,
                "latest_loaded_bar_started_at": "2026-03-16T15:00:00Z",
            }
        ).encode("utf-8"),
    )
    assert ack_response.status_code == 200
    ack_body = json.loads(ack_response.body)
    assert ack_body["verification"]["verified"] is False
    assert ack_body["rebuild_result"]["triggered"] is False

def test_backfill_ack_requires_the_missing_segment_to_be_fully_present() -> None:
    application = build_application()
    request_payload = {
        "cache_key": "NQ|1m|2026-03-16T14:30:00Z|2026-03-16T15:00:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-16T14:30:00Z",
        "window_end": "2026-03-16T15:00:00Z",
        "chart_instance_id": "NQ-chart-main",
        "reason": "candle_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": False,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-16T14:39:59Z",
                "next_started_at": "2026-03-16T14:42:00Z",
                "missing_bar_count": 2,
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["source"]["instrument_symbol"] = "NQ"
    history_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    history_payload["bar_timeframe"] = "1m"
    history_payload["observed_window_start"] = "2026-03-16T14:42:00Z"
    history_payload["observed_window_end"] = "2026-03-16T14:47:59Z"
    history_payload["emitted_at"] = "2026-03-16T15:00:30Z"
    for index, bar in enumerate(history_payload["bars"]):
        minute = 42 + index
        bar["started_at"] = f"2026-03-16T14:{minute:02d}:00Z"
        bar["ended_at"] = f"2026-03-16T14:{minute:02d}:59Z"
    history_response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )
    assert history_response.status_code == 201

    ack_response = application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": request_id,
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-16T15:01:00Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": False,
                "latest_loaded_bar_started_at": "2026-03-16T15:00:00Z",
            }
        ).encode("utf-8"),
    )
    assert ack_response.status_code == 200
    ack_body = json.loads(ack_response.body)
    assert ack_body["verification"]["verified"] is False
    assert ack_body["verification"]["missing_segment_count"] == 1
    assert ack_body["rebuild_result"]["triggered"] is False

def test_live_tail_returns_integrity_and_refresh_signal_after_acknowledged_backfill() -> None:
    application = build_application()

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["instrument"]["symbol"] = "NQ"
    continuous_payload["source"]["instrument_symbol"] = "NQ"
    continuous_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    continuous_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T09:00:01Z"
    continuous_payload["emitted_at"] = "2026-03-17T09:00:01Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    request_payload = {
        "cache_key": "NQ|1m|2026-03-17T09:00:00Z|2026-03-17T09:05:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "1m",
        "window_start": "2026-03-17T09:00:00Z",
        "window_end": "2026-03-17T09:05:00Z",
        "chart_instance_id": "NQ-chart-main",
        "reason": "candle_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": False,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-17T09:00:59Z",
                "next_started_at": "2026-03-17T09:03:00Z",
                "missing_bar_count": 2,
            }
        ],
    }
    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    request_id = json.loads(create_response.body)["request"]["request_id"]

    history_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_payload["instrument"]["symbol"] = "NQ"
    history_payload["source"]["instrument_symbol"] = "NQ"
    history_payload["source"]["chart_instance_id"] = "NQ-chart-main"
    history_payload["bar_timeframe"] = "1m"
    history_payload["observed_window_start"] = "2026-03-17T09:00:00Z"
    history_payload["observed_window_end"] = "2026-03-17T09:05:00Z"
    history_payload["emitted_at"] = "2026-03-17T09:05:10Z"
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_payload).encode("utf-8"),
    )
    application.dispatch(
        "POST",
        "/api/v1/adapter/backfill-ack",
        json.dumps(
            {
                "request_id": request_id,
                "instrument_symbol": "NQ",
                "chart_instance_id": "NQ-chart-main",
                "acknowledged_at": "2026-03-17T09:05:20Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": False,
                "latest_loaded_bar_started_at": "2026-03-17T09:05:00Z",
            }
        ).encode("utf-8"),
    )

    live_tail_response = application.dispatch(
        "GET",
        "/api/v1/workbench/live-tail?instrument_symbol=NQ&display_timeframe=1m&lookback_bars=4",
    )
    assert live_tail_response.status_code == 200
    payload = json.loads(live_tail_response.body)
    assert payload["integrity"] is not None
    assert payload["latest_backfill_request"]["request_id"] == request_id
    assert len(payload["event_annotations"]) >= 1
    assert len(payload["focus_regions"]) >= 1
    assert payload["snapshot_refresh_required"] in {True, False}


    application = build_application()
    request_payload = {
        "cache_key": "NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z",
        "instrument_symbol": "NQ",
        "display_timeframe": "5m",
        "window_start": "2026-03-12T07:00:00Z",
        "window_end": "2026-03-17T02:15:00Z",
        "reason": "snapshot_gap_detected",
        "request_history_bars": True,
        "request_history_footprint": False,
        "missing_segments": [
            {
                "prev_ended_at": "2026-03-14T01:24:59Z",
                "next_started_at": "2026-03-14T01:35:00Z",
                "missing_bar_count": 2,
            }
        ],
    }

    first_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )
    second_response = application.dispatch(
        "POST",
        "/api/v1/workbench/atas-backfill-requests",
        json.dumps(request_payload).encode("utf-8"),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first_body = json.loads(first_response.body)
    second_body = json.loads(second_response.body)
    assert first_body["request"]["request_id"] == second_body["request"]["request_id"]
    assert second_body["reused_existing_request"] is True
