export function createChartInteractionController({
  state,
  els,
  renderChart,
  renderSnapshot,
  loadFootprintBarDetail,
  clampChartView,
}) {
  function visibleSpan() {
    if (!state.chartView) {
      return 0;
    }
    return state.chartView.endIndex - state.chartView.startIndex + 1;
  }

  function zoomChart(factor) {
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
      chart.timeScale().zoom(factor * 10);
      renderSnapshot();
    } else {
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
      renderSnapshot();
    }
  }

  function zoomPriceAxis(factor) {
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
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
      renderChart();
    }
  }

  function resetChartView() {
    const chart = window._lwChartState?.chartInstance;
    if (chart) {
      chart.timeScale().fitContent();
      renderSnapshot();
    } else {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      state.chartView = {
        startIndex: 0,
        endIndex: state.snapshot.candles.length - 1,
        yMin: null,
        yMax: null,
      };
      renderSnapshot();
    }
  }

  function chartMouseToModel(event) {
    const chart = window._lwChartState?.chartInstance;
    if (chart && state.chartMetrics) {
      const rect = els.chartContainer.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const time = chart.timeScale().coordinateToTime(x);
      const price = chart.priceScale("right").coordinateToPrice(y);
      if (time && price) {
        return {
          x,
          y,
          timestamp: time * 1000,
          price,
        };
      }
    }
    const metrics = state.chartMetrics;
    if (!metrics) {
      return null;
    }
    const rect = els.chartSvg?.getBoundingClientRect?.() || els.chartContainer?.getBoundingClientRect?.();
    if (!rect) return null;
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (x < metrics.leftPad || x > metrics.width - metrics.rightPad || y < metrics.topPad || y > metrics.height - metrics.bottomPad) {
      return null;
    }
    const ratioX = (x - metrics.leftPad) / metrics.chartWidth;
    const ratioY = (y - metrics.topPad) / metrics.chartHeight;
    const timestamp = metrics.visibleStartTime + ratioX * (metrics.visibleEndTime - metrics.visibleStartTime);
    const price = metrics.yMax - ratioY * (metrics.yMax - metrics.yMin);
    return { x, y, timestamp, price };
  }

  function pickCandleIndexFromEvent(event) {
    const chart = window._lwChartState?.chartInstance;
    const snapshot = state.snapshot;
    if (chart && snapshot?.candles?.length) {
      const rect = els.chartContainer.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const time = chart.timeScale().coordinateToTime(x);
      if (time) {
        const timestamp = time * 1000;
        const bar = snapshot.candles.find((c) => Math.abs(c.started_at - timestamp) < 120000);
        if (bar) {
          return snapshot.candles.indexOf(bar);
        }
      }
    }
    const model = chartMouseToModel(event);
    if (!model || !snapshot?.candles?.length || !state.chartView) {
      return null;
    }
    const localIndex = Math.max(0, Math.min(visibleSpan() - 1, Math.floor((model.x - state.chartMetrics.leftPad) / state.chartMetrics.candleSpacing)));
    return state.chartView.startIndex + localIndex;
  }

  async function selectCandle(globalIndex) {
    const snapshot = state.snapshot;
    const candle = snapshot?.candles?.[globalIndex];
    if (!candle) {
      return;
    }
    state.selectedCandleIndex = globalIndex;
    state.selectedFootprintBar = null;
    renderSnapshot();
    await loadFootprintBarDetail(candle.started_at);
    renderSnapshot();
  }

  function beginRegionDraft(event) {
    const model = chartMouseToModel(event);
    if (!model) {
      return;
    }
    state.chartInteraction.draftRegion = {
      started_at: new Date(model.timestamp).toISOString(),
      ended_at: new Date(model.timestamp).toISOString(),
      price_low: model.price,
      price_high: model.price,
    };
    renderChart();
  }

  function updateRegionDraft(event) {
    const model = chartMouseToModel(event);
    const draft = state.chartInteraction.draftRegion;
    if (!model || !draft) {
      return;
    }
    const startTime = new Date(draft.started_at).getTime();
    draft.ended_at = new Date(model.timestamp).toISOString();
    draft.price_low = Math.min(draft.price_low, model.price);
    draft.price_high = Math.max(draft.price_high, model.price);
    if (model.timestamp < startTime) {
      draft.started_at = new Date(model.timestamp).toISOString();
      draft.ended_at = new Date(startTime).toISOString();
    }
    renderChart();
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
