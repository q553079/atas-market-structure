from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

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


class KeyLevelRole(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"
    PIVOT = "pivot"


class KeyLevelState(str, Enum):
    MONITORING = "monitoring"
    DEFENDED = "defended"
    BROKEN = "broken"
    FLIPPED = "flipped"


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


class ReplayAcquisitionMode(str, Enum):
    CACHE_REUSE = "cache_reuse"
    ATAS_FETCH = "atas_fetch"


class ReplayVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DURABLE = "durable"
    INVALIDATED = "invalidated"


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


class MeasurementReferenceKind(str, Enum):
    MANIPULATION_LEG = "manipulation_leg"
    RANGE_AMPLITUDE = "range_amplitude"
    INITIATIVE_DRIVE = "initiative_drive"
    OPENING_RANGE = "opening_range"
    GAP_SPAN = "gap_span"


class GapDirection(str, Enum):
    UP = "up"
    DOWN = "down"


class GapFillState(str, Enum):
    UNTOUCHED = "untouched"
    PARTIAL_FILL = "partial_fill"
    FULLY_FILLED = "fully_filled"


class GapFillLikelihood(str, Enum):
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    PROBABLE = "probable"
    COMPLETED = "completed"


class PostHarvestOutcome(str, Enum):
    CONTINUATION = "continuation"
    CONSOLIDATION = "consolidation"
    PULLBACK = "pullback"
    REVERSAL = "reversal"
    MIXED = "mixed"


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

