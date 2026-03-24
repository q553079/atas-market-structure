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
    EventEpisode,
    EventHypothesisStateContract,
    FeatureSliceContract,
    RecognizerBuild,
    RegimePosteriorContract,
    TuningRecommendation,
)
from atas_market_structure.models._schema_versions import (
    BELIEF_STATE_SCHEMA_VERSION,
    CORE_CANONICAL_SCHEMA_VERSIONS,
    EPISODE_EVALUATION_SCHEMA_VERSION,
    EVENT_EPISODE_SCHEMA_VERSION,
    EVENT_HYPOTHESIS_STATE_SCHEMA_VERSION,
    FEATURE_SLICE_SCHEMA_VERSION,
    INSTRUMENT_PROFILE_SCHEMA_VERSION,
    RECOGNIZER_BUILD_SCHEMA_VERSION,
    REGIME_POSTERIOR_SCHEMA_VERSION,
    TUNING_RECOMMENDATION_SCHEMA_VERSION,
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
