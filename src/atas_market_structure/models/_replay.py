from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from atas_market_structure.models._adapter_states import (
    AdapterInitiativeDriveState,
    AdapterPostHarvestResponseState,
    AdapterSamePriceReplenishmentState,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
)
from atas_market_structure.models._enums import (
    DegradedMode,
    EpisodeResolution,
    EventHypothesisKind,
    EventPhase,
    EvaluationFailureMode,
    RecognitionMode,
    RegimeKind,
    ReplayAcquisitionMode,
    ReplayVerificationStatus,
    ReviewSource,
    RollMode,
    StructureSide,
    Timeframe,
    TradableEventKind,
)
from atas_market_structure.models._refs import InstrumentRef, SourceRef


class ReplayAiBriefing(BaseModel):
    """Compact AI briefing packet derived from replay events and strategy-library matches."""

    objective: str = Field(
        ...,
        description="What the AI should decide or highlight for the operator.",
        examples=["Identify the most defensible support and resistance zones from the last 5 sessions."],
    )
    focus_questions: list[str] = Field(default_factory=list, description="Specific questions that the AI should answer.")
    required_outputs: list[str] = Field(default_factory=list, description="Expected output sections for the AI response.")
    notes: list[str] = Field(default_factory=list, description="Additional operator instructions preserved in the packet.")



class ReplayAiChatAttachment(BaseModel):
    """Optional image attachment sent with one replay-workbench AI chat request."""

    name: str | None = Field(None, description="Optional attachment name shown in the UI.")
    media_type: str = Field(..., description="Attachment MIME type.", examples=["image/png"])
    data_url: str = Field(..., min_length=16, description="Inline data URL used for lightweight pasted screenshots.")



class ReplayAiChatPlanCandidate(BaseModel):
    title: str | None = Field(None, description="Optional plan title.")
    side: str | None = Field(None, description="Trade side.")
    entry_price: float | None = Field(None, description="Entry price.")
    entry_price_low: float | None = Field(None, description="Entry range low.")
    entry_price_high: float | None = Field(None, description="Entry range high.")
    stop_price: float | None = Field(None, description="Stop price.")
    take_profits: list[dict[str, Any]] = Field(default_factory=list, description="Take profit definitions.")
    invalidations: list[str] = Field(default_factory=list, description="Invalidation rules.")
    summary: str | None = Field(None, description="Short plan summary.")
    notes: str | None = Field(None, description="Plan notes.")
    confidence: float | None = Field(None, description="Optional confidence.")
    priority: int | None = Field(None, description="Optional priority.")
    supporting_zones: list[dict[str, Any]] = Field(default_factory=list, description="Supporting zones.")


class ReplayAiChatAnnotationCandidate(BaseModel):
    type: str = Field(..., description="Annotation type.")
    subtype: str | None = Field(None, description="Annotation subtype.")
    label: str | None = Field(None, description="Annotation label.")
    reason: str | None = Field(None, description="Annotation reason.")
    start_time: datetime | None = Field(None, description="Optional start time.")
    end_time: datetime | None = Field(None, description="Optional end time.")
    expires_at: datetime | None = Field(None, description="Optional expiry time.")
    status: str | None = Field(None, description="Optional status.")
    priority: int | None = Field(None, description="Optional priority.")
    confidence: float | None = Field(None, description="Optional confidence.")
    visible: bool = Field(True, description="Whether annotation is visible.")
    pinned: bool = Field(False, description="Whether annotation is pinned.")
    source_kind: str | None = Field(None, description="Source kind.")
    side: str | None = Field(None, description="Optional side.")
    entry_price: float | None = Field(None, description="Optional entry price.")
    stop_price: float | None = Field(None, description="Optional stop price.")
    target_price: float | None = Field(None, description="Optional target price.")
    tp_level: int | None = Field(None, description="Optional take-profit level.")
    price_low: float | None = Field(None, description="Optional zone low.")
    price_high: float | None = Field(None, description="Optional zone high.")
    path_points: list[dict[str, Any]] = Field(default_factory=list, description="Optional path points.")


class ReplayAiChatContent(BaseModel):
    """Structured AI chat payload returned by the provider before persistence."""

    reply_text: str = Field(..., description="Assistant reply shown in the UI.")
    live_context_summary: list[str] = Field(default_factory=list, description="Short live-context facts attached to this turn.")
    referenced_strategy_ids: list[str] = Field(default_factory=list, description="Strategy-library candidates considered for this turn.")
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Suggested follow-up prompts for the operator.")
    attachment_summaries: list[str] = Field(default_factory=list, description="Short summaries of user-provided image attachments.")
    plan_cards: list[ReplayAiChatPlanCandidate] = Field(default_factory=list, description="Optional structured plan cards.")
    annotations: list[ReplayAiChatAnnotationCandidate] = Field(default_factory=list, description="Optional structured annotations.")



class ReplayAiChatMessage(BaseModel):
    """Conversation turn shown in the replay workbench AI pane."""

    role: Literal["user", "assistant"] = Field(..., description="Conversation role.")
    content: str = Field(..., description="Message content.")



class ReplayAiChatPreset(str, Enum):
    GENERAL = "general"
    RECENT_20_BARS = "recent_20_bars"
    RECENT_20_MINUTES = "recent_20_minutes"
    FOCUS_REGIONS = "focus_regions"
    TRAPPED_LARGE_ORDERS = "trapped_large_orders"
    LIVE_DEPTH = "live_depth"



class ReplayAiChatRequest(BaseModel):
    """Request for contextual AI conversation over one replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier to discuss.")
    preset: ReplayAiChatPreset = Field(ReplayAiChatPreset.GENERAL, description="Preset analysis lens for this request.")
    user_message: str = Field(..., min_length=1, description="Latest user question or instruction.")
    history: list[ReplayAiChatMessage] = Field(default_factory=list, description="Previous chat turns to preserve continuity.")
    model_override: str | None = Field(None, description="Optional AI model override for this request.")
    include_live_context: bool = Field(True, description="Whether to merge the latest live adapter context into the discussion.")
    attachments: list[ReplayAiChatAttachment] = Field(
        default_factory=list,
        description="Optional pasted screenshots or chart snippets attached to the question.",
    )



class ReplayAiChatResponse(BaseModel):
    """Stored result of one replay-workbench AI conversation turn."""

    ingestion_id: str = Field(..., description="Stored AI-chat ingestion identifier.")
    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay snapshot identifier.")
    generated_at: datetime = Field(..., description="Persistence timestamp.")
    provider: str = Field(..., description="AI provider identifier.")
    model: str = Field(..., description="Model name used to generate the answer.")
    preset: ReplayAiChatPreset = Field(..., description="Preset analysis lens used for this turn.")
    request_message: str = Field(..., description="Latest user prompt submitted for this turn.")
    reply_text: str = Field(..., description="Assistant reply shown in the UI.")
    live_context_summary: list[str] = Field(default_factory=list, description="Short live-context facts attached to this turn.")
    referenced_strategy_ids: list[str] = Field(default_factory=list, description="Strategy-library candidates considered for this turn.")
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Suggested follow-up prompts for the operator.")
    attachment_summaries: list[str] = Field(default_factory=list, description="Short summaries of user-provided image attachments.")
    plan_cards: list[ReplayAiChatPlanCandidate] = Field(default_factory=list, description="Structured plan cards returned by the model.")
    annotations: list[ReplayAiChatAnnotationCandidate] = Field(default_factory=list, description="Structured annotations returned by the model.")
    raw_text: str = Field(..., description="Provider raw text output preserved for debugging and audit.")



class ReplayAiEntryReview(BaseModel):
    """AI review over one operator-recorded entry inside the replay window."""

    entry_id: str = Field(..., description="Operator-entry identifier being reviewed.")
    verdict: str = Field(..., description="Compact verdict such as valid, weak, late, or avoid.")
    context_alignment_score: float = Field(..., ge=0.0, le=1.0, description="How well the entry aligned with broader and local context.")
    rationale: list[str] = Field(default_factory=list, description="Evidence supporting the verdict.")
    mistakes: list[str] = Field(default_factory=list, description="Specific mistakes or weaknesses in the entry.")
    better_conditions: list[str] = Field(default_factory=list, description="What the operator should have waited for instead.")



class ReplayAiInvalidationReview(BaseModel):
    """AI-specified invalidation level tied to the replay context."""

    label: str = Field(..., description="Short invalidation label.")
    price: float = Field(..., description="Invalidation price.")
    reason: str = Field(..., description="Why a break of this price matters.")



class ReplayAiReviewContent(BaseModel):
    """Structured AI output returned for one replay packet."""

    narrative_summary: str = Field(..., description="Compact narrative summary of the replay context.")
    key_zones: list[ReplayAiZoneReview] = Field(default_factory=list, description="Ranked support, resistance, or pivot zones.")
    script_review: ReplayAiScriptReview = Field(..., description="Continuation versus reversal review.")
    entry_reviews: list[ReplayAiEntryReview] = Field(default_factory=list, description="Per-entry review for operator-recorded openings.")
    invalidations: list[ReplayAiInvalidationReview] = Field(default_factory=list, description="Invalidation levels to monitor.")
    no_trade_guidance: list[str] = Field(default_factory=list, description="Conditions or zones where the operator should avoid opening.")
    unresolved_conflicts: list[str] = Field(default_factory=list, description="Conflicts or ambiguities the operator should watch.")
    operator_focus: list[str] = Field(default_factory=list, description="Short operator-facing reminders.")



class ReplayAiReviewRequest(BaseModel):
    """Request to run AI review for one stored replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier to review.")
    model_override: str | None = Field(None, description="Optional AI model override for this request.")
    force_refresh: bool = Field(False, description="Whether to ignore previously stored AI reviews and generate a new one.")



class ReplayAiReviewResponse(BaseModel):
    """Stored result of an AI review over one replay-workbench packet."""

    ingestion_id: str = Field(..., description="Stored AI-review ingestion identifier.")
    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier reviewed by the model.")
    replay_snapshot_id: str = Field(..., description="Replay snapshot identifier reviewed by the model.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    provider: str = Field(..., description="AI provider identifier.")
    model: str = Field(..., description="Model name used to generate the review.")
    review: ReplayAiReviewContent = Field(..., description="Structured AI review content.")
    raw_text: str = Field(..., description="Provider raw text output preserved for debugging and audit.")



class ReplayAiScriptReview(BaseModel):
    """AI comparison of continuation and reversal scripts for the replay window."""

    preferred_script: str = Field(..., description="Preferred script label, for example continuation, reversal, or neutral.")
    continuation_case: list[str] = Field(default_factory=list, description="Evidence supporting the continuation case.")
    reversal_case: list[str] = Field(default_factory=list, description="Evidence supporting the reversal case.")
    preferred_rationale: list[str] = Field(default_factory=list, description="Why the preferred script currently dominates.")



class ReplayAiZoneReview(BaseModel):
    """AI-ranked key zone derived from replay context."""

    label: str = Field(..., description="Short label for the reviewed zone.")
    zone_low: float = Field(..., description="Lower zone boundary.")
    zone_high: float = Field(..., description="Upper zone boundary.")
    role: str = Field(..., description="Zone role such as support, resistance, pivot, or liquidity magnet.")
    strength_score: float = Field(..., ge=0.0, le=1.0, description="AI-ranked zone strength.")
    evidence: list[str] = Field(default_factory=list, description="Observed evidence backing the zone.")



class ReplayCachePolicy(BaseModel):
    """Replay cache policy controlling when ATAS should be queried and when snapshots become durable."""

    fetch_only_when_missing: bool = Field(
        True,
        description="Only fetch from ATAS when the replay packet is missing from local storage.",
    )
    max_verifications_per_day: int = Field(
        1,
        ge=1,
        description="Maximum number of verification passes allowed per day.",
    )
    verification_passes_to_lock: int = Field(
        3,
        ge=1,
        description="How many successful verifications are required before the replay packet is locked as durable.",
    )
    manual_reimport_required_after_invalidation: bool = Field(
        True,
        description="Whether replay acquisition must stay disabled until the operator explicitly re-enables it after invalidation.",
    )



class ReplayChartBar(BaseModel):
    """Chart bar reconstructed for the standalone replay workbench UI."""

    started_at: datetime = Field(..., description="Inclusive bar start timestamp.")
    ended_at: datetime = Field(..., description="Inclusive bar end timestamp.")
    open: float = Field(..., description="Bar open.", examples=[21540.25])
    high: float = Field(..., description="Bar high.", examples=[21548.0])
    low: float = Field(..., description="Bar low.", examples=[21535.5])
    close: float = Field(..., description="Bar close.", examples=[21544.75])
    volume: int | None = Field(None, ge=0, description="Optional total volume for the bar.", examples=[842])
    delta: int | None = Field(None, description="Optional net delta for the bar.", examples=[121])
    bid_volume: int | None = Field(None, ge=0, description="Optional bid-side traded volume.", examples=[360])
    ask_volume: int | None = Field(None, ge=0, description="Optional ask-side traded volume.", examples=[481])
    source_kind: str | None = Field(
        None,
        description="Normalized candle source, for example history_bars, continuous_state, chart_candles, or synthetic_gap_fill.",
    )
    is_synthetic: bool = Field(False, description="Whether this candle is synthetic gap-fill rather than observed market data.")
    bar_timestamp_utc: datetime | None = Field(
        None,
        description="UTC-normalised bar timestamp preserved from ATAS metadata before timezone normalisation.",
    )
    original_bar_time_text: str | None = Field(
        None,
        description="Raw bar time text string as it appeared in ATAS before any timezone interpretation.",
        examples=["2026-03-17 09:30:00 EST"],
    )



class AtasChartBarRaw(BaseModel):
    """Raw ATAS chart bar mirrored exactly as received from one chart instance."""

    chart_instance_id: str | None = Field(None, description="ATAS chart-instance identifier when known.")
    root_symbol: str | None = Field(None, description="Root or continuous symbol when known.")
    contract_symbol: str | None = Field(None, description="Resolved contract symbol when known.")
    symbol: str = Field(..., description="Display symbol as emitted by the adapter.")
    venue: str | None = Field(None, description="Execution or quote venue when known.")
    timeframe: Timeframe = Field(..., description="Native timeframe of the mirrored chart bars.")
    started_at_utc: datetime = Field(..., description="UTC-normalized bar start used as the primary time key.")
    ended_at_utc: datetime = Field(..., description="UTC-normalized bar end.")
    source_started_at: datetime = Field(
        ...,
        description="Original source bar start preserved alongside the UTC key.",
    )
    original_bar_time_text: str | None = Field(
        None,
        description="Raw bar time text as it appeared in ATAS before timezone normalization.",
    )
    timestamp_basis: str | None = Field(None, description="Primary basis used to normalize timestamps to UTC.")
    chart_display_timezone_mode: str | None = Field(None, description="ATAS chart display timezone mode when known.")
    chart_display_timezone_name: str | None = Field(None, description="ATAS chart display timezone name when known.")
    chart_display_utc_offset_minutes: int | None = Field(None, description="Chart display UTC offset in minutes.")
    instrument_timezone_value: str | None = Field(None, description="Raw instrument timezone metadata value.")
    instrument_timezone_source: str | None = Field(None, description="Where the instrument timezone came from.")
    collector_local_timezone_name: str | None = Field(None, description="Collector machine local timezone name.")
    collector_local_utc_offset_minutes: int | None = Field(None, description="Collector machine local UTC offset in minutes.")
    timezone_capture_confidence: str | None = Field(None, description="Confidence level of the timezone capture.")
    open: float = Field(..., description="Bar open.")
    high: float = Field(..., description="Bar high.")
    low: float = Field(..., description="Bar low.")
    close: float = Field(..., description="Bar close.")
    volume: int | None = Field(None, ge=0, description="Optional total volume.")
    bid_volume: int | None = Field(None, ge=0, description="Optional bid-side volume.")
    ask_volume: int | None = Field(None, ge=0, description="Optional ask-side volume.")
    delta: int | None = Field(None, description="Optional net delta.")
    trade_count: int | None = Field(None, ge=0, description="Optional trade count.")
    updated_at: datetime = Field(..., description="When this raw mirror row was last updated.")


class ChartCandle(BaseModel):
    """Pre-aggregated OHLCV candle stored in a dedicated chart-candles table.

    This table is the single source of truth for rendering charts.
    Aggregation happens incrementally in the background — the UI only reads
    pre-computed OHLCV rows and never aggregates on load.
    """

    symbol: str = Field(..., description="Instrument symbol, e.g. 'NQ'.", examples=["NQ"])
    timeframe: Timeframe = Field(..., description="Bar timeframe.")
    started_at: datetime = Field(..., description="Inclusive bar start in UTC.")
    ended_at: datetime = Field(..., description="Inclusive bar end in UTC.")
    source_started_at: datetime | None = Field(
        None,
        description="Original source-bar start in UTC, used to preserve open/close ordering during append-only storage.",
    )
    open: float = Field(..., description="Bar open price.", examples=[21540.25])
    high: float = Field(..., description="Bar high price.", examples=[21548.0])
    low: float = Field(..., description="Bar low price.", examples=[21535.5])
    close: float = Field(..., description="Bar close price.", examples=[21544.75])
    volume: int = Field(default=0, ge=0, description="Total traded volume for the bar.")
    tick_volume: int = Field(default=0, ge=0, description="Total tick count for the bar.")
    delta: int = Field(default=0, description="Net buy-sell volume (bid_fill - ask_fill).")
    updated_at: datetime = Field(..., description="When this row was last updated.")
    source_timezone: str | None = Field(
        None,
        description="Original timezone of the source bar before UTC normalisation (e.g. 'America/New_York', 'EST').",
    )

    model_config = {"frozen": False}


class ChartCandleUpsertRequest(BaseModel):
    """Request to upsert one or more chart candles."""

    candles: list[ChartCandle] = Field(..., description="Candles to upsert.")


class ChartCandleEnvelope(BaseModel):
    """REST response envelope for chart candle queries."""

    symbol: str = Field(..., description="Instrument symbol.")
    timeframe: Timeframe = Field(..., description="Timeframe of returned candles.")
    window_start: datetime = Field(..., description="Query window start (inclusive).")
    window_end: datetime = Field(..., description="Query window end (inclusive).")
    count: int = Field(..., description="Number of candles returned.")
    candles: list[ChartCandle] = Field(default_factory=list, description="Matching chart candles.")


class ChartCandleBackfillRequest(BaseModel):
    """Request to trigger a full historical backfill of chart candles for a symbol."""

    symbol: str = Field(..., description="Instrument symbol to backfill.")
    from_timeframe: Timeframe = Field(
        default=Timeframe.MIN_1,
        description="Source timeframe to aggregate from.",
    )
    to_timeframes: list[Timeframe] = Field(
        default_factory=lambda: [
            Timeframe.MIN_1,
            Timeframe.MIN_5,
            Timeframe.MIN_15,
            Timeframe.MIN_30,
            Timeframe.HOUR_1,
            Timeframe.HOUR_4,
        ],
        description="Target timeframes to write into chart_candles.",
    )


class ChartCandleBackfillEnvelope(BaseModel):
    """REST response after triggering a chart candle backfill."""

    symbol: str = Field(..., description="Instrument symbol that was backfilled.")
    backfill_started: datetime = Field(..., description="When the backfill job started.")
    bars_aggregated: int = Field(default=0, description="Number of source bars processed.")
    candles_written: int = Field(default=0, description="Number of chart candle rows written.")


class MirrorBarsEnvelope(BaseModel):
    """REST response for mirror (raw contract) bar queries.

    Mirror bars return the raw contract data exactly as stored, without
    any continuous or roll adjustments. This is the "true" contract view.
    """

    chart_instance_id: str | None = Field(None, description="ATAS chart-instance filter when specified.")
    contract_symbol: str = Field(..., description="Contract symbol queried.")
    timeframe: Timeframe = Field(..., description="Bar timeframe.")
    window_start: datetime = Field(..., description="Query window start (inclusive).")
    window_end: datetime = Field(..., description="Query window end (inclusive).")
    count: int = Field(default=0, description="Number of bars returned.")
    bars: list[ReplayChartBar] = Field(default_factory=list, description="Raw contract bars.")


class ContinuousBarsEnvelope(BaseModel):
    """REST response for continuous-series bar queries.

    Continuous bars return price bars adjusted for contract rolls,
    providing a seamless series across expiration dates. The roll_mode
    parameter controls how adjustments are applied.
    """

    root_symbol: str = Field(..., description="Root/continuous symbol queried.")
    timeframe: Timeframe = Field(..., description="Bar timeframe.")
    roll_mode: RollMode = Field(..., description="Roll mode used for this continuous series.")
    window_start: datetime = Field(..., description="Query window start (inclusive).")
    window_end: datetime = Field(..., description="Query window end (inclusive).")
    count: int = Field(default=0, description="Number of bars returned.")
    bars: list[ReplayChartBar] = Field(default_factory=list, description="Continuous-series bars.")


class ReplayEventAnnotation(BaseModel):
    """Structured event marker rendered as an overlay on the replay UI."""

    event_id: str = Field(..., description="Stable event identifier.")
    event_kind: str = Field(..., description="Event family or pattern key.", examples=["initiative_drive", "gap_first_touch"])
    source_kind: str = Field(
        ...,
        description="Where this event came from, for example collector, strategy_library, manual_review, or ai_review.",
        examples=["collector"],
    )
    observed_at: datetime = Field(..., description="Timestamp of the event marker.")
    price: float | None = Field(None, description="Primary event price.", examples=[21544.75])
    price_low: float | None = Field(None, description="Lower bound when the event spans a zone.", examples=[21542.0])
    price_high: float | None = Field(None, description="Upper bound when the event spans a zone.", examples=[21545.0])
    side: StructureSide | None = Field(None, description="Associated directional side when applicable.")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Optional source-side confidence.", examples=[0.74])
    linked_ids: list[str] = Field(default_factory=list, description="Linked event, drive, zone, or strategy identifiers.")
    notes: list[str] = Field(default_factory=list, description="Short render-ready notes shown in the UI.")



class ReplayFocusRegion(BaseModel):
    """Price region highlighted for operator review and AI focus."""

    region_id: str = Field(..., description="Stable focus-region identifier.")
    label: str = Field(..., description="Short UI label for the region.", examples=["Europe defended bid"])
    started_at: datetime = Field(..., description="When this region became relevant.")
    ended_at: datetime | None = Field(None, description="When this region stopped being relevant, if known.")
    price_low: float = Field(..., description="Lower boundary of the highlighted region.", examples=[21538.0])
    price_high: float = Field(..., description="Upper boundary of the highlighted region.", examples=[21544.0])
    priority: int = Field(..., ge=0, le=10, description="Priority for UI emphasis.", examples=[8])
    reason_codes: list[str] = Field(default_factory=list, description="Compact reason tags behind the focus region.")
    linked_event_ids: list[str] = Field(default_factory=list, description="Events that justify this focus region.")
    notes: list[str] = Field(default_factory=list, description="Human-readable notes for the workbench sidebar.")



class ReplayFootprintBarDetail(BaseModel):
    """Footprint detail for one selected replay bar."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol.")
    timeframe: Timeframe = Field(..., description="Timeframe of the selected bar.")
    started_at: datetime = Field(..., description="Bar start timestamp.")
    ended_at: datetime = Field(..., description="Bar end timestamp.")
    open: float = Field(..., description="Bar open.")
    high: float = Field(..., description="Bar high.")
    low: float = Field(..., description="Bar low.")
    close: float = Field(..., description="Bar close.")
    volume: int | None = Field(None, ge=0, description="Bar total volume.")
    delta: int | None = Field(None, description="Bar net delta.")
    bid_volume: int | None = Field(None, ge=0, description="Bar bid volume.")
    ask_volume: int | None = Field(None, ge=0, description="Bar ask volume.")
    price_levels: list[ReplayFootprintLevelDetail] = Field(default_factory=list, description="Price-level footprint detail.")



class ReplayFootprintLevelDetail(BaseModel):
    """One footprint price level rendered for a selected replay bar."""

    price: float = Field(..., description="Price level.")
    bid_volume: int | None = Field(None, ge=0, description="Bid-side traded volume.")
    ask_volume: int | None = Field(None, ge=0, description="Ask-side traded volume.")
    total_volume: int | None = Field(None, ge=0, description="Total traded volume.")
    delta: int | None = Field(None, description="Net delta at the price level.")
    trade_count: int | None = Field(None, ge=0, description="Trade count at the price level.")



class ReplayLiveStreamState(str, Enum):
    LIVE = "live"
    DELAYED = "delayed"
    STALE = "stale"
    OFFLINE = "offline"



class ReplayManualRegionAnnotationAcceptedResponse(BaseModel):
    """REST response after a manual chart region is stored."""

    region: ReplayManualRegionAnnotationRecord = Field(..., description="Stored manual region annotation.")



class ReplayManualRegionAnnotationEnvelope(BaseModel):
    """REST response listing manual chart regions for one replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    regions: list[ReplayManualRegionAnnotationRecord] = Field(default_factory=list, description="Stored manual chart regions.")



class ReplayManualRegionAnnotationRecord(BaseModel):
    """Operator-defined region and hypothesis drawn on the standalone replay chart."""

    region_annotation_id: str = Field(..., description="Stable manual-region identifier.")
    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay snapshot identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol.")
    label: str = Field(..., description="Short region label.")
    thesis: str = Field(..., description="Operator hypothesis about this region.")
    price_low: float = Field(..., description="Lower bound of the manual region.")
    price_high: float = Field(..., description="Upper bound of the manual region.")
    started_at: datetime = Field(..., description="Lower time boundary of the region.")
    ended_at: datetime = Field(..., description="Upper time boundary of the region.")
    side_bias: StructureSide | None = Field(None, description="Optional directional bias attached by the operator.")
    notes: list[str] = Field(default_factory=list, description="Additional operator notes for this region.")
    tags: list[str] = Field(default_factory=list, description="Optional tags such as support, trap, trapped_inventory.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")



class ReplayManualRegionAnnotationRequest(BaseModel):
    """Request to store one operator-defined chart region."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    label: str = Field(..., min_length=1, description="Short region label.")
    thesis: str = Field(..., min_length=1, description="Operator hypothesis about this region.")
    price_low: float = Field(..., description="Lower bound of the manual region.")
    price_high: float = Field(..., description="Upper bound of the manual region.")
    started_at: datetime = Field(..., description="Lower time boundary of the region.")
    ended_at: datetime = Field(..., description="Upper time boundary of the region.")
    side_bias: StructureSide | None = Field(None, description="Optional directional bias attached by the operator.")
    notes: list[str] = Field(default_factory=list, description="Additional operator notes.")
    tags: list[str] = Field(default_factory=list, description="Optional tags used for filtering or AI prompts.")

    @model_validator(mode="after")
    def validate_bounds(self) -> "ReplayManualRegionAnnotationRequest":
        if self.price_high < self.price_low:
            raise ValueError("price_high must be greater than or equal to price_low")
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")
        return self



class ReplayOperatorEntryAcceptedResponse(BaseModel):
    """REST response after an operator entry is stored.""" 

    entry: ReplayOperatorEntryRecord = Field(..., description="Stored operator entry.")



class ReplayOperatorEntryEnvelope(BaseModel):
    """REST response listing operator entries for one replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    entries: list[ReplayOperatorEntryRecord] = Field(default_factory=list, description="Stored operator entries for this replay.")



class ReplayOperatorEntryListQuery(BaseModel):
    """Query object used when listing operator entries for one replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")



class ReplayOperatorEntryRecord(BaseModel):
    """Operator-recorded entry bound to one replay packet for later review."""

    entry_id: str = Field(..., description="Stable operator-entry identifier.")
    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay snapshot identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol.")
    chart_instance_id: str | None = Field(None, description="ATAS chart-instance identifier when known.")
    executed_at: datetime = Field(..., description="When the operator opened the position.")
    side: StructureSide = Field(..., description="Entry direction.")
    entry_price: float = Field(..., description="Entry price.")
    quantity: float | None = Field(None, gt=0, description="Position size or quantity.")
    stop_price: float | None = Field(None, description="Initial stop price when recorded.")
    target_price: float | None = Field(None, description="Initial target price when recorded.")
    timeframe_context: Timeframe | None = Field(None, description="Primary timeframe the operator used for this entry.")
    thesis: str | None = Field(None, description="Short thesis captured at entry time.")
    context_notes: list[str] = Field(default_factory=list, description="Additional context notes captured with the entry.")
    tags: list[str] = Field(default_factory=list, description="Operator tags such as scalp, continuation, reversal.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")



class ReplayOperatorEntryRequest(BaseModel):
    """Request to store one operator entry against a replay packet."""

    replay_ingestion_id: str = Field(..., description="Replay-workbench ingestion identifier to attach this entry to.")
    executed_at: datetime = Field(..., description="When the operator opened the position.")
    side: StructureSide = Field(..., description="Entry direction.")
    entry_price: float = Field(..., description="Entry price.")
    quantity: float | None = Field(None, gt=0, description="Position size or quantity.")
    stop_price: float | None = Field(None, description="Initial stop price when recorded.")
    target_price: float | None = Field(None, description="Initial target price when recorded.")
    timeframe_context: Timeframe | None = Field(None, description="Primary timeframe used for this entry.")
    thesis: str | None = Field(None, description="Short thesis captured at entry time.")
    context_notes: list[str] = Field(default_factory=list, description="Additional context notes captured with the entry.")
    tags: list[str] = Field(default_factory=list, description="Operator tags such as scalp, continuation, reversal.")



class ReplayStrategyCandidate(BaseModel):
    """Strategy-library item matched to the current replay window."""

    strategy_id: str = Field(..., description="Stable strategy-library candidate identifier.")
    title: str = Field(..., description="Short title displayed in the UI.", examples=["NQ replenished bid launchpad"])
    source_path: str = Field(..., description="Strategy-library document path or reference.")
    matched_event_ids: list[str] = Field(default_factory=list, description="Event ids that caused this candidate to be attached.")
    why_relevant: list[str] = Field(default_factory=list, description="Short statements explaining why the candidate is attached.")



class ReplayVerificationState(BaseModel):
    """Current verification state of the replay packet stored in the workbench cache."""

    status: ReplayVerificationStatus = Field(
        ReplayVerificationStatus.UNVERIFIED,
        description="Verification state of the cached replay packet.",
    )
    verification_count: int = Field(
        0,
        ge=0,
        description="How many successful verification passes have been completed for this replay packet.",
    )
    last_verified_at: datetime | None = Field(
        None,
        description="When the replay packet was last verified against ATAS or other trusted source.",
    )
    next_verification_due_at: datetime | None = Field(
        None,
        description="Next time a verification pass is allowed or required.",
    )
    invalidated_at: datetime | None = Field(
        None,
        description="When the replay packet was manually invalidated, if it was invalidated.",
    )
    invalidation_reason: str | None = Field(
        None,
        description="Optional operator note explaining why the replay packet was invalidated.",
    )
    locked_until_manual_reset: bool = Field(
        False,
        description="Whether this replay packet should remain durable until the operator manually invalidates it.",
    )



class ReplayVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DURABLE = "durable"
    INVALIDATED = "invalidated"



class ReplayWorkbenchIntegrity(BaseModel):
    """Unified replay data integrity state shared by build, snapshot, and live-tail APIs."""

    status: str = Field(..., description="High-level integrity status such as complete, missing_local_history, or gaps_detected.")
    window_start: datetime = Field(..., description="Integrity evaluation window start.")
    window_end: datetime = Field(..., description="Integrity evaluation window end.")
    window_days: int = Field(..., ge=1, description="Whole-day window size used for integrity evaluation.")
    gap_count: int = Field(0, ge=0, description="How many missing candle segments were detected.")
    missing_bar_count: int = Field(0, ge=0, description="Total missing bar count across all detected segments.")
    completeness: str | None = Field(None, description="Compact completeness label for UI and downstream consumers.")
    freshness: str | None = Field(None, description="Compact freshness label for UI and downstream consumers.")
    latest_data_status: str | None = Field(None, description="Compact data-status classification such as complete, degraded, or no_live_data.")
    missing_segments: list[ReplayWorkbenchGapSegment] = Field(default_factory=list, description="Missing candle segments normalized for backfill requests.")
    latest_backfill_request_id: str | None = Field(None, description="Most recent related backfill request id when available.")
    latest_backfill_status: ReplayWorkbenchAtasBackfillStatus | None = Field(None, description="Status of the most recent related backfill request when available.")


class ReplayWorkbenchAckVerification(BaseModel):
    """Verification result produced immediately after a backfill acknowledgement."""

    verified: bool = Field(..., description="Whether post-ack history coverage was verified from persisted data.")
    bars_verified: bool = Field(..., description="Whether bars were present and satisfied minimum coverage.")
    footprint_available: bool = Field(..., description="Whether matching footprint payloads were found for the request window.")
    requested_window_start: datetime = Field(..., description="Requested verification window start.")
    requested_window_end: datetime = Field(..., description="Requested verification window end.")
    covered_window_start: datetime | None = Field(None, description="Earliest verified bar start within the requested window.")
    covered_window_end: datetime | None = Field(None, description="Latest verified bar end within the requested window.")
    missing_segment_count: int = Field(0, ge=0, description="How many missing segments still remain after verification.")
    note: str | None = Field(None, description="Optional verification note for operators and UI.")


class ReplayWorkbenchAckRebuildResult(BaseModel):
    """Snapshot rebuild result produced after a verified backfill acknowledgement."""

    triggered: bool = Field(..., description="Whether the server triggered a snapshot rebuild.")
    build_result: ReplayWorkbenchBuildResponse | None = Field(None, description="Fresh build result when a rebuild was triggered.")


class ReplayWorkbenchAcceptedResponse(BaseModel):
    """REST response after a replay workbench packet is validated and stored."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay packet identifier.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    summary: ReplayWorkbenchAcceptedSummary = Field(..., description="Compact summary of the stored replay packet.")



class ReplayWorkbenchAcceptedSummary(BaseModel):
    """Compact summary returned after a replay workbench packet is stored."""

    instrument_symbol: str = Field(..., description="Instrument symbol for the replay packet.")
    display_timeframe: Timeframe = Field(..., description="Primary replay timeframe.")
    acquisition_mode: ReplayAcquisitionMode = Field(..., description="Whether this replay packet was fetched from ATAS or reused from cache.")
    verification_status: ReplayVerificationStatus = Field(..., description="Current verification status for the replay packet.")
    verification_count: int = Field(..., ge=0, description="How many successful verification passes have been recorded.")
    locked_until_manual_reset: bool = Field(..., description="Whether the replay packet is now durable until manual invalidation.")
    fetch_only_when_missing: bool = Field(..., description="Whether the cache policy forbids reacquisition while local data exists.")
    max_verifications_per_day: int = Field(..., ge=1, description="How many verification passes are allowed per day.")
    verification_passes_to_lock: int = Field(..., ge=1, description="How many verification passes are required before permanent retention.")
    candle_count: int = Field(..., ge=0, description="How many candles were stored.")
    event_annotation_count: int = Field(..., ge=0, description="How many event markers were stored.")
    focus_region_count: int = Field(..., ge=0, description="How many focus regions were stored.")
    strategy_candidate_count: int = Field(..., ge=0, description="How many strategy-library candidates were attached.")
    has_ai_briefing: bool = Field(..., description="Whether the packet already includes an AI briefing.")



class ReplayWorkbenchAtasBackfillAcceptedResponse(BaseModel):
    """REST response after a backfill request is queued or deduplicated."""

    request: ReplayWorkbenchAtasBackfillRecord = Field(..., description="Server-side request record.")
    reused_existing_request: bool = Field(
        ...,
        description="Whether the server reused a recent active request instead of creating a new one.",
    )



class ReplayWorkbenchAtasBackfillRecord(BaseModel):
    """Durable server-side record for one ATAS history repair request."""

    request_id: str = Field(..., description="Stable server-generated request identifier.")
    cache_key: str = Field(..., description="Replay cache key whose coverage should be repaired.")
    instrument_symbol: str = Field(..., description="Instrument symbol being repaired.")
    contract_symbol: str | None = Field(None, description="Specific contract symbol to backfill.")
    root_symbol: str | None = Field(None, description="Root/continuous symbol for the backfill.")
    target_contract_symbol: str | None = Field(
        None,
        description="Explicit target contract symbol preferred for the repair when distinct from instrument_symbol.",
    )
    target_root_symbol: str | None = Field(
        None,
        description="Explicit target root symbol preferred for the repair when distinct from instrument_symbol.",
    )
    display_timeframe: Timeframe = Field(..., description="Timeframe where the gap was observed.")
    window_start: datetime = Field(..., description="Inclusive replay window start.")
    window_end: datetime = Field(..., description="Inclusive replay window end.")
    chart_instance_id: str | None = Field(None, description="Preferred chart instance when explicitly targeted.")
    missing_segments: list[ReplayWorkbenchGapSegment] = Field(default_factory=list, description="Observed missing segments.")
    requested_ranges: list[ReplayWorkbenchBackfillRange] = Field(
        default_factory=list,
        description="Explicit bar-time ranges that should be resent during backfill.",
    )
    reason: str = Field(..., description="Why the request exists.")
    request_history_bars: bool = Field(..., description="Whether history bars should be resent.")
    request_history_footprint: bool = Field(..., description="Whether history footprint should be resent.")
    status: ReplayWorkbenchAtasBackfillStatus = Field(..., description="Current lifecycle state of the request.")
    requested_at: datetime = Field(..., description="When the request was created.")
    expires_at: datetime = Field(..., description="When the request should no longer be dispatched.")
    dispatch_count: int = Field(..., ge=0, description="How many times the request was handed to an adapter.")
    dispatched_at: datetime | None = Field(None, description="Last dispatch timestamp when handed to an adapter.")
    dispatched_chart_instance_id: str | None = Field(
        None,
        description="Chart instance that most recently received this request.",
    )
    acknowledged_at: datetime | None = Field(None, description="When the adapter acknowledged the request.")
    acknowledged_chart_instance_id: str | None = Field(
        None,
        description="Chart instance that acknowledged the request.",
    )
    acknowledged_history_bars: bool = Field(
        False,
        description="Whether the adapter reported re-enqueuing history bars.",
    )
    acknowledged_history_footprint: bool = Field(
        False,
        description="Whether the adapter reported re-enqueuing history footprint payloads.",
    )
    latest_loaded_bar_started_at: datetime | None = Field(
        None,
        description="Latest loaded historical bar start known to the adapter when it acknowledged the request.",
    )
    note: str | None = Field(None, description="Optional adapter or server note attached to the request.")



class ReplayWorkbenchAtasBackfillRequest(BaseModel):
    """UI or service-side request asking the ATAS collector to resend loaded history coverage."""

    cache_key: str = Field(..., description="Replay cache key whose missing coverage should be repaired.")
    instrument_symbol: str = Field(..., description="Instrument symbol to repair.", examples=["NQ"])
    contract_symbol: str | None = Field(
        None,
        description="Optional specific contract symbol to backfill instead of the default.",
    )
    root_symbol: str | None = Field(
        None,
        description="Optional root/continuous symbol for the backfill request.",
    )
    target_contract_symbol: str | None = Field(
        None,
        description="Optional explicit target contract symbol for the adapter-facing command.",
    )
    target_root_symbol: str | None = Field(
        None,
        description="Optional explicit target root symbol for the adapter-facing command.",
    )
    display_timeframe: Timeframe = Field(..., description="Display timeframe where the missing bars were detected.")
    window_start: datetime = Field(..., description="Inclusive replay window start needing repair.")
    window_end: datetime = Field(..., description="Inclusive replay window end needing repair.")
    chart_instance_id: str | None = Field(
        None,
        description="Optional preferred ATAS chart instance when a specific chart should fulfill the request.",
    )
    missing_segments: list[ReplayWorkbenchGapSegment] = Field(
        default_factory=list,
        description="Detected candle-time holes to help the adapter understand what should be resent.",
    )
    requested_ranges: list[ReplayWorkbenchBackfillRange] = Field(
        default_factory=list,
        description="Optional explicit resend ranges; when omitted the server derives them from missing segments.",
    )
    reason: str = Field(
        "candle_gap_detected",
        min_length=1,
        description="Why this backfill request was issued.",
    )
    request_history_bars: bool = Field(
        True,
        description="Whether the adapter should resend loaded history bars.",
    )
    request_history_footprint: bool = Field(
        True,
        description="Whether the adapter should resend loaded footprint history.",
    )

    @model_validator(mode="after")
    def validate_window(self) -> "ReplayWorkbenchAtasBackfillRequest":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be greater than or equal to window_start")
        return self



class ReplayWorkbenchAtasBackfillStatus(str, Enum):
    """Lifecycle state of a server-side request asking the ATAS adapter to resend history."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"



class ReplayWorkbenchBuildAction(str, Enum):
    CACHE_HIT = "cache_hit"
    BUILT_FROM_ATAS_HISTORY = "built_from_atas_history"
    BUILT_FROM_LOCAL_HISTORY = "built_from_local_history"
    ATAS_FETCH_REQUIRED = "atas_fetch_required"



class ReplayWorkbenchBuildRequest(BaseModel):
    """Request to build or reuse a replay workbench packet for one historical window."""

    cache_key: str = Field(..., description="Stable replay cache key.")
    instrument_symbol: str = Field(..., description="Instrument symbol to build from local history.", examples=["NQ"])
    display_timeframe: Timeframe = Field(..., description="Primary replay bar timeframe.")
    window_start: datetime = Field(..., description="Inclusive replay window start.")
    window_end: datetime = Field(..., description="Inclusive replay window end.")
    chart_instance_id: str | None = Field(
        None,
        description="Optional ATAS chart-instance filter used when multiple charts for the same symbol are running.",
    )
    force_rebuild: bool = Field(
        False,
        description="Bypass cache reuse and attempt a fresh local rebuild for this replay window.",
    )
    min_continuous_messages: int = Field(
        10,
        ge=1,
        description="Minimum number of local continuous-state messages required before a replay packet can be rebuilt from local history.",
    )

    @model_validator(mode="after")
    def validate_window(self) -> "ReplayWorkbenchBuildRequest":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be greater than or equal to window_start")
        return self



class ReplayWorkbenchBuildResponse(BaseModel):
    """Result of a replay-workbench build attempt."""

    schema_version: str = Field(..., description="Response schema version for this build result.")
    profile_version: str = Field(..., description="Instrument-profile version attached to the derived replay output.")
    engine_version: str = Field(..., description="Recognizer engine version attached to the derived replay output.")
    data_status: BeliefDataStatus = Field(..., description="Freshness, completeness, and degraded-mode summary for this build result.")
    action: ReplayWorkbenchBuildAction = Field(..., description="Whether the builder reused cache, built locally, or needs ATAS history.")
    cache_key: str = Field(..., description="Replay cache key handled by this request.")
    reason: str = Field(..., description="Short explanation of the chosen action.")
    local_message_count: int = Field(..., ge=0, description="How many local continuous-state messages matched the request window.")
    replay_snapshot_id: str | None = Field(None, description="Replay packet identifier when a packet exists or was built.")
    ingestion_id: str | None = Field(None, description="Stored ingestion identifier when a packet exists or was built.")
    core_snapshot: ReplayWorkbenchSnapshotPayload | None = Field(
        None,
        description="Replay snapshot payload returned inline for first-screen rendering when immediately available.",
    )
    summary: ReplayWorkbenchAcceptedSummary | None = Field(None, description="Stored or newly created replay summary when available.")
    cache_record: ReplayWorkbenchCacheRecord | None = Field(None, description="Latest cache record after the build decision.")
    atas_fetch_request: dict[str, Any] | None = Field(
        None,
        description="Minimal ATAS history request guidance when local history is insufficient.",
    )
    atas_backfill_request: ReplayWorkbenchAtasBackfillRecord | None = Field(
        None,
        description="Backfill request automatically created or reused for this replay window.",
    )
    integrity: ReplayWorkbenchIntegrity | None = Field(
        None,
        description="Unified replay integrity state for the requested window.",
    )



class ReplayWorkbenchCacheEnvelope(BaseModel):
    """Replay cache lookup result used before deciding whether ATAS needs to be queried."""

    cache_key: str = Field(..., description="Requested replay cache key.")
    record: ReplayWorkbenchCacheRecord | None = Field(
        None,
        description="Latest replay cache record for this key, or null when no cached packet exists.",
    )
    auto_fetch_allowed: bool = Field(
        ...,
        description="Whether the system is allowed to fetch from ATAS automatically for this key.",
    )
    verification_due_now: bool = Field(
        ...,
        description="Whether a verification pass is currently due according to the stored verification state.",
    )



class ReplayWorkbenchCacheRecord(BaseModel):
    """Index view of the latest cached replay packet for one cache key."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay packet identifier.")
    cache_key: str = Field(..., description="Stable replay cache key.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    created_at: datetime = Field(..., description="When the replay packet was generated.")
    instrument_symbol: str = Field(..., description="Instrument symbol.")
    display_timeframe: Timeframe = Field(..., description="Primary replay timeframe.")
    window_start: datetime = Field(..., description="Replay window start.")
    window_end: datetime = Field(..., description="Replay window end.")
    acquisition_mode: ReplayAcquisitionMode = Field(..., description="Whether the packet came from cache reuse or ATAS fetch.")
    cache_policy: ReplayCachePolicy = Field(..., description="Cache policy attached to the replay packet.")
    verification_state: ReplayVerificationState = Field(..., description="Verification state attached to the replay packet.")
    candle_count: int = Field(..., ge=0, description="How many candles were stored in the replay packet.")
    event_annotation_count: int = Field(..., ge=0, description="How many event annotations were stored.")
    focus_region_count: int = Field(..., ge=0, description="How many focus regions were stored.")
    strategy_candidate_count: int = Field(..., ge=0, description="How many strategy-library candidates were attached.")
    has_ai_briefing: bool = Field(..., description="Whether an AI briefing is already attached.")



class ReplayWorkbenchGapSegment(BaseModel):
    """One missing candle-time segment detected in a rebuilt replay packet."""

    prev_ended_at: datetime | None = Field(
        None,
        description="End timestamp of the candle immediately before the gap when available.",
    )
    next_started_at: datetime = Field(
        ...,
        description="Start timestamp of the first observed candle after the gap.",
    )
    missing_bar_count: int = Field(
        ...,
        ge=1,
        description="How many bars are missing between prev_ended_at and next_started_at.",
    )



class ReplayWorkbenchBackfillRange(BaseModel):
    """One explicit time range the adapter should prioritize during a backfill resend."""

    range_start: datetime = Field(..., description="Inclusive backfill range start in UTC.")
    range_end: datetime = Field(..., description="Inclusive backfill range end in UTC.")

    @model_validator(mode="after")
    def validate_range(self) -> "ReplayWorkbenchBackfillRange":
        if self.range_end < self.range_start:
            raise ValueError("range_end must be greater than or equal to range_start")
        return self

class ReplayWorkbenchInvalidationRequest(BaseModel):
    """Manual invalidation request for a cached replay packet."""

    cache_key: str | None = Field(None, description="Replay cache key to invalidate.")
    replay_snapshot_id: str | None = Field(None, description="Specific replay snapshot identifier to invalidate.")
    ingestion_id: str | None = Field(None, description="Specific ingestion identifier to invalidate.")
    invalidation_reason: str = Field(..., min_length=1, description="Operator reason for manual invalidation.")

    @model_validator(mode="after")
    def validate_identity(self) -> "ReplayWorkbenchInvalidationRequest":
        if not any([self.cache_key, self.replay_snapshot_id, self.ingestion_id]):
            raise ValueError("cache_key, replay_snapshot_id, or ingestion_id is required")
        return self



class ReplayWorkbenchInvalidationResponse(BaseModel):
    """REST response after a replay cache record is manually invalidated."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    replay_snapshot_id: str = Field(..., description="Replay packet identifier.")
    cache_key: str = Field(..., description="Replay cache key.")
    invalidated_at: datetime = Field(..., description="Manual invalidation timestamp.")
    invalidation_reason: str = Field(..., description="Operator reason preserved with the packet.")
    verification_status: ReplayVerificationStatus = Field(..., description="Updated verification status.")
    locked_until_manual_reset: bool = Field(..., description="Updated durable lock state after invalidation.")



class ReplayWorkbenchLiveSourceStatus(BaseModel):
    """Latest stored-ingestion timestamp for one adapter feed kind."""

    ingestion_kind: str = Field(..., description="Adapter ingestion kind being summarized.")
    latest_ingestion_id: str | None = Field(None, description="Most recent stored ingestion identifier for this kind.")
    latest_stored_at: datetime | None = Field(None, description="Most recent backend persistence timestamp for this kind.")
    lag_seconds: int | None = Field(None, ge=0, description="Current lag in whole seconds from latest_stored_at to now.")



class ReplayWorkbenchLiveStatusResponse(BaseModel):
    """Freshness summary used by the workbench to decide whether an old replay can be reused."""

    schema_version: str = Field(..., description="Response schema version for live status.")
    profile_version: str = Field(..., description="Instrument-profile version attached to this live-status view.")
    engine_version: str = Field(..., description="Recognizer engine version attached to this live-status view.")
    data_status: BeliefDataStatus = Field(..., description="Freshness, completeness, and degraded-mode summary for this live-status view.")
    instrument_symbol: str = Field(..., description="Instrument symbol being checked.")
    replay_ingestion_id: str | None = Field(None, description="Replay ingestion currently shown in the UI, when known.")
    replay_snapshot_stored_at: datetime | None = Field(None, description="Stored_at timestamp of the replay currently shown.")
    latest_adapter_sync_at: datetime | None = Field(None, description="Most recent adapter timestamp across continuous state and history sync feeds.")
    latest_adapter_sync_lag_seconds: int | None = Field(None, ge=0, description="Current lag in whole seconds from latest_adapter_sync_at to now.")
    stream_state: ReplayLiveStreamState = Field(..., description="High-level health state of the adapter feed for this symbol.")
    should_refresh_snapshot: bool = Field(..., description="Whether adapter data is newer than the replay snapshot currently shown.")
    latest_continuous_state: ReplayWorkbenchLiveSourceStatus = Field(..., description="Latest continuous-state ingestion for this symbol.")
    latest_history_bars: ReplayWorkbenchLiveSourceStatus = Field(..., description="Latest history-bars ingestion for this symbol.")
    latest_history_footprint: ReplayWorkbenchLiveSourceStatus = Field(..., description="Latest history-footprint ingestion for this symbol.")



class ReplayWorkbenchLiveTailResponse(BaseModel):
    """Latest in-flight tail built from continuous adapter messages for realtime UI patching."""

    schema_version: str = Field(..., description="Response schema version for live tail.")
    profile_version: str = Field(..., description="Instrument-profile version attached to this live-tail view.")
    engine_version: str = Field(..., description="Recognizer engine version attached to this live-tail view.")
    data_status: BeliefDataStatus = Field(..., description="Freshness, completeness, and degraded-mode summary for this live-tail view.")
    instrument_symbol: str = Field(..., description="Instrument symbol being patched in realtime.")
    display_timeframe: Timeframe = Field(..., description="Display timeframe used to bucket the live tail.")
    latest_observed_at: datetime | None = Field(
        None,
        description="Latest observed ATAS timestamp carried by the continuous-state stream.",
    )
    latest_price: float | None = Field(
        None,
        description="Most recent last-traded price from the adapter stream.",
    )
    best_bid: float | None = Field(
        None,
        description="Most recent best bid from the adapter stream when available.",
    )
    best_ask: float | None = Field(
        None,
        description="Most recent best ask from the adapter stream when available.",
    )
    latest_price_source: str | None = Field(
        None,
        description="Source used for latest_price (for example: continuous_state, ticks_raw, candle_close).",
    )
    best_bid_source: str | None = Field(
        None,
        description="Source used for best_bid (for example: continuous_state, ticks_raw).",
    )
    best_ask_source: str | None = Field(
        None,
        description="Source used for best_ask (for example: continuous_state, ticks_raw).",
    )
    source_message_count: int = Field(
        ...,
        ge=0,
        description="How many recent continuous-state messages were used to build this live tail.",
    )
    candles: list[ReplayChartBar] = Field(
        default_factory=list,
        description="Latest reconstructed bars that should patch the right edge of the replay chart.",
    )
    event_annotations: list[ReplayEventAnnotation] = Field(
        default_factory=list,
        description="Latest collector-derived event overlays that should refresh alongside the live tail.",
    )
    focus_regions: list[ReplayFocusRegion] = Field(
        default_factory=list,
        description="Latest collector-derived focus regions that should refresh alongside the live tail.",
    )
    trade_summary: AdapterTradeSummary | None = Field(
        None,
        description="Latest rolling trade summary from the continuous-state stream.",
    )
    significant_liquidity: list[AdapterSignificantLiquidityLevel] = Field(
        default_factory=list,
        description="Latest significant displayed-liquidity tracks for realtime overlays.",
    )
    same_price_replenishment: list[AdapterSamePriceReplenishmentState] = Field(
        default_factory=list,
        description="Latest repeated-replenishment observations for realtime overlays.",
    )
    active_initiative_drive: AdapterInitiativeDriveState | None = Field(
        None,
        description="Latest active initiative-drive state for realtime overlays.",
    )
    active_post_harvest_response: AdapterPostHarvestResponseState | None = Field(
        None,
        description="Latest post-harvest response state for realtime overlays.",
    )
    integrity: ReplayWorkbenchIntegrity | None = Field(
        None,
        description="Unified replay integrity state for the recent live window.",
    )
    snapshot_refresh_required: bool = Field(
        False,
        description="Whether the frontend should reload the current snapshot instead of applying a tail patch.",
    )
    latest_backfill_request: ReplayWorkbenchAtasBackfillRecord | None = Field(
        None,
        description="Most recent matching backfill request for this symbol/timeframe when available.",
    )


class InstrumentProfile(BaseModel):
    """Versioned instrument profile used by the deterministic recognizer."""

    instrument_symbol: str = Field(..., description="Instrument symbol that this profile applies to.")
    profile_version: str = Field(..., description="Version identifier for this profile.")
    schema_version: str = Field(..., description="Schema version for the profile payload.")
    ontology_version: str = Field(..., description="Fixed ontology version referenced by this profile.")
    is_active: bool = Field(True, description="Whether this profile is currently active for the instrument.")
    normalization: dict[str, Any] = Field(default_factory=dict, description="Normalization and scaling settings.")
    time_windows: dict[str, Any] = Field(default_factory=dict, description="Session or replay time-window settings.")
    thresholds: dict[str, Any] = Field(default_factory=dict, description="Threshold parameters used by the recognizer.")
    weights: dict[str, Any] = Field(default_factory=dict, description="Relative weights for evidence buckets.")
    decay: dict[str, Any] = Field(default_factory=dict, description="Decay settings for stale evidence and anchors.")
    priors: dict[str, Any] = Field(default_factory=dict, description="Prior probabilities for regimes and event hypotheses.")
    safety: dict[str, Any] = Field(default_factory=dict, description="Safety bounds for degraded operation and evaluation.")
    created_at: datetime = Field(..., description="When this profile version was created.")


class RecognizerBuild(BaseModel):
    """Versioned recognizer build metadata attached to all derived outputs."""

    engine_version: str = Field(..., description="Recognizer engine build identifier.")
    schema_version: str = Field(..., description="Schema version used by this build.")
    ontology_version: str = Field(..., description="Ontology version used by this build.")
    is_active: bool = Field(True, description="Whether this recognizer build is the active engine build.")
    status: str = Field("active", description="Build lifecycle status.")
    notes: list[str] = Field(default_factory=list, description="Operator-facing notes about this build.")
    created_at: datetime = Field(..., description="When this recognizer build was created.")


class BeliefDataStatus(BaseModel):
    """Freshness, completeness, and degraded-signal state for one belief snapshot."""

    data_freshness_ms: int = Field(..., ge=0, description="Estimated freshness lag in milliseconds.")
    feature_completeness: float = Field(..., ge=0.0, le=1.0, description="Fraction of expected features available to the recognizer.")
    depth_available: bool = Field(..., description="Whether depth-derived evidence was available.")
    dom_available: bool = Field(..., description="Whether DOM-derived evidence was available.")
    ai_available: bool = Field(..., description="Whether AI services were available for optional review layers.")
    degraded_modes: list[DegradedMode] = Field(default_factory=list, description="Explicit degraded modes active for this snapshot.")
    freshness: str | None = Field(None, description="Compact freshness label for UI display.")
    completeness: str | None = Field(None, description="Compact completeness label for UI display.")


class RegimePosteriorRecord(BaseModel):
    """Append-only probability snapshot for one regime candidate."""

    regime: RegimeKind = Field(..., description="Fixed regime ontology label.")
    probability: float = Field(..., ge=0.0, le=1.0, description="Posterior probability for this regime.")
    evidence: list[str] = Field(default_factory=list, description="Observed evidence supporting this regime probability.")


class EventHypothesisState(BaseModel):
    """Append-only event-hypothesis state emitted by the recognizer."""

    hypothesis_id: str = Field(..., description="Stable hypothesis identifier within one belief snapshot.")
    hypothesis_kind: EventHypothesisKind = Field(..., description="Fixed event-hypothesis ontology label.")
    mapped_event_kind: TradableEventKind | None = Field(None, description="Optional tradable event kind mapped from this hypothesis.")
    phase: EventPhase = Field(..., description="Lifecycle phase of the hypothesis.")
    posterior_probability: float = Field(..., ge=0.0, le=1.0, description="Posterior probability for this hypothesis.")
    supporting_evidence: list[str] = Field(default_factory=list, description="Evidence currently supporting the hypothesis.")
    missing_confirmation: list[str] = Field(default_factory=list, description="Evidence still missing before stronger confirmation.")
    invalidating_signals: list[str] = Field(default_factory=list, description="Signals that would weaken or invalidate the hypothesis.")
    transition_watch: list[str] = Field(default_factory=list, description="Competing transitions that the engine is watching.")


class MemoryAnchorSnapshot(BaseModel):
    """Versioned memory-anchor view attached to one belief snapshot."""

    anchor_id: str = Field(..., description="Stable memory-anchor identifier.")
    anchor_type: str = Field(..., description="Anchor ontology type such as balance_center or gap_edge.")
    reference_price: float | None = Field(None, description="Primary price reference for the anchor.")
    reference_time: datetime | None = Field(None, description="Primary time reference for the anchor.")
    freshness: str | None = Field(None, description="Anchor freshness label.")
    profile_version: str = Field(..., description="Profile version used to emit this anchor snapshot.")


class BeliefStateSnapshot(BaseModel):
    """Append-only current market-understanding snapshot consumed by UI and review flows."""

    belief_state_id: str = Field(..., description="Stable belief-state identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol described by this belief state.")
    observed_at: datetime = Field(..., description="Observed market timestamp represented by the belief state.")
    stored_at: datetime = Field(..., description="Persistence timestamp for the belief state.")
    schema_version: str = Field(..., description="Belief-state schema version.")
    profile_version: str = Field(..., description="Instrument-profile version used for this belief state.")
    engine_version: str = Field(..., description="Recognizer build version used for this belief state.")
    recognition_mode: RecognitionMode = Field(..., description="Recognition operating mode used for this belief state.")
    data_status: BeliefDataStatus = Field(..., description="Freshness, completeness, and degraded-signal state.")
    regime_posteriors: list[RegimePosteriorRecord] = Field(default_factory=list, description="Top regime posteriors for the current state.")
    event_hypotheses: list[EventHypothesisState] = Field(default_factory=list, description="Parallel event hypotheses for the current state.")
    active_anchors: list[MemoryAnchorSnapshot] = Field(default_factory=list, description="Active memory anchors that influence the current posterior.")
    notes: list[str] = Field(default_factory=list, description="Additional operator-facing notes emitted by the recognizer.")


class EventEpisode(BaseModel):
    """Append-only closed event trajectory emitted by the recognizer."""

    episode_id: str = Field(..., description="Stable closed-episode identifier.")
    instrument_symbol: str = Field(..., description="Instrument symbol for this episode.")
    event_kind: TradableEventKind = Field(..., description="V1 tradable event kind represented by this episode.")
    hypothesis_kind: EventHypothesisKind = Field(..., description="Dominant event-hypothesis kind behind the episode.")
    phase: EventPhase = Field(..., description="Final phase reached by the episode.")
    resolution: EpisodeResolution = Field(..., description="Terminal episode resolution.")
    started_at: datetime = Field(..., description="When the episode started forming.")
    ended_at: datetime = Field(..., description="When the episode closed.")
    peak_probability: float = Field(..., ge=0.0, le=1.0, description="Highest posterior probability reached during the episode.")
    dominant_regime: RegimeKind = Field(..., description="Dominant regime during the episode.")
    supporting_evidence: list[str] = Field(default_factory=list, description="Key evidence that supported the episode.")
    invalidating_evidence: list[str] = Field(default_factory=list, description="Key evidence that weakened or ended the episode.")
    active_anchor_ids: list[str] = Field(default_factory=list, description="Relevant memory anchors referenced by the episode.")
    replacement_episode_id: str | None = Field(None, description="Replacement episode identifier when this one was superseded.")
    schema_version: str = Field(..., description="Episode schema version.")
    profile_version: str = Field(..., description="Instrument-profile version used for this episode.")
    engine_version: str = Field(..., description="Recognizer build version used for this episode.")
    data_status: BeliefDataStatus = Field(..., description="Data state captured when the episode closed.")


class EpisodeEvaluationScorecard(BaseModel):
    """Standardized scorecard for one episode evaluation."""

    structure_alignment: float = Field(..., ge=0.0, le=1.0, description="Alignment between episode structure and the observed path.")
    timing_quality: float = Field(..., ge=0.0, le=1.0, description="Whether the episode progressed within the declared time window.")
    confirmation_quality: float = Field(..., ge=0.0, le=1.0, description="Strength and cleanliness of the confirmation sequence.")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall normalized episode score.")


class EpisodeEvaluation(BaseModel):
    """Append-only standardized evaluation over one closed event episode."""

    evaluation_id: str = Field(..., description="Stable evaluation identifier.")
    episode_id: str = Field(..., description="Closed event episode being evaluated.")
    instrument_symbol: str = Field(..., description="Instrument symbol for the episode.")
    event_kind: TradableEventKind = Field(..., description="V1 tradable event kind evaluated.")
    judgement_source: ReviewSource = Field(..., description="Source that produced this evaluation.")
    failure_mode: EvaluationFailureMode = Field(..., description="Primary failure mode for this evaluation.")
    summary: str = Field(..., description="Compact evaluation summary.")
    strengths: list[str] = Field(default_factory=list, description="What worked well in the episode lifecycle.")
    weaknesses: list[str] = Field(default_factory=list, description="Where the episode or confirmation sequence was weak.")
    tuning_hints: list[str] = Field(default_factory=list, description="Non-binding tuning hints for later review.")
    scorecard: EpisodeEvaluationScorecard = Field(..., description="Normalized scorecard for this evaluation.")
    schema_version: str = Field(..., description="Evaluation schema version.")
    profile_version: str = Field(..., description="Instrument-profile version used for this evaluation.")
    engine_version: str = Field(..., description="Recognizer build version used for this evaluation.")
    evaluated_at: datetime = Field(..., description="When this evaluation was produced.")


class BeliefLatestEnvelope(BaseModel):
    """REST response envelope returning the latest belief-state snapshot."""

    belief: BeliefStateSnapshot | None = Field(None, description="Latest belief-state snapshot when available.")


class EpisodeListEnvelope(BaseModel):
    """REST response envelope returning recently closed event episodes."""

    instrument_symbol: str = Field(..., description="Instrument symbol that was queried.")
    episodes: list[EventEpisode] = Field(default_factory=list, description="Recently closed episodes for the instrument.")


class EpisodeEvaluationEnvelope(BaseModel):
    """REST response envelope returning one stored episode evaluation."""

    evaluation: EpisodeEvaluation | None = Field(None, description="Stored episode evaluation when available.")


class ReplayWorkbenchRebuildLatestRequest(BaseModel):
    """One-shot request that invalidates the current cache and rebuilds it from the latest synced data."""

    cache_key: str = Field(..., description="Stable replay cache key to rebuild.")
    instrument_symbol: str = Field(..., description="Instrument symbol for the replay window.", examples=["NQ"])
    display_timeframe: Timeframe = Field(..., description="Primary replay bar timeframe.")
    window_start: datetime = Field(..., description="Inclusive replay window start.")
    window_end: datetime = Field(..., description="Inclusive replay window end.")
    chart_instance_id: str | None = Field(
        None,
        description="Optional ATAS chart-instance filter when multiple charts for the same symbol are running.",
    )
    min_continuous_messages: int = Field(
        10,
        ge=1,
        description="Minimum number of local continuous-state messages required before local-history rebuild is allowed.",
    )
    invalidation_reason: str = Field(
        "operator requested rebuild from latest synced data",
        min_length=1,
        description="Reason stored on the invalidated cache record before rebuilding.",
    )

    @model_validator(mode="after")
    def validate_window(self) -> "ReplayWorkbenchRebuildLatestRequest":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be greater than or equal to window_start")
        return self



class ReplayWorkbenchRebuildLatestResponse(BaseModel):
    """Result of invalidating the active replay cache and rebuilding from the newest synced payloads."""

    cache_key: str = Field(..., description="Replay cache key that was rebuilt.")
    invalidated_existing_cache: bool = Field(..., description="Whether an existing cache record was invalidated first.")
    invalidation_result: ReplayWorkbenchInvalidationResponse | None = Field(
        None,
        description="Invalidation details when a prior cache record existed.",
    )
    build_result: ReplayWorkbenchBuildResponse = Field(
        ...,
        description="Fresh build result created from the latest synced payloads.",
    )



class ReplayWorkbenchSnapshotPayload(BaseModel):
    """Standalone replay-workbench packet used by the future UI and AI review loop."""

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    profile_version: str = Field(..., description="Instrument-profile version attached to this derived replay snapshot.")
    engine_version: str = Field(..., description="Recognizer engine version attached to this derived replay snapshot.")
    data_status: BeliefDataStatus = Field(..., description="Freshness, completeness, and degraded-mode summary for this replay snapshot.")
    replay_snapshot_id: str = Field(..., description="Replay packet identifier.", examples=["replay-20260317-nq-europe-01"])
    cache_key: str = Field(
        ...,
        description="Stable cache key used to decide whether the replay packet should be reused or reacquired.",
        examples=["NQ|5m|2026-03-12T07:00:00Z|2026-03-17T02:15:00Z"],
    )
    acquisition_mode: ReplayAcquisitionMode = Field(
        ...,
        description="Whether the packet came from local cache reuse or a fresh ATAS acquisition.",
    )
    created_at: datetime = Field(..., description="When the replay packet was generated.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    display_timeframe: Timeframe = Field(..., description="Primary bar timeframe used by the UI replay chart.")
    window_start: datetime = Field(..., description="Inclusive replay window start.")
    window_end: datetime = Field(..., description="Inclusive replay window end.")
    cache_policy: ReplayCachePolicy = Field(
        default_factory=ReplayCachePolicy,
        description="Cache policy controlling replay reacquisition and verification cadence.",
    )
    verification_state: ReplayVerificationState = Field(
        default_factory=ReplayVerificationState,
        description="Current verification state for this replay packet.",
    )
    integrity: ReplayWorkbenchIntegrity | None = Field(
        None,
        description="Unified replay integrity state captured at snapshot build time.",
    )
    candles: list[ReplayChartBar] = Field(default_factory=list, description="Reconstructed bar series used by the standalone replay UI.")
    event_annotations: list[ReplayEventAnnotation] = Field(default_factory=list, description="Structured event overlays rendered on the replay chart.")
    focus_regions: list[ReplayFocusRegion] = Field(default_factory=list, description="High-priority regions highlighted for operator and AI review.")
    strategy_candidates: list[ReplayStrategyCandidate] = Field(default_factory=list, description="Strategy-library candidates attached to this replay window.")
    ai_briefing: ReplayAiBriefing | None = Field(
        None,
        description="Optional AI briefing assembled from events, focus regions, and strategy-library matches.",
    )
    raw_features: dict[str, Any] = Field(default_factory=dict, description="Additional replay metadata such as history depth or ATAS workspace info.")

    @model_validator(mode="after")
    def validate_replay_window(self) -> "ReplayWorkbenchSnapshotPayload":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be greater than or equal to window_start")
        if self.verification_state.status == ReplayVerificationStatus.DURABLE:
            if self.verification_state.verification_count < self.cache_policy.verification_passes_to_lock:
                raise ValueError("durable replay packets must satisfy verification_passes_to_lock")
            if not self.verification_state.locked_until_manual_reset:
                raise ValueError("durable replay packets must stay locked_until_manual_reset")
        if self.verification_state.status == ReplayVerificationStatus.INVALIDATED and self.verification_state.invalidated_at is None:
            raise ValueError("invalidated replay packets must include invalidated_at")
        return self



