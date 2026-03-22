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

function utcTickMarkFormatter(time) {
  if (typeof time === "number") {
    const d = new Date(time * 1000);
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const min = String(d.getUTCMinutes()).padStart(2, "0");
    return `${hh}:${min}`;
  }
  return null;
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

function buildChartData(snapshot) {
  const candles = snapshot?.candles || [];
  const candleData = candles.map((bar) => ({
    time: toChartTime(bar.started_at),
    open: Number(bar.open) || 0,
    high: Number(bar.high) || 0,
    low: Number(bar.low) || 0,
    close: Number(bar.close) || 0,
  }));

  const volumeData = candles.map((bar) => ({
    time: toChartTime(bar.started_at),
    value: getBarVolume(bar),
    color: Number(bar.close) >= Number(bar.open)
      ? "rgba(34, 171, 148, 0.58)"
      : "rgba(242, 54, 69, 0.58)",
  }));

  const emaPeriod = 20;
  const emaData = [];
  const multiplier = 2 / (emaPeriod + 1);
  let ema = null;

  for (let i = 0; i < candles.length; i++) {
    if (i < emaPeriod - 1) {
      continue;
    }
    const close = Number(candles[i].close) || 0;
    if (ema === null) {
      let sum = 0;
      for (let j = 0; j < emaPeriod; j++) {
        sum += Number(candles[i - emaPeriod + 1 + j].close) || 0;
      }
      ema = sum / emaPeriod;
    } else {
      ema = (close - ema) * multiplier + ema;
    }
    emaData.push({
      time: toChartTime(candles[i].started_at),
      value: ema,
    });
  }

  return { candleData, volumeData, emaData };
}

function buildSnapshotSignature(snapshot) {
  const candles = snapshot?.candles || [];
  if (!candles.length) {
    return "empty";
  }
  const lastBar = candles[candles.length - 1] || {};
  return `${candles.length}:${lastBar.started_at || ""}:${lastBar.ended_at || ""}:${lastBar.close || ""}`;
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
  if (!lastChartDataset || updateType === "initial") {
    return false;
  }
  const candles = snapshot?.candles || [];
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
  return candles.length === previousCandles.length
    ? previousLastStartedAt === nextLastStartedAt
    : candles[candles.length - 2]?.started_at === previousLastStartedAt;
}

function canApplyPrependHistory(snapshot, updateType) {
  if (!lastChartDataset || updateType !== "prepend_history") {
    return false;
  }
  const candles = snapshot?.candles || [];
  const previousCandles = lastChartDataset.candles || [];
  if (!candles.length || !previousCandles.length || candles.length <= previousCandles.length) {
    return false;
  }
  const suffix = candles.slice(candles.length - previousCandles.length);
  return suffix.every((bar, index) => bar?.started_at === previousCandles[index]?.started_at);
}

function applyTailUpdate(snapshot) {
  const candles = snapshot?.candles || [];
  if (!candles.length) {
    return;
  }
  const latestBar = candles[candles.length - 1];
  const latestCandle = {
    time: toChartTime(latestBar.started_at),
    open: Number(latestBar.open) || 0,
    high: Number(latestBar.high) || 0,
    low: Number(latestBar.low) || 0,
    close: Number(latestBar.close) || 0,
  };
  const latestVolume = {
    time: toChartTime(latestBar.started_at),
    value: getBarVolume(latestBar),
    color: Number(latestBar.close) >= Number(latestBar.open)
      ? "rgba(34, 171, 148, 0.58)"
      : "rgba(242, 54, 69, 0.58)",
  };
  candleSeries.update(latestCandle);
  volumeSeries.update(latestVolume);
}

function applyPrependHistory(snapshot) {
  const { candleData, volumeData, emaData } = buildChartData(snapshot);
  candleSeries.setData(candleData);
  volumeSeries.setData(volumeData);
  emaSeries.setData(emaData);
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
      barSpacing: 10,
      minBarSpacing: 4,
      lockVisibleTimeRangeOnResize: false,
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
      mouseWheel: true,
      pinch: true,
      axisDoubleClickReset: true,
    },
    handleScroll: {
      mouseWheel: true,
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
  if (!candleSeries || !volumeSeries || !emaSeries || !snapshot?.candles?.length) {
    return;
  }

  const updateType = options.updateType || "initial";
  const syncStateFromLogicalRange = options.syncStateFromLogicalRange !== false;
  const signature = buildSnapshotSignature(snapshot);
  const shouldFitInitially = !lastDataSignature;
  const dataChanged = signature !== lastDataSignature;

  if (dataChanged && canApplyTailUpdate(snapshot, updateType)) {
    applyTailUpdate(snapshot);
    const { emaData } = buildChartData(snapshot);
    emaSeries.setData(emaData);
    lastUpdateType = updateType;
  } else if (dataChanged && canApplyPrependHistory(snapshot, updateType)) {
    applyPrependHistory(snapshot);
    lastUpdateType = updateType;
  } else {
    const { candleData, volumeData, emaData } = buildChartData(snapshot);
    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);
    emaSeries.setData(emaData);
    lastUpdateType = dataChanged ? updateType : lastUpdateType;
  }

  if (dataChanged && chartInstance) {
    lastDataSignature = signature;
    lastChartDataset = { candles: snapshot.candles.map((bar) => ({ started_at: bar.started_at })) };
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

  if (syncStateFromLogicalRange && chartInstance && snapshot?.candles?.length && chartView) {
    const logicalRange = chartInstance.timeScale().getVisibleLogicalRange?.();
    if (logicalRange) {
      syncStateChartViewFromLogicalRange(logicalRange, snapshot, chartView);
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
