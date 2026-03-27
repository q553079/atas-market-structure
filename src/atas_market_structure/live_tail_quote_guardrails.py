from __future__ import annotations

from dataclasses import dataclass
import math

from atas_market_structure.models import ReplayChartBar

_MIN_REFERENCE_PAD = 1.0
_REFERENCE_PAD_MULTIPLIER = 1.5


@dataclass(frozen=True)
class LiveTailQuoteSanitizationResult:
    latest_price: float | None
    latest_price_source: str | None
    best_bid: float | None
    best_ask: float | None
    was_sanitized: bool = False
    reason: str | None = None


def sanitize_live_tail_quote(
    *,
    latest_price: float | None,
    latest_price_source: str | None,
    best_bid: float | None,
    best_ask: float | None,
    tick_latest_price: float | None,
    tick_latest_price_source: str | None,
    local_range_low: float | None,
    local_range_high: float | None,
    reference_candle: ReplayChartBar | None,
) -> LiveTailQuoteSanitizationResult:
    latest_price = _finite_or_none(latest_price)
    best_bid = _finite_or_none(best_bid)
    best_ask = _finite_or_none(best_ask)
    tick_latest_price = _finite_or_none(tick_latest_price)
    local_range_low = _finite_or_none(local_range_low)
    local_range_high = _finite_or_none(local_range_high)

    if (
        best_bid is not None
        and best_ask is not None
        and best_ask < best_bid
    ):
        best_bid = None
        best_ask = None

    reference_prices = _collect_reference_prices(
        best_bid=best_bid,
        best_ask=best_ask,
        local_range_low=local_range_low,
        local_range_high=local_range_high,
        reference_candle=reference_candle,
    )
    band = _build_reference_band(reference_prices)
    if latest_price is None or band is None or _price_within_band(latest_price, band):
        return LiveTailQuoteSanitizationResult(
            latest_price=latest_price,
            latest_price_source=latest_price_source if latest_price is not None else None,
            best_bid=best_bid,
            best_ask=best_ask,
        )

    candidates = [
        (
            tick_latest_price,
            tick_latest_price_source if tick_latest_price is not None else None,
            "replaced_with_tick_latest_price",
        ),
        (
            _midpoint(best_bid, best_ask),
            latest_price_source if best_bid is not None and best_ask is not None else None,
            "replaced_with_quote_midpoint",
        ),
        (
            _midpoint(local_range_low, local_range_high),
            latest_price_source if local_range_low is not None and local_range_high is not None else None,
            "replaced_with_local_range_midpoint",
        ),
        (
            _reference_candle_close(reference_candle),
            "candle_close" if reference_candle is not None else None,
            "replaced_with_reference_candle_close",
        ),
    ]
    for candidate_price, candidate_source, reason in candidates:
        candidate_price = _finite_or_none(candidate_price)
        if candidate_price is None or not _price_within_band(candidate_price, band):
            continue
        return LiveTailQuoteSanitizationResult(
            latest_price=candidate_price,
            latest_price_source=candidate_source,
            best_bid=best_bid,
            best_ask=best_ask,
            was_sanitized=True,
            reason=reason,
        )

    return LiveTailQuoteSanitizationResult(
        latest_price=latest_price,
        latest_price_source=latest_price_source if latest_price is not None else None,
        best_bid=best_bid,
        best_ask=best_ask,
        was_sanitized=False,
        reason=None,
    )


def _collect_reference_prices(
    *,
    best_bid: float | None,
    best_ask: float | None,
    local_range_low: float | None,
    local_range_high: float | None,
    reference_candle: ReplayChartBar | None,
) -> list[float]:
    prices = [
        _finite_or_none(best_bid),
        _finite_or_none(best_ask),
        _finite_or_none(local_range_low),
        _finite_or_none(local_range_high),
    ]
    if reference_candle is not None:
        prices.extend([
            _finite_or_none(reference_candle.open),
            _finite_or_none(reference_candle.high),
            _finite_or_none(reference_candle.low),
            _finite_or_none(reference_candle.close),
        ])
    return [value for value in prices if value is not None]


def _build_reference_band(reference_prices: list[float]) -> tuple[float, float] | None:
    if not reference_prices:
        return None
    low = min(reference_prices)
    high = max(reference_prices)
    span = max(0.0, high - low)
    pad = max(_MIN_REFERENCE_PAD, span * _REFERENCE_PAD_MULTIPLIER)
    return (low - pad, high + pad)


def _price_within_band(value: float, band: tuple[float, float]) -> bool:
    low, high = band
    return low <= value <= high


def _midpoint(first: float | None, second: float | None) -> float | None:
    first = _finite_or_none(first)
    second = _finite_or_none(second)
    if first is None or second is None:
        return None
    return (first + second) / 2.0


def _reference_candle_close(reference_candle: ReplayChartBar | None) -> float | None:
    if reference_candle is None:
        return None
    return _finite_or_none(reference_candle.close)


def _finite_or_none(value: float | None) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric
