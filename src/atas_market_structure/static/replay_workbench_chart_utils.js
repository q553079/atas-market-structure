export function clampChartView(totalCount, startIndex, endIndex, baseView = null) {
  const maxIndex = Math.max(0, totalCount - 1);
  const clampedStart = Math.max(0, Math.min(startIndex, maxIndex));
  const clampedEnd = Math.max(clampedStart, Math.min(endIndex, maxIndex));
  return {
    startIndex: clampedStart,
    endIndex: clampedEnd,
    yMin: baseView?.yMin ?? null,
    yMax: baseView?.yMax ?? null,
  };
}

export function formatAxisTime(value) {
  const date = new Date(value);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hour}:${minute}`;
}

export function clampNumber(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function derivePriceEnvelope(visibleCandles, events = [], focusRegions = [], manualRegions = [], operatorEntries = [], bubbleMarks = []) {
  if (!visibleCandles.length) {
    return { min: 0, max: 1 };
  }
  const visibleStartTime = new Date(visibleCandles[0].started_at).getTime();
  const visibleEndTime = new Date(visibleCandles[visibleCandles.length - 1].ended_at).getTime();
  const withinVisibleWindow = (value) => {
    const timestamp = new Date(value).getTime();
    return timestamp >= visibleStartTime && timestamp <= visibleEndTime;
  };

  const prices = [];
  visibleCandles.forEach((bar) => prices.push(bar.high, bar.low));
  events.filter((event) => withinVisibleWindow(event.observed_at)).forEach((event) => {
    if (event.price != null) prices.push(event.price);
    if (event.price_low != null) prices.push(event.price_low);
    if (event.price_high != null) prices.push(event.price_high);
  });
  focusRegions.forEach((region) => {
    if (withinVisibleWindow(region.started_at) || withinVisibleWindow(region.ended_at || visibleCandles[visibleCandles.length - 1].ended_at)) {
      prices.push(region.price_low, region.price_high);
    }
  });
  manualRegions.forEach((region) => {
    if (withinVisibleWindow(region.started_at) || withinVisibleWindow(region.ended_at)) {
      prices.push(region.price_low, region.price_high);
    }
  });
  operatorEntries.forEach((entry) => {
    if (withinVisibleWindow(entry.executed_at)) {
      prices.push(entry.entry_price, entry.stop_price ?? entry.entry_price, entry.target_price ?? entry.entry_price);
    }
  });
  bubbleMarks.forEach((bubble) => {
    if (bubble.topVolumeLevel?.price != null) {
      prices.push(Number(bubble.topVolumeLevel.price));
    }
    if (bubble.topDeltaLevel?.price != null) {
      prices.push(Number(bubble.topDeltaLevel.price));
    }
    if (bubble.candleLow != null) {
      prices.push(Number(bubble.candleLow));
    }
    if (bubble.candleHigh != null) {
      prices.push(Number(bubble.candleHigh));
    }
  });

  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const paddingPrice = Math.max((maxPrice - minPrice) * 0.08, 1);
  return {
    min: minPrice - paddingPrice,
    max: maxPrice + paddingPrice,
  };
}

export function computeEmaSeries(candles, period) {
  const alpha = 2 / (period + 1);
  let ema = null;
  return candles.map((bar) => {
    const close = Number(bar.close);
    ema = ema == null ? close : (close * alpha) + (ema * (1 - alpha));
    return ema;
  });
}

export function collectFootprintBubbles(snapshot, visibleStartTime, visibleEndTime) {
  const digest = snapshot?.raw_features?.history_footprint_digest;
  const topBars = Array.isArray(digest?.top_bars) ? digest.top_bars : [];
  const candleByStartedAt = new Map((snapshot?.candles || []).map((bar) => [bar.started_at, bar]));
  const visible = topBars.filter((item) => {
    const startedAt = item.started_at || item.startedAt;
    if (!startedAt) {
      return false;
    }
    const timestamp = new Date(startedAt).getTime();
    return timestamp >= visibleStartTime && timestamp <= visibleEndTime;
  });
  const maxBarVolume = Math.max(1, ...visible.map((item) => Number(item.bar_total_price_level_volume || item.volume || 0)));
  return visible.slice(0, 48).map((item) => {
    const startedAt = item.started_at || item.startedAt;
    const candle = candleByStartedAt.get(startedAt);
    return {
      startedAt,
      topVolumeLevel: item.top_volume_level || null,
      topDeltaLevel: item.top_delta_level || null,
      barVolume: Number(item.bar_total_price_level_volume || item.volume || 0),
      barDelta: Number(item.bar_abs_price_level_delta || Math.abs(item.delta || 0)),
      volumeRatio: Number(item.bar_total_price_level_volume || item.volume || 0) / maxBarVolume,
      candleLow: candle ? Number(candle.low) : null,
      candleHigh: candle ? Number(candle.high) : null,
      candleOpen: candle ? Number(candle.open) : null,
      candleClose: candle ? Number(candle.close) : null,
    };
  });
}

export function createChartViewHelpers({ state }) {
  function createDefaultChartView(totalCount) {
    const visibleBars = totalCount <= 180 ? totalCount : Math.min(totalCount, 180);
    const endIndex = Math.max(0, totalCount - 1);
    const startIndex = Math.max(0, endIndex - visibleBars + 1);
    return {
      startIndex,
      endIndex,
      yMin: null,
      yMax: null,
    };
  }

  function ensureChartView(snapshot, manualRegions = [], operatorEntries = []) {
    const totalCount = snapshot?.candles?.length || 0;
    if (!totalCount) {
      state.chartView = null;
      state.chartMetrics = null;
      return null;
    }
    if (!state.chartView) {
      state.chartView = createDefaultChartView(totalCount);
    }
    state.chartView = clampChartView(totalCount, state.chartView.startIndex, state.chartView.endIndex, state.chartView);
    const visibleCandles = snapshot.candles.slice(state.chartView.startIndex, state.chartView.endIndex + 1);
    const envelope = derivePriceEnvelope(
      visibleCandles,
      snapshot.event_annotations || [],
      snapshot.focus_regions || [],
      manualRegions,
      operatorEntries,
    );
    if (state.chartView.yMin == null || state.chartView.yMax == null || state.chartView.yMax <= state.chartView.yMin) {
      state.chartView.yMin = envelope.min;
      state.chartView.yMax = envelope.max;
    }
    return state.chartView;
  }

  return {
    ensureChartView,
    createDefaultChartView,
  };
}
