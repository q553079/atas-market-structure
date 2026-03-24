from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.models import (
    BeliefStateSnapshot,
    EventHypothesisStateContract,
    FeatureSliceContract,
    RegimePosteriorContract,
)
from atas_market_structure.models._schema_versions import (
    BELIEF_STATE_SCHEMA_VERSION,
    EPISODE_EVALUATION_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
    TUNING_RECOMMENDATION_SCHEMA_VERSION,
)
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.tuning_services import TuningAdvisorService
from tests.contract_support import (
    build_test_belief,
    build_test_episode,
    build_test_profile,
    persist_belief,
    persist_episode,
    persist_profile_build,
)
from tests.test_integration_chain import _continuous_payload, _history_bars_payload, _process_context_payload


def test_ingestion_to_recognition_persists_frozen_append_only_contracts(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    observed_at = datetime(2026, 3, 23, 9, 30, tzinfo=UTC).replace(microsecond=0)

    repository.save_ingestion(
        ingestion_id="ing-hist-momo",
        ingestion_kind="adapter_history_bars",
        source_snapshot_id="hist-momo",
        instrument_symbol="NQ",
        observed_payload=_history_bars_payload(
            symbol="NQ",
            start=observed_at - timedelta(minutes=6),
            bars=[
                (21490.0, 21493.0, 21489.75, 21492.75, 240, 95),
                (21492.75, 21496.0, 21492.5, 21495.75, 260, 112),
                (21495.75, 21499.0, 21495.5, 21498.75, 270, 118),
                (21498.75, 21502.0, 21498.5, 21501.75, 285, 124),
                (21501.75, 21505.0, 21501.5, 21504.75, 300, 138),
                (21504.75, 21508.0, 21504.5, 21507.75, 320, 150),
            ],
            emitted_at=observed_at,
        ),
        stored_at=observed_at,
    )
    repository.save_ingestion(
        ingestion_id="ing-proc-momo",
        ingestion_kind="process_context",
        source_snapshot_id="proc-momo",
        instrument_symbol="NQ",
        observed_payload=_process_context_payload(
            symbol="NQ",
            observed_at=observed_at,
            point_of_control=21484.0,
            initiative_side="buy",
            zone_low=21487.0,
            zone_high=21488.5,
        ),
        stored_at=observed_at,
    )
    repository.save_ingestion(
        ingestion_id="ing-cont-momo",
        ingestion_kind="adapter_continuous_state",
        source_snapshot_id="msg-momo",
        instrument_symbol="NQ",
        observed_payload=_continuous_payload(
            symbol="NQ",
            observed_at=observed_at,
            last_price=21518.25,
            local_low=21505.0,
            local_high=21518.25,
            net_delta=820,
            volume=1400,
            side="buy",
            drive_low=21505.0,
            drive_high=21518.25,
        ),
        stored_at=observed_at,
    )

    result = DeterministicRecognitionService(repository=repository, ai_available=False).run_for_instrument(
        "NQ",
        triggered_by="pytest_contract_flow",
    )

    assert result.triggered is True
    assert result.belief_state is not None
    assert result.belief_state.schema_version == BELIEF_STATE_SCHEMA_VERSION

    feature_row = repository.list_feature_slices(instrument_symbol="NQ", limit=1)[0]
    posterior_row = repository.list_regime_posteriors(instrument_symbol="NQ", limit=1)[0]
    hypothesis_row = repository.list_event_hypothesis_states(instrument_symbol="NQ", limit=1)[0]
    latest_belief_row = repository.get_latest_belief_state("NQ")

    feature = FeatureSliceContract.model_validate(asdict(feature_row))
    posterior = RegimePosteriorContract.model_validate(asdict(posterior_row))
    hypothesis = EventHypothesisStateContract.model_validate(asdict(hypothesis_row))
    belief = BeliefStateSnapshot.model_validate(latest_belief_row.belief_payload)

    assert feature.schema_version == FEATURE_SLICE_SCHEMA_VERSION
    assert posterior.schema_version == REGIME_POSTERIOR_SCHEMA_VERSION
    assert hypothesis.hypothesis_payload.mapped_event_kind == belief.event_hypotheses[0].mapped_event_kind
    assert belief.schema_version == BELIEF_STATE_SCHEMA_VERSION


def test_episode_evaluation_to_tuning_recommendation_stays_on_frozen_contracts(tmp_path: Path) -> None:
    repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
    repository.initialize()
    persist_profile_build(repository)

    base = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    beliefs = [
        build_test_belief(belief_id="b0", observed_at=base, phase="confirming", probability=0.62),
        build_test_belief(belief_id="b1", observed_at=base + timedelta(minutes=1), phase="resolved", probability=0.77),
    ]
    for belief in beliefs:
        persist_belief(repository, belief)

    episode = build_test_episode(
        started_at=base,
        ended_at=base + timedelta(minutes=1),
        resolution="confirmed",
        data_status=beliefs[-1].data_status,
    )
    persist_episode(repository, episode)

    evaluation = EpisodeEvaluationService(repository=repository).evaluate_episode(
        episode=episode,
        beliefs=beliefs,
        profile=build_test_profile(),
        persist=True,
    )
    advisory = TuningAdvisorService(repository=repository).recommend_for_instrument("NQ", persist=False)

    assert evaluation.schema_version == EPISODE_EVALUATION_SCHEMA_VERSION
    assert advisory.bundle.episode_evaluations[0].schema_version == EPISODE_EVALUATION_SCHEMA_VERSION
    assert advisory.recommendation.schema_version == TUNING_RECOMMENDATION_SCHEMA_VERSION
    assert advisory.recommendation.top_failure_modes
    assert advisory.recommendation.recommendations
