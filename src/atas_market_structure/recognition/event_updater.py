from __future__ import annotations

import hashlib
import math
from typing import Any

from atas_market_structure.models import (
    DegradedMode,
    EventHypothesisKind,
    EventHypothesisState,
    EventPhase,
    RegimeKind,
    RegimePosteriorRecord,
    TradableEventKind,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.recognition.types import RecognitionFeatureVector


class EventHypothesisUpdater:
    """Deterministic multi-hypothesis updater scoped to the V1 tradable events."""

    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def build(
        self,
        *,
        feature: RecognitionFeatureVector,
        regimes: list[RegimePosteriorRecord],
        anchors: list[Any],
        profile_payload: dict[str, Any],
        run_key: str | None = None,
    ) -> list[EventHypothesisState]:
        priors = profile_payload.get("priors") if isinstance(profile_payload.get("priors"), dict) else {}
        hypothesis_priors = priors.get("hypotheses") if isinstance(priors.get("hypotheses"), dict) else {}
        thresholds = profile_payload.get("thresholds") if isinstance(profile_payload.get("thresholds"), dict) else {}
        metrics = feature.metrics
        regime_map = {item.regime: item.probability for item in regimes}
        anchor_support = max((item.influence or 0.0 for item in anchors), default=0.0)
        data_status = feature.context_payloads.get("data_status", {})
        stale_macro = False
        if isinstance(data_status, dict):
            stale_macro = any(
                mode in {DegradedMode.STALE_MACRO.value, "stale_macro"}
                for mode in (data_status.get("degraded_modes") or [])
            )

        strong_trend = regime_map.get(RegimeKind.STRONG_MOMENTUM_TREND, 0.0)
        weak_trend = regime_map.get(RegimeKind.WEAK_MOMENTUM_TREND_NARROW, 0.0) + regime_map.get(RegimeKind.WEAK_MOMENTUM_TREND_WIDE, 0.0)
        balance_regime = regime_map.get(RegimeKind.BALANCE_MEAN_REVERSION, 0.0)
        compression = regime_map.get(RegimeKind.COMPRESSION, 0.0)
        transition = regime_map.get(RegimeKind.TRANSITION_EXHAUSTION, 0.0)
        initiative_buy = metrics.get("initiative_buy_score", 0.0)
        initiative_sell = metrics.get("initiative_sell_score", 0.0)
        initiative_strength = max(initiative_buy, initiative_sell)
        opposite_initiative = min(initiative_buy, initiative_sell)
        trend_efficiency = metrics.get("trend_efficiency", 0.0)
        balance_score = metrics.get("balance_score", 0.0)
        absorption = metrics.get("absorption_score", 0.0)
        path_score = metrics.get("path_dependency_score", 0.0)
        direction = metrics.get("current_direction", 0.0)
        distance_to_center = metrics.get("distance_to_balance_center_ticks", 999.0)
        center_hit_ticks = float(thresholds.get("center_hit_ticks") or 10.0)
        reacceleration_threshold = float(thresholds.get("initiative_reacceleration_score") or 0.68)
        build_threshold = float(thresholds.get("building_hypothesis_probability") or 0.36)
        confirm_threshold = float(thresholds.get("confirming_hypothesis_probability") or 0.56)
        resolve_threshold = float(thresholds.get("resolved_hypothesis_probability") or 0.74)
        weakening_drop = float(thresholds.get("weakening_drop_threshold") or 0.12)

        raw_scores = {
            EventHypothesisKind.CONTINUATION_BASE: _prior(hypothesis_priors, "continuation_base")
            + (0.55 * strong_trend)
            + (0.45 * weak_trend)
            + (0.85 * trend_efficiency)
            + (0.70 * initiative_strength)
            + (0.25 * path_score)
            - (0.80 * balance_score)
            - (0.70 * absorption),
            EventHypothesisKind.DISTRIBUTION_BALANCE: _prior(hypothesis_priors, "distribution_balance")
            + (0.70 * balance_regime)
            + (0.35 * compression)
            + (0.75 * balance_score)
            + (0.25 * anchor_support)
            + (0.20 * path_score)
            - (0.65 * initiative_strength),
            EventHypothesisKind.ABSORPTION_ACCUMULATION: _prior(hypothesis_priors, "absorption_accumulation")
            + (0.65 * transition)
            + (0.35 * compression)
            + (0.90 * absorption)
            + (0.30 * anchor_support)
            + (0.25 * path_score)
            - (0.35 * trend_efficiency),
            EventHypothesisKind.REVERSAL_PREPARATION: _prior(hypothesis_priors, "reversal_preparation")
            + (0.60 * transition)
            + (0.30 * compression)
            + (0.60 * absorption)
            + (0.40 * opposite_initiative)
            + (0.32 * anchor_support)
            + (0.25 * path_score)
            - (0.55 * initiative_strength)
            - (0.20 * _same_side_direction(direction, initiative_buy, initiative_sell)),
        }
        probabilities = _softmax(raw_scores)
        if stale_macro:
            probabilities = _flatten(probabilities, 0.12)

        previous = self._load_previous_states(feature.instrument_symbol)
        ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        states: list[EventHypothesisState] = []
        for kind, probability in ordered:
            prior_state = previous.get(kind)
            support, missing, invalidating = _evidence_lists(
                kind=kind,
                trend_efficiency=trend_efficiency,
                balance_score=balance_score,
                absorption=absorption,
                initiative_strength=initiative_strength,
                direction=direction,
                distance_to_center=distance_to_center,
                center_hit_ticks=center_hit_ticks,
                anchor_support=anchor_support,
                opposite_initiative=opposite_initiative,
            )
            phase = _phase_for(
                kind=kind,
                probability=probability,
                build_threshold=build_threshold,
                confirm_threshold=confirm_threshold,
                resolve_threshold=resolve_threshold,
                prior_probability=prior_state.posterior_probability if prior_state is not None else None,
                weakening_drop=weakening_drop,
                initiative_strength=initiative_strength,
                balance_score=balance_score,
                absorption=absorption,
                distance_to_center=distance_to_center,
                center_hit_ticks=center_hit_ticks,
                reacceleration_threshold=reacceleration_threshold,
                opposite_initiative=opposite_initiative,
            )
            mapped_event = _mapped_event(kind)
            stability = 1.0
            if prior_state is not None:
                stability = _clamp(1.0 - (abs(probability - prior_state.posterior_probability) / 0.5))
            transition_watch = _transition_watch(kind, ordered)
            states.append(
                EventHypothesisState(
                    hypothesis_id=_hypothesis_id(
                        feature.instrument_symbol,
                        kind,
                        feature.market_time,
                        feature.source_observation_table,
                        feature.source_observation_id,
                        run_key=run_key,
                    ),
                    hypothesis_kind=kind,
                    mapped_event_kind=mapped_event,
                    phase=phase,
                    posterior_probability=round(probability, 6),
                    supporting_evidence=support,
                    missing_confirmation=missing,
                    invalidating_signals=invalidating,
                    transition_watch=transition_watch,
                    data_quality_score=_clamp(float(data_status.get("feature_completeness", 0.0))),
                    evidence_density_score=_clamp(len(support) / 6.0),
                    model_stability_score=round(stability, 4),
                    anchor_dependence_score=round(anchor_support, 4),
                ),
            )
        return states

    def _load_previous_states(self, instrument_symbol: str) -> dict[EventHypothesisKind, EventHypothesisState]:
        stored_rows = self._repository.list_event_hypothesis_states(instrument_symbol=instrument_symbol, limit=32)
        previous: dict[EventHypothesisKind, EventHypothesisState] = {}
        for row in stored_rows:
            kind = EventHypothesisKind(row.hypothesis_kind)
            if kind in previous:
                continue
            previous[kind] = EventHypothesisState.model_validate(row.hypothesis_payload)
        return previous


def _mapped_event(kind: EventHypothesisKind) -> TradableEventKind:
    if kind is EventHypothesisKind.CONTINUATION_BASE:
        return TradableEventKind.MOMENTUM_CONTINUATION
    if kind is EventHypothesisKind.DISTRIBUTION_BALANCE:
        return TradableEventKind.BALANCE_MEAN_REVERSION
    return TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION


def _evidence_lists(
    *,
    kind: EventHypothesisKind,
    trend_efficiency: float,
    balance_score: float,
    absorption: float,
    initiative_strength: float,
    direction: float,
    distance_to_center: float,
    center_hit_ticks: float,
    anchor_support: float,
    opposite_initiative: float,
) -> tuple[list[str], list[str], list[str]]:
    if kind is EventHypothesisKind.CONTINUATION_BASE:
        return (
            _compact(
                "trend_efficiency_support" if trend_efficiency >= 0.55 else "",
                "initiative_relaunch_present" if initiative_strength >= 0.60 else "",
                "no_deep_return_to_center" if distance_to_center > center_hit_ticks else "",
                "path_still_directional" if abs(direction) >= 0.30 else "",
            ),
            _compact("fresh_push_needed", "acceptance_after_pullback", "avoid_return_to_old_balance"),
            _compact(
                "returned_to_balance_center" if distance_to_center <= center_hit_ticks else "",
                "opposite_initiative_displacement" if opposite_initiative >= 0.45 else "",
                "absorption_against_trend" if absorption >= 0.55 else "",
            ),
        )
    if kind is EventHypothesisKind.DISTRIBUTION_BALANCE:
        return (
            _compact(
                "balance_center_defined" if distance_to_center < 999 else "",
                "overlap_and_rotation" if balance_score >= 0.55 else "",
                "initiative_weakened" if initiative_strength <= 0.60 else "",
                "anchor_as_center_magnet" if anchor_support >= 0.25 else "",
            ),
            _compact("continued_return_to_center", "avoid_fresh_single_sided_acceptance"),
            _compact(
                "fresh_initiative_breakout" if initiative_strength >= 0.70 else "",
                "acceptance_away_from_center" if distance_to_center > center_hit_ticks * 3 else "",
            ),
        )
    if kind is EventHypothesisKind.ABSORPTION_ACCUMULATION:
        return (
            _compact(
                "repeated_absorption" if absorption >= 0.55 else "",
                "trend_efficiency_fading" if trend_efficiency <= 0.50 else "",
                "anchor_proximity_support" if anchor_support >= 0.25 else "",
            ),
            _compact("need_sustained_hold", "need_opposite_initiative_hint"),
            _compact("trend_reaccelerated" if initiative_strength >= 0.70 and trend_efficiency >= 0.60 else ""),
        )
    return (
        _compact(
            "absorption_established" if absorption >= 0.50 else "",
            "opposite_initiative_emerging" if opposite_initiative >= 0.30 else "",
            "transition_regime_support" if anchor_support >= 0.25 or balance_score >= 0.45 else "",
        ),
        _compact("need_clear_opposite_push", "need_follow_through_away_from_edge"),
        _compact(
            "same_side_reacceleration" if initiative_strength >= 0.72 and abs(direction) >= 0.35 else "",
            "stuck_in_static_balance" if balance_score >= 0.70 and opposite_initiative < 0.25 else "",
        ),
    )


def _phase_for(
    *,
    kind: EventHypothesisKind,
    probability: float,
    build_threshold: float,
    confirm_threshold: float,
    resolve_threshold: float,
    prior_probability: float | None,
    weakening_drop: float,
    initiative_strength: float,
    balance_score: float,
    absorption: float,
    distance_to_center: float,
    center_hit_ticks: float,
    reacceleration_threshold: float,
    opposite_initiative: float,
) -> EventPhase:
    if kind is EventHypothesisKind.CONTINUATION_BASE:
        if initiative_strength >= reacceleration_threshold and probability >= resolve_threshold and distance_to_center > center_hit_ticks:
            return EventPhase.RESOLVED
        if distance_to_center <= center_hit_ticks or (absorption >= 0.55 and opposite_initiative >= 0.30):
            return EventPhase.INVALIDATED
    if kind is EventHypothesisKind.DISTRIBUTION_BALANCE:
        if distance_to_center <= center_hit_ticks and probability >= confirm_threshold:
            return EventPhase.RESOLVED
        if initiative_strength >= reacceleration_threshold and distance_to_center > center_hit_ticks * 2:
            return EventPhase.INVALIDATED
    if kind is EventHypothesisKind.ABSORPTION_ACCUMULATION:
        if initiative_strength >= reacceleration_threshold and absorption < 0.45:
            return EventPhase.INVALIDATED
    if kind is EventHypothesisKind.REVERSAL_PREPARATION:
        if probability >= resolve_threshold and absorption >= 0.55 and opposite_initiative >= 0.30:
            return EventPhase.RESOLVED
        if initiative_strength >= reacceleration_threshold and balance_score < 0.65:
            return EventPhase.INVALIDATED

    if prior_probability is not None and prior_probability - probability >= weakening_drop and probability >= build_threshold:
        return EventPhase.WEAKENING
    if probability >= confirm_threshold:
        return EventPhase.CONFIRMING
    if probability >= build_threshold:
        return EventPhase.BUILDING
    return EventPhase.EMERGING


def _transition_watch(kind: EventHypothesisKind, ordered: list[tuple[EventHypothesisKind, float]]) -> list[str]:
    competitors = [item for item, _ in ordered if item is not kind][:2]
    return [f"watch_{item.value}" for item in competitors]


def _prior(priors: dict[str, Any], key: str) -> float:
    value = priors.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.25


def _softmax(scores: dict[EventHypothesisKind, float]) -> dict[EventHypothesisKind, float]:
    max_score = max(scores.values()) if scores else 0.0
    scaled = {key: math.exp(value - max_score) for key, value in scores.items()}
    total = sum(scaled.values()) or 1.0
    return {key: value / total for key, value in scaled.items()}


def _flatten(probabilities: dict[EventHypothesisKind, float], blend: float) -> dict[EventHypothesisKind, float]:
    uniform = 1.0 / max(1, len(probabilities))
    return {key: ((1.0 - blend) * value) + (blend * uniform) for key, value in probabilities.items()}


def _hypothesis_id(
    instrument_symbol: str,
    kind: EventHypothesisKind,
    market_time,
    source_observation_table: str,
    source_observation_id: str,
    *,
    run_key: str | None = None,
) -> str:
    material = "|".join(
        (
            instrument_symbol,
            kind.value,
            market_time.isoformat(),
            source_observation_table,
            source_observation_id,
            run_key or "",
        ),
    )
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:12]
    return f"hyp-{instrument_symbol.lower()}-{kind.value}-{digest}"


def _compact(*values: str) -> list[str]:
    return [item for item in values if item]


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _same_side_direction(direction: float, initiative_buy: float, initiative_sell: float) -> float:
    if initiative_buy >= initiative_sell:
        return max(0.0, direction)
    return max(0.0, -direction)
