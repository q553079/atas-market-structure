from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atas_market_structure.models._derived import (
    DerivedLiquidityMemoryInterpretation,
    DerivedStructureAnalysis,
)
from atas_market_structure.models._enums import (
    DepthCoverageState,
    ReplayAcquisitionMode,
    ReplayVerificationStatus,
    ServiceHealthStatus,
    Timeframe,
)
from atas_market_structure.models._observed import ObservedLargeLiquidityLevel
from atas_market_structure.models._replay import (
    BeliefDataStatus,
    ReplayCachePolicy,
    ReplayChartBar,
    ReplayWorkbenchBackfillRange,
    ReplayLiveStreamState,
    ReplayWorkbenchAcceptedSummary,
    ReplayWorkbenchAckRebuildResult,
    ReplayWorkbenchAckVerification,
    ReplayWorkbenchAtasBackfillRecord,
    ReplayWorkbenchAtasBackfillStatus,
    ReplayWorkbenchBuildAction,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheRecord,
    ReplayWorkbenchGapSegment,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchIntegrity,
    ReplayWorkbenchLiveSourceStatus,
)

class AdapterAcceptedResponse(BaseModel):
    """REST response after an adapter message is validated and stored."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    message_id: str = Field(..., description="Original adapter message identifier.")
    message_type: str = Field(..., description="Adapter message family.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    summary: AdapterAcceptedSummary = Field(..., description="Compact summary of the accepted adapter message.")
    durable_outputs: list[AdapterBridgedArtifact] = Field(
        default_factory=list,
        description="Synthetic durable outputs automatically bridged from the adapter payload.",
    )
    bridge_errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal bridge errors encountered after raw adapter storage.",
    )



class AdapterAcceptedSummary(BaseModel):
    """Compact adapter ingestion summary returned immediately after storage."""

    instrument_symbol: str = Field(..., description="Instrument symbol.")
    observed_window_start: datetime = Field(..., description="Observed window start.")
    observed_window_end: datetime = Field(..., description="Observed window end.")
    significant_liquidity_count: int = Field(
        default=0,
        ge=0,
        description="How many significant liquidity tracks were attached.",
    )
    has_gap_reference: bool = Field(False, description="Whether the message carried a gap reference.")
    has_active_initiative_drive: bool = Field(False, description="Whether the message carried an initiative drive.")
    has_active_manipulation_leg: bool = Field(False, description="Whether the message carried a manipulation leg.")
    has_active_measured_move: bool = Field(False, description="Whether the message carried a measured move.")
    has_active_post_harvest_response: bool = Field(
        False,
        description="Whether the message carried a post-harvest response.",
    )
    trigger_type: AdapterTriggerType | None = Field(None, description="Trigger type for burst messages.")
    reason_codes: list[str] = Field(default_factory=list, description="Trigger reason codes for burst messages.")
    trade_event_count: int = Field(default=0, ge=0, description="Trade-event count across burst windows.")
    depth_event_count: int = Field(default=0, ge=0, description="Depth-event count across burst windows.")
    second_feature_count: int = Field(default=0, ge=0, description="Second-feature count across burst windows.")
    history_bar_count: int = Field(default=0, ge=0, description="Bar count for chart-loaded history messages.")
    history_bar_timeframe: Timeframe | None = Field(None, description="Native timeframe of the exported history bars.")
    history_footprint_bar_count: int = Field(
        default=0,
        ge=0,
        description="Bar count for chart-loaded historical footprint messages.",
    )
    history_footprint_timeframe: Timeframe | None = Field(
        None,
        description="Native timeframe of the exported historical footprint bars.",
    )
    history_footprint_chunk_index: int | None = Field(
        None,
        ge=0,
        description="Zero-based chunk index for a chunked historical footprint export.",
    )
    history_footprint_chunk_count: int | None = Field(
        None,
        ge=1,
        description="Total chunk count for a chunked historical footprint export.",
    )



class AdapterBackfillAcknowledgeRequest(BaseModel):
    """Adapter callback confirming whether a dispatched backfill request was actioned."""

    request_id: str = Field(..., description="Request identifier previously dispatched by the server.")
    cache_key: str | None = Field(None, description="Replay cache key associated with the dispatched request.")
    instrument_symbol: str = Field(..., description="Instrument symbol that acknowledged the request.")
    chart_instance_id: str | None = Field(None, description="Chart instance that handled the request.")
    acknowledged_at: datetime = Field(..., description="When the adapter finished handling the request.")
    acknowledged_history_bars: bool = Field(
        False,
        description="Whether history bars were re-enqueued.",
    )
    acknowledged_history_footprint: bool = Field(
        False,
        description="Whether history footprint chunks were re-enqueued.",
    )
    latest_loaded_bar_started_at: datetime | None = Field(
        None,
        description="Latest loaded historical bar start available in the chart when acknowledged.",
    )
    note: str | None = Field(None, description="Optional adapter note.")



class AdapterBackfillAcknowledgeResponse(BaseModel):
    """Server confirmation after recording an adapter backfill acknowledgement."""

    request: ReplayWorkbenchAtasBackfillRecord = Field(..., description="Updated durable request record.")
    verification: ReplayWorkbenchAckVerification | None = Field(
        None,
        description="Post-ack verification result based on persisted history coverage.",
    )
    rebuild_result: ReplayWorkbenchAckRebuildResult | None = Field(
        None,
        description="Snapshot rebuild result when verification triggered an automatic rebuild.",
    )



class AdapterBackfillCommand(BaseModel):
    """Minimal command payload consumed by the ATAS adapter control loop."""

    request_id: str = Field(..., description="Server-generated request identifier.")
    cache_key: str = Field(..., description="Replay cache key affected by this request.")
    instrument_symbol: str = Field(..., description="Instrument symbol to repair.")
    contract_symbol: str | None = Field(None, description="Specific contract symbol to repair when available.")
    root_symbol: str | None = Field(None, description="Root/continuous symbol associated with the repair.")
    target_contract_symbol: str | None = Field(None, description="Explicit adapter-facing contract target when set.")
    target_root_symbol: str | None = Field(None, description="Explicit adapter-facing root-symbol target when set.")
    display_timeframe: Timeframe = Field(..., description="Display timeframe where the gap was detected.")
    window_start: datetime = Field(..., description="Inclusive replay window start.")
    window_end: datetime = Field(..., description="Inclusive replay window end.")
    chart_instance_id: str | None = Field(None, description="Preferred chart instance when targeted.")
    missing_segments: list[ReplayWorkbenchGapSegment] = Field(default_factory=list, description="Observed missing segments.")
    requested_ranges: list[ReplayWorkbenchBackfillRange] = Field(
        default_factory=list,
        description="Explicit resend ranges for the adapter to prioritize.",
    )
    reason: str = Field(..., description="Why the request was created.")
    request_history_bars: bool = Field(..., description="Whether history bars should be resent.")
    request_history_footprint: bool = Field(..., description="Whether history footprint should be resent.")
    replace_existing_history: bool = Field(
        False,
        description="Whether the server already cleared the targeted history window before this dispatch.",
    )
    dispatch_count: int = Field(..., ge=1, description="Current dispatch attempt number.")
    requested_at: datetime = Field(..., description="When the request was first created.")
    dispatched_at: datetime = Field(..., description="When this dispatch lease was granted.")



class AdapterBackfillDispatchResponse(BaseModel):
    """Response returned to the adapter when it polls for pending repair work."""

    instrument_symbol: str = Field(..., description="Instrument symbol that was polled.")
    chart_instance_id: str | None = Field(None, description="Polling chart instance when supplied.")
    polled_at: datetime = Field(..., description="Server poll timestamp.")
    request: AdapterBackfillCommand | None = Field(
        None,
        description="Pending backfill command when work is available, otherwise null.",
    )



class AdapterBridgedArtifact(BaseModel):
    """Synthetic durable output created from an adapter payload."""

    ingestion_kind: Literal["market_structure", "event_snapshot"] = Field(..., description="Durable output kind.")
    source_snapshot_id: str = Field(..., description="Synthetic snapshot id used for the durable output.")
    ingestion_id: str = Field(..., description="Durable ingestion identifier.")
    analysis_id: str = Field(..., description="Durable analysis identifier.")
    route_key: str = Field(..., description="Knowledge route selected for the durable output.")



class AdapterDepthCoverage(BaseModel):
    """Compact depth-feed coverage state for validating live DOM collection."""

    coverage_state: DepthCoverageState = Field(..., description="Current depth-feed coverage state.")
    snapshot_level_count: int = Field(..., ge=0, description="How many levels were present in the last depth snapshot.")
    tracked_liquidity_count: int = Field(..., ge=0, description="How many active significant-liquidity tracks are currently alive.")
    last_snapshot_at: datetime | None = Field(None, description="Timestamp of the most recent successful depth snapshot.")
    best_bid_available: bool = Field(..., description="Whether a best bid is currently available.")
    best_ask_available: bool = Field(..., description="Whether a best ask is currently available.")



class AdapterEmaContext(BaseModel):
    """Optional EMA context kept in observed facts for later AI reasoning."""

    ema20: float = Field(..., description="Current EMA20 value.", examples=[21568.25])
    ema20_distance_ticks: int = Field(..., description="Distance between price and EMA20 in ticks.", examples=[24])
    ema20_slope: float = Field(..., description="Current EMA20 slope measure.", examples=[1.35])
    ema20_reclaim_confirmed: bool = Field(..., description="Whether price has reclaimed EMA20.", examples=[True])
    bars_above_ema20_after_reclaim: int = Field(
        ...,
        ge=0,
        description="Bars spent above EMA20 since reclaim.",
        examples=[5],
    )



class AdapterEnvelopeBase(BaseModel):
    """Common adapter message envelope shared by continuous and burst payloads."""

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    message_id: str = Field(..., description="Unique adapter message identifier.", examples=["adapter-msg-20260316-143001"])
    emitted_at: datetime = Field(..., description="When the adapter emitted this message.")
    observed_window_start: datetime = Field(..., description="Inclusive start of the observed window.")
    observed_window_end: datetime = Field(..., description="Inclusive end of the observed window.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")

    @model_validator(mode="after")
    def validate_observed_window(self) -> "AdapterEnvelopeBase":
        if self.observed_window_end < self.observed_window_start:
            raise ValueError("observed_window_end must be greater than or equal to observed_window_start")
        return self



class AdapterGapReferenceState(BaseModel):
    """Compact gap state used in the always-on adapter stream."""

    gap_id: str = Field(..., description="Stable gap identifier.")
    direction: GapDirection = Field(..., description="Gap direction.")
    opened_at: datetime = Field(..., description="When the gap reference became active.")
    gap_low: float = Field(..., description="Lower boundary of the gap.", examples=[21539.5])
    gap_high: float = Field(..., description="Upper boundary of the gap.", examples=[21542.0])
    gap_size_ticks: int = Field(..., ge=0, description="Gap size expressed in ticks.", examples=[10])
    first_touch_at: datetime | None = Field(None, description="First touch time when available.")
    max_fill_ticks: int = Field(..., ge=0, description="Deepest repair observed so far, in ticks.", examples=[6])
    fill_ratio: float = Field(..., ge=0.0, le=1.0, description="Observed repaired fraction of the gap.", examples=[0.6])
    fill_attempt_count: int = Field(..., ge=0, description="How many fill attempts were observed.", examples=[1])
    accepted_inside_gap: bool | None = Field(None, description="Whether price has shown acceptance inside the gap.")
    rejected_from_gap: bool | None = Field(None, description="Whether price has rejected from the gap area.")
    fully_filled_at: datetime | None = Field(None, description="When the gap was fully repaired, if completed.")



class AdapterInitiativeDriveState(BaseModel):
    """Compact initiative-drive state used in the always-on adapter stream."""

    drive_id: str = Field(..., description="Drive identifier.")
    side: StructureSide = Field(..., description="Directional side of the drive.")
    started_at: datetime = Field(..., description="When the drive began.")
    price_low: float = Field(..., description="Lower boundary of the drive path.", examples=[21560.0])
    price_high: float = Field(..., description="Upper boundary of the drive path.", examples=[21574.25])
    aggressive_volume: int = Field(..., ge=0, description="Aggressive volume attributed to the drive.", examples=[1420])
    net_delta: int = Field(..., description="Net delta of the drive.", examples=[1180])
    trade_count: int = Field(..., ge=0, description="Trade count inside the drive.", examples=[268])
    consumed_price_levels: int = Field(..., ge=0, description="How many price levels were consumed.", examples=[7])
    price_travel_ticks: int = Field(..., ge=0, description="Drive travel in ticks.", examples=[57])
    max_counter_move_ticks: int = Field(..., ge=0, description="Largest counter move while the drive was active.", examples=[4])
    continuation_seconds: int = Field(..., ge=0, description="Continuation duration after the initial release.", examples=[80])



class AdapterManipulationLegState(BaseModel):
    """Compact manipulation-leg state used in the always-on adapter stream."""

    leg_id: str = Field(..., description="Manipulation-leg identifier.")
    side: StructureSide = Field(..., description="Directional side of the leg.")
    started_at: datetime = Field(..., description="When the manipulation leg began.")
    ended_at: datetime = Field(..., description="When the manipulation leg completed.")
    price_low: float = Field(..., description="Lower boundary of the leg.", examples=[21553.0])
    price_high: float = Field(..., description="Upper boundary of the leg.", examples=[21560.0])
    displacement_ticks: int = Field(..., ge=0, description="Leg size in ticks.", examples=[28])
    primary_objective_ticks: int | None = Field(None, ge=0, description="Primary objective in ticks.")
    secondary_objective_ticks: int | None = Field(None, ge=0, description="Secondary objective in ticks.")
    primary_objective_reached: bool = Field(..., description="Whether the primary objective was reached.")
    secondary_objective_reached: bool = Field(..., description="Whether the secondary objective was reached.")



class AdapterMeasuredMoveState(BaseModel):
    """Compact measured-move ladder state used in the always-on adapter stream."""

    measurement_id: str = Field(..., description="Measured-move identifier.")
    measured_subject_id: str = Field(..., description="Subject identifier being measured.")
    measured_subject_kind: str = Field(..., description="Subject kind being measured.", examples=["initiative_drive"])
    side: StructureSide = Field(..., description="Directional side of the measured move.")
    anchor_price: float = Field(..., description="Measurement anchor price.", examples=[21560.0])
    latest_price: float = Field(..., description="Latest price reached by the measured move.", examples=[21574.25])
    achieved_distance_ticks: int = Field(..., ge=0, description="Achieved distance in ticks.", examples=[57])
    reference_kind: MeasurementReferenceKind = Field(..., description="Reference family for the measurement.")
    reference_id: str | None = Field(None, description="Optional reference identifier.")
    reference_distance_ticks: int = Field(..., ge=1, description="Reference unit size in ticks.", examples=[28])
    achieved_multiple: float = Field(..., ge=0.0, description="Achieved multiple of the reference unit.", examples=[2.04])
    body_confirmed_threshold_multiple: float | None = Field(
        None,
        ge=0.0,
        description="Highest body-confirmed threshold multiple.",
        examples=[2.0],
    )
    next_target_multiple: float | None = Field(None, ge=0.0, description="Next target multiple on the ladder.", examples=[4.0])
    invalidated: bool = Field(False, description="Whether the measured ladder has been invalidated.")



class AdapterPostHarvestResponseState(BaseModel):
    """Compact post-harvest state used after a liquidity objective has been reached."""

    response_id: str = Field(..., description="Post-harvest response identifier.")
    harvest_subject_id: str = Field(..., description="Observed subject that completed the harvest.")
    harvest_subject_kind: str = Field(..., description="Kind of observed subject that completed the harvest.", examples=["initiative_drive"])
    harvest_side: StructureSide = Field(..., description="Directional side of the completed harvest move.")
    harvest_completed_at: datetime = Field(..., description="When the harvest was considered complete.")
    harvested_price_low: float = Field(..., description="Lower bound of the harvested price zone.", examples=[21573.5])
    harvested_price_high: float = Field(..., description="Upper bound of the harvested price zone.", examples=[21576.0])
    completion_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Observed completion ratio for the targeted liquidity pocket.",
        examples=[1.0],
    )
    continuation_ticks_after_completion: int = Field(
        ...,
        ge=0,
        description="Additional same-side travel after the harvest completed, in ticks.",
        examples=[6],
    )
    consolidation_range_ticks: int = Field(
        ...,
        ge=0,
        description="Observed consolidation width after the harvest completed, in ticks.",
        examples=[8],
    )
    pullback_ticks: int = Field(
        ...,
        ge=0,
        description="Largest pullback after the harvest completed, in ticks.",
        examples=[10],
    )
    reversal_ticks: int = Field(
        ...,
        ge=0,
        description="Largest opposite-direction reversal after the harvest completed, in ticks.",
        examples=[18],
    )
    seconds_to_first_pullback: int | None = Field(
        None,
        ge=0,
        description="Seconds between harvest completion and the first meaningful pullback.",
        examples=[11],
    )
    seconds_to_reversal: int | None = Field(
        None,
        ge=0,
        description="Seconds between harvest completion and the strongest reversal print.",
        examples=[54],
    )
    reached_next_opposing_liquidity: bool = Field(
        ...,
        description="Whether price reached the next opposing liquidity after completing the harvest.",
        examples=[True],
    )
    next_opposing_liquidity_price: float | None = Field(
        None,
        description="Observed price of the next opposing liquidity pocket when it was reached.",
        examples=[21567.0],
    )
    post_harvest_delta: int | None = Field(
        None,
        description="Net delta observed after completion inside the response window.",
        examples=[-212],
    )
    outcome: PostHarvestOutcome = Field(..., description="Observed outcome after the liquidity harvest completed.")



class AdapterPriceState(BaseModel):
    """Compact price-state snapshot for the current low-latency window."""

    last_price: float = Field(..., description="Last traded price.", examples=[21574.25])
    best_bid: float | None = Field(None, description="Current best bid.", examples=[21574.0])
    best_ask: float | None = Field(None, description="Current best ask.", examples=[21574.25])
    local_range_low: float = Field(..., description="Observed local range low.", examples=[21560.0])
    local_range_high: float = Field(..., description="Observed local range high.", examples=[21574.25])
    opening_range_low: float | None = Field(None, description="Opening range low when available.", examples=[21540.75])
    opening_range_high: float | None = Field(None, description="Opening range high when available.", examples=[21576.0])
    opening_range_size_ticks: int | None = Field(
        None,
        ge=0,
        description="Opening range size in ticks when available.",
        examples=[141],
    )



class AdapterReferenceLevel(BaseModel):
    """Additional compact location references attached to an adapter state message."""

    kind: str = Field(..., description="Reference family label.", examples=["upper_liquidity_band"])
    price: float = Field(..., description="Observed reference price.", examples=[21576.0])
    notes: list[str] = Field(
        default_factory=list,
        description="Short source-side notes for operator review.",
        examples=[["visible ask wall still above price during ascent"]],
    )



class AdapterSamePriceReplenishmentState(BaseModel):
    """Compact repeated-replenishment observation for a defended price."""

    track_id: str = Field(..., description="Tracked liquidity identifier.")
    side: StructureSide = Field(..., description="Side defending the price.")
    price: float = Field(..., description="Defended price.", examples=[21574.0])
    current_size: int = Field(..., ge=0, description="Current displayed size at the defended price.", examples=[64])
    distance_from_price_ticks: int = Field(..., ge=0, description="Distance from current price in ticks.", examples=[1])
    touch_count: int = Field(..., ge=0, description="Observed touch count at this price.", examples=[3])
    replenishment_count: int = Field(..., ge=0, description="Observed replenishment count at this price.", examples=[4])
    buyers_hitting_same_level_count: int = Field(..., ge=0, description="Buyer hits when the defended side is bid.", examples=[3])
    sellers_hitting_same_level_count: int = Field(..., ge=0, description="Seller hits when the defended side is ask.", examples=[0])



class AdapterSessionContext(BaseModel):
    """Always-on session references needed to rebuild the active script."""

    session_code: SessionCode = Field(..., description="Current trading session code.")
    trading_date: str = Field(..., description="Trading date in YYYY-MM-DD format.", examples=["2026-03-16"])
    is_rth_open: bool = Field(..., description="Whether the regular trading session is open.", examples=[True])
    prior_rth_close: float = Field(..., description="Prior regular-session close.", examples=[21539.5])
    prior_rth_high: float = Field(..., description="Prior regular-session high.", examples=[21548.25])
    prior_rth_low: float = Field(..., description="Prior regular-session low.", examples=[21492.75])
    prior_value_area_low: float | None = Field(None, description="Prior value area low when available.", examples=[21512.25])
    prior_value_area_high: float | None = Field(None, description="Prior value area high when available.", examples=[21538.5])
    prior_point_of_control: float | None = Field(None, description="Prior point of control when available.", examples=[21526.5])
    overnight_high: float | None = Field(None, description="Overnight session high.", examples=[21544.0])
    overnight_low: float | None = Field(None, description="Overnight session low.", examples=[21498.25])
    overnight_mid: float | None = Field(None, description="Overnight midpoint.", examples=[21521.125])



class AdapterSignificantLiquidityLevel(BaseModel):
    """Compact significant-liquidity state used by the always-on adapter stream."""

    track_id: str = Field(..., description="Stable track identifier.")
    side: StructureSide = Field(..., description="Book side of the tracked liquidity.")
    price: float = Field(..., description="Tracked price.", examples=[21576.0])
    current_size: int = Field(..., ge=0, description="Current displayed size.", examples=[188])
    max_seen_size: int = Field(..., ge=0, description="Largest displayed size seen so far.", examples=[342])
    distance_from_price_ticks: int = Field(..., ge=0, description="Distance from current price in ticks.", examples=[7])
    first_observed_at: datetime = Field(..., description="When the track first appeared.")
    last_observed_at: datetime = Field(..., description="Most recent update time for the track.")
    status: LargeLiquidityStatus = Field(..., description="Current lifecycle status of the track.")
    touch_count: int = Field(..., ge=0, description="How many touches or near-touches occurred.", examples=[2])
    executed_volume_estimate: int = Field(..., ge=0, description="Estimated executed volume at the tracked price.", examples=[104])
    replenishment_count: int = Field(..., ge=0, description="Observed replenishment count.", examples=[3])
    buyers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Observed buyer hits into the same price when this is a defending bid.",
        examples=[2],
    )
    sellers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Observed seller hits into the same price when this is a defending ask.",
        examples=[0],
    )
    pull_count: int = Field(..., ge=0, description="Observed pull count.", examples=[0])
    move_count: int = Field(..., ge=0, description="Observed repricing count.", examples=[0])
    price_reaction_ticks: int | None = Field(
        None,
        ge=0,
        description="Observed reaction after interacting with the level, in ticks.",
        examples=[5],
    )
    heat_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Normalized prominence score for the tracked liquidity.",
        examples=[0.87],
    )



class AdapterTradeSummary(BaseModel):
    """Always-on aggressive-trade summary for the current window."""

    trade_count: int = Field(..., ge=0, description="Observed trade count inside the window.", examples=[162])
    volume: int = Field(..., ge=0, description="Observed traded volume inside the window.", examples=[914])
    aggressive_buy_volume: int = Field(..., ge=0, description="Aggressive buy-side volume.", examples=[642])
    aggressive_sell_volume: int = Field(..., ge=0, description="Aggressive sell-side volume.", examples=[272])
    net_delta: int = Field(..., description="Observed net delta for the window.", examples=[370])



class AdapterTriggerType(str, Enum):
    SIGNIFICANT_LIQUIDITY_NEAR_TOUCH = "significant_liquidity_near_touch"
    LIQUIDITY_PULL = "liquidity_pull"
    LIQUIDITY_FILL = "liquidity_fill"
    GAP_FIRST_TOUCH = "gap_first_touch"
    GAP_PARTIAL_FILL = "gap_partial_fill"
    MEASURED_MOVE_THRESHOLD = "measured_move_threshold"
    PROBE_REVERSAL_CANDIDATE = "probe_reversal_candidate"
    FAILED_OVERHEAD_CAPPING = "failed_overhead_capping"
    OFFER_REVERSAL_RELEASE = "offer_reversal_release"
    HARVEST_COMPLETED = "harvest_completed"
    POST_HARVEST_PULLBACK = "post_harvest_pullback"
    POST_HARVEST_REVERSAL = "post_harvest_reversal"



class AdapterZoneInteraction(BaseModel):
    """Compact active-zone interaction state for probe or defense logic."""

    zone_id: str = Field(..., description="Adapter zone identifier.", examples=["probe-zone-21566-01"])
    zone_low: float = Field(..., description="Lower boundary of the active zone.", examples=[21565.5])
    zone_high: float = Field(..., description="Upper boundary of the active zone.", examples=[21566.5])
    started_at: datetime = Field(..., description="When the active interaction began.")
    executed_volume_against: int = Field(
        ...,
        ge=0,
        description="Executed volume observed against the zone.",
        examples=[184],
    )
    replenishment_count: int = Field(..., ge=0, description="Observed replenishment count.", examples=[2])
    buyers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Aggressive buy prints repeatedly hitting the same defended price or narrow zone.",
        examples=[3],
    )
    sellers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Aggressive sell prints repeatedly hitting the same defended price or narrow zone.",
        examples=[1],
    )
    pull_count: int = Field(..., ge=0, description="Observed pull count.", examples=[0])
    price_rejection_ticks: int = Field(..., ge=0, description="Observed reaction distance in ticks.", examples=[8])
    seconds_held: int = Field(..., ge=0, description="How long the zone has held so far.", examples=[12])



class DecisionLayerSet(BaseModel):
    """Decision-layered market context. This is the canonical observed-facts container."""

    macro_context: list[ObservedContextWindow] = Field(
        default_factory=list,
        description="Higher timeframe context: month, week, day.",
    )
    intraday_bias: list[ObservedContextWindow] = Field(
        default_factory=list,
        description="Bias context: last 3 days, 1h, 30m.",
    )
    setup_context: list[ObservedContextWindow] = Field(
        default_factory=list,
        description="Setup context: 15m and 5m.",
    )
    execution_context: list[ObservedContextWindow] = Field(
        default_factory=list,
        description="Execution context: 1m, footprint, DOM.",
    )

    @model_validator(mode="after")
    def validate_layer_timeframes(self) -> "DecisionLayerSet":
        self._validate_group("macro_context", self.macro_context, MACRO_TIMEFRAMES)
        self._validate_group("intraday_bias", self.intraday_bias, INTRADAY_TIMEFRAMES)
        self._validate_group("setup_context", self.setup_context, SETUP_TIMEFRAMES)
        self._validate_group("execution_context", self.execution_context, EXECUTION_TIMEFRAMES)
        return self

    @staticmethod
    def _validate_group(
        group_name: str,
        windows: list[ObservedContextWindow],
        allowed: set[Timeframe],
    ) -> None:
        for window in windows:
            if window.timeframe not in allowed:
                allowed_text = ", ".join(item.value for item in sorted(allowed, key=lambda value: value.value))
                raise ValueError(
                    f"{group_name} only accepts [{allowed_text}], got {window.timeframe.value}",
                )



class DepthCoverageState(str, Enum):
    UNAVAILABLE = "depth_unavailable"
    BOOTSTRAP = "depth_bootstrap"
    LIVE = "depth_live"
    INTERRUPTED = "depth_interrupted"



class DepthSnapshotAcceptedResponse(BaseModel):
    """REST response after a depth snapshot is ingested and memory is updated."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    coverage_state: DepthCoverageState = Field(..., description="Coverage state reported by the snapshot.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    updated_memories: list[LiquidityMemoryRecord] = Field(
        default_factory=list,
        description="Memory records created or updated by the snapshot.",
    )



class DepthSnapshotPayload(BaseModel):
    """Observed depth snapshot for elastic tracking of significant large orders."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0.0",
                "depth_snapshot_id": "depth-20260316-143001",
                "observed_at": "2026-03-16T14:30:01Z",
                "source": {
                    "system": "ATAS",
                    "instance_id": "DESKTOP-ATAS-01",
                    "adapter_version": "0.3.0",
                },
                "instrument": {
                    "symbol": "ESM6",
                    "venue": "CME",
                    "tick_size": 0.25,
                    "currency": "USD",
                },
                "coverage_state": "depth_live",
                "coverage_started_at": "2026-03-16T13:58:11Z",
                "best_bid": 4291.75,
                "best_ask": 4292.00,
                "reference_price": 4291.75,
                "significant_levels": [],
            },
        },
    )

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    depth_snapshot_id: str = Field(..., description="Producer-generated depth snapshot identifier.")
    observed_at: datetime = Field(..., description="Timestamp of the snapshot.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    coverage_state: DepthCoverageState = Field(..., description="Depth feed availability state at this moment.")
    coverage_started_at: datetime | None = Field(
        None,
        description="When the current uninterrupted depth coverage started, if known.",
    )
    best_bid: float | None = Field(None, description="Observed best bid at snapshot time.", examples=[4291.75])
    best_ask: float | None = Field(None, description="Observed best ask at snapshot time.", examples=[4292.00])
    reference_price: float | None = Field(
        None,
        description="Reference traded price used by the adapter when computing distance.",
        examples=[4291.75],
    )
    significant_levels: list[ObservedLargeLiquidityLevel] = Field(
        default_factory=list,
        description="Only the significant large order tracks selected by the adapter or local filter.",
    )



class DerivedBias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"



class DerivedGapAssessment(BaseModel):
    """Derived gap-fill context used by AI and later review workflows."""

    gap_id: str = Field(..., description="Observed gap identifier.")
    direction: GapDirection = Field(..., description="Direction of the gap reference.")
    gap_low: float = Field(..., description="Lower boundary of the observed gap.")
    gap_high: float = Field(..., description="Upper boundary of the observed gap.")
    fill_state: GapFillState = Field(..., description="Observed fill state of the gap.")
    fill_likelihood: GapFillLikelihood = Field(..., description="Derived likelihood that the gap will continue toward full repair.")
    directional_bias: DerivedBias = Field(..., description="Directional implication of the current gap interaction.")
    fill_ratio: float = Field(..., ge=0.0, le=1.0, description="Observed repaired fraction of the gap.")
    remaining_fill_ticks: int = Field(
        ...,
        ge=0,
        description="Ticks still remaining until the gap is fully repaired.",
    )
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed gap measurements referenced by the assessment.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about gap repair, acceptance, or rejection.",
    )



class DerivedKeyLevelAssessment(BaseModel):
    """Structured support and resistance context derived from exertion zones."""

    zone_id: str = Field(..., description="Observed exertion-zone identifier.")
    role: KeyLevelRole = Field(..., description="Current role of the zone for trading context.")
    state: KeyLevelState = Field(..., description="Most recent state of the zone.")
    price_low: float = Field(..., description="Lower boundary of the key level zone.")
    price_high: float = Field(..., description="Upper boundary of the key level zone.")
    directional_bias: DerivedBias = Field(..., description="Directional implication when price interacts with the zone.")
    strength_score: float = Field(..., ge=0.0, le=1.0, description="Normalized support or resistance strength score.")
    revisit_count: int = Field(..., ge=0, description="How many revisits the zone has already seen.")
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements referenced when scoring the zone.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about why the zone matters now.",
    )



class DerivedLiquidityMemoryInterpretation(BaseModel):
    """Derived interpretation for a tracked significant large order."""

    memory_id: str = Field(..., description="Stable memory identifier.")
    track_id: str = Field(..., description="Observed track identifier.")
    classification: LiquidityMemoryClassification = Field(..., description="High-value classification for the track.")
    directional_bias: DerivedBias = Field(..., description="Directional implication derived from the track outcome.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classifier confidence score.", examples=[0.81])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements referenced by the classifier.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived statements about the track and its likely outcome.",
    )



class DerivedProcessInterpretation(BaseModel):
    """Derived interpretation for process-aware observed data."""

    subject_id: str = Field(..., description="Observed subject identifier used by the recognizer.")
    subject_kind: str = Field(..., description="Observed subject type.", examples=["liquidity_episode"])
    directional_bias: DerivedBias = Field(..., description="Derived directional implication of the process data.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognizer confidence score.", examples=[0.72])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed measurements used by the recognizer.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived interpretation statements for process data.",
    )



class DerivedStructureAnalysis(BaseModel):
    """Top-level derived interpretation stored separately from observed payloads."""

    analysis_id: str = Field(..., description="Analysis record identifier.")
    ingestion_kind: str = Field(..., description="Source ingestion kind.", examples=["market_structure"])
    source_snapshot_id: str = Field(..., description="Original producer snapshot identifier.")
    generated_at: datetime = Field(..., description="When the derived analysis was created.")
    macro_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    intraday_bias: list[DerivedWindowInterpretation] = Field(default_factory=list)
    setup_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    execution_context: list[DerivedWindowInterpretation] = Field(default_factory=list)
    process_context: list[DerivedProcessInterpretation] = Field(
        default_factory=list,
        description="Derived process-aware interpretations spanning seconds to cross-session sequences.",
    )
    key_levels: list[DerivedKeyLevelAssessment] = Field(
        default_factory=list,
        description="Structured support and resistance assessments derived from exertion zones.",
    )
    gap_assessments: list[DerivedGapAssessment] = Field(
        default_factory=list,
        description="Derived gap-fill assessments for script and location context.",
    )
    knowledge_route: KnowledgeRoute = Field(..., description="Knowledge-base routing result.")
    analyst_flags: list[str] = Field(
        default_factory=list,
        description="Phase-1 machine-generated flags for operator review.",
    )



class DerivedWindowInterpretation(BaseModel):
    """Recognizer output for one timeframe. This is intentionally separate from observed facts."""

    timeframe: Timeframe = Field(..., description="Timeframe being interpreted.")
    directional_bias: DerivedBias = Field(..., description="Minimal derived directional bias.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Recognizer confidence score.", examples=[0.67])
    observations_used: list[str] = Field(
        default_factory=list,
        description="Observed facts referenced by the recognizer.",
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Derived interpretation statements based on observed facts.",
    )



class EventSnapshotPayload(BaseModel):
    """Top-level payload emitted on critical event triggers."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0.0",
                "event_snapshot_id": "evt-20260315-093200",
                "event_type": "liquidity_sweep",
                "observed_at": "2026-03-15T09:32:00Z",
                "source": {
                    "system": "ATAS",
                    "instance_id": "DESKTOP-ATAS-01",
                    "adapter_version": "0.1.0",
                },
                "instrument": {
                    "symbol": "NQH6",
                    "venue": "CME",
                    "tick_size": 0.25,
                    "currency": "USD",
                },
                "trigger_event": {
                    "event_type": "liquidity_sweep",
                    "observed_at": "2026-03-15T09:31:52Z",
                    "price": 21581.25,
                    "details": {"swept_level": "prior_day_high"},
                },
                "decision_layers": {
                    "macro_context": [],
                    "intraday_bias": [],
                    "setup_context": [],
                    "execution_context": [],
                },
                "process_context": {
                    "session_windows": [],
                    "second_features": [],
                    "liquidity_episodes": [],
                    "initiative_drives": [],
                    "measured_moves": [],
                    "manipulation_legs": [],
                    "gap_references": [],
                    "exertion_zones": [],
                    "cross_session_sequences": [],
                },
            },
        },
    )

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    event_snapshot_id: str = Field(..., description="Producer-generated event snapshot identifier.", examples=["evt-20260315-093200"])
    event_type: EventType = Field(..., description="Primary event type for the snapshot.")
    observed_at: datetime = Field(..., description="Timestamp of the event snapshot.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    trigger_event: ObservedEventMarker = Field(..., description="Observed event that triggered the snapshot.")
    decision_layers: DecisionLayerSet = Field(..., description="Decision-layered observed facts at trigger time.")
    process_context: ObservedProcessContext | None = Field(
        None,
        description="Optional process-aware context from seconds to cross-session sequences.",
    )



class EventType(str, Enum):
    BREAK_OF_STRUCTURE = "break_of_structure"
    CHANGE_OF_CHARACTER = "change_of_character"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    VALUE_AREA_REJECTION = "value_area_rejection"
    ORDERFLOW_IMBALANCE = "orderflow_imbalance"
    OTHER = "other"



class GapDirection(str, Enum):
    UP = "up"
    DOWN = "down"



class GapFillLikelihood(str, Enum):
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    PROBABLE = "probable"
    COMPLETED = "completed"



class GapFillState(str, Enum):
    UNTOUCHED = "untouched"
    PARTIAL_FILL = "partial_fill"
    FULLY_FILLED = "fully_filled"



class IngestionAcceptedResponse(BaseModel):
    """REST response after a payload is validated, stored, and analyzed."""

    ingestion_id: str = Field(..., description="Stored ingestion record identifier.")
    analysis_id: str = Field(..., description="Stored analysis record identifier.")
    route_key: str = Field(..., description="Selected knowledge route.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    analysis: DerivedStructureAnalysis = Field(..., description="Derived interpretation.")



class ReliableIngestionResponse(BaseModel):
    """Store-first ingestion response used by the reliability endpoints."""

    endpoint: str = Field(..., description="HTTP endpoint that accepted the payload.")
    ingestion_kind: str = Field(..., description="Observed ingestion kind persisted for the payload.")
    status: str = Field(..., description="Accepted/duplicate/store-only state for this request.")
    request_id: str | None = Field(None, description="Natural request identifier when the payload provides one.")
    dedup_key: str = Field(..., description="Idempotency key derived from request id or canonical payload hash.")
    payload_hash: str = Field(..., description="Canonical payload hash used for duplicate protection.")
    duplicate: bool = Field(False, description="Whether the request matched a previously stored payload.")
    stored_at: datetime | None = Field(None, description="Timestamp when the raw payload was durably stored.")
    ingestion_id: str | None = Field(None, description="Stored raw-ingestion identifier when persistence succeeded.")
    dead_letter_id: str | None = Field(None, description="Dead-letter identifier when the request was quarantined.")
    downstream_status: str = Field(..., description="Status of non-critical post-store processing.")
    downstream_result: dict[str, Any] | None = Field(
        None,
        description="Optional downstream output generated after the raw payload was persisted.",
    )
    profile_version: str = Field(..., description="Instrument profile version attached to this response.")
    engine_version: str = Field(..., description="Recognizer build version attached to this response.")
    schema_version: str = Field(..., description="Response schema version.")
    data_status: BeliefDataStatus = Field(..., description="Freshness/completeness state for UI and recognition consumers.")
    freshness: str | None = Field(None, description="Compact freshness label copied from data_status.")
    completeness: str | None = Field(None, description="Compact completeness label copied from data_status.")


class IngestionErrorResponse(BaseModel):
    """Standard error envelope for reliability ingestion endpoints."""

    error: str = Field(..., description="Stable error code.")
    detail: Any = Field(..., description="Structured error detail.")
    endpoint: str = Field(..., description="HTTP endpoint that rejected the payload.")
    ingestion_kind: str = Field(..., description="Target ingestion kind for the rejected payload.")
    request_id: str | None = Field(None, description="Natural request identifier when one could be extracted.")
    dedup_key: str | None = Field(None, description="Derived idempotency key when one could be extracted.")
    payload_hash: str | None = Field(None, description="Payload hash when one could be computed.")
    dead_letter_id: str | None = Field(None, description="Dead-letter identifier if the payload was quarantined.")
    profile_version: str = Field(..., description="Instrument profile version attached to this error response.")
    engine_version: str = Field(..., description="Recognizer build version attached to this error response.")
    schema_version: str = Field(..., description="Response schema version.")


class IngestionMetricsSnapshot(BaseModel):
    """Compact counters derived from recent ingestion run logs."""

    total_count: int = Field(..., ge=0, description="Total run-log rows included in the metrics window.")
    accepted_count: int = Field(..., ge=0, description="Successful accepted ingestions.")
    duplicate_count: int = Field(..., ge=0, description="Duplicate submissions absorbed by idempotency.")
    dead_letter_count: int = Field(..., ge=0, description="Requests written to dead letter.")
    downstream_failure_count: int = Field(..., ge=0, description="Post-store failures that did not block raw persistence.")


class IngestionRunLogEntry(BaseModel):
    """Recent ingestion run-log row surfaced by health endpoints."""

    run_id: str = Field(..., description="Run-log identifier.")
    endpoint: str = Field(..., description="Endpoint that handled the request.")
    ingestion_kind: str = Field(..., description="Observed ingestion kind.")
    instrument_symbol: str | None = Field(None, description="Instrument symbol when available.")
    request_id: str | None = Field(None, description="Natural request identifier when available.")
    dedup_key: str = Field(..., description="Derived idempotency key.")
    payload_hash: str = Field(..., description="Canonical payload hash.")
    outcome: str = Field(..., description="Accepted/duplicate/dead-letter/downstream-failed outcome.")
    http_status: int = Field(..., description="HTTP status returned to the caller.")
    ingestion_id: str | None = Field(None, description="Raw-ingestion identifier when persistence succeeded.")
    dead_letter_id: str | None = Field(None, description="Dead-letter identifier when one was created.")
    detail: dict[str, Any] = Field(default_factory=dict, description="Structured run-log detail for operators.")
    started_at: datetime = Field(..., description="When processing began.")
    completed_at: datetime = Field(..., description="When processing finished.")


class IngestionHealthResponse(BaseModel):
    """Health and recent-run summary for the ingestion plane."""

    status: ServiceHealthStatus = Field(..., description="Overall ingestion-plane health state.")
    degraded_reasons: list[str] = Field(default_factory=list, description="Explicit degraded reasons for operators and UI.")
    profile_version: str = Field(..., description="Instrument profile version attached to this health payload.")
    engine_version: str = Field(..., description="Recognizer build version attached to this health payload.")
    schema_version: str = Field(..., description="Health payload schema version.")
    data_status: BeliefDataStatus = Field(..., description="Data freshness/completeness state surfaced to UI and recognition.")
    freshness: str | None = Field(None, description="Compact freshness label copied from data_status.")
    completeness: str | None = Field(None, description="Compact completeness label copied from data_status.")
    last_success_at: datetime | None = Field(None, description="Most recent accepted raw-ingestion timestamp.")
    last_dead_letter_at: datetime | None = Field(None, description="Most recent dead-letter timestamp.")
    last_run_at: datetime | None = Field(None, description="Most recent run-log completion timestamp.")
    metrics: IngestionMetricsSnapshot = Field(..., description="Recent ingestion counters.")
    recent_runs: list[IngestionRunLogEntry] = Field(default_factory=list, description="Tail of recent run-log entries.")


class DataQualitySourceStatus(BaseModel):
    """Per-source freshness/completeness summary used by recognition and UI."""

    source_kind: str = Field(..., description="Observed source family.")
    latest_observed_at: datetime | None = Field(None, description="Latest timestamp observed for this source.")
    available: bool = Field(..., description="Whether at least one recent payload was available.")
    freshness_ms: int | None = Field(None, ge=0, description="Age in milliseconds from now to latest_observed_at.")


class DataQualityResponse(BaseModel):
    """Current data-quality envelope consumed by recognition and UI layers."""

    status: ServiceHealthStatus = Field(..., description="Overall data-quality health state.")
    degraded_reasons: list[str] = Field(default_factory=list, description="Explicit degraded reasons active right now.")
    instrument_symbol: str | None = Field(None, description="Instrument symbol the quality snapshot is scoped to.")
    profile_version: str = Field(..., description="Instrument profile version attached to this quality payload.")
    engine_version: str = Field(..., description="Recognizer build version attached to this quality payload.")
    schema_version: str = Field(..., description="Quality payload schema version.")
    data_status: BeliefDataStatus = Field(..., description="Belief-style data status for recognition and UI consumers.")
    freshness: str | None = Field(None, description="Compact freshness label copied from data_status.")
    completeness: str | None = Field(None, description="Compact completeness label copied from data_status.")
    source_statuses: list[DataQualitySourceStatus] = Field(
        default_factory=list,
        description="Latest availability/freshness state for each observed source family.",
    )


class InstrumentRef(BaseModel):
    """Stable instrument metadata for replay and backtests."""

    symbol: str = Field(..., description="Trading symbol.", examples=["NQH6"])
    venue: str = Field(..., description="Execution or quote venue.", examples=["CME"])
    tick_size: float = Field(..., gt=0, description="Minimum price increment.", examples=[0.25])
    currency: str = Field(..., description="PnL currency.", examples=["USD"])



class KeyLevelRole(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"
    PIVOT = "pivot"



class KeyLevelState(str, Enum):
    MONITORING = "monitoring"
    DEFENDED = "defended"
    BROKEN = "broken"
    FLIPPED = "flipped"



class KnowledgeRoute(BaseModel):
    """Routing hint for future playbook or retrieval augmentation selection."""

    route_key: str = Field(..., description="Stable route identifier.", examples=["trend_continuation_review"])
    summary: str = Field(..., description="Short explanation for the route choice.")
    required_context: list[str] = Field(
        default_factory=list,
        description="Context categories the next stage should load.",
        examples=[["macro_context", "intraday_bias", "execution_context"]],
    )



class LargeLiquidityStatus(str, Enum):
    ACTIVE = "active"
    PULLED = "pulled"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    MOVED = "moved"
    EXPIRED = "expired"



class LiquidityLevelType(str, Enum):
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"
    PRIOR_DAY_HIGH = "prior_day_high"
    PRIOR_DAY_LOW = "prior_day_low"
    WEEKLY_EXTREME = "weekly_extreme"
    COMPOSITE_POC = "composite_poc"
    MANUAL = "manual"



class LiquidityMemoryClassification(str, Enum):
    MONITORING = "monitoring"
    SPOOF_CANDIDATE = "spoof_candidate"
    ABSORPTION_CANDIDATE = "absorption_candidate"
    MAGNET_CANDIDATE = "magnet_candidate"
    DEFENDED_LEVEL_CANDIDATE = "defended_level_candidate"



class LiquidityMemoryEnvelope(BaseModel):
    """REST response for listing active significant liquidity memories."""

    memories: list[LiquidityMemoryRecord] = Field(default_factory=list)



class LiquidityMemoryRecord(BaseModel):
    """Persisted 3-day memory of a significant large order track."""

    memory_id: str = Field(..., description="Stable memory identifier.")
    track_key: str = Field(..., description="Unique backend track key.")
    instrument_symbol: str = Field(..., description="Instrument symbol.")
    coverage_state: DepthCoverageState = Field(..., description="Latest coverage state when the record was updated.")
    observed_track: ObservedLargeLiquidityLevel = Field(..., description="Latest observed summary of the track.")
    derived_interpretation: DerivedLiquidityMemoryInterpretation = Field(
        ...,
        description="Derived classification of the track outcome.",
    )
    expires_at: datetime = Field(..., description="Expiration time for the 3-day memory.")
    updated_at: datetime = Field(..., description="Last update timestamp.")



class MachineStrategyCard(BaseModel):
    """Machine-readable strategy card consumed by replay and AI services."""

    schema_version: str = Field(..., description="Strategy-card schema version.")
    strategy_id: str = Field(..., description="Stable strategy identifier.")
    title: str = Field(..., description="Short display title.")
    status: str = Field(..., description="Strategy-library status marker.")
    source_path: str = Field(..., description="Source markdown path for the human card.")
    instrument_scope: list[str] = Field(default_factory=list, description="Instruments this card applies to.")
    session_scope: list[str] = Field(default_factory=list, description="Sessions this card applies to.")
    timeframe_scope: list[str] = Field(default_factory=list, description="Decision layers or timeframe families.")
    preferred_presets: list[str] = Field(default_factory=list, description="Replay AI presets where this card is most relevant.")
    context_tags: list[str] = Field(default_factory=list, description="Context tags used for routing and review.")
    event_kinds: list[str] = Field(default_factory=list, description="Replay event kinds associated with the card.")
    reason_codes: list[str] = Field(default_factory=list, description="Focus-region or event reason codes associated with the card.")
    summary: MachineStrategySummary = Field(..., description="Structured card summary.")
    when_relevant: list[str] = Field(default_factory=list, description="Contexts where the card becomes relevant.")
    required_evidence: list[str] = Field(default_factory=list, description="Observed evidence that must be present.")
    confirmation_signals: list[str] = Field(default_factory=list, description="Signals that confirm the card.")
    invalidation_signals: list[str] = Field(default_factory=list, description="Signals that invalidate the card.")
    no_trade_conditions: list[str] = Field(default_factory=list, description="Conditions where the operator should not open.")
    entry_archetypes: list[MachineStrategyEntryArchetype] = Field(default_factory=list, description="Supported entry families.")
    management_notes: list[str] = Field(default_factory=list, description="Management and post-entry notes.")
    review_questions: list[str] = Field(default_factory=list, description="Questions to use during replay review.")
    machine_hints: MachineStrategyHints = Field(..., description="Machine-facing hints for matching and ranking.")



class MachineStrategyEntryArchetype(BaseModel):
    """Reusable entry family attached to one strategy card."""

    name: str = Field(..., description="Short entry archetype name.")
    description: str = Field(..., description="What the entry looks like.")
    risk_note: str = Field(..., description="Primary risk note or disqualifier.")



class MachineStrategyHints(BaseModel):
    """Machine hints used by replay builder and AI routing."""

    candidate_priority: float = Field(..., ge=0.0, le=1.0, description="How strongly this card should be surfaced.")
    match_requirements: "MachineStrategyMatchRequirements" = Field(
        default_factory=lambda: MachineStrategyMatchRequirements(),
        description="Structured matching requirements.",
    )
    disqualifiers: list[str] = Field(default_factory=list, description="Conditions that should suppress the card.")
    focus_region_bias: list[str] = Field(default_factory=list, description="Preferred region roles or target types.")
    entry_review_bias: list[str] = Field(default_factory=list, description="Operator-entry mistakes to emphasize.")



class MachineStrategyIndex(BaseModel):
    """Top-level machine-readable strategy index."""

    schema_version: str = Field(..., description="Index schema version.")
    generated_at: datetime = Field(..., description="When the index file was generated.")
    strategies: list[MachineStrategyIndexEntry] = Field(default_factory=list, description="Indexed strategy entries.")



class MachineStrategyIndexEntry(BaseModel):
    """Compact strategy index entry used for strategy-card lookup."""

    strategy_id: str = Field(..., description="Stable strategy identifier.")
    title: str = Field(..., description="Short display title.")
    status: str = Field(..., description="Strategy status marker.")
    source_path: str = Field(..., description="Source markdown path.")
    machine_card_path: str = Field(..., description="Path to the machine-readable card JSON.")
    instrument_scope: list[str] = Field(default_factory=list, description="Supported instruments.")
    session_scope: list[str] = Field(default_factory=list, description="Supported sessions.")
    preferred_presets: list[str] = Field(default_factory=list, description="Replay AI presets where this card is most relevant.")
    event_kinds: list[str] = Field(default_factory=list, description="Event kinds associated with the card.")
    reason_codes: list[str] = Field(default_factory=list, description="Reason codes associated with the card.")
    candidate_priority: float = Field(..., ge=0.0, le=1.0, description="Candidate ranking priority.")



class MachineStrategyMatchRequirements(BaseModel):
    """Machine-readable requirements for candidate matching and filtering."""

    event_kinds_all: list[str] = Field(default_factory=list, description="Event kinds that must all be present.")
    reason_codes_any: list[str] = Field(default_factory=list, description="Reason codes where any one is sufficient.")
    focus_region_role_any: list[str] = Field(default_factory=list, description="Allowed focus-region roles.")



class MachineStrategySummary(BaseModel):
    """Human and AI oriented summary for one strategy card."""

    thesis: str = Field(..., description="Compact thesis statement.")
    operator_translation: str = Field(..., description="How the operator should apply the card in practice.")
    ai_usage_note: str = Field(..., description="How the AI layer should use this card.")



class MarketStructurePayload(BaseModel):
    """Top-level payload sent every 10 minutes from ATAS."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0.0",
                "snapshot_id": "ms-20260315-093000",
                "observed_at": "2026-03-15T09:30:00Z",
                "source": {
                    "system": "ATAS",
                    "instance_id": "DESKTOP-ATAS-01",
                    "adapter_version": "0.1.0",
                },
                "instrument": {
                    "symbol": "NQH6",
                    "venue": "CME",
                    "tick_size": 0.25,
                    "currency": "USD",
                },
                "decision_layers": {
                    "macro_context": [],
                    "intraday_bias": [],
                    "setup_context": [],
                    "execution_context": [],
                },
                "process_context": {
                    "session_windows": [],
                    "second_features": [],
                    "liquidity_episodes": [],
                    "initiative_drives": [],
                    "measured_moves": [],
                    "manipulation_legs": [],
                    "gap_references": [],
                    "post_harvest_responses": [],
                    "exertion_zones": [],
                    "cross_session_sequences": [],
                },
                "observed_events": [],
            },
        },
    )

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    snapshot_id: str = Field(..., description="Producer-generated snapshot identifier.", examples=["ms-20260315-093000"])
    observed_at: datetime = Field(..., description="Timestamp of the complete snapshot.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    decision_layers: DecisionLayerSet = Field(..., description="Decision-layered observed facts.")
    process_context: ObservedProcessContext | None = Field(
        None,
        description="Optional process-aware context from seconds to cross-session sequences.",
    )
    observed_events: list[ObservedEventMarker] = Field(
        default_factory=list,
        description="Observed event markers associated with this 10-minute snapshot.",
    )



class MeasurementReferenceKind(str, Enum):
    MANIPULATION_LEG = "manipulation_leg"
    RANGE_AMPLITUDE = "range_amplitude"
    INITIATIVE_DRIVE = "initiative_drive"
    OPENING_RANGE = "opening_range"
    GAP_SPAN = "gap_span"



class ObservationOriginMode(str, Enum):
    BOOTSTRAP = "bootstrap"
    LIVE = "live"



class ObservedContextWindow(BaseModel):
    """Observed facts for one timeframe within one decision layer."""

    timeframe: Timeframe = Field(..., description="Timeframe for this context window.")
    bars_considered: int = Field(..., ge=1, description="Number of bars used by the producer.", examples=[24])
    latest_range: ObservedRange = Field(..., description="Latest observed range for the timeframe.")
    swing_points: list[ObservedSwingPoint] = Field(
        default_factory=list,
        description="Observed swing sequence available to downstream recognizers.",
    )
    liquidity_levels: list[ObservedLiquidityLevel] = Field(
        default_factory=list,
        description="Observed liquidity references relevant to the timeframe.",
    )
    orderflow_signals: list[ObservedOrderFlowSignal] = Field(
        default_factory=list,
        description="Observed order-flow events captured for the timeframe.",
    )
    value_area: ObservedValueArea | None = Field(
        None,
        description="Observed value area snapshot when available.",
    )
    session_stats: ObservedSessionStats | None = Field(
        None,
        description="Observed session aggregate statistics when available.",
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional raw facts for future backward-compatible extensions.",
        examples=[{"distance_to_vah_ticks": 8, "opening_drive_up": True}],
    )



class ObservedCrossSessionSequence(BaseModel):
    """Observed sequence that links process data across multiple sessions."""

    sequence_id: str = Field(..., description="Stable cross-session sequence identifier.")
    started_at: datetime = Field(..., description="Sequence start time.")
    last_observed_at: datetime = Field(..., description="Most recent time the sequence was updated.")
    session_sequence: list[SessionCode] = Field(
        default_factory=list,
        description="Sessions already involved in the sequence.",
        examples=[["europe", "us_regular"]],
    )
    price_zone_low: float = Field(..., description="Observed lower boundary of the active price zone.", examples=[21528.75])
    price_zone_high: float = Field(..., description="Observed upper boundary of the active price zone.", examples=[21548.25])
    start_price: float = Field(..., description="Observed price when the sequence started.", examples=[21533.25])
    latest_price: float = Field(..., description="Most recent observed price for the sequence.", examples=[21570.25])
    linked_episode_ids: list[str] = Field(
        default_factory=list,
        description="Liquidity episode identifiers attached to the sequence.",
        examples=[["ep-europe-absorb-01"]],
    )
    linked_drive_ids: list[str] = Field(
        default_factory=list,
        description="Initiative-drive identifiers attached to the sequence.",
        examples=[["drive-us-open-01"]],
    )
    linked_exertion_zone_ids: list[str] = Field(
        default_factory=list,
        description="Exertion-zone identifiers attached to the sequence.",
        examples=[["zone-europe-bid-01"]],
    )
    linked_event_ids: list[str] = Field(
        default_factory=list,
        description="Observed event identifiers attached to the sequence.",
        examples=[["evt-20260315-093200"]],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured sequence features for replay and scoring.",
        examples=[{"zone_hold_seconds": 1380, "release_velocity_ticks_per_minute": 24.5}],
    )



class ObservedEventMarker(BaseModel):
    """Producer-side marker used to attach notable events to a snapshot."""

    event_type: EventType = Field(..., description="Observed event category.")
    observed_at: datetime = Field(..., description="When the event was observed.")
    price: float | None = Field(None, description="Associated event price if available.", examples=[21581.25])
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional raw event facts emitted by the producer.",
        examples=[{"swept_level": "prior_day_high", "reclaimed_within_bars": 2}],
    )



class ObservedExertionZone(BaseModel):
    """Historically important price zone created by prior large executed volume and exertion."""

    zone_id: str = Field(..., description="Stable exertion-zone identifier.")
    source_drive_id: str = Field(..., description="Initiative-drive identifier that established the zone.")
    side: StructureSide = Field(..., description="Side that originally pushed from the zone.")
    price_low: float = Field(..., description="Lower bound of the exertion zone.", examples=[21534.5])
    price_high: float = Field(..., description="Upper bound of the exertion zone.", examples=[21536.25])
    established_at: datetime = Field(..., description="When the zone first became important.")
    last_interacted_at: datetime = Field(..., description="Most recent revisit or interaction time.")
    establishing_volume: int = Field(
        ...,
        ge=0,
        description="Observed total traded volume that established the zone.",
        examples=[2280],
    )
    establishing_delta: int = Field(
        ...,
        description="Observed net delta while the zone was being established.",
        examples=[1180],
    )
    establishing_trade_count: int = Field(
        ...,
        ge=0,
        description="Observed trade count during the establishing burst.",
        examples=[344],
    )
    peak_price_level_volume: int | None = Field(
        None,
        ge=0,
        description="Largest observed price-level executed volume inside the zone when available.",
        examples=[640],
    )
    revisit_count: int = Field(
        ...,
        ge=0,
        description="How many times price revisited the zone after establishment.",
        examples=[2],
    )
    successful_reengagement_count: int = Field(
        ...,
        ge=0,
        description="Observed revisits where the original side responded again from the zone.",
        examples=[1],
    )
    failed_reengagement_count: int = Field(
        ...,
        ge=0,
        description="Observed revisits where the original side failed to defend or re-fire from the zone.",
        examples=[0],
    )
    last_revisit_delta: int = Field(
        ...,
        description="Observed delta during the most recent revisit window.",
        examples=[486],
    )
    last_revisit_volume: int = Field(
        ...,
        ge=0,
        description="Observed traded volume during the most recent revisit window.",
        examples=[712],
    )
    last_revisit_trade_count: int = Field(
        ...,
        ge=0,
        description="Observed trade count during the most recent revisit window.",
        examples=[128],
    )
    last_defended_reaction_ticks: int = Field(
        ...,
        ge=0,
        description="Reaction achieved after the latest successful defense, in ticks.",
        examples=[16],
    )
    last_failed_break_ticks: int = Field(
        ...,
        ge=0,
        description="Distance price moved through the zone after the latest failure, in ticks.",
        examples=[0],
    )
    post_failure_delta: int | None = Field(
        None,
        description="Observed delta after the latest failure window, useful for stop-driven follow-through.",
        examples=[-540],
    )
    post_failure_move_ticks: int | None = Field(
        None,
        ge=0,
        description="Follow-through distance after the latest failure, in ticks.",
        examples=[18],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured zone features for replay and context-building.",
        examples=[{"origin_session": "europe", "trapped_volume_estimate": 340}],
    )



class ObservedGapReference(BaseModel):
    """Observed session gap and its interaction history."""

    gap_id: str = Field(..., description="Stable gap identifier.")
    session_code: SessionCode = Field(..., description="Session where the gap reference is anchored.")
    opened_at: datetime = Field(..., description="Timestamp when the gap became active.")
    direction: GapDirection = Field(..., description="Whether the session opened above or below the prior reference.")
    prior_reference_price: float = Field(
        ...,
        description="Reference price from the prior auction, usually prior session close or value edge.",
        examples=[21548.25],
    )
    current_open_price: float = Field(
        ...,
        description="Observed open price that created the gap reference.",
        examples=[21542.0],
    )
    gap_low: float = Field(..., description="Lower boundary of the gap.", examples=[21542.0])
    gap_high: float = Field(..., description="Upper boundary of the gap.", examples=[21548.25])
    gap_size_ticks: int = Field(
        ...,
        ge=0,
        description="Observed gap size expressed in ticks.",
        examples=[25],
    )
    first_touch_at: datetime | None = Field(
        None,
        description="First time price traded back into the gap, if it has happened.",
    )
    max_fill_ticks: int = Field(
        ...,
        ge=0,
        description="Deepest observed penetration into the gap, in ticks.",
        examples=[16],
    )
    fill_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Observed fraction of the gap that has been repaired so far.",
        examples=[0.64],
    )
    fill_attempt_count: int = Field(
        ...,
        ge=0,
        description="How many observed attempts have interacted with the gap.",
        examples=[2],
    )
    accepted_inside_gap: bool | None = Field(
        None,
        description="Whether price has shown acceptance inside the gap area.",
        examples=[True],
    )
    rejected_from_gap: bool | None = Field(
        None,
        description="Whether price has rejected after entering or touching the gap area.",
        examples=[False],
    )
    fully_filled_at: datetime | None = Field(
        None,
        description="Timestamp when the gap was fully filled, if completed.",
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional observed facts such as distance-to-fill or value relationship.",
        examples=[{"distance_to_fill_ticks": 9, "inside_balance": False}],
    )

    @model_validator(mode="after")
    def validate_gap_metrics(self) -> "ObservedGapReference":
        if self.max_fill_ticks > self.gap_size_ticks:
            raise ValueError("max_fill_ticks cannot exceed gap_size_ticks")
        if self.fully_filled_at is not None and self.fill_ratio < 1.0:
            raise ValueError("fully filled gaps must report fill_ratio >= 1.0")
        return self



class ObservedInitiativeDrive(BaseModel):
    """Measured aggressive-order push that moved price away from a zone."""

    drive_id: str = Field(..., description="Stable initiative-drive identifier.")
    started_at: datetime = Field(..., description="Drive start timestamp.")
    ended_at: datetime = Field(..., description="Drive end timestamp.")
    side: StructureSide = Field(..., description="Aggressive side that initiated the push.")
    price_low: float = Field(..., description="Lower bound of the drive origin or drive path.", examples=[21534.5])
    price_high: float = Field(..., description="Upper bound of the drive origin or drive path.", examples=[21541.5])
    aggressive_volume: int = Field(
        ...,
        ge=0,
        description="Observed aggressive traded volume attributed to the drive.",
        examples=[1840],
    )
    net_delta: int = Field(
        ...,
        description="Observed net delta during the drive window.",
        examples=[1260],
    )
    trade_count: int = Field(
        ...,
        ge=0,
        description="Observed number of trades inside the drive window.",
        examples=[320],
    )
    consumed_price_levels: int = Field(
        ...,
        ge=0,
        description="How many price levels were consumed or lifted during the drive.",
        examples=[9],
    )
    price_travel_ticks: int = Field(
        ...,
        ge=0,
        description="Observed travel distance achieved by the drive, in ticks.",
        examples=[28],
    )
    max_counter_move_ticks: int = Field(
        ...,
        ge=0,
        description="Largest counter move observed while the drive was active, in ticks.",
        examples=[6],
    )
    continuation_seconds: int = Field(
        ...,
        ge=0,
        description="How long price continued in the drive direction after the initial push.",
        examples=[170],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured drive features for replay and later modeling.",
        examples=[{"aggressive_trade_burst_per_second": 42, "max_sweep_ticks": 7}],
    )



class ObservedLargeLiquidityLevel(BaseModel):
    """Observed summary for one significant large order track."""

    track_id: str = Field(..., description="Stable track identifier from the adapter.")
    side: StructureSide = Field(..., description="Book side where the large order is observed.")
    price: float = Field(..., description="Observed price of the large order.", examples=[4292.00])
    current_size: int = Field(..., ge=0, description="Current displayed size.", examples=[245])
    max_seen_size: int = Field(..., ge=0, description="Largest displayed size seen for this track.", examples=[812])
    distance_from_price_ticks: int = Field(
        ...,
        ge=0,
        description="Distance from the current traded price in ticks.",
        examples=[5],
    )
    first_observed_at: datetime = Field(..., description="When this track was first observed.")
    last_observed_at: datetime = Field(..., description="Most recent update for this track.")
    first_seen_mode: ObservationOriginMode = Field(
        ...,
        description="Whether the track already existed at bootstrap or originated during live tracking.",
    )
    status: LargeLiquidityStatus = Field(..., description="Latest observed status for this track.")
    touch_count: int = Field(..., ge=0, description="How many times price touched or nearly touched the level.", examples=[3])
    executed_volume_estimate: int = Field(
        ...,
        ge=0,
        description="Observed executed volume estimate at the tracked price or zone.",
        examples=[96],
    )
    replenishment_count: int = Field(..., ge=0, description="Observed replenishment count.", examples=[4])
    pull_count: int = Field(..., ge=0, description="Observed pull or cancel count.", examples=[1])
    move_count: int = Field(..., ge=0, description="Observed repricing count for the track.", examples=[0])
    price_reaction_ticks: int | None = Field(
        None,
        ge=0,
        description="Measured reaction after interaction with the level, in ticks.",
        examples=[12],
    )
    heat_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Normalized prominence score for the level in the local order book.",
        examples=[0.91],
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Short adapter-side observations about the track.",
        examples=[["large ask wall remained visible for 41 seconds"]],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional observed metrics for replay and later modeling.",
        examples=[{"seconds_visible": 41, "near_touch_without_fill": True}],
    )



class ObservedLiquidityEpisode(BaseModel):
    """Measured price-band interaction episode, still kept as observed facts."""

    episode_id: str = Field(..., description="Stable episode identifier.")
    started_at: datetime = Field(..., description="Episode start timestamp.")
    ended_at: datetime = Field(..., description="Episode end timestamp.")
    side: StructureSide = Field(..., description="Dominant side associated with the episode.")
    price_low: float = Field(..., description="Lower bound of the defended or contested zone.", examples=[21528.75])
    price_high: float = Field(..., description="Upper bound of the defended or contested zone.", examples=[21534.5])
    executed_volume_against: int = Field(
        ...,
        ge=0,
        description="Observed executed volume hitting the zone from the opposite side.",
        examples=[1284],
    )
    replenishment_count: int = Field(
        ...,
        ge=0,
        description="Observed number of replenishment events near the zone.",
        examples=[6],
    )
    buyers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Observed count of aggressive buyers repeatedly hitting the same defended price or zone.",
        examples=[4],
    )
    sellers_hitting_same_level_count: int = Field(
        0,
        ge=0,
        description="Observed count of aggressive sellers repeatedly hitting the same defended price or zone.",
        examples=[2],
    )
    pull_count: int = Field(
        ...,
        ge=0,
        description="Observed number of liquidity pull events near the zone.",
        examples=[1],
    )
    price_rejection_ticks: int = Field(
        ...,
        ge=0,
        description="Observed rejection distance after interaction, in ticks.",
        examples=[18],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured episode features.",
        examples=[{"max_resting_bid": 812, "seconds_held": 54}],
    )



class ObservedLiquidityLevel(BaseModel):
    """A price level derived by the producer and stored as an observed fact."""

    level_type: LiquidityLevelType = Field(..., description="Observed liquidity reference type.")
    price: float = Field(..., description="Observed level price.", examples=[21580.00])
    first_seen_at: datetime = Field(..., description="When this level first entered the current dataset.")
    touch_count: int = Field(..., ge=0, description="Number of observed touches.", examples=[1])
    swept: bool = Field(..., description="Whether price traded through the level.", examples=[False])



class ObservedManipulationLeg(BaseModel):
    """Observed forcing leg used later for range, trap, or extension analysis."""

    leg_id: str = Field(..., description="Stable manipulation-leg identifier.")
    started_at: datetime = Field(..., description="Manipulation leg start timestamp.")
    ended_at: datetime = Field(..., description="Manipulation leg end timestamp.")
    side: StructureSide = Field(..., description="Directional side of the forcing leg.")
    price_low: float = Field(..., description="Lower bound of the leg.", examples=[21547.0])
    price_high: float = Field(..., description="Upper bound of the leg.", examples=[21555.0])
    displacement_ticks: int = Field(
        ...,
        ge=0,
        description="Observed size of the manipulation leg, in ticks.",
        examples=[32],
    )
    linked_zone_id: str | None = Field(
        None,
        description="Related exertion zone or key zone when the leg originates from one.",
        examples=["zone-europe-ask-01"],
    )
    primary_objective_ticks: int | None = Field(
        None,
        ge=0,
        description="First observed objective for the leg, in ticks.",
        examples=[32],
    )
    secondary_objective_ticks: int | None = Field(
        None,
        ge=0,
        description="Second observed objective for the leg, in ticks.",
        examples=[64],
    )
    primary_objective_reached: bool = Field(
        ...,
        description="Whether the first objective was reached.",
        examples=[True],
    )
    secondary_objective_reached: bool = Field(
        ...,
        description="Whether the second objective was reached.",
        examples=[False],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional facts about trap context, displacement, or distribution after the leg.",
        examples=[{"post_leg_distribution_seconds": 90, "trap_side": "sell"}],
    )



class ObservedMeasuredMove(BaseModel):
    """Measured price expansion expressed as a multiple of a reference leg or range."""

    measurement_id: str = Field(..., description="Stable measurement identifier.")
    measured_subject_id: str = Field(..., description="Observed subject that is being measured.")
    measured_subject_kind: str = Field(
        ...,
        description="Observed subject kind being measured.",
        examples=["initiative_drive"],
    )
    started_at: datetime = Field(..., description="Measurement start timestamp.")
    ended_at: datetime = Field(..., description="Measurement end timestamp.")
    side: StructureSide = Field(..., description="Directional side of the measured move.")
    anchor_price: float = Field(..., description="Price where the measured expansion began.", examples=[21558.25])
    latest_price: float = Field(..., description="Latest price reached by the measured move.", examples=[21574.25])
    achieved_distance_ticks: int = Field(
        ...,
        ge=0,
        description="Observed travel distance achieved by the measured move, in ticks.",
        examples=[64],
    )
    reference_kind: MeasurementReferenceKind = Field(
        ...,
        description="Reference family used to normalize the measured move.",
    )
    reference_id: str | None = Field(
        None,
        description="Optional identifier for the reference leg, gap, or range.",
        examples=["manip-leg-us-open-01"],
    )
    reference_distance_ticks: int = Field(
        ...,
        ge=1,
        description="Observed size of the reference unit, in ticks.",
        examples=[32],
    )
    achieved_multiple: float = Field(
        ...,
        ge=0.0,
        description="Achieved distance expressed as a multiple of the reference unit.",
        examples=[2.0],
    )
    body_confirmed_threshold_multiple: float | None = Field(
        None,
        ge=0.0,
        description="Highest threshold multiple confirmed by body close, if tracked.",
        examples=[2.0],
    )
    next_target_multiple: float | None = Field(
        None,
        ge=0.0,
        description="Next target multiple activated by the current measurement ladder.",
        examples=[4.0],
    )
    invalidated: bool = Field(
        False,
        description="Whether the measured move has been invalidated by later structure.",
        examples=[False],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured facts about thresholds, bodies, or pauses inside the leg.",
        examples=[{"body_confirmed_ticks": 48, "threshold_ladder": [1.0, 2.0, 4.0]}],
    )



class ObservedOrderFlowSignal(BaseModel):
    """Execution-level order-flow signal captured from footprint or DOM."""

    signal_type: OrderFlowSignalType = Field(..., description="Observed order-flow signal category.")
    side: StructureSide = Field(..., description="Side associated with the signal.")
    observed_at: datetime = Field(..., description="Timestamp of the signal.")
    price: float | None = Field(None, description="Associated price if the signal is price-specific.", examples=[21566.75])
    magnitude: float | None = Field(
        None,
        description="Normalized producer-side magnitude for filtering or sorting.",
        examples=[0.84],
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Short producer-side annotations explaining the signal.",
        examples=[["three stacked ask imbalances"]],
    )



class ObservedPostHarvestResponse(BaseModel):
    """Observed response after a liquidity objective has already been harvested."""

    response_id: str = Field(..., description="Stable post-harvest response identifier.")
    harvest_subject_id: str = Field(..., description="Observed subject that completed the harvest.")
    harvest_subject_kind: str = Field(
        ...,
        description="Observed subject kind that completed the harvest.",
        examples=["initiative_drive"],
    )
    harvest_completed_at: datetime = Field(..., description="Timestamp when the harvest was considered complete.")
    harvest_side: StructureSide = Field(..., description="Directional side of the completed harvest move.")
    harvested_price_low: float = Field(..., description="Lower boundary of the harvested price zone.", examples=[21573.5])
    harvested_price_high: float = Field(..., description="Upper boundary of the harvested price zone.", examples=[21576.0])
    completion_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Observed completion ratio for the targeted liquidity pocket.",
        examples=[1.0],
    )
    continuation_ticks_after_completion: int = Field(
        ...,
        ge=0,
        description="Additional same-side travel after completion, in ticks.",
        examples=[6],
    )
    consolidation_range_ticks: int = Field(
        ...,
        ge=0,
        description="Observed consolidation width after completion, in ticks.",
        examples=[8],
    )
    pullback_ticks: int = Field(
        ...,
        ge=0,
        description="Largest pullback observed after completion, in ticks.",
        examples=[10],
    )
    reversal_ticks: int = Field(
        ...,
        ge=0,
        description="Largest opposite-direction reversal observed after completion, in ticks.",
        examples=[18],
    )
    seconds_to_first_pullback: int | None = Field(
        None,
        ge=0,
        description="Seconds between completion and the first pullback.",
        examples=[11],
    )
    seconds_to_reversal: int | None = Field(
        None,
        ge=0,
        description="Seconds between completion and the strongest reversal print.",
        examples=[54],
    )
    reached_next_opposing_liquidity: bool = Field(
        ...,
        description="Whether price reached the next opposing liquidity pocket after completion.",
        examples=[True],
    )
    next_opposing_liquidity_price: float | None = Field(
        None,
        description="Observed price of the next opposing liquidity pocket when reached.",
        examples=[21567.0],
    )
    post_harvest_delta: int | None = Field(
        None,
        description="Net delta observed after completion inside the response window.",
        examples=[-212],
    )
    outcome: PostHarvestOutcome = Field(..., description="Observed response outcome after completion.")
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured facts such as drift speed, counter-drive quality, or reversion targets.",
        examples=[{"ema20_retest": True, "lower_liquidity_reached_ticks": 24}],
    )



class ObservedProcessContext(BaseModel):
    """Optional process-aware context spanning seconds to cross-session sequences."""

    session_windows: list[ObservedSessionWindow] = Field(
        default_factory=list,
        description="Observed session windows for longer-horizon context.",
    )
    second_features: list[ObservedSecondFeature] = Field(
        default_factory=list,
        description="Second-level heatmap and path features.",
    )
    liquidity_episodes: list[ObservedLiquidityEpisode] = Field(
        default_factory=list,
        description="Measured zone-interaction episodes.",
    )
    initiative_drives: list[ObservedInitiativeDrive] = Field(
        default_factory=list,
        description="Measured aggressive-order drives and their execution quality.",
    )
    measured_moves: list[ObservedMeasuredMove] = Field(
        default_factory=list,
        description="Measured distance ladders expressed as multiples of a leg, range, or gap span.",
    )
    manipulation_legs: list[ObservedManipulationLeg] = Field(
        default_factory=list,
        description="Observed forcing legs used for trap, extension, or distribution context.",
    )
    gap_references: list[ObservedGapReference] = Field(
        default_factory=list,
        description="Observed session gaps plus their fill and acceptance history.",
    )
    post_harvest_responses: list[ObservedPostHarvestResponse] = Field(
        default_factory=list,
        description="Observed reactions after a liquidity objective has already been harvested.",
    )
    exertion_zones: list[ObservedExertionZone] = Field(
        default_factory=list,
        description="Historically important drive-origin zones and revisit evidence.",
    )
    cross_session_sequences: list[ObservedCrossSessionSequence] = Field(
        default_factory=list,
        description="Observed sequences connecting episodes across sessions.",
    )



class ObservedRange(BaseModel):
    """Directly observed price range facts."""

    open: float = Field(..., description="Observed open price.", examples=[21542.25])
    high: float = Field(..., description="Observed high price.", examples=[21578.75])
    low: float = Field(..., description="Observed low price.", examples=[21518.50])
    close: float = Field(..., description="Observed close price.", examples=[21570.25])



class ObservedSecondFeature(BaseModel):
    """One-second microstructure aggregate for heatmap and path reconstruction."""

    second_started_at: datetime = Field(..., description="Inclusive second window start.")
    second_ended_at: datetime = Field(..., description="Inclusive second window end.")
    latest_range: ObservedRange = Field(..., description="Observed price path within the second.")
    trade_count: int = Field(..., ge=0, description="Observed trades in the second.", examples=[42])
    volume: int = Field(..., ge=0, description="Observed traded volume in the second.", examples=[315])
    delta: int = Field(..., description="Observed delta in the second.", examples=[-84])
    best_bid: float | None = Field(None, description="Best bid observed near the end of the second.", examples=[21564.5])
    best_ask: float | None = Field(None, description="Best ask observed near the end of the second.", examples=[21564.75])
    max_bid_depth: float | None = Field(
        None,
        ge=0,
        description="Maximum observed bid depth inside the second.",
        examples=[740.0],
    )
    max_ask_depth: float | None = Field(
        None,
        ge=0,
        description="Maximum observed ask depth inside the second.",
        examples=[910.0],
    )
    depth_imbalance: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Normalized depth imbalance for the second.",
        examples=[-0.28],
    )
    raw_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measured microstructure features for replay.",
        examples=[{"absorption_score": 0.81, "sweep_distance_ticks": 6}],
    )



class ObservedSessionStats(BaseModel):
    """Observed session metrics from ATAS or a local adapter."""

    volume: int = Field(..., ge=0, description="Observed traded volume.", examples=[182340])
    delta: int = Field(..., description="Observed cumulative delta.", examples=[12450])
    trades: int = Field(..., ge=0, description="Observed number of trades.", examples=[28490])



class ObservedSessionWindow(BaseModel):
    """Observed session-level process context for cross-session analysis."""

    session_code: SessionCode = Field(..., description="Named trading session.")
    started_at: datetime = Field(..., description="Session start timestamp.")
    ended_at: datetime = Field(..., description="Session end timestamp.")
    latest_range: ObservedRange = Field(..., description="Observed session price range.")
    value_area: ObservedValueArea | None = Field(
        None,
        description="Observed session value area when available.",
    )
    session_stats: ObservedSessionStats | None = Field(
        None,
        description="Observed session statistics when available.",
    )
    key_levels: list[ObservedLiquidityLevel] = Field(
        default_factory=list,
        description="Observed session liquidity references.",
    )



class ObservedSwingPoint(BaseModel):
    """A price swing directly measured from bars or swing logic on the producer side."""

    kind: SwingKind = Field(..., description="Whether the swing is a high or a low.")
    price: float = Field(..., description="Observed swing price.", examples=[21578.75])
    formed_at: datetime = Field(..., description="Timestamp when the swing became valid.")
    leg_index: int = Field(..., ge=0, description="Zero-based position in the local swing sequence.", examples=[2])
    tags: list[str] = Field(
        default_factory=list,
        description="Observed producer-side labels, not analyst interpretation.",
        examples=[["session_high", "untested"]],
    )



class ObservedValueArea(BaseModel):
    """Observed value area statistics."""

    low: float = Field(..., description="Observed value area low.", examples=[21534.50])
    high: float = Field(..., description="Observed value area high.", examples=[21568.75])
    point_of_control: float = Field(..., description="Observed point of control.", examples=[21552.25])



class OrderFlowSignalType(str, Enum):
    STACKED_IMBALANCE = "stacked_imbalance"
    ABSORPTION = "absorption"
    UNFINISHED_AUCTION = "unfinished_auction"
    DELTA_DIVERGENCE = "delta_divergence"
    INITIATIVE_BUYING = "initiative_buying"
    INITIATIVE_SELLING = "initiative_selling"



class PostHarvestOutcome(str, Enum):
    CONTINUATION = "continuation"
    CONSOLIDATION = "consolidation"
    PULLBACK = "pullback"
    REVERSAL = "reversal"
    MIXED = "mixed"



class SessionCode(str, Enum):
    ASIA = "asia"
    EUROPE = "europe"
    US_PREMARKET = "us_premarket"
    US_REGULAR = "us_regular"
    US_AFTER_HOURS = "us_after_hours"



class SourceRef(BaseModel):
    """Producer metadata for tracing and support."""

    system: str = Field(..., description="Source system name.", examples=["ATAS"])
    instance_id: str = Field(..., description="Producer instance identifier.", examples=["DESKTOP-ATAS-01"])
    chart_instance_id: str | None = Field(
        None,
        description="Chart or indicator-instance identifier used to separate multiple live ATAS charts.",
        examples=["NQM6-7fa31b2c"],
    )
    adapter_version: str = Field(..., description="Source adapter version.", examples=["0.1.0"])



class StructureSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"



class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"



class Timeframe(str, Enum):
    MONTH_1 = "1mo"
    WEEK_1 = "1w"
    DAY_1 = "1d"
    DAY_3 = "3d"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    MIN_30 = "30m"
    MIN_15 = "15m"
    MIN_5 = "5m"
    MIN_1 = "1m"
    FOOTPRINT = "footprint"
    DOM = "dom"


MACRO_TIMEFRAMES = {Timeframe.MONTH_1, Timeframe.WEEK_1, Timeframe.DAY_1}
INTRADAY_TIMEFRAMES = {Timeframe.DAY_3, Timeframe.HOUR_1, Timeframe.MIN_30}
SETUP_TIMEFRAMES = {Timeframe.MIN_15, Timeframe.MIN_5}
EXECUTION_TIMEFRAMES = {Timeframe.MIN_1, Timeframe.FOOTPRINT, Timeframe.DOM}

