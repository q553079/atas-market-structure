from __future__ import annotations

import math
from typing import Any

from atas_market_structure.models import DegradedMode, RegimeKind, RegimePosteriorRecord
from atas_market_structure.recognition.types import RecognitionFeatureVector


class RegimeUpdater:
    """Deterministic regime posterior updater for the fixed V1 ontology."""

    def build(
        self,
        *,
        feature: RecognitionFeatureVector,
        profile_payload: dict[str, Any],
    ) -> list[RegimePosteriorRecord]:
        metrics = feature.metrics
        priors = profile_payload.get("priors") if isinstance(profile_payload.get("priors"), dict) else {}
        regime_priors = priors.get("regimes") if isinstance(priors.get("regimes"), dict) else {}
        direction_abs = abs(metrics.get("current_direction", 0.0))
        initiative = max(metrics.get("initiative_buy_score", 0.0), metrics.get("initiative_sell_score", 0.0))
        trend_efficiency = metrics.get("trend_efficiency", 0.0)
        balance_score = metrics.get("balance_score", 0.0)
        compression_score = metrics.get("compression_score", 0.0)
        absorption_score = metrics.get("absorption_score", 0.0)
        range_expansion = metrics.get("range_expansion_score", 0.0)
        anchor_score = metrics.get("anchor_interaction_score", 0.0)
        path_score = metrics.get("path_dependency_score", 0.0)
        evidence = feature.evidence_buckets

        raw_scores = {
            RegimeKind.STRONG_MOMENTUM_TREND: _prior(regime_priors, RegimeKind.STRONG_MOMENTUM_TREND)
            + (1.20 * trend_efficiency)
            + (0.90 * initiative)
            + (0.55 * range_expansion)
            - (0.75 * balance_score)
            - (0.35 * absorption_score),
            RegimeKind.WEAK_MOMENTUM_TREND_NARROW: _prior(regime_priors, RegimeKind.WEAK_MOMENTUM_TREND_NARROW)
            + (0.80 * trend_efficiency)
            + (0.55 * initiative)
            + (0.45 * compression_score)
            + (0.20 * direction_abs)
            - (0.45 * balance_score),
            RegimeKind.WEAK_MOMENTUM_TREND_WIDE: _prior(regime_priors, RegimeKind.WEAK_MOMENTUM_TREND_WIDE)
            + (0.78 * trend_efficiency)
            + (0.62 * initiative)
            + (0.60 * range_expansion)
            + (0.22 * direction_abs)
            - (0.40 * balance_score),
            RegimeKind.BALANCE_MEAN_REVERSION: _prior(regime_priors, RegimeKind.BALANCE_MEAN_REVERSION)
            + (1.10 * balance_score)
            + (0.50 * (1.0 - trend_efficiency))
            + (0.30 * anchor_score)
            - (0.65 * initiative),
            RegimeKind.COMPRESSION: _prior(regime_priors, RegimeKind.COMPRESSION)
            + (1.00 * compression_score)
            + (0.45 * balance_score)
            - (0.42 * initiative)
            - (0.30 * range_expansion),
            RegimeKind.TRANSITION_EXHAUSTION: _prior(regime_priors, RegimeKind.TRANSITION_EXHAUSTION)
            + (0.95 * absorption_score)
            + (0.52 * (1.0 - trend_efficiency))
            + (0.42 * path_score)
            + (0.25 * anchor_score)
            - (0.30 * initiative),
        }
        probabilities = _softmax(raw_scores)
        degraded = feature.context_payloads.get("data_status", {})
        degraded_modes = degraded.get("degraded_modes") if isinstance(degraded, dict) else []
        if "stale_macro" in degraded_modes:
            probabilities = _flatten(probabilities, 0.15)
        if "replay_rebuild" in degraded_modes:
            probabilities = _flatten(probabilities, 0.22)

        records = []
        for regime, probability in sorted(probabilities.items(), key=lambda item: item[1], reverse=True):
            bucket_names = _top_bucket_names(evidence, regime=regime)
            records.append(
                RegimePosteriorRecord(
                    regime=regime,
                    probability=round(probability, 6),
                    evidence=bucket_names,
                ),
            )
        return records


def _prior(priors: dict[str, Any], regime: RegimeKind) -> float:
    value = priors.get(regime.value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.16


def _softmax(scores: dict[RegimeKind, float]) -> dict[RegimeKind, float]:
    max_score = max(scores.values()) if scores else 0.0
    scaled = {key: math.exp(value - max_score) for key, value in scores.items()}
    total = sum(scaled.values()) or 1.0
    return {key: value / total for key, value in scaled.items()}


def _flatten(probabilities: dict[RegimeKind, float], blend: float) -> dict[RegimeKind, float]:
    uniform = 1.0 / max(1, len(probabilities))
    return {key: ((1.0 - blend) * value) + (blend * uniform) for key, value in probabilities.items()}


def _top_bucket_names(evidence: dict[str, Any], *, regime: RegimeKind) -> list[str]:
    scored = []
    for bucket in evidence.values():
        if not bucket.available:
            continue
        score = float(bucket.score) * float(bucket.weight)
        if regime in {RegimeKind.BALANCE_MEAN_REVERSION, RegimeKind.COMPRESSION} and bucket.name in {"balance", "anchor_interaction"}:
            score += 0.2
        if regime in {RegimeKind.STRONG_MOMENTUM_TREND, RegimeKind.WEAK_MOMENTUM_TREND_NARROW, RegimeKind.WEAK_MOMENTUM_TREND_WIDE} and bucket.name in {"initiative", "trend_efficiency"}:
            score += 0.2
        if regime is RegimeKind.TRANSITION_EXHAUSTION and bucket.name in {"absorption", "path_dependency"}:
            score += 0.2
        scored.append((score, bucket.name))
    scored.sort(reverse=True)
    return [name for _, name in scored[:3]]
