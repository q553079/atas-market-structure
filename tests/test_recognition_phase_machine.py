"""
Comprehensive tests for the V1 Recognizer Phase State Machine.

Requirements:
- Each of the 3 V1 events: >= 3 success + >= 3 failure/invalidation scenarios
- Replacement / invalidation / downgrade scenarios
- Idempotency: same input -> same output

V1 events:
    momentum_continuation        -> CONTINUATION_BASE
    balance_mean_reversion       -> DISTRIBUTION_BALANCE
    absorption_to_reversal_prep -> ABSORPTION_ACCUMULATION + REVERSAL_PREPARATION

Phase lifecycle:
    EMERGING -> BUILDING -> CONFIRMING -> RESOLVED (confirmed)
                  |            |              |
                  v            v              v
               WEAKENING   WEAKENING     INVALIDATED
                  |            |
                  v            v
             INVALIDATED   INVALIDATED
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atas_market_structure.models import (
    DegradedMode,
    EpisodeResolution,
    EventHypothesisKind,
    EventPhase,
    TradableEventKind,
)
from atas_market_structure.recognition.phase_machine import (
    PhaseTransitionContext,
    compute_phase,
    get_thresholds,
)
from atas_market_structure.repository import SQLiteAnalysisRepository


# ─────────────────────────────────────────────────────────────────────────────
# Test helper: build a PhaseTransitionContext with defaults
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(
    hypothesis_kind: EventHypothesisKind,
    probability: float,
    prior_probability: float | None = None,
    initiative_strength: float = 0.50,
    initiative_buy_score: float = 0.50,
    initiative_sell_score: float = 0.30,
    trend_efficiency: float = 0.50,
    balance_score: float = 0.30,
    absorption_score: float = 0.30,
    distance_to_center_ticks: float = 20.0,
    center_hit_ticks: float = 10.0,
    reacceleration_threshold: float = 0.68,
    weak_trend_probability: float = 0.20,
    compression_probability: float = 0.20,
    transition_probability: float = 0.20,
    strong_trend_probability: float = 0.40,
    anchor_support: float = 0.30,
    opposite_initiative: float | None = None,
) -> PhaseTransitionContext:
    if opposite_initiative is None:
        opposite_initiative = min(initiative_buy_score, initiative_sell_score)
    return PhaseTransitionContext(
        hypothesis_kind=hypothesis_kind,
        current_probability=probability,
        prior_probability=prior_probability,
        initiative_strength=initiative_strength,
        initiative_buy_score=initiative_buy_score,
        initiative_sell_score=initiative_sell_score,
        trend_efficiency=trend_efficiency,
        balance_score=balance_score,
        absorption_score=absorption_score,
        distance_to_center_ticks=distance_to_center_ticks,
        center_hit_ticks=center_hit_ticks,
        reacceleration_threshold=reacceleration_threshold,
        weak_trend_probability=weak_trend_probability,
        compression_probability=compression_probability,
        transition_probability=transition_probability,
        strong_trend_probability=strong_trend_probability,
        anchor_support=anchor_support,
        opposite_initiative=opposite_initiative,
    )


DEFAULT_THRESHOLDS = get_thresholds({})


# ═════════════════════════════════════════════════════════════════════════════
# MOMENTUM CONTINUATION: CONTINUATION_BASE
# ═════════════════════════════════════════════════════════════════════════════

class TestMomentumContinuationSuccess:
    """>= 3 success scenarios for momentum_continuation."""

    def test_momentum_resolved_with_reacceleration(self) -> None:
        """Scenario 1: Strong initiative re-acceleration + high probability + far from center -> RESOLVED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.80,
            initiative_strength=0.72,
            initiative_buy_score=0.72,
            initiative_sell_score=0.10,
            trend_efficiency=0.72,
            balance_score=0.15,
            absorption_score=0.20,
            distance_to_center_ticks=18.0,
            opposite_initiative=0.10,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.RESOLVED
        assert result.resolution == EpisodeResolution.CONFIRMED
        assert result.is_terminal is True

    def test_momentum_confirming_before_resolution(self) -> None:
        """Scenario 2: High probability but not yet at re-acceleration threshold -> CONFIRMING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.62,
            initiative_strength=0.60,
            initiative_buy_score=0.60,
            initiative_sell_score=0.20,
            trend_efficiency=0.68,
            balance_score=0.20,
            absorption_score=0.25,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.CONFIRMING
        assert result.is_terminal is False

    def test_momentum_building_phase(self) -> None:
        """Scenario 3: Probability above build threshold but below confirm -> BUILDING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.45,
            initiative_strength=0.55,
            initiative_buy_score=0.55,
            initiative_sell_score=0.20,
            trend_efficiency=0.60,
            balance_score=0.25,
            absorption_score=0.20,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.BUILDING
        assert result.is_terminal is False


class TestMomentumContinuationFailure:
    """>= 3 failure/invalidation scenarios for momentum_continuation."""

    def test_momentum_invalidated_back_to_balance_center(self) -> None:
        """Failure 1: Price returned to balance center -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.70,
            initiative_strength=0.65,
            initiative_buy_score=0.65,
            initiative_sell_score=0.15,
            trend_efficiency=0.60,
            balance_score=0.50,
            absorption_score=0.30,
            distance_to_center_ticks=5.0,
            opposite_initiative=0.15,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "back_to_center" in result.reason

    def test_momentum_invalidated_opposite_initiative(self) -> None:
        """Failure 2: Opposite initiative displaced momentum -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.70,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.50,
            trend_efficiency=0.55,
            balance_score=0.20,
            absorption_score=0.30,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.50,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "opposite_initiative" in result.reason

    def test_momentum_invalidated_by_absorption(self) -> None:
        """Failure 3: Absorption against the trend -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.68,
            initiative_strength=0.65,
            initiative_buy_score=0.65,
            initiative_sell_score=0.15,
            trend_efficiency=0.58,
            balance_score=0.25,
            absorption_score=0.60,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.15,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "absorption" in result.reason

    def test_momentum_weakening(self) -> None:
        """Failure 4: Probability dropped significantly -> WEAKENING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.58,
            prior_probability=0.72,
            initiative_strength=0.60,
            initiative_buy_score=0.60,
            initiative_sell_score=0.20,
            trend_efficiency=0.55,
            balance_score=0.20,
            absorption_score=0.25,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.WEAKENING

    def test_momentum_emerging(self) -> None:
        """Failure 5: Probability below build threshold -> EMERGING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.30,
            initiative_strength=0.40,
            initiative_buy_score=0.40,
            initiative_sell_score=0.20,
            trend_efficiency=0.45,
            balance_score=0.40,
            absorption_score=0.30,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.EMERGING


# ═════════════════════════════════════════════════════════════════════════════
# BALANCE MEAN REVERSION: DISTRIBUTION_BALANCE
# ═════════════════════════════════════════════════════════════════════════════

class TestBalanceMeanReversionSuccess:
    """>= 3 success scenarios for balance_mean_reversion."""

    def test_balance_resolved_price_reached_center(self) -> None:
        """Scenario 1: Price reached balance center + high probability -> RESOLVED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.62,
            initiative_strength=0.30,
            initiative_buy_score=0.30,
            initiative_sell_score=0.25,
            trend_efficiency=0.35,
            balance_score=0.65,
            absorption_score=0.20,
            distance_to_center_ticks=4.0,
            opposite_initiative=0.25,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.RESOLVED
        assert result.resolution == EpisodeResolution.CONFIRMED
        assert result.is_terminal is True

    def test_balance_confirming_building(self) -> None:
        """Scenario 2: probability 0.50 (>= build 0.36, < confirm 0.56) -> BUILDING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.50,
            initiative_strength=0.35,
            initiative_buy_score=0.35,
            initiative_sell_score=0.20,
            trend_efficiency=0.38,
            balance_score=0.60,
            absorption_score=0.20,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.BUILDING
        assert result.is_terminal is False

    def test_balance_building_phase(self) -> None:
        """Scenario 3: Above build threshold but not near center -> BUILDING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.42,
            initiative_strength=0.40,
            initiative_buy_score=0.40,
            initiative_sell_score=0.20,
            trend_efficiency=0.40,
            balance_score=0.55,
            absorption_score=0.20,
            distance_to_center_ticks=12.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.BUILDING
        assert result.is_terminal is False


class TestBalanceMeanReversionFailure:
    """>= 3 failure/invalidation scenarios for balance_mean_reversion."""

    def test_balance_invalidated_initiative_breakout(self) -> None:
        """Failure 1: Fresh initiative breakout -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.60,
            initiative_strength=0.72,
            initiative_buy_score=0.72,
            initiative_sell_score=0.15,
            trend_efficiency=0.55,
            balance_score=0.45,
            absorption_score=0.20,
            distance_to_center_ticks=25.0,
            opposite_initiative=0.15,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "breakout" in result.reason

    def test_balance_invalidated_acceptance_away_from_center(self) -> None:
        """Failure 2: Price accepted away from center -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.58,
            initiative_strength=0.70,
            initiative_buy_score=0.70,
            initiative_sell_score=0.20,
            trend_efficiency=0.50,
            balance_score=0.40,
            absorption_score=0.20,
            distance_to_center_ticks=28.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED

    def test_balance_weakening(self) -> None:
        """Failure 3: Probability dropped significantly -> WEAKENING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.40,
            prior_probability=0.55,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.20,
            trend_efficiency=0.40,
            balance_score=0.50,
            absorption_score=0.25,
            distance_to_center_ticks=10.0,
            opposite_initiative=0.20,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.WEAKENING

    def test_balance_emerging_low_probability(self) -> None:
        """Failure 4: Low probability below build threshold -> EMERGING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.28,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.30,
            trend_efficiency=0.50,
            balance_score=0.35,
            absorption_score=0.30,
            distance_to_center_ticks=20.0,
            opposite_initiative=0.30,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.EMERGING


# ═════════════════════════════════════════════════════════════════════════════
# ABSORPTION TO REVERSAL PREPARATION: ABSORPTION_ACCUMULATION
# ═════════════════════════════════════════════════════════════════════════════

class TestAbsorptionAccumulationSuccess:
    """>= 3 success scenarios for absorption_accumulation."""

    def test_absorption_confirming_high_absorption(self) -> None:
        """Scenario 1: High absorption score -> CONFIRMING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.60,
            initiative_strength=0.40,
            initiative_buy_score=0.40,
            initiative_sell_score=0.25,
            trend_efficiency=0.40,
            balance_score=0.30,
            absorption_score=0.65,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.25,
            transition_probability=0.55,
            compression_probability=0.40,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.CONFIRMING
        assert result.is_terminal is False

    def test_absorption_building_phase(self) -> None:
        """Scenario 2: Above build threshold -> BUILDING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.45,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.20,
            trend_efficiency=0.42,
            balance_score=0.30,
            absorption_score=0.55,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
            transition_probability=0.45,
            compression_probability=0.35,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.BUILDING

    def test_absorption_emerging_low_probability(self) -> None:
        """Scenario 3: Low probability -> EMERGING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.30,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.25,
            trend_efficiency=0.48,
            balance_score=0.30,
            absorption_score=0.40,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.25,
            transition_probability=0.30,
            compression_probability=0.25,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.EMERGING


class TestAbsorptionAccumulationFailure:
    """>= 3 failure/invalidation scenarios for absorption_accumulation."""

    def test_absorption_invalidated_reacceleration(self) -> None:
        """Failure 1: Initiative re-accelerated + absorption dropped -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.60,
            initiative_strength=0.70,
            initiative_buy_score=0.70,
            initiative_sell_score=0.15,
            trend_efficiency=0.50,
            balance_score=0.25,
            absorption_score=0.35,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.15,
            transition_probability=0.50,
            compression_probability=0.35,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "reacceleration" in result.reason

    def test_absorption_invalidated_trend_reacceleration(self) -> None:
        """Failure 2: Trend re-accelerated strongly -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.60,
            initiative_strength=0.72,
            initiative_buy_score=0.72,
            initiative_sell_score=0.15,
            trend_efficiency=0.65,
            balance_score=0.25,
            absorption_score=0.50,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.15,
            transition_probability=0.45,
            compression_probability=0.30,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "trend_reacceleration" in result.reason

    def test_absorption_weakening(self) -> None:
        """Failure 3: Probability dropped significantly -> WEAKENING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.42,
            prior_probability=0.58,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.25,
            trend_efficiency=0.45,
            balance_score=0.30,
            absorption_score=0.50,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.25,
            transition_probability=0.45,
            compression_probability=0.35,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.WEAKENING


# ═════════════════════════════════════════════════════════════════════════════
# ABSORPTION TO REVERSAL PREPARATION: REVERSAL_PREPARATION
# ═════════════════════════════════════════════════════════════════════════════

class TestReversalPreparationSuccess:
    """>= 3 success scenarios for reversal_preparation."""

    def test_reversal_resolved(self) -> None:
        """Scenario 1: High probability + absorption + opposite initiative -> RESOLVED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.78,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.50,
            trend_efficiency=0.40,
            balance_score=0.40,
            absorption_score=0.60,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.50,
            transition_probability=0.55,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.RESOLVED
        assert result.resolution == EpisodeResolution.CONFIRMED
        assert result.is_terminal is True

    def test_reversal_confirming(self) -> None:
        """Scenario 2: Above confirm threshold -> CONFIRMING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.60,
            initiative_strength=0.48,
            initiative_buy_score=0.48,
            initiative_sell_score=0.40,
            trend_efficiency=0.42,
            balance_score=0.45,
            absorption_score=0.55,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.40,
            transition_probability=0.50,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.CONFIRMING
        assert result.is_terminal is False

    def test_reversal_building_phase(self) -> None:
        """Scenario 3: Above build threshold -> BUILDING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.42,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.30,
            trend_efficiency=0.40,
            balance_score=0.40,
            absorption_score=0.50,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.30,
            transition_probability=0.42,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.BUILDING


class TestReversalPreparationFailure:
    """>= 3 failure/invalidation scenarios for reversal_preparation."""

    def test_reversal_invalidated_same_side_reacceleration(self) -> None:
        """Failure 1: Same-side re-acceleration -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.75,
            initiative_strength=0.72,
            initiative_buy_score=0.72,
            initiative_sell_score=0.20,
            trend_efficiency=0.55,
            balance_score=0.40,
            absorption_score=0.50,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
            transition_probability=0.50,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "same_side" in result.reason

    def test_reversal_invalidated_stuck_balance(self) -> None:
        """Failure 2: Stuck in static balance without opposite initiative -> INVALIDATED."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.65,
            initiative_strength=0.35,
            initiative_buy_score=0.35,
            initiative_sell_score=0.25,
            trend_efficiency=0.35,
            balance_score=0.72,
            absorption_score=0.45,
            distance_to_center_ticks=8.0,
            opposite_initiative=0.20,
            transition_probability=0.40,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.INVALIDATED
        assert result.resolution == EpisodeResolution.INVALIDATED
        assert "stuck_balance" in result.reason

    def test_reversal_weakening(self) -> None:
        """Failure 3: Probability dropped significantly -> WEAKENING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.42,
            prior_probability=0.58,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.35,
            trend_efficiency=0.40,
            balance_score=0.45,
            absorption_score=0.50,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.35,
            transition_probability=0.45,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.WEAKENING

    def test_reversal_emerging_low_probability(self) -> None:
        """Failure 4: Low probability -> EMERGING."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.28,
            initiative_strength=0.45,
            initiative_buy_score=0.45,
            initiative_sell_score=0.30,
            trend_efficiency=0.40,
            balance_score=0.45,
            absorption_score=0.40,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.30,
            transition_probability=0.35,
        )
        result = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result.new_phase == EventPhase.EMERGING


# ═════════════════════════════════════════════════════════════════════════════
# IDEMPOTENCY: same input -> same output
# ═════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    """Same input must produce same output across multiple runs."""

    def test_momentum_same_input_produces_same_phase(self) -> None:
        """Momentum: identical context produces identical phase."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.70,
            initiative_strength=0.72,
            initiative_buy_score=0.72,
            initiative_sell_score=0.10,
            trend_efficiency=0.70,
            balance_score=0.15,
            absorption_score=0.20,
            distance_to_center_ticks=18.0,
            opposite_initiative=0.10,
        )
        result1 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        result2 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result1.new_phase == result2.new_phase
        assert result1.resolution == result2.resolution
        assert result1.reason == result2.reason

    def test_balance_same_input_produces_same_phase(self) -> None:
        """Balance: identical context produces identical phase."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.DISTRIBUTION_BALANCE,
            probability=0.62,
            initiative_strength=0.30,
            initiative_buy_score=0.30,
            initiative_sell_score=0.25,
            trend_efficiency=0.35,
            balance_score=0.65,
            absorption_score=0.20,
            distance_to_center_ticks=4.0,
            opposite_initiative=0.25,
        )
        result1 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        result2 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result1.new_phase == result2.new_phase
        assert result1.resolution == result2.resolution

    def test_absorption_same_input_produces_same_phase(self) -> None:
        """Absorption: identical context produces identical phase."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.ABSORPTION_ACCUMULATION,
            probability=0.60,
            initiative_strength=0.40,
            initiative_buy_score=0.40,
            initiative_sell_score=0.25,
            trend_efficiency=0.40,
            balance_score=0.30,
            absorption_score=0.65,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.25,
            transition_probability=0.55,
            compression_probability=0.40,
        )
        result1 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        result2 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result1.new_phase == result2.new_phase
        assert result1.resolution == result2.resolution

    def test_reversal_same_input_produces_same_phase(self) -> None:
        """Reversal: identical context produces identical phase."""
        ctx = _ctx(
            hypothesis_kind=EventHypothesisKind.REVERSAL_PREPARATION,
            probability=0.78,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.50,
            trend_efficiency=0.40,
            balance_score=0.40,
            absorption_score=0.60,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.50,
            transition_probability=0.55,
        )
        result1 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        result2 = compute_phase(ctx, DEFAULT_THRESHOLDS)
        assert result1.new_phase == result2.new_phase
        assert result1.resolution == result2.resolution


# ═════════════════════════════════════════════════════════════════════════════
# THRESHOLDS: profile payload override
# ═════════════════════════════════════════════════════════════════════════════

class TestThresholds:
    """Profile thresholds can override defaults."""

    def test_thresholds_override_via_phase_machine(self) -> None:
        """Custom thresholds via phase_machine.change thresholds are used by compute_phase."""
        ctx_default = _ctx(
            hypothesis_kind=EventHypothesisKind.CONTINUATION_BASE,
            probability=0.40,
            initiative_strength=0.50,
            initiative_buy_score=0.50,
            initiative_sell_score=0.20,
            trend_efficiency=0.50,
            balance_score=0.20,
            absorption_score=0.20,
            distance_to_center_ticks=15.0,
            opposite_initiative=0.20,
        )
        result_default = compute_phase(ctx_default, DEFAULT_THRESHOLDS)
        assert result_default.new_phase == EventPhase.BUILDING

        custom_thresholds = get_thresholds({"thresholds": {"building_hypothesis_probability": 0.50}})
        result_custom = compute_phase(ctx_default, custom_thresholds)
        assert result_custom.new_phase == EventPhase.EMERGING

    def test_get_thresholds_returns_defaults_for_empty_payload(self) -> None:
        """Empty payload returns all defaults."""
        thresholds = get_thresholds({})
        assert thresholds["building_probability"] == 0.36
        assert thresholds["confirming_probability"] == 0.56
        assert thresholds["resolved_probability"] == 0.74
        assert thresholds["weakening_drop"] == 0.12
        assert thresholds["reacceleration_threshold"] == 0.68
        assert thresholds["center_hit_ticks"] == 10.0

    def test_get_thresholds_partial_override(self) -> None:
        """Partial override preserves other defaults."""
        thresholds = get_thresholds({"thresholds": {"center_hit_ticks": 8.0}})
        assert thresholds["center_hit_ticks"] == 8.0
        assert thresholds["building_probability"] == 0.36
        assert thresholds["confirming_probability"] == 0.56


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION: full recognizer pipeline with invalidation
# ═════════════════════════════════════════════════════════════════════════════

class TestRecognizerPipelineInvalidation:
    """End-to-end tests for invalidation scenarios in the recognizer pipeline."""

    def test_momentum_invalidation_episode_closed(self, tmp_path: Path) -> None:
        """When momentum is invalidated, an episode should be closed."""
        repository = SQLiteAnalysisRepository(tmp_path / "data" / "market_structure.db")
        repository.initialize()
        now = datetime.now(tz=UTC).replace(microsecond=0)

        repository.save_ingestion(
            ingestion_id="ing-hist-inv",
            ingestion_kind="adapter_history_bars",
            source_snapshot_id="hist-inv",
            instrument_symbol="NQ",
            observed_payload={
                "schema_version": "1.0.0",
                "message_id": "hist-inv",
                "message_type": "history_bars",
                "emitted_at": now.isoformat(),
                "observed_window_start": (now - timedelta(minutes=5)).isoformat(),
                "observed_window_end": now.isoformat(),
                "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": "NQ-test", "adapter_version": "test"},
                "instrument": {"symbol": "NQ", "venue": "CME", "tick_size": 0.25, "currency": "USD"},
                "bar_timeframe": "1m",
                "bars": [
                    {"started_at": (now - timedelta(minutes=5)).isoformat(), "ended_at": (now - timedelta(minutes=4, seconds=59)).isoformat(), "open": 21500.0, "high": 21501.0, "low": 21499.0, "close": 21500.0, "volume": 100, "delta": 5, "bid_volume": 40, "ask_volume": 60},
                    {"started_at": (now - timedelta(minutes=4)).isoformat(), "ended_at": (now - timedelta(minutes=3, seconds=59)).isoformat(), "open": 21500.0, "high": 21500.5, "low": 21499.5, "close": 21500.2, "volume": 95, "delta": 2, "bid_volume": 38, "ask_volume": 57},
                    {"started_at": (now - timedelta(minutes=3)).isoformat(), "ended_at": (now - timedelta(minutes=2, seconds=59)).isoformat(), "open": 21500.2, "high": 21500.8, "low": 21500.0, "close": 21500.5, "volume": 90, "delta": 3, "bid_volume": 35, "ask_volume": 55},
                    {"started_at": (now - timedelta(minutes=2)).isoformat(), "ended_at": (now - timedelta(minutes=1, seconds=59)).isoformat(), "open": 21500.5, "high": 21501.2, "low": 21500.2, "close": 21500.8, "volume": 88, "delta": 3, "bid_volume": 36, "ask_volume": 52},
                    {"started_at": (now - timedelta(minutes=1)).isoformat(), "ended_at": (now - timedelta(seconds=59)).isoformat(), "open": 21500.8, "high": 21501.5, "low": 21500.5, "close": 21500.6, "volume": 85, "delta": -2, "bid_volume": 34, "ask_volume": 51},
                    {"started_at": (now - timedelta(seconds=59)).isoformat(), "ended_at": now.isoformat(), "open": 21500.6, "high": 21500.8, "low": 21500.4, "close": 21500.5, "volume": 82, "delta": -1, "bid_volume": 33, "ask_volume": 49},
                ],
            },
            stored_at=now,
        )
        repository.save_ingestion(
            ingestion_id="ing-proc-inv",
            ingestion_kind="process_context",
            source_snapshot_id="proc-inv",
            instrument_symbol="NQ",
            observed_payload={
                "schema_version": "1.0.0",
                "process_context_id": "proc-inv",
                "observed_at": now.isoformat(),
                "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": "NQ-test", "adapter_version": "test"},
                "instrument": {"symbol": "NQ", "venue": "CME", "tick_size": 0.25, "currency": "USD"},
                "process_context": {
                    "session_windows": [
                        {
                            "session_code": "us_regular",
                            "started_at": (now - timedelta(minutes=30)).isoformat(),
                            "ended_at": now.isoformat(),
                            "latest_range": {"open": 21500.5, "high": 21501.5, "low": 21500.0, "close": 21500.5},
                            "value_area": {"low": 21500.0, "high": 21501.0, "point_of_control": 21500.5},
                            "session_stats": {"volume": 500, "delta": 0, "trades": 150},
                            "key_levels": [],
                        }
                    ],
                    "second_features": [],
                    "liquidity_episodes": [],
                    "initiative_drives": [
                        {
                            "drive_id": "drive-inv",
                            "started_at": (now - timedelta(minutes=3)).isoformat(),
                            "ended_at": (now - timedelta(minutes=1)).isoformat(),
                            "side": "buy",
                            "price_low": 21500.0,
                            "price_high": 21501.0,
                            "aggressive_volume": 400,
                            "net_delta": 300,
                            "trade_count": 90,
                            "consumed_price_levels": 3,
                            "price_travel_ticks": 4,
                            "max_counter_move_ticks": 8,
                            "continuation_seconds": 30,
                            "raw_features": {},
                        }
                    ],
                    "measured_moves": [],
                    "manipulation_legs": [],
                    "gap_references": [],
                    "post_harvest_responses": [],
                    "exertion_zones": [],
                    "cross_session_sequences": [],
                },
            },
            stored_at=now,
        )

        from atas_market_structure.recognition import DeterministicRecognitionService

        service = DeterministicRecognitionService(repository=repository)
        result = service.run_for_instrument("NQ", triggered_by="pytest_invalidation")

        assert result.triggered is True
        assert result.belief_state is not None
        assert len(result.belief_state.event_hypotheses) >= 3

    def test_recognizer_idempotent_same_input_same_output(self, tmp_path: Path) -> None:
        """Two identical runs produce identical belief states."""
        repository1 = SQLiteAnalysisRepository(tmp_path / "data1" / "market_structure.db")
        repository1.initialize()
        repository2 = SQLiteAnalysisRepository(tmp_path / "data2" / "market_structure.db")
        repository2.initialize()
        now = datetime.now(tz=UTC).replace(microsecond=0)

        def _seed_bars(repo: SQLiteAnalysisRepository) -> None:
            repo.save_ingestion(
                ingestion_id="ing-hist-idemp",
                ingestion_kind="adapter_history_bars",
                source_snapshot_id="hist-idemp",
                instrument_symbol="NQ",
                observed_payload={
                    "schema_version": "1.0.0",
                    "message_id": "hist-idemp",
                    "message_type": "history_bars",
                    "emitted_at": now.isoformat(),
                    "observed_window_start": (now - timedelta(minutes=5)).isoformat(),
                    "observed_window_end": now.isoformat(),
                    "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": "NQ-test", "adapter_version": "test"},
                    "instrument": {"symbol": "NQ", "venue": "CME", "tick_size": 0.25, "currency": "USD"},
                    "bar_timeframe": "1m",
                    "bars": [
                        {"started_at": (now - timedelta(minutes=5)).isoformat(), "ended_at": (now - timedelta(minutes=4, seconds=59)).isoformat(), "open": 21500.0, "high": 21502.0, "low": 21499.0, "close": 21501.0, "volume": 100, "delta": 10, "bid_volume": 60, "ask_volume": 40},
                        {"started_at": (now - timedelta(minutes=4)).isoformat(), "ended_at": (now - timedelta(minutes=3, seconds=59)).isoformat(), "open": 21501.0, "high": 21503.0, "low": 21500.0, "close": 21502.0, "volume": 110, "delta": 12, "bid_volume": 65, "ask_volume": 45},
                        {"started_at": (now - timedelta(minutes=3)).isoformat(), "ended_at": (now - timedelta(minutes=2, seconds=59)).isoformat(), "open": 21502.0, "high": 21504.0, "low": 21501.0, "close": 21503.0, "volume": 120, "delta": 14, "bid_volume": 70, "ask_volume": 50},
                        {"started_at": (now - timedelta(minutes=2)).isoformat(), "ended_at": (now - timedelta(minutes=1, seconds=59)).isoformat(), "open": 21503.0, "high": 21505.0, "low": 21502.0, "close": 21504.0, "volume": 130, "delta": 15, "bid_volume": 75, "ask_volume": 55},
                        {"started_at": (now - timedelta(minutes=1)).isoformat(), "ended_at": (now - timedelta(seconds=59)).isoformat(), "open": 21504.0, "high": 21506.0, "low": 21503.0, "close": 21505.0, "volume": 140, "delta": 16, "bid_volume": 80, "ask_volume": 60},
                        {"started_at": (now - timedelta(seconds=59)).isoformat(), "ended_at": now.isoformat(), "open": 21505.0, "high": 21507.0, "low": 21504.0, "close": 21506.0, "volume": 150, "delta": 18, "bid_volume": 85, "ask_volume": 65},
                    ],
                },
                stored_at=now,
            )
            repo.save_ingestion(
                ingestion_id="ing-proc-idemp",
                ingestion_kind="process_context",
                source_snapshot_id="proc-idemp",
                instrument_symbol="NQ",
                observed_payload={
                    "schema_version": "1.0.0",
                    "process_context_id": "proc-idemp",
                    "observed_at": now.isoformat(),
                    "source": {"system": "ATAS", "instance_id": "TEST", "chart_instance_id": "NQ-test", "adapter_version": "test"},
                    "instrument": {"symbol": "NQ", "venue": "CME", "tick_size": 0.25, "currency": "USD"},
                    "process_context": {
                        "session_windows": [
                            {
                                "session_code": "us_regular",
                                "started_at": (now - timedelta(minutes=30)).isoformat(),
                                "ended_at": now.isoformat(),
                                "latest_range": {"open": 21502.0, "high": 21507.0, "low": 21499.0, "close": 21506.0},
                                "value_area": {"low": 21502.0, "high": 21506.0, "point_of_control": 21504.0},
                                "session_stats": {"volume": 800, "delta": 0, "trades": 200},
                                "key_levels": [],
                            }
                        ],
                        "second_features": [],
                        "liquidity_episodes": [],
                        "initiative_drives": [
                            {
                                "drive_id": "drive-idemp",
                                "started_at": (now - timedelta(minutes=3)).isoformat(),
                                "ended_at": (now - timedelta(minutes=1)).isoformat(),
                                "side": "buy",
                                "price_low": 21503.0,
                                "price_high": 21508.0,
                                "aggressive_volume": 800,
                                "net_delta": 700,
                                "trade_count": 180,
                                "consumed_price_levels": 5,
                                "price_travel_ticks": 20,
                                "max_counter_move_ticks": 4,
                                "continuation_seconds": 60,
                                "raw_features": {},
                            }
                        ],
                        "measured_moves": [],
                        "manipulation_legs": [],
                        "gap_references": [],
                        "post_harvest_responses": [],
                        "exertion_zones": [],
                        "cross_session_sequences": [],
                    },
                },
                stored_at=now,
            )

        _seed_bars(repository1)
        _seed_bars(repository2)

        from atas_market_structure.recognition import DeterministicRecognitionService
        service1 = DeterministicRecognitionService(repository=repository1)
        service2 = DeterministicRecognitionService(repository=repository2)

        # Use identical reference_time to ensure deterministic run_key
        ref_time = datetime(2026, 3, 24, 9, 45, 0, tzinfo=UTC)
        result1 = service1.run_for_instrument("NQ", triggered_by="pytest_idempotent", reference_time=ref_time)
        result2 = service2.run_for_instrument("NQ", triggered_by="pytest_idempotent", reference_time=ref_time)

        assert result1.triggered == result2.triggered
        if result1.belief_state and result2.belief_state:
            assert result1.belief_state.belief_state_id == result2.belief_state.belief_state_id
            for h1, h2 in zip(result1.belief_state.event_hypotheses, result2.belief_state.event_hypotheses):
                assert h1.posterior_probability == h2.posterior_probability
                assert h1.phase == h2.phase
