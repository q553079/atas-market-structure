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

/** 与 K 线数据一致：按 UTC 显示，便于与交易所/回放 UTC 时刻对齐 */
export function formatAxisTime(value) {
  const date = new Date(value);
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  return `${month}/${day} ${hour}:${minute} UTC`;
}

export function clampNumber(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function buildChartViewportKey(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return "";
  }
  const source = snapshot.source && typeof snapshot.source === "object" ? snapshot.source : {};
  const instrument = snapshot.instrument && typeof snapshot.instrument === "object" ? snapshot.instrument : {};
  const chartInstanceId = String(source.chart_instance_id || snapshot.chart_instance_id || "").trim();
  const contractSymbol = String(instrument.contract_symbol || snapshot.contract_symbol || "").trim().toUpperCase();
  const instrumentSymbol = String(snapshot.instrument_symbol || instrument.symbol || "").trim().toUpperCase();
  const timeframe = String(snapshot.display_timeframe || snapshot.timeframe || "").trim();
  return [
    chartInstanceId || "no-chart",
    contractSymbol || "no-contract",
    instrumentSymbol || "no-symbol",
    timeframe || "no-timeframe",
  ].join("|");
}

export function snapshotChartViewForRegistry(totalCount, chartView, options = {}) {
  if (!totalCount || !chartView) {
    return null;
  }
  const clampedView = clampChartView(totalCount, chartView.startIndex, chartView.endIndex, chartView);
  const spanBars = Math.max(1, clampedView.endIndex - clampedView.startIndex + 1);
  const rightPadding = Math.max(0, Math.max(0, totalCount - 1) - clampedView.endIndex);
  return {
    startIndex: clampedView.startIndex,
    endIndex: clampedView.endIndex,
    yMin: clampedView.yMin ?? null,
    yMax: clampedView.yMax ?? null,
    totalCount,
    spanBars,
    rightPadding,
    followLatest: rightPadding <= Math.max(6, Math.ceil(spanBars * 0.12)),
    lastVisibleEndedAt: options.lastVisibleEndedAt || null,
    savedAt: new Date().toISOString(),
  };
}

export function restoreChartViewFromRegistry(totalCount, savedView, options = {}) {
  if (!totalCount || !savedView) {
    return null;
  }
  const safeTotalCount = Math.max(1, Number(totalCount) || 0);
  const savedTotalCount = Math.max(1, Number(savedView.totalCount) || safeTotalCount);
  const requestedSpan = Math.max(
    12,
    Math.min(
      safeTotalCount,
      Number(savedView.spanBars)
      || (Number(savedView.endIndex) - Number(savedView.startIndex) + 1)
      || Math.min(180, safeTotalCount),
    ),
  );
  const followLatest = options.forceFollowLatest === true || savedView.followLatest !== false;
  if (followLatest) {
    const rightPadding = clampNumber(Number(savedView.rightPadding) || 4, 2, 12);
    const targetEnd = Math.max(requestedSpan - 1, Math.max(0, safeTotalCount - 1 - rightPadding));
    return clampChartView(
      safeTotalCount,
      targetEnd - requestedSpan + 1,
      targetEnd,
      savedView,
    );
  }
  const growth = safeTotalCount - savedTotalCount;
  return clampChartView(
    safeTotalCount,
    Number(savedView.startIndex ?? 0) + growth,
    Number(savedView.endIndex ?? (requestedSpan - 1)) + growth,
    savedView,
  );
}

function toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function appendBoundedOverlayPrices(target, values, candleMin, candleMax, maxDistance) {
  (Array.isArray(values) ? values : [values]).forEach((value) => {
    const numeric = toFiniteNumber(value);
    if (numeric == null) {
      return;
    }
    if (numeric < candleMin - maxDistance || numeric > candleMax + maxDistance) {
      return;
    }
    target.push(numeric);
  });
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

  const candlePrices = [];
  visibleCandles.forEach((bar) => {
    const high = toFiniteNumber(bar.high);
    const low = toFiniteNumber(bar.low);
    if (high != null) candlePrices.push(high);
    if (low != null) candlePrices.push(low);
  });
  if (!candlePrices.length) {
    return { min: 0, max: 1 };
  }

  const candleMin = Math.min(...candlePrices);
  const candleMax = Math.max(...candlePrices);
  const candleSpan = Math.max(candleMax - candleMin, Math.max(Math.abs(candleMax) * 0.002, 2));
  const maxDistance = Math.max(candleSpan * 4, Math.max(Math.abs(candleMax) * 0.002, 8));
  const overlayPrices = [];

  events.filter((event) => withinVisibleWindow(event.observed_at)).forEach((event) => {
    appendBoundedOverlayPrices(overlayPrices, [event.price, event.price_low, event.price_high], candleMin, candleMax, maxDistance);
  });
  focusRegions.forEach((region) => {
    if (withinVisibleWindow(region.started_at) || withinVisibleWindow(region.ended_at || visibleCandles[visibleCandles.length - 1].ended_at)) {
      appendBoundedOverlayPrices(overlayPrices, [region.price_low, region.price_high], candleMin, candleMax, maxDistance);
    }
  });
  manualRegions.forEach((region) => {
    if (withinVisibleWindow(region.started_at) || withinVisibleWindow(region.ended_at)) {
      appendBoundedOverlayPrices(overlayPrices, [region.price_low, region.price_high], candleMin, candleMax, maxDistance);
    }
  });
  operatorEntries.forEach((entry) => {
    if (withinVisibleWindow(entry.executed_at)) {
      appendBoundedOverlayPrices(
        overlayPrices,
        [entry.entry_price, entry.stop_price ?? entry.entry_price, entry.target_price ?? entry.entry_price],
        candleMin,
        candleMax,
        maxDistance,
      );
    }
  });
  bubbleMarks.forEach((bubble) => {
    appendBoundedOverlayPrices(
      overlayPrices,
      [
        bubble.topVolumeLevel?.price,
        bubble.topDeltaLevel?.price,
        bubble.candleLow,
        bubble.candleHigh,
      ],
      candleMin,
      candleMax,
      maxDistance,
    );
  });

  const prices = [...candlePrices, ...overlayPrices];
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
      const restoredView = restoreChartViewFromRegistry(totalCount, state.pendingChartViewRestore);
      state.chartView = restoredView || createDefaultChartView(totalCount);
      state.pendingChartViewRestore = null;
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
