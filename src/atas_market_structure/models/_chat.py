from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._replay import ReplayAiChatAttachment


class ChatWindowRange(BaseModel):
    start: datetime = Field(..., description="Inclusive session window start.")
    end: datetime = Field(..., description="Inclusive session window end.")


class ChatSession(BaseModel):
    session_id: str = Field(..., description="Chat session identifier.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    title: str = Field(..., description="User-visible session title.")
    symbol: str = Field(..., description="Instrument symbol.")
    contract_id: str | None = Field(None, description="Instrument contract identifier.")
    timeframe: Timeframe | str = Field(..., description="Session timeframe.")
    window_range: ChatWindowRange = Field(..., description="Replay window bound to this session.")
    active_model: str | None = Field(None, description="Preferred model for this session.")
    status: str = Field("active", description="Session status.")
    draft_text: str = Field("", description="Draft text currently in the composer.")
    draft_attachments: list[ReplayAiChatAttachment] = Field(default_factory=list, description="Draft attachments.")
    selected_prompt_block_ids: list[str] = Field(default_factory=list, description="Selected prompt block ids.")
    pinned_context_block_ids: list[str] = Field(default_factory=list, description="Pinned prompt block ids.")
    include_memory_summary: bool = Field(False, description="Whether to include session memory summary by default.")
    include_recent_messages: bool = Field(False, description="Whether to include recent messages by default.")
    mounted_reply_ids: list[str] = Field(default_factory=list, description="Mounted assistant message ids.")
    active_plan_id: str | None = Field(None, description="Currently highlighted plan id.")
    memory_summary_id: str | None = Field(None, description="Current memory summary id.")
    unread_count: int = Field(0, ge=0, description="Unread assistant message count.")
    scroll_offset: int = Field(0, ge=0, description="Persisted scroll offset.")
    pinned: bool = Field(False, description="Whether the session is pinned in the UI.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class ChatMessage(BaseModel):
    message_id: str = Field(..., description="Message identifier.")
    session_id: str = Field(..., description="Owning session identifier.")
    parent_message_id: str | None = Field(None, description="Optional parent assistant message id for regenerate lineage.")
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role.")
    content: str = Field(..., description="Message content.")
    status: str = Field(..., description="Message status.")
    reply_title: str | None = Field(None, description="Optional short assistant reply title.")
    stream_buffer: str = Field("", description="Temporary streaming buffer.")
    model: str | None = Field(None, description="Model used to generate the assistant reply.")
    annotations: list[str] = Field(default_factory=list, description="Associated annotation ids.")
    plan_cards: list[str] = Field(default_factory=list, description="Associated plan card ids.")
    mounted_to_chart: bool = Field(False, description="Whether this message is mounted to chart.")
    mounted_object_ids: list[str] = Field(default_factory=list, description="Mounted object ids.")
    is_key_conclusion: bool = Field(False, description="Whether the message is marked as key conclusion.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class PromptBlock(BaseModel):
    block_id: str = Field(..., description="Prompt block identifier.")
    session_id: str = Field(..., description="Owning session identifier.")
    symbol: str = Field(..., description="Instrument symbol.")
    contract_id: str | None = Field(None, description="Instrument contract identifier.")
    timeframe: Timeframe | str | None = Field(None, description="Prompt block timeframe.")
    kind: str = Field(..., description="Prompt block kind.")
    title: str = Field(..., description="Prompt block title.")
    preview_text: str = Field(..., description="Compact UI preview for the block.")
    full_payload: dict[str, Any] = Field(default_factory=dict, description="Full payload sent to the model.")
    selected_by_default: bool = Field(False, description="Whether the block should be selected by default.")
    pinned: bool = Field(False, description="Whether the block is pinned in context.")
    ephemeral: bool = Field(True, description="Whether the block is ephemeral and can expire.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    expires_at: datetime | None = Field(None, description="Optional expiry time.")


class SessionMemory(BaseModel):
    memory_summary_id: str = Field(..., description="Memory summary identifier.")
    session_id: str = Field(..., description="Owning session identifier.")
    summary_version: int = Field(1, ge=1, description="Summary version.")
    active_model: str | None = Field(None, description="Active model when summary was produced.")
    symbol: str = Field(..., description="Instrument symbol.")
    contract_id: str | None = Field(None, description="Instrument contract identifier.")
    timeframe: Timeframe | str = Field(..., description="Session timeframe.")
    window_range: ChatWindowRange = Field(..., description="Session replay window.")
    user_goal_summary: str = Field("", description="Stable user goal summary.")
    market_context_summary: str = Field("", description="Current market context summary.")
    key_zones_summary: list[str] = Field(default_factory=list, description="Summarized key zones.")
    active_plans_summary: list[str] = Field(default_factory=list, description="Summarized active plans.")
    invalidated_plans_summary: list[str] = Field(default_factory=list, description="Summarized invalidated plans.")
    important_messages: list[str] = Field(default_factory=list, description="Important message ids.")
    current_user_intent: str = Field("", description="Current user intent summary.")
    latest_question: str = Field("", description="Latest user question.")
    latest_answer_summary: str = Field("", description="Latest answer summary.")
    selected_annotations: list[str] = Field(default_factory=list, description="Selected annotation ids.")
    last_updated_at: datetime = Field(..., description="Last update timestamp.")


class ChatAnnotation(BaseModel):
    annotation_id: str = Field(..., description="Annotation identifier.")
    session_id: str = Field(..., description="Owning session identifier.")
    message_id: str = Field(..., description="Owning message identifier.")
    plan_id: str | None = Field(None, description="Linked plan id when applicable.")
    symbol: str = Field(..., description="Instrument symbol.")
    contract_id: str | None = Field(None, description="Instrument contract identifier.")
    timeframe: Timeframe | str | None = Field(None, description="Annotation timeframe.")
    type: str = Field(..., description="Annotation type.")
    subtype: str | None = Field(None, description="Annotation subtype.")
    label: str = Field(..., description="User-visible label.")
    reason: str = Field("", description="Rationale behind the annotation.")
    start_time: datetime = Field(..., description="Start time.")
    end_time: datetime | None = Field(None, description="End time.")
    expires_at: datetime | None = Field(None, description="Expiry time.")
    status: str = Field("active", description="Lifecycle status.")
    priority: int | None = Field(None, description="Optional display priority.")
    confidence: float | None = Field(None, description="Optional confidence value.")
    visible: bool = Field(True, description="Whether the annotation is visible.")
    pinned: bool = Field(False, description="Whether the annotation is pinned.")
    source_kind: str = Field("replay_analysis", description="Annotation source kind.")
    event_kind: str | None = Field(None, description="Normalized event kind for UI grouping.")
    side: str | None = Field(None, description="Optional trade side.")
    entry_price: float | None = Field(None, description="Optional entry price.")
    stop_price: float | None = Field(None, description="Optional stop price.")
    target_price: float | None = Field(None, description="Optional target price.")
    tp_level: int | None = Field(None, description="Optional take-profit level.")
    price_low: float | None = Field(None, description="Optional zone low.")
    price_high: float | None = Field(None, description="Optional zone high.")
    path_points: list[dict[str, Any]] = Field(default_factory=list, description="Optional path points.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Raw object payload.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class ChatPlanCard(BaseModel):
    plan_id: str = Field(..., description="Plan identifier.")
    session_id: str = Field(..., description="Owning session identifier.")
    message_id: str = Field(..., description="Owning message identifier.")
    title: str = Field(..., description="Plan title.")
    side: str = Field(..., description="Trade side.")
    entry_type: str | None = Field(None, description="Entry type.")
    entry_price: float | None = Field(None, description="Entry price.")
    entry_price_low: float | None = Field(None, description="Entry range low.")
    entry_price_high: float | None = Field(None, description="Entry range high.")
    stop_price: float | None = Field(None, description="Stop price.")
    take_profits: list[dict[str, Any]] = Field(default_factory=list, description="Take profit definitions.")
    invalidations: list[str] = Field(default_factory=list, description="Invalidation rules.")
    time_validity: str | None = Field(None, description="Plan validity duration.")
    risk_reward: float | None = Field(None, description="Risk reward estimate.")
    confidence: float | None = Field(None, description="Optional confidence.")
    priority: int | None = Field(None, description="Optional priority.")
    status: str = Field("active", description="Plan lifecycle status.")
    source_kind: str = Field("replay_analysis", description="Plan source kind.")
    notes: str = Field("", description="Plan notes.")
    payload: dict[str, Any] = Field(default_factory=dict, description="Raw plan payload.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class CreateChatSessionRequest(BaseModel):
    workspace_id: str = Field("replay_main", description="Workspace identifier.")
    title: str = Field("新会话", description="Initial session title.")
    symbol: str = Field(..., description="Instrument symbol.")
    contract_id: str | None = Field(None, description="Instrument contract identifier.")
    timeframe: Timeframe | str = Field(..., description="Session timeframe.")
    window_range: ChatWindowRange = Field(..., description="Replay window range.")
    active_model: str | None = Field(None, description="Initial active model.")
    start_blank: bool = Field(True, description="Whether to start with no history or injected context.")


class UpdateChatSessionRequest(BaseModel):
    title: str | None = Field(None, description="Updated title.")
    active_model: str | None = Field(None, description="Updated active model.")
    pinned: bool | None = Field(None, description="Updated pinned state.")
    mounted_reply_ids: list[str] | None = Field(None, description="Mounted reply ids.")
    selected_prompt_block_ids: list[str] | None = Field(None, description="Selected prompt block ids.")
    pinned_context_block_ids: list[str] | None = Field(None, description="Pinned prompt block ids.")
    include_memory_summary: bool | None = Field(None, description="Whether to include session memory summary by default.")
    include_recent_messages: bool | None = Field(None, description="Whether to include recent messages by default.")
    draft_text: str | None = Field(None, description="Draft text.")
    draft_attachments: list[ReplayAiChatAttachment] | None = Field(None, description="Draft attachments.")
    active_plan_id: str | None = Field(None, description="Active plan id.")
    status: str | None = Field(None, description="Session status.")


class CreateChatMessageRequest(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role.")
    content: str = Field(..., min_length=1, description="Message content.")
    attachments: list[ReplayAiChatAttachment] = Field(default_factory=list, description="Attachments.")
    selected_block_ids: list[str] = Field(default_factory=list, description="Selected block ids.")


class BuildPromptBlocksRequest(BaseModel):
    candidates: list[str] = Field(default_factory=list, description="Prompt block kinds to build.")


class ChatReplyRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="Current user input.")
    selected_block_ids: list[str] = Field(default_factory=list, description="Selected block ids.")
    pinned_block_ids: list[str] = Field(default_factory=list, description="Pinned block ids.")
    include_memory_summary: bool = Field(False, description="Whether to inject session memory summary.")
    include_recent_messages: bool = Field(False, description="Whether to inject recent messages.")
    model: str | None = Field(None, description="Requested model override.")
    preset: str = Field("general", description="Analysis preset.")
    analysis_type: str | None = Field(None, description="Optional structured analysis intent.")
    analysis_range: str | None = Field(None, description="Optional analysis range hint.")
    analysis_style: str | None = Field(None, description="Optional style hint for reply shaping.")
    extra_context: dict[str, Any] | None = Field(None, description="Optional extra context from UI/runtime.")
    attachments: list[ReplayAiChatAttachment] = Field(default_factory=list, description="User attachments.")
    replay_ingestion_id: str | None = Field(None, description="Replay ingestion identifier used to resolve current snapshot.")


class ChatReplyResponse(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    session: ChatSession = Field(..., description="Updated session snapshot.")
    user_message: ChatMessage = Field(..., description="Stored user message.")
    assistant_message: ChatMessage = Field(..., description="Stored assistant message.")
    annotations: list[ChatAnnotation] = Field(default_factory=list, description="Generated annotations.")
    plan_cards: list[ChatPlanCard] = Field(default_factory=list, description="Generated plan cards.")
    memory: SessionMemory | None = Field(None, description="Updated session memory.")
    reply_text: str = Field(..., description="Convenience assistant reply text.")
    provider: str | None = Field(None, description="AI provider used.")
    model: str | None = Field(None, description="AI model used.")
    preset: str = Field(..., description="Preset used for the reply.")
    referenced_strategy_ids: list[str] = Field(default_factory=list, description="Referenced strategy ids.")
    live_context_summary: list[str] = Field(default_factory=list, description="Live context summary items.")
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Follow-up suggestions.")
    attachment_summaries: list[str] = Field(default_factory=list, description="Attachment summaries.")
    session_only: bool = Field(False, description="Whether the reply was generated without replay snapshot context.")


class ChatSessionEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    session: ChatSession = Field(..., description="Session record.")


class ChatSessionsEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    sessions: list[ChatSession] = Field(default_factory=list, description="Session records.")


class ChatMessagesEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    messages: list[ChatMessage] = Field(default_factory=list, description="Message records.")


class PromptBlocksEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    blocks: list[PromptBlock] = Field(default_factory=list, description="Prompt block records.")


class SessionMemoryEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    memory: SessionMemory | None = Field(None, description="Session memory record.")


class ChatLifecycleEvaluateRequest(BaseModel):
    bars: list[dict[str, Any]] = Field(default_factory=list, description="Bars used for lifecycle evaluation.")
    live_tail: dict[str, Any] | None = Field(None, description="Optional live tail snapshot.")
    object_ids: list[str] = Field(default_factory=list, description="Object ids to evaluate.")


class ChatLifecycleTransition(BaseModel):
    object_id: str = Field(..., description="Object identifier.")
    from_status: str = Field(..., description="Previous lifecycle status.")
    to_status: str = Field(..., description="Next lifecycle status.")
    event: str = Field(..., description="Transition event.")


class ChatLifecycleEvaluateResponse(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    transitions: list[ChatLifecycleTransition] = Field(default_factory=list, description="Lifecycle transitions.")


class ChatHandoffRequest(BaseModel):
    target_model: str | None = Field(None, description="Target model for handoff.")
    mode: Literal["question_only", "summary_only", "summary_plus_recent_3"] = Field(
        "summary_plus_recent_3",
        description="Handoff mode.",
    )


class ChatHandoffPacket(BaseModel):
    session_meta: dict[str, Any] = Field(default_factory=dict, description="Session metadata.")
    memory_summary: dict[str, Any] = Field(default_factory=dict, description="Session memory snapshot.")
    recent_messages: list[dict[str, Any]] = Field(default_factory=list, description="Recent messages included in handoff.")
    active_annotations: list[dict[str, Any]] = Field(default_factory=list, description="Active annotations.")
    active_plans: list[dict[str, Any]] = Field(default_factory=list, description="Active plans.")


class ChatHandoffResponse(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    handoff_packet: ChatHandoffPacket = Field(..., description="Generated handoff packet.")


class UpdateMountedMessageRequest(BaseModel):
    mounted_to_chart: bool = Field(..., description="Whether to mount the message to chart.")
    mount_mode: Literal["append", "replace", "focus_only"] = Field("replace", description="Mount behavior.")
    mounted_object_ids: list[str] = Field(default_factory=list, description="Mounted object ids.")


class ChatObjectsEnvelope(BaseModel):
    ok: bool = Field(True, description="Whether the request succeeded.")
    annotations: list[ChatAnnotation] = Field(default_factory=list, description="Annotation records.")
    plan_cards: list[ChatPlanCard] = Field(default_factory=list, description="Plan card records.")
    mounted_to_chart: bool = Field(False, description="Whether the source message is mounted.")
    mounted_object_ids: list[str] = Field(default_factory=list, description="Mounted object ids.")
