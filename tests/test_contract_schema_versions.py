from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atas_market_structure.models import (
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EventCandidate,
    EventMemoryEntry,
    EventOutcomeLedger,
    EventOutcomeListEnvelope,
    EventOutcomeResult,
    EventEpisode,
    EventStatsBreakdownEnvelope,
    EventStatsSummaryEnvelope,
    EventStreamEntry,
    EventStreamEnvelope,
    EventStreamQuery,
    EventOutcomeQuery,
    EventStatsQuery,
    EventHypothesisStateContract,
    FeatureSliceContract,
    PromptTrace,
    PromptTraceBlockSummary,
    PromptTraceEnvelope,
    PromptTraceListEnvelope,
    RecognizerBuild,
    RegimePosteriorContract,
    TuningRecommendation,
)
from atas_market_structure.models._schema_versions import (
    BELIEF_STATE_SCHEMA_VERSION,
    CORE_CANONICAL_SCHEMA_VERSIONS,
    EPISODE_EVALUATION_SCHEMA_VERSION,
    EVENT_CANDIDATE_SCHEMA_VERSION,
    EVENT_EPISODE_SCHEMA_VERSION,
    EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION,
    EVENT_MEMORY_ENTRY_SCHEMA_VERSION,
    EVENT_OUTCOME_LEDGER_SCHEMA_VERSION,
    EVENT_STREAM_ENTRY_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    INSTRUMENT_PROFILE_SCHEMA_VERSION,
    PROMPT_TRACE_SCHEMA_VERSION,
    RECOGNIZER_BUILD_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
    TUNING_RECOMMENDATION_SCHEMA_VERSION,
    WORKBENCH_EVENT_STREAM_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_OUTCOME_LIST_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_STATS_BREAKDOWN_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_STATS_SUMMARY_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_PROMPT_TRACE_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_PROMPT_TRACE_LIST_ENVELOPE_SCHEMA_VERSION,
)
from atas_market_structure.profile_services import build_instrument_profile_v1, default_tick_size_for_symbol
from atas_market_structure.storage_models import (
    StoredEventHypothesisState,
    StoredFeatureSlice,
    StoredRegimePosterior,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_core_canonical_schema_catalog_is_stable() -> None:
    assert CORE_CANONICAL_SCHEMA_VERSIONS == (
        "instrument_profile_v1",
        "recognizer_build_v1",
        "feature_slice_v1",
        "regime_posterior_v1",
        "event_hypothesis_state_v1",
        "belief_state_snapshot_v1",
        "event_episode_v1",
        "episode_evaluation_v1",
        "tuning_recommendation_v1",
    )


def test_core_public_contracts_normalize_legacy_schema_versions() -> None:
    profile = build_instrument_profile_v1(
        "NQ",
        tick_size=default_tick_size_for_symbol("NQ"),
        profile_version="nq-profile-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )
    build = RecognizerBuild(
        engine_version="recognizer-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        is_active=True,
        status="active",
        notes=[],
        created_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )
    belief_payload = _load_json(ROOT / "samples" / "recognition" / "momentum_continuation.sample.json")
    belief_payload["schema_version"] = "1.0.0"
    belief = BeliefStateSnapshot.model_validate(belief_payload)
    episode = EventEpisode(
        episode_id="ep-momentum-093000",
        instrument_symbol="NQ",
        event_kind="momentum_continuation",
        hypothesis_kind="continuation_base",
        phase="resolved",
        resolution="confirmed",
        started_at=datetime(2026, 3, 23, 9, 30, tzinfo=UTC),
        ended_at=datetime(2026, 3, 23, 9, 33, tzinfo=UTC),
        peak_probability=0.81,
        dominant_regime="strong_momentum_trend",
        supporting_evidence=["initiative"],
        invalidating_evidence=[],
        key_evidence_summary=["continuation held"],
        active_anchor_ids=[],
        replacement_episode_id=None,
        replacement_event_kind=None,
        schema_version="1.0.0",
        profile_version=belief.profile_version,
        engine_version=belief.engine_version,
        data_status=belief.data_status,
    )
    evaluation_payload = _load_json(ROOT / "samples" / "episode_evaluations" / "momentum_confirmed_none.sample.json")
    evaluation_payload["schema_version"] = "1.0.0"
    evaluation = EpisodeEvaluation.model_validate(evaluation_payload)
    recommendation_payload = _load_json(ROOT / "samples" / "tuning" / "tuning_recommendation.sample.json")
    recommendation_payload["schema_version"] = "1.0.0"
    recommendation = TuningRecommendation.model_validate(recommendation_payload)

    assert profile.schema_version == INSTRUMENT_PROFILE_SCHEMA_VERSION
    assert build.schema_version == RECOGNIZER_BUILD_SCHEMA_VERSION
    assert belief.schema_version == BELIEF_STATE_SCHEMA_VERSION
    assert episode.schema_version == EVENT_EPISODE_SCHEMA_VERSION
    assert evaluation.schema_version == EPISODE_EVALUATION_SCHEMA_VERSION
    assert recommendation.schema_version == TUNING_RECOMMENDATION_SCHEMA_VERSION


def test_workbench_event_contracts_normalize_legacy_schema_versions() -> None:
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    candidate = EventCandidate(
        schema_version="1.0.0",
        event_id="evt-test",
        session_id="sess-test",
        candidate_kind="key_level",
        title="关键价位",
        summary="21524 为关键价位",
        symbol="NQ",
        timeframe="1m",
        anchor_start_ts=now,
        anchor_end_ts=None,
        price_lower=None,
        price_upper=None,
        price_ref=21524.0,
        side_hint="buy",
        confidence=0.8,
        evidence_refs=[],
        source_type="ai_reply_text",
        source_message_id="msg-test",
        source_prompt_trace_id=None,
        lifecycle_state="candidate",
        invalidation_rule={},
        evaluation_window={},
        metadata={},
        dedup_key="dedup-1",
        promoted_projection_type=None,
        promoted_projection_id=None,
        created_at=now,
        updated_at=now,
    )
    stream_entry = EventStreamEntry(
        schema_version="1.0.0",
        stream_entry_id="estream-test",
        event_id="evt-test",
        session_id="sess-test",
        candidate_kind="key_level",
        title="关键价位",
        summary="21524 为关键价位",
        symbol="NQ",
        timeframe="1m",
        anchor_start_ts=now,
        anchor_end_ts=None,
        price_lower=None,
        price_upper=None,
        price_ref=21524.0,
        side_hint="buy",
        confidence=0.8,
        evidence_refs=[],
        source_type="ai_reply_text",
        source_message_id="msg-test",
        source_prompt_trace_id=None,
        lifecycle_state="candidate",
        invalidation_rule={},
        evaluation_window={},
        metadata={},
        stream_action="extracted",
        created_at=now,
        updated_at=now,
    )
    memory_entry = EventMemoryEntry(
        schema_version="1.0.0",
        memory_entry_id="emem-test",
        event_id="evt-test",
        session_id="sess-test",
        candidate_kind="key_level",
        title="关键价位",
        summary="21524 为关键价位",
        symbol="NQ",
        timeframe="1m",
        anchor_start_ts=now,
        anchor_end_ts=None,
        price_lower=None,
        price_upper=None,
        price_ref=21524.0,
        side_hint="buy",
        confidence=0.8,
        evidence_refs=[],
        source_type="ai_reply_text",
        source_message_id="msg-test",
        source_prompt_trace_id=None,
        lifecycle_state="candidate",
        invalidation_rule={},
        evaluation_window={},
        metadata={},
        memory_bucket="active",
        created_at=now,
        updated_at=now,
    )
    envelope = EventStreamEnvelope(
        schema_version="1.0.0",
        query=EventStreamQuery(session_id="sess-test"),
        candidates=[candidate],
        items=[stream_entry],
        memory_entries=[memory_entry],
    )

    assert candidate.schema_version == EVENT_CANDIDATE_SCHEMA_VERSION
    assert stream_entry.schema_version == EVENT_STREAM_ENTRY_SCHEMA_VERSION
    assert memory_entry.schema_version == EVENT_MEMORY_ENTRY_SCHEMA_VERSION
    assert envelope.schema_version == WORKBENCH_EVENT_STREAM_ENVELOPE_SCHEMA_VERSION


def test_workbench_prompt_trace_contracts_normalize_legacy_schema_versions() -> None:
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    trace = PromptTrace(
        schema_version="1.0.0",
        prompt_trace_id="trace-test",
        session_id="sess-test",
        message_id="msg-test",
        symbol="NQ",
        timeframe="1m",
        analysis_type="structure",
        analysis_range="current_window",
        analysis_style="standard",
        selected_block_ids=["pb-1"],
        pinned_block_ids=["pb-2"],
        attached_event_ids=["evt-1"],
        prompt_block_summaries=[
            PromptTraceBlockSummary(
                block_id="pb-1",
                kind="candles_20",
                title="最近 20 根 K 线",
                preview_text="K 线摘要",
                payload_summary={"bar_count": 20},
            )
        ],
        bar_window_summary={"selected_bar_count": 20},
        manual_selection_summary={"region_count": 1},
        memory_summary={"include_recent_messages": True},
        final_system_prompt="system prompt",
        final_user_prompt="user prompt",
        model_name="fake-chat-e2e",
        model_input_hash="hash-1",
        snapshot={"request_snapshot": {"transport_mode": "text_only"}},
        metadata={"truncation": {}},
        created_at=now,
        updated_at=now,
    )
    envelope = PromptTraceEnvelope(schema_version="1.0.0", trace=trace)
    list_envelope = PromptTraceListEnvelope(schema_version="1.0.0", traces=[trace])

    assert trace.schema_version == PROMPT_TRACE_SCHEMA_VERSION
    assert envelope.schema_version == WORKBENCH_PROMPT_TRACE_ENVELOPE_SCHEMA_VERSION
    assert list_envelope.schema_version == WORKBENCH_PROMPT_TRACE_LIST_ENVELOPE_SCHEMA_VERSION


def test_workbench_event_outcome_contracts_normalize_legacy_schema_versions() -> None:
    now = datetime(2026, 3, 25, 9, 30, tzinfo=UTC)
    outcome = EventOutcomeLedger(
        schema_version="1.0.0",
        outcome_id="out-test",
        event_id="evt-test",
        session_id="sess-test",
        source_message_id="msg-test",
        source_prompt_trace_id="trace-test",
        analysis_preset="recent_20_bars",
        model_name="gpt-test",
        symbol="NQ",
        timeframe="1m",
        event_kind="plan_intent",
        born_at=now,
        observed_price=21524.0,
        target_rule={"type": "plan_target", "price": 21530.0},
        invalidation_rule={"type": "plan_stop", "price": 21518.0},
        evaluation_window_start=now,
        evaluation_window_end=now,
        expiry_policy={"window_end": now.isoformat()},
        realized_outcome=EventOutcomeResult.SUCCESS,
        outcome_label="success",
        mfe=6.0,
        mae=1.0,
        hit_target=True,
        hit_stop=False,
        timed_out=False,
        inconclusive=False,
        evaluated_at=now,
        metadata={"resolution_reason": "target_rule_hit"},
        created_at=now,
        updated_at=now,
    )
    list_envelope = EventOutcomeListEnvelope(
        schema_version="1.0.0",
        query=EventOutcomeQuery(session_id="sess-test"),
        outcomes=[outcome],
    )
    summary_envelope = EventStatsSummaryEnvelope(
        schema_version="1.0.0",
        query=EventStatsQuery(session_id="sess-test"),
        summary={
            "total_count": 1,
            "settled_count": 1,
            "open_count": 0,
            "success_count": 1,
            "failure_count": 0,
            "timeout_count": 0,
            "inconclusive_count": 0,
            "accuracy_rate": 1.0,
            "failure_rate": 0.0,
            "timeout_rate": 0.0,
            "inconclusive_rate": 0.0,
        },
    )
    breakdown_envelope = EventStatsBreakdownEnvelope(
        schema_version="1.0.0",
        query=EventStatsQuery(session_id="sess-test"),
        dimension="event_kind",
        buckets=[],
    )

    assert outcome.schema_version == EVENT_OUTCOME_LEDGER_SCHEMA_VERSION
    assert list_envelope.schema_version == WORKBENCH_EVENT_OUTCOME_LIST_ENVELOPE_SCHEMA_VERSION
    assert summary_envelope.schema_version == WORKBENCH_EVENT_STATS_SUMMARY_ENVELOPE_SCHEMA_VERSION
    assert breakdown_envelope.schema_version == WORKBENCH_EVENT_STATS_BREAKDOWN_ENVELOPE_SCHEMA_VERSION


def test_append_only_recognition_contracts_validate_storage_shapes() -> None:
    market_time = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    belief_payload = _load_json(ROOT / "samples" / "recognition" / "momentum_continuation.sample.json")
    belief = BeliefStateSnapshot.model_validate(belief_payload)

    feature = FeatureSliceContract.model_validate(
        asdict(
            StoredFeatureSlice(
                feature_slice_id="fs-nq-202603230930",
                instrument_symbol="NQ",
                market_time=market_time,
                session_date="2026-03-23",
                ingested_at=market_time,
                schema_version="1.0.0",
                profile_version=belief.profile_version,
                engine_version=belief.engine_version,
                source_observation_table="observation_adapter_payload",
                source_observation_id="obs-nq-1",
                slice_kind="deterministic_recognition_v1",
                window_start=market_time,
                window_end=market_time,
                data_status=belief.data_status.model_dump(mode="json"),
                feature_payload={
                    "current_price": 21574.25,
                    "metrics": {"trend_efficiency": 0.82},
                    "evidence_buckets": {
                        "initiative": {
                            "score": 0.82,
                            "available": True,
                            "weight": 1.0,
                            "signals": ["initiative_drive_follow_through"],
                            "metrics": {"net_delta": 370},
                        }
                    },
                    "notes": ["test-slice"],
                },
            )
        )
    )
    posterior = RegimePosteriorContract.model_validate(
        asdict(
            StoredRegimePosterior(
                posterior_id="reg-nq-202603230930",
                instrument_symbol="NQ",
                market_time=market_time,
                session_date="2026-03-23",
                ingested_at=market_time,
                schema_version="1.0.0",
                profile_version=belief.profile_version,
                engine_version=belief.engine_version,
                feature_slice_id=feature.feature_slice_id,
                posterior_payload={
                    "regime_posteriors": [item.model_dump(mode="json") for item in belief.regime_posteriors],
                    "top_regime": belief.regime_posteriors[0].regime.value,
                },
            )
        )
    )
    hypothesis = EventHypothesisStateContract.model_validate(
        asdict(
            StoredEventHypothesisState(
                hypothesis_state_id="hyp-nq-202603230930",
                instrument_symbol="NQ",
                market_time=market_time,
                session_date="2026-03-23",
                ingested_at=market_time,
                schema_version="1.0.0",
                profile_version=belief.profile_version,
                engine_version=belief.engine_version,
                feature_slice_id=feature.feature_slice_id,
                hypothesis_kind=belief.event_hypotheses[0].hypothesis_kind.value,
                hypothesis_payload=belief.event_hypotheses[0].model_dump(mode="json"),
            )
        )
    )

    assert feature.schema_version == FEATURE_SLICE_SCHEMA_VERSION
    assert posterior.schema_version == REGIME_POSTERIOR_SCHEMA_VERSION
    assert hypothesis.schema_version == EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION
    assert posterior.posterior_payload.top_regime == belief.regime_posteriors[0].regime
    assert hypothesis.hypothesis_kind == belief.event_hypotheses[0].hypothesis_kind


def test_unknown_schema_version_is_rejected_for_frozen_contracts() -> None:
    payload = _load_json(ROOT / "samples" / "recognition" / "momentum_continuation.sample.json")
    payload["schema_version"] = "belief_state_snapshot_v2"

    with pytest.raises(ValidationError):
        BeliefStateSnapshot.model_validate(payload)
