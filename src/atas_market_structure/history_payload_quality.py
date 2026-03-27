from __future__ import annotations

from typing import Any


_LOCAL_TIMEZONE_FALLBACK_BASES = frozenset(
    {
        "collector_local_timezone_fallback",
        "chart_display_timezone_derived_from_local",
        "collector_local_time",
    }
)
_LOW_CONFIDENCE_VALUES = frozenset({"", "low", "medium", "unknown"})
_GUARDRAIL_CORRECTED_BASIS = "python_guardrail_forced_utc_from_original_bar_time_text"


def history_payload_chart_path_verdict(payload: Any) -> tuple[bool, str]:
    timestamp_basis = _coalesce_history_field(payload, "timestamp_basis")
    timezone_mode = _coalesce_history_field(payload, "chart_display_timezone_mode")
    timezone_confidence = _coalesce_history_field(payload, "timezone_capture_confidence")
    return _chart_path_verdict(
        timestamp_basis=timestamp_basis,
        timezone_mode=timezone_mode,
        timezone_confidence=timezone_confidence,
    )


def raw_history_row_chart_path_verdict(row: Any) -> tuple[bool, str]:
    return _chart_path_verdict(
        timestamp_basis=getattr(row, "timestamp_basis", None),
        timezone_mode=getattr(row, "chart_display_timezone_mode", None),
        timezone_confidence=getattr(row, "timezone_capture_confidence", None),
    )


def _chart_path_verdict(
    *,
    timestamp_basis: Any,
    timezone_mode: Any,
    timezone_confidence: Any,
) -> tuple[bool, str]:
    normalized_basis = str(timestamp_basis or "").strip().lower()
    normalized_mode = str(timezone_mode or "").strip().lower()
    normalized_confidence = str(timezone_confidence or "").strip().lower()

    if normalized_basis == _GUARDRAIL_CORRECTED_BASIS:
        return True, "guardrail_corrected_utc"
    if normalized_basis in _LOCAL_TIMEZONE_FALLBACK_BASES:
        return False, f"untrusted_timestamp_basis:{normalized_basis}"
    if normalized_mode == "local" and normalized_confidence in _LOW_CONFIDENCE_VALUES:
        return False, f"untrusted_local_timezone:{normalized_confidence or 'empty'}"
    return True, "trusted_history_timestamp"


def _coalesce_history_field(payload: Any, field_name: str) -> Any:
    source = _nested_value(payload, "source")
    source_value = _nested_value(source, field_name)
    if source_value is not None:
        return source_value
    time_context = _nested_value(payload, "time_context")
    return _nested_value(time_context, field_name)


def _nested_value(target: Any, field_name: str) -> Any:
    if target is None:
        return None
    if isinstance(target, dict):
        return target.get(field_name)
    return getattr(target, field_name, None)
