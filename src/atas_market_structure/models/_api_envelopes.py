from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import ConfigDict, Field

from atas_market_structure.models._derived import DerivedStructureAnalysis
from atas_market_structure.models._replay import (
    BeliefStateSnapshot,
    EpisodeEvaluation,
    EventEpisode,
    InstrumentProfile,
    ProfilePatchCandidate,
    ProfilePatchValidationResult,
    RecognizerBuild,
    ReplayProjectionQuery,
    ReplayProjectionTimelineEntry,
    ReplayWorkbenchBeliefTimelineEntry,
    ReplayWorkbenchEpisodeEvaluationItem,
    ReplayWorkbenchEpisodeReviewItem,
    ReplayWorkbenchTuningReviewItem,
)
from atas_market_structure.models._responses import DataQualityResponse, IngestionHealthResponse
from atas_market_structure.models._schema_versions import (
    ANALYSIS_ENVELOPE_SCHEMA_VERSION,
    BELIEF_LATEST_ENVELOPE_SCHEMA_VERSION,
    CanonicalSchemaVersionedModel,
    EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION,
    EPISODE_LIST_ENVELOPE_SCHEMA_VERSION,
    INGESTION_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_BELIEF_TIMELINE_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_EPISODE_EVALUATION_LIST_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_EPISODE_REVIEW_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_HEALTH_STATUS_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_PROFILE_ENGINE_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_PROJECTION_ENVELOPE_SCHEMA_VERSION,
    REPLAY_WORKBENCH_TUNING_REVIEW_ENVELOPE_SCHEMA_VERSION,
)


class AnalysisEnvelope(CanonicalSchemaVersionedModel):
    """REST response for analysis retrieval."""

    canonical_schema_version: ClassVar[str] = ANALYSIS_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this analysis response.")
    analysis: DerivedStructureAnalysis


class IngestionEnvelope(CanonicalSchemaVersionedModel):
    """REST response for observed payload retrieval."""

    canonical_schema_version: ClassVar[str] = INGESTION_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this ingestion retrieval response.")
    ingestion_id: str
    ingestion_kind: str
    source_snapshot_id: str
    observed_payload: dict[str, object]
    stored_at: datetime


class ReplayWorkbenchBeliefTimelineEnvelope(CanonicalSchemaVersionedModel):
    """Read-model response for replay workbench belief-state timelines."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_BELIEF_TIMELINE_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this belief-timeline response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to build this timeline.")
    current_belief: BeliefStateSnapshot | None = Field(None, description="Latest belief-state snapshot in scope when available.")
    items: list[ReplayWorkbenchBeliefTimelineEntry] = Field(default_factory=list, description="Timeline-ordered belief-state rows.")


class ReplayWorkbenchEpisodeReviewEnvelope(CanonicalSchemaVersionedModel):
    """Read-model response for replay workbench event episode review."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_EPISODE_REVIEW_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this episode-review response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to build this review section.")
    items: list[ReplayWorkbenchEpisodeReviewItem] = Field(default_factory=list, description="Episode review rows in descending time order.")


class ReplayWorkbenchEpisodeEvaluationListEnvelope(CanonicalSchemaVersionedModel):
    """Read-model response for replay workbench episode-evaluation timelines."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_EPISODE_EVALUATION_LIST_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this episode-evaluation response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to build this evaluation section.")
    items: list[ReplayWorkbenchEpisodeEvaluationItem] = Field(default_factory=list, description="Evaluation rows in descending time order.")


class ReplayWorkbenchTuningReviewEnvelope(CanonicalSchemaVersionedModel):
    """Read-model response for replay workbench tuning recommendation review."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_TUNING_REVIEW_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this tuning-review response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to build this tuning section.")
    items: list[ReplayWorkbenchTuningReviewItem] = Field(default_factory=list, description="Tuning review rows in descending time order.")


class ReplayWorkbenchProfileEngineEnvelope(CanonicalSchemaVersionedModel):
    """Current profile/build metadata shown by replay workbench review panels."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_PROFILE_ENGINE_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this profile/build metadata response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to resolve the active metadata.")
    active_profile: InstrumentProfile | None = Field(None, description="Currently active instrument profile when available.")
    active_build: RecognizerBuild | None = Field(None, description="Currently active recognizer build when available.")
    latest_patch_candidate_status: str | None = Field(None, description="Stored lifecycle status for the latest patch candidate when available.")
    latest_patch_candidate: ProfilePatchCandidate | None = Field(None, description="Most recent patch candidate for the instrument when available.")
    latest_patch_validation_result: ProfilePatchValidationResult | None = Field(
        None,
        description="Latest validation result linked to the latest patch candidate when available.",
    )


class ReplayWorkbenchHealthStatusEnvelope(CanonicalSchemaVersionedModel):
    """Combined health/data-quality view consumed by replay workbench review UIs."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_HEALTH_STATUS_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this health-status response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to scope the health view.")
    health: IngestionHealthResponse = Field(..., description="Current ingestion-plane health payload.")
    data_quality: DataQualityResponse = Field(..., description="Current data-quality payload for recognition/UI consumers.")
    latest_belief: BeliefStateSnapshot | None = Field(None, description="Latest belief-state snapshot available for the instrument.")


class ReplayWorkbenchProjectionEnvelope(CanonicalSchemaVersionedModel):
    """Full replay workbench projection/read-model bundle for timeline and review panels."""

    model_config = ConfigDict(extra="forbid")
    canonical_schema_version: ClassVar[str] = REPLAY_WORKBENCH_PROJECTION_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this projection response.")
    query: ReplayProjectionQuery = Field(..., description="Filters used to build this projection.")
    health_status: ReplayWorkbenchHealthStatusEnvelope = Field(..., description="Health and degraded-state view.")
    metadata: ReplayWorkbenchProfileEngineEnvelope = Field(..., description="Current profile/build metadata view.")
    belief_timeline: ReplayWorkbenchBeliefTimelineEnvelope = Field(..., description="Belief-state timeline section.")
    episode_reviews: ReplayWorkbenchEpisodeReviewEnvelope = Field(..., description="Closed-episode review section.")
    episode_evaluations: ReplayWorkbenchEpisodeEvaluationListEnvelope = Field(..., description="Episode-evaluation review section.")
    tuning_reviews: ReplayWorkbenchTuningReviewEnvelope = Field(..., description="Tuning recommendation review section.")
    timeline: list[ReplayProjectionTimelineEntry] = Field(default_factory=list, description="Merged timeline-friendly projection rows.")


class BeliefLatestEnvelope(CanonicalSchemaVersionedModel):
    """REST response envelope returning the latest belief-state snapshot."""

    canonical_schema_version: ClassVar[str] = BELIEF_LATEST_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this latest-belief response.")
    belief: BeliefStateSnapshot | None = Field(None, description="Latest belief-state snapshot when available.")


class EpisodeListEnvelope(CanonicalSchemaVersionedModel):
    """REST response envelope returning recently closed event episodes."""

    canonical_schema_version: ClassVar[str] = EPISODE_LIST_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this episode-list response.")
    instrument_symbol: str = Field(..., description="Instrument symbol that was queried.")
    episodes: list[EventEpisode] = Field(default_factory=list, description="Recently closed episodes for the instrument.")


class EpisodeEvaluationEnvelope(CanonicalSchemaVersionedModel):
    """REST response envelope returning one stored episode evaluation."""

    canonical_schema_version: ClassVar[str] = EPISODE_EVALUATION_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this episode-evaluation response.")
    evaluation: EpisodeEvaluation | None = Field(None, description="Stored episode evaluation when available.")
