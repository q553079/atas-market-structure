"""
ChartCandleService — pre-aggregated OHLCV store for fast chart rendering.

Architecture
────────────
Each incoming raw bar (from ATAS adapter history) is immediately aggregated
into `chart_candles` for its native timeframe and any coarser timeframes.
The UI never aggregates on load; it only reads pre-computed OHLCV rows.
This makes chart loads sub-100 ms regardless of window size.

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
import logging
from typing import TYPE_CHECKING

from atas_market_structure.history_payload_quality import history_payload_chart_path_verdict
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
_DISPLAY_PRICE_EPSILON = 1e-6
LOGGER = logging.getLogger(__name__)


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


def _can_aggregate_source_into_target(source_tf: Timeframe, target_tf: Timeframe) -> bool:
    """Only allow same-timeframe or fine-to-coarse aggregation."""
    return _TF_SECONDS[target_tf] >= _TF_SECONDS[source_tf]


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
            if not _can_aggregate_source_into_target(source_tf, tf):
                continue
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
            trusted_for_chart_path, _ = history_payload_chart_path_verdict(payload)
            if not trusted_for_chart_path:
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
                if not _can_aggregate_source_into_target(source_tf, tf):
                    continue
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
        candles = self._repo.list_chart_candles(
            symbol=symbol,
            timeframe=timeframe.value,
            window_start=window_start,
            window_end=window_end,
            limit=limit,
        )
        return self.sanitize_candles_for_display(candles)

    def has_candles(self, symbol: str, timeframe: Timeframe) -> bool:
        """Return True if we have any chart candles for this symbol/tf."""
        return self._repo.count_chart_candles(symbol, timeframe.value) > 0

    @classmethod
    def sanitize_candles_for_display(cls, candles: list[ChartCandle]) -> list[ChartCandle]:
        if not candles:
            return []

        ordered = sorted(candles, key=lambda item: item.started_at)
        prev_traded_close: list[float | None] = []
        last_traded_close: float | None = None
        for candle in ordered:
            prev_traded_close.append(last_traded_close)
            if cls._is_structurally_valid_candle(candle) and int(candle.volume or 0) > 0:
                last_traded_close = float(candle.close)

        next_traded_close: list[float | None] = [None] * len(ordered)
        upcoming_traded_close: float | None = None
        for index in range(len(ordered) - 1, -1, -1):
            next_traded_close[index] = upcoming_traded_close
            candle = ordered[index]
            if cls._is_structurally_valid_candle(candle) and int(candle.volume or 0) > 0:
                upcoming_traded_close = float(candle.close)

        sanitized: list[ChartCandle] = []
        dropped = 0
        for index, candle in enumerate(ordered):
            if cls._is_displayable_candle(
                candle,
                prev_trade_close=prev_traded_close[index],
                next_trade_close=next_traded_close[index],
            ):
                sanitized.append(candle)
                continue
            dropped += 1

        if dropped > 0:
            LOGGER.warning("ChartCandleService: dropped %s suspect historical candles from display path.", dropped)
        return sanitized

    @classmethod
    def _is_displayable_candle(
        cls,
        candle: ChartCandle,
        *,
        prev_trade_close: float | None,
        next_trade_close: float | None,
    ) -> bool:
        if not cls._is_structurally_valid_candle(candle):
            return False

        if int(candle.volume or 0) > 0:
            return True

        if not cls._is_flat_zero_volume_candle(candle):
            return False

        close_price = float(candle.close)
        epsilon = _DISPLAY_PRICE_EPSILON
        for reference_close in (prev_trade_close, next_trade_close):
            if reference_close is not None and abs(close_price - reference_close) <= epsilon:
                return True
        return False

    @classmethod
    def _is_structurally_valid_candle(cls, candle: ChartCandle) -> bool:
        epsilon = _DISPLAY_PRICE_EPSILON
        open_price = float(candle.open)
        high_price = float(candle.high)
        low_price = float(candle.low)
        close_price = float(candle.close)
        if high_price + epsilon < low_price:
            return False
        if high_price + epsilon < max(open_price, close_price):
            return False
        if low_price - epsilon > min(open_price, close_price):
            return False
        return True

    @classmethod
    def _is_flat_zero_volume_candle(cls, candle: ChartCandle) -> bool:
        epsilon = _DISPLAY_PRICE_EPSILON
        open_price = float(candle.open)
        high_price = float(candle.high)
        low_price = float(candle.low)
        close_price = float(candle.close)
        return (
            abs(open_price - close_price) <= epsilon
            and abs(high_price - low_price) <= epsilon
            and abs(open_price - high_price) <= epsilon
            and abs(close_price - low_price) <= epsilon
        )
