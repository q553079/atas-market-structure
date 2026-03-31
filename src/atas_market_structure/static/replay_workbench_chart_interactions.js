export function createChartInteractionController({
  state,
  els,
  renderChart,
  renderSnapshot,
  renderViewportSnapshot = null,
  renderRegionSelectionSurface = null,
  renderRegionDraftPreview = null,
  loadFootprintBarDetail,
  clampChartView,
  createDefaultChartView,
}) {
  let draftUpdateFrame = 0;
  let pendingDraftPointer = null;
  let draftModelContext = null;

  const renderViewportSurface = typeof renderViewportSnapshot === "function"
    ? renderViewportSnapshot
    : renderSnapshot;
  const renderCommittedDraftSurface = typeof renderRegionSelectionSurface === "function"
    ? renderRegionSelectionSurface
    : renderViewportSurface;

  function visibleSpan() {
    if (!state.chartView) {
      return 0;
    }
    return state.chartView.endIndex - state.chartView.startIndex + 1;
  }

  function clonePointerLikeEvent(event) {
    return {
      type: String(event?.type || ""),
      clientX: Number(event?.clientX),
      clientY: Number(event?.clientY),
      button: Number(event?.button ?? 0),
      pointerId: event?.pointerId,
    };
  }

  function cancelPendingDraftUpdate() {
    if (draftUpdateFrame) {
      cancelAnimationFrame(draftUpdateFrame);
      draftUpdateFrame = 0;
    }
    pendingDraftPointer = null;
  }

  function invalidateDraftModelContext() {
    draftModelContext = null;
  }

  function buildDraftModelContext(snapshot = state.snapshot) {
    const candles = Array.isArray(snapshot?.candles) ? snapshot.candles : [];
    const view = state.chartView;
    const chartContainerRect = els.chartContainer?.getBoundingClientRect?.() || null;
    const svgRect = els.chartSvg?.getBoundingClientRect?.() || chartContainerRect;
    const chartViewStart = Number.isFinite(Number(view?.startIndex)) ? Number(view.startIndex) : null;
    const chartViewEnd = Number.isFinite(Number(view?.endIndex)) ? Number(view.endIndex) : null;
    const visibleStartIndex = chartViewStart == null ? 0 : Math.max(0, chartViewStart);
    const visibleEndIndex = chartViewEnd == null ? -1 : Math.min(candles.length - 1, chartViewEnd);
    const visibleCandles = visibleEndIndex >= visibleStartIndex
      ? candles.slice(visibleStartIndex, visibleEndIndex + 1)
      : [];
    const fallbackPriceMin = Math.min(...visibleCandles.map((item) => Number(item?.low)).filter(Number.isFinite));
    const fallbackPriceMax = Math.max(...visibleCandles.map((item) => Number(item?.high)).filter(Number.isFinite));
    return {
      snapshot,
      candles,
      view,
      chart: window._lwChartState?.chartInstance || null,
      candleSeries: window._lwChartState?.candleSeries || null,
      chartContainerRect,
      svgRect,
      chartMetrics: state.chartMetrics || null,
      chartViewStart,
      chartViewEnd,
      chartViewYMin: Number(view?.yMin),
      chartViewYMax: Number(view?.yMax),
      visibleStartIndex,
      visibleCandles,
      fallbackPriceMin,
      fallbackPriceMax,
      candleSpacing: chartContainerRect?.width && visibleCandles.length
        ? chartContainerRect.width / Math.max(visibleCandles.length, 1)
        : null,
    };
  }

  function getDraftModelContext(snapshot = state.snapshot, { forceRefresh = false } = {}) {
    if (!forceRefresh && draftModelContext) {
      const view = state.chartView;
      const chartViewStart = Number.isFinite(Number(view?.startIndex)) ? Number(view.startIndex) : null;
      const chartViewEnd = Number.isFinite(Number(view?.endIndex)) ? Number(view.endIndex) : null;
      const chartViewYMin = Number(view?.yMin);
      const chartViewYMax = Number(view?.yMax);
      if (
        draftModelContext.snapshot === snapshot
        && draftModelContext.view === view
        && draftModelContext.chartMetrics === (state.chartMetrics || null)
        && draftModelContext.chartViewStart === chartViewStart
        && draftModelContext.chartViewEnd === chartViewEnd
        && draftModelContext.chartViewYMin === chartViewYMin
        && draftModelContext.chartViewYMax === chartViewYMax
      ) {
        return draftModelContext;
      }
    }
    draftModelContext = buildDraftModelContext(snapshot);
    return draftModelContext;
  }

  function normalizeCoordinateTimeToMs(value) {
    if (typeof value === "number") {
      const seconds = value > 1e12 ? value / 1000 : value;
      return Number.isFinite(seconds) ? Math.round(seconds * 1000) : null;
    }
    if (value && typeof value === "object") {
      const year = Number(value.year);
      const month = Number(value.month);
      const day = Number(value.day);
      if (Number.isFinite(year) && Number.isFinite(month) && Number.isFinite(day)) {
        return Date.UTC(year, month - 1, day);
      }
    }
    if (typeof value === "string") {
      const timestamp = new Date(value).getTime();
      return Number.isFinite(timestamp) ? timestamp : null;
    }
    return null;
  }

  function resolveChartLogicalIndex(event, snapshot = state.snapshot, modelContext = null) {
    const context = modelContext || getDraftModelContext(snapshot);
    const chart = context?.chart;
    const candles = context?.candles;
    if (!chart?.timeScale || !Array.isArray(candles) || !candles.length || !context?.chartContainerRect) {
      return null;
    }
    const x = Number(event?.clientX) - context.chartContainerRect.left;
    const logical = chart.timeScale().coordinateToLogical?.(x);
    if (!Number.isFinite(logical)) {
      return null;
    }
    return Math.max(0, Math.min(candles.length - 1, Math.round(logical)));
  }

  function zoomChart(factor) {
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
      invalidateDraftModelContext();
      const range = chart.timeScale().getVisibleLogicalRange?.();
      if (!range) {
        chart.timeScale().fitContent();
        return;
      }
      const center = (range.from + range.to) / 2;
      const currentSpan = Math.max(10, range.to - range.from);
      const targetSpan = Math.max(10, currentSpan * factor);
      chart.timeScale().setVisibleLogicalRange({
        from: center - targetSpan / 2,
        to: center + targetSpan / 2,
      });
      return;
    }
    const snapshot = state.snapshot;
    if (!snapshot?.candles?.length || !state.chartView) {
      return;
    }
    const total = snapshot.candles.length;
    const currentSpan = visibleSpan();
    const targetSpan = Math.max(20, Math.min(total, Math.round(currentSpan * factor)));
    const center = Math.round((state.chartView.startIndex + state.chartView.endIndex) / 2);
    let startIndex = center - Math.floor(targetSpan / 2);
    let endIndex = startIndex + targetSpan - 1;
    if (startIndex < 0) {
      startIndex = 0;
      endIndex = targetSpan - 1;
    }
    if (endIndex >= total) {
      endIndex = total - 1;
      startIndex = Math.max(0, endIndex - targetSpan + 1);
    }
    state.chartView = clampChartView(total, startIndex, endIndex, state.chartView);
    invalidateDraftModelContext();
    renderViewportSurface();
  }

  function zoomPriceAxis(factor) {
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
      invalidateDraftModelContext();
      chart.applyOptions({
        rightPriceScale: {
          scaleMargins: { top: 0.1 * factor, bottom: 0.2 },
        },
      });
    } else {
      if (!state.snapshot?.candles?.length || !state.chartView || state.chartView.yMin == null || state.chartView.yMax == null) {
        return;
      }
      const currentSpan = state.chartView.yMax - state.chartView.yMin;
      const targetSpan = Math.max(0.5, currentSpan * factor);
      const center = (state.chartView.yMin + state.chartView.yMax) / 2;
      state.chartView.yMin = center - (targetSpan / 2);
      state.chartView.yMax = center + (targetSpan / 2);
      invalidateDraftModelContext();
      renderChart();
    }
  }

  function resetChartView() {
    if (!state.snapshot?.candles?.length) {
      return;
    }
    invalidateDraftModelContext();
    state.chartView = createDefaultChartView(state.snapshot.candles.length);
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
      const { startIndex, endIndex } = state.chartView;
      chart.timeScale().setVisibleLogicalRange({
        from: startIndex,
        to: endIndex,
      });
    }
    invalidateDraftModelContext();
    renderViewportSurface();
  }

  function chartMouseToModel(event, { modelContext = null } = {}) {
    const snapshot = state.snapshot;
    const context = modelContext || getDraftModelContext(snapshot);
    const view = context?.view;
    const chart = context?.chart;
    const candleSeries = context?.candleSeries;
    if (chart && context?.candles?.length && context?.chartContainerRect) {
      const x = Number(event?.clientX) - context.chartContainerRect.left;
      const y = Number(event?.clientY) - context.chartContainerRect.top;
      const logicalIndex = resolveChartLogicalIndex(event, snapshot, context);
      const candle = Number.isInteger(logicalIndex) ? context.candles[logicalIndex] : null;
      const timestampMs = Date.parse(candle?.started_at || "");
      const price = candleSeries?.coordinateToPrice?.(y);
      if (Number.isFinite(timestampMs) && Number.isFinite(price)) {
        return {
          x,
          y,
          timestamp: timestampMs,
          price,
          globalIndex: logicalIndex,
        };
      }
    }
    const chartRect = context?.chartContainerRect;
    if (context?.candles?.length && view && chartRect?.width && chartRect?.height) {
      const x = Number(event?.clientX) - chartRect.left;
      const y = Number(event?.clientY) - chartRect.top;
      if (x >= 0 && x <= chartRect.width && y >= 0 && y <= chartRect.height) {
        const visibleCandles = context.visibleCandles;
        if (visibleCandles.length) {
          const localIndex = Math.max(0, Math.min(visibleCandles.length - 1, Math.floor(x / Math.max(context.candleSpacing || 1, 1))));
          const candle = visibleCandles[localIndex];
          const timestampMs = Date.parse(candle?.started_at || "");
          const yMin = Number.isFinite(Number(view.yMin)) ? Number(view.yMin) : context.fallbackPriceMin;
          const yMax = Number.isFinite(Number(view.yMax)) ? Number(view.yMax) : context.fallbackPriceMax;
          const priceRange = yMax - yMin;
          const price = Number.isFinite(priceRange) && priceRange > 0
            ? yMax - (Math.max(0, Math.min(chartRect.height, y)) / chartRect.height) * priceRange
            : Number(candle?.close ?? candle?.open ?? 0);
          if (Number.isFinite(timestampMs) && Number.isFinite(price)) {
            return {
              x,
              y,
              timestamp: timestampMs,
              price,
              globalIndex: context.visibleStartIndex + localIndex,
            };
          }
        }
      }
    }
    if (chart && context?.chartMetrics && context?.chartContainerRect) {
      const x = Number(event?.clientX) - context.chartContainerRect.left;
      const y = Number(event?.clientY) - context.chartContainerRect.top;
      const time = chart.timeScale().coordinateToTime(x);
      const price = candleSeries?.coordinateToPrice?.(y);
      const timestampMs = normalizeCoordinateTimeToMs(time);
      if (Number.isFinite(timestampMs) && Number.isFinite(price)) {
        return {
          x,
          y,
          timestamp: timestampMs,
          price,
        };
      }
    }
    const metrics = context?.chartMetrics;
    if (!metrics) {
      return null;
    }
    const rect = context?.svgRect || context?.chartContainerRect;
    if (!rect) return null;
    const x = Number(event?.clientX) - rect.left;
    const y = Number(event?.clientY) - rect.top;
    if (x < metrics.leftPad || x > metrics.width - metrics.rightPad || y < metrics.topPad || y > metrics.height - metrics.bottomPad) {
      return null;
    }
    const ratioX = (x - metrics.leftPad) / metrics.chartWidth;
    const ratioY = (y - metrics.topPad) / metrics.chartHeight;
    const timestamp = metrics.visibleStartTime + ratioX * (metrics.visibleEndTime - metrics.visibleStartTime);
    const price = metrics.yMax - ratioY * (metrics.yMax - metrics.yMin);
    return { x, y, timestamp, price };
  }

  function pickCandleIndexFromEvent(event, { modelContext = null } = {}) {
    const context = modelContext || getDraftModelContext(state.snapshot);
    const model = chartMouseToModel(event, { modelContext: context });
    if (Number.isInteger(model?.globalIndex)) {
      return model.globalIndex;
    }
    const logicalIndex = resolveChartLogicalIndex(event, state.snapshot, context);
    if (Number.isInteger(logicalIndex)) {
      return logicalIndex;
    }
    const chart = context?.chart;
    const snapshot = context?.snapshot || state.snapshot;
    if (chart && snapshot?.candles?.length && context?.chartContainerRect) {
      const x = Number(event?.clientX) - context.chartContainerRect.left;
      const time = chart.timeScale().coordinateToTime(x);
      const timestamp = normalizeCoordinateTimeToMs(time);
      if (Number.isFinite(timestamp)) {
        const bar = snapshot.candles.find((c) => {
          const startedAtMs = Date.parse(c?.started_at || "");
          return Number.isFinite(startedAtMs) && Math.abs(startedAtMs - timestamp) < 120000;
        });
        if (bar) {
          return snapshot.candles.indexOf(bar);
        }
      }
    }
    if (!model || !snapshot?.candles?.length || !state.chartView) {
      return null;
    }
    const localIndex = Math.max(0, Math.min(visibleSpan() - 1, Math.floor((model.x - state.chartMetrics.leftPad) / state.chartMetrics.candleSpacing)));
    return state.chartView.startIndex + localIndex;
  }

  function resolveDraftTimeWindow(event, model, { modelContext = null } = {}) {
    const candleIndex = pickCandleIndexFromEvent(event, { modelContext });
    const candle = candleIndex != null ? state.snapshot?.candles?.[candleIndex] : null;
    const candleStartMs = Date.parse(candle?.started_at || "");
    const candleEndMs = Date.parse(candle?.ended_at || candle?.started_at || "");
    if (Number.isFinite(candleStartMs)) {
      return {
        startedAtIso: new Date(candleStartMs).toISOString(),
        endedAtIso: new Date(
          Number.isFinite(candleEndMs) && candleEndMs >= candleStartMs
            ? candleEndMs
            : candleStartMs,
        ).toISOString(),
      };
    }
    return {
      startedAtIso: new Date(model.timestamp).toISOString(),
      endedAtIso: new Date(model.timestamp).toISOString(),
    };
  }

  async function selectCandle(globalIndex) {
    const snapshot = state.snapshot;
    const candle = snapshot?.candles?.[globalIndex];
    if (!candle) {
      return;
    }
    state.selectedCandleIndex = globalIndex;
    state.selectedFootprintBar = null;
    renderViewportSurface();
    await loadFootprintBarDetail(candle.started_at);
    renderViewportSurface();
  }

  function isDraftCommitEvent(eventType = "") {
    return eventType === "mouseup" || eventType === "pointerup" || eventType === "pointercancel" || eventType === "click";
  }

  function renderDraftRegionSurface({ commit = false } = {}) {
    if (commit) {
      renderCommittedDraftSurface();
      return;
    }
    if (typeof renderRegionDraftPreview === "function") {
      renderRegionDraftPreview();
      return;
    }
    renderChart();
  }

  function beginRegionDraft(event) {
    cancelPendingDraftUpdate();
    const modelContext = getDraftModelContext(state.snapshot, { forceRefresh: true });
    const model = chartMouseToModel(event, { modelContext });
    if (!model) {
      return false;
    }
    const draftWindow = resolveDraftTimeWindow(event, model, { modelContext });
    state.chartInteraction.draftRegion = {
      started_at: draftWindow.startedAtIso,
      ended_at: draftWindow.endedAtIso,
      price_low: model.price,
      price_high: model.price,
      anchor_started_at: draftWindow.startedAtIso,
      anchor_ended_at: draftWindow.endedAtIso,
      anchor_price: model.price,
    };
    renderDraftRegionSurface({ commit: false });
    return true;
  }

  function updateRegionDraft(event, { deferMove = true } = {}) {
    const eventType = String(event?.type || "");
    const commit = isDraftCommitEvent(eventType);
    if (!commit && deferMove) {
      pendingDraftPointer = clonePointerLikeEvent(event);
      if (!draftUpdateFrame) {
        draftUpdateFrame = requestAnimationFrame(() => {
          draftUpdateFrame = 0;
          const nextEvent = pendingDraftPointer;
          pendingDraftPointer = null;
          if (nextEvent) {
            updateRegionDraft(nextEvent, { deferMove: false });
          }
        });
      }
      return true;
    }
    if (commit) {
      cancelPendingDraftUpdate();
    }
    const modelContext = getDraftModelContext(state.snapshot, { forceRefresh: commit });
    const model = chartMouseToModel(event, { modelContext });
    const draft = state.chartInteraction.draftRegion;
    if (!model || !draft) {
      return false;
    }
    const draftWindow = resolveDraftTimeWindow(event, model, { modelContext });
    const anchorStartTime = Date.parse(draft.anchor_started_at || draft.started_at || "");
    const anchorEndTime = Date.parse(draft.anchor_ended_at || draft.ended_at || draft.started_at || "");
    const targetStartTime = Date.parse(draftWindow.startedAtIso || "");
    const targetEndTime = Date.parse(draftWindow.endedAtIso || draftWindow.startedAtIso || "");
    if (Number.isFinite(anchorStartTime) && Number.isFinite(targetStartTime)) {
      if (targetStartTime < anchorStartTime) {
        draft.started_at = new Date(targetStartTime).toISOString();
        draft.ended_at = new Date(
          Number.isFinite(anchorEndTime) && anchorEndTime >= anchorStartTime
            ? anchorEndTime
            : anchorStartTime,
        ).toISOString();
      } else {
        draft.started_at = new Date(anchorStartTime).toISOString();
        draft.ended_at = new Date(
          Number.isFinite(targetEndTime) && targetEndTime >= targetStartTime
            ? targetEndTime
            : targetStartTime,
        ).toISOString();
      }
    } else {
      draft.started_at = draftWindow.startedAtIso;
      draft.ended_at = draftWindow.endedAtIso;
    }
    const anchorPrice = Number.isFinite(Number(draft.anchor_price)) ? Number(draft.anchor_price) : model.price;
    draft.price_low = Math.min(anchorPrice, model.price);
    draft.price_high = Math.max(anchorPrice, model.price);
    renderDraftRegionSurface({ commit });
    if (commit) {
      invalidateDraftModelContext();
    }
    return true;
  }

  return {
    visibleSpan,
    zoomChart,
    zoomPriceAxis,
    resetChartView,
    chartMouseToModel,
    pickCandleIndexFromEvent,
    selectCandle,
    beginRegionDraft,
    updateRegionDraft,
  };
}
