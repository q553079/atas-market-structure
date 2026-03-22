"""Lightweight market regime monitor.

Infers the current market regime (trending, ranging, volatile, quiet) from
replay candles and event annotations without external API calls.

Also maintains a lightweight rolling per-instrument bar cache so low-latency
adapter ingestion can query adaptive thresholds in O(1) for repeated requests
within the same minute.

On every bar ingestion (continuous or history-loaded), this module writes
OHLCV into the `chart_candles` table ONLY for the native/source timeframe.
Upper-timeframe aggregation is a separate downstream process that aggregates
from finer to coarser timeframes — never the reverse.

Consumers:
- strategy_selection_engine (session_scope filter + regime-aware ranking)
- ai_review_services (prompt context)
- adapter_bridge (dynamic adaptive event filtering)
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from atas_market_structure.models import (
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    ChartCandle,
    ReplayChartBar,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.models._enums import Timeframe

if TYPE_CHECKING:
    from atas_market_structure.repository import AnalysisRepository

LOGGER = logging.getLogger(__name__)

# Timeframe resolution constants for UTC bucketing.
_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.MIN_1:  60,
    Timeframe.MIN_5:  300,
    Timeframe.MIN_15: 900,
    Timeframe.MIN_30: 1800,
    Timeframe.HOUR_1: 3600,
    Timeframe.HOUR_4: 14400,
    Timeframe.DAY_1:  86400,
}


def _floor(dt: datetime, tf: Timeframe) -> datetime:
    ts = int(dt.timestamp())
    return datetime.fromtimestamp((ts // _TF_SECONDS[tf]) * _TF_SECONDS[tf], tz=UTC)


@dataclass
class RegimeAssessment:
    """Machine-readable market regime snapshot."""
    regime: str  # "trending_up", "trending_down", "ranging", "volatile", "quiet"
    confidence: float  # 0.0 to 1.0
    atr_estimate: float  # average true range over sampled candles
    directional_bias: str  # "bullish", "bearish", "neutral"
    volatility_state: str  # "expanding", "contracting", "stable"
    evidence: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "confidence": round(self.confidence, 2),
            "atr_estimate": round(self.atr_estimate, 4),
            "directional_bias": self.directional_bias,
            "volatility_state": self.volatility_state,
            "evidence": self.evidence,
            "details": self.details,
        }


@dataclass(frozen=True)
class DynamicThresholds:
    """Adaptive threshold snapshot derived from recent rolling bars."""

    instrument_symbol: str
    minute_bucket: datetime
    lookback_bars: int
    bars_available: int
    current_atr_ticks: float
    baseline_bar_volume: float
    baseline_abs_delta: float
    current_bar_range_ticks: float
    volatility_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_symbol": self.instrument_symbol,
            "minute_bucket": self.minute_bucket.isoformat(),
            "lookback_bars": self.lookback_bars,
            "bars_available": self.bars_available,
            "current_atr_ticks": round(self.current_atr_ticks, 4),
            "baseline_bar_volume": round(self.baseline_bar_volume, 2),
            "baseline_abs_delta": round(self.baseline_abs_delta, 2),
            "current_bar_range_ticks": round(self.current_bar_range_ticks, 4),
            "volatility_ratio": round(self.volatility_ratio, 4),
        }


@dataclass
class _InstrumentRollingBar:
    started_at: datetime
    ended_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    delta: int = 0


class RegimeMonitor:
    """Infers market regime and serves cached adaptive thresholds from rolling bars.

    On every bar ingestion, OHLCV rows are written to the `chart_candles` table
    for the native/source timeframe only.  Upper-timeframe aggregation is a
    separate downstream process that aggregates from finer to coarser timeframes.
    """

    def __init__(self, repository: "AnalysisRepository | None" = None) -> None:
        self._repository = repository
        self._rolling_bars: dict[str, deque[_InstrumentRollingBar]] = {}
        self._dynamic_threshold_cache: dict[tuple[str, datetime], DynamicThresholds] = {}
        self._max_cached_bars = 512

    def assess(
        self,
        snapshot: ReplayWorkbenchSnapshotPayload,
        *,
        lookback_bars: int = 20,
    ) -> RegimeAssessment:
        candles = snapshot.candles
        if not candles:
            return RegimeAssessment(
                regime="quiet",
                confidence=0.0,
                atr_estimate=0.0,
                directional_bias="neutral",
                volatility_state="stable",
                evidence=["No candles available."],
            )

        sample = candles[-lookback_bars:] if len(candles) > lookback_bars else candles
        atr = self._compute_atr(sample)
        net_change = sample[-1].close - sample[0].open if sample else 0.0
        abs_change = abs(net_change)
        total_range = max(c.high for c in sample) - min(c.low for c in sample) if sample else 0.0

        higher_closes = sum(1 for i in range(1, len(sample)) if sample[i].close > sample[i - 1].close)
        lower_closes = len(sample) - 1 - higher_closes if len(sample) > 1 else 0
        close_ratio = higher_closes / max(1, higher_closes + lower_closes)

        if close_ratio >= 0.65:
            directional_bias = "bullish"
        elif close_ratio <= 0.35:
            directional_bias = "bearish"
        else:
            directional_bias = "neutral"

        mid = len(sample) // 2
        if mid > 0:
            early_atr = self._compute_atr(sample[:mid])
            late_atr = self._compute_atr(sample[mid:])
            if late_atr > early_atr * 1.3:
                volatility_state = "expanding"
            elif late_atr < early_atr * 0.7:
                volatility_state = "contracting"
            else:
                volatility_state = "stable"
        else:
            volatility_state = "stable"

        evidence: list[str] = []
        if total_range > 0 and abs_change / total_range > 0.6:
            regime = "trending_up" if net_change > 0 else "trending_down"
            confidence = min(1.0, abs_change / total_range)
            evidence.append(f"net_change/total_range={abs_change / total_range:.2f}")
        elif atr > 0 and total_range / (atr * len(sample)) > 1.5:
            regime = "volatile"
            confidence = min(1.0, total_range / (atr * len(sample)))
            evidence.append(f"range_expansion={total_range / (atr * len(sample)):.2f}")
        elif atr > 0 and abs_change / (atr * len(sample)) < 0.15:
            regime = "quiet"
            confidence = 0.6
            evidence.append("Low directional movement relative to ATR.")
        else:
            regime = "ranging"
            confidence = 0.5
            evidence.append("No strong trend or volatility signal.")

        evidence.append(f"atr={atr:.4f}")
        evidence.append(f"close_ratio={close_ratio:.2f}")
        evidence.append(f"volatility_state={volatility_state}")

        events = snapshot.event_annotations
        if events:
            event_density = len(events) / max(1, len(sample))
            evidence.append(f"event_density={event_density:.2f}")
            if event_density > 2.0:
                evidence.append("High event density — active market.")

        return RegimeAssessment(
            regime=regime,
            confidence=confidence,
            atr_estimate=atr,
            directional_bias=directional_bias,
            volatility_state=volatility_state,
            evidence=evidence,
            details={
                "sample_bar_count": len(sample),
                "net_change": round(net_change, 4),
                "total_range": round(total_range, 4),
                "higher_close_count": higher_closes,
                "lower_close_count": lower_closes,
            },
        )

    def ingest_history_bars(self, payload: AdapterHistoryBarsPayload) -> None:
        symbol = payload.instrument.symbol.upper()
        bars = self._rolling_bars.setdefault(symbol, deque(maxlen=self._max_cached_bars))
        by_start = {item.started_at: item for item in bars}
        for item in payload.bars:
            by_start[item.started_at] = _InstrumentRollingBar(
                started_at=item.started_at.astimezone(UTC),
                ended_at=item.ended_at.astimezone(UTC),
                open=item.open,
                high=item.high,
                low=item.low,
                close=item.close,
                volume=item.volume or 0,
                delta=item.delta or 0,
            )
        merged = sorted(by_start.values(), key=lambda item: item.started_at)
        self._rolling_bars[symbol] = deque(merged[-self._max_cached_bars :], maxlen=self._max_cached_bars)
        self._evict_cache_for_symbol(symbol)

    def ingest_continuous_state(self, payload: AdapterContinuousStatePayload) -> None:
        symbol = payload.instrument.symbol.upper()
        bars = self._rolling_bars.setdefault(symbol, deque(maxlen=self._max_cached_bars))
        bucket_start = payload.observed_window_end.astimezone(UTC).replace(second=0, microsecond=0)
        bucket_end = bucket_start.replace(second=59)
        price_state = payload.price_state
        volume = payload.trade_summary.volume or 0
        delta = payload.trade_summary.net_delta or 0

        if bars and bars[-1].started_at == bucket_start:
            current = bars[-1]
            current.high = max(current.high, price_state.local_range_high, price_state.last_price)
            current.low = min(current.low, price_state.local_range_low, price_state.last_price)
            current.close = price_state.last_price
            current.ended_at = max(current.ended_at, payload.observed_window_end.astimezone(UTC), bucket_end)
            current.volume += volume
            current.delta += delta
        else:
            open_price = bars[-1].close if bars else price_state.last_price
            bars.append(
                _InstrumentRollingBar(
                    started_at=bucket_start,
                    ended_at=max(payload.observed_window_end.astimezone(UTC), bucket_end),
                    open=open_price,
                    high=max(price_state.local_range_high, price_state.last_price),
                    low=min(price_state.local_range_low, price_state.last_price),
                    close=price_state.last_price,
                    volume=volume,
                    delta=delta,
                )
            )
        self._evict_cache_for_symbol(symbol)
        if bars:
            bar = bars[-1]
            self._persist_bar(
                symbol=symbol,
                started_at=bar.started_at,
                ended_at=bar.ended_at,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                delta=bar.delta,
                timeframe=Timeframe.MIN_1,
            )

    def get_dynamic_thresholds(
        self,
        instrument_symbol: str,
        current_timestamp: datetime,
        *,
        tick_size: float,
        lookback_bars: int = 20,
        fallback_price_range: float | None = None,
        fallback_volume: int | None = None,
        fallback_abs_delta: int | None = None,
    ) -> DynamicThresholds:
        symbol = instrument_symbol.upper()
        minute_bucket = current_timestamp.astimezone(UTC).replace(second=0, microsecond=0)
        cache_key = (symbol, minute_bucket)
        cached = self._dynamic_threshold_cache.get(cache_key)
        if cached is not None:
            return cached

        bars = list(self._rolling_bars.get(symbol, ()))
        sample = bars[-lookback_bars:] if len(bars) > lookback_bars else bars

        if sample:
            atr_ticks = self._compute_atr_ticks(sample, tick_size)
            avg_volume = sum(max(0, item.volume) for item in sample) / len(sample)
            avg_abs_delta = sum(abs(item.delta) for item in sample) / len(sample)
            current_range_ticks = max(0.0, (sample[-1].high - sample[-1].low) / max(tick_size, 1e-9))
        else:
            atr_ticks = max(1.0, (fallback_price_range or 0.0) / max(tick_size, 1e-9))
            avg_volume = float(max(0, fallback_volume or 0))
            avg_abs_delta = float(max(0, fallback_abs_delta or 0))
            current_range_ticks = atr_ticks

        thresholds = DynamicThresholds(
            instrument_symbol=symbol,
            minute_bucket=minute_bucket,
            lookback_bars=lookback_bars,
            bars_available=len(sample),
            current_atr_ticks=max(1.0, atr_ticks),
            baseline_bar_volume=max(1.0, avg_volume),
            baseline_abs_delta=max(1.0, avg_abs_delta),
            current_bar_range_ticks=max(0.0, current_range_ticks),
            volatility_ratio=max(0.1, current_range_ticks / max(1.0, atr_ticks)),
        )
        self._dynamic_threshold_cache[cache_key] = thresholds
        self._trim_threshold_cache(symbol=symbol, keep_after=minute_bucket)
        return thresholds

    @staticmethod
    def _compute_atr(candles: list[ReplayChartBar]) -> float:
        if not candles:
            return 0.0
        true_ranges: list[float] = []
        previous_close: float | None = None
        for candle in candles:
            bar_range = candle.high - candle.low
            if previous_close is None:
                true_range = bar_range
            else:
                true_range = max(
                    bar_range,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            true_ranges.append(max(0.0, true_range))
            previous_close = candle.close
        return sum(true_ranges) / len(true_ranges)

    @staticmethod
    def _compute_atr_ticks(candles: list[_InstrumentRollingBar], tick_size: float) -> float:
        if not candles or tick_size <= 0:
            return 0.0
        true_ranges: list[float] = []
        previous_close: float | None = None
        for candle in candles:
            bar_range = candle.high - candle.low
            if previous_close is None:
                true_range = bar_range
            else:
                true_range = max(
                    bar_range,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            true_ranges.append(max(0.0, true_range) / tick_size)
            previous_close = candle.close
        return sum(true_ranges) / len(true_ranges)

    def _evict_cache_for_symbol(self, symbol: str) -> None:
        stale_keys = [key for key in self._dynamic_threshold_cache if key[0] == symbol]
        for key in stale_keys:
            self._dynamic_threshold_cache.pop(key, None)

    def _trim_threshold_cache(self, *, symbol: str, keep_after: datetime) -> None:
        cutoff = keep_after - timedelta(minutes=3)
        stale_keys = [key for key in self._dynamic_threshold_cache if key[0] == symbol and key[1] < cutoff]
        for key in stale_keys:
            self._dynamic_threshold_cache.pop(key, None)

    # ─── Real-time chart-candle persistence ────────────────────────────────────

    def _persist_bar(
        self,
        symbol: str,
        started_at: datetime,
        ended_at: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        delta: int,
        timeframe: Timeframe,
    ) -> None:
        """Write one raw bar into chart_candles for its native timeframe only.

        This is used for continuous-state ingestion where the regime monitor
        maintains its own rolling bars at whatever timeframe the adapter sends.
        For history ingestion, use `persist_history_bars_native` instead.
        """
        if self._repository is None:
            return

        now = datetime.now(tz=UTC)
        bucket = _floor(started_at, timeframe)
        bucket_end = bucket + timedelta(seconds=_TF_SECONDS[timeframe])
        candle = ChartCandle(
            symbol=symbol,
            timeframe=timeframe,
            started_at=bucket,
            ended_at=bucket_end,
            source_started_at=started_at,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            tick_volume=1,
            delta=delta,
            updated_at=now,
        )
        self._repository.upsert_chart_candles([candle])

    def persist_history_bars_native(
        self,
        symbol: str,
        bars: list[dict],
        native_timeframe: Timeframe,
    ) -> int:
        """Bulk-persist history bars for ONE native timeframe only.

        This replaces the old behaviour that projected every raw bar into all
        timeframes (1m × 5m × 15m × 30m × 1h × 4h).  Upper-timeframe candles
        must be produced by a separate upward-aggregation pass that reads from
        finer timeframes.

        Aggregation rules (strict direction):
        - 1m  → 5m, 15m, 30m, 1h, 4h   (OK: fine to coarse)
        - 5m  → 15m, 30m, 1h, 4h       (OK)
        - 15m → 30m, 1h, 4h             (OK)
        - 30m → 1h, 4h                  (OK)
        - 1h  → 4h                      (OK)
        - 4h  → daily, weekly, monthly  (OK)

        Reverse aggregation (coarse to fine) is NOT permitted.
        """
        if self._repository is None or not bars:
            return 0

        tf_seconds = _TF_SECONDS.get(native_timeframe)
        if tf_seconds is None:
            LOGGER.warning("[ChartCandle] Unknown timeframe %s for %s — skipping.", native_timeframe, symbol)
            return 0

        now = datetime.now(tz=UTC)
        candles: list[ChartCandle] = []
        for bar in bars:
            raw_started = bar.get("started_at")
            if isinstance(raw_started, str):
                raw_started = datetime.fromisoformat(raw_started.replace("Z", "+00:00"))
            elif not isinstance(raw_started, datetime):
                continue
            started = raw_started.astimezone(UTC)
            ended = bar.get("ended_at")
            if isinstance(ended, str):
                ended = datetime.fromisoformat(ended.replace("Z", "+00:00")).astimezone(UTC)
            elif isinstance(ended, datetime):
                ended = ended.astimezone(UTC)
            else:
                ended = started + timedelta(seconds=tf_seconds)

            bucket = _floor(started, native_timeframe)
            candles.append(
                ChartCandle(
                    symbol=symbol,
                    timeframe=native_timeframe,
                    started_at=bucket,
                    ended_at=bucket + timedelta(seconds=tf_seconds),
                    source_started_at=started,
                    open=bar.get("open") or 0.0,
                    high=bar.get("high") or 0.0,
                    low=bar.get("low") or 0.0,
                    close=bar.get("close") or 0.0,
                    volume=int(bar.get("volume") or 0),
                    tick_volume=1,
                    delta=int(bar.get("delta") or 0),
                    updated_at=now,
                )
            )

        self._repository.upsert_chart_candles(candles)
        LOGGER.info(
            "[ChartCandle] persisted %d native candles (%s) for %s",
            len(candles),
            native_timeframe.value,
            symbol,
        )
        return len(candles)
