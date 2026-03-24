from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class StoredIngestion:
    ingestion_id: str
    ingestion_kind: str
    source_snapshot_id: str
    instrument_symbol: str
    observed_payload: dict[str, Any]
    stored_at: datetime


@dataclass(frozen=True)
class StoredAnalysis:
    analysis_id: str
    ingestion_id: str
    route_key: str
    analysis_payload: dict[str, Any]
    stored_at: datetime


@dataclass(frozen=True)
class StoredLiquidityMemory:
    memory_id: str
    track_key: str
    instrument_symbol: str
    coverage_state: str
    observed_track: dict[str, Any]
    derived_summary: dict[str, Any]
    expires_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredBeliefState:
    belief_state_id: str
    instrument_symbol: str
    observed_at: datetime
    stored_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    recognition_mode: str
    belief_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEventEpisode:
    episode_id: str
    instrument_symbol: str
    event_kind: str
    started_at: datetime
    ended_at: datetime
    resolution: str
    schema_version: str
    profile_version: str
    engine_version: str
    episode_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredEpisodeEvaluation:
    evaluation_id: str
    episode_id: str
    instrument_symbol: str
    event_kind: str
    evaluated_at: datetime
    schema_version: str
    profile_version: str
    engine_version: str
    evaluation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredInstrumentProfile:
    instrument_symbol: str
    profile_version: str
    schema_version: str
    ontology_version: str
    is_active: bool
    profile_payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class StoredRecognizerBuild:
    engine_version: str
    schema_version: str
    ontology_version: str
    is_active: bool
    status: str
    build_payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class StoredTuningRecommendationRecord:
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
class StoredProfilePatchCandidateRecord:
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
class StoredPatchValidationResultRecord:
    validation_result_id: str
    instrument_symbol: str
    market_time: datetime
    ingested_at: datetime
    schema_version: str
    candidate_id: str
    validation_status: str
    validation_payload: dict[str, Any]


@dataclass(frozen=True)
class StoredPatchPromotionHistoryRecord:
    """Business-layer view of a patch promotion history row."""

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
class StoredIngestionDeadLetter:
    dead_letter_id: str
    endpoint: str
    ingestion_kind: str
    instrument_symbol: str | None
    source_snapshot_id: str | None
    request_id: str | None
    dedup_key: str
    payload_hash: str
    raw_payload: str
    error_code: str
    error_detail: dict[str, Any]
    ingestion_id: str | None
    stored_at: datetime


@dataclass(frozen=True)
class StoredIngestionIdempotencyKey:
    endpoint: str
    dedup_key: str
    request_id: str | None
    payload_hash: str
    ingestion_id: str
    response_payload: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    duplicate_count: int


@dataclass(frozen=True)
class StoredIngestionRunLog:
    run_id: str
    endpoint: str
    ingestion_kind: str
    instrument_symbol: str | None
    request_id: str | None
    dedup_key: str
    payload_hash: str
    outcome: str
    http_status: int
    ingestion_id: str | None
    dead_letter_id: str | None
    detail: dict[str, Any]
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class StoredChatSession:
    session_id: str
    workspace_id: str
    title: str
    symbol: str
    contract_id: str | None
    timeframe: str
    window_range: dict[str, Any]
    active_model: str | None
    status: str
    draft_text: str
    draft_attachments: list[dict[str, Any]]
    selected_prompt_block_ids: list[str]
    pinned_context_block_ids: list[str]
    include_memory_summary: bool
    include_recent_messages: bool
    mounted_reply_ids: list[str]
    active_plan_id: str | None
    memory_summary_id: str | None
    unread_count: int
    scroll_offset: int
    pinned: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredChatMessage:
    message_id: str
    session_id: str
    parent_message_id: str | None
    role: str
    content: str
    status: str
    reply_title: str | None
    stream_buffer: str
    model: str | None
    annotations: list[str]
    plan_cards: list[str]
    mounted_to_chart: bool
    mounted_object_ids: list[str]
    is_key_conclusion: bool
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredPromptBlock:
    block_id: str
    session_id: str
    symbol: str
    contract_id: str | None
    timeframe: str | None
    kind: str
    title: str
    preview_text: str
    full_payload: dict[str, Any]
    selected_by_default: bool
    pinned: bool
    ephemeral: bool
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class StoredSessionMemory:
    memory_summary_id: str
    session_id: str
    summary_version: int
    active_model: str | None
    symbol: str
    contract_id: str | None
    timeframe: str
    window_range: dict[str, Any]
    user_goal_summary: str
    market_context_summary: str
    key_zones_summary: list[str]
    active_plans_summary: list[str]
    invalidated_plans_summary: list[str]
    important_messages: list[str]
    current_user_intent: str
    latest_question: str
    latest_answer_summary: str
    selected_annotations: list[str]
    last_updated_at: datetime


@dataclass(frozen=True)
class StoredChatAnnotation:
    annotation_id: str
    session_id: str
    message_id: str
    plan_id: str | None
    symbol: str
    contract_id: str | None
    timeframe: str | None
    annotation_type: str
    subtype: str | None
    label: str
    reason: str
    start_time: datetime
    end_time: datetime | None
    expires_at: datetime | None
    status: str
    priority: int | None
    confidence: float | None
    visible: bool
    pinned: bool
    source_kind: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredChatPlanCard:
    plan_id: str
    session_id: str
    message_id: str
    title: str
    side: str
    entry_type: str | None
    entry_price: float | None
    entry_price_low: float | None
    entry_price_high: float | None
    stop_price: float | None
    take_profits: list[dict[str, Any]]
    invalidations: list[str]
    time_validity: str | None
    risk_reward: float | None
    confidence: float | None
    priority: int | None
    status: str
    source_kind: str
    notes: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
