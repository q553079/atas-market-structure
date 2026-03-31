from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence


def prune_live_tail_seed_candles(
    candles: Sequence[Any],
    *,
    timeframe_minutes: int,
    lookback_bars: int,
    reference_time: datetime | None,
    padding_bars: int = 3,
    anchor_bars: int = 1,
) -> list[Any]:
    """Keep live-tail seed candles near the latest observed time plus one anchor bar.

    Live-tail gap filling should operate on a short recent window. If we seed the
    merge with only the last N observed candles during an inactive session, those
    candles can span hours and expand into hundreds of synthetic minute bars.
    """

    ordered = _ordered_candles(candles)
    if not ordered:
        return []

    safe_lookback = max(1, int(lookback_bars))
    step = timedelta(minutes=max(1, int(timeframe_minutes)))
    window_end = reference_time or _resolve_bar_end(ordered[-1]) or _resolve_bar_start(ordered[-1])
    if window_end is None:
        return ordered[-safe_lookback:]

    window_start = window_end - (step * max(2, safe_lookback + max(0, int(padding_bars))))
    keep_from_index: int | None = None
    for index, candle in enumerate(ordered):
        candle_end = _resolve_bar_end(candle) or _resolve_bar_start(candle)
        if candle_end is not None and candle_end >= window_start:
            keep_from_index = max(0, index - max(0, int(anchor_bars)))
            break

    if keep_from_index is None:
        return ordered[-min(len(ordered), safe_lookback + max(0, int(anchor_bars))):]
    return ordered[keep_from_index:]


def trim_live_tail_display_candles(
    candles: Sequence[Any],
    *,
    lookback_bars: int,
) -> list[Any]:
    ordered = _ordered_candles(candles)
    safe_lookback = max(1, int(lookback_bars))
    if len(ordered) <= safe_lookback:
        return ordered
    return ordered[-safe_lookback:]


def _ordered_candles(candles: Sequence[Any]) -> list[Any]:
    return sorted(
        (
            candle
            for candle in candles
            if candle is not None and _resolve_bar_start(candle) is not None
        ),
        key=lambda candle: _resolve_bar_start(candle),
    )


def _resolve_bar_start(candle: Any) -> datetime | None:
    value = getattr(candle, "started_at", None)
    return value if isinstance(value, datetime) else None


def _resolve_bar_end(candle: Any) -> datetime | None:
    value = getattr(candle, "ended_at", None)
    return value if isinstance(value, datetime) else None
