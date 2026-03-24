"""
V1 Event Templates for the three required tradable events.

Design principles:
- Events are LIFECYCLE TRAJECTORIES, not static labels.
- Each template defines: setup_features, validation_rules, invalidation_rules,
  time_window, replacement_candidates, required_evidence, missing_confirmation, confidence_shaping.
- DOM/盘口 evidence is MECHANISM evidence layer, NOT the final judgment layer.
- Belief state is PROJECTION layer, NOT the raw observation layer.

Three V1 events:
    momentum_continuation        -> CONTINUATION_BASE
    balance_mean_reversion       -> DISTRIBUTION_BALANCE
    absorption_to_reversal_prep  -> ABSORPTION_ACCUMULATION + REVERSAL_PREPARATION
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atas_market_structure.models import EventHypothesisKind, EventPhase, TradableEventKind


@dataclass(frozen=True)
class SetupFeatures:
    """Feature conditions required for the event to be considered active."""

    min_trend_efficiency: float = 0.55
    min_initiative_strength: float = 0.60
    min_regime_probability: float = 0.45
    required_regimes: tuple[str, ...] = ()
    forbidden_regimes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationRule:
    """A single validation rule for event confirmation."""

    name: str
    metric_key: str
    operator: str  # "gte", "lte", "gt", "lt", "eq"
    threshold: float
    description: str


@dataclass(frozen=True)
class InvalidationRule:
    """A single invalidation rule that ends the event hypothesis."""

    name: str
    metric_key: str
    operator: str
    threshold: float
    description: str


@dataclass(frozen=True)
class EvidenceRequirement:
    """Required evidence for event confirmation."""

    bucket: str  # evidence_buckets key
    min_score: float
    description: str


@dataclass(frozen=True)
class ConfidenceShaping:
    """How confidence scores shape the posterior probability."""

    boost_signals: tuple[str, ...] = field(default_factory=tuple())
    penalty_signals: tuple[str, ...] = field(default_factory=tuple())
    anchor_boost: float = 0.10
    path_dependency_boost: float = 0.08


@dataclass(frozen=True)
class EventTemplate:
    """
    Complete template for one V1 tradable event.

    This is the STRUCTURED DEFINITION of the event lifecycle.
    It is NOT executable code; it is documentation + reference for
    the phase_machine and event_updater.
    """

    event_kind: TradableEventKind
    hypothesis_kind: EventHypothesisKind

    # Phase lifecycle description
    phase_lifecycle: str = field(repr=False)

    # Feature conditions for setup
    setup: SetupFeatures

    # Rules for reaching CONFIRMING phase
    validation_rules: tuple[ValidationRule, ...]

    # Rules for reaching RESOLVED (CONFIRMED) phase
    confirmation_rules: tuple[ValidationRule, ...]

    # Rules for INVALIDATED phase
    invalidation_rules: tuple[InvalidationRule, ...]

    # Rules for WEAKENING phase
    weakening_conditions: tuple[str, ...]

    # Evidence requirements
    required_evidence: tuple[EvidenceRequirement, ...]

    # What's missing before confirmation
    missing_confirmation_hints: tuple[str, ...]

    # Replacement candidates (what can supersede this event)
    replacement_candidates: tuple[str, ...]

    # Time window (in minutes from emergence)
    typical_duration_minutes: int = 60
    max_duration_minutes: int = 180

    # Confidence shaping
    confidence_shaping: ConfidenceShaping = field(default_factory=ConfidenceShaping)

    # Human-readable description
    description: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# momentum_continuation: CONTINUATION_BASE
# ─────────────────────────────────────────────────────────────────────────────

MOMENTUM_CONTINUATION = EventTemplate(
    event_kind=TradableEventKind.MOMENTUM_CONTINUATION,
    hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
    phase_lifecycle=(
        "EMERGING → BUILDING → CONFIRMING → RESOLVED (confirmed) | WEAKENING → INVALIDATED"
    ),
    setup=SetupFeatures(
        min_trend_efficiency=0.55,
        min_initiative_strength=0.60,
        min_regime_probability=0.45,
        required_regimes=("strong_momentum_trend", "weak_momentum_trend_narrow", "weak_momentum_trend_wide"),
        forbidden_regimes=("balance_mean_reversion", "compression"),
    ),
    validation_rules=(
        ValidationRule(
            name="trend_efficiency_support",
            metric_key="trend_efficiency",
            operator="gte",
            threshold=0.55,
            description="Trend efficiency must be at least 0.55 for momentum to be credible.",
        ),
        ValidationRule(
            name="initiative_relaunch_present",
            metric_key="initiative_strength",
            operator="gte",
            threshold=0.60,
            description="Initiative (buy or sell) must have re-accelerated for momentum confirmation.",
        ),
        ValidationRule(
            name="no_deep_return_to_center",
            metric_key="distance_to_balance_center_ticks",
            operator="gt",
            threshold=10.0,
            description="Price must remain away from balance center for momentum to persist.",
        ),
        ValidationRule(
            name="path_still_directional",
            metric_key="current_direction",
            operator="gte",
            threshold=0.30,
            description="Direction must be sustained (|direction| >= 0.30) for momentum.",
        ),
    ),
    confirmation_rules=(
        ValidationRule(
            name="momentum_confirmed",
            metric_key="initiative_reacceleration_score",
            operator="gte",
            threshold=0.68,
            description="Initiative re-acceleration >= 0.68 is the trigger for momentum RESOLVED.",
        ),
        ValidationRule(
            name="far_from_balance_center",
            metric_key="distance_to_balance_center_ticks",
            operator="gt",
            threshold=10.0,
            description="Must remain far from balance center on resolution.",
        ),
    ),
    invalidation_rules=(
        InvalidationRule(
            name="returned_to_balance_center",
            metric_key="distance_to_balance_center_ticks",
            operator="lte",
            threshold=10.0,
            description="Price returned to balance center invalidates momentum hypothesis.",
        ),
        InvalidationRule(
            name="opposite_initiative_displacement",
            metric_key="opposite_initiative",
            operator="gte",
            threshold=0.45,
            description="Opposite initiative >= 0.45 displaces the current momentum direction.",
        ),
        InvalidationRule(
            name="absorption_against_trend",
            metric_key="absorption_score",
            operator="gte",
            threshold=0.55,
            description="Absorption >= 0.55 against the trend signals potential reversal.",
        ),
    ),
    weakening_conditions=(
        "probability_dropped_above_threshold",
        "initiative_fading_below_0.50",
        "absorption_emerging",
        "distance_to_center_decreasing",
    ),
    required_evidence=(
        EvidenceRequirement(bucket="initiative", min_score=0.60, description="Initiative bucket must have buy or sell signal."),
        EvidenceRequirement(bucket="trend_efficiency", min_score=0.55, description="Trend efficiency must be available."),
        EvidenceRequirement(bucket="bar_structure", min_score=0.50, description="Bar structure must confirm directional movement."),
    ),
    missing_confirmation_hints=(
        "fresh_push_needed",
        "acceptance_after_pullback",
        "avoid_return_to_old_balance",
        "need_sustained_initiative",
    ),
    replacement_candidates=(
        "balance_mean_reversion",
        "absorption_to_reversal_preparation",
    ),
    typical_duration_minutes=30,
    max_duration_minutes=120,
    confidence_shaping=ConfidenceShaping(
        boost_signals=("initiative_relaunch_present", "trend_efficiency_high", "path_directional"),
        penalty_signals=("absorption_against_trend", "opposite_initiative_growing", "back_to_center"),
        anchor_boost=0.10,
        path_dependency_boost=0.08,
    ),
    description=(
        "momentum_continuation: Price is in a directional move that is expected to persist. "
        "Initiative traders are driving price away from balance center with high trend efficiency. "
        "DOM evidence (initiative imbalance) is mechanism evidence that feeds the initiative_score, "
        "but the final judgment is based on the composite trend_efficiency + initiative_strength score."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# balance_mean_reversion: DISTRIBUTION_BALANCE
# ─────────────────────────────────────────────────────────────────────────────

BALANCE_MEAN_REVERSION = EventTemplate(
    event_kind=TradableEventKind.BALANCE_MEAN_REVERSION,
    hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
    phase_lifecycle=(
        "EMERGING → BUILDING → CONFIRMING → RESOLVED (confirmed) | WEAKENING → INVALIDATED"
    ),
    setup=SetupFeatures(
        min_trend_efficiency=0.0,
        min_initiative_strength=0.0,
        min_regime_probability=0.45,
        required_regimes=("balance_mean_reversion", "compression"),
        forbidden_regimes=("strong_momentum_trend", "weak_momentum_trend_wide"),
    ),
    validation_rules=(
        ValidationRule(
            name="balance_center_defined",
            metric_key="distance_to_balance_center_ticks",
            operator="lte",
            threshold=24.0,
            description="Balance center must be defined (distance < 24 ticks).",
        ),
        ValidationRule(
            name="overlap_and_rotation",
            metric_key="balance_score",
            operator="gte",
            threshold=0.55,
            description="Balance score >= 0.55 indicates overlapping bars and rotation.",
        ),
        ValidationRule(
            name="initiative_weakened",
            metric_key="initiative_strength",
            operator="lte",
            threshold=0.60,
            description="Initiative must be subdued for balance to form.",
        ),
        ValidationRule(
            name="anchor_as_center_magnet",
            metric_key="anchor_interaction_score",
            operator="gte",
            threshold=0.25,
            description="Memory anchors near balance center reinforce mean reversion.",
        ),
    ),
    confirmation_rules=(
        ValidationRule(
            name="price_reached_center",
            metric_key="distance_to_balance_center_ticks",
            operator="lte",
            threshold=10.0,
            description="Price reached balance center (distance <= 10 ticks) for reversion confirmation.",
        ),
        ValidationRule(
            name="balance_score_confirmed",
            metric_key="balance_score",
            operator="gte",
            threshold=0.56,
            description="Balance score >= 0.56 confirms the distribution pattern.",
        ),
    ),
    invalidation_rules=(
        InvalidationRule(
            name="fresh_initiative_breakout",
            metric_key="initiative_strength",
            operator="gte",
            threshold=0.70,
            description="Fresh initiative breakout (>= 0.70) breaks the balance and invalidates reversion.",
        ),
        InvalidationRule(
            name="acceptance_away_from_center",
            metric_key="distance_to_balance_center_ticks",
            operator="gt",
            threshold=30.0,
            description="Price accepted away from center (> 30 ticks) shows directional intent.",
        ),
    ),
    weakening_conditions=(
        "probability_dropped_above_threshold",
        "initiative_building_above_0.55",
        "distance_from_center_increasing",
        "compression_breaking",
    ),
    required_evidence=(
        EvidenceRequirement(bucket="balance", min_score=0.50, description="Balance center must be defined and near."),
        EvidenceRequirement(bucket="anchor_interaction", min_score=0.20, description="Anchor interaction strengthens reversion case."),
        EvidenceRequirement(bucket="volatility_range", min_score=0.0, description="Volatility/range evidence helps confirm compression."),
    ),
    missing_confirmation_hints=(
        "continued_return_to_center",
        "avoid_fresh_single_sided_acceptance",
        "need_overlap_confirmation",
        "need_sustained_near_center",
    ),
    replacement_candidates=(
        "momentum_continuation",
        "absorption_to_reversal_preparation",
    ),
    typical_duration_minutes=60,
    max_duration_minutes=180,
    confidence_shaping=ConfidenceShaping(
        boost_signals=("balance_center_defined", "overlap_confirmed", "anchor_near_center"),
        penalty_signals=("fresh_initiative_emerging", "away_from_center", "compression_breaking"),
        anchor_boost=0.15,
        path_dependency_boost=0.10,
    ),
    description=(
        "balance_mean_reversion: Price is oscillating around a balance center (POC). "
        "Initiative is subdued, bars overlap, and price tends to return to center. "
        "DOM evidence (stacked imbalance) feeds the initiative/absorption scores, "
        "but the composite balance_score determines the hypothesis probability. "
        "DOM alone does NOT decide; it is ONE of the evidence buckets."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# absorption_to_reversal_preparation: ABSORPTION_ACCUMULATION + REVERSAL_PREPARATION
# ─────────────────────────────────────────────────────────────────────────────

ABSORPTION_ACCUMULATION = EventTemplate(
    event_kind=TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
    hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
    phase_lifecycle=(
        "EMERGING → BUILDING → CONFIRMING → (ABSORPTION_INVALIDATED → REVERSAL_PREPARATION) "
        "| WEAKENING → INVALIDATED"
    ),
    setup=SetupFeatures(
        min_trend_efficiency=0.0,
        min_initiative_strength=0.0,
        min_regime_probability=0.40,
        required_regimes=("transition_exhaustion", "compression"),
        forbidden_regimes=("strong_momentum_trend", "weak_momentum_trend_wide"),
    ),
    validation_rules=(
        ValidationRule(
            name="repeated_absorption",
            metric_key="absorption_score",
            operator="gte",
            threshold=0.55,
            description="Absorption score >= 0.55 indicates repeated liquidity absorption.",
        ),
        ValidationRule(
            name="trend_efficiency_fading",
            metric_key="trend_efficiency",
            operator="lte",
            threshold=0.50,
            description="Trend efficiency fading (<= 0.50) signals momentum exhaustion.",
        ),
        ValidationRule(
            name="anchor_proximity_support",
            metric_key="anchor_interaction_score",
            operator="gte",
            threshold=0.25,
            description="Price near a memory anchor (>= 0.25) supports absorption thesis.",
        ),
        ValidationRule(
            name="path_dependency_present",
            metric_key="path_dependency_score",
            operator="gte",
            threshold=0.20,
            description="Path dependency (>= 0.20) indicates accumulation history.",
        ),
    ),
    confirmation_rules=(
        ValidationRule(
            name="absorption_confirmed",
            metric_key="absorption_score",
            operator="gte",
            threshold=0.60,
            description="Absorption >= 0.60 confirms accumulation phase.",
        ),
    ),
    invalidation_rules=(
        InvalidationRule(
            name="trend_reaccelerated",
            metric_key="initiative_strength",
            operator="gte",
            threshold=0.70,
            description="Initiative re-acceleration (>= 0.70) + efficiency >= 0.60 breaks absorption.",
        ),
        InvalidationRule(
            name="absorption_ended",
            metric_key="absorption_score",
            operator="lt",
            threshold=0.45,
            description="Absorption dropped below 0.45 signals initiative won.",
        ),
    ),
    weakening_conditions=(
        "probability_dropped_above_threshold",
        "absorption_score_decreasing",
        "trend_efficiency_increasing",
        "anchor_support_weakening",
    ),
    required_evidence=(
        EvidenceRequirement(bucket="absorption", min_score=0.50, description="Absorption evidence must be present."),
        EvidenceRequirement(bucket="path_dependency", min_score=0.15, description="Path dependency evidence strengthens accumulation case."),
        EvidenceRequirement(bucket="anchor_interaction", min_score=0.20, description="Anchor interaction near absorption levels."),
    ),
    missing_confirmation_hints=(
        "need_sustained_hold",
        "need_opposite_initiative_hint",
        "need_path_stability",
    ),
    replacement_candidates=(
        "momentum_continuation",
    ),
    typical_duration_minutes=45,
    max_duration_minutes=150,
    confidence_shaping=ConfidenceShaping(
        boost_signals=("repeated_absorption", "efficiency_fading", "anchor_near_absorption"),
        penalty_signals=("initiative_reaccelerating", "absorption_ending", "trend_resuming"),
        anchor_boost=0.12,
        path_dependency_boost=0.10,
    ),
    description=(
        "absorption_accumulation: Market is absorbing initiative trades at a price level. "
        "Trend efficiency is fading, and price is stuck near a key level. "
        "DOM evidence (large resting orders) feeds the absorption_score, "
        "but the composite absorption + trend_efficiency determines the hypothesis. "
        "This is the FIRST PHASE of absorption_to_reversal_preparation."
    ),
)


REVERSAL_PREPARATION = EventTemplate(
    event_kind=TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
    hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
    phase_lifecycle=(
        "EMERGING → BUILDING → CONFIRMING → RESOLVED (confirmed) | WEAKENING → INVALIDATED"
    ),
    setup=SetupFeatures(
        min_trend_efficiency=0.0,
        min_initiative_strength=0.0,
        min_regime_probability=0.40,
        required_regimes=("transition_exhaustion",),
        forbidden_regimes=("strong_momentum_trend",),
    ),
    validation_rules=(
        ValidationRule(
            name="absorption_established",
            metric_key="absorption_score",
            operator="gte",
            threshold=0.50,
            description="Absorption >= 0.50 must be established before reversal can form.",
        ),
        ValidationRule(
            name="opposite_initiative_emerging",
            metric_key="opposite_initiative",
            operator="gte",
            threshold=0.30,
            description="Opposite initiative emerging (>= 0.30) is the reversal catalyst.",
        ),
        ValidationRule(
            name="transition_regime_support",
            metric_key="anchor_interaction_score",
            operator="gte",
            threshold=0.25,
            description="Anchor near the absorption level supports reversal thesis.",
        ),
    ),
    confirmation_rules=(
        ValidationRule(
            name="reversal_confirmed",
            metric_key="opposite_initiative",
            operator="gte",
            threshold=0.30,
            description="Opposite initiative >= 0.30 + absorption >= 0.55 confirms reversal.",
        ),
        ValidationRule(
            name="absorption_present_at_reversal",
            metric_key="absorption_score",
            operator="gte",
            threshold=0.55,
            description="Absorption must still be present at reversal confirmation.",
        ),
    ),
    invalidation_rules=(
        InvalidationRule(
            name="same_side_reacceleration",
            metric_key="initiative_strength",
            operator="gte",
            threshold=0.72,
            description="Same-side re-acceleration (>= 0.72) with low balance (< 0.65) breaks reversal.",
        ),
        InvalidationRule(
            name="stuck_in_static_balance",
            metric_key="balance_score",
            operator="gte",
            threshold=0.70,
            description="Static balance (>= 0.70) without opposite initiative (< 0.25) means no reversal.",
        ),
    ),
    weakening_conditions=(
        "probability_dropped_above_threshold",
        "opposite_initiative_fading",
        "absorption_ending",
        "balance_strengthening",
    ),
    required_evidence=(
        EvidenceRequirement(bucket="absorption", min_score=0.50, description="Absorption must precede reversal."),
        EvidenceRequirement(bucket="initiative", min_score=0.30, description="Opposite initiative must emerge."),
        EvidenceRequirement(bucket="anchor_interaction", min_score=0.20, description="Anchor near reversal level."),
    ),
    missing_confirmation_hints=(
        "need_clear_opposite_push",
        "need_follow_through_away_from_edge",
        "need_sustained_opposite_initiative",
    ),
    replacement_candidates=(
        "momentum_continuation",
        "balance_mean_reversion",
    ),
    typical_duration_minutes=20,
    max_duration_minutes=90,
    confidence_shaping=ConfidenceShaping(
        boost_signals=("opposite_initiative_emerging", "absorption_confirmed", "anchor_near_reversal"),
        penalty_signals=("same_side_reaccelerating", "stuck_balance", "no_opposite_initiative"),
        anchor_boost=0.12,
        path_dependency_boost=0.08,
    ),
    description=(
        "reversal_preparation: After absorption_accumulation, opposite initiative begins to emerge. "
        "Price is preparing to reverse direction from the absorbed level. "
        "DOM evidence (stacked offers/bids being lifted/hit) is mechanism evidence "
        "for the opposite_initiative_score. "
        "The composite absorption + opposite_initiative + balance_score determines the hypothesis. "
        "This is the SECOND PHASE of absorption_to_reversal_preparation."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

V1_EVENT_TEMPLATES: dict[TradableEventKind, EventTemplate] = {
    MOMENTUM_CONTINUATION.event_kind: MOMENTUM_CONTINUATION,
    BALANCE_MEAN_REVERSION.event_kind: BALANCE_MEAN_REVERSION,
    ABSORPTION_ACCUMULATION.event_kind: ABSORPTION_ACCUMULATION,
}

V1_HYPOTHESIS_TEMPLATES: dict[EventHypothesisKind, EventTemplate] = {
    template.hypothesis_kind: template for template in V1_EVENT_TEMPLATES.values()
}

# REVERSAL_PREPARATION shares the same event_kind as ABSORPTION_ACCUMULATION
# but has a different hypothesis_kind, so we add it separately
V1_HYPOTHESIS_TEMPLATES[REVERSAL_PREPARATION.hypothesis_kind] = REVERSAL_PREPARATION
