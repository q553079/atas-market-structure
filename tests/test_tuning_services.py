from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.models import (
    BeliefDataStatus,
    BeliefStateSnapshot,
    DegradedMode,
    EpisodeResolution,
    EventEpisode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    InstrumentProfile,
    MemoryAnchorSnapshot,
    RecognitionMode,
    RegimeKind,
    RegimePosteriorRecord,
    ProfilePatchCandidate,
    ProfilePatchValidationResult,
    TuningInputBundle,
    TuningRecommendation,
    TradableEventKind,
)
from atas_market_structure.profile_services import InstrumentProfileService, build_instrument_profile_v1, default_tick_size_for_symbol
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.tuning_services import (
    TUNING_INPUT_BUNDLE_SCHEMA_VERSION,
    TUNING_RECOMMENDATION_SCHEMA_VERSION,
    TuningAdvisorService,
)


ROOT = Path(__file__).resolve().parents[1]


def test_tuning_bundle_builder_collects_profile_evaluations_patch_history_and_degradation(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    service = TuningAdvisorService(repository=repository)

    bundle = service.build_bundle_for_instrument("NQ")

    assert bundle.schema_version == TUNING_INPUT_BUNDLE_SCHEMA_VERSION
    assert bundle.profile_version == "nq-profile-test"
    assert bundle.engine_version == "recognizer-test"
    assert bundle.analysis_window.episode_count == 2
    assert bundle.analysis_window.evaluation_count == 2
    assert bundle.positive_negative_summary.positive_episode_count == 1
    assert bundle.positive_negative_summary.negative_episode_count == 1
    assert bundle.positive_negative_summary.failure_mode_counts["early_confirmation"] == 1
    assert bundle.patch_history
    assert bundle.degradation_statistics is not None
    assert bundle.degradation_statistics.degraded_mode_counts["degraded_no_depth"] >= 1
    assert bundle.degradation_statistics.ai_unavailable_count >= 1


def test_tuning_advisor_generates_structured_recommendation_and_validation_scaffold(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    service = TuningAdvisorService(repository=repository)

    advisory = service.recommend_for_instrument("NQ", persist=False)

    assert advisory.recommendation.schema_version == TUNING_RECOMMENDATION_SCHEMA_VERSION
    assert advisory.recommendation.allow_ai_auto_apply is False
    assert advisory.recommendation.top_failure_modes
    assert advisory.recommendation.top_failure_modes[0].kind.value == "early_confirmation"
    assert advisory.patch_candidate is not None
    assert advisory.validation_result is not None
    assert any(
        item.parameter == "thresholds.confirming_hypothesis_probability"
        for item in advisory.recommendation.recommendations
    )
    assert advisory.patch_candidate.allow_ai_auto_apply is False
    assert advisory.validation_result.schema_version == "patch_validation_result_v1"
    assert advisory.validation_result.offline_replay_validation.status == "not_run"
    assert advisory.validation_result.human_approval.status == "pending"
    assert advisory.validation_result.promotion_ready is False


def test_tuning_advisor_persists_recommendation_candidate_and_validation(tmp_path: Path) -> None:
    repository = _seed_repository(tmp_path)
    service = TuningAdvisorService(repository=repository)

    advisory = service.recommend_for_instrument("NQ", persist=True)

    recommendation_rows = repository.list_tuning_recommendations(instrument_symbol="NQ", limit=10)
    candidate_rows = repository.list_profile_patch_candidates(instrument_symbol="NQ", limit=10)
    validation_rows = repository.list_patch_validation_results(
        candidate_id=advisory.patch_candidate.candidate_id,
        limit=10,
    )

    assert recommendation_rows
    assert recommendation_rows[0].schema_version == TUNING_RECOMMENDATION_SCHEMA_VERSION
    assert recommendation_rows[0].recommendation_payload["bundle_id"] == advisory.bundle.bundle_id
    assert candidate_rows
    assert any(row.candidate_id == advisory.patch_candidate.candidate_id for row in candidate_rows)
    assert validation_rows
    assert validation_rows[0].validation_payload["human_approval"]["status"] == "pending"


def test_tuning_samples_load_against_contracts() -> None:
    bundle = TuningInputBundle.model_validate(
        json.loads((ROOT / "samples" / "tuning" / "tuning_input_bundle.sample.json").read_text(encoding="utf-8"))
    )
    recommendation = TuningRecommendation.model_validate(
        json.loads((ROOT / "samples" / "tuning" / "tuning_recommendation.sample.json").read_text(encoding="utf-8"))
    )
    candidate = ProfilePatchCandidate.model_validate(
        json.loads((ROOT / "samples" / "tuning" / "profile_patch_candidate.sample.json").read_text(encoding="utf-8"))
    )
    validation = ProfilePatchValidationResult.model_validate(
        json.loads((ROOT / "samples" / "tuning" / "patch_validation_result.sample.json").read_text(encoding="utf-8"))
    )

    assert bundle.schema_version == TUNING_INPUT_BUNDLE_SCHEMA_VERSION
    assert recommendation.schema_version == TUNING_RECOMMENDATION_SCHEMA_VERSION
    assert candidate.schema_version == "profile_patch_candidate_v1"
    assert validation.schema_version == "patch_validation_result_v1"


def _seed_repository(tmp_path: Path) -> SQLiteAnalysisRepository:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()

    profile = _profile("NQ")
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
        engine_version="recognizer-test",
        schema_version="recognizer_build_v1",
        ontology_version=profile.ontology_version,
        is_active=True,
        status="active",
        build_payload={"notes": ["test recognizer build"]},
        created_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )

    evaluation_service = EpisodeEvaluationService(repository=repository)

    early_base = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    early_beliefs = [
        _belief(
            "b0-early",
            early_base,
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.62)],
            data_status=_data_status(depth_available=False, degraded_modes=[DegradedMode.NO_DEPTH, DegradedMode.NO_AI]),
        ),
        _belief(
            "b1-early",
            early_base + timedelta(minutes=1),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.77)],
        ),
    ]
    early_episode = _episode(
        event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        resolution=EpisodeResolution.CONFIRMED,
        started_at=early_base,
        ended_at=early_base + timedelta(minutes=1),
    )
    _persist_episode_and_beliefs(repository, early_episode, early_beliefs)
    evaluation_service.evaluate_episode(
        episode=early_episode,
        beliefs=early_beliefs,
        profile=profile,
        persist=True,
    )

    healthy_base = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)
    healthy_beliefs = [
        _belief(
            "b0-ok",
            healthy_base,
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.EMERGING, 0.31)],
        ),
        _belief(
            "b1-ok",
            healthy_base + timedelta(minutes=1),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.BUILDING, 0.44)],
        ),
        _belief(
            "b2-ok",
            healthy_base + timedelta(minutes=2),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.60)],
        ),
        _belief(
            "b3-ok",
            healthy_base + timedelta(minutes=3),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.76)],
        ),
    ]
    healthy_episode = _episode(
        event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        resolution=EpisodeResolution.CONFIRMED,
        started_at=healthy_base,
        ended_at=healthy_base + timedelta(minutes=3),
    )
    _persist_episode_and_beliefs(repository, healthy_episode, healthy_beliefs)
    evaluation_service.evaluate_episode(
        episode=healthy_episode,
        beliefs=healthy_beliefs,
        profile=profile,
        persist=True,
    )

    InstrumentProfileService(repository=repository).validate_patch(
        base_profile=profile,
        patch={"weights": {"depth_dom": 0.8}},
        persist=True,
    )
    return repository


def _persist_episode_and_beliefs(
    repository: SQLiteAnalysisRepository,
    episode: EventEpisode,
    beliefs: list[BeliefStateSnapshot],
) -> None:
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
    for belief in beliefs:
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


def _profile(symbol: str) -> InstrumentProfile:
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
) -> EventEpisode:
    return EventEpisode(
        episode_id=f"ep-{event_kind.value}-{started_at.strftime('%H%M')}",
        instrument_symbol="NQ",
        event_kind=event_kind,
        hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
        phase=EventPhase.RESOLVED if resolution is EpisodeResolution.CONFIRMED else EventPhase.INVALIDATED,
        resolution=resolution,
        started_at=started_at,
        ended_at=ended_at,
        peak_probability=0.78 if resolution is EpisodeResolution.CONFIRMED else 0.22,
        dominant_regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
        supporting_evidence=["support_a", "support_b"],
        invalidating_evidence=[],
        key_evidence_summary=["support_a", "support_b"],
        active_anchor_ids=["anc-balance"],
        replacement_episode_id=None,
        replacement_event_kind=None,
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
    data_status: BeliefDataStatus | None = None,
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
        data_status=data_status or _data_status(),
        regime_posteriors=[
            RegimePosteriorRecord(
                regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
                probability=0.44,
                evidence=["trend_efficiency"],
            ),
        ],
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
        missing_confirmation=[],
        invalidating_signals_seen=[],
        transition_watch=[],
        notes=[],
    )


def _state(
    hypothesis_kind: EventHypothesisKind,
    event_kind: TradableEventKind,
    phase: EventPhase,
    probability: float,
) -> EventHypothesisState:
    return EventHypothesisState(
        hypothesis_id=f"hyp-{hypothesis_kind.value}-{phase.value}-{int(probability * 100)}",
        hypothesis_kind=hypothesis_kind,
        mapped_event_kind=event_kind,
        phase=phase,
        posterior_probability=probability,
        supporting_evidence=["support"],
        missing_confirmation=[],
        invalidating_signals=[],
        transition_watch=[],
        data_quality_score=1.0,
        evidence_density_score=0.7,
        model_stability_score=0.8,
        anchor_dependence_score=0.5,
    )


def _data_status(
    *,
    depth_available: bool = True,
    dom_available: bool = True,
    ai_available: bool = False,
    degraded_modes: list[DegradedMode] | None = None,
) -> BeliefDataStatus:
    return BeliefDataStatus(
        data_freshness_ms=0,
        feature_completeness=0.85 if degraded_modes else 1.0,
        depth_available=depth_available,
        dom_available=dom_available,
        ai_available=ai_available,
        degraded_modes=list(degraded_modes or []),
        freshness="fresh",
        completeness="partial" if degraded_modes else "complete",
    )
