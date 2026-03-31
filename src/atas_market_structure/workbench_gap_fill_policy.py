from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from atas_market_structure.models._enums import Timeframe

_CME_GLOBEX_TIMEZONE = ZoneInfo("America/Chicago")
_CME_MAINTENANCE_START = time(hour=16, minute=0)
_CME_REOPEN_TIME = time(hour=17, minute=0)
_SUPPORTED_TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.MIN_1: 1,
    Timeframe.MIN_5: 5,
    Timeframe.MIN_15: 15,
    Timeframe.MIN_30: 30,
    Timeframe.HOUR_1: 60,
    Timeframe.DAY_1: 1440,
}


def timeframe_delta(timeframe: Timeframe) -> timedelta:
    minutes = _SUPPORTED_TIMEFRAME_MINUTES.get(timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported timeframe for gap-fill policy: {timeframe!r}")
    return timedelta(minutes=minutes)


def is_fixed_session_closure(*, started_at: datetime, instrument_venue: str | None = None) -> bool:
    normalized_venue = str(instrument_venue or "CME").strip().upper()
    if normalized_venue != "CME":
        return False

    local_started_at = started_at.astimezone(_CME_GLOBEX_TIMEZONE)
    weekday = local_started_at.weekday()
    local_time = local_started_at.timetz().replace(tzinfo=None)

    if weekday == 5:
        return True
    if weekday == 6:
        return local_time < _CME_REOPEN_TIME
    if weekday == 4:
        return local_time >= _CME_MAINTENANCE_START
    return _CME_MAINTENANCE_START <= local_time < _CME_REOPEN_TIME


def iter_fillable_gap_starts(
    *,
    previous_started_at: datetime,
    next_started_at: datetime,
    timeframe: Timeframe,
    instrument_venue: str | None = None,
    tolerance: timedelta = timedelta(seconds=5),
):
    delta = timeframe_delta(timeframe)
    cursor = previous_started_at.astimezone(UTC) + delta
    upper_bound = next_started_at.astimezone(UTC) - tolerance

    while cursor < upper_bound:
        if not is_fixed_session_closure(started_at=cursor, instrument_venue=instrument_venue):
            yield cursor
        cursor += delta


def count_fillable_gap_bars(
    *,
    previous_started_at: datetime,
    next_started_at: datetime,
    timeframe: Timeframe,
    instrument_venue: str | None = None,
    tolerance: timedelta = timedelta(seconds=5),
) -> int:
    return sum(
        1
        for _ in iter_fillable_gap_starts(
            previous_started_at=previous_started_at,
            next_started_at=next_started_at,
            timeframe=timeframe,
            instrument_venue=instrument_venue,
            tolerance=tolerance,
        )
    )
