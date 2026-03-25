from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._schema_versions import (
    PROMPT_TRACE_SCHEMA_VERSION,
    WORKBENCH_PROMPT_TRACE_ENVELOPE_SCHEMA_VERSION,
    WORKBENCH_PROMPT_TRACE_LIST_ENVELOPE_SCHEMA_VERSION,
    CanonicalSchemaVersionedModel,
)


class PromptTraceBlockSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(..., description="Prompt block identifier.")
    kind: str = Field(..., description="Prompt block kind.")
    title: str = Field(..., description="Prompt block title.")
    preview_text: str = Field("", description="Compact preview text shown in the UI.")
    payload_summary: dict[str, Any] = Field(default_factory=dict, description="Readable payload summary for the block.")


class PromptTrace(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = PROMPT_TRACE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this prompt trace.")
    prompt_trace_id: str = Field(..., description="Prompt trace identifier.")
    session_id: str = Field(..., description="Owning chat session identifier.")
    message_id: str = Field(..., description="Assistant message identifier linked to the trace.")
    symbol: str = Field(..., description="Instrument symbol.")
    timeframe: Timeframe | str = Field(..., description="Trace timeframe.")
    analysis_type: str | None = Field(None, description="Structured analysis type hint.")
    analysis_range: str | None = Field(None, description="Structured analysis range hint.")
    analysis_style: str | None = Field(None, description="Structured analysis style hint.")
    selected_block_ids: list[str] = Field(default_factory=list, description="Explicitly selected prompt block ids.")
    pinned_block_ids: list[str] = Field(default_factory=list, description="Pinned prompt block ids.")
    attached_event_ids: list[str] = Field(default_factory=list, description="Event candidate ids linked after reply extraction.")
    prompt_block_summaries: list[PromptTraceBlockSummary] = Field(
        default_factory=list,
        description="Readable summaries of the prompt blocks used for this request.",
    )
    bar_window_summary: dict[str, Any] = Field(default_factory=dict, description="Summary of the bar window supplied.")
    manual_selection_summary: dict[str, Any] = Field(default_factory=dict, description="Summary of manual region/bar selection context.")
    memory_summary: dict[str, Any] = Field(default_factory=dict, description="Summary of session memory and recent-message context.")
    final_system_prompt: str = Field("", description="Final system prompt snapshot sent to the model.")
    final_user_prompt: str = Field("", description="Final user prompt snapshot sent to the model.")
    model_name: str | None = Field(None, description="Resolved model name used for the request.")
    model_input_hash: str = Field(..., description="Stable hash of the model input snapshot.")
    snapshot: dict[str, Any] = Field(default_factory=dict, description="Expanded input snapshot for trace replay/debug.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additive metadata and truncation markers.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class PromptTraceEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_PROMPT_TRACE_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this prompt-trace response.")
    ok: bool = Field(True, description="Whether the request succeeded.")
    trace: PromptTrace = Field(..., description="Prompt trace record.")


class PromptTraceListEnvelope(CanonicalSchemaVersionedModel):
    model_config = ConfigDict(extra="forbid")
    canonical_schema_version = WORKBENCH_PROMPT_TRACE_LIST_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(..., description="Schema version for this prompt-trace list response.")
    ok: bool = Field(True, description="Whether the request succeeded.")
    traces: list[PromptTrace] = Field(default_factory=list, description="Prompt trace records.")
