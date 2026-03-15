from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Timeframe(str, Enum):
    MONTH_1 = "1mo"
    WEEK_1 = "1w"
    DAY_1 = "1d"
    DAY_3 = "3d"
    HOUR_1 = "1h"
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


class StructureSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"


class LiquidityLevelType(str, Enum):
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"
    PRIOR_DAY_HIGH = "prior_day_high"
    PRIOR_DAY_LOW = "prior_day_low"
    WEEKLY_EXTREME = "weekly_extreme"
    COMPOSITE_POC = "composite_poc"
    MANUAL = "manual"


class OrderFlowSignalType(str, Enum):
    STACKED_IMBALANCE = "stacked_imbalance"
    ABSORPTION = "absorption"
    UNFINISHED_AUCTION = "unfinished_auction"
    DELTA_DIVERGENCE = "delta_divergence"
    INITIATIVE_BUYING = "initiative_buying"
    INITIATIVE_SELLING = "initiative_selling"


class EventType(str, Enum):
    BREAK_OF_STRUCTURE = "break_of_structure"
    CHANGE_OF_CHARACTER = "change_of_character"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    VALUE_AREA_REJECTION = "value_area_rejection"
    ORDERFLOW_IMBALANCE = "orderflow_imbalance"
    OTHER = "other"


class DerivedBias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class DepthCoverageState(str, Enum):
    UNAVAILABLE = "depth_unavailable"
    BOOTSTRAP = "depth_bootstrap"
    LIVE = "depth_live"
    INTERRUPTED = "depth_interrupted"


class ObservationOriginMode(str, Enum):
    BOOTSTRAP = "bootstrap"
    LIVE = "live"


class LargeLiquidityStatus(str, Enum):
    ACTIVE = "active"
    PULLED = "pulled"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    MOVED = "moved"
    EXPIRED = "expired"


class LiquidityMemoryClassification(str, Enum):
    MONITORING = "monitoring"
    SPOOF_CANDIDATE = "spoof_candidate"
    ABSORPTION_CANDIDATE = "absorption_candidate"
    MAGNET_CANDIDATE = "magnet_candidate"
    DEFENDED_LEVEL_CANDIDATE = "defended_level_candidate"


class SessionCode(str, Enum):
    ASIA = "asia"
    EUROPE = "europe"
    US_PREMARKET = "us_premarket"
    US_REGULAR = "us_regular"
    US_AFTER_HOURS = "us_after_hours"


class InstrumentRef(BaseModel):
    """Stable instrument metadata for replay and backtests."""

    symbol: str = Field(..., description="Trading symbol.", examples=["NQH6"])
    venue: str = Field(..., description="Execution or quote venue.", examples=["CME"])
    tick_size: float = Field(..., gt=0, description="Minimum price increment.", examples=[0.25])
    currency: str = Field(..., description="PnL currency.", examples=["USD"])


class SourceRef(BaseModel):
    """Producer metadata for tracing and support."""

    system: str = Field(..., description="Source system name.", examples=["ATAS"])
    instance_id: str = Field(..., description="Producer instance identifier.", examples=["DESKTOP-ATAS-01"])
    adapter_version: str = Field(..., description="Source adapter version.", examples=["0.1.0"])


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


class KnowledgeRoute(BaseModel):
    """Routing hint for future playbook or retrieval augmentation selection."""

    route_key: str = Field(..., description="Stable route identifier.", examples=["trend_continuation_review"])
    summary: str = Field(..., description="Short explanation for the route choice.")
    required_context: list[str] = Field(
        default_factory=list,
        description="Context categories the next stage should load.",
        examples=[["macro_context", "intraday_bias", "execution_context"]],
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
    knowledge_route: KnowledgeRoute = Field(..., description="Knowledge-base routing result.")
    analyst_flags: list[str] = Field(
        default_factory=list,
        description="Phase-1 machine-generated flags for operator review.",
    )


class IngestionAcceptedResponse(BaseModel):
    """REST response after a payload is validated, stored, and analyzed."""

    ingestion_id: str = Field(..., description="Stored ingestion record identifier.")
    analysis_id: str = Field(..., description="Stored analysis record identifier.")
    route_key: str = Field(..., description="Selected knowledge route.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    analysis: DerivedStructureAnalysis = Field(..., description="Derived interpretation.")


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


class DepthSnapshotAcceptedResponse(BaseModel):
    """REST response after a depth snapshot is ingested and memory is updated."""

    ingestion_id: str = Field(..., description="Stored ingestion identifier.")
    coverage_state: DepthCoverageState = Field(..., description="Coverage state reported by the snapshot.")
    stored_at: datetime = Field(..., description="Persistence timestamp.")
    updated_memories: list[LiquidityMemoryRecord] = Field(
        default_factory=list,
        description="Memory records created or updated by the snapshot.",
    )


class LiquidityMemoryEnvelope(BaseModel):
    """REST response for listing active significant liquidity memories."""

    memories: list[LiquidityMemoryRecord] = Field(default_factory=list)


class AnalysisEnvelope(BaseModel):
    """REST response for analysis retrieval."""

    analysis: DerivedStructureAnalysis


class IngestionEnvelope(BaseModel):
    """REST response for observed payload retrieval."""

    ingestion_id: str
    ingestion_kind: str
    source_snapshot_id: str
    observed_payload: dict[str, Any]
    stored_at: datetime
