from __future__ import annotations

from datetime import datetime
from typing import Protocol

from atas_market_structure.repository_records import (
    StoredInstrumentProfile,
    StoredPatchPromotionHistoryRecord,
    StoredPatchValidationResultRecord,
    StoredProfilePatchCandidateRecord,
    StoredTuningRecommendationRecord,
)


class EvaluationTuningRepository(Protocol):
    """Evaluation/tuning/patch-lineage surface.

    Allowed to own:
    tuning recommendations, patch candidates, validation results, promotion history,
    profile version lineage queries.

    Must not own:
    chat state, raw ingest reliability logs, UI-only replay cache state.
    """

    def save_tuning_recommendation(self, *, recommendation_id: str, instrument_symbol: str, market_time: datetime, ingested_at: datetime, schema_version: str, profile_version: str, engine_version: str, episode_id: str | None, evaluation_id: str | None, source_kind: str, recommendation_payload: dict[str, object]) -> StoredTuningRecommendationRecord:
        ...

    def list_tuning_recommendations(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredTuningRecommendationRecord]:
        ...

    def save_profile_patch_candidate(self, *, candidate_id: str, instrument_symbol: str, market_time: datetime, ingested_at: datetime, schema_version: str, base_profile_version: str, proposed_profile_version: str, recommendation_id: str | None, status: str, patch_payload: dict[str, object]) -> StoredProfilePatchCandidateRecord:
        ...

    def list_profile_patch_candidates(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredProfilePatchCandidateRecord]:
        ...

    def save_patch_validation_result(self, *, validation_result_id: str, instrument_symbol: str, market_time: datetime, ingested_at: datetime, schema_version: str, candidate_id: str, validation_status: str, validation_payload: dict[str, object]) -> StoredPatchValidationResultRecord:
        ...

    def list_patch_validation_results(self, *, candidate_id: str, limit: int = 100) -> list[StoredPatchValidationResultRecord]:
        ...

    def save_patch_promotion_history(self, *, promotion_id: str, candidate_id: str, instrument_symbol: str, promoted_profile_version: str, previous_profile_version: str, promoted_at: datetime, promoted_by: str, promotion_notes: str, detail: dict[str, object]) -> StoredPatchPromotionHistoryRecord:
        ...

    def get_patch_promotion(self, promotion_id: str) -> StoredPatchPromotionHistoryRecord | None:
        ...

    def list_patch_promotions(
        self,
        *,
        candidate_id: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 200,
    ) -> list[StoredPatchPromotionHistoryRecord]:
        ...

    def get_instrument_profile_version(
        self,
        instrument_symbol: str,
        profile_version: str,
    ) -> StoredInstrumentProfile | None:
        ...

    def list_instrument_profile_versions(
        self,
        instrument_symbol: str,
        limit: int = 100,
    ) -> list[StoredInstrumentProfile]:
        ...
