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

def test_market_structure_ingestion_returns_derived_analysis() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        load_fixture("market_structure.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["route_key"] == "trend_continuation_review_long"
    assert payload["analysis"]["knowledge_route"]["route_key"] == "trend_continuation_review_long"

    analysis_response = application.dispatch("GET", f"/api/v1/analyses/{payload['analysis_id']}")
    assert analysis_response.status_code == 200
    analysis_payload = json.loads(analysis_response.body)
    assert analysis_payload["analysis"]["analysis_id"] == payload["analysis_id"]

    ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert ingestion_response.status_code == 200
    ingestion_payload = json.loads(ingestion_response.body)
    assert ingestion_payload["observed_payload"]["snapshot_id"] == "ms-20260315-093000"

def test_event_snapshot_ingestion_supports_execution_reversal_route() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/event-snapshot",
        load_fixture("event_snapshot.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["analysis"]["knowledge_route"]["route_key"] == "execution_reversal_review"

def test_process_context_supports_cross_session_release_route() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        load_fixture("market_structure.process.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["analysis"]["knowledge_route"]["route_key"] == "session_release_review_long"
    assert payload["analysis"]["process_context"]
    subject_kinds = {item["subject_kind"] for item in payload["analysis"]["process_context"]}
    assert "cross_session_sequence" in subject_kinds
    assert "liquidity_episode" in subject_kinds
    assert "initiative_drive" in subject_kinds
    assert "measured_move" in subject_kinds
    assert "manipulation_leg" in subject_kinds
    assert "gap_reference" in subject_kinds
    assert "post_harvest_response" in subject_kinds
    assert "exertion_zone" in subject_kinds
    analyst_flags = set(payload["analysis"]["analyst_flags"])
    assert "initiative_drive_present" in analyst_flags
    assert "measured_move_present" in analyst_flags
    assert "manipulation_leg_present" in analyst_flags
    assert "gap_reference_present" in analyst_flags
    assert "post_harvest_response_present" in analyst_flags
    assert "probable_gap_fill_present" in analyst_flags
    assert "historical_exertion_zone_present" in analyst_flags
    assert "trapped_inventory_watch" in analyst_flags
    assert "strong_key_level_present" in analyst_flags
    key_levels = payload["analysis"]["key_levels"]
    assert len(key_levels) == 2
    states = {item["state"] for item in key_levels}
    roles = {item["role"] for item in key_levels}
    assert "defended" in states
    assert "broken" in states
    assert "support" in roles or "resistance" in roles
    assert any(item["strength_score"] >= 0.75 for item in key_levels)
    gap_assessments = payload["analysis"]["gap_assessments"]
    assert len(gap_assessments) == 1
    assert gap_assessments[0]["fill_likelihood"] == "probable"
    assert gap_assessments[0]["fill_state"] == "partial_fill"
    assert gap_assessments[0]["remaining_fill_ticks"] == 4

def test_depth_snapshot_updates_significant_liquidity_memory() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/depth-snapshot",
        load_fixture("depth_snapshot.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["coverage_state"] == "depth_live"
    assert len(payload["updated_memories"]) == 2

    classifications = {item["derived_interpretation"]["classification"] for item in payload["updated_memories"]}
    assert "spoof_candidate" in classifications
    assert "absorption_candidate" in classifications

def test_liquidity_memory_endpoint_lists_active_records() -> None:
    application = build_application()
    application.dispatch(
        "POST",
        "/api/v1/ingestions/depth-snapshot",
        load_fixture("depth_snapshot.sample.json"),
    )

    response = application.dispatch("GET", "/api/v1/liquidity-memory?symbol=ESM6")
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert len(payload["memories"]) == 2
    assert all(item["instrument_symbol"] == "ESM6" for item in payload["memories"])

def test_adapter_continuous_state_ingestion_is_stored() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        load_fixture("atas_adapter.continuous_state.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["message_type"] == "continuous_state"
    assert payload["summary"]["significant_liquidity_count"] == 2
    assert payload["summary"]["has_gap_reference"] is True
    assert payload["summary"]["has_active_initiative_drive"] is True
    assert payload["summary"]["has_active_manipulation_leg"] is True
    assert payload["summary"]["has_active_measured_move"] is True
    assert payload["summary"]["has_active_post_harvest_response"] is True
    assert payload["bridge_errors"] == []
    assert len(payload["durable_outputs"]) == 1
    durable_output = payload["durable_outputs"][0]
    assert durable_output["ingestion_kind"] == "market_structure"
    assert durable_output["route_key"] == "session_release_review_long"

    ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert ingestion_response.status_code == 200
    ingestion_payload = json.loads(ingestion_response.body)
    assert ingestion_payload["ingestion_kind"] == "adapter_continuous_state"
    assert ingestion_payload["observed_payload"]["message_id"] == "adapter-msg-20260316-143001"
    assert ingestion_payload["observed_payload"]["source"]["chart_instance_id"] == "NQ-7fa31b2c"

    bridged_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{durable_output['ingestion_id']}")
    assert bridged_ingestion_response.status_code == 200
    bridged_ingestion_payload = json.loads(bridged_ingestion_response.body)
    assert bridged_ingestion_payload["ingestion_kind"] == "market_structure"
    assert bridged_ingestion_payload["observed_payload"]["snapshot_id"] == "bridge-ms-adapter-msg-20260316-143001"
    assert bridged_ingestion_payload["observed_payload"]["source"]["chart_instance_id"] == "NQ-7fa31b2c"

    bridged_analysis_response = application.dispatch("GET", f"/api/v1/analyses/{durable_output['analysis_id']}")
    assert bridged_analysis_response.status_code == 200

def test_adapter_history_bars_accepts_numeric_timeframe_alias_from_atas() -> None:
    application = build_application()
    payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    payload["message_id"] = "history-bars-alias-1"
    payload["display_timeframe"] = "1"
    payload["bar_timeframe"] = "1"
    payload["source"]["chart_instance_id"] = "chart-GC-1-CME-USD"
    payload["instrument"]["symbol"] = "GC"
    payload["instrument"]["root_symbol"] = "GC"
    payload["instrument"]["contract_symbol"] = "GC"

    response = application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(payload).encode("utf-8"),
    )

    assert response.status_code == 201
    body = json.loads(response.body)
    assert body["message_type"] == "history_bars"
    assert body["summary"]["history_bar_timeframe"] == "1m"

def test_adapter_trigger_burst_ingestion_is_stored() -> None:
    application = build_application()

    response = application.dispatch(
        "POST",
        "/api/v1/adapter/trigger-burst",
        load_fixture("atas_adapter.trigger_burst.sample.json"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["message_type"] == "trigger_burst"
    assert payload["summary"]["trigger_type"] == "failed_overhead_capping"
    assert payload["summary"]["trade_event_count"] == 6
    assert payload["summary"]["depth_event_count"] == 4
    assert payload["summary"]["second_feature_count"] == 4
    assert "renewed_aggressive_buying" in payload["summary"]["reason_codes"]
    assert payload["bridge_errors"] == []
    assert len(payload["durable_outputs"]) == 1
    durable_output = payload["durable_outputs"][0]
    assert durable_output["ingestion_kind"] == "event_snapshot"

    ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{payload['ingestion_id']}")
    assert ingestion_response.status_code == 200
    ingestion_payload = json.loads(ingestion_response.body)
    assert ingestion_payload["ingestion_kind"] == "adapter_trigger_burst"
    assert ingestion_payload["observed_payload"]["trigger"]["trigger_type"] == "failed_overhead_capping"
    assert ingestion_payload["observed_payload"]["source"]["chart_instance_id"] == "NQ-7fa31b2c"

    bridged_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{durable_output['ingestion_id']}")
    assert bridged_ingestion_response.status_code == 200
    bridged_ingestion_payload = json.loads(bridged_ingestion_response.body)
    assert bridged_ingestion_payload["ingestion_kind"] == "event_snapshot"
    assert bridged_ingestion_payload["observed_payload"]["event_snapshot_id"] == "bridge-evt-adapter-burst-20260316-143020"
    assert bridged_ingestion_payload["observed_payload"]["source"]["chart_instance_id"] == "NQ-7fa31b2c"

    bridged_analysis_response = application.dispatch("GET", f"/api/v1/analyses/{durable_output['analysis_id']}")
    assert bridged_analysis_response.status_code == 200

def test_adapter_continuous_state_generic_chart_instance_id_is_canonicalized_on_ingest() -> None:
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

    response = application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    assert response.status_code == 201
    body = json.loads(response.body)
    stored = application._repository.get_ingestion(body["ingestion_id"])
    assert stored is not None
    assert stored.observed_payload["source"]["chart_instance_id"] == "chart-NQH6-1m-CME-USD"
