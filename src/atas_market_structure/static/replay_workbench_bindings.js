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
    if (els.buildButton) {
      els.buildButton.addEventListener("click", () => {
        try {
          handleBuildWithForceRefresh();
        } catch (error) {
          console.error("加载图表按钮错误:", error);
          renderStatusStrip([{ label: "加载图表失败", variant: "warn" }]);
        }
      });
    }
    if (els.preset7d1mButton) {
      els.preset7d1mButton.addEventListener("click", async () => {
        try {
          applyWindowPreset("5m", 7);
          await handleBuildWithForceRefresh();
        } catch (error) {
          console.error("预设按钮错误:", error);
          renderStatusStrip([{ label: "应用预设失败", variant: "warn" }]);
        }
      });
    }
    if (els.preset3d5mButton) {
      els.preset3d5mButton.addEventListener("click", async () => {
        try {
          applyWindowPreset("1m", 7);
          await handleBuildWithForceRefresh();
        } catch (error) {
          console.error("预设按钮错误:", error);
          renderStatusStrip([{ label: "应用预设失败", variant: "warn" }]);
        }
      });
    }
    if (els.preset1d1mButton) {
      els.preset1d1mButton.addEventListener("click", async () => {
        try {
          applyWindowPreset("5m", 15);
          await handleBuildWithForceRefresh();
        } catch (error) {
          console.error("预设按钮错误:", error);
          renderStatusStrip([{ label: "应用预设失败", variant: "warn" }]);
        }
      });
    }
    if (els.aiReviewButton) {
      els.aiReviewButton.addEventListener("click", () => {
        try {
          handleAiReview();
        } catch (error) {
          console.error("AI复盘按钮错误:", error);
          renderStatusStrip([{ label: "AI复盘失败", variant: "warn" }]);
        }
      });
    }
    if (els.refreshAllButton) {
      els.refreshAllButton.addEventListener("click", () => {
        try {
          handleBuildWithForceRefresh();
        } catch (error) {
          console.error("刷新数据按钮错误:", error);
          renderStatusStrip([{ label: "刷新数据失败", variant: "warn" }]);
        }
      });
    }
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
    els.aiNewThreadButton.addEventListener("click", async () => {
      await createNewThread();
    });
    els.aiChatSendButton.addEventListener("click", handleAiChatSend);
    if (els.zoomInButton) {
      els.zoomInButton.addEventListener("click", () => {
        try {
          zoomChart(0.6);
        } catch (error) {
          console.error("放大按钮错误:", error);
          renderStatusStrip([{ label: "放大操作失败", variant: "warn" }]);
        }
      });
    }
    if (els.zoomOutButton) {
      els.zoomOutButton.addEventListener("click", () => {
        try {
          zoomChart(1.6);
        } catch (error) {
          console.error("缩小按钮错误:", error);
          renderStatusStrip([{ label: "缩小操作失败", variant: "warn" }]);
        }
      });
    }
    if (els.zoomPriceInButton) {
      els.zoomPriceInButton.addEventListener("click", () => {
        try {
          zoomPriceAxis(0.84);
        } catch (error) {
          console.error("价格放大按钮错误:", error);
          renderStatusStrip([{ label: "价格放大操作失败", variant: "warn" }]);
        }
      });
    }
    if (els.zoomPriceOutButton) {
      els.zoomPriceOutButton.addEventListener("click", () => {
        try {
          zoomPriceAxis(1.2);
        } catch (error) {
          console.error("价格缩小按钮错误:", error);
          renderStatusStrip([{ label: "价格缩小操作失败", variant: "warn" }]);
        }
      });
    }
    if (els.resetViewButton) {
      els.resetViewButton.addEventListener("click", () => {
        try {
          resetChartView();
        } catch (error) {
          console.error("重置视图按钮错误:", error);
          renderStatusStrip([{ label: "重置视图失败", variant: "warn" }]);
        }
      });
    }
    if (els.armRegionButton) {
      els.armRegionButton.addEventListener("click", () => {
        try {
          state.chartInteraction.regionMode = !state.chartInteraction.regionMode;
          if (!state.chartInteraction.regionMode) {
            state.chartInteraction.draftRegion = null;
          }
          renderSnapshot();
        } catch (error) {
          console.error("框选区域按钮错误:", error);
          renderStatusStrip([{ label: "框选区域操作失败", variant: "warn" }]);
        }
      });
    }
    if (els.saveRegionButton) {
      els.saveRegionButton.addEventListener("click", () => {
        try {
          handleSaveRegion();
        } catch (error) {
          console.error("保存区域按钮错误:", error);
          renderStatusStrip([{ label: "保存区域失败", variant: "warn" }]);
        }
      });
    }
    els.aiChatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleAiChatSend();
      }
    });
    if (els.recordEntryButton) {
      els.recordEntryButton.addEventListener("click", () => {
        try {
          handleRecordEntry();
        } catch (error) {
          console.error("记录开仓按钮错误:", error);
          renderStatusStrip([{ label: "记录开仓失败", variant: "warn" }]);
        }
      });
    }
    if (els.lookupButton) {
      els.lookupButton.addEventListener("click", () => {
        try {
          handleLookup();
        } catch (error) {
          console.error("查看缓存按钮错误:", error);
          renderStatusStrip([{ label: "查看缓存失败", variant: "warn" }]);
        }
      });
    }
    if (els.invalidateButton) {
      els.invalidateButton.addEventListener("click", () => {
        try {
          handleInvalidate();
        } catch (error) {
          console.error("清除缓存按钮错误:", error);
          renderStatusStrip([{ label: "清除缓存失败", variant: "warn" }]);
        }
      });
    }
    els.instrumentSymbol.addEventListener("input", syncCacheKey);
    els.displayTimeframe.addEventListener("change", syncCacheKey);
    els.windowStart.addEventListener("change", syncCacheKey);
    els.windowEnd.addEventListener("change", syncCacheKey);

    const chartContainer = els.chartContainer || els.chartSvg;

    chartContainer.addEventListener("wheel", (event) => {
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

    chartContainer.addEventListener("mousedown", (event) => {
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
      chartContainer.style.cursor = "grabbing";
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
      chartContainer.style.cursor = state.chartInteraction.regionMode ? "crosshair" : "grab";
    });

    window.addEventListener("blur", () => {
      state.chartInteraction.panStartX = null;
      state.chartInteraction.panStartY = null;
      state.chartInteraction.panStartView = null;
      state.chartInteraction.panStartPriceRange = null;
      finishLayoutDrag();
      chartContainer.style.cursor = state.chartInteraction.regionMode ? "crosshair" : "grab";
    });
  }

  function bootstrap() {
    initializePanelToggles();
    initializeSectionToggles();
    window.addEventListener("resize", scheduleChartRerender);
    applyWindowPreset("1m", 1); // 默认1分钟1天，最大7天
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
