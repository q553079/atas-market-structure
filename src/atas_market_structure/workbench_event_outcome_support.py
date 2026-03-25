from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from atas_market_structure.models import EventOutcomeResult


@dataclass(frozen=True)
class OutcomeSpec:
    observed_price: float | None
    side_hint: str | None
    target_price: float | None
    stop_price: float | None
    target_distance: float | None
    stop_distance: float | None
    evaluation_window_start: datetime
    evaluation_window_end: datetime
    expiry_policy: dict[str, Any]
    target_rule: dict[str, Any]
    invalidation_rule: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SettlementSnapshot:
    observed_price: float | None
    target_rule: dict[str, Any]
    invalidation_rule: dict[str, Any]
    realized_outcome: EventOutcomeResult | None
    outcome_label: str
    mfe: float | None
    mae: float | None
    hit_target: bool
    hit_stop: bool
    timed_out: bool
    inconclusive: bool
    evaluated_at: datetime
    metadata: dict[str, Any]


def normalize_timeframe(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_side(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"buy", "long", "bull", "bullish", "多", "做多"}:
        return "buy"
    if raw in {"sell", "short", "bear", "bearish", "空", "做空"}:
        return "sell"
    return None


def opposite_side(side: str | None) -> str | None:
    if side == "buy":
        return "sell"
    if side == "sell":
        return "buy"
    return None


def safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
