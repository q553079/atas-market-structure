from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from atas_market_structure.ai_review_services import ReplayAiChatService, ReplayAiReviewService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.models import (
    ReplayAiChatContent,
    ReplayAiChatPreset,
    ReplayAiChatRequest,
    ReplayAiInvalidationReview,
    ReplayAiEntryReview,
    ReplayAiReviewContent,
    ReplayAiReviewRequest,
    ReplayAiScriptReview,
    ReplayAiZoneReview,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
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
    assert "AI 分析".encode("utf-8") in response.body
    assert "7天 1分".encode("utf-8") in response.body
    assert "7天 5分".encode("utf-8") in response.body
    assert "手工区域".encode("utf-8") in response.body
    assert "分析已标注区域".encode("utf-8") in response.body
    assert "分析选中K线足迹".encode("utf-8") in response.body


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

    replay_ingestion_response = application.dispatch("GET", f"/api/v1/ingestions/{build_body['ingestion_id']}")
    assert replay_ingestion_response.status_code == 200
    replay_ingestion_body = json.loads(replay_ingestion_response.body)
    assert replay_ingestion_body["observed_payload"]["acquisition_mode"] == "atas_fetch"
    assert replay_ingestion_body["observed_payload"]["raw_features"]["history_source"] == "adapter_history_bars"
    assert replay_ingestion_body["observed_payload"]["candles"][0]["open"] == 21498.0


def test_adapter_history_footprint_ingestion_enriches_replay_raw_features() -> None:
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


def test_replay_workbench_builder_requests_atas_fetch_when_local_history_is_insufficient() -> None:
    application = build_application()

    build_request = load_json_fixture("replay_workbench.build_request.sample.json")
    response = application.dispatch(
        "POST",
        "/api/v1/workbench/replay-builder/build",
        json.dumps(build_request).encode("utf-8"),
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["action"] == "atas_fetch_required"
    assert payload["local_message_count"] == 0
    assert payload["atas_fetch_request"]["instrument_symbol"] == "NQ"


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
    assert payload["cache_record"]["cache_key"] == "NQ|5m|2026-03-16T14:30:00Z|2026-03-16T14:41:00Z"
