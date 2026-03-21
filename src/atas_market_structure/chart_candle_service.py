"""
ChartCandleService — pre-aggregated OHLCV store for fast chart rendering.

Architecture
────────────
Each incoming raw bar (from ATAS adapter history) is immediately aggregated
into `chart_candles` for every registered timeframe.  The UI never aggregates
on load; it only reads pre-computed OHLCV rows.  This makes chart loads
sub-100 ms regardless of window size.

Incremental update (on new raw bars):
    raw_bar → align to target tf bucket → upsert chart_candle

Historical backfill (one-shot or scheduled):
    scan existing raw bars for a symbol → aggregate into all timeframes

Data layout
───────────
One row per (symbol, timeframe, started_at) — the primary key is the
bucket start, which is deterministic: NQ + 1m + 2025-03-20T20:52:00Z
means the 1-minute bucket that starts at 20:52 UTC.

Supported timeframes
────────────────────
MIN_1 | MIN_5 | MIN_15 | MIN_30 | HOUR_1 | HOUR_4
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._replay import ChartCandle

if TYPE_CHECKING:
    from atas_market_structure.repository import AnalysisRepository


# All timeframes written by the service
ALL_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MIN_1,
    Timeframe.MIN_5,
    Timeframe.MIN_15,
    Timeframe.MIN_30,
    Timeframe.HOUR_1,
    Timeframe.HOUR_4,
]

# Map timeframe → number of seconds per bucket
_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.MIN_1:  60,
    Timeframe.MIN_5:  300,
    Timeframe.MIN_15: 900,
    Timeframe.MIN_30: 1800,
    Timeframe.HOUR_1: 3600,
    Timeframe.HOUR_4: 14400,
}


def _floor(dt: datetime, tf: Timeframe) -> datetime:
    """Return the bucket start (UTC) for datetime `dt` in timeframe `tf`.

    If `dt` has no timezone info it is assumed to be UTC — this matches the
    assumption that all incoming timestamps are UTC.
    """
    ts = int(dt.timestamp())
    bucket = _TF_SECONDS[tf]
    floored = (ts // bucket) * bucket
    return datetime.fromtimestamp(floored, tz=UTC)


def _bucket_end(start: datetime, tf: Timeframe) -> datetime:
    """Return the bucket end (exclusive) for a bucket start."""
    return start + timedelta(seconds=_TF_SECONDS[tf])


class ChartCandleService:
    """
    Write-once-then-update aggregation engine for chart candles.

    The service is stateless — it reads from the repository and writes back.
    It is safe to call `upsert_from_raw_bars` repeatedly with the same
    source data because the ON CONFLICT clause keeps aggregate values correct.
    """

    def __init__(self, repository: "AnalysisRepository") -> None:
        self._repo = repository

    # ─── Incremental (live) upsert ─────────────────────────────────────────────

    def upsert_from_raw_bars(
        self,
        symbol: str,
        bars: list[dict],
        source_tf: Timeframe,
    ) -> dict[Timeframe, int]:
        """
        Aggregate raw bars into all registered timeframes and upsert.

        Args
        ---
        symbol : instrument symbol, e.g. "NQ"
        bars   : list of dicts with keys
                 started_at, ended_at, open, high, low, close,
                 volume (int|None), delta (int|None),
                 bid_volume (int|None), ask_volume (int|None)
        source_tf : native timeframe of the source bars (used to pick the
                    coarsest source that fits each target tf)

        Returns
        -------
        dict[Timeframe, int] — candles written per timeframe
        """
        written: dict[Timeframe, int] = defaultdict(int)

        for tf in ALL_TIMEFRAMES:
            # We aggregate every target tf; ON CONFLICT handles idempotency.
            # Downsampling (source=5m, target=1m) is allowed and will
            # simply produce one output candle per source bar.
            candles = self._aggregate_into_tf(symbol, tf, bars)
            if candles:
                self._repo.upsert_chart_candles(candles)
                written[tf] = len(candles)

        return dict(written)

    def upsert_chart_candles(self, candles: list[ChartCandle]) -> int:
        """Direct upsert of already-aggregated ChartCandle objects."""
        if not candles:
            return 0
        return self._repo.upsert_chart_candles(candles)

    # ─── Aggregation helper ────────────────────────────────────────────────────

    def _aggregate_into_tf(
        self,
        symbol: str,
        tf: Timeframe,
        bars: list[dict],
    ) -> list[ChartCandle]:
        """
        Re-sample a list of raw bars into timeframe `tf` and return ChartCandle objects.
        """
        if not bars:
            return []

        # Group source bars by target bucket
        buckets: dict[datetime, list[dict]] = defaultdict(list)
        for bar in bars:
            started = bar.get("started_at")
            if isinstance(started, str):
                started = datetime.fromisoformat(started.replace("Z", "+00:00")).astimezone(UTC)
            elif not isinstance(started, datetime) or started is None:
                continue
            # Guard against naive datetimes: if no tzinfo, assume local and convert.
            started = started.astimezone(UTC)
            bucket_start = _floor(started, tf)
            buckets[bucket_start].append(bar)

        now = datetime.now(tz=UTC)
        candles: list[ChartCandle] = []

        for bucket_start, bucket_bars in sorted(buckets.items()):
            raw_first = bucket_bars[0]["started_at"]
            if isinstance(raw_first, str):
                raw_first = datetime.fromisoformat(raw_first.replace("Z", "+00:00")).astimezone(UTC)
            bucket_start = _floor(raw_first, tf)
            bucket_end = _bucket_end(bucket_start, tf)

            open_  = bucket_bars[0].get("open")  or 0.0
            high   = max((b.get("high")  or 0.0) for b in bucket_bars)
            low    = min((b.get("low")   or 0.0) for b in bucket_bars)
            close  = bucket_bars[-1].get("close") or 0.0
            volume = sum(int(b.get("volume")  or 0) for b in bucket_bars)
            delta  = sum(int(b.get("delta")   or 0) for b in bucket_bars)
            # tick_volume: approximate with bar count if not available
            tick_volume = len(bucket_bars)

            candles.append(
                ChartCandle(
                    symbol=symbol,
                    timeframe=tf,
                    started_at=bucket_start,
                    ended_at=bucket_end,
                    source_started_at=raw_first.astimezone(UTC),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    tick_volume=tick_volume,
                    delta=delta,
                    updated_at=now,
                )
            )

        return candles

    # ─── Backfill from existing history ──────────────────────────────────────

    def backfill_from_ingestions(
        self,
        symbol: str,
        target_timeframes: list[Timeframe] | None = None,
        limit_ingestions: int = 500,
    ) -> dict[Timeframe, int]:
        """
        Scan existing `adapter_history_bars` ingestions for `symbol` and
        aggregate them into `chart_candles`.

        This is idempotent — re-running it simply refreshes any updated bars.
        """
        if target_timeframes is None:
            target_timeframes = ALL_TIMEFRAMES

        stored = self._repo.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol=symbol,
            limit=limit_ingestions,
        )

        written: dict[Timeframe, int] = defaultdict(int)

        for st in stored:
            payload = st.observed_payload
            if not payload:
                continue
            # Skip payloads that are clearly not history bars
            if payload.get("message_type") != "history_bars":
                continue
            bars_raw = payload.get("bars") or []
            if not bars_raw:
                continue

            source_tf_value = payload.get("bar_timeframe")
            if not source_tf_value:
                continue
            try:
                source_tf = Timeframe(source_tf_value)
            except ValueError:
                continue

            for tf in target_timeframes:
                candles = self._aggregate_into_tf(symbol, tf, bars_raw)
                if candles:
                    self._repo.upsert_chart_candles(candles)
                    written[tf] += len(candles)

        return dict(written)

    # ─── Read (used by workbench build flow) ──────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list[ChartCandle]:
        """Return pre-aggregated chart candles for the UI."""
        return self._repo.list_chart_candles(
            symbol=symbol,
            timeframe=timeframe.value,
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )

    def has_candles(self, symbol: str, timeframe: Timeframe) -> bool:
        """Return True if we have any chart candles for this symbol/tf."""
        return self._repo.count_chart_candles(symbol, timeframe.value) > 0
