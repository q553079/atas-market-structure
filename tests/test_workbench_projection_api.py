from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.app import MarketStructureApplication
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
    MemoryAnchorSnapshot,
    RecognitionMode,
    RegimeKind,
    RegimePosteriorRecord,
    TradableEventKind,
)
from atas_market_structure.profile_services import (
    build_instrument_profile_v1,
    default_tick_size_for_symbol,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.tuning_services import TuningAdvisorService


def test_workbench_projection_api_returns_combined_projection(tmp_path: Path) -> None:
    application = _build_seeded_application(tmp_path)

    response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/projection"
        "?instrument_symbol=NQ"
        "&window_start=2026-03-23T09:29:00+00:00"
        "&window_end=2026-03-23T10:05:00+00:00"
        "&limit=20",
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["query"]["instrument_symbol"] == "NQ"
    assert payload["belief_timeline"]["current_belief"]["belief_state_id"] == "b3-ok"
    assert payload["episode_reviews"]["items"]
    assert payload["episode_evaluations"]["items"]
    assert payload["tuning_reviews"]["items"]
    entry_types = {item["entry_type"] for item in payload["timeline"]}
    assert "belief_state" in entry_types
    assert "event_episode" in entry_types
    assert "episode_evaluation" in entry_types
    assert "tuning_recommendation" in entry_types
    assert payload["metadata"]["active_profile"]["profile_version"] == "nq-profile-test"
    assert payload["metadata"]["active_build"]["engine_version"] == "recognizer-test"


def test_workbench_projection_api_supports_episode_and_evaluation_filters(tmp_path: Path) -> None:
    application = _build_seeded_application(tmp_path)

    episode_response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/event-episodes"
        "?instrument_symbol=NQ"
        "&session_date=2026-03-23"
        "&window_start=2026-03-23T09:29:00+00:00"
        "&window_end=2026-03-23T10:05:00+00:00",
    )
    evaluation_response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/episode-evaluations"
        "?instrument_symbol=NQ"
        "&session_date=2026-03-23"
        "&window_start=2026-03-23T09:29:00+00:00"
        "&window_end=2026-03-23T10:05:00+00:00",
    )

    assert episode_response.status_code == 200
    assert evaluation_response.status_code == 200

    episode_payload = json.loads(episode_response.body)
    evaluation_payload = json.loads(evaluation_response.body)

    assert episode_payload["items"][0]["episode"]["event_kind"] == "momentum_continuation"
    assert episode_payload["items"][0]["evaluation"] is not None
    assert episode_payload["items"][0]["primary_failure_mode"] in {"none", "early_confirmation"}

    assert evaluation_payload["items"]
    assert evaluation_payload["items"][0]["evaluation"]["evaluation_id"].startswith("eval-")
    assert isinstance(evaluation_payload["items"][0]["candidate_parameters"], list)


def test_workbench_projection_api_returns_tuning_metadata_and_health_views(tmp_path: Path) -> None:
    application = _build_seeded_application(tmp_path)

    tuning_response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/tuning-recommendations"
        "?instrument_symbol=NQ"
        "&window_start=2026-03-23T09:29:00+00:00"
        "&window_end=2026-03-23T10:30:00+00:00",
    )
    metadata_response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/profile-engine?instrument_symbol=NQ",
    )
    health_response = application.dispatch(
        "GET",
        "/api/v1/workbench/review/health-status?instrument_symbol=NQ",
    )
    js_response = application.dispatch("GET", "/static/replay_workbench_bootstrap.js")
    loader_js_response = application.dispatch("GET", "/static/replay_workbench_replay_loader.js")

    assert tuning_response.status_code == 200
    assert metadata_response.status_code == 200
    assert health_response.status_code == 200
    assert js_response.status_code == 200
    assert loader_js_response.status_code == 200

    tuning_payload = json.loads(tuning_response.body)
    metadata_payload = json.loads(metadata_response.body)
    health_payload = json.loads(health_response.body)

    assert tuning_payload["items"][0]["recommendation"]["allow_ai_auto_apply"] is False
    assert tuning_payload["items"][0]["patch_candidate"] is not None
    assert tuning_payload["items"][0]["latest_validation_result"] is not None

    assert metadata_payload["active_profile"]["profile_version"] == "nq-profile-test"
    assert metadata_payload["active_build"]["engine_version"] == "recognizer-test"
    assert metadata_payload["latest_patch_candidate"] is not None
    assert metadata_payload["latest_patch_validation_result"] is not None

    assert health_payload["health"]["profile_version"] == "nq-profile-test"
    assert health_payload["health"]["engine_version"] == "recognizer-test"
    assert health_payload["data_quality"]["data_status"]["completeness"] is not None
    assert b"/api/v1/workbench/review/projection" in loader_js_response.body
    assert b"Belief State" in js_response.body


def _build_seeded_application(tmp_path: Path) -> MarketStructureApplication:
    repository = SQLiteAnalysisRepository(tmp_path / "projection.db")
    repository.initialize()
    _seed_repository(repository)
    return MarketStructureApplication(repository=repository)


def _seed_repository(repository: SQLiteAnalysisRepository) -> None:
    profile = build_instrument_profile_v1(
        "NQ",
        tick_size=default_tick_size_for_symbol("NQ"),
        profile_version="nq-profile-test",
        schema_version="1.0.0",
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
    )
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
        build_payload={"notes": ["projection test recognizer"]},
        created_at=datetime(2026, 3, 23, 8, 15, tzinfo=UTC),
    )

    evaluation_service = EpisodeEvaluationService(repository=repository)

    early_base = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    early_beliefs = [
        _belief(
            "b0-early",
            early_base,
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.62)],
            data_status=_data_status(degraded_modes=[DegradedMode.NO_DEPTH, DegradedMode.NO_AI], depth_available=False, ai_available=False),
        ),
        _belief(
            "b1-early",
            early_base + timedelta(minutes=1),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.78)],
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
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.EMERGING, 0.33)],
        ),
        _belief(
            "b1-ok",
            healthy_base + timedelta(minutes=1),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.BUILDING, 0.47)],
        ),
        _belief(
            "b2-ok",
            healthy_base + timedelta(minutes=2),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.CONFIRMING, 0.63)],
        ),
        _belief(
            "b3-ok",
            healthy_base + timedelta(minutes=3),
            [_state(EventHypothesisKind.CONTINUATION_BASE, TradableEventKind.MOMENTUM_CONTINUATION, EventPhase.RESOLVED, 0.80)],
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

    TuningAdvisorService(repository=repository).recommend_for_instrument("NQ", persist=True)


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
        peak_probability=0.8 if resolution is EpisodeResolution.CONFIRMED else 0.25,
        dominant_regime=RegimeKind.WEAK_MOMENTUM_TREND_NARROW,
        supporting_evidence=["trend_efficiency", "initiative_push"],
        invalidating_evidence=[],
        key_evidence_summary=["trend_efficiency", "initiative_push"],
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
                probability=0.46,
                evidence=["trend_efficiency"],
            ),
            RegimePosteriorRecord(
                regime=RegimeKind.BALANCE_MEAN_REVERSION,
                probability=0.25,
                evidence=["balance"],
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
        transition_watch=["absorption_to_reversal_preparation"],
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
        supporting_evidence=["trend_efficiency", "initiative_push"],
        missing_confirmation=[],
        invalidating_signals=[],
        transition_watch=["balance_mean_reversion"],
        data_quality_score=1.0,
        evidence_density_score=0.75,
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
