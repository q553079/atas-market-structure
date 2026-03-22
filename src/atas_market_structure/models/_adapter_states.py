from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atas_market_structure.models._refs import InstrumentRef, SourceRef

class AdapterTimeContext(BaseModel):
    """Time-zone metadata describing how ATAS timestamps were interpreted."""

    instrument_timezone_value: str | None = Field(None, description="Raw instrument timezone value from ATAS metadata.")
    instrument_timezone_source: str = Field("unavailable", description="Where the instrument timezone came from.")
    chart_display_timezone_mode: str | None = Field(None, description="ATAS chart display timezone mode when known.")
    chart_display_timezone_source: str | None = Field(None, description="Where the chart display timezone mode came from.")
    chart_display_timezone_name: str | None = Field(None, description="Resolved chart display timezone name or abbreviation.")
    chart_display_utc_offset_minutes: int | None = Field(None, description="Resolved chart display UTC offset in minutes.")
    timezone_capture_confidence: str | None = Field(None, description="Confidence level of the timezone capture: high, medium, low, or unknown.")
    collector_local_timezone_name: str | None = Field(None, description="Collector machine local timezone name.")
    collector_local_utc_offset_minutes: int | None = Field(None, description="Collector machine local UTC offset in minutes.")
    timestamp_basis: str | None = Field(None, description="Primary basis used to normalize timestamps to UTC.")
    started_at_output_timezone: str = Field("UTC", description="Timezone used for started_at-style output fields.")
    started_at_time_source: str | None = Field(None, description="Source used to resolve started_at timestamps.")

class AdapterEnvelopeBase(BaseModel):
    """Common adapter message envelope shared by continuous and burst payloads."""

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    message_id: str = Field(..., description="Unique adapter message identifier.", examples=["adapter-msg-20260316-143001"])
    emitted_at: datetime = Field(..., description="When the adapter emitted this message.")
    observed_window_start: datetime = Field(..., description="Inclusive start of the observed window.")
    observed_window_end: datetime = Field(..., description="Inclusive end of the observed window.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    display_timeframe: str | None = Field(None, description="Display/native chart timeframe when known.")
    time_context: AdapterTimeContext | None = Field(None, description="Timezone-resolution metadata for this payload.")

    @model_validator(mode="after")
    def validate_observed_window(self) -> "AdapterEnvelopeBase":
        if self.observed_window_end < self.observed_window_start:
            raise ValueError("observed_window_end must be greater than or equal to observed_window_start")
        return self


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


class AdapterDepthCoverage(BaseModel):
    """Compact depth-feed coverage state for validating live DOM collection."""

    coverage_state: DepthCoverageState = Field(..., description="Current depth-feed coverage state.")
    snapshot_level_count: int = Field(..., ge=0, description="How many levels were present in the last depth snapshot.")
    tracked_liquidity_count: int = Field(..., ge=0, description="How many active significant-liquidity tracks are currently alive.")
    last_snapshot_at: datetime | None = Field(None, description="Timestamp of the most recent successful depth snapshot.")
    best_bid_available: bool = Field(..., description="Whether a best bid is currently available.")
    best_ask_available: bool = Field(..., description="Whether a best ask is currently available.")


class AdapterTradeSummary(BaseModel):
    """Always-on aggressive-trade summary for the current window."""

    trade_count: int = Field(..., ge=0, description="Observed trade count inside the window.", examples=[162])
    volume: int = Field(..., ge=0, description="Observed traded volume inside the window.", examples=[914])
    aggressive_buy_volume: int = Field(..., ge=0, description="Aggressive buy-side volume.", examples=[642])
    aggressive_sell_volume: int = Field(..., ge=0, description="Aggressive sell-side volume.", examples=[272])
    net_delta: int = Field(..., description="Observed net delta for the window.", examples=[370])


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


class AdapterReferenceLevel(BaseModel):
    """Additional compact location references attached to an adapter state message."""

    kind: str = Field(..., description="Reference family label.", examples=["upper_liquidity_band"])
    price: float = Field(..., description="Observed reference price.", examples=[21576.0])
    notes: list[str] = Field(
        default_factory=list,
        description="Short source-side notes for operator review.",
        examples=[["visible ask wall still above price during ascent"]],
    )


