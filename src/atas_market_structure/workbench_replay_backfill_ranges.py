from __future__ import annotations

from datetime import UTC, datetime, timedelta

from atas_market_structure.models import ReplayWorkbenchBackfillRange, Timeframe


_TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.MIN_1: 1,
    Timeframe.MIN_5: 5,
    Timeframe.MIN_15: 15,
    Timeframe.MIN_30: 30,
    Timeframe.HOUR_1: 60,
    Timeframe.DAY_1: 1440,
}


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def chunk_backfill_ranges(
    *,
    display_timeframe: Timeframe,
    requested_ranges: list[ReplayWorkbenchBackfillRange],
    max_bars_per_range: int,
) -> list[ReplayWorkbenchBackfillRange]:
    if not requested_ranges:
        return []

    normalized_max_bars = max(1, int(max_bars_per_range))
    timeframe_minutes = max(1, _TIMEFRAME_MINUTES.get(display_timeframe, 1))
    max_range_span = timedelta(minutes=timeframe_minutes * normalized_max_bars) - timedelta(seconds=1)

    chunked: list[ReplayWorkbenchBackfillRange] = []
    for requested_range in requested_ranges:
        range_start = _ensure_utc(requested_range.range_start)
        range_end = _ensure_utc(requested_range.range_end)
        cursor = range_start
        while cursor <= range_end:
            chunk_end = min(cursor + max_range_span, range_end)
            chunked.append(
                ReplayWorkbenchBackfillRange(
                    range_start=cursor,
                    range_end=chunk_end,
                )
            )
            if chunk_end >= range_end:
                break
            cursor = chunk_end + timedelta(seconds=1)

    return chunked
