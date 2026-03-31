from __future__ import annotations

from datetime import datetime

from atas_market_structure.models import Timeframe
from atas_market_structure.workbench_gap_fill_policy import (
    count_fillable_gap_bars,
    iter_fillable_gap_starts,
)


def test_gap_fill_policy_counts_large_tradable_intraday_gap() -> None:
    previous_started_at = datetime.fromisoformat("2026-03-16T14:30:00+00:00")
    next_started_at = datetime.fromisoformat("2026-03-16T15:05:00+00:00")

    assert count_fillable_gap_bars(
        previous_started_at=previous_started_at,
        next_started_at=next_started_at,
        timeframe=Timeframe.MIN_1,
        instrument_venue="CME",
    ) == 34


def test_gap_fill_policy_skips_cme_daily_maintenance_buckets() -> None:
    previous_started_at = datetime.fromisoformat("2026-03-16T20:55:00+00:00")
    next_started_at = datetime.fromisoformat("2026-03-16T22:01:00+00:00")

    fillable = list(
        iter_fillable_gap_starts(
            previous_started_at=previous_started_at,
            next_started_at=next_started_at,
            timeframe=Timeframe.MIN_1,
            instrument_venue="CME",
        )
    )

    assert [item.isoformat().replace("+00:00", "Z") for item in fillable] == [
        "2026-03-16T20:56:00Z",
        "2026-03-16T20:57:00Z",
        "2026-03-16T20:58:00Z",
        "2026-03-16T20:59:00Z",
        "2026-03-16T22:00:00Z",
    ]
