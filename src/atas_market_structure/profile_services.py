from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any
from uuid import uuid4

from atas_market_structure.models import (
    InstrumentProfile,
    InstrumentProfileParameterMetadata,
    ParameterCriticality,
    PatchValidationStatus,
    ProfilePatchCandidate,
    ProfilePatchFieldDiff,
    ProfilePatchPreview,
    ProfilePatchValidationIssue,
    ProfilePatchValidationResult,
    ProfileSuggestedChange,
    TradableEventKind,
)
from atas_market_structure.repository import AnalysisRepository


PROFILE_SCHEMA_VERSION = "instrument_profile_v1"
PROFILE_PATCH_CANDIDATE_SCHEMA_VERSION = "profile_patch_candidate_v1"
PATCH_VALIDATION_RESULT_SCHEMA_VERSION = "patch_validation_result_v1"

_DEFAULT_TICK_SIZES = {
    "ES": 0.25,
    "NQ": 0.25,
    "GC": 0.1,
    "CL": 0.01,
}

_GENERAL_EVENTS = [
    TradableEventKind.MOMENTUM_CONTINUATION,
    TradableEventKind.BALANCE_MEAN_REVERSION,
    TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION,
]
_MOMENTUM_EVENTS = [TradableEventKind.MOMENTUM_CONTINUATION]
_BALANCE_EVENTS = [TradableEventKind.BALANCE_MEAN_REVERSION]
_ABSORPTION_EVENTS = [TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION]
_REVERSAL_EVENTS = [TradableEventKind.ABSORPTION_TO_REVERSAL_PREPARATION]

_IMMUTABLE_PATCH_PATHS = {
    "instrument",
    "instrument_symbol",
    "profile_version",
    "schema_version",
    "ontology_version",
    "is_active",
    "created_at",
    "normalization.price_unit",
    "normalization.tick_size",
    "normalization.displacement_normalizer",
    "normalization.volume_normalizer",
    "safety.allow_ai_auto_apply",
    "safety.require_offline_validation",
}

_BASE_PROFILE_SEED: dict[str, Any] = {
    "normalization": {
        "price_unit": "ticks",
        "atr_window_bars": 20,
        "displacement_normalizer": "atr_fraction",
        "volume_normalizer": "rolling_quantile",
        "range_ticks_reference": 32.0,
        "anchor_active_distance_ticks": 48.0,
    },
    "time_windows": {
        "feature_lookback_bars": 20,
        "feature_lookback_minutes": 60,
        "momentum_continuation": {
            "strong": {"bars_min": 2, "bars_max": 6},
            "normal": {"bars_min": 3, "bars_max": 8},
        },
        "balance_mean_reversion": {"normal": {"bars_min": 4, "bars_max": 12}},
        "absorption_to_reversal_preparation": {"normal": {"bars_min": 3, "bars_max": 10}},
    },
    "thresholds": {
        "active_hypothesis_probability": 0.28,
        "building_hypothesis_probability": 0.36,
        "confirming_hypothesis_probability": 0.56,
        "resolved_hypothesis_probability": 0.74,
        "weakening_drop_threshold": 0.12,
        "momentum_efficiency_high": 0.58,
        "balance_score_high": 0.60,
        "compression_score_high": 0.62,
        "absorption_score_high": 0.56,
        "center_hit_ticks": 10.0,
        "anchor_near_ticks": 20.0,
        "initiative_reacceleration_score": 0.68,
        "initiative_push": {"displacement_zscore": 1.4, "efficiency_min": 0.58},
        "shallow_pullback": {"retrace_ratio_max": 0.38},
        "deep_pullback": {"retrace_ratio_min": 0.55},
        "balance_return_penalty_trigger": {"distance_to_balance_ticks": 8.0},
    },
    "weights": {
        "bar_structure": 1.0,
        "volatility_range": 0.8,
        "trend_efficiency": 1.0,
        "initiative": 1.0,
        "balance": 0.95,
        "absorption": 1.0,
        "depth_dom": 0.9,
        "anchor_interaction": 0.85,
        "path_dependency": 0.8,
    },
    "decay": {
        "stale_macro_penalty": 0.08,
        "missing_depth_penalty": 0.10,
        "missing_dom_penalty": 0.08,
        "anchor_freshness_hours": 72,
        "balance_center_half_life_bars": 120,
        "gap_edge_half_life_bars": 80,
        "initiative_origin_half_life_bars": 60,
    },
    "priors": {
        "regimes": {
            "strong_momentum_trend": 0.18,
            "weak_momentum_trend_narrow": 0.18,
            "weak_momentum_trend_wide": 0.14,
            "balance_mean_reversion": 0.20,
            "compression": 0.14,
            "transition_exhaustion": 0.16,
        },
        "hypotheses": {
            "continuation_base": 0.27,
            "distribution_balance": 0.24,
            "absorption_accumulation": 0.23,
            "reversal_preparation": 0.26,
        },
    },
    "safety": {
        "allow_ai_auto_apply": False,
        "require_offline_validation": True,
        "max_belief_regimes": 3,
        "max_belief_hypotheses": 3,
        "max_active_anchors": 3,
        "minimum_bar_count_for_primary_features": 3,
    },
}

_INSTRUMENT_OVERRIDES: dict[str, dict[str, Any]] = {
    "ES": {
        "normalization": {"range_ticks_reference": 24.0, "anchor_active_distance_ticks": 36.0},
        "time_windows": {
            "momentum_continuation": {
                "strong": {"bars_min": 2, "bars_max": 5},
                "normal": {"bars_min": 3, "bars_max": 7},
            },
            "balance_mean_reversion": {"normal": {"bars_min": 4, "bars_max": 10}},
            "absorption_to_reversal_preparation": {"normal": {"bars_min": 3, "bars_max": 9}},
        },
        "thresholds": {
            "momentum_efficiency_high": 0.60,
            "center_hit_ticks": 6.0,
            "anchor_near_ticks": 14.0,
            "initiative_push": {"displacement_zscore": 1.25},
            "balance_return_penalty_trigger": {"distance_to_balance_ticks": 6.0},
        },
        "weights": {"balance": 1.02, "depth_dom": 0.82, "anchor_interaction": 0.92},
        "decay": {"balance_center_half_life_bars": 144, "gap_edge_half_life_bars": 96},
        "priors": {
            "regimes": {"balance_mean_reversion": 0.24, "strong_momentum_trend": 0.16},
            "hypotheses": {"distribution_balance": 0.28, "continuation_base": 0.24},
        },
    },
    "NQ": {
        "normalization": {"range_ticks_reference": 32.0, "anchor_active_distance_ticks": 48.0},
        "weights": {"initiative": 1.05, "absorption": 1.05, "depth_dom": 0.88},
    },
    "GC": {
        "normalization": {"range_ticks_reference": 28.0, "anchor_active_distance_ticks": 42.0},
        "thresholds": {"center_hit_ticks": 7.0, "anchor_near_ticks": 16.0},
        "weights": {"absorption": 1.08, "anchor_interaction": 0.9},
    },
    "CL": {
        "normalization": {"range_ticks_reference": 40.0, "anchor_active_distance_ticks": 56.0},
        "thresholds": {"momentum_efficiency_high": 0.61, "center_hit_ticks": 6.0, "anchor_near_ticks": 18.0},
        "weights": {"volatility_range": 0.9, "path_dependency": 0.9, "depth_dom": 0.84},
        "decay": {"initiative_origin_half_life_bars": 72},
    },
}


def default_tick_size_for_symbol(instrument_symbol: str) -> float:
    """Return the fallback tick size used for instrument profile bootstrap."""

    return _DEFAULT_TICK_SIZES.get(instrument_symbol.strip().upper(), 0.25)


def build_instrument_profile_v1(
    instrument_symbol: str,
    *,
    tick_size: float,
    profile_version: str,
    schema_version: str,
    ontology_version: str,
    created_at: datetime | None = None,
    is_active: bool = True,
) -> InstrumentProfile:
    """Build one strict instrument_profile_v1 instance."""

    created = created_at or datetime.now(tz=UTC)
    payload = _merged_profile_seed(instrument_symbol=instrument_symbol, tick_size=tick_size)
    return InstrumentProfile.model_validate(
        {
            "instrument": instrument_symbol.strip().upper(),
            "profile_version": profile_version,
            "schema_version": schema_version,
            "ontology_version": ontology_version,
            "is_active": is_active,
            "normalization": payload["normalization"],
            "time_windows": payload["time_windows"],
            "thresholds": payload["thresholds"],
            "weights": payload["weights"],
            "decay": payload["decay"],
            "priors": payload["priors"],
            "safety": payload["safety"],
            "created_at": created,
        },
    )


def get_parameter_metadata_registry(instrument_symbol: str) -> dict[str, InstrumentProfileParameterMetadata]:
    """Return the metadata registry for all adjustable numeric parameters."""

    safe_profile = build_instrument_profile_v1(
        instrument_symbol,
        tick_size=default_tick_size_for_symbol(instrument_symbol),
        profile_version="safe-default",
        schema_version=PROFILE_SCHEMA_VERSION,
        ontology_version="master_spec_v2_v1",
        created_at=datetime(2026, 3, 23, tzinfo=UTC),
    )
    safe_values = safe_profile.model_dump(mode="python")
    registry: dict[str, InstrumentProfileParameterMetadata] = {}

    spec_rows = [
        ("normalization.atr_window_bars", "int", 5, 120, 1, ParameterCriticality.MEDIUM, _GENERAL_EVENTS, "ATR lookback used by normalized movement helpers."),
        ("normalization.range_ticks_reference", "float", 4.0, 128.0, 0.5, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Reference range in ticks for normalization-sensitive evidence."),
        ("normalization.anchor_active_distance_ticks", "float", 4.0, 128.0, 0.5, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Activation radius for anchor-aware evidence."),
        ("time_windows.feature_lookback_bars", "int", 8, 120, 1, ParameterCriticality.MEDIUM, _GENERAL_EVENTS, "Lookback depth in bars for deterministic feature assembly."),
        ("time_windows.feature_lookback_minutes", "int", 15, 480, 5, ParameterCriticality.MEDIUM, _GENERAL_EVENTS, "Lookback depth in minutes for deterministic feature assembly."),
        ("thresholds.active_hypothesis_probability", "float", 0.10, 0.60, 0.01, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Minimum posterior needed to keep a hypothesis active."),
        ("thresholds.building_hypothesis_probability", "float", 0.15, 0.75, 0.01, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Posterior threshold for the building phase."),
        ("thresholds.confirming_hypothesis_probability", "float", 0.20, 0.90, 0.01, ParameterCriticality.CRITICAL, _GENERAL_EVENTS, "Posterior threshold for the confirming phase."),
        ("thresholds.resolved_hypothesis_probability", "float", 0.25, 0.95, 0.01, ParameterCriticality.CRITICAL, _GENERAL_EVENTS, "Posterior threshold for closing a resolved event episode."),
        ("thresholds.weakening_drop_threshold", "float", 0.01, 0.40, 0.01, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Posterior drop required before a state is tagged weakening."),
        ("thresholds.momentum_efficiency_high", "float", 0.20, 0.95, 0.01, ParameterCriticality.HIGH, _MOMENTUM_EVENTS, "Efficiency threshold that supports momentum continuation bias."),
        ("thresholds.balance_score_high", "float", 0.20, 0.95, 0.01, ParameterCriticality.HIGH, _BALANCE_EVENTS, "Balance threshold that supports mean-reversion bias."),
        ("thresholds.compression_score_high", "float", 0.20, 0.95, 0.01, ParameterCriticality.MEDIUM, _BALANCE_EVENTS + _ABSORPTION_EVENTS, "Compression threshold used in transition-sensitive contexts."),
        ("thresholds.absorption_score_high", "float", 0.20, 0.95, 0.01, ParameterCriticality.HIGH, _ABSORPTION_EVENTS, "Absorption threshold used in reversal-preparation contexts."),
        ("thresholds.center_hit_ticks", "float", 1.0, 32.0, 0.5, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Distance threshold used to treat price as back at balance center."),
        ("thresholds.anchor_near_ticks", "float", 1.0, 64.0, 0.5, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Distance threshold for anchor-aware confirmation checks."),
        ("thresholds.initiative_reacceleration_score", "float", 0.20, 0.95, 0.01, ParameterCriticality.CRITICAL, _MOMENTUM_EVENTS + _REVERSAL_EVENTS, "Threshold used when reacceleration invalidates a competing hypothesis."),
        ("thresholds.initiative_push.displacement_zscore", "float", 0.5, 4.0, 0.05, ParameterCriticality.HIGH, _MOMENTUM_EVENTS, "Displacement boundary for initiative push detection."),
        ("thresholds.initiative_push.efficiency_min", "float", 0.20, 0.95, 0.01, ParameterCriticality.HIGH, _MOMENTUM_EVENTS, "Minimum efficiency required for an initiative push."),
        ("thresholds.shallow_pullback.retrace_ratio_max", "float", 0.05, 0.80, 0.01, ParameterCriticality.MEDIUM, _MOMENTUM_EVENTS, "Maximum retrace ratio used to classify shallow pullbacks."),
        ("thresholds.deep_pullback.retrace_ratio_min", "float", 0.10, 0.95, 0.01, ParameterCriticality.MEDIUM, _MOMENTUM_EVENTS + _REVERSAL_EVENTS, "Minimum retrace ratio used to classify deep pullbacks."),
        ("thresholds.balance_return_penalty_trigger.distance_to_balance_ticks", "float", 1.0, 32.0, 0.5, ParameterCriticality.HIGH, _MOMENTUM_EVENTS + _BALANCE_EVENTS, "Distance-to-balance trigger used when continuation loses structure."),
        ("decay.stale_macro_penalty", "float", 0.0, 1.0, 0.01, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Penalty applied when macro/process context is stale."),
        ("decay.missing_depth_penalty", "float", 0.0, 1.0, 0.01, ParameterCriticality.CRITICAL, _GENERAL_EVENTS, "Penalty applied when depth is unavailable."),
        ("decay.missing_dom_penalty", "float", 0.0, 1.0, 0.01, ParameterCriticality.CRITICAL, _GENERAL_EVENTS, "Penalty applied when DOM is unavailable."),
        ("decay.anchor_freshness_hours", "int", 4, 720, 1, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Freshness horizon for anchor usage."),
        ("decay.balance_center_half_life_bars", "int", 8, 1000, 1, ParameterCriticality.MEDIUM, _BALANCE_EVENTS, "Half-life for balance-center anchors."),
        ("decay.gap_edge_half_life_bars", "int", 8, 1000, 1, ParameterCriticality.MEDIUM, _GENERAL_EVENTS, "Half-life for gap-edge anchors."),
        ("decay.initiative_origin_half_life_bars", "int", 8, 1000, 1, ParameterCriticality.MEDIUM, _MOMENTUM_EVENTS + _REVERSAL_EVENTS, "Half-life for initiative-origin anchors."),
        ("safety.max_belief_regimes", "int", 1, 6, 1, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Maximum number of regimes surfaced in one belief snapshot."),
        ("safety.max_belief_hypotheses", "int", 1, 8, 1, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Maximum number of hypotheses surfaced in one belief snapshot."),
        ("safety.max_active_anchors", "int", 1, 8, 1, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Maximum number of anchors surfaced in one belief snapshot."),
        ("safety.minimum_bar_count_for_primary_features", "int", 1, 32, 1, ParameterCriticality.HIGH, _GENERAL_EVENTS, "Minimum bar count before bar-based features can dominate."),
    ]

    for path, value_type, min_value, max_value, step, criticality, applies_to_events, description in spec_rows:
        registry[path] = _meta(path, value_type, min_value, max_value, step, _get_path(safe_values, path), criticality, applies_to_events, description)

    for path, criticality, applies_to_events in (
        ("time_windows.momentum_continuation.strong.bars_min", ParameterCriticality.HIGH, _MOMENTUM_EVENTS),
        ("time_windows.momentum_continuation.strong.bars_max", ParameterCriticality.HIGH, _MOMENTUM_EVENTS),
        ("time_windows.momentum_continuation.normal.bars_min", ParameterCriticality.MEDIUM, _MOMENTUM_EVENTS),
        ("time_windows.momentum_continuation.normal.bars_max", ParameterCriticality.HIGH, _MOMENTUM_EVENTS),
        ("time_windows.balance_mean_reversion.normal.bars_min", ParameterCriticality.MEDIUM, _BALANCE_EVENTS),
        ("time_windows.balance_mean_reversion.normal.bars_max", ParameterCriticality.HIGH, _BALANCE_EVENTS),
        ("time_windows.absorption_to_reversal_preparation.normal.bars_min", ParameterCriticality.MEDIUM, _ABSORPTION_EVENTS),
        ("time_windows.absorption_to_reversal_preparation.normal.bars_max", ParameterCriticality.HIGH, _ABSORPTION_EVENTS),
    ):
        is_max = path.endswith("bars_max")
        registry[path] = _meta(path, "int", 1 if not is_max else 2, 32 if not is_max else 32, 1, _get_path(safe_values, path), criticality, applies_to_events, "Tempo window boundary for the mapped tradable event.")

    for path, applies_to_events in (
        ("weights.bar_structure", _GENERAL_EVENTS),
        ("weights.volatility_range", _GENERAL_EVENTS),
        ("weights.trend_efficiency", _MOMENTUM_EVENTS),
        ("weights.initiative", _MOMENTUM_EVENTS + _ABSORPTION_EVENTS),
        ("weights.balance", _BALANCE_EVENTS),
        ("weights.absorption", _ABSORPTION_EVENTS),
        ("weights.depth_dom", _GENERAL_EVENTS),
        ("weights.anchor_interaction", _GENERAL_EVENTS),
        ("weights.path_dependency", _GENERAL_EVENTS),
    ):
        criticality = ParameterCriticality.CRITICAL if path == "weights.depth_dom" else ParameterCriticality.HIGH if path in {"weights.trend_efficiency", "weights.initiative", "weights.balance", "weights.absorption", "weights.anchor_interaction", "weights.path_dependency"} else ParameterCriticality.MEDIUM
        registry[path] = _meta(path, "float", 0.0, 2.0, 0.05, _get_path(safe_values, path), criticality, applies_to_events, "Evidence bucket weight.")

    for path, applies_to_events in (
        ("priors.regimes.strong_momentum_trend", _MOMENTUM_EVENTS),
        ("priors.regimes.weak_momentum_trend_narrow", _MOMENTUM_EVENTS),
        ("priors.regimes.weak_momentum_trend_wide", _MOMENTUM_EVENTS),
        ("priors.regimes.balance_mean_reversion", _BALANCE_EVENTS),
        ("priors.regimes.compression", _BALANCE_EVENTS + _ABSORPTION_EVENTS),
        ("priors.regimes.transition_exhaustion", _ABSORPTION_EVENTS),
        ("priors.hypotheses.continuation_base", _MOMENTUM_EVENTS),
        ("priors.hypotheses.distribution_balance", _BALANCE_EVENTS),
        ("priors.hypotheses.absorption_accumulation", _ABSORPTION_EVENTS),
        ("priors.hypotheses.reversal_preparation", _REVERSAL_EVENTS),
    ):
        registry[path] = _meta(path, "float", 0.0, 1.0, 0.01, _get_path(safe_values, path), ParameterCriticality.MEDIUM, applies_to_events, "Prior probability used before evidence accumulation.")

    return registry


class InstrumentProfileService:
    """Loads, validates, compares, and persists bounded instrument profile patches."""

    def __init__(self, repository: AnalysisRepository | None = None) -> None:
        self._repository = repository

    def build_default_profile(
        self,
        *,
        instrument_symbol: str,
        tick_size: float | None,
        profile_version: str,
        schema_version: str,
        ontology_version: str,
        created_at: datetime | None = None,
        is_active: bool = True,
    ) -> InstrumentProfile:
        """Build the canonical instrument_profile_v1 for one symbol."""

        return build_instrument_profile_v1(
            instrument_symbol,
            tick_size=tick_size or default_tick_size_for_symbol(instrument_symbol),
            profile_version=profile_version,
            schema_version=schema_version,
            ontology_version=ontology_version,
            created_at=created_at,
            is_active=is_active,
        )

    def validate_patch(
        self,
        *,
        base_profile: InstrumentProfile,
        patch: dict[str, Any],
        proposed_profile_version: str | None = None,
        recommendation_id: str | None = None,
        persist: bool = False,
    ) -> tuple[ProfilePatchCandidate, ProfilePatchValidationResult]:
        """Validate one patch against boundary metadata and produce compare/preview output."""

        now = datetime.now(tz=UTC)
        flat_patch = _normalize_patch_input(patch)
        metadata = get_parameter_metadata_registry(base_profile.instrument_symbol)
        base_payload = base_profile.model_dump(mode="python")
        merged_payload = base_profile.model_dump(mode="python")

        candidate_parameters = sorted(flat_patch)
        suggested_changes: dict[str, ProfileSuggestedChange] = {}
        changed_fields: list[ProfilePatchFieldDiff] = []
        errors: list[ProfilePatchValidationIssue] = []
        warnings: list[ProfilePatchValidationIssue] = []
        aggregate_risks: list[str] = []

        for path, value in flat_patch.items():
            if path in _IMMUTABLE_PATCH_PATHS:
                errors.append(ProfilePatchValidationIssue(path=path, code="immutable_parameter", message=f"{path} is fixed and cannot be patched."))
                continue
            if path.startswith("ontology_version"):
                errors.append(ProfilePatchValidationIssue(path=path, code="ontology_locked", message="Ontology fields are fixed by Master Spec v2 and cannot be modified."))
                continue
            if path == "safety.allow_ai_auto_apply":
                errors.append(ProfilePatchValidationIssue(path=path, code="ai_auto_apply_forbidden", message="allow_ai_auto_apply must stay false."))
                continue

            meta = metadata.get(path)
            if meta is None:
                errors.append(ProfilePatchValidationIssue(path=path, code="illegal_parameter", message=f"{path} is not an adjustable instrument_profile_v1 parameter."))
                continue

            old_value = _get_path(base_payload, path)
            new_value = _coerce_numeric(value, meta=meta)
            if new_value is None:
                errors.append(ProfilePatchValidationIssue(path=path, code="type_mismatch", message=f"{path} expects a {meta.value_type} value."))
                continue
            if new_value < meta.min or new_value > meta.max:
                errors.append(ProfilePatchValidationIssue(path=path, code="out_of_bounds", message=f"{path} must stay within [{meta.min}, {meta.max}]."))
                continue
            if not _matches_step(new_value, meta=meta):
                errors.append(ProfilePatchValidationIssue(path=path, code="invalid_step", message=f"{path} must move in steps of {meta.step}."))
                continue
            if _same_value(old_value, new_value):
                warnings.append(ProfilePatchValidationIssue(path=path, code="no_effective_change", message=f"{path} keeps the same value and will have no effect."))
                continue

            action = _change_action(old_value, new_value)
            suggested_changes[path] = ProfileSuggestedChange(action=action, from_value=old_value, to_value=new_value)
            _set_path(merged_payload, path, new_value)
            field_risks = _build_field_risks(path=path, old_value=old_value, new_value=new_value, meta=meta)
            aggregate_risks.extend(field_risks)
            changed_fields.append(
                ProfilePatchFieldDiff(
                    path=path,
                    action=action,
                    previous_value=old_value,
                    next_value=new_value,
                    metadata=meta,
                    risk_notes=field_risks,
                ),
            )

        if not changed_fields and not errors:
            errors.append(ProfilePatchValidationIssue(path="", code="no_effective_changes", message="Patch did not produce any effective bounded changes."))

        proposed_version = proposed_profile_version or _derive_profile_version(base_profile.profile_version)
        preview: ProfilePatchPreview | None = None
        if not errors:
            InstrumentProfile.model_validate({**merged_payload, "profile_version": proposed_version})
            preview = ProfilePatchPreview(
                instrument_symbol=base_profile.instrument_symbol,
                base_profile_version=base_profile.profile_version,
                proposed_profile_version=proposed_version,
                candidate_parameters=[field.path for field in changed_fields],
                changed_fields=changed_fields,
                risk_notes=_unique_preserve_order(aggregate_risks),
            )

        candidate = ProfilePatchCandidate(
            candidate_id=f"patch-{uuid4().hex}",
            instrument_symbol=base_profile.instrument_symbol,
            schema_version=PROFILE_PATCH_CANDIDATE_SCHEMA_VERSION,
            ontology_version=base_profile.ontology_version,
            base_profile_version=base_profile.profile_version,
            proposed_profile_version=proposed_version,
            recommendation_id=recommendation_id,
            candidate_parameters=[field.path for field in changed_fields] if changed_fields else candidate_parameters,
            suggested_changes=suggested_changes,
            risk_notes=_unique_preserve_order(aggregate_risks),
            created_at=now,
        )
        validation = ProfilePatchValidationResult(
            schema_version=PATCH_VALIDATION_RESULT_SCHEMA_VERSION,
            candidate_id=candidate.candidate_id,
            instrument_symbol=base_profile.instrument_symbol,
            validation_status=PatchValidationStatus.REJECTED if errors else PatchValidationStatus.ACCEPTED,
            boundary_validation_status=PatchValidationStatus.REJECTED if errors else PatchValidationStatus.ACCEPTED,
            recommendation_id=recommendation_id,
            base_profile_version=base_profile.profile_version,
            proposed_profile_version=proposed_version,
            errors=errors,
            warnings=warnings,
            changed_fields=[field.path for field in changed_fields],
            risk_notes=_unique_preserve_order(aggregate_risks),
            preview=preview,
            validated_at=now,
        )

        if persist:
            self._persist_candidate(candidate)
            self._persist_validation(validation)
        return candidate, validation

    def compare_profiles(
        self,
        *,
        base_profile: InstrumentProfile,
        patch: dict[str, Any],
        proposed_profile_version: str | None = None,
    ) -> ProfilePatchPreview:
        """Return compare/preview output or raise when the patch is invalid."""

        _, validation = self.validate_patch(
            base_profile=base_profile,
            patch=patch,
            proposed_profile_version=proposed_profile_version,
            persist=False,
        )
        if validation.validation_status is PatchValidationStatus.REJECTED or validation.preview is None:
            detail = "; ".join(issue.message for issue in validation.errors) or "invalid profile patch"
            raise ValueError(detail)
        return validation.preview

    def _persist_candidate(self, candidate: ProfilePatchCandidate) -> None:
        if self._repository is None:
            return
        self._repository.save_profile_patch_candidate(
            candidate_id=candidate.candidate_id,
            instrument_symbol=candidate.instrument_symbol,
            market_time=candidate.created_at,
            ingested_at=candidate.created_at,
            schema_version=candidate.schema_version,
            base_profile_version=candidate.base_profile_version,
            proposed_profile_version=candidate.proposed_profile_version,
            recommendation_id=candidate.recommendation_id,
            status="candidate_created",
            patch_payload=candidate.model_dump(mode="json"),
        )

    def _persist_validation(self, validation: ProfilePatchValidationResult) -> None:
        if self._repository is None:
            return
        self._repository.save_patch_validation_result(
            validation_result_id=f"pvr-{uuid4().hex}",
            instrument_symbol=validation.instrument_symbol,
            market_time=validation.validated_at,
            ingested_at=validation.validated_at,
            schema_version=validation.schema_version,
            candidate_id=validation.candidate_id,
            validation_status=validation.validation_status.value,
            validation_payload=validation.model_dump(mode="json"),
        )


def _merged_profile_seed(*, instrument_symbol: str, tick_size: float) -> dict[str, Any]:
    symbol = instrument_symbol.strip().upper()
    payload = _deep_merge({}, _BASE_PROFILE_SEED)
    payload["normalization"]["tick_size"] = tick_size
    override = _INSTRUMENT_OVERRIDES.get(symbol)
    if override is not None:
        payload = _deep_merge(payload, override)
    return payload


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif isinstance(value, dict):
            merged[key] = _deep_merge({}, value)
        else:
            merged[key] = value
    return merged


def _meta(
    path: str,
    value_type: str,
    min_value: float,
    max_value: float,
    step: float,
    safe_default: float,
    criticality: ParameterCriticality,
    applies_to_events: list[TradableEventKind],
    description: str,
) -> InstrumentProfileParameterMetadata:
    return InstrumentProfileParameterMetadata(
        path=path,
        value_type=value_type,
        min=min_value,
        max=max_value,
        step=step,
        safe_default=float(safe_default),
        criticality=criticality,
        applies_to_events=applies_to_events,
        description=description,
    )


def _normalize_patch_input(patch: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "suggested_changes" and isinstance(value, dict):
            for path, change in value.items():
                if isinstance(change, dict) and "to" in change:
                    flat[path] = change["to"]
            continue
        if "." in key and not isinstance(value, dict):
            flat[key] = value
            continue
        if isinstance(value, dict):
            flat.update(_flatten_dict(value, prefix=key))
            continue
        flat[key] = value
    return flat


def _flatten_dict(payload: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_dict(value, prefix=path))
        else:
            flat[path] = value
    return flat


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    current = payload
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _coerce_numeric(value: Any, *, meta: InstrumentProfileParameterMetadata) -> int | float | None:
    if isinstance(value, bool):
        return None
    if meta.value_type == "int":
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _matches_step(value: int | float, *, meta: InstrumentProfileParameterMetadata) -> bool:
    offset = (float(value) - meta.min) / meta.step
    return math.isclose(offset, round(offset), abs_tol=1e-9)


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), abs_tol=1e-9)
    return left == right


def _change_action(old_value: int | float, new_value: int | float) -> str:
    if float(new_value) > float(old_value):
        return "increase"
    if float(new_value) < float(old_value):
        return "decrease"
    return "set"


def _build_field_risks(
    *,
    path: str,
    old_value: int | float,
    new_value: int | float,
    meta: InstrumentProfileParameterMetadata,
) -> list[str]:
    notes = [f"{path} is a {meta.criticality.value}-criticality parameter."]
    if meta.criticality in {ParameterCriticality.HIGH, ParameterCriticality.CRITICAL}:
        notes.append("This change requires replay validation before promotion.")
    if float(meta.safe_default) != 0.0:
        deviation = abs(float(new_value) - float(meta.safe_default)) / abs(float(meta.safe_default))
        if deviation >= 0.20:
            notes.append(f"{path} moves more than 20% away from the safe default.")
    if float(old_value) != 0.0:
        movement = abs(float(new_value) - float(old_value)) / abs(float(old_value))
        if movement >= 0.25:
            notes.append(f"{path} changes more than 25% from the current profile value.")
    if path.startswith("weights.") and float(new_value) < 0.50:
        notes.append("Evidence weight becomes light and may mute otherwise valid signals.")
    if path.startswith("thresholds.") and meta.criticality in {ParameterCriticality.HIGH, ParameterCriticality.CRITICAL}:
        notes.append("Threshold movement can materially change confirmation or invalidation timing.")
    if path.startswith("priors.") and abs(float(new_value) - float(old_value)) >= 0.08:
        notes.append("Prior shift may distort multi-hypothesis balance before evidence accumulates.")
    if path.startswith("time_windows.") and abs(float(new_value) - float(old_value)) >= 3:
        notes.append("Tempo window shift is material and may change episode timing.")
    return _unique_preserve_order(notes)


def _derive_profile_version(base_profile_version: str) -> str:
    return f"{base_profile_version}.patch-preview"


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
