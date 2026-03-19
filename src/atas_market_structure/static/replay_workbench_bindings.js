export function createWorkbenchBindings({
  state,
  els,
  applyWindowPreset,
  handleBuildWithForceRefresh,
  handleAiReview,
  handlePresetAnalysis,
  buildManualRegionAnalysisPrompt,
  buildSelectedBarAnalysisPrompt,
  renderStatusStrip,
  createNewThread,
  handleAiChatSend,
  zoomChart,
  zoomPriceAxis,
  resetChartView,
  renderSnapshot,
  handleSaveRegion,
  handleRecordEntry,
  handleLookup,
  handleInvalidate,
  syncCacheKey,
  beginRegionDraft,
  updateLayoutDrag,
  updateRegionDraft,
  visibleSpan,
  clampChartView,
  pickCandleIndexFromEvent,
  selectCandle,
  finishLayoutDrag,
  renderChart,
  initializePanelToggles,
  initializeSectionToggles,
  scheduleChartRerender,
}) {
  function attachBindings() {
    els.buildButton.addEventListener("click", handleBuildWithForceRefresh);
    els.preset7d1mButton.addEventListener("click", async () => {
      applyWindowPreset("5m", 7);
      await handleBuildWithForceRefresh();
    });
    els.preset3d5mButton.addEventListener("click", async () => {
      applyWindowPreset("1m", 7);
      await handleBuildWithForceRefresh();
    });
    els.preset1d1mButton.addEventListener("click", async () => {
      applyWindowPreset("5m", 15);
      await handleBuildWithForceRefresh();
    });
    els.aiReviewButton.addEventListener("click", handleAiReview);
    els.refreshAllButton.addEventListener("click", handleBuildWithForceRefresh);
    els.recent20BarsButton.addEventListener("click", () => handlePresetAnalysis("recent_20_bars", "请分析最近20根K线，指出哪里不能开仓。"));
    els.recent20MinutesButton.addEventListener("click", () => handlePresetAnalysis("recent_20_minutes", "请分析最近20分钟K线，说明当前微趋势是否和大趋势配合。"));
    els.focusRegionsButton.addEventListener("click", () => handlePresetAnalysis("focus_regions", "请分析重点价格区域，标出最该盯的支撑阻力与无效开仓区。"));
    els.trappedOrdersButton.addEventListener("click", () => handlePresetAnalysis("trapped_large_orders", "请分析大单是否被套，以及哪些区域可能触发解套或止损。"));
    els.liveDepthButton.addEventListener("click", () => handlePresetAnalysis("live_depth", "请分析实时挂单数据，判断吸收、补单、诱导和当前不该开仓的位置。"));
    els.manualRegionButton.addEventListener("click", async () => {
      try {
        await handlePresetAnalysis("focus_regions", buildManualRegionAnalysisPrompt());
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });
    els.selectedBarButton.addEventListener("click", async () => {
      try {
        await handlePresetAnalysis("focus_regions", buildSelectedBarAnalysisPrompt());
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });
    els.aiNewThreadButton.addEventListener("click", () => {
      createNewThread();
    });
    els.aiChatSendButton.addEventListener("click", handleAiChatSend);
    els.zoomInButton.addEventListener("click", () => zoomChart(0.6));
    els.zoomOutButton.addEventListener("click", () => zoomChart(1.6));
    els.zoomPriceInButton.addEventListener("click", () => zoomPriceAxis(0.84));
    els.zoomPriceOutButton.addEventListener("click", () => zoomPriceAxis(1.2));
    els.resetViewButton.addEventListener("click", resetChartView);
    els.armRegionButton.addEventListener("click", () => {
      state.chartInteraction.regionMode = !state.chartInteraction.regionMode;
      if (!state.chartInteraction.regionMode) {
        state.chartInteraction.draftRegion = null;
      }
      renderSnapshot();
    });
    els.saveRegionButton.addEventListener("click", handleSaveRegion);
    els.aiChatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleAiChatSend();
      }
    });
    els.recordEntryButton.addEventListener("click", handleRecordEntry);
    els.lookupButton.addEventListener("click", handleLookup);
    els.invalidateButton.addEventListener("click", handleInvalidate);
    els.instrumentSymbol.addEventListener("input", syncCacheKey);
    els.displayTimeframe.addEventListener("change", syncCacheKey);
    els.windowStart.addEventListener("change", syncCacheKey);
    els.windowEnd.addEventListener("change", syncCacheKey);

    els.chartSvg.addEventListener("wheel", (event) => {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      event.preventDefault();
      if (event.shiftKey) {
        zoomPriceAxis(event.deltaY < 0 ? 0.84 : 1.2);
        return;
      }
      zoomChart(event.deltaY < 0 ? 0.8 : 1.25);
    }, { passive: false });

    els.chartSvg.addEventListener("mousedown", (event) => {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      if (event.button !== 0) {
        return;
      }
      event.preventDefault();
      if (state.chartInteraction.regionMode) {
        beginRegionDraft(event);
        return;
      }
      state.chartInteraction.panStartX = event.clientX;
      state.chartInteraction.panStartY = event.clientY;
      state.chartInteraction.panStartView = state.chartView ? { ...state.chartView } : null;
      state.chartInteraction.panStartPriceRange = state.chartView
        ? { yMin: state.chartView.yMin, yMax: state.chartView.yMax }
        : null;
      els.chartSvg.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (event) => {
      if (updateLayoutDrag(event)) {
        return;
      }
      if (state.chartInteraction.regionMode && state.chartInteraction.draftRegion) {
        updateRegionDraft(event);
        return;
      }
      if (state.chartInteraction.panStartX == null || !state.chartInteraction.panStartView || !state.chartMetrics || !state.snapshot?.candles?.length) {
        return;
      }
      const deltaX = event.clientX - state.chartInteraction.panStartX;
      const deltaY = event.clientY - state.chartInteraction.panStartY;
      const shiftBars = Math.round((-deltaX / state.chartMetrics.chartWidth) * visibleSpan());
      const nextStart = state.chartInteraction.panStartView.startIndex + shiftBars;
      const nextEnd = state.chartInteraction.panStartView.endIndex + shiftBars;
      state.chartView = clampChartView(state.snapshot.candles.length, nextStart, nextEnd, state.chartInteraction.panStartView);
      if (state.chartInteraction.panStartPriceRange && state.chartMetrics.chartHeight > 0) {
        const span = state.chartInteraction.panStartPriceRange.yMax - state.chartInteraction.panStartPriceRange.yMin;
        const priceShift = (deltaY / state.chartMetrics.chartHeight) * span;
        state.chartView.yMin = state.chartInteraction.panStartPriceRange.yMin + priceShift;
        state.chartView.yMax = state.chartInteraction.panStartPriceRange.yMax + priceShift;
      }
      renderChart();
    });

    window.addEventListener("mouseup", async (event) => {
      if (state.layout.dragKind) {
        finishLayoutDrag();
        return;
      }
      if (state.chartInteraction.regionMode && state.chartInteraction.draftRegion) {
        updateRegionDraft(event);
        return;
      }
      if (state.chartInteraction.panStartX != null && Math.abs(event.clientX - state.chartInteraction.panStartX) < 4) {
        const candleIndex = pickCandleIndexFromEvent(event);
        if (candleIndex != null) {
          await selectCandle(candleIndex);
        }
      }
      state.chartInteraction.panStartX = null;
      state.chartInteraction.panStartY = null;
      state.chartInteraction.panStartView = null;
      state.chartInteraction.panStartPriceRange = null;
      els.chartSvg.style.cursor = state.chartInteraction.regionMode ? "crosshair" : "grab";
    });

    window.addEventListener("blur", () => {
      state.chartInteraction.panStartX = null;
      state.chartInteraction.panStartY = null;
      state.chartInteraction.panStartView = null;
      state.chartInteraction.panStartPriceRange = null;
      finishLayoutDrag();
      els.chartSvg.style.cursor = state.chartInteraction.regionMode ? "crosshair" : "grab";
    });
  }

  function bootstrap() {
    initializePanelToggles();
    initializeSectionToggles();
    window.addEventListener("resize", scheduleChartRerender);
    applyWindowPreset("1m", 7);
    window.requestAnimationFrame(async () => {
      if (state.autoBootstrapped) {
        return;
      }
      state.autoBootstrapped = true;
      await handleBuildWithForceRefresh();
    });
  }

  return {
    attachBindings,
    bootstrap,
  };
}
