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
    HOUR_4 = "4h"
    MIN_30 = "30m"
    MIN_15 = "15m"
    MIN_5 = "5m"
    MIN_1 = "1m"
    FOOTPRINT = "footprint"
    DOM = "dom"

    @classmethod
    def _missing_(cls, value: object) -> "Timeframe" | None:
        if value is None:
            return None
        candidate = str(value).strip().lower()
        aliases = {
            "1": cls.MIN_1,
            "m1": cls.MIN_1,
            "5": cls.MIN_5,
            "m5": cls.MIN_5,
            "15": cls.MIN_15,
            "m15": cls.MIN_15,
            "30": cls.MIN_30,
            "m30": cls.MIN_30,
            "60": cls.HOUR_1,
            "h1": cls.HOUR_1,
            "240": cls.HOUR_4,
            "h4": cls.HOUR_4,
        }
        return aliases.get(candidate)


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


class RollMode(str, Enum):
    """Continuous contract roll mode specification."""

    NONE = "none"
    BY_CONTRACT_START = "by_contract_start"
    BY_VOLUME_PROXY = "by_volume_proxy"
    MANUAL_SEQUENCE = "manual_sequence"
    FRONT_MONTH = "front_month"
    PASSIVE_ROLL = "passive_roll"
    NEAR_ROLL = "near_roll"
    ALL_CONTRACTS = "all_contracts"


class ContinuousAdjustmentMode(str, Enum):
    """Explicit adjustment mode for derived continuous bars."""

    NONE = "none"
    GAP_SHIFT = "gap_shift"


class RegimeKind(str, Enum):
    """Fixed V1 regime ontology from Master Spec v2."""

    STRONG_MOMENTUM_TREND = "strong_momentum_trend"
    WEAK_MOMENTUM_TREND_NARROW = "weak_momentum_trend_narrow"
    WEAK_MOMENTUM_TREND_WIDE = "weak_momentum_trend_wide"
    BALANCE_MEAN_REVERSION = "balance_mean_reversion"
    COMPRESSION = "compression"
    TRANSITION_EXHAUSTION = "transition_exhaustion"


class EventHypothesisKind(str, Enum):
    """Fixed V1 event-hypothesis ontology from Master Spec v2."""

    CONTINUATION_BASE = "continuation_base"
    ABSORPTION_ACCUMULATION = "absorption_accumulation"
    PROFIT_TAKING_PAUSE = "profit_taking_pause"
    REVERSAL_PREPARATION = "reversal_preparation"
    BREAKOUT_ACCEPTANCE = "breakout_acceptance"
    BREAKOUT_REJECTION = "breakout_rejection"
    FAILED_REVERSAL = "failed_reversal"
    DISTRIBUTION_BALANCE = "distribution_balance"


class TradableEventKind(str, Enum):
    """V1 tradable event ontology required by Master Spec v2."""

    MOMENTUM_CONTINUATION = "momentum_continuation"
    BALANCE_MEAN_REVERSION = "balance_mean_reversion"
    ABSORPTION_TO_REVERSAL_PREPARATION = "absorption_to_reversal_preparation"


class EventPhase(str, Enum):
    """Lifecycle phase for one event hypothesis or episode."""

    EMERGING = "emerging"
    BUILDING = "building"
    CONFIRMING = "confirming"
    WEAKENING = "weakening"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


class EpisodeResolution(str, Enum):
    """Terminal resolution for one closed event episode."""

    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"
    TIMED_OUT = "timed_out"
    REPLACED = "replaced"
    EXPIRED = "expired"


class EvaluationFailureMode(str, Enum):
    """Standardized evaluation failure modes for episode review."""

    NONE = "none"
    EARLY_CONFIRMATION = "early_confirmation"
    LATE_CONFIRMATION = "late_confirmation"
    LATE_INVALIDATION = "late_invalidation"
    MISSED_TRANSITION = "missed_transition"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"


class ReviewSource(str, Enum):
    """Source that produced an episode evaluation."""

    RULE_REVIEW_V1 = "rule_review_v1"
    HUMAN_REVIEW_V1 = "human_review_v1"
    HYBRID_REVIEW_V1 = "hybrid_review_v1"


class RecognitionMode(str, Enum):
    """Recognition operating mode attached to belief-state outputs.

    The canonical V1 surface follows Master Spec v2 naming. Legacy
    values are still accepted through `_missing_` so older samples and
    tests can be read during the closeout transition.
    """

    NORMAL = "normal"
    DEGRADED_NO_DEPTH = "degraded_no_depth"
    DEGRADED_NO_DOM = "degraded_no_dom"
    REPLAY_REBUILD_MODE = "replay_rebuild_mode"
    BAR_ANCHOR_ONLY = "degraded_no_depth"

    @classmethod
    def _missing_(cls, value: object) -> "RecognitionMode" | None:
        legacy_map = {
            "bar_anchor_only": cls.DEGRADED_NO_DEPTH,
            "degraded_sparse_microstructure": cls.DEGRADED_NO_DEPTH,
            "degraded_stale_context": cls.DEGRADED_NO_DOM,
        }
        if isinstance(value, str):
            return legacy_map.get(value)
        return None


class DegradedMode(str, Enum):
    """Explicit degraded conditions that should not stop the engine.

    Canonical values are prefixed to match Master Spec v2 and health/UI
    badges. Legacy unprefixed inputs are still accepted for backward
    compatibility with older persisted payloads and samples.
    """

    NONE = "none"
    NO_DEPTH = "degraded_no_depth"
    NO_DOM = "degraded_no_dom"
    NO_AI = "degraded_no_ai"
    STALE_MACRO = "degraded_stale_macro"
    REPLAY_REBUILD = "replay_rebuild_mode"

    @classmethod
    def _missing_(cls, value: object) -> "DegradedMode" | None:
        legacy_map = {
            "no_depth": cls.NO_DEPTH,
            "no_dom": cls.NO_DOM,
            "no_ai": cls.NO_AI,
            "stale_macro": cls.STALE_MACRO,
            "replay_rebuild": cls.REPLAY_REBUILD,
        }
        if isinstance(value, str):
            return legacy_map.get(value)
        return None


class ServiceHealthStatus(str, Enum):
    """High-level health state for ingestion and recognition services."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    REBUILD_REQUIRED = "rebuild_required"
    PAUSED = "paused"


class ParameterCriticality(str, Enum):
    """Risk level for one tunable profile parameter."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PatchValidationStatus(str, Enum):
    """Validation result for one profile patch candidate."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"

