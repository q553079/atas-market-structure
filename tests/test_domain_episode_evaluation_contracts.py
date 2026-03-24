from __future__ import annotations

from datetime import UTC, datetime, timedelta

from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.models import (
    EpisodeResolution,
    EvaluationFailureMode,
    EventHypothesisKind,
    EventPhase,
    TradableEventKind,
)
from tests.contract_support import build_test_belief, build_test_episode, build_test_profile


def test_replaced_episode_maps_to_missed_transition_contract() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    beliefs = [
        build_test_belief(
            belief_id="prior",
            observed_at=base - timedelta(minutes=1),
            phase=EventPhase.BUILDING,
            probability=0.36,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            transition_watch=["watch_absorption_accumulation"],
        ),
        build_test_belief(
            belief_id="b0",
            observed_at=base,
            phase=EventPhase.BUILDING,
            probability=0.40,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            transition_watch=["watch_absorption_accumulation"],
        ),
        build_test_belief(
            belief_id="b1",
            observed_at=base + timedelta(minutes=1),
            phase=EventPhase.WEAKENING,
            probability=0.31,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            transition_watch=["watch_absorption_accumulation"],
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
        build_test_belief(
            belief_id="b2",
            observed_at=base + timedelta(minutes=2),
            phase=EventPhase.INVALIDATED,
            probability=0.16,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            transition_watch=["watch_absorption_accumulation"],
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
    ]
    episode = build_test_episode(
        started_at=base,
        ended_at=base + timedelta(minutes=2),
        resolution=EpisodeResolution.REPLACED,
        event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
        hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
        replacement_event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        data_status=beliefs[-1].data_status,
    )

    evaluation = service.evaluate_episode(
        episode=episode,
        beliefs=beliefs,
        profile=build_test_profile(),
    )

    assert evaluation.schema_version == "episode_evaluation_v1"
    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.MISSED_TRANSITION
    assert evaluation.scores.transition_handling_score < 0
    assert evaluation.lifecycle.replacement_event is TradableEventKind.MOMENTUM_CONTINUATION


def test_invalidated_episode_maps_to_late_invalidation_contract() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 11, 0, tzinfo=UTC)
    beliefs = [
        build_test_belief(
            belief_id="b0",
            observed_at=base,
            phase=EventPhase.BUILDING,
            probability=0.44,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
        ),
        build_test_belief(
            belief_id="b1",
            observed_at=base + timedelta(minutes=1),
            phase=EventPhase.BUILDING,
            probability=0.41,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
        build_test_belief(
            belief_id="b2",
            observed_at=base + timedelta(minutes=2),
            phase=EventPhase.WEAKENING,
            probability=0.35,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
        build_test_belief(
            belief_id="b3",
            observed_at=base + timedelta(minutes=3),
            phase=EventPhase.WEAKENING,
            probability=0.30,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
        build_test_belief(
            belief_id="b4",
            observed_at=base + timedelta(minutes=4),
            phase=EventPhase.INVALIDATED,
            probability=0.14,
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            invalidating_signals_seen=["fresh_initiative_breakout"],
        ),
    ]
    episode = build_test_episode(
        started_at=base,
        ended_at=base + timedelta(minutes=4),
        resolution=EpisodeResolution.INVALIDATED,
        event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
        hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
        data_status=beliefs[-1].data_status,
    )

    evaluation = service.evaluate_episode(
        episode=episode,
        beliefs=beliefs,
        profile=build_test_profile(),
    )

    assert evaluation.schema_version == "episode_evaluation_v1"
    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.LATE_INVALIDATION
    assert evaluation.scores.invalidation_timing_score < 0
    assert "thresholds.active_hypothesis_probability" in evaluation.diagnosis.candidate_parameters
