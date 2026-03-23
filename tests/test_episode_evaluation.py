from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    EpisodeResolution,
    EvaluationFailureMode,
    EventEpisode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    MemoryAnchorSnapshot,
    RecognitionMode,
    RegimeKind,
    RegimePosteriorRecord,
    TradableEventKind,
    EpisodeEvaluation,
)
from atas_market_structure.profile_services import build_instrument_profile_v1, default_tick_size_for_symbol
from atas_market_structure.repository import SQLiteAnalysisRepository


ROOT = Path(__file__).resolve().parents[1]


def test_rule_review_v1_none_for_confirmed_episode_with_timely_confirmation() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    profile = _profile("NQ")
    prior = _belief(
        belief_id="prior",
        observed_at=base - timedelta(minutes=1),
        states=[
            _state(
                hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
                event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
                phase=EventPhase.BUILDING,
                probability=0.34,
                transition_watch=["watch_distribution_balance"],
            ),
        ],
        transition_watch=["watch_distribution_balance"],
    )
    beliefs = [
        prior,
        _belief("b0", base, [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.EMERGING, 0.32)]),
        _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.BUILDING, 0.45)]),
        _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.61)]),
        _belief("b3", base + timedelta(minutes=3), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.78)]),
    ]
    episode = _episode(
        event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        resolution=EpisodeResolution.CONFIRMED,
        started_at=base,
        ended_at=base + timedelta(minutes=3),
    )

    evaluation = service.evaluate_episode(episode=episode, beliefs=beliefs, profile=profile)

    assert evaluation.schema_version == "episode_evaluation_v1"
    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.NONE
    assert evaluation.scores.hypothesis_selection_score == 2
    assert evaluation.scores.confirmation_timing_score == 1
    assert evaluation.scores.calibration_score == 2
    assert evaluation.outcome.did_event_materialize is True
    assert evaluation.diagnosis.candidate_parameters == []


def test_rule_review_v1_detects_early_confirmation() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)

    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
            resolution=EpisodeResolution.CONFIRMED,
            started_at=base,
            ended_at=base + timedelta(minutes=1),
        ),
        beliefs=[
            _belief("b0", base, [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.62)]),
            _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.77)]),
        ],
        profile=_profile("NQ"),
    )

    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.EARLY_CONFIRMATION
    assert evaluation.scores.confirmation_timing_score < 0
    assert "thresholds.confirming_hypothesis_probability" in evaluation.diagnosis.candidate_parameters
    assert evaluation.diagnosis.suggested_direction["thresholds.confirming_hypothesis_probability"] == "increase"


def test_rule_review_v1_detects_late_invalidation() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 11, 0, tzinfo=UTC)
    beliefs = [
        _belief("b0", base, [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.BUILDING, 0.44)]),
        _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.BUILDING, 0.41, invalidating_signals=["fresh_initiative_breakout"])], invalidating_signals_seen=["fresh_initiative_breakout"]),
        _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.WEAKENING, 0.35, invalidating_signals=["fresh_initiative_breakout"])], invalidating_signals_seen=["fresh_initiative_breakout"]),
        _belief("b3", base + timedelta(minutes=3), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.WEAKENING, 0.30, invalidating_signals=["fresh_initiative_breakout"])], invalidating_signals_seen=["fresh_initiative_breakout"]),
        _belief("b4", base + timedelta(minutes=4), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.INVALIDATED, 0.14, invalidating_signals=["fresh_initiative_breakout"])], invalidating_signals_seen=["fresh_initiative_breakout"]),
    ]

    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            resolution=EpisodeResolution.INVALIDATED,
            started_at=base,
            ended_at=base + timedelta(minutes=4),
        ),
        beliefs=beliefs,
        profile=_profile("NQ"),
    )

    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.LATE_INVALIDATION
    assert evaluation.scores.invalidation_timing_score < 0
    assert "thresholds.active_hypothesis_probability" in evaluation.diagnosis.candidate_parameters


def test_rule_review_v1_detects_missed_transition() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    beliefs = [
        _belief("prior", base - timedelta(minutes=1), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.BUILDING, 0.36)], transition_watch=["watch_absorption_accumulation"]),
        _belief("b0", base, [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.BUILDING, 0.40)], transition_watch=["watch_absorption_accumulation"]),
        _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.WEAKENING, 0.31, invalidating_signals=["fresh_initiative_breakout"])], transition_watch=["watch_absorption_accumulation"], invalidating_signals_seen=["fresh_initiative_breakout"]),
        _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.INVALIDATED, 0.16, invalidating_signals=["fresh_initiative_breakout"])], transition_watch=["watch_absorption_accumulation"], invalidating_signals_seen=["fresh_initiative_breakout"]),
    ]

    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            resolution=EpisodeResolution.REPLACED,
            started_at=base,
            ended_at=base + timedelta(minutes=2),
            replacement_event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        ),
        beliefs=beliefs,
        profile=_profile("NQ"),
    )

    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.MISSED_TRANSITION
    assert evaluation.scores.transition_handling_score < 0
    assert "weights.path_dependency" in evaluation.diagnosis.candidate_parameters


def test_rule_review_v1_detects_false_positive() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 13, 0, tzinfo=UTC)
    beliefs = [
        _belief("b0", base, [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.EMERGING, 0.31)]),
        _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.BUILDING, 0.45)]),
        _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.78)]),
        _belief("b3", base + timedelta(minutes=3), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.INVALIDATED, 0.18, invalidating_signals=["returned_to_balance_center"])], invalidating_signals_seen=["returned_to_balance_center"]),
    ]

    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
            resolution=EpisodeResolution.INVALIDATED,
            started_at=base,
            ended_at=base + timedelta(minutes=3),
        ),
        beliefs=beliefs,
        profile=_profile("NQ"),
    )

    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.FALSE_POSITIVE
    assert evaluation.scores.calibration_score < 0
    assert evaluation.diagnosis.suggested_direction["thresholds.confirming_hypothesis_probability"] == "increase"


def test_rule_review_v1_detects_false_negative() -> None:
    service = EpisodeEvaluationService()
    base = datetime(2026, 3, 23, 14, 0, tzinfo=UTC)
    beliefs = [
        _belief("prior", base - timedelta(minutes=1), [_state(EventHypothesisKind.REVERSAL_PREPARATION, TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION, EventPhase.EMERGING, 0.21)], transition_watch=["watch_reversal_preparation"]),
        _belief("b0", base, [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.EMERGING, 0.12)]),
        _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.EMERGING, 0.18)]),
        _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.BUILDING, 0.29)]),
        _belief("b3", base + timedelta(minutes=3), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.CONFIRMING, 0.58)]),
        _belief("b4", base + timedelta(minutes=4), [_state(EventHypothesisKind.DISTRIBUTION_BALANCE, TradableEventKind.BALANCE_MEAN_REVERSION, EventPhase.RESOLVED, 0.77)]),
    ]

    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
            resolution=EpisodeResolution.CONFIRMED,
            started_at=base,
            ended_at=base + timedelta(minutes=4),
        ),
        beliefs=beliefs,
        profile=_profile("NQ"),
    )

    assert evaluation.diagnosis.primary_failure_mode is EvaluationFailureMode.FALSE_NEGATIVE
    assert evaluation.scores.hypothesis_selection_score < 0
    assert evaluation.diagnosis.suggested_direction["priors.hypotheses.distribution_balance"] == "increase"


def test_episode_evaluation_can_persist_and_samples_load(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    service = EpisodeEvaluationService(repository=repository)
    base = datetime(2026, 3, 23, 15, 0, tzinfo=UTC)
    evaluation = service.evaluate_episode(
        episode=_episode(
            event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
            resolution=EpisodeResolution.CONFIRMED,
            started_at=base,
            ended_at=base + timedelta(minutes=3),
        ),
        beliefs=[
            _belief("b0", base, [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.EMERGING, 0.31)]),
            _belief("b1", base + timedelta(minutes=1), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.BUILDING, 0.44)]),
            _belief("b2", base + timedelta(minutes=2), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.60)]),
            _belief("b3", base + timedelta(minutes=3), [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.76)]),
        ],
        profile=_profile("NQ"),
        persist=True,
    )

    stored = repository.get_episode_evaluation(evaluation.episode_id)
    assert stored is not None
    assert stored.schema_version == "episode_evaluation_v1"

    sample_files = sorted((ROOT / "samples" / "episode_evaluations").glob("*.json"))
    assert len(sample_files) >= 5
    for path in sample_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = EpisodeEvaluation.model_validate(payload)
        assert model.schema_version == "episode_evaluation_v1"


def _profile(symbol: str):
    return build_instrument_profile_v1(
        symbol,
        tick_size=default_tick_size_for_symbol(symbol),
        profile_version=f"{symbol.lower()}-profile-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )


def _episode(
    *,
    event_kind: TradableEventKind,
    resolution: EpisodeResolution,
    started_at: datetime,
    ended_at: datetime,
    replacement_event_kind: TradableEventKind | None = None,
) -> EventEpisode:
    return EventEpisode(
        episode_id=f"ep-{event_kind.value}-{started_at.strftime('%H%M')}",
        instrument_symbol="NQ",
        event_kind=event_kind,
        hypothesis_kind=_primary_hypothesis_kind(event_kind),
        phase=EventPhase.RESOLVED if resolution is EpisodeResolution.CONFIRMED else EventPhase.INVALIDATED,
        resolution=resolution,
        started_at=started_at,
        ended_at=ended_at,
        peak_probability=0.78 if resolution is EpisodeResolution.CONFIRMED else 0.76,
        dominant_regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
        supporting_evidence=["support_a", "support_b"],
        invalidating_evidence=["invalidate_a"] if resolution is not EpisodeResolution.CONFIRMED else [],
        key_evidence_summary=["support_a", "support_b"],
        active_anchor_ids=["anc-balance"],
        replacement_episode_id=None,
        replacement_event_kind=replacement_event_kind,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        data_status=_data_status(),
    )


def _belief(
    belief_id: str,
    observed_at: datetime,
    states: list[EventHypothesisState],
    *,
    transition_watch: list[str] | None = None,
    invalidating_signals_seen: list[str] | None = None,
) -> BeliefStateSnapshot:
    return BeliefStateSnapshot(
        belief_state_id=belief_id,
        instrument_symbol="NQ",
        observed_at=observed_at,
        stored_at=observed_at,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        recognition_mode=RecognitionMode.NORMAL,
        data_status=_data_status(),
        regime_posteriors=[RegimePosteriorRecord(regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW, probability=0.44, evidence=["trend_efficiency"])],
        event_hypotheses=states,
        active_anchors=[
            MemoryAnchorSnapshot(
                anchor_id="anc-balance",
                anchor_type="balance_center",
                reference_price=21500.0,
                reference_time=observed_at,
                freshness="fresh",
                distance_ticks=0.0,
                influence=0.7,
                role_profile={"magnet": 0.8},
                profile_version="nq-profile-test",
            ),
        ],
        missing_confirmation=_merge_strings(*(state.missing_confirmation for state in states)),
        invalidating_signals_seen=list(invalidating_signals_seen or []),
        transition_watch=list(transition_watch or []),
        notes=[],
    )


def _state(
    hypothesis_kind: EventHypothesisKind,
    event_kind: TradableEventKind,
    phase: EventPhase,
    probability: float,
    *,
    transition_watch: list[str] | None = None,
    missing_confirmation: list[str] | None = None,
    invalidating_signals: list[str] | None = None,
) -> EventHypothesisState:
    return EventHypothesisState(
        hypothesis_id=f"hyp-{hypothesis_kind.value}-{phase.value}-{int(probability * 100)}",
        hypothesis_kind=hypothesis_kind,
        mapped_event_kind=event_kind,
        phase=phase,
        posterior_probability=probability,
        supporting_evidence=["support"],
        missing_confirmation=list(missing_confirmation or []),
        invalidating_signals=list(invalidating_signals or []),
        transition_watch=list(transition_watch or []),
        data_quality_score=1.0,
        evidence_density_score=0.6,
        model_stability_score=0.8,
        anchor_dependence_score=0.5,
    )


def _primary_hypothesis_kind(event_kind: TradableEventKind) -> EventHypothesisKind:
    if event_kind is TradableEventKind.MOMENTUM_CONTINUATION:
        return EventHypothesisKind.CONTINUATION_BASE
    if event_kind is TradableEventKind.BALANCE_MEAN_REVERSION:
        return EventHypothesisKind.DISTRIBUTION_BALANCE
    return EventHypothesisKind.ABSORPTION_ACCUMULATION


def _data_status() -> BeliefDataStatus:
    return BeliefDataStatus(
        data_freshness_ms=0,
        feature_completeness=1.0,
        depth_available=True,
        dom_available=True,
        ai_available=False,
        degraded_modes=[],
        freshness="fresh",
        completeness="complete",
    )


def _merge_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged
