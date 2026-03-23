from __future__ import annotations

import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiChatService, ReplayAiReviewService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ChartCandle,
    ReplayAiChatContent,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiInvalidationReview,
    ReplayAiEntryReview,
    ReplayAiReviewContent,
    ReplayAiReviewRequest,
    ReplayAiScriptReview,
    ReplayAiZoneReview,
    ReplayWorkbenchBuildRequest,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.server import ApplicationRequestHandler
from atas_market_structure.strategy_library_services import StrategyLibraryService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "samples"
TEST_DB_DIR = Path(__file__).resolve().parents[1] / "data" / "test-runs"


class FakeReplayReviewer:
    def generate_review(self, payload, *, operator_entries, manual_regions, model_override: str | None = None):
        model_name = model_override or "fake-gpt-test"
        return (
            "fake-openai",
            model_name,
            ReplayAiReviewContent(
                narrative_summary="Replay shows defended support and a continuation bias into upper liquidity.",
                key_zones=[
                    ReplayAiZoneReview(
                        label="Europe defended bid",
                        zone_low=payload.focus_regions[0].price_low if payload.focus_regions else 21500.0,
                        zone_high=payload.focus_regions[0].price_high if payload.focus_regions else 21504.0,
                        role="support",
                        strength_score=0.82,
                        evidence=["same_price_replenishment", "initiative_drive_follow_through"],
                    ),
                ],
                script_review=ReplayAiScriptReview(
                    preferred_script="continuation",
                    continuation_case=["initiative drive is still active"],
                    reversal_case=["upper liquidity has not failed yet"],
                    preferred_rationale=["defended bid and higher-lows sequence remain intact"],
                ),
                entry_reviews=[
                    ReplayAiEntryReview(
                        entry_id=(operator_entries[0].entry_id if operator_entries else "entry-none"),
                        verdict="valid" if operator_entries else "not_reviewed",
                        context_alignment_score=0.76 if operator_entries else 0.0,
                        rationale=["entry aligned with defended support"] if operator_entries else [],
                        mistakes=["entry was slightly early"] if operator_entries else [],
                        better_conditions=["wait for one more confirming higher low"] if operator_entries else [],
                    )
                ] if operator_entries else [],
                invalidations=[
                    ReplayAiInvalidationReview(
                        label="Defended bid fails",
                        price=payload.focus_regions[0].price_low if payload.focus_regions else 21500.0,
                        reason="Loss of the defended bid breaks the continuation case.",
                    )
                ],
                no_trade_guidance=["Do not open inside the middle of the balance without fresh initiative."],
                unresolved_conflicts=["Need to confirm whether upper liquidity absorbs or releases."],
                operator_focus=["Watch the first retest of the defended bid."],
            ),
        )


class FakeReplayChatAssistant:
    def generate_reply(
        self,
        payload,
        *,
        strategy_cards,
        operator_entries,
        manual_regions,
        live_context_messages,
        attachments=None,
        preset,
        user_message: str,
        history,
        model_override: str | None = None,
    ):
        model_name = model_override or "fake-chat-test"
        live_summary = [
            f"live_messages={len(live_context_messages)}",
            f"strategy_cards={len(strategy_cards)}",
            f"operator_entries={len(operator_entries)}",
            f"manual_regions={len(manual_regions)}",
        ]
        referenced_strategy_ids = [item.strategy_id for item in strategy_cards[:2]]
        return (
            "fake-openai",
            model_name,
            ReplayAiChatContent(
                reply_text=f"preset={preset.value}; user={user_message}",
                live_context_summary=live_summary,
                referenced_strategy_ids=referenced_strategy_ids,
                follow_up_suggestions=[
                    "确认当前 focus region 是否已经被消耗。",
                    "检查大单是否仍在原价位连续补单。",
                ],
            ),
        )


def build_application(
    *,
    replay_ai_review_service: ReplayAiReviewService | None = None,
    replay_ai_chat_service: ReplayAiChatService | None = None,
) -> MarketStructureApplication:
    TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    return MarketStructureApplication(
        repository=repository,
        replay_ai_review_service=replay_ai_review_service,
        replay_ai_chat_service=replay_ai_chat_service,
    )


def load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def load_json_fixture(name: str) -> dict[str, object]:
    return json.loads(load_fixture(name))


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


def test_replay_workbench_page_is_served() -> None:
    application = build_application()

    response = application.dispatch("GET", "/workbench/replay")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert "<title>盘前复盘工作台</title>".encode("utf-8") in response.body
    assert 'href="/static/chat_window.css"'.encode("utf-8") in response.body
    assert 'from "/static/replay_workbench_bootstrap.js"'.encode("utf-8") in response.body
    assert "打开 AI 助手".encode("utf-8") in response.body
    assert "最近7天".encode("utf-8") in response.body
    assert "手工区域".encode("utf-8") in response.body
    assert "标记管理".encode("utf-8") in response.body
    assert "发送当前可视区域到聊天".encode("utf-8") in response.body


def test_replay_workbench_chat_static_assets_are_served() -> None:
    application = build_application()

    css_response = application.dispatch("GET", "/static/chat_window.css")
    js_response = application.dispatch("GET", "/static/chat_window.js")

    assert css_response.status_code == 200
    assert css_response.headers["Content-Type"] == "text/css; charset=utf-8"
    assert ".chat-message.user".encode("utf-8") in css_response.body
    assert ".ai-chat-module".encode("utf-8") in css_response.body

    assert js_response.status_code == 200
    assert js_response.headers["Content-Type"] == "application/javascript; charset=utf-8"
    assert "window.ReplayChatWindow".encode("utf-8") in js_response.body
    assert "renderThread".encode("utf-8") in js_response.body


def test_invalid_layer_timeframe_is_rejected() -> None:
    application = build_application()
    invalid_payload = json.loads(load_fixture("market_structure.sample.json"))
    invalid_payload["decision_layers"]["macro_context"][0]["timeframe"] = "1m"

    response = application.dispatch(
        "POST",
        "/api/v1/ingestions/market-structure",
        json.dumps(invalid_payload).encode("utf-8"),
    )

    assert response.status_code == 422
    payload = json.loads(response.body)
    assert payload["error"] == "validation_error"


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


def test_replay_ai_review_endpoint_returns_structured_review() -> None:
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    review_service = ReplayAiReviewService(repository=repository, reviewer=FakeReplayReviewer())
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_review_service=review_service,
    )

    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)
    entry_response = application.dispatch(
        "POST",
        "/api/v1/workbench/operator-entries",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "executed_at": "2026-03-17T01:05:00Z",
                "side": "buy",
                "entry_price": 21524.25,
                "quantity": 1,
                "stop_price": 21518.25,
                "timeframe_context": "1m",
                "thesis": "micro trend continuation",
                "context_notes": ["defended bid held twice"],
                "tags": ["scalp", "continuation"],
            }
        ).encode("utf-8"),
    )
    assert entry_response.status_code == 201

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-ai-review",
        json.dumps(
            ReplayAiReviewRequest(
                replay_ingestion_id=replay_payload["ingestion_id"],
                model_override="fake-gpt-override",
                force_refresh=False,
            ).model_dump(mode="json")
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["provider"] == "fake-openai"
    assert payload["model"] == "fake-gpt-override"
    assert payload["replay_ingestion_id"] == replay_payload["ingestion_id"]
    assert payload["review"]["script_review"]["preferred_script"] == "continuation"
    assert payload["review"]["key_zones"][0]["role"] == "support"
    assert payload["review"]["entry_reviews"][0]["verdict"] == "valid"
    assert payload["review"]["no_trade_guidance"][0].startswith("Do not open")


def test_operator_entry_is_stored_and_listed() -> None:
    application = build_application()
    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/operator-entries",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "executed_at": "2026-03-17T01:05:00Z",
                "side": "sell",
                "entry_price": 21531.5,
                "quantity": 2,
                "stop_price": 21535.0,
                "target_price": 21521.0,
                "timeframe_context": "1m",
                "thesis": "fade failed overhead cap",
                "context_notes": ["upper liquidity already harvested"],
                "tags": ["scalp", "fade"],
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["entry"]["side"] == "sell"
    assert payload["entry"]["instrument_symbol"] == "NQ"

    list_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/operator-entries?replay_ingestion_id={replay_payload['ingestion_id']}",
    )
    assert list_response.status_code == 200
    list_payload = json.loads(list_response.body)
    assert list_payload["replay_ingestion_id"] == replay_payload["ingestion_id"]
    assert len(list_payload["entries"]) == 1
    assert list_payload["entries"][0]["thesis"] == "fade failed overhead cap"


def test_manual_region_is_stored_and_listed() -> None:
    application = build_application()
    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/manual-regions",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "label": "bullish defense candidate",
                "thesis": "If price returns here with absorption, the region may reverse higher.",
                "price_low": 21508.5,
                "price_high": 21514.25,
                "started_at": "2026-03-17T00:30:00Z",
                "ended_at": "2026-03-17T01:15:00Z",
                "side_bias": "buy",
                "notes": ["watch replenishment", "wait for rejection"],
                "tags": ["support", "trapped_inventory"],
            }
        ).encode("utf-8"),
    )

    assert response.status_code == 201
    payload = json.loads(response.body)
    assert payload["region"]["label"] == "bullish defense candidate"
    assert payload["region"]["side_bias"] == "buy"

    list_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/manual-regions?replay_ingestion_id={replay_payload['ingestion_id']}",
    )
    assert list_response.status_code == 200
    list_payload = json.loads(list_response.body)
    assert len(list_payload["regions"]) == 1
    assert list_payload["regions"][0]["tags"] == ["support", "trapped_inventory"]


def test_replay_footprint_bar_detail_endpoint_returns_price_levels() -> None:
    application = build_application()
    history_bars_payload = load_json_fixture("atas_adapter.history_bars.sample.json")
    history_footprint_payload = load_json_fixture("atas_adapter.history_footprint.sample.json")

    application.dispatch(
        "POST",
        "/api/v1/adapter/history-bars",
        json.dumps(history_bars_payload).encode("utf-8"),
    )
    application.dispatch(
        "POST",
        "/api/v1/adapter/history-footprint",
        json.dumps(history_footprint_payload).encode("utf-8"),
    )

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
    build_body = json.loads(build_response.body)

    detail_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/footprint-bar?replay_ingestion_id={build_body['ingestion_id']}&bar_started_at=2026-03-17T09:00:00+00:00",
    )
    assert detail_response.status_code == 200
    detail_payload = json.loads(detail_response.body)
    assert detail_payload["instrument_symbol"] == "NQ"
    assert len(detail_payload["price_levels"]) == 5
    assert detail_payload["price_levels"][0]["price"] >= detail_payload["price_levels"][-1]["price"]


def test_replay_ai_chat_endpoint_uses_strategy_library_cards() -> None:
    repository = SQLiteAnalysisRepository(database_path=TEST_DB_DIR / f"{uuid4().hex}.db")
    repository.initialize()
    chat_service = ReplayAiChatService(
        repository=repository,
        assistant=FakeReplayChatAssistant(),
        strategy_library_service=StrategyLibraryService(root_dir=Path(__file__).resolve().parents[1]),
    )
    application = MarketStructureApplication(
        repository=repository,
        replay_ai_chat_service=chat_service,
    )

    replay_response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-snapshots",
        load_fixture("replay_workbench.snapshot.sample.json"),
    )
    replay_payload = json.loads(replay_response.body)
    application.dispatch(
        "POST",
        "/api/v1/workbench/manual-regions",
        json.dumps(
            {
                "replay_ingestion_id": replay_payload["ingestion_id"],
                "label": "bullish defense candidate",
                "thesis": "This region may hold only if absorption appears on retest.",
                "price_low": 21508.5,
                "price_high": 21514.25,
                "started_at": "2026-03-17T00:30:00Z",
                "ended_at": "2026-03-17T01:15:00Z",
                "side_bias": "buy",
                "notes": ["wait for confirmation"],
                "tags": ["support", "manual_region"],
            }
        ).encode("utf-8"),
    )

    continuous_payload = load_json_fixture("atas_adapter.continuous_state.sample.json")
    continuous_payload["message_id"] = "adapter-msg-chat-01"
    continuous_payload["emitted_at"] = "2026-03-17T01:04:30Z"
    continuous_payload["observed_window_start"] = "2026-03-17T01:04:00Z"
    continuous_payload["observed_window_end"] = "2026-03-17T01:05:00Z"
    continuous_payload["source"]["chart_instance_id"] = "NQ-03d4a876"
    continuous_payload["instrument"]["symbol"] = "NQ"
    application.dispatch(
        "POST",
        "/api/v1/adapter/continuous-state",
        json.dumps(continuous_payload).encode("utf-8"),
    )

    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-ai-chat",
        json.dumps(
            ReplayAiChatRequest(
                replay_ingestion_id=replay_payload["ingestion_id"],
                preset=ReplayAiChatPreset.FOCUS_REGIONS,
                user_message="分析重点价格区域，并说明哪里不能开仓。",
                history=[],
                model_override="fake-chat-override",
                include_live_context=True,
            ).model_dump(mode="json")
        ).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["provider"] == "fake-openai"
    assert payload["model"] == "fake-chat-override"
    assert payload["preset"] == "focus_regions"
    assert payload["reply_text"].startswith("preset=focus_regions")
    assert payload["referenced_strategy_ids"] == ["pattern-nq-replenished-bid-launchpad"]
    assert payload["live_context_summary"][0] == "live_messages=1"
    assert payload["live_context_summary"][3] == "manual_regions=1"
    assert len(payload["follow_up_suggestions"]) == 2


def test_chat_session_routes_remain_available_without_ai_backend() -> None:
    application = build_application()

    create_response = application.dispatch(
        "POST",
        "/api/v1/workbench/chat/sessions",
        json.dumps(
            {
                "workspace_id": "replay_main",
                "title": "无模型会话",
                "symbol": "NQ",
                "contract_id": "NQ",
                "timeframe": "1m",
                "window_range": {
                    "start": "2026-03-17T13:30:00Z",
                    "end": "2026-03-17T20:00:00Z",
                },
                "start_blank": True,
            }
        ).encode("utf-8"),
    )
    assert create_response.status_code == 201
    session_id = json.loads(create_response.body)["session"]["session_id"]

    list_response = application.dispatch("GET", "/api/v1/workbench/chat/sessions")
    assert list_response.status_code == 200
    assert len(json.loads(list_response.body)["sessions"]) == 1

    reply_response = application.dispatch(
        "POST",
        f"/api/v1/workbench/chat/sessions/{session_id}/reply",
        json.dumps(
            {
                "preset": ReplayAiChatPreset.GENERAL.value,
                "user_input": "这里还能不能继续做多？",
                "selected_block_ids": [],
                "pinned_block_ids": [],
                "include_memory_summary": False,
                "include_recent_messages": False,
                "attachments": [],
            }
        ).encode("utf-8"),
    )
    assert reply_response.status_code == 503
    reply_payload = json.loads(reply_response.body)
    assert reply_payload["error"] == "chat_unavailable"

    messages_response = application.dispatch(
        "GET",
        f"/api/v1/workbench/chat/sessions/{session_id}/messages",
    )
    assert messages_response.status_code == 200
    assert json.loads(messages_response.body)["messages"] == []


def test_http_bridge_supports_patch_requests_for_chat_sessions() -> None:
    application = build_application()
    ApplicationRequestHandler.application = application
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApplicationRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        create_response = application.dispatch(
            "POST",
            "/api/v1/workbench/chat/sessions",
            json.dumps(
                {
                    "workspace_id": "replay_main",
                    "title": "PATCH 会话",
                    "symbol": "NQ",
                    "contract_id": "NQ",
                    "timeframe": "1m",
                    "window_range": {
                        "start": "2026-03-17T13:30:00Z",
                        "end": "2026-03-17T20:00:00Z",
                    },
                    "start_blank": True,
                }
            ).encode("utf-8"),
        )
        session_id = json.loads(create_response.body)["session"]["session_id"]

        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request(
            "PATCH",
            f"/api/v1/workbench/chat/sessions/{session_id}",
            body=json.dumps({"title": "PATCH 已更新", "pinned": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()

        assert response.status == 200
        assert payload["session"]["title"] == "PATCH 已更新"
        assert payload["session"]["pinned"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


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
