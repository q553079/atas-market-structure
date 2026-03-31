from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.models._chat import ChatAnnotation, ChatPlanCard
from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._schema_versions import (
    EVENT_CANDIDATE_SCHEMA_VERSION,
    EVENT_MEMORY_ENTRY_SCHEMA_VERSION,
    EVENT_STREAM_ENTRY_SCHEMA_VERSION,
    CanonicalSchemaVersionedModel,
    WORKBENCH_EVENT_MUTATION_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_STREAM_ENVELOPE_SCHEMA_VERSION,
)


class EventCandidateKind(str, Enum):
    KEY_LEVEL = "key_level"
    PRICE_ZONE = "price_zone"
    MARKET_EVENT = "market_event"
    THESIS_FRAGMENT = "thesis_fragment"
    PLAN_INTENT = "plan_intent"
    RISK_NOTE = "risk_note"


class EventCandidateLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    MOUNTED = "mounted"
    IGNORED = "ignored"
    PROMOTED_PLAN = "promoted_plan"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class EventCandidateSourceType(str, Enum):
    MANUAL = "manual"
    RECOGNIZER = "recognizer"
    ORCHESTRATION = "orchestration"
    AI_REPLY_STRUCTURED = "ai_reply_structured"
    AI_REPLY_TEXT = "ai_reply_text"
    USER_CREATED = "user_created"


class EventStreamAction(str, Enum):
    CREATED = "created"
    EXTRACTED = "extracted"
    PATCHED = "patched"
    STATE_TRANSITION = "state_transition"
    PROMOTED = "promoted"
    MEMORY_REFRESHED = "memory_refreshed"


class EventMemoryBucket(str, Enum):
    ACTIVE = "active"
    WATCHLIST = "watchlist"
    PROJECTED = "projected"
    INACTIVE = "inactive"


class EventLifecycleAction(str, Enum):
    CONFIRM = "confirm"
    ARCHIVE = "archive"
    EXPIRE = "expire"


class EventPromotionTarget(str, Enum):
    ANNOTATION = "annotation"
    PLAN_CARD = "plan_card"


class EventStreamQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Chat session identifier.")
    symbol: str | None = Field(None, description="Optional symbol filter.")
    timeframe: Timeframe | str | None = Field(None, description="Optional timeframe filter.")
    source_message_id: str | None = Field(None, description="Optional source message filter.")
    limit: int = Field(200, ge=1, le=1000, description="Maximum number of rows to return.")


class WorkbenchEventBase(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Stable event candidate identifier.")
    session_id: str = Field(..., description="Owning chat session identifier.")
    candidate_kind: EventCandidateKind = Field(..., description="Normalized event candidate kind.")
    title: str = Field(..., description="Short operator-facing title.")
    summary: str = Field("", description="Compact explanation of the candidate.")
    symbol: str = Field(..., description="Instrument symbol.")
    timeframe: Timeframe | str = Field(..., description="Candidate timeframe.")
    anchor_start_ts: datetime | None = Field(None, description="Optional anchor/window start timestamp.")
    anchor_end_ts: datetime | None = Field(None, description="Optional anchor/window end timestamp.")
    price_lower: float | None = Field(None, description="Optional zone low.")
    price_upper: float | None = Field(None, description="Optional zone high.")
    price_ref: float | None = Field(None, description="Optional single reference price.")
    side_hint: str | None = Field(None, description="Optional directional hint such as buy or sell.")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Optional confidence score.")
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, description="Structured evidence references.")
    source_type: EventCandidateSourceType = Field(..., description="Primary candidate source.")
    source_message_id: str | None = Field(None, description="Source assistant message identifier when present.")
    source_prompt_trace_id: str | None = Field(None, description="Optional prompt trace identifier when present.")
    lifecycle_state: EventCandidateLifecycleState = Field(..., description="Current lifecycle state.")
    invalidation_rule: dict[str, Any] = Field(default_factory=dict, description="Optional invalidation rule payload.")
    evaluation_window: dict[str, Any] = Field(default_factory=dict, description="Optional evaluation window payload.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional additive metadata. Stable workbench UI facts should live under metadata.presentation.",
    )
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class EventCandidate(WorkbenchEventBase):
    canonical_schema_version = EVENT_CANDIDATE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event candidate.")
    dedup_key: str | None = Field(None, description="Service-generated dedupe key when available.")
    promoted_projection_type: str | None = Field(None, description="Derived projection type when promoted.")
    promoted_projection_id: str | None = Field(None, description="Derived projection identifier when promoted.")


class EventStreamEntry(WorkbenchEventBase):
    canonical_schema_version = EVENT_STREAM_ENTRY_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event-stream entry.")
    stream_entry_id: str = Field(..., description="Append-only stream entry identifier.")
    stream_action: EventStreamAction = Field(..., description="Why this event-stream row was recorded.")


class EventMemoryEntry(WorkbenchEventBase):
    canonical_schema_version = EVENT_MEMORY_ENTRY_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event-memory entry.")
    memory_entry_id: str = Field(..., description="Event memory row identifier.")
    memory_bucket: EventMemoryBucket = Field(..., description="How this candidate is represented in event memory.")


class EventStreamExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Chat session identifier.")
    source_message_id: str | None = Field(None, description="Assistant message to extract from. Defaults to the latest assistant message.")
    symbol: str | None = Field(None, description="Optional symbol filter.")
    timeframe: Timeframe | str | None = Field(None, description="Optional timeframe filter.")
    limit: int = Field(200, ge=1, le=1000, description="Maximum rows returned after extraction.")


class EventCandidatePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, description="Updated title.")
    summary: str | None = Field(None, description="Updated summary.")
    side_hint: str | None = Field(None, description="Updated directional hint.")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Updated confidence.")
    invalidation_rule: dict[str, Any] | None = Field(None, description="Updated invalidation rule payload.")
    evaluation_window: dict[str, Any] | None = Field(None, description="Updated evaluation window payload.")
    metadata: dict[str, Any] | None = Field(
        None,
        description="Metadata fields to merge into the candidate metadata. Stable workbench UI facts should live under metadata.presentation.",
    )
    lifecycle_action: EventLifecycleAction | None = Field(None, description="Optional validated lifecycle action.")


class CreateEventCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Owning chat session identifier.")
    candidate_kind: EventCandidateKind = Field(..., description="Normalized event candidate kind.")
    title: str = Field(..., min_length=1, description="Operator-facing short title.")
    summary: str = Field("", description="Compact candidate summary.")
    symbol: str | None = Field(None, description="Optional symbol override. Defaults to the session symbol.")
    timeframe: Timeframe | str | None = Field(None, description="Optional timeframe override. Defaults to the session timeframe.")
    anchor_start_ts: datetime | None = Field(None, description="Optional anchor/window start timestamp.")
    anchor_end_ts: datetime | None = Field(None, description="Optional anchor/window end timestamp.")
    price_lower: float | None = Field(None, description="Optional lower price for a zone.")
    price_upper: float | None = Field(None, description="Optional upper price for a zone.")
    price_ref: float | None = Field(None, description="Optional reference price for a level.")
    side_hint: str | None = Field(None, description="Optional directional hint such as buy or sell.")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Optional operator confidence score.")
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, description="Structured evidence references.")
    source_type: EventCandidateSourceType = Field(
        default=EventCandidateSourceType.MANUAL,
        description="Candidate source classification.",
    )
    source_message_id: str | None = Field(None, description="Optional source assistant message identifier.")
    source_prompt_trace_id: str | None = Field(None, description="Optional prompt-trace identifier.")
    invalidation_rule: dict[str, Any] = Field(default_factory=dict, description="Optional invalidation rule payload.")
    evaluation_window: dict[str, Any] = Field(default_factory=dict, description="Optional evaluation window payload.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional additive metadata. Stable workbench UI facts should live under metadata.presentation.",
    )


class PromoteEventCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: EventPromotionTarget = Field(..., description="Derived projection target.")


class EventStreamEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_EVENT_STREAM_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event-stream response.")
    query: EventStreamQuery = Field(..., description="Filters applied to the event stream query.")
    candidates: list[EventCandidate] = Field(default_factory=list, description="Current event candidates matching the query.")
    items: list[EventStreamEntry] = Field(default_factory=list, description="Append-only event-stream rows.")
    memory_entries: list[EventMemoryEntry] = Field(default_factory=list, description="Current event-memory rows for the session.")


class EventMutationEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_EVENT_MUTATION_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event mutation response.")
    session_id: str = Field(..., description="Owning chat session identifier.")
    candidate: EventCandidate = Field(..., description="Updated event candidate.")
    stream_entry: EventStreamEntry | None = Field(None, description="Stream row created by the mutation.")
    memory_entry: EventMemoryEntry | None = Field(None, description="Updated event-memory row when applicable.")
    projected_annotation: ChatAnnotation | None = Field(None, description="Derived annotation when the mutation creates one.")
    projected_plan_card: ChatPlanCard | None = Field(None, description="Derived plan card when the mutation creates one.")
