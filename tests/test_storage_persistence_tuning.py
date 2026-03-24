"""Tests for Thread 2: storage / episode evaluation / tuning recommendation.

Covers:
- repository round-trip for episode_evaluation
- append-only semantics (duplicate pk raises IntegrityError)
- patch promotion history read/write
- profile version lineage
- profile version compare
- evaluation serialization round-trip
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atas_market_structure.models import (
    EpisodeEvaluation,
    EpisodeEvaluationDeclaredTimeWindow,
    EpisodeEvaluationDiagnosis,
    EpisodeEvaluationLifecycle,
    EpisodeEvaluationOutcome,
    EpisodeEvaluationScorecard,
    EpisodeEvaluationTuningHints,
    EpisodeResolution,
    EvaluationFailureMode,
    EventPhase,
    PatchValidationStatus,
    ProfilePatchCandidate,
    ProfilePatchPreview,
    ProfilePatchValidationResult,
    ProfileSuggestedChange,
    RegimeKind,
    ReviewSource,
    TradableEventKind,
)
from atas_market_structure.profile_services import InstrumentProfileService, build_instrument_profile_v1
from atas_market_structure.repository import SQLiteAnalysisRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteAnalysisRepository:
    db_path = tmp_path / "test_market_structure.db"
    r = SQLiteAnalysisRepository(db_path)
    r.initialize()
    return r


@pytest.fixture
def profile_service(repo: SQLiteAnalysisRepository) -> InstrumentProfileService:
    return InstrumentProfileService(repository=repo)


@pytest.fixture
def base_profile_v1() -> dict:
    """Minimal v1 instrument profile payload for ES, used as a dict for repository storage."""
    return build_instrument_profile_v1(
        instrument_symbol="ES",
        tick_size=0.25,
        profile_version="es-v1.0.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        is_active=True,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Episode Evaluation round-trip
# ---------------------------------------------------------------------------


def test_episode_evaluation_serialization_round_trip() -> None:
    """EpisodeEvaluation survives model_validate after model_dump."""
    evaluation = EpisodeEvaluation(
        evaluation_id="eval-test-001",
        episode_id="ep-001",
        instrument="ES",
        session="us_regular",
        bar_tf="5m",
        market_time_start=datetime(2026, 3, 20, 9, 30, tzinfo=UTC),
        market_time_end=datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
        profile_version="es-v1.0.0",
        engine_version="engine-v1",
        schema_version="episode_evaluation_v1",
        initial_regime_top1=RegimeKind.BALANCE_MEAN_REVERSION,
        initial_regime_prob=0.72,
        evaluated_event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
        initial_phase=EventPhase.BUILDING,
        initial_prob=0.42,
        declared_time_window=EpisodeEvaluationDeclaredTimeWindow(mode="next_10_bars", bars_min=5, bars_max=15),
        anchor_context=["anchor-1"],
        lifecycle=EpisodeEvaluationLifecycle(
            started_at=datetime(2026, 3, 20, 9, 30, tzinfo=UTC),
            first_validation_hit_at=datetime(2026, 3, 20, 9, 40, tzinfo=UTC),
            peak_prob=0.81,
            peak_prob_at=datetime(2026, 3, 20, 9, 45, tzinfo=UTC),
            first_invalidation_hit_at=None,
            downgraded_at=None,
            resolved_at=datetime(2026, 3, 20, 9, 55, tzinfo=UTC),
            resolution=EpisodeResolution.CONFIRMED,
            replacement_event=None,
        ),
        outcome=EpisodeEvaluationOutcome(
            did_event_materialize=True,
            did_partial_materialize=False,
            dominant_final_event=TradableEventKind.BALANCE_MEAN_REVERSION,
            judgement_source=ReviewSource.RULE_REVIEW_V1,
        ),
        scores=EpisodeEvaluationScorecard(
            hypothesis_selection_score=1,
            confirmation_timing_score=1,
            invalidation_timing_score=0,
            transition_handling_score=1,
            calibration_score=1,
        ),
        diagnosis=EpisodeEvaluationDiagnosis(
            primary_failure_mode=EvaluationFailureMode.NONE,
            supporting_reasons=["confirm_within_window", "peak_above_074"],
            missing_confirmation=[],
            invalidating_signals_seen=[],
            candidate_parameters=["thresholds.confirming_hypothesis_probability"],
            suggested_direction={},
        ),
        tuning_hints=EpisodeEvaluationTuningHints(
            candidate_parameters=[],
            suggested_direction={},
            confidence="high",
        ),
        evaluated_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
    )

    # Serialize -> Deserialize
    data = evaluation.model_dump(mode="json")
    restored = EpisodeEvaluation.model_validate(data)

    # instrument alias: the field is `instrument` but stored as `instrument` in JSON
    assert restored.evaluation_id == evaluation.evaluation_id
    assert restored.episode_id == evaluation.episode_id
    assert restored.market_time_start == evaluation.market_time_start
    assert restored.evaluated_event_kind == evaluation.evaluated_event_kind
    assert restored.initial_regime_top1 == evaluation.initial_regime_top1
    assert restored.lifecycle.resolution == evaluation.lifecycle.resolution
    assert restored.scores.calibration_score == evaluation.scores.calibration_score
    assert restored.diagnosis.primary_failure_mode == EvaluationFailureMode.NONE
    assert restored.tuning_hints.confidence == "high"


def test_episode_evaluation_repo_round_trip(
    repo: SQLiteAnalysisRepository,
) -> None:
    """EpisodeEvaluation can be saved to and loaded from the repository."""
    evaluation = EpisodeEvaluation(
        evaluation_id="eval-repo-001",
        episode_id="ep-repo-001",
        instrument="NQ",
        market_time_start=datetime(2026, 3, 21, 9, 30, tzinfo=UTC),
        market_time_end=datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
        profile_version="nq-v1.0.0",
        engine_version="engine-v1",
        schema_version="episode_evaluation_v1",
        evaluated_event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
        declared_time_window=EpisodeEvaluationDeclaredTimeWindow(mode="next_5_bars", bars_min=3, bars_max=8),
        lifecycle=EpisodeEvaluationLifecycle(
            started_at=datetime(2026, 3, 21, 9, 30, tzinfo=UTC),
            peak_prob=0.65,
            resolution=EpisodeResolution.CONFIRMED,
        ),
        outcome=EpisodeEvaluationOutcome(
            did_event_materialize=True,
            did_partial_materialize=False,
            judgement_source=ReviewSource.RULE_REVIEW_V1,
        ),
        scores=EpisodeEvaluationScorecard(
            hypothesis_selection_score=1,
            confirmation_timing_score=0,
            invalidation_timing_score=0,
            transition_handling_score=0,
            calibration_score=1,
        ),
        diagnosis=EpisodeEvaluationDiagnosis(
            primary_failure_mode=EvaluationFailureMode.NONE,
        ),
        tuning_hints=EpisodeEvaluationTuningHints(),
        evaluated_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
    )

    ingested_at = datetime(2026, 3, 21, 12, 1, tzinfo=UTC)
    repo.save_episode_evaluation(
        evaluation_id=evaluation.evaluation_id,
        episode_id=evaluation.episode_id,
        instrument_symbol="NQ",
        event_kind=evaluation.evaluated_event_kind.value,
        evaluated_at=evaluation.evaluated_at,
        schema_version=evaluation.schema_version,
        profile_version=evaluation.profile_version,
        engine_version=evaluation.engine_version,
        evaluation_payload=evaluation.model_dump(mode="json"),
    )

    loaded = repo.get_episode_evaluation(evaluation.episode_id)
    assert loaded is not None

    restored = EpisodeEvaluation.model_validate(loaded.evaluation_payload)
    assert restored.evaluation_id == evaluation.evaluation_id
    assert restored.market_time_end == evaluation.market_time_end
    assert restored.evaluated_event_kind == TradableEventKind.MOMENTUM_CONTINUATION


# ---------------------------------------------------------------------------
# Append-only semantics
# ---------------------------------------------------------------------------


def test_episode_evaluation_append_only_raises_on_duplicate_pk(
    repo: SQLiteAnalysisRepository,
) -> None:
    """Saving the same evaluation_id twice raises sqlite3.IntegrityError."""
    ingested_at = datetime(2026, 3, 22, tzinfo=UTC)
    payload = EpisodeEvaluation(
        evaluation_id="eval-dup-001",
        episode_id="ep-dup-001",
        instrument="ES",
        market_time_start=datetime(2026, 3, 22, 9, 30, tzinfo=UTC),
        market_time_end=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        profile_version="es-v1.0.0",
        engine_version="engine-v1",
        schema_version="episode_evaluation_v1",
        evaluated_event_kind=TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
        declared_time_window=EpisodeEvaluationDeclaredTimeWindow(mode="next_20_bars"),
        lifecycle=EpisodeEvaluationLifecycle(
            started_at=datetime(2026, 3, 22, 9, 30, tzinfo=UTC),
            peak_prob=0.5,
            resolution=EpisodeResolution.INVALIDATED,
        ),
        outcome=EpisodeEvaluationOutcome(
            did_event_materialize=False,
            did_partial_materialize=False,
            judgement_source=ReviewSource.RULE_REVIEW_V1,
        ),
        scores=EpisodeEvaluationScorecard(
            hypothesis_selection_score=-1,
            confirmation_timing_score=0,
            invalidation_timing_score=0,
            transition_handling_score=0,
            calibration_score=-1,
        ),
        diagnosis=EpisodeEvaluationDiagnosis(
            primary_failure_mode=EvaluationFailureMode.FALSE_POSITIVE,
        ),
        tuning_hints=EpisodeEvaluationTuningHints(),
        evaluated_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
    )

    repo.save_episode_evaluation(
        evaluation_id=payload.evaluation_id,
        episode_id=payload.episode_id,
        instrument_symbol="ES",
        event_kind=payload.evaluated_event_kind.value,
        evaluated_at=payload.evaluated_at,
        schema_version=payload.schema_version,
        profile_version=payload.profile_version,
        engine_version=payload.engine_version,
        evaluation_payload=payload.model_dump(mode="json"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.save_episode_evaluation(
            evaluation_id=payload.evaluation_id,
            episode_id=payload.episode_id,
            instrument_symbol="ES",
            event_kind=payload.evaluated_event_kind.value,
            evaluated_at=payload.evaluated_at,
            schema_version=payload.schema_version,
            profile_version=payload.profile_version,
            engine_version=payload.engine_version,
            evaluation_payload=payload.model_dump(mode="json"),
        )


# ---------------------------------------------------------------------------
# Patch Promotion History
# ---------------------------------------------------------------------------


def test_patch_promotion_history_save_and_retrieve(
    repo: SQLiteAnalysisRepository,
) -> None:
    """Patch promotion history can be saved and retrieved by promotion_id."""
    promoted_at = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)

    repo.save_patch_promotion_history(
        promotion_id="promo-001",
        candidate_id="cand-001",
        instrument_symbol="ES",
        promoted_profile_version="es-v1.1.0",
        previous_profile_version="es-v1.0.0",
        promoted_at=promoted_at,
        promoted_by="operator_chen",
        promotion_notes="Promoted after manual review of tuning recommendation.",
        detail={"recommendation_id": "rec-001", "evaluation_count": 12},
    )

    loaded = repo.get_patch_promotion("promo-001")
    assert loaded is not None
    assert loaded.promotion_id == "promo-001"
    assert loaded.candidate_id == "cand-001"
    assert loaded.instrument_symbol == "ES"
    assert loaded.promoted_profile_version == "es-v1.1.0"
    assert loaded.previous_profile_version == "es-v1.0.0"
    assert loaded.promoted_by == "operator_chen"
    assert loaded.detail["evaluation_count"] == 12


def test_patch_promotion_history_append_only(
    repo: SQLiteAnalysisRepository,
) -> None:
    """Duplicate promotion_id raises IntegrityError."""
    promoted_at = datetime(2026, 3, 23, 11, 0, tzinfo=UTC)

    repo.save_patch_promotion_history(
        promotion_id="promo-dup-001",
        candidate_id="cand-dup-001",
        instrument_symbol="NQ",
        promoted_profile_version="nq-v1.1.0",
        previous_profile_version="nq-v1.0.0",
        promoted_at=promoted_at,
        promoted_by="operator_wang",
        promotion_notes="",
        detail={},
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.save_patch_promotion_history(
            promotion_id="promo-dup-001",
            candidate_id="cand-dup-001",
            instrument_symbol="NQ",
            promoted_profile_version="nq-v1.1.0",
            previous_profile_version="nq-v1.0.0",
            promoted_at=promoted_at,
            promoted_by="operator_wang",
            promotion_notes="",
            detail={},
        )


def test_patch_promotion_list_filtered(
    repo: SQLiteAnalysisRepository,
) -> None:
    """list_patch_promotions supports filtering by candidate_id and instrument_symbol."""
    t1 = datetime(2026, 3, 23, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 23, 10, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 23, 11, 0, tzinfo=UTC)

    repo.save_patch_promotion_history(
        promotion_id="promo-ls-001",
        candidate_id="cand-A",
        instrument_symbol="ES",
        promoted_profile_version="es-v1.1.0",
        previous_profile_version="es-v1.0.0",
        promoted_at=t1,
        promoted_by="op1",
        promotion_notes="",
        detail={},
    )
    repo.save_patch_promotion_history(
        promotion_id="promo-ls-002",
        candidate_id="cand-A",
        instrument_symbol="ES",
        promoted_profile_version="es-v1.2.0",
        previous_profile_version="es-v1.1.0",
        promoted_at=t2,
        promoted_by="op2",
        promotion_notes="",
        detail={},
    )
    repo.save_patch_promotion_history(
        promotion_id="promo-ls-003",
        candidate_id="cand-B",
        instrument_symbol="NQ",
        promoted_profile_version="nq-v1.1.0",
        previous_profile_version="nq-v1.0.0",
        promoted_at=t3,
        promoted_by="op3",
        promotion_notes="",
        detail={},
    )

    # Filter by candidate
    rows_cand_a = repo.list_patch_promotions(candidate_id="cand-A")
    assert len(rows_cand_a) == 2
    assert all(r.candidate_id == "cand-A" for r in rows_cand_a)

    # Filter by instrument
    rows_es = repo.list_patch_promotions(instrument_symbol="ES")
    assert len(rows_es) == 2
    assert all(r.instrument_symbol == "ES" for r in rows_es)

    # Combined filter
    rows_combined = repo.list_patch_promotions(candidate_id="cand-B", instrument_symbol="NQ")
    assert len(rows_combined) == 1
    assert rows_combined[0].promotion_id == "promo-ls-003"


# ---------------------------------------------------------------------------
# Profile Version Lineage
# ---------------------------------------------------------------------------


def test_instrument_profile_version_save_and_retrieve(
    repo: SQLiteAnalysisRepository,
    base_profile_v1: dict,
) -> None:
    """Saved profile versions can be retrieved individually."""
    now = datetime(2026, 3, 20, tzinfo=UTC)

    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.0.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=True,
        profile_payload=base_profile_v1,
        created_at=now,
    )

    loaded = repo.get_instrument_profile_version("ES", "es-v1.0.0")
    assert loaded is not None
    assert loaded.profile_version == "es-v1.0.0"
    assert loaded.is_active is True
    assert loaded.profile_payload["instrument_symbol"] == "ES"


def test_instrument_profile_version_not_found(
    repo: SQLiteAnalysisRepository,
) -> None:
    """get_instrument_profile_version returns None for unknown version."""
    result = repo.get_instrument_profile_version("ES", "es-unknown-99.0.0")
    assert result is None


def test_instrument_profile_version_lineage(
    repo: SQLiteAnalysisRepository,
    base_profile_v1: dict,
) -> None:
    """list_instrument_profile_versions returns all versions in creation order."""
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 2, 1, tzinfo=UTC)

    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.0.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=False,
        profile_payload=base_profile_v1,
        created_at=t1,
    )

    payload_v2 = {**base_profile_v1, "profile_version": "es-v1.1.0"}
    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.1.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=True,
        profile_payload=payload_v2,
        created_at=t2,
    )

    versions = repo.list_instrument_profile_versions("ES")
    assert len(versions) == 2
    version_map = {v.profile_version: v for v in versions}
    assert version_map["es-v1.0.0"].is_active is False
    assert version_map["es-v1.1.0"].is_active is True


# ---------------------------------------------------------------------------
# Profile Version Compare
# ---------------------------------------------------------------------------


def test_compare_profile_versions_success(
    profile_service: InstrumentProfileService,
    repo: SQLiteAnalysisRepository,
    base_profile_v1: dict,
) -> None:
    """compare_profile_versions returns a valid ProfilePatchPreview."""
    now = datetime(2026, 3, 20, tzinfo=UTC)

    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.0.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=True,
        profile_payload=base_profile_v1,
        created_at=now,
    )

    # Save proposed version with a simple threshold change patch
    proposed_payload = {
        **base_profile_v1,
        "profile_version": "es-v1.1.0",
        "thresholds": {
            **base_profile_v1.get("thresholds", {}),
            "confirming_hypothesis_probability": 0.65,
        },
    }
    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.1.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=False,
        profile_payload=proposed_payload,
        created_at=now,
    )

    # Compare uses deep_merge of base+proposed as the patch input
    patch = {**proposed_payload}
    preview = profile_service.compare_profile_versions(
        instrument_symbol="ES",
        base_version="es-v1.0.0",
        proposed_version="es-v1.1.0",
    )

    assert isinstance(preview, ProfilePatchPreview)
    assert preview.base_profile_version == "es-v1.0.0"
    assert preview.proposed_profile_version == "es-v1.1.0"
    assert preview.instrument_symbol == "ES"
    assert preview.requires_human_review is True
    assert preview.allow_ai_auto_apply is False


def test_compare_profile_versions_unknown_base(
    profile_service: InstrumentProfileService,
) -> None:
    """compare_profile_versions raises ValueError when base version not found."""
    with pytest.raises(ValueError, match="base profile version not found"):
        profile_service.compare_profile_versions(
            instrument_symbol="ES",
            base_version="es-nonexistent",
            proposed_version="es-v1.1.0",
        )


def test_compare_profile_versions_unknown_proposed(
    profile_service: InstrumentProfileService,
    repo: SQLiteAnalysisRepository,
    base_profile_v1: dict,
) -> None:
    """compare_profile_versions raises ValueError when proposed version not found."""
    now = datetime(2026, 3, 20, tzinfo=UTC)
    repo.save_instrument_profile(
        instrument_symbol="ES",
        profile_version="es-v1.0.0",
        schema_version="instrument_profile_v1",
        ontology_version="v1",
        is_active=True,
        profile_payload=base_profile_v1,
        created_at=now,
    )

    with pytest.raises(ValueError, match="proposed profile version not found"):
        profile_service.compare_profile_versions(
            instrument_symbol="ES",
            base_version="es-v1.0.0",
            proposed_version="es-nonexistent",
        )


# ---------------------------------------------------------------------------
# Tuning Recommendation round-trip
# ---------------------------------------------------------------------------


def test_tuning_recommendation_serialization_round_trip() -> None:
    """TuningRecommendation survives model_validate after model_dump."""
    from atas_market_structure.models import TuningAnalysisWindow, TuningRecommendation, TuningRecommendationItem

    recommendation = TuningRecommendation(
        recommendation_id="rec-001",
        bundle_id="bundle-001",
        instrument="ES",
        schema_version="tuning_recommendation_v1",
        profile_version="es-v1.0.0",
        engine_version="engine-v1",
        generated_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
        advisor_kind="offline_stub_v1",
        analysis_window=TuningAnalysisWindow(
            episode_count=10,
            evaluation_count=8,
            date_from=datetime(2026, 3, 1, tzinfo=UTC),
            date_to=datetime(2026, 3, 20, tzinfo=UTC),
        ),
        top_failure_modes=[],
        recommendations=[
            TuningRecommendationItem(
                event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
                parameter="thresholds.confirming_hypothesis_probability",
                direction="increase",
                current_value=0.56,
                proposed_value=0.62,
                support_count=5,
                reason="late_confirmation_pattern",
                expected_improvement="Earlier confirmation signal",
                risk="May trigger on noise",
                confidence="medium",
            ),
        ],
        expected_improvement="Reduce late confirmation latency",
        risk="Possible increase in false positives",
        confidence="medium",
    )

    data = recommendation.model_dump(mode="json")
    restored = TuningRecommendation.model_validate(data)

    assert restored.recommendation_id == recommendation.recommendation_id
    assert restored.profile_version == "es-v1.0.0"
    assert len(restored.recommendations) == 1
    assert restored.recommendations[0].direction == "increase"
    assert restored.allow_ai_auto_apply is False


# ---------------------------------------------------------------------------
# Profile Patch Candidate round-trip
# ---------------------------------------------------------------------------


def test_profile_patch_candidate_repo_round_trip(
    repo: SQLiteAnalysisRepository,
) -> None:
    """ProfilePatchCandidate can be saved and retrieved from repository."""
    from uuid import uuid4

    candidate_id = f"cand-test-{uuid4().hex[:8]}"
    now = datetime(2026, 3, 20, tzinfo=UTC)

    candidate = ProfilePatchCandidate(
        candidate_id=candidate_id,
        instrument="ES",
        schema_version="profile_patch_candidate_v1",
        ontology_version="v1",
        base_profile_version="es-v1.0.0",
        proposed_profile_version="es-v1.1.0",
        candidate_parameters=["thresholds.confirming_hypothesis_probability"],
        suggested_changes={
            "thresholds.confirming_hypothesis_probability": ProfileSuggestedChange(
                action="increase",
                **{"from": 0.56, "to": 0.62},
            ),
        },
        created_at=now,
    )

    repo.save_profile_patch_candidate(
        candidate_id=candidate.candidate_id,
        instrument_symbol=candidate.instrument_symbol,
        market_time=now,
        ingested_at=now,
        schema_version=candidate.schema_version,
        base_profile_version=candidate.base_profile_version,
        proposed_profile_version=candidate.proposed_profile_version,
        recommendation_id=None,
        status="candidate_created",
        patch_payload=candidate.model_dump(mode="json"),
    )

    rows = repo.list_profile_patch_candidates(instrument_symbol="ES", limit=10)
    assert len(rows) >= 1
    found = next((r for r in rows if r.candidate_id == candidate_id), None)
    assert found is not None

    restored = ProfilePatchCandidate.model_validate(found.patch_payload)
    assert restored.candidate_id == candidate_id
    assert restored.base_profile_version == "es-v1.0.0"
    assert restored.proposed_profile_version == "es-v1.1.0"
    assert len(restored.suggested_changes) == 1
