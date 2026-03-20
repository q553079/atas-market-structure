from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from atas_market_structure.models._adapter_states import (
    AdapterDepthCoverage,
    AdapterEmaContext,
    AdapterEnvelopeBase,
    AdapterGapReferenceState,
    AdapterInitiativeDriveState,
    AdapterManipulationLegState,
    AdapterMeasuredMoveState,
    AdapterPostHarvestResponseState,
    AdapterPriceState,
    AdapterReferenceLevel,
    AdapterSamePriceReplenishmentState,
    AdapterSessionContext,
    AdapterSignificantLiquidityLevel,
    AdapterTradeSummary,
    AdapterZoneInteraction,
)
from atas_market_structure.models._enums import (
    AdapterTriggerType,
    LargeLiquidityStatus,
    StructureSide,
    Timeframe,
)

class AdapterContinuousStatePayload(AdapterEnvelopeBase):
    """Low-overhead adapter state message emitted on a continuous cadence."""

    message_type: Literal["continuous_state"] = Field(
        ...,
        description="Adapter message family for always-on compact state.",
    )
    session_context: AdapterSessionContext = Field(..., description="Current session and prior-auction references.")
    price_state: AdapterPriceState = Field(..., description="Compact price-state snapshot.")
    trade_summary: AdapterTradeSummary = Field(..., description="Compact trade and delta summary.")
    depth_coverage: AdapterDepthCoverage | None = Field(
        None,
        description="Compact DOM coverage and availability state for this continuous window.",
    )
    significant_liquidity: list[AdapterSignificantLiquidityLevel] = Field(
        default_factory=list,
        description="Only significant liquidity tracks, not the full order book.",
    )
    same_price_replenishment: list[AdapterSamePriceReplenishmentState] = Field(
        default_factory=list,
        description="Compact repeated-replenishment observations extracted from active liquidity tracks.",
    )
    gap_reference: AdapterGapReferenceState | None = Field(
        None,
        description="Current or recently relevant gap reference when applicable.",
    )
    active_initiative_drive: AdapterInitiativeDriveState | None = Field(
        None,
        description="Currently active or freshly completed initiative drive.",
    )
    active_manipulation_leg: AdapterManipulationLegState | None = Field(
        None,
        description="Currently active or freshly completed manipulation leg.",
    )
    active_measured_move: AdapterMeasuredMoveState | None = Field(
        None,
        description="Currently active measured move ladder when applicable.",
    )
    active_post_harvest_response: AdapterPostHarvestResponseState | None = Field(
        None,
        description="Current post-harvest reaction state when a liquidity objective has just completed.",
    )
    active_zone_interaction: AdapterZoneInteraction | None = Field(
        None,
        description="Compact active zone interaction state.",
    )
    ema_context: AdapterEmaContext | None = Field(
        None,
        description="Optional EMA context preserved as observed facts.",
    )
    reference_levels: list[AdapterReferenceLevel] = Field(
        default_factory=list,
        description="Additional source-side price references for replay and review.",
    )


class AdapterTriggerInfo(BaseModel):
    """Trigger metadata for a high-fidelity adapter burst."""

    trigger_id: str = Field(..., description="Unique trigger identifier.")
    trigger_type: AdapterTriggerType = Field(..., description="Trigger family.")
    triggered_at: datetime = Field(..., description="When the trigger fired.")
    price: float | None = Field(None, description="Associated trigger price when applicable.", examples=[21574.0])
    reason_codes: list[str] = Field(
        default_factory=list,
        description="Compact reason labels explaining why the burst was emitted.",
        examples=[["upper_liquidity_near_touch", "renewed_aggressive_buying"]],
    )


class AdapterTradeEvent(BaseModel):
    """Raw aggressive-trade event preserved inside a burst window."""

    event_time: datetime = Field(..., description="Trade timestamp.")
    local_sequence: int = Field(..., ge=0, description="Monotonic local sequence for ordering.")
    price: float = Field(..., description="Executed trade price.", examples=[21573.5])
    size: int = Field(..., ge=0, description="Executed size.", examples=[31])
    aggressor_side: StructureSide = Field(..., description="Aggressor side for the trade.")
    best_bid_before: float | None = Field(None, description="Best bid immediately before the trade.")
    best_ask_before: float | None = Field(None, description="Best ask immediately before the trade.")
    best_bid_after: float | None = Field(None, description="Best bid immediately after the trade.")
    best_ask_after: float | None = Field(None, description="Best ask immediately after the trade.")


class AdapterDepthEvent(BaseModel):
    """Compact depth lifecycle event preserved inside a burst window."""

    event_time: datetime = Field(..., description="Depth-event timestamp.")
    track_id: str = Field(..., description="Referenced significant-liquidity track identifier.")
    side: StructureSide = Field(..., description="Book side of the tracked liquidity.")
    price: float = Field(..., description="Tracked price for the liquidity event.", examples=[21576.0])
    size_before: int = Field(..., ge=0, description="Displayed size before the event.", examples=[286])
    size_after: int = Field(..., ge=0, description="Displayed size after the event.", examples=[244])
    status_before: LargeLiquidityStatus = Field(..., description="Track status before the event.")
    status_after: LargeLiquidityStatus = Field(..., description="Track status after the event.")
    distance_from_price_ticks: int = Field(
        ...,
        ge=0,
        description="Distance from current price in ticks at event time.",
        examples=[10],
    )


class AdapterSecondFeature(BaseModel):
    """Compact one-second summary emitted inside a burst window."""

    second_started_at: datetime = Field(..., description="Inclusive second start timestamp.")
    second_ended_at: datetime = Field(..., description="Inclusive second end timestamp.")
    open: float = Field(..., description="Observed open price in the second.")
    high: float = Field(..., description="Observed high price in the second.")
    low: float = Field(..., description="Observed low price in the second.")
    close: float = Field(..., description="Observed close price in the second.")
    trade_count: int = Field(..., ge=0, description="Trade count inside the second.")
    volume: int = Field(..., ge=0, description="Traded volume inside the second.")
    delta: int = Field(..., description="Net delta inside the second.")
    best_bid: float | None = Field(None, description="Best bid at the end of the second.")
    best_ask: float | None = Field(None, description="Best ask at the end of the second.")
    depth_imbalance: float | None = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Normalized depth imbalance for the second.",
        examples=[0.24],
    )


class AdapterBookmark(BaseModel):
    """Replay bookmark attached to a burst window."""

    kind: str = Field(..., description="Bookmark type.", examples=["ema20_reclaim"])
    event_time: datetime = Field(..., description="When the bookmarked moment occurred.")
    price: float | None = Field(None, description="Associated bookmark price when available.")
    notes: list[str] = Field(default_factory=list, description="Short bookmark notes.")


class AdapterBurstWindow(BaseModel):
    """One burst sub-window around a trigger event."""

    trade_events: list[AdapterTradeEvent] = Field(default_factory=list, description="Raw trade events for the sub-window.")
    depth_events: list[AdapterDepthEvent] = Field(default_factory=list, description="Raw depth events for the sub-window.")
    second_features: list[AdapterSecondFeature] = Field(
        default_factory=list,
        description="Compact second-level features for the sub-window.",
    )
    price_levels: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional compact price-level summaries when footprint data is attached.",
    )
    bookmarks: list[AdapterBookmark] = Field(default_factory=list, description="Replay bookmarks for the sub-window.")


class AdapterTriggerBurstPayload(AdapterEnvelopeBase):
    """High-fidelity adapter burst emitted only around meaningful triggers."""

    message_type: Literal["trigger_burst"] = Field(
        ...,
        description="Adapter message family for event-driven raw bursts.",
    )
    trigger: AdapterTriggerInfo = Field(..., description="Trigger metadata for this burst.")
    pre_window: AdapterBurstWindow = Field(..., description="Short raw window before the trigger.")
    event_window: AdapterBurstWindow = Field(..., description="Raw window around the trigger itself.")
    post_window: AdapterBurstWindow = Field(..., description="Short raw window after the trigger.")


class AdapterHistoryBar(BaseModel):
    """One chart-loaded historical bar exported directly from ATAS."""

    started_at: datetime = Field(..., description="Inclusive bar start timestamp.")
    ended_at: datetime = Field(..., description="Inclusive bar end timestamp.")
    open: float = Field(..., description="Bar open.", examples=[21540.25])
    high: float = Field(..., description="Bar high.", examples=[21548.0])
    low: float = Field(..., description="Bar low.", examples=[21535.5])
    close: float = Field(..., description="Bar close.", examples=[21544.75])
    volume: int | None = Field(None, ge=0, description="Optional total volume.", examples=[842])
    delta: int | None = Field(None, description="Optional net delta.", examples=[121])
    bid_volume: int | None = Field(None, ge=0, description="Optional bid-side traded volume.", examples=[360])
    ask_volume: int | None = Field(None, ge=0, description="Optional ask-side traded volume.", examples=[481])


class AdapterHistoryBarsPayload(AdapterEnvelopeBase):
    """Chart-loaded history exported from the active ATAS chart."""

    message_type: Literal["history_bars"] = Field(
        ...,
        description="Adapter message family for chart-loaded historical bars.",
    )
    bar_timeframe: Timeframe = Field(..., description="Native timeframe of the exported chart bars.")
    bars: list[AdapterHistoryBar] = Field(
        default_factory=list,
        description="Historical bars currently loaded inside the active ATAS chart.",
    )

    @model_validator(mode="after")
    def validate_bars(self) -> "AdapterHistoryBarsPayload":
        previous_start: datetime | None = None
        for bar in self.bars:
            if bar.ended_at < bar.started_at:
                raise ValueError("history bar ended_at must be greater than or equal to started_at")
            if previous_start is not None and bar.started_at < previous_start:
                raise ValueError("history bars must be ordered by started_at")
            previous_start = bar.started_at
        return self


class AdapterHistoryFootprintLevel(BaseModel):
    """One historical footprint price level exported from an ATAS candle."""

    price: float = Field(..., description="Price level.", examples=[21544.75])
    bid_volume: int | None = Field(None, ge=0, description="Bid-side traded volume at this price.", examples=[24])
    ask_volume: int | None = Field(None, ge=0, description="Ask-side traded volume at this price.", examples=[37])
    total_volume: int | None = Field(None, ge=0, description="Total traded volume at this price.", examples=[61])
    delta: int | None = Field(None, description="Net delta at this price.", examples=[13])
    trade_count: int | None = Field(None, ge=0, description="Optional trade count or ticks at this price.", examples=[9])


class AdapterHistoryFootprintBar(AdapterHistoryBar):
    """One historical bar enriched with price-level footprint structure."""

    price_levels: list[AdapterHistoryFootprintLevel] = Field(
        default_factory=list,
        description="Price-level footprint rows captured for this bar.",
    )


class AdapterHistoryFootprintPayload(AdapterEnvelopeBase):
    """Chunked chart-loaded historical footprint exported from the active ATAS chart."""

    message_type: Literal["history_footprint"] = Field(
        ...,
        description="Adapter message family for chart-loaded historical footprint chunks.",
    )
    batch_id: str = Field(
        ...,
        description="Stable batch identifier grouping all chunks for one historical footprint export.",
        examples=["footprint-batch-nq-20260317T091500Z"],
    )
    bar_timeframe: Timeframe = Field(..., description="Native timeframe of the exported chart bars.")
    chunk_index: int = Field(..., ge=0, description="Zero-based chunk index.")
    chunk_count: int = Field(..., ge=1, description="Total chunk count in this batch.")
    bars: list[AdapterHistoryFootprintBar] = Field(
        default_factory=list,
        description="Historical footprint bars for this chunk.",
    )

    @model_validator(mode="after")
    def validate_history_footprint(self) -> "AdapterHistoryFootprintPayload":
        if self.chunk_index >= self.chunk_count:
            raise ValueError("chunk_index must be less than chunk_count")
        previous_start: datetime | None = None
        for bar in self.bars:
            if bar.ended_at < bar.started_at:
                raise ValueError("history footprint bar ended_at must be greater than or equal to started_at")
            if previous_start is not None and bar.started_at < previous_start:
                raise ValueError("history footprint bars must be ordered by started_at")
            previous_start = bar.started_at
        return self

