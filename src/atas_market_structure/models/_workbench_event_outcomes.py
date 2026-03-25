from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._schema_versions import (
    EVENT_OUTCOME_LEDGER_SCHEMA_VERSION,
    WORKBENCH_EVENT_OUTCOME_LIST_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_STATS_BREAKDOWN_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_EVENT_STATS_SUMMARY_ENVELOPE_SCHEMA_VERSION,
    CanonicalSchemaVersionedModel,
)


class EventOutcomeResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    INCONCLUSIVE = "inconclusive"


class EventOutcomeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Owning chat session identifier.")
    symbol: str | None = Field(None, description="Optional symbol filter.")
    timeframe: Timeframe | str | None = Field(None, description="Optional timeframe filter.")
    event_id: str | None = Field(None, description="Optional event identifier filter.")
    event_kind: str | None = Field(None, description="Optional event kind filter.")
    realized_outcome: EventOutcomeResult | str | None = Field(None, description="Optional settled outcome filter.")
    limit: int = Field(500, ge=1, le=2000, description="Maximum rows returned.")


class EventStatsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Owning chat session identifier.")
    symbol: str | None = Field(None, description="Optional symbol filter.")
    timeframe: Timeframe | str | None = Field(None, description="Optional timeframe filter.")
    limit: int = Field(2000, ge=1, le=10000, description="Maximum rows considered for aggregation.")


class EventOutcomeLedger(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = EVENT_OUTCOME_LEDGER_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this outcome ledger row.")
    outcome_id: str = Field(..., description="Stable outcome identifier.")
    event_id: str = Field(..., description="Linked event candidate identifier.")
    session_id: str = Field(..., description="Owning chat session identifier.")
    source_message_id: str | None = Field(None, description="Linked source assistant message identifier.")
    source_prompt_trace_id: str | None = Field(None, description="Linked prompt trace identifier.")
    analysis_preset: str | None = Field(None, description="Prompt preset used when the event was created.")
    model_name: str | None = Field(None, description="Resolved model name used when the event was created.")
    symbol: str = Field(..., description="Instrument symbol.")
    timeframe: Timeframe | str = Field(..., description="Event timeframe.")
    event_kind: str = Field(..., description="Settled workbench event kind.")
    born_at: datetime = Field(..., description="When the event started to be tracked.")
    observed_price: float | None = Field(None, description="Reference price used for outcome settlement.")
    target_rule: dict[str, Any] = Field(default_factory=dict, description="Deterministic target rule used for settlement.")
    invalidation_rule: dict[str, Any] = Field(default_factory=dict, description="Deterministic invalidation rule used for settlement.")
    evaluation_window_start: datetime = Field(..., description="Settlement window start.")
    evaluation_window_end: datetime = Field(..., description="Settlement window end.")
    expiry_policy: dict[str, Any] = Field(default_factory=dict, description="Explicit expiry policy snapshot.")
    realized_outcome: EventOutcomeResult | None = Field(None, description="Final settled outcome when available.")
    outcome_label: str = Field(..., description="Operator-facing outcome label. Pending rows keep 'pending'.")
    mfe: float | None = Field(None, description="Maximum favorable excursion in price units.")
    mae: float | None = Field(None, description="Maximum adverse excursion in price units.")
    hit_target: bool = Field(False, description="Whether the target rule was touched.")
    hit_stop: bool = Field(False, description="Whether the invalidation rule was touched.")
    timed_out: bool = Field(False, description="Whether the event timed out without another settlement.")
    inconclusive: bool = Field(False, description="Whether settlement was blocked by insufficient/ambiguous evidence.")
    evaluated_at: datetime = Field(..., description="Last evaluation timestamp.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additive evaluation metadata and evidence.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class EventOutcomeListEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_EVENT_OUTCOME_LIST_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event outcome list response.")
    ok: bool = Field(True, description="Whether the request succeeded.")
    query: EventOutcomeQuery = Field(..., description="Applied list query.")
    outcomes: list[EventOutcomeLedger] = Field(default_factory=list, description="Outcome ledger rows.")


class EventStatsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_count: int = Field(0, description="All tracked outcome rows matching the query.")
    settled_count: int = Field(0, description="Rows with a settled outcome.")
    open_count: int = Field(0, description="Rows still pending settlement.")
    success_count: int = Field(0, description="Rows settled as success.")
    failure_count: int = Field(0, description="Rows settled as failure.")
    timeout_count: int = Field(0, description="Rows settled as timeout.")
    inconclusive_count: int = Field(0, description="Rows settled as inconclusive.")
    accuracy_rate: float = Field(0.0, description="Success share across settled rows.")
    failure_rate: float = Field(0.0, description="Failure share across settled rows.")
    timeout_rate: float = Field(0.0, description="Timeout share across settled rows.")
    inconclusive_rate: float = Field(0.0, description="Inconclusive share across settled rows.")


class EventStatsSummaryEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_EVENT_STATS_SUMMARY_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event-stats summary response.")
    ok: bool = Field(True, description="Whether the request succeeded.")
    query: EventStatsQuery = Field(..., description="Applied stats query.")
    summary: EventStatsSummary = Field(..., description="Aggregated summary statistics.")


class EventStatsBreakdownBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket_key: str = Field(..., description="Stable bucket identifier.")
    bucket_label: str = Field(..., description="Readable label for the bucket.")
    total_count: int = Field(0, description="All tracked outcome rows in this bucket.")
    settled_count: int = Field(0, description="Settled rows in this bucket.")
    open_count: int = Field(0, description="Pending rows in this bucket.")
    success_count: int = Field(0, description="Success rows in this bucket.")
    failure_count: int = Field(0, description="Failure rows in this bucket.")
    timeout_count: int = Field(0, description="Timeout rows in this bucket.")
    inconclusive_count: int = Field(0, description="Inconclusive rows in this bucket.")
    accuracy_rate: float = Field(0.0, description="Success share across settled rows.")
    failure_rate: float = Field(0.0, description="Failure share across settled rows.")
    timeout_rate: float = Field(0.0, description="Timeout share across settled rows.")
    inconclusive_rate: float = Field(0.0, description="Inconclusive share across settled rows.")


class EventStatsBreakdownEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_EVENT_STATS_BREAKDOWN_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this event-stats breakdown response.")
    ok: bool = Field(True, description="Whether the request succeeded.")
    query: EventStatsQuery = Field(..., description="Applied stats query.")
    dimension: str = Field(..., description="Breakdown dimension, such as event_kind or analysis_preset.")
    buckets: list[EventStatsBreakdownBucket] = Field(default_factory=list, description="Breakdown buckets.")
