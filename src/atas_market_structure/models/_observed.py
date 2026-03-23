from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atas_market_structure.models._enums import (
    EXECUTION_TIMEFRAMES,
    GapDirection,
    INTRADAY_TIMEFRAMES,
    LiquidityLevelType,
    MACRO_TIMEFRAMES,
    MeasurementReferenceKind,
    OrderFlowSignalType,
    PostHarvestOutcome,
    SessionCode,
    SETUP_TIMEFRAMES,
    StructureSide,
    SwingKind,
    Timeframe,
)

class ObservedRange(BaseModel):
    """Directly observed price range facts."""

    open: float = Field(..., description="Observed open price.", examples=[21542.25])
    high: float = Field(..., description="Observed high price.", examples=[21578.75])
    low: float = Field(..., description="Observed low price.", examples=[21518.50])
    close: float = Field(..., description="Observed close price.", examples=[21570.25])


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


class ObservedLiquidityLevel(BaseModel):
    """A price level derived by the producer and stored as an observed fact."""

    level_type: LiquidityLevelType = Field(..., description="Observed liquidity reference type.")
    price: float = Field(..., description="Observed level price.", examples=[21580.00])
    first_seen_at: datetime = Field(..., description="When this level first entered the current dataset.")
    touch_count: int = Field(..., ge=0, description="Number of observed touches.", examples=[1])
    swept: bool = Field(..., description="Whether price traded through the level.", examples=[False])


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


class ObservedValueArea(BaseModel):
    """Observed value area statistics."""

    low: float = Field(..., description="Observed value area low.", examples=[21534.50])
    high: float = Field(..., description="Observed value area high.", examples=[21568.75])
    point_of_control: float = Field(..., description="Observed point of control.", examples=[21552.25])


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


class ProcessContextPayload(BaseModel):
    """Observed process-context payload stored independently from full structure snapshots."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schema_version": "1.0.0",
                "process_context_id": "proc-20260315-093100",
                "observed_at": "2026-03-15T09:31:00Z",
                "source": {
                    "system": "ATAS",
                    "instance_id": "DESKTOP-ATAS-01",
                    "adapter_version": "0.3.0",
                },
                "instrument": {
                    "symbol": "NQH6",
                    "venue": "CME",
                    "tick_size": 0.25,
                    "currency": "USD",
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
            },
        },
    )

    schema_version: str = Field(..., description="Payload schema version.", examples=["1.0.0"])
    process_context_id: str = Field(..., description="Producer-generated process-context identifier.")
    observed_at: datetime = Field(..., description="Timestamp of the process-context snapshot.")
    source: SourceRef = Field(..., description="Source metadata.")
    instrument: InstrumentRef = Field(..., description="Instrument metadata.")
    process_context: ObservedProcessContext = Field(
        ...,
        description="Observed multi-horizon process context kept separate from derived interpretation.",
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

