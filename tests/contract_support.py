from __future__ import annotations

from datetime import UTC, datetime

from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    DegradedMode,
    EpisodeResolution,
    EventEpisode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    RecognitionMode,
    RecognizerBuild,
    RegimeKind,
    RegimePosteriorRecord,
    TradableEventKind,
)
from atas_market_structure.profile_services import build_instrument_profile_v1, default_tick_size_for_symbol


def build_test_profile(symbol: str = "NQ"):
    return build_instrument_profile_v1(
        symbol,
        tick_size=default_tick_size_for_symbol(symbol),
        profile_version=f"{symbol.lower()}-profile-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )


def build_test_build() -> RecognizerBuild:
    return RecognizerBuild(
        engine_version="recognizer-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        is_active=True,
        status="active",
        notes=["test recognizer build"],
        created_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )


def build_test_data_status(
    *,
    depth_available: bool = False,
    dom_available: bool = False,
    ai_available: bool = False,
    degraded_modes: list[DegradedMode] | None = None,
) -> BeliefDataStatus:
    effective_modes = list(degraded_modes or [])
    if not depth_available and DegradedMode.NO_DEPTH not in effective_modes:
        effective_modes.append(DegradedMode.NO_DEPTH)
    if not dom_available and DegradedMode.NO_DOM not in effective_modes:
        effective_modes.append(DegradedMode.NO_DOM)
    if not ai_available and DegradedMode.NO_AI not in effective_modes:
        effective_modes.append(DegradedMode.NO_AI)
    return BeliefDataStatus(
        data_freshness_ms=1500,
        feature_completeness=0.7 if depth_available or dom_available else 0.5,
        depth_available=depth_available,
        dom_available=dom_available,
        ai_available=ai_available,
        degraded_modes=effective_modes,
        freshness="current" if depth_available else "delayed",
        completeness="complete" if dom_available else "partial",
    )


def build_test_hypothesis(
    *,
    hypothesis_id: str,
    phase: EventPhase,
    probability: float,
    hypothesis_kind: EventHypothesisKind = EventHypothesisKind.CONTINUATION_BASE,
    event_kind: TradableEventKind = TradableEventKind.MOMENTUM_CONTINUATION,
    transition_watch: list[str] | None = None,
    invalidating_signals: list[str] | None = None,
) -> EventHypothesisState:
    phase_value = EventPhase(phase)
    hypothesis_kind_value = EventHypothesisKind(hypothesis_kind)
    event_kind_value = TradableEventKind(event_kind)
    return EventHypothesisState(
        hypothesis_id=hypothesis_id,
        hypothesis_kind=hypothesis_kind_value,
        mapped_event_kind=event_kind_value,
        phase=phase_value,
        posterior_probability=probability,
        supporting_evidence=["trend_efficiency_support"],
        missing_confirmation=["fresh_push_needed"] if phase_value is not EventPhase.RESOLVED else [],
        invalidating_signals=invalidating_signals or [],
        transition_watch=transition_watch or [],
        data_quality_score=0.8,
        evidence_density_score=0.75,
        model_stability_score=0.7,
        anchor_dependence_score=0.4,
    )


def build_test_belief(
    *,
    belief_id: str,
    observed_at: datetime,
    phase: EventPhase,
    probability: float,
    recognition_mode: RecognitionMode = RecognitionMode.DEGRADED_NO_DEPTH,
    data_status: BeliefDataStatus | None = None,
    event_kind: TradableEventKind = TradableEventKind.MOMENTUM_CONTINUATION,
    hypothesis_kind: EventHypothesisKind = EventHypothesisKind.CONTINUATION_BASE,
    transition_watch: list[str] | None = None,
    invalidating_signals_seen: list[str] | None = None,
) -> BeliefStateSnapshot:
    phase_value = EventPhase(phase)
    recognition_mode_value = RecognitionMode(recognition_mode)
    event_kind_value = TradableEventKind(event_kind)
    hypothesis_kind_value = EventHypothesisKind(hypothesis_kind)
    status = data_status or build_test_data_status()
    return BeliefStateSnapshot(
        belief_state_id=belief_id,
        instrument_symbol="NQ",
        observed_at=observed_at,
        stored_at=observed_at,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        recognition_mode=recognition_mode_value,
        data_status=status,
        regime_posteriors=[
            RegimePosteriorRecord(
                regime=RegimeKind.STRONG_MOMENTUM_TREND,
                probability=0.64,
                evidence=["initiative", "trend_efficiency"],
            )
        ],
        event_hypotheses=[
            build_test_hypothesis(
                hypothesis_id=f"{belief_id}-hyp",
                hypothesis_kind=hypothesis_kind_value,
                event_kind=event_kind_value,
                phase=phase_value,
                probability=probability,
                transition_watch=transition_watch,
                invalidating_signals=invalidating_signals_seen,
            )
        ],
        active_anchors=[],
        missing_confirmation=["fresh_push_needed"] if phase_value is not EventPhase.RESOLVED else [],
        invalidating_signals_seen=invalidating_signals_seen or [],
        transition_watch=transition_watch or [],
        notes=["test-belief"],
    )


def build_test_episode(
    *,
    started_at: datetime,
    ended_at: datetime,
    resolution: EpisodeResolution,
    data_status: BeliefDataStatus | None = None,
    event_kind: TradableEventKind = TradableEventKind.MOMENTUM_CONTINUATION,
    hypothesis_kind: EventHypothesisKind = EventHypothesisKind.CONTINUATION_BASE,
    replacement_event_kind: TradableEventKind | None = None,
) -> EventEpisode:
    resolution_value = EpisodeResolution(resolution)
    event_kind_value = TradableEventKind(event_kind)
    hypothesis_kind_value = EventHypothesisKind(hypothesis_kind)
    replacement_event_kind_value = (
        TradableEventKind(replacement_event_kind) if replacement_event_kind is not None else None
    )
    return EventEpisode(
        episode_id=f"ep-{event_kind_value.value}-{started_at.strftime('%H%M%S')}",
        instrument_symbol="NQ",
        event_kind=event_kind_value,
        hypothesis_kind=hypothesis_kind_value,
        phase=EventPhase.RESOLVED if resolution_value is EpisodeResolution.CONFIRMED else EventPhase.INVALIDATED,
        resolution=resolution_value,
        started_at=started_at,
        ended_at=ended_at,
        peak_probability=0.78,
        dominant_regime=RegimeKind.STRONG_MOMENTUM_TREND,
        supporting_evidence=["trend_efficiency_support"],
        invalidating_evidence=["returned_to_balance_center"] if resolution_value is not EpisodeResolution.CONFIRMED else [],
        key_evidence_summary=["test-summary"],
        active_anchor_ids=[],
        replacement_episode_id=None,
        replacement_event_kind=replacement_event_kind_value,
        schema_version="1.0.0",
        profile_version="nq-profile-test",
        engine_version="recognizer-test",
        data_status=data_status or build_test_data_status(),
    )


def persist_profile_build(repository, *, symbol: str = "NQ") -> None:
    profile = build_test_profile(symbol)
    build = build_test_build()
    repository.save_instrument_profile(
        instrument_symbol=profile.instrument_symbol,
        profile_version=profile.profile_version,
        schema_version=profile.schema_version,
        ontology_version=profile.ontology_version,
        is_active=profile.is_active,
        profile_payload=profile.model_dump(mode="json", by_alias=True),
        created_at=profile.created_at,
    )
    repository.save_recognizer_build(
        engine_version=build.engine_version,
        schema_version=build.schema_version,
        ontology_version=build.ontology_version,
        is_active=build.is_active,
        status=build.status,
        build_payload={"notes": build.notes},
        created_at=build.created_at,
    )


def persist_belief(repository, belief: BeliefStateSnapshot) -> None:
    repository.save_belief_state(
        belief_state_id=belief.belief_state_id,
        instrument_symbol=belief.instrument_symbol,
        observed_at=belief.observed_at,
        stored_at=belief.stored_at,
        schema_version=belief.schema_version,
        profile_version=belief.profile_version,
        engine_version=belief.engine_version,
        recognition_mode=belief.recognition_mode.value,
        belief_payload=belief.model_dump(mode="json", by_alias=True),
    )


def persist_episode(repository, episode: EventEpisode) -> None:
    repository.save_event_episode(
        episode_id=episode.episode_id,
        instrument_symbol=episode.instrument_symbol,
        event_kind=episode.event_kind.value,
        started_at=episode.started_at,
        ended_at=episode.ended_at,
        resolution=episode.resolution.value,
        schema_version=episode.schema_version,
        profile_version=episode.profile_version,
        engine_version=episode.engine_version,
        episode_payload=episode.model_dump(mode="json", by_alias=True),
    )
