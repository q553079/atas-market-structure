from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class TailOutlierStats:
    max_range: float
    max_displacement: float
    max_neighbor_drift: float


def suppress_tail_outlier_candles(
    candles: Sequence[Any],
    *,
    freshness: str | None = None,
    guarded_tail_bars: int = 24,
    stale_tail_bars: int = 4,
) -> tuple[list[Any], int]:
    """Repair display-only tail spikes without mutating persisted data.

    The workbench receives a mix of stable history bars and fast-changing tail bars.
    A transient bad quote or continuous-state sample can produce a structurally valid
    but visually absurd wick. For display paths, replace those isolated tail outliers
    with a close-to-close bar anchored by neighboring observed closes.
    """

    ordered = list(candles)
    if len(ordered) < 3:
        return ordered, 0

    normalized_freshness = str(freshness or "").strip().lower()
    repaired = list(ordered)
    repaired_count = 0
    guarded_tail_start = max(0, len(ordered) - max(1, guarded_tail_bars))

    for index in range(guarded_tail_start, len(ordered)):
        candle = ordered[index]
        if _is_synthetic_gap_bar(candle):
            continue

        open_price = _finite_or_none(getattr(candle, "open", None))
        high_price = _finite_or_none(getattr(candle, "high", None))
        low_price = _finite_or_none(getattr(candle, "low", None))
        close_price = _finite_or_none(getattr(candle, "close", None))
        if None in {open_price, high_price, low_price, close_price}:
            continue

        stats = _build_tail_outlier_stats(ordered, index)
        candle_range = max(0.0, high_price - low_price)
        if candle_range <= stats.max_range:
            continue

        previous_bar = _find_nearest_observed_bar(ordered, index - 1, -1)
        next_bar = _find_nearest_observed_bar(ordered, index + 1, 1)
        previous_close = _finite_or_none(getattr(previous_bar, "close", None))
        next_close = _finite_or_none(getattr(next_bar, "close", None))
        anchor_close = _median([previous_close, next_close])
        if anchor_close is None:
            continue

        displacement = max(
            abs(open_price - anchor_close),
            abs(high_price - anchor_close),
            abs(low_price - anchor_close),
            abs(close_price - anchor_close),
        )
        neighbor_drift = (
            abs(previous_close - next_close)
            if previous_close is not None and next_close is not None
            else 0.0
        )
        is_tail_stale = (
            normalized_freshness != "fresh"
            and index >= max(0, len(ordered) - max(1, stale_tail_bars))
        )
        isolated_outlier = displacement > stats.max_displacement and (
            (
                previous_close is not None
                and next_close is not None
                and neighbor_drift <= stats.max_neighbor_drift
            )
            or is_tail_stale
        )
        if not isolated_outlier:
            continue

        synthetic_open = previous_close if previous_close is not None else anchor_close
        synthetic_close = next_close if next_close is not None else anchor_close
        repaired[index] = candle.model_copy(
            update={
                "open": synthetic_open,
                "high": max(synthetic_open, synthetic_close),
                "low": min(synthetic_open, synthetic_close),
                "close": synthetic_close,
            }
        )
        repaired_count += 1

    return repaired, repaired_count


def anchor_last_candle_to_price(
    candles: Sequence[Any],
    *,
    price: float | None,
) -> tuple[list[Any], bool]:
    """Clamp the last display candle to a trusted price when the raw tail is invalid."""

    trusted_price = _finite_or_none(price)
    ordered = list(candles)
    if not ordered or trusted_price is None:
        return ordered, False

    last_candle = ordered[-1]
    if _is_synthetic_gap_bar(last_candle):
        return ordered, False

    low_price = _finite_or_none(getattr(last_candle, "low", None))
    high_price = _finite_or_none(getattr(last_candle, "high", None))
    if low_price is not None and high_price is not None and low_price <= trusted_price <= high_price:
        return ordered, False

    repaired = list(ordered)
    repaired[-1] = last_candle.model_copy(
        update={
            "open": trusted_price,
            "high": trusted_price,
            "low": trusted_price,
            "close": trusted_price,
        }
    )
    return repaired, True


def _build_tail_outlier_stats(candles: Sequence[Any], index: int) -> TailOutlierStats:
    context_bars: list[Any] = []
    start = max(0, index - 12)
    end = min(len(candles) - 1, index + 6)
    for offset in range(start, end + 1):
        if offset == index:
            continue
        candle = candles[offset]
        if candle is None or _is_synthetic_gap_bar(candle):
            continue
        context_bars.append(candle)

    ranges: list[float] = []
    close_moves: list[float] = []
    previous_close: float | None = None
    for candle in context_bars:
        high_price = _finite_or_none(getattr(candle, "high", None))
        low_price = _finite_or_none(getattr(candle, "low", None))
        close_price = _finite_or_none(getattr(candle, "close", None))
        if high_price is not None and low_price is not None:
            ranges.append(max(0.0, high_price - low_price))
        if close_price is not None and previous_close is not None:
            close_moves.append(abs(close_price - previous_close))
        if close_price is not None:
            previous_close = close_price

    median_range = _median(ranges)
    median_close_move = _median(close_moves)
    return TailOutlierStats(
        max_range=max(
            4.0,
            (median_range * 8.0) if median_range is not None else 0.0,
            (median_close_move * 16.0) if median_close_move is not None else 0.0,
        ),
        max_displacement=max(
            6.0,
            (median_range * 6.0) if median_range is not None else 0.0,
            (median_close_move * 14.0) if median_close_move is not None else 0.0,
        ),
        max_neighbor_drift=max(
            2.0,
            (median_range * 3.0) if median_range is not None else 0.0,
            (median_close_move * 6.0) if median_close_move is not None else 0.0,
        ),
    )


def _find_nearest_observed_bar(candles: Sequence[Any], start_index: int, direction: int) -> Any | None:
    index = start_index
    while 0 <= index < len(candles):
        candle = candles[index]
        if candle is not None and not _is_synthetic_gap_bar(candle):
            return candle
        index += direction
    return None


def _is_synthetic_gap_bar(candle: Any) -> bool:
    return bool(
        candle
        and (
            getattr(candle, "is_synthetic", False) is True
            or str(getattr(candle, "source_kind", "") or "").lower() == "synthetic_gap_fill"
        )
    )


def _median(values: Sequence[float | None]) -> float | None:
    ordered = sorted(value for value in (_finite_or_none(item) for item in values) if value is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[middle - 1] + ordered[middle]) / 2.0
    return ordered[middle]


def _finite_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        return None
    return numeric
