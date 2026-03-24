from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class StorageLifecyclePolicy(str, Enum):
    """Lifecycle policy enforced by the storage blueprint."""

    APPEND_ONLY = "append_only"
    VERSIONED = "versioned"


class ObservationTable(str, Enum):
    """Append-only observed-fact tables defined by Master Spec v2."""

    BAR = "observation_bar"
    TRADE_CLUSTER = "observation_trade_cluster"
    DEPTH_EVENT = "observation_depth_event"
    GAP_EVENT = "observation_gap_event"
    SWING_EVENT = "observation_swing_event"
    ABSORPTION_EVENT = "observation_absorption_event"
    ADAPTER_PAYLOAD = "observation_adapter_payload"


@dataclass(frozen=True)
class StorageTableLifecycle:
    """Lifecycle metadata mirrored into schema_registry and docs."""

    table_name: str
    object_kind: str
    lifecycle_policy: StorageLifecyclePolicy
    notes: str


@dataclass(frozen=True)
class AppliedMigration:
    """One applied SQLite migration row."""

    version: str
    name: str
    checksum: str
    applied_at: datetime


@dataclass(frozen=True)
class StoredObservationRecord:
    """Generic append-only observed-fact row stored in an observation_* table."""

    table_name: ObservationTable
    observation_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    source_ingestion_id: str | None
    source_request_id: str | None
    dedup_key: str | None
    payload_hash: str | None
    observation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredFeatureSlice:
    """Append-only feature slice derived from one or more observations."""

    feature_slice_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    source_observation_table: str | None
    source_observation_id: str | None
    slice_kind: str
    window_start: datetime | None
    window_end: datetime | None
    data_status: dict[str, Any]
    feature_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredRegimePosterior:
    """Append-only regime posterior row emitted by deterministic recognition."""

    posterior_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    feature_slice_id: str | None
    posterior_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEventHypothesisState:
    """Append-only event-hypothesis posterior state."""

    hypothesis_state_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    feature_slice_id: str | None
    hypothesis_kind: str
    hypothesis_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredProjectionSnapshot:
    """Append-only projection snapshot derived from one belief state."""

    projection_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    belief_state_id: str | None
    projection_kind: str
    projection_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredBeliefStateSnapshot:
    """Append-only belief-state snapshot stored in the blueprint table."""

    belief_state_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    recognition_mode: str
    data_status: dict[str, Any]
    belief_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredMemoryAnchor:
    """Current versioned memory-anchor state."""

    anchor_id: str
    instrument_symbol: str
    anchor_type: str
    status: str
    freshness: str | None
    current_version_id: str | None
    reference_price: float | None
    reference_time: datetime | None
    schema_version: str
    profile_version: str
    engine_version: str
    anchor_payload: dict[str, Any]
    updated_at: datetime


@dataclass(frozen=True)
class StoredMemoryAnchorVersion:
    """Append-only memory-anchor version history row."""

    anchor_version_id: str
    anchor_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    freshness: str | None
    anchor_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredAnchorInteraction:
    """Append-only observation-to-anchor interaction."""

    anchor_interaction_id: str
    anchor_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    interaction_kind: str
    source_observation_table: str | None
    source_observation_id: str | None
    interaction_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEventEpisodeEvidence:
    """Append-only evidence row linked to one event episode."""

    evidence_id: str
    episode_id: str
    instrument_symbol: str
    market_time: datetime
    session_date: str | None
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    evidence_kind: str
    source_observation_table: str | None
    source_observation_id: str | None
    evidence_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEventEpisodeRecord:
    """Append-only event episode stored in the blueprint table."""

    episode_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    event_kind: str
    started_at: datetime
    ended_at: datetime
    resolution: str
    episode_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEpisodeEvaluationRecord:
    """Append-only episode evaluation stored in the blueprint table."""

    evaluation_id: str
    episode_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    event_kind: str
    evaluated_at: datetime
    evaluation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredTuningRecommendation:
    """Append-only tuning recommendation emitted after evaluation."""

    recommendation_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    episode_id: str | None
    evaluation_id: str | None
    source_kind: str
    recommendation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredProfilePatchCandidate:
    """Append-only candidate patch proposed for one instrument profile."""

    candidate_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    base_profile_version: str
    proposed_profile_version: str
    recommendation_id: str | None
    status: str
    patch_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredPatchValidationResult:
    """Append-only offline validation result for one patch candidate."""

    validation_result_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    candidate_id: str
    validation_status: str
    validation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredPatchPromotionHistory:
    """Append-only patch promotion history record.

    Tracks each promotion event: a candidate patch becoming the active profile.
    One candidate_id can appear multiple times (e.g., re-promoted after rollback),
    but each promotion_id is unique and immutable.
    """

    promotion_id: str
    candidate_id: str
    instrument_symbol: str
    promoted_profile_version: str
    previous_profile_version: str
    promoted_at: datetime
    promoted_by: str
    promotion_notes: str
    detail: dict[str, Any]


@dataclass(frozen=True)
class StoredInstrumentProfileVersion:
    """Versioned instrument-profile row."""

    instrument_symbol: str
    profile_version: str
    schema_version: str
    ontology_version: str
    is_active: bool
    profile_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredRecognizerBuildVersion:
    """Versioned recognizer-build row."""

    engine_version: str
    schema_version: str
    ontology_version: str
    is_active: bool
    status: str
    build_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredIngestionRunLogRecord:
    """Append-only ingestion run-log row in the blueprint ops table."""

    run_id: str
    endpoint: str
    ingestion_kind: str
    instrument_symbol: str | None
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    request_id: str | None
    dedup_key: str | None
    payload_hash: str | None
    ingestion_id: str | None
    dead_letter_id: str | None
    outcome: str
    http_status: int
    detail: dict[str, Any]
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class StoredRebuildRunLog:
    """Operator-auditable rebuild run record."""

    rebuild_run_id: str
    instrument_symbol: str | None
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    triggered_by: str | None
    reason: str
    status: str
    window_start: datetime | None
    window_end: datetime | None
    cleared_tables: list[str]
    detail: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class StoredDeadLetterPayload:
    """Operational dead-letter row for failed payload handling."""

    dead_letter_id: str
    endpoint: str
    ingestion_kind: str
    instrument_symbol: str | None
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    request_id: str | None
    dedup_key: str | None
    payload_hash: str | None
    source_ingestion_id: str | None
    error_code: str
    error_detail: dict[str, Any]
    raw_payload: str


@dataclass(frozen=True)
class StoredSchemaRegistryEntry:
    """Registry metadata for one blueprint table or schema object."""

    object_name: str
    object_kind: str
    lifecycle_policy: StorageLifecyclePolicy
    schema_version: str
    notes: str
    registered_at: datetime


BLUEPRINT_TABLE_LIFECYCLES: tuple[StorageTableLifecycle, ...] = (
    StorageTableLifecycle(ObservationTable.BAR.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed bars mirrored from adapter history payloads."),
    StorageTableLifecycle(ObservationTable.TRADE_CLUSTER.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed trade-cluster style event payloads."),
    StorageTableLifecycle(ObservationTable.DEPTH_EVENT.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed depth/DOM facts that must survive degraded mode."),
    StorageTableLifecycle(ObservationTable.GAP_EVENT.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed gap references extracted from raw observations."),
    StorageTableLifecycle(ObservationTable.SWING_EVENT.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed swing references extracted from structure payloads."),
    StorageTableLifecycle(ObservationTable.ABSORPTION_EVENT.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Observed absorption evidence kept separate from interpretation."),
    StorageTableLifecycle(ObservationTable.ADAPTER_PAYLOAD.value, "observation", StorageLifecyclePolicy.APPEND_ONLY, "Raw adapter payload mirror used for replay-safe rebuild."),
    StorageTableLifecycle("feature_slice", "derived", StorageLifecyclePolicy.APPEND_ONLY, "Windowed numeric features derived from observations."),
    StorageTableLifecycle("regime_posterior", "derived", StorageLifecyclePolicy.APPEND_ONLY, "Regime posterior snapshots."),
    StorageTableLifecycle("event_hypothesis_state", "derived", StorageLifecyclePolicy.APPEND_ONLY, "Parallel event-hypothesis posterior state."),
    StorageTableLifecycle("belief_state_snapshot", "derived", StorageLifecyclePolicy.APPEND_ONLY, "Top-level belief state snapshots consumed by UI and replay."),
    StorageTableLifecycle("projection_snapshot", "derived", StorageLifecyclePolicy.APPEND_ONLY, "Plan/zone/risk projections derived from belief state."),
    StorageTableLifecycle("memory_anchor", "memory", StorageLifecyclePolicy.VERSIONED, "Current memory-anchor state keyed by stable anchor_id."),
    StorageTableLifecycle("memory_anchor_version", "memory", StorageLifecyclePolicy.APPEND_ONLY, "Historical anchor versions referenced by current memory_anchor state."),
    StorageTableLifecycle("anchor_interaction", "memory", StorageLifecyclePolicy.APPEND_ONLY, "Observed interactions between live market state and historical anchors."),
    StorageTableLifecycle("event_episode", "trajectory", StorageLifecyclePolicy.APPEND_ONLY, "Closed event trajectory snapshots."),
    StorageTableLifecycle("event_episode_evidence", "trajectory", StorageLifecyclePolicy.APPEND_ONLY, "Evidence rows linked to one event episode."),
    StorageTableLifecycle("episode_evaluation", "evaluation", StorageLifecyclePolicy.APPEND_ONLY, "Standardized episode evaluations."),
    StorageTableLifecycle("tuning_recommendation", "evaluation", StorageLifecyclePolicy.APPEND_ONLY, "Append-only tuning recommendations."),
    StorageTableLifecycle("profile_patch_candidate", "evaluation", StorageLifecyclePolicy.APPEND_ONLY, "Candidate profile patches awaiting validation."),
    StorageTableLifecycle("patch_validation_result", "evaluation", StorageLifecyclePolicy.APPEND_ONLY, "Offline validation rows for patch candidates."),
    StorageTableLifecycle("patch_promotion_history", "evaluation", StorageLifecyclePolicy.APPEND_ONLY, "Append-only promotion audit trail for patch candidates."),
    StorageTableLifecycle("instrument_profile", "versioned_state", StorageLifecyclePolicy.VERSIONED, "Versioned instrument profile registry."),
    StorageTableLifecycle("recognizer_build", "versioned_state", StorageLifecyclePolicy.VERSIONED, "Versioned recognizer build registry."),
    StorageTableLifecycle("ingestion_run_log", "ops", StorageLifecyclePolicy.APPEND_ONLY, "Operational ingestion run log mirrored from HTTP ingest plane."),
    StorageTableLifecycle("rebuild_run_log", "ops", StorageLifecyclePolicy.APPEND_ONLY, "Operator-visible rebuild audit trail."),
    StorageTableLifecycle("dead_letter_payload", "ops", StorageLifecyclePolicy.APPEND_ONLY, "Dead-letter quarantine payloads."),
    StorageTableLifecycle("schema_registry", "ops", StorageLifecyclePolicy.VERSIONED, "Registry of blueprint tables and lifecycle policies."),
)
