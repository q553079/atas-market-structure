"""
Phase State Machine for V1 Event Hypotheses.

Design principles:
- Events are LIFECYCLE TRAJECTORIES, not static labels.
- Phase transitions are deterministic and rule-driven (no LLM in critical path).
- Each of the 3 V1 events has explicit setup / validation / invalidation rules.
- REPLACED is an EPISODE resolution, not a hypothesis phase.

Phase lifecycle:
    EMERGING -> BUILDING -> CONFIRMING -> RESOLVED (success)
                  |            |              |
                  v            v              v
               WEAKENING   WEAKENING     INVALIDATED
                  |            |
                  v            v
             INVALIDATED   INVALIDATED

Episode resolution (from CONFIRMING/RESOLVED):
    - CONFIRMED: reached RESOLVED with valid confirmation
    - INVALIDATED: reached INVALIDATED from any phase
    - TIMED_OUT: exceeded time window without resolution
    - REPLACED: another event kind superseded this hypothesis
    - EXPIRED: exceeded episode duration without confirmation

V1 event mapping:
    momentum_continuation        -> CONTINUATION_BASE
    balance_mean_reversion       -> DISTRIBUTION_BALANCE
    absorption_to_reversal_prep  -> ABSORPTION_ACCUMULATION + REVERSAL_PREPARATION
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atas_market_structure.models import EpisodeResolution, EventHypothesisKind, EventPhase


@dataclass(frozen=True)
class PhaseTransitionContext:
    """Immutable context for phase transition decisions."""

    hypothesis_kind: EventHypothesisKind
    current_probability: float
    prior_probability: float | None
    initiative_strength: float
    initiative_buy_score: float
    initiative_sell_score: float
    trend_efficiency: float
    balance_score: float
    absorption_score: float
    distance_to_center_ticks: float
    center_hit_ticks: float
    reacceleration_threshold: float
    weak_trend_probability: float
    compression_probability: float
    transition_probability: float
    strong_trend_probability: float
    anchor_support: float
    opposite_initiative: float


@dataclass(frozen=True)
class PhaseTransitionResult:
    """Result of a phase transition decision."""

    new_phase: EventPhase
    reason: str
    is_terminal: bool = False
    resolution: EpisodeResolution | None = None


_THRESHOLDS = {
    "building_probability": 0.36,
    "confirming_probability": 0.56,
    "resolved_probability": 0.74,
    "weakening_drop": 0.12,
    "reacceleration_threshold": 0.68,
    "center_hit_ticks": 10.0,
}


def get_thresholds(profile_payload: dict[str, Any]) -> dict[str, float]:
    """Merge profile thresholds with defaults."""
    thresholds = profile_payload.get("thresholds") if isinstance(profile_payload.get("thresholds"), dict) else {}
    return {
        "building_probability": float(thresholds.get("building_hypothesis_probability", _THRESHOLDS["building_probability"])),
        "confirming_probability": float(thresholds.get("confirming_hypothesis_probability", _THRESHOLDS["confirming_probability"])),
        "resolved_probability": float(thresholds.get("resolved_hypothesis_probability", _THRESHOLDS["resolved_probability"])),
        "weakening_drop": float(thresholds.get("weakening_drop_threshold", _THRESHOLDS["weakening_drop"])),
        "reacceleration_threshold": float(thresholds.get("initiative_reacceleration_score", _THRESHOLDS["reacceleration_threshold"])),
        "center_hit_ticks": float(thresholds.get("center_hit_ticks", _THRESHOLDS["center_hit_ticks"])),
    }


def compute_phase(ctx: PhaseTransitionContext, thresholds: dict[str, float]) -> PhaseTransitionResult:
    """
    Deterministic phase computation for the given hypothesis and context.

    This is the SINGLE source of truth for phase decisions.
    All phase transitions are explicit, rule-driven, and testable.
    """
    build_thr = thresholds["building_probability"]
    confirm_thr = thresholds["confirming_probability"]
    resolve_thr = thresholds["resolved_probability"]
    weaken_drop = thresholds["weakening_drop"]
    reacc_thr = thresholds["reacceleration_threshold"]
    center_hit = thresholds["center_hit_ticks"]
    prob = ctx.current_probability
    prior_prob = ctx.prior_probability

    match ctx.hypothesis_kind:
        case EventHypothesisKind.CONTINUATION_BASE:
            return _continuation_phase(ctx, prob, prior_prob, build_thr, confirm_thr, resolve_thr, weaken_drop, reacc_thr, center_hit)

        case EventHypothesisKind.DISTRIBUTION_BALANCE:
            return _balance_phase(ctx, prob, prior_prob, build_thr, confirm_thr, weaken_drop, reacc_thr, center_hit)

        case EventHypothesisKind.ABSORPTION_ACCUMULATION:
            return _absorption_phase(ctx, prob, prior_prob, build_thr, confirm_thr, weaken_drop, reacc_thr)

        case EventHypothesisKind.REVERSAL_PREPARATION:
            return _reversal_phase(ctx, prob, prior_prob, build_thr, confirm_thr, resolve_thr, weaken_drop, reacc_thr)


def _continuation_phase(
    ctx: PhaseTransitionContext,
    prob: float,
    prior_prob: float | None,
    build_thr: float,
    confirm_thr: float,
    resolve_thr: float,
    weaken_drop: float,
    reacc_thr: float,
    center_hit: float,
) -> PhaseTransitionResult:
    """
    momentum_continuation: CONTINUATION_BASE

    Lifecycle rules:
    - EMERGING: probability < building threshold
    - BUILDING: probability >= building, < confirming
    - CONFIRMING: probability >= confirming, < resolved, with initiative re-acceleration
    - RESOLVED: initiative_reacceleration + probability >= resolve + far from balance center
    - WEAKENING: probability dropped significantly from prior (>= weakening_drop)
    - INVALIDATED: price returned to balance center OR opposite initiative displacement
                   OR absorption against the trend

    Validation signals: trend_efficiency >= 0.55, initiative_relaunch >= 0.60,
                         far_from_center (> center_hit_ticks), directional path
    Invalidation signals: back_to_center, opposite_initiative >= 0.45, absorption >= 0.55
    """
    if prob >= resolve_thr and ctx.initiative_strength >= reacc_thr and ctx.distance_to_center_ticks > center_hit:
        return PhaseTransitionResult(
            new_phase=EventPhase.RESOLVED,
            reason="continuation_resolved",
            is_terminal=True,
            resolution=EpisodeResolution.CONFIRMED,
        )

    if ctx.distance_to_center_ticks <= center_hit:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="continuation_invalidated_back_to_center",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if ctx.opposite_initiative >= 0.45:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="continuation_invalidated_opposite_initiative",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if ctx.absorption_score >= 0.55:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="continuation_invalidated_absorption",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if prior_prob is not None and (prior_prob - prob) >= weaken_drop and prob >= confirm_thr:
        return PhaseTransitionResult(
            new_phase=EventPhase.WEAKENING,
            reason="continuation_weakening",
        )

    if prob >= confirm_thr:
        return PhaseTransitionResult(new_phase=EventPhase.CONFIRMING, reason="continuation_confirming")

    if prob >= build_thr:
        return PhaseTransitionResult(new_phase=EventPhase.BUILDING, reason="continuation_building")

    return PhaseTransitionResult(new_phase=EventPhase.EMERGING, reason="continuation_emerging")


def _balance_phase(
    ctx: PhaseTransitionContext,
    prob: float,
    prior_prob: float | None,
    build_thr: float,
    confirm_thr: float,
    weaken_drop: float,
    reacc_thr: float,
    center_hit: float,
) -> PhaseTransitionResult:
    """
    balance_mean_reversion: DISTRIBUTION_BALANCE

    Lifecycle rules:
    - RESOLVED: price reached balance center AND probability >= confirm
    - INVALIDATED: fresh initiative breakout OR acceptance away from center
    - WEAKENING: probability dropped but still above build threshold
    - CONFIRMING: near center + probability >= confirm threshold
    - BUILDING: probability >= build threshold

    Validation signals: balance_center_defined, overlap_and_rotation,
                        initiative_weakened, anchor_as_center_magnet
    Invalidation signals: fresh_initiative >= 0.70, acceptance_away_from_center
    """
    if prob >= confirm_thr and ctx.distance_to_center_ticks <= center_hit:
        return PhaseTransitionResult(
            new_phase=EventPhase.RESOLVED,
            reason="balance_resolved",
            is_terminal=True,
            resolution=EpisodeResolution.CONFIRMED,
        )

    if ctx.initiative_strength >= reacc_thr and ctx.distance_to_center_ticks > center_hit * 2:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="balance_invalidated_initiative_breakout",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if prior_prob is not None and (prior_prob - prob) >= weaken_drop and prob >= build_thr:
        return PhaseTransitionResult(
            new_phase=EventPhase.WEAKENING,
            reason="balance_weakening",
        )

    if prob >= confirm_thr:
        return PhaseTransitionResult(new_phase=EventPhase.CONFIRMING, reason="balance_confirming")

    if prob >= build_thr:
        return PhaseTransitionResult(new_phase=EventPhase.BUILDING, reason="balance_building")

    return PhaseTransitionResult(new_phase=EventPhase.EMERGING, reason="balance_emerging")


def _absorption_phase(
    ctx: PhaseTransitionContext,
    prob: float,
    prior_prob: float | None,
    build_thr: float,
    confirm_thr: float,
    weaken_drop: float,
    reacc_thr: float,
) -> PhaseTransitionResult:
    """
    absorption_to_reversal_preparation (part 1): ABSORPTION_ACCUMULATION

    Lifecycle rules:
    - RESOLVED: initiative re-acceleration occurred (absorption ended) -> triggers REVERSAL_PREPARATION
    - INVALIDATED: initiative re-accelerated AND absorption dropped (< 0.45)
                   OR trend re-accelerated strongly
    - WEAKENING: probability dropped significantly
    - CONFIRMING: probability >= confirm threshold
    - BUILDING: probability >= build threshold

    Validation signals: repeated_absorption >= 0.55, trend_efficiency_fading <= 0.50,
                        anchor_proximity >= 0.25
    Invalidation signals: trend_reaccelerated >= 0.70 AND efficiency >= 0.60
    """
    if ctx.initiative_strength >= reacc_thr and ctx.absorption_score < 0.45:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="absorption_invalidated_reacceleration",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if ctx.trend_efficiency >= 0.60 and ctx.initiative_strength >= reacc_thr:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="absorption_invalidated_trend_reacceleration",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if prior_prob is not None and (prior_prob - prob) >= weaken_drop and prob >= build_thr:
        return PhaseTransitionResult(
            new_phase=EventPhase.WEAKENING,
            reason="absorption_weakening",
        )

    if prob >= confirm_thr:
        return PhaseTransitionResult(new_phase=EventPhase.CONFIRMING, reason="absorption_confirming")

    if prob >= build_thr:
        return PhaseTransitionResult(new_phase=EventPhase.BUILDING, reason="absorption_building")

    return PhaseTransitionResult(new_phase=EventPhase.EMERGING, reason="absorption_emerging")


def _reversal_phase(
    ctx: PhaseTransitionContext,
    prob: float,
    prior_prob: float | None,
    build_thr: float,
    confirm_thr: float,
    resolve_thr: float,
    weaken_drop: float,
    reacc_thr: float,
) -> PhaseTransitionResult:
    """
    absorption_to_reversal_preparation (part 2): REVERSAL_PREPARATION

    Lifecycle rules:
    - RESOLVED: probability >= resolve + absorption >= 0.55 + opposite_initiative >= 0.30
    - INVALIDATED: initiative re-accelerated on same side AND balance < 0.65
    - WEAKENING: probability dropped significantly
    - CONFIRMING: probability >= confirm threshold
    - BUILDING: probability >= build threshold

    Validation signals: absorption_established >= 0.50, opposite_initiative_emerging >= 0.30,
                        transition_regime >= 0.25
    Invalidation signals: same_side_reacceleration >= 0.72, stuck_in_static_balance
    """
    if prob >= resolve_thr and ctx.absorption_score >= 0.55 and ctx.opposite_initiative >= 0.30:
        return PhaseTransitionResult(
            new_phase=EventPhase.RESOLVED,
            reason="reversal_resolved",
            is_terminal=True,
            resolution=EpisodeResolution.CONFIRMED,
        )

    if ctx.initiative_strength >= reacc_thr and ctx.balance_score < 0.65:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="reversal_invalidated_same_side_reacceleration",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if ctx.balance_score >= 0.70 and ctx.opposite_initiative < 0.25:
        return PhaseTransitionResult(
            new_phase=EventPhase.INVALIDATED,
            reason="reversal_invalidated_stuck_balance",
            is_terminal=True,
            resolution=EpisodeResolution.INVALIDATED,
        )

    if prior_prob is not None and (prior_prob - prob) >= weaken_drop and prob >= build_thr:
        return PhaseTransitionResult(
            new_phase=EventPhase.WEAKENING,
            reason="reversal_weakening",
        )

    if prob >= confirm_thr:
        return PhaseTransitionResult(new_phase=EventPhase.CONFIRMING, reason="reversal_confirming")

    if prob >= build_thr:
        return PhaseTransitionResult(new_phase=EventPhase.BUILDING, reason="reversal_building")

    return PhaseTransitionResult(new_phase=EventPhase.EMERGING, reason="reversal_emerging")
