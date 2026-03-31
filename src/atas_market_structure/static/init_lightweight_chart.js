import { sanitizeReplayCandles } from "./replay_workbench_ui_utils.js";
import { isTimestampWithinBarBucket } from "./replay_workbench_live_time_policy.js";

let chartInstance = null;
let volumeChartInstance = null;
let candleSeries = null;
let volumeSeries = null;
let emaSeries = null;
let priceLineMap = {};
let priceLineCounter = 0;
let resizeObserver = null;
let syncingVisibleRange = false;
let lastDataSignature = "";
let lastChartDataset = null;
let lastUpdateType = "initial";
let livePreviewAnimationFrame = null;
let livePreviewState = null;
let livePreviewListener = null;

function getRenderableCandles(snapshot) {
  const normalized = sanitizeReplayCandles(snapshot?.candles || [], {
    context: "chart-render",
    log: false,
  });
  return suppressRenderableTailOutliers(normalized, snapshot);
}

function computeTailGuardMedian(numbers = []) {
  const values = numbers
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);
  if (!values.length) {
    return null;
  }
  const middle = Math.floor(values.length / 2);
  if (values.length % 2 === 0) {
    return (values[middle - 1] + values[middle]) / 2;
  }
  return values[middle];
}

function findNearestObservedBar(candles = [], startIndex = 0, direction = -1) {
  for (let index = startIndex; index >= 0 && index < candles.length; index += direction) {
    const bar = candles[index];
    if (bar && !isSyntheticGapBar(bar)) {
      return { bar, index };
    }
  }
  return { bar: null, index: -1 };
}

function buildTailOutlierStats(candles = [], index = 0) {
  const contextBars = [];
  for (let offset = Math.max(0, index - 12); offset <= Math.min(candles.length - 1, index + 6); offset += 1) {
    if (offset === index) {
      continue;
    }
    const bar = candles[offset];
    if (!bar || isSyntheticGapBar(bar)) {
      continue;
    }
    contextBars.push(bar);
  }
  const ranges = [];
  const closeMoves = [];
  let previousClose = null;
  contextBars.forEach((bar) => {
    const high = Number(bar?.high);
    const low = Number(bar?.low);
    const close = Number(bar?.close);
    if (Number.isFinite(high) && Number.isFinite(low)) {
      ranges.push(Math.max(0, high - low));
    }
    if (Number.isFinite(close) && Number.isFinite(previousClose)) {
      closeMoves.push(Math.abs(close - previousClose));
    }
    previousClose = Number.isFinite(close) ? close : previousClose;
  });
  const medianRange = computeTailGuardMedian(ranges);
  const medianMove = computeTailGuardMedian(closeMoves);
  return {
    medianRange,
    medianMove,
    maxRange: Math.max(
      4,
      Number.isFinite(medianRange) ? medianRange * 8 : 0,
      Number.isFinite(medianMove) ? medianMove * 16 : 0,
    ),
    maxDisplacement: Math.max(
      6,
      Number.isFinite(medianRange) ? medianRange * 6 : 0,
      Number.isFinite(medianMove) ? medianMove * 14 : 0,
    ),
    maxNeighborDrift: Math.max(
      2,
      Number.isFinite(medianRange) ? medianRange * 3 : 0,
      Number.isFinite(medianMove) ? medianMove * 6 : 0,
    ),
  };
}

function suppressRenderableTailOutliers(candles = [], snapshot = null) {
  if (!Array.isArray(candles) || candles.length < 3) {
    return candles;
  }
  const freshness = String(snapshot?.live_tail?.data_status?.freshness || "").toLowerCase();
  const guardedTailStart = Math.max(0, candles.length - 24);
  const nextCandles = [...candles];
  let suppressedCount = 0;

  for (let index = guardedTailStart; index < candles.length; index += 1) {
    const bar = candles[index];
    if (!bar || isSyntheticGapBar(bar)) {
      continue;
    }
    const open = Number(bar?.open);
    const high = Number(bar?.high);
    const low = Number(bar?.low);
    const close = Number(bar?.close);
    if (![open, high, low, close].every((value) => Number.isFinite(value))) {
      continue;
    }
    const stats = buildTailOutlierStats(candles, index);
    const range = Math.max(0, high - low);
    if (!(range > stats.maxRange)) {
      continue;
    }

    const previous = findNearestObservedBar(candles, index - 1, -1).bar;
    const next = findNearestObservedBar(candles, index + 1, 1).bar;
    const previousClose = Number(previous?.close);
    const nextClose = Number(next?.close);
    const anchorCandidates = [previousClose, nextClose].filter((value) => Number.isFinite(value));
    const anchorClose = computeTailGuardMedian(anchorCandidates);
    if (!Number.isFinite(anchorClose)) {
      continue;
    }
    const displacement = Math.max(
      Math.abs(open - anchorClose),
      Math.abs(high - anchorClose),
      Math.abs(low - anchorClose),
      Math.abs(close - anchorClose),
    );
    const neighborDrift = (
      Number.isFinite(previousClose) && Number.isFinite(nextClose)
        ? Math.abs(previousClose - nextClose)
        : 0
    );
    const isTailStale = freshness !== "fresh" && index >= candles.length - 4;
    const isIsolatedOutlier = displacement > stats.maxDisplacement && (
      (Number.isFinite(previousClose) && Number.isFinite(nextClose) && neighborDrift <= stats.maxNeighborDrift)
      || isTailStale
    );
    if (!isIsolatedOutlier) {
      continue;
    }

    const syntheticOpen = Number.isFinite(previousClose) ? previousClose : anchorClose;
    const syntheticClose = Number.isFinite(nextClose) ? nextClose : anchorClose;
    nextCandles[index] = {
      ...bar,
      open: syntheticOpen,
      high: Math.max(syntheticOpen, syntheticClose),
      low: Math.min(syntheticOpen, syntheticClose),
      close: syntheticClose,
      visual_suppressed_outlier: true,
    };
    suppressedCount += 1;
  }

  if (suppressedCount > 0) {
    console.warn(`chart-render: suppressed ${suppressedCount} suspicious tail candle(s)`);
  }
  return nextCandles;
}

function toChartTime(value) {
  if (typeof value === "string") {
    const ts = new Date(value).getTime();
    return Number.isFinite(ts) ? ts / 1000 : 0;
  }
  if (typeof value === "number") {
    return value > 1e12 ? value / 1000 : value;
  }
  return 0;
}

/** 横轴与十字线统一用 UTC，避免与「UTC 20:52」对照时因浏览器本地时区产生 8h 等偏差 */
function formatUtcChartTime(time) {
  if (typeof time === "number") {
    const d = new Date(time * 1000);
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const min = String(d.getUTCMinutes()).padStart(2, "0");
    return `${mm}/${dd} ${hh}:${min} UTC`;
  }
  if (time && typeof time === "object" && "year" in time) {
    return `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`;
  }
  return "";
}

function formatUtcTickDate(d) {
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${mm}/${dd}`;
}

function utcTickMarkFormatter(time, tickMarkType) {
  if (typeof time !== "number") {
    return null;
  }
  const d = new Date(time * 1000);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const min = String(d.getUTCMinutes()).padStart(2, "0");
  const sec = String(d.getUTCSeconds()).padStart(2, "0");
  const tickTypes = window.LightweightCharts?.TickMarkType || {};

  if (tickMarkType === tickTypes.TimeWithSeconds || d.getUTCSeconds() !== 0) {
    return `${hh}:${min}:${sec}`;
  }
  if (
    tickMarkType === tickTypes.DayOfMonth
    || tickMarkType === tickTypes.DayOfWeek
    || tickMarkType === tickTypes.Month
    || tickMarkType === tickTypes.Year
    || (d.getUTCHours() === 0 && d.getUTCMinutes() === 0)
  ) {
    return `${formatUtcTickDate(d)} ${hh}:${min}`;
  }
  return `${hh}:${min}`;
}

function getBarVolume(bar) {
  if (!bar || typeof bar !== "object") {
    return 0;
  }
  return Number(
    bar.bar_total_price_level_volume
    ?? bar.total_volume
    ?? bar.volume
    ?? 0,
  ) || 0;
}

function isSyntheticGapBar(bar) {
  return !!bar && (
    bar.is_synthetic === true
    || String(bar.source_kind || "").toLowerCase() === "synthetic_gap_fill"
  );
}

function resolveObservedStepMs(observedCandles) {
  let expectedStepMs = null;
  for (let index = 1; index < observedCandles.length; index += 1) {
    const previousStartedAtMs = Date.parse(observedCandles[index - 1]?.started_at || "");
    const startedAtMs = Date.parse(observedCandles[index]?.started_at || "");
    if (!Number.isFinite(previousStartedAtMs) || !Number.isFinite(startedAtMs)) {
      continue;
    }
    const stepMs = startedAtMs - previousStartedAtMs;
    if (stepMs > 0 && (expectedStepMs == null || stepMs < expectedStepMs)) {
      expectedStepMs = stepMs;
    }
  }
  return expectedStepMs;
}

function buildEmaData(candles, emaPeriod) {
  const observedCandles = candles.filter((bar) => !isSyntheticGapBar(bar));
  const expectedStepMs = resolveObservedStepMs(observedCandles);
  const gapThresholdMs = expectedStepMs != null ? expectedStepMs * 1.5 : null;
  const multiplier = 2 / (emaPeriod + 1);
  const emaData = [];
  let ema = null;
  let previousStartedAtMs = null;

  observedCandles.forEach((bar) => {
    const startedAtMs = Date.parse(bar?.started_at || "");
    const close = Number(bar?.close);
    if (!Number.isFinite(startedAtMs) || !Number.isFinite(close)) {
      return;
    }

    const hasGap = (
      gapThresholdMs != null
      && previousStartedAtMs != null
      && (startedAtMs - previousStartedAtMs) > gapThresholdMs
    );
    if (hasGap) {
      if (emaData.length) {
        const gapBreakTime = expectedStepMs != null
          ? (previousStartedAtMs + expectedStepMs) / 1000
          : startedAtMs / 1000;
        emaData.push({ time: gapBreakTime });
      }
    }

    ema = (ema == null || hasGap)
      ? close
      : ((close - ema) * multiplier) + ema;

    emaData.push({
      time: startedAtMs / 1000,
      value: ema,
    });
    previousStartedAtMs = startedAtMs;
  });

  return emaData;
}

function buildChartData(snapshot) {
  const candles = getRenderableCandles(snapshot);
  const candleData = candles.map((bar) => {
    const time = toChartTime(bar.started_at);
    if (isSyntheticGapBar(bar)) {
      return { time };
    }
    return {
      time,
      open: Number(bar.open) || 0,
      high: Number(bar.high) || 0,
      low: Number(bar.low) || 0,
      close: Number(bar.close) || 0,
    };
  });

  const volumeData = candles.map((bar) => {
    const time = toChartTime(bar.started_at);
    if (isSyntheticGapBar(bar)) {
      return { time };
    }
    return {
      time,
      value: getBarVolume(bar),
      color: Number(bar.close) >= Number(bar.open)
        ? "rgba(34, 171, 148, 0.58)"
        : "rgba(242, 54, 69, 0.58)",
    };
  });

  const emaPeriod = 20;
  const emaData = buildEmaData(candles, emaPeriod);

  return { candleData, volumeData, emaData };
}

function buildSnapshotSignature(snapshot) {
  const candles = getRenderableCandles(snapshot);
  if (!candles.length) {
    return "empty";
  }
  const lastBar = candles[candles.length - 1] || {};
  return `${candles.length}:${lastBar.started_at || ""}:${lastBar.ended_at || ""}:${lastBar.close || ""}`;
}

function buildBarSignature(bar) {
  if (!bar || typeof bar !== "object") {
    return "";
  }
  return [
    toChartTime(bar.started_at),
    Number(bar.open),
    Number(bar.high),
    Number(bar.low),
    Number(bar.close),
    getBarVolume(bar),
    Number(bar.delta ?? 0),
    Number(bar.bid_volume ?? 0),
    Number(bar.ask_volume ?? 0),
    bar.is_synthetic === true ? 1 : 0,
    String(bar.source_kind || ""),
  ].join(":");
}

function resolveBarSignature(bar) {
  if (!bar || typeof bar !== "object") {
    return "";
  }
  if (typeof bar.signature === "string") {
    return bar.signature;
  }
  return buildBarSignature(bar);
}

function hasSameBarSignatures(previousCandles = [], nextCandles = [], length = previousCandles.length) {
  if (!Array.isArray(previousCandles) || !Array.isArray(nextCandles) || length < 0) {
    return false;
  }
  if (length === 0) {
    return true;
  }
  if (previousCandles.length < length || nextCandles.length < length) {
    return false;
  }
  for (let index = 0; index < length; index += 1) {
    if (resolveBarSignature(previousCandles[index]) !== resolveBarSignature(nextCandles[index])) {
      return false;
    }
  }
  return true;
}

function syncStateChartViewFromLogicalRange(logicalRange, snapshot, chartView) {
  if (!logicalRange || !snapshot?.candles?.length || !chartView) {
    return;
  }
  const lastIndex = snapshot.candles.length - 1;
  const from = Number.isFinite(logicalRange.from) ? logicalRange.from : 0;
  const to = Number.isFinite(logicalRange.to) ? logicalRange.to : lastIndex;
  chartView.startIndex = Math.max(0, Math.min(lastIndex, Math.floor(from)));
  chartView.endIndex = Math.max(chartView.startIndex, Math.min(lastIndex, Math.ceil(to)));
}

function canApplyTailUpdate(snapshot, updateType) {
  if (!lastChartDataset || updateType === "initial" || updateType === "chart_refresh") {
    return false;
  }
  const candles = getRenderableCandles(snapshot);
  const previousCandles = lastChartDataset.candles || [];
  if (!candles.length || !previousCandles.length) {
    return false;
  }
  if (candles.length < previousCandles.length) {
    return false;
  }
  if (candles.length - previousCandles.length > 1) {
    return false;
  }
  const previousLast = previousCandles[previousCandles.length - 1];
  const nextLast = candles[candles.length - 1];
  const previousLastStartedAt = previousLast?.started_at;
  const nextLastStartedAt = nextLast?.started_at;
  if (!previousLastStartedAt || !nextLastStartedAt) {
    return false;
  }
  if (candles.length === previousCandles.length) {
    return previousLastStartedAt === nextLastStartedAt
      && hasSameBarSignatures(previousCandles, candles, previousCandles.length - 1);
  }
  return hasSameBarSignatures(previousCandles, candles, previousCandles.length);
}

function canApplyAppendTail(snapshot, updateType) {
  if (!lastChartDataset || updateType !== "append_tail" || updateType === "chart_refresh") {
    return false;
  }
  const candles = getRenderableCandles(snapshot);
  const previousCandles = lastChartDataset.candles || [];
  if (!candles.length || !previousCandles.length || candles.length <= previousCandles.length) {
    return false;
  }
  if (previousCandles.length === 1) {
    return previousCandles[0]?.started_at === candles[0]?.started_at;
  }
  return hasSameBarSignatures(previousCandles, candles, previousCandles.length - 1)
    && previousCandles[previousCandles.length - 1]?.started_at === candles[previousCandles.length - 1]?.started_at;
}

function canApplyPrependHistory(snapshot, updateType) {
  if (!lastChartDataset || updateType !== "prepend_history") {
    return false;
  }
  const candles = getRenderableCandles(snapshot);
  const previousCandles = lastChartDataset.candles || [];
  if (!candles.length || !previousCandles.length || candles.length <= previousCandles.length) {
    return false;
  }
  const suffix = candles.slice(candles.length - previousCandles.length);
  return hasSameBarSignatures(previousCandles, suffix, previousCandles.length);
}

function buildCandlePoint(bar) {
  const time = toChartTime(bar?.started_at);
  if (isSyntheticGapBar(bar)) {
    return { time };
  }
  return {
    time,
    open: Number(bar?.open) || 0,
    high: Number(bar?.high) || 0,
    low: Number(bar?.low) || 0,
    close: Number(bar?.close) || 0,
  };
}

function buildVolumePoint(bar) {
  const time = toChartTime(bar?.started_at);
  if (isSyntheticGapBar(bar)) {
    return { time };
  }
  return {
    time,
    value: getBarVolume(bar),
    color: Number(bar?.close) >= Number(bar?.open)
      ? "rgba(34, 171, 148, 0.58)"
      : "rgba(242, 54, 69, 0.58)",
  };
}

function restoreRenderedLastBar(lastBar) {
  if (!lastBar) {
    return;
  }
  candleSeries.update(buildCandlePoint(lastBar));
  volumeSeries.update(buildVolumePoint(lastBar));
}

function applyTailUpdate(snapshot) {
  const candles = getRenderableCandles(snapshot);
  if (!candles.length) {
    return;
  }
  const latestBar = candles[candles.length - 1];
  candleSeries.update(buildCandlePoint(latestBar));
  volumeSeries.update(buildVolumePoint(latestBar));
}

function applyAppendTail(snapshot) {
  const candles = getRenderableCandles(snapshot);
  const previousCandles = lastChartDataset?.candles || [];
  if (!candles.length || !previousCandles.length || candles.length <= previousCandles.length) {
    return;
  }
  const startIndex = Math.max(0, previousCandles.length - 1);
  for (let index = startIndex; index < candles.length; index += 1) {
    const bar = candles[index];
    candleSeries.update(buildCandlePoint(bar));
    volumeSeries.update(buildVolumePoint(bar));
  }
}

function applyPrependHistory(snapshot) {
  const { candleData, volumeData, emaData } = buildChartData(snapshot);
  candleSeries.setData(candleData);
  volumeSeries.setData(volumeData);
  emaSeries.setData(emaData);
}

function emitLivePreview(quote) {
  if (typeof livePreviewListener !== "function") {
    return;
  }
  try {
    livePreviewListener(quote);
  } catch (error) {
    console.warn("live preview listener failed:", error);
  }
}

function cancelLivePreviewAnimation({ emitNull = false } = {}) {
  if (livePreviewAnimationFrame) {
    cancelAnimationFrame(livePreviewAnimationFrame);
    livePreviewAnimationFrame = null;
  }
  if (emitNull) {
    emitLivePreview(null);
  }
}

function buildPreviewCandle(lastBar, price) {
  const open = Number(lastBar?.open) || 0;
  const high = Math.max(Number(lastBar?.high) || open, price, open);
  const low = Math.min(Number(lastBar?.low) || open, price, open);
  return {
    time: toChartTime(lastBar?.started_at),
    open,
    high,
    low,
    close: price,
  };
}

function isLiveTailFreshForPreview(liveTail) {
  return String(liveTail?.data_status?.freshness || "").toLowerCase() === "fresh";
}

function computeMedian(values = []) {
  const ordered = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);
  if (!ordered.length) {
    return null;
  }
  const middle = Math.floor(ordered.length / 2);
  if (ordered.length % 2 === 0) {
    return (ordered[middle - 1] + ordered[middle]) / 2;
  }
  return ordered[middle];
}

function buildLivePreviewSanityWindow(candles = [], lastBar = null) {
  const observed = candles
    .filter((bar) => bar && !isSyntheticGapBar(bar))
    .slice(-24);

  const ranges = [];
  const closeMoves = [];
  const anchors = [];
  let previousClose = null;

  observed.forEach((bar) => {
    const open = Number(bar?.open);
    const high = Number(bar?.high);
    const low = Number(bar?.low);
    const close = Number(bar?.close);
    if (![open, high, low, close].every((value) => Number.isFinite(value))) {
      return;
    }
    anchors.push(open, high, low, close);
    ranges.push(Math.max(0, high - low));
    if (Number.isFinite(previousClose)) {
      closeMoves.push(Math.abs(close - previousClose));
    }
    previousClose = close;
  });

  if (lastBar && typeof lastBar === "object") {
    [lastBar.open, lastBar.high, lastBar.low, lastBar.close].forEach((value) => {
      const numeric = Number(value);
      if (Number.isFinite(numeric)) {
        anchors.push(numeric);
      }
    });
  }

  const anchorLow = anchors.length ? Math.min(...anchors) : null;
  const anchorHigh = anchors.length ? Math.max(...anchors) : null;
  const medianRange = computeMedian(ranges);
  const medianCloseMove = computeMedian(closeMoves);
  const padding = Math.max(
    1,
    Number.isFinite(medianRange) ? medianRange * 6 : 0,
    Number.isFinite(medianCloseMove) ? medianCloseMove * 12 : 0,
  );
  const maxSpread = Math.max(
    0.5,
    Number.isFinite(medianRange) ? medianRange * 3 : 0,
    Number.isFinite(medianCloseMove) ? medianCloseMove * 6 : 0,
  );

  return {
    low: Number.isFinite(anchorLow) ? anchorLow - padding : null,
    high: Number.isFinite(anchorHigh) ? anchorHigh + padding : null,
    maxSpread,
  };
}

function resolveLivePreviewTargetPrice(candles, lastBar, liveTail) {
  const sanityWindow = buildLivePreviewSanityWindow(candles, lastBar);
  const latestPrice = Number(liveTail?.latest_price);
  const bestBid = Number(liveTail?.best_bid);
  const bestAsk = Number(liveTail?.best_ask);
  const hasValidBook = Number.isFinite(bestBid) && Number.isFinite(bestAsk) && bestAsk >= bestBid;
  const quoteMidpoint = hasValidBook ? (bestBid + bestAsk) / 2 : null;
  const quoteSpread = hasValidBook ? (bestAsk - bestBid) : null;

  if (Number.isFinite(quoteSpread) && quoteSpread > sanityWindow.maxSpread) {
    return null;
  }

  const candidates = [];
  if (Number.isFinite(latestPrice)) {
    if (!Number.isFinite(quoteMidpoint) || !Number.isFinite(quoteSpread)) {
      candidates.push(latestPrice);
    } else if (latestPrice >= (bestBid - quoteSpread) && latestPrice <= (bestAsk + quoteSpread)) {
      candidates.push(latestPrice);
    }
  }
  if (Number.isFinite(quoteMidpoint)) {
    candidates.push(quoteMidpoint);
  }
  const lastClose = Number(lastBar?.close);
  if (Number.isFinite(lastClose)) {
    candidates.push(lastClose);
  }
  const lastOpen = Number(lastBar?.open);
  if (Number.isFinite(lastOpen)) {
    candidates.push(lastOpen);
  }

  for (const candidate of candidates) {
    if (
      Number.isFinite(candidate)
      && (
        !Number.isFinite(sanityWindow.low)
        || !Number.isFinite(sanityWindow.high)
        || (candidate >= sanityWindow.low && candidate <= sanityWindow.high)
      )
    ) {
      return candidate;
    }
  }
  return null;
}

function interpolateQuoteValue(startValue, targetValue, progress) {
  const startNumeric = Number(startValue);
  const targetNumeric = Number(targetValue);
  if (!Number.isFinite(targetNumeric)) {
    return null;
  }
  if (!Number.isFinite(startNumeric)) {
    return targetNumeric;
  }
  return startNumeric + ((targetNumeric - startNumeric) * progress);
}

export function setLiveQuotePreviewListener(listener) {
  livePreviewListener = typeof listener === "function" ? listener : null;
  if (!livePreviewListener) {
    emitLivePreview(null);
  }
}

export function startLiveQuotePreview(snapshot, liveTail, options = {}) {
  const candles = getRenderableCandles(snapshot);
  if (!candleSeries || !candles.length) {
    cancelLivePreviewAnimation({ emitNull: true });
    livePreviewState = null;
    return false;
  }

  const lastBar = candles[candles.length - 1];
  if (
    isSyntheticGapBar(lastBar)
    || !isLiveTailFreshForPreview(liveTail)
    || !isTimestampWithinBarBucket(liveTail?.latest_observed_at, lastBar, snapshot?.display_timeframe)
  ) {
    cancelLivePreviewAnimation({ emitNull: true });
    restoreRenderedLastBar(lastBar);
    livePreviewState = null;
    return false;
  }
  const latestPrice = resolveLivePreviewTargetPrice(candles, lastBar, liveTail);
  if (!Number.isFinite(latestPrice)) {
    cancelLivePreviewAnimation({ emitNull: true });
    restoreRenderedLastBar(lastBar);
    livePreviewState = null;
    return false;
  }
  const barTime = toChartTime(lastBar?.started_at);
  const actualClose = Number(lastBar?.close) || Number(lastBar?.open) || latestPrice;
  const startPrice = livePreviewState?.barTime === barTime
    ? Number(livePreviewState.currentPrice)
    : actualClose;
  const targetPrice = latestPrice;
  const observedAt = liveTail?.latest_observed_at || null;
  if (
    livePreviewState?.barTime === barTime
    && livePreviewState?.latestObservedAt === observedAt
    && Math.abs(Number(livePreviewState.targetPrice) - targetPrice) < 1e-9
  ) {
    emitLivePreview({
      latest_price: livePreviewState.currentPrice,
      best_bid: livePreviewState.bestBid,
      best_ask: livePreviewState.bestAsk,
      latest_observed_at: livePreviewState.latestObservedAt,
      latest_price_source: liveTail?.latest_price_source || null,
      best_bid_source: liveTail?.best_bid_source || null,
      best_ask_source: liveTail?.best_ask_source || null,
    });
    return true;
  }
  const durationMs = Math.max(
    600,
    Math.min(
      2200,
      Number(options.durationMs)
      || (String(liveTail?.latest_price_source || "").toLowerCase() === "ticks_raw" ? 900 : 1400),
    ),
  );
  const startBid = livePreviewState?.barTime === barTime ? livePreviewState.bestBid : Number(liveTail?.best_bid);
  const startAsk = livePreviewState?.barTime === barTime ? livePreviewState.bestAsk : Number(liveTail?.best_ask);
  cancelLivePreviewAnimation();

  if (Math.abs(targetPrice - startPrice) < 1e-9) {
    candleSeries.update(buildPreviewCandle(lastBar, targetPrice));
    livePreviewState = {
      barTime,
      currentPrice: targetPrice,
      targetPrice,
      bestBid: Number.isFinite(Number(liveTail?.best_bid)) ? Number(liveTail.best_bid) : null,
      bestAsk: Number.isFinite(Number(liveTail?.best_ask)) ? Number(liveTail.best_ask) : null,
      latestObservedAt: observedAt,
    };
    emitLivePreview({
      latest_price: livePreviewState.currentPrice,
      best_bid: livePreviewState.bestBid,
      best_ask: livePreviewState.bestAsk,
      latest_observed_at: livePreviewState.latestObservedAt,
      latest_price_source: liveTail?.latest_price_source || null,
      best_bid_source: liveTail?.best_bid_source || null,
      best_ask_source: liveTail?.best_ask_source || null,
    });
    return true;
  }

  const startedAt = performance.now();
  const step = (frameNow) => {
    const progress = Math.max(0, Math.min(1, (frameNow - startedAt) / durationMs));
    const eased = 1 - ((1 - progress) ** 3);
    const currentPrice = startPrice + ((targetPrice - startPrice) * eased);
    candleSeries.update(buildPreviewCandle(lastBar, currentPrice));
    livePreviewState = {
      barTime,
      currentPrice,
      targetPrice,
      bestBid: interpolateQuoteValue(startBid, liveTail?.best_bid, eased),
      bestAsk: interpolateQuoteValue(startAsk, liveTail?.best_ask, eased),
      latestObservedAt: observedAt,
    };
    emitLivePreview({
      latest_price: currentPrice,
      best_bid: livePreviewState.bestBid,
      best_ask: livePreviewState.bestAsk,
      latest_observed_at: livePreviewState.latestObservedAt,
      latest_price_source: liveTail?.latest_price_source || null,
      best_bid_source: liveTail?.best_bid_source || null,
      best_ask_source: liveTail?.best_ask_source || null,
    });
    if (progress >= 1) {
      livePreviewAnimationFrame = null;
      return;
    }
    livePreviewAnimationFrame = requestAnimationFrame(step);
  };
  livePreviewAnimationFrame = requestAnimationFrame(step);
  return true;
}

export function initLightweightCharts(els) {
  if (typeof LightweightCharts === "undefined") {
    console.error("LightweightCharts library not loaded");
    return null;
  }

  if (resizeObserver) {
    try {
      resizeObserver.disconnect();
    } catch (error) {
      console.warn("disconnect ResizeObserver 失败:", error);
    }
    resizeObserver = null;
  }

  if (chartInstance) {
    cancelLivePreviewAnimation({ emitNull: true });
    livePreviewState = null;
    chartInstance.remove();
    chartInstance = null;
    volumeChartInstance = null;
    candleSeries = null;
    volumeSeries = null;
    emaSeries = null;
    priceLineMap = {};
  }

  const chartOptions = {
    layout: {
      background: { color: "#101827" },
      textColor: "#9ca3af",
    },
    grid: {
      vertLines: { color: "rgba(42, 46, 57, 0.5)" },
      horzLines: { color: "rgba(42, 46, 57, 0.5)" },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {
        color: "#505665",
        labelBackgroundColor: "#2d3748",
      },
      horzLine: {
        color: "#505665",
        labelBackgroundColor: "#2d3748",
      },
    },
    timeScale: {
      borderColor: "#2d3748",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 6,
      barSpacing: 6,
      minBarSpacing: 1,
      lockVisibleTimeRangeOnResize: true,
      fixLeftEdge: false,
      fixRightEdge: false,
      tickMarkFormatter: utcTickMarkFormatter,
    },
    localization: {
      locale: "en-US",
      dateFormat: "dd MMM 'yy",
      timeFormatter: formatUtcChartTime,
    },
    rightPriceScale: {
      visible: true,
      borderColor: "#2d3748",
      scaleMargins: { top: 0.08, bottom: 0.2 },
      autoScale: true,
    },
    handleScale: {
      axisPressedMouseMove: {
        time: true,
        price: true,
      },
      mouseWheel: false,
      pinch: false,
      axisDoubleClickReset: true,
    },
    handleScroll: {
      mouseWheel: false,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: true,
    },
    kineticScroll: {
      mouse: true,
      touch: true,
    },
  };

  const chartWidth = els.chartContainer.clientWidth || els.chartContainer.offsetWidth || 1200;
  const chartHeight = els.chartContainer.clientHeight || els.chartContainer.offsetHeight || 600;
  const volumeWidth = els.volumeChartContainer.clientWidth || els.volumeChartContainer.offsetWidth || 1200;
  const volumeHeight = els.volumeChartContainer.clientHeight || els.volumeChartContainer.offsetHeight || 120;

  if (chartWidth <= 0 || chartHeight <= 0) {
    console.error("图表容器尺寸无效:", { chartWidth, chartHeight });
    return null;
  }

  chartInstance = LightweightCharts.createChart(els.chartContainer, {
    ...chartOptions,
    width: chartWidth,
    height: chartHeight,
  });

  volumeChartInstance = LightweightCharts.createChart(els.volumeChartContainer, {
    ...chartOptions,
    width: volumeWidth,
    height: volumeHeight,
    timeScale: {
      ...chartOptions.timeScale,
      visible: false,
      borderVisible: false,
      ticksVisible: false,
    },
    rightPriceScale: {
      visible: false,
      borderColor: "#2d3748",
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Hidden,
    },
  });

  candleSeries = chartInstance.addCandlestickSeries({
    upColor: "#22ab94",
    downColor: "#f23645",
    borderUpColor: "#22ab94",
    borderDownColor: "#f23645",
    wickUpColor: "#22ab94",
    wickDownColor: "#f23645",
    priceLineVisible: false,
  });

  volumeSeries = volumeChartInstance.addHistogramSeries({
    color: "#26a69a",
    priceFormat: { type: "volume" },
    priceScaleId: "",
    priceLineVisible: false,
    lastValueVisible: false,
  });

  volumeChartInstance.priceScale("").applyOptions({
    scaleMargins: { top: 0.08, bottom: 0 },
  });

  emaSeries = chartInstance.addLineSeries({
    color: "#3b82f6",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: false,
  });

  chartInstance.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || !volumeChartInstance || syncingVisibleRange) {
      return;
    }
    syncingVisibleRange = true;
    try {
      volumeChartInstance.timeScale().setVisibleLogicalRange(range);
    } finally {
      syncingVisibleRange = false;
    }
  });

  volumeChartInstance.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || !chartInstance || syncingVisibleRange) {
      return;
    }
    syncingVisibleRange = true;
    try {
      chartInstance.timeScale().setVisibleLogicalRange(range);
    } finally {
      syncingVisibleRange = false;
    }
  });

  resizeObserver = new ResizeObserver(() => {
    if (chartInstance && els.chartContainer) {
      const width = els.chartContainer.clientWidth;
      const height = els.chartContainer.clientHeight;
      if (width > 0 && height > 0) {
        chartInstance.resize(width, height);
      }
    }
    if (volumeChartInstance && els.volumeChartContainer) {
      const width = els.volumeChartContainer.clientWidth;
      const height = els.volumeChartContainer.clientHeight;
      if (width > 0 && height > 0) {
        volumeChartInstance.resize(width, height);
      }
    }
  });
  resizeObserver.observe(els.chartContainer);
  resizeObserver.observe(els.volumeChartContainer);

  return { chartInstance, volumeChartInstance, candleSeries, volumeSeries, emaSeries };
}

export function updateChartData(snapshot, chartView, els, options = {}) {
  const startedAt = performance.now();
  const candles = getRenderableCandles(snapshot);
  if (!candleSeries || !volumeSeries || !emaSeries || !candles.length) {
    return;
  }

  const updateType = options.updateType || "initial";
  const syncStateFromLogicalRange = options.syncStateFromLogicalRange !== false;
  const signature = buildSnapshotSignature(snapshot);
  const shouldFitInitially = !lastDataSignature;
  const dataChanged = signature !== lastDataSignature;
  const incrementalEligible = updateType !== "chart_refresh";

  if (!dataChanged) {
    if (candleSeries?.setMarkers) {
      candleSeries.setMarkers(Array.isArray(options.markers) ? options.markers : []);
    }
    if (syncStateFromLogicalRange && chartInstance && candles.length && chartView) {
      const logicalRange = chartInstance.timeScale().getVisibleLogicalRange?.();
      if (logicalRange) {
        syncStateChartViewFromLogicalRange(logicalRange, { ...snapshot, candles }, chartView);
      }
    }
    if (els?.chartContainer) {
      els.chartContainer.style.cursor = chartView?.regionMode ? "crosshair" : "grab";
      els.chartContainer.dataset.lastUpdateType = lastUpdateType;
      els.chartContainer.dataset.lastChartUpdateMs = String(Math.round(performance.now() - startedAt));
    }
    return;
  }

  if (incrementalEligible && canApplyTailUpdate(snapshot, updateType)) {
    applyTailUpdate(snapshot);
    const { emaData } = buildChartData(snapshot);
    emaSeries.setData(emaData);
    lastUpdateType = updateType;
  } else if (incrementalEligible && canApplyAppendTail(snapshot, updateType)) {
    applyAppendTail(snapshot);
    const { emaData } = buildChartData(snapshot);
    emaSeries.setData(emaData);
    lastUpdateType = updateType;
  } else if (incrementalEligible && canApplyPrependHistory(snapshot, updateType)) {
    applyPrependHistory(snapshot);
    lastUpdateType = updateType;
  } else {
    const { candleData, volumeData, emaData } = buildChartData(snapshot);
    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);
    emaSeries.setData(emaData);
    lastUpdateType = updateType;
  }

  if (dataChanged && chartInstance) {
    lastDataSignature = signature;
    lastChartDataset = {
      candles: candles.map((bar) => ({
        started_at: bar.started_at,
        signature: buildBarSignature(bar),
      })),
    };
    if (shouldFitInitially) {
      try {
        chartInstance.timeScale().fitContent();
        volumeChartInstance?.timeScale().fitContent();
      } catch (error) {
        console.warn("初次 fitContent 失败:", error);
      }
    }
  }

  if (candleSeries?.setMarkers) {
    candleSeries.setMarkers(Array.isArray(options.markers) ? options.markers : []);
  }

  if (syncStateFromLogicalRange && chartInstance && candles.length && chartView) {
    const logicalRange = chartInstance.timeScale().getVisibleLogicalRange?.();
    if (logicalRange) {
      syncStateChartViewFromLogicalRange(logicalRange, { ...snapshot, candles }, chartView);
    }
  }

  if (els?.chartContainer) {
    els.chartContainer.style.cursor = chartView?.regionMode ? "crosshair" : "grab";
    els.chartContainer.dataset.lastUpdateType = lastUpdateType;
    els.chartContainer.dataset.lastChartUpdateMs = String(Math.round(performance.now() - startedAt));
  }
}

export function addPriceLine(price, color, title) {
  if (!candleSeries) return null;
  const id = `pl_${priceLineCounter++}`;
  const line = candleSeries.createPriceLine({
    price,
    color,
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title,
  });
  priceLineMap[id] = line;
  return id;
}

export function removePriceLine(id) {
  if (id && candleSeries && priceLineMap[id]) {
    candleSeries.removePriceLine(priceLineMap[id]);
    delete priceLineMap[id];
  }
}

export function clearAllPriceLines() {
  Object.keys(priceLineMap).forEach((id) => removePriceLine(id));
}

export function getChartInstance() {
  return chartInstance;
}

export function getVolumeChartInstance() {
  return volumeChartInstance;
}

export function getCandleSeries() {
  return candleSeries;
}

export function subscribeCrosshairMove(callback) {
  if (chartInstance) {
    chartInstance.subscribeCrosshairMove((param) => {
      callback(param);
    });
  }
}

export function subscribeClick(callback, els = null) {
  if (chartInstance) {
    chartInstance.subscribeClick((param) => {
      callback(param);
    });
  }
  if (els?.chartContainer) {
    els.chartContainer.addEventListener("contextmenu", (e) => {
      e.preventDefault();
    });
  }
}

export function subscribeVisibleRangeChange(callback) {
  if (chartInstance?.timeScale) {
    chartInstance.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      callback(range);
    });
  }
}

export function scrollToTime(time) {
  if (chartInstance) {
    chartInstance.timeScale().scrollToPosition(0, false);
  }
}

export function scrollToPosition(position) {
  if (chartInstance) {
    chartInstance.timeScale().scrollToPosition(position, true);
  }
}

export function zoomChart(factor) {
  if (chartInstance) {
    const range = chartInstance.timeScale().getVisibleLogicalRange?.();
    if (!range) {
      chartInstance.timeScale().fitContent();
      return;
    }
    const center = (range.from + range.to) / 2;
    const span = Math.max(10, (range.to - range.from) * factor);
    chartInstance.timeScale().setVisibleLogicalRange({
      from: center - span / 2,
      to: center + span / 2,
    });
  }
}

export function resizeCharts(els) {
  if (chartInstance && els.chartContainer) {
    chartInstance.resize(els.chartContainer.clientWidth, els.chartContainer.clientHeight);
  }
  if (volumeChartInstance && els.volumeChartContainer) {
    volumeChartInstance.resize(els.volumeChartContainer.clientWidth, els.volumeChartContainer.clientHeight);
  }
}

export function destroyCharts() {
  cancelLivePreviewAnimation({ emitNull: true });
  livePreviewState = null;
  if (resizeObserver) {
    try {
      resizeObserver.disconnect();
    } catch (error) {
      console.warn("disconnect ResizeObserver 失败:", error);
    }
    resizeObserver = null;
  }
  if (chartInstance) {
    chartInstance.remove();
    chartInstance = null;
  }
  if (volumeChartInstance) {
    volumeChartInstance.remove();
    volumeChartInstance = null;
  }
  candleSeries = null;
  volumeSeries = null;
  emaSeries = null;
  priceLineMap = {};
  lastDataSignature = "";
  lastChartDataset = null;
  syncingVisibleRange = false;
}
