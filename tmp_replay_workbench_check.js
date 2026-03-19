
    const state = {
      buildResponse: null,
      snapshot: null,
      operatorEntries: [],
      manualRegions: [],
      aiReview: null,
      aiThreads: [],
      activeAiThreadId: null,
      pendingAiAttachments: [],
      currentReplayIngestionId: null,
      selectedCandleIndex: null,
      selectedFootprintBar: null,
      chartView: null,
      chartInteraction: {
        regionMode: false,
        draftRegion: null,
        // Lightweight-charts 版区域框选拖拽状态
        regionDragActive: false,
        regionDragStart: null,
      },
      liveStatus: null,
      liveTail: null,
      liveRenderedPrice: null,
      livePriceAnimationFrame: null,
      livePriceAnimationFrom: null,
      livePriceAnimationTarget: null,
      livePriceAnimationStartedAt: 0,
      pendingAiAttachmentSource: null,
      layerVisibility: {
        largeOrders: false,
        absorption: false,
        iceberg: false,
        replenishment: false,
        events: false,
        aiLevels: false,
        manualRegions: true,
        entries: true,
      },
    };

    const els = {
      cacheKey: document.getElementById("cacheKey"),
      instrumentSymbol: document.getElementById("instrumentSymbol"),
      displayTimeframe: document.getElementById("displayTimeframe"),
      windowStart: document.getElementById("windowStart"),
      windowEnd: document.getElementById("windowEnd"),
      chartInstanceId: document.getElementById("chartInstanceId"),
      minContinuousMessages: document.getElementById("minContinuousMessages"),
      forceRebuild: document.getElementById("forceRebuild"),
      invalidateReason: document.getElementById("invalidateReason"),
      aiModelOverride: document.getElementById("aiModelOverride"),
      forceAiRefresh: document.getElementById("forceAiRefresh"),
      instrumentSymbolClone: document.getElementById("instrumentSymbolClone"),
      displayTimeframeClone: document.getElementById("displayTimeframeClone"),
      windowStartClone: document.getElementById("windowStartClone"),
      windowEndClone: document.getElementById("windowEndClone"),
      buildButtonInline: document.getElementById("buildButtonInline"),
      aiReviewButtonInline: document.getElementById("aiReviewButtonInline"),
      lookupButtonInline: document.getElementById("lookupButtonInline"),
      recordEntryButtonInline: document.getElementById("recordEntryButtonInline"),
      layerLargeOrders: document.getElementById("layerLargeOrders"),
      layerAbsorption: document.getElementById("layerAbsorption"),
      layerIceberg: document.getElementById("layerIceberg"),
      layerReplenishment: document.getElementById("layerReplenishment"),
      layerEvents: document.getElementById("layerEvents"),
      layerAiLevels: document.getElementById("layerAiLevels"),
      layerManualRegions: document.getElementById("layerManualRegions"),
      layerEntries: document.getElementById("layerEntries"),
      shellLayout: document.getElementById("shellLayout"),
      leftPanel: document.getElementById("leftPanel"),
      rightPanel: document.getElementById("rightPanel"),
      toggleLeftPanelButton: document.getElementById("toggleLeftPanelButton"),
      toggleRightPanelButton: document.getElementById("toggleRightPanelButton"),
      restoreLeftPanelButton: document.getElementById("restoreLeftPanelButton"),
      restoreRightPanelButton: document.getElementById("restoreRightPanelButton"),
      leftResizeHandle: document.getElementById("leftResizeHandle"),
      rightResizeHandle: document.getElementById("rightResizeHandle"),
      entryExecutedAt: document.getElementById("entryExecutedAt"),
      entrySide: document.getElementById("entrySide"),
      entryPrice: document.getElementById("entryPrice"),
      entryStopPrice: document.getElementById("entryStopPrice"),
      entryQuantity: document.getElementById("entryQuantity"),
      entryTimeframe: document.getElementById("entryTimeframe"),
      entryThesis: document.getElementById("entryThesis"),
      regionLabel: document.getElementById("regionLabel"),
      regionThesis: document.getElementById("regionThesis"),
      regionSideBias: document.getElementById("regionSideBias"),
      regionTags: document.getElementById("regionTags"),
      regionNotes: document.getElementById("regionNotes"),
      buildButton: document.getElementById("buildButton"),
      preset7d1mButton: document.getElementById("preset7d1mButton"),
      preset3d5mButton: document.getElementById("preset3d5mButton"),
      preset1d1mButton: document.getElementById("preset1d1mButton"),
      aiReviewButton: document.getElementById("aiReviewButton"),
      refreshAllButton: document.getElementById("refreshAllButton"),
      recent20BarsButton: document.getElementById("recent20BarsButton"),
      recent20MinutesButton: document.getElementById("recent20MinutesButton"),
      focusRegionsButton: document.getElementById("focusRegionsButton"),
      trappedOrdersButton: document.getElementById("trappedOrdersButton"),
      liveDepthButton: document.getElementById("liveDepthButton"),
      manualRegionButton: document.getElementById("manualRegionButton"),
      selectedBarButton: document.getElementById("selectedBarButton"),
      aiChatSendButton: document.getElementById("aiChatSendButton"),
      aiChatAttachButton: document.getElementById("aiChatAttachButton"),
      aiChatImageInput: document.getElementById("aiChatImageInput"),
      aiChatClearAttachmentsButton: document.getElementById("aiChatClearAttachmentsButton"),
      zoomInButton: document.getElementById("zoomInButton"),
      zoomOutButton: document.getElementById("zoomOutButton"),
      zoomPriceInButton: document.getElementById("zoomPriceInButton"),
      zoomPriceOutButton: document.getElementById("zoomPriceOutButton"),
      resetViewButton: document.getElementById("resetViewButton"),
      armRegionButton: document.getElementById("armRegionButton"),
      saveRegionButton: document.getElementById("saveRegionButton"),
      recordEntryButton: document.getElementById("recordEntryButton"),
      lookupButton: document.getElementById("lookupButton"),
      invalidateButton: document.getElementById("invalidateButton"),
      streamAlertBanner: document.getElementById("streamAlertBanner"),
      streamAlertBannerMeta: document.getElementById("streamAlertBannerMeta"),
      statusStrip: document.getElementById("statusStrip"),
      liveStatusStrip: document.getElementById("liveStatusStrip"),
      buildProgress: document.getElementById("buildProgress"),
      buildProgressFill: document.getElementById("buildProgressFill"),
      buildProgressLabel: document.getElementById("buildProgressLabel"),
      buildProgressPercent: document.getElementById("buildProgressPercent"),
      chartFrame: document.getElementById("chartFrame"),
      chartViewportMeta: document.getElementById("chartViewportMeta"),
      chartPlaceholder: document.getElementById("chartPlaceholder"),
      chartStack: document.getElementById("chartStack"),
      chartContainer: document.getElementById("chartContainer"),
      volumePane: document.getElementById("volumePane"),
      volumeChartContainer: document.getElementById("volumeChartContainer"),
      volumeChartResizeHandle: document.getElementById("volumeChartResizeHandle"),
      embeddedAiPanel: document.getElementById("embeddedAiPanel"),
      embeddedAiNewThreadButton: document.getElementById("embeddedAiNewThreadButton"),
      embeddedPromptSelect: document.getElementById("embeddedPromptSelect"),
      embeddedUseSelectedBarButton: document.getElementById("embeddedUseSelectedBarButton"),
      embeddedUseRegionButton: document.getElementById("embeddedUseRegionButton"),
      embeddedSourceChipRow: document.getElementById("embeddedSourceChipRow"),
      sourceChipChart: document.getElementById("sourceChipChart"),
      sourceChipWidget: document.getElementById("sourceChipWidget"),
      sourceChipContext: document.getElementById("sourceChipContext"),
      embeddedAttachmentBadgeRow: document.getElementById("embeddedAttachmentBadgeRow"),
      embeddedAiChatThread: document.getElementById("embeddedAiChatThread"),
      embeddedAiImageInput: document.getElementById("embeddedAiImageInput"),
      embeddedAiChartShotButton: document.getElementById("embeddedAiChartShotButton"),
      embeddedAiAttachWidgetButton: document.getElementById("embeddedAiAttachWidgetButton"),
      embeddedAiClearButton: document.getElementById("embeddedAiClearButton"),
      embeddedAiInput: document.getElementById("embeddedAiInput"),
      embeddedAiSendButton: document.getElementById("embeddedAiSendButton"),
      buildSummary: document.getElementById("buildSummary"),
      selectedCandle: document.getElementById("selectedCandle"),
      footprintLadder: document.getElementById("footprintLadder"),
      manualRegions: document.getElementById("manualRegions"),
      focusRegions: document.getElementById("focusRegions"),
      strategyCandidates: document.getElementById("strategyCandidates"),
      operatorEntries: document.getElementById("operatorEntries"),
      aiReview: document.getElementById("aiReview"),
      aiThreadTabs: document.getElementById("aiThreadTabs"),
      aiNewThreadButton: document.getElementById("aiNewThreadButton"),
      aiChatThread: document.getElementById("aiChatThread"),
      aiChatResizeHandle: document.getElementById("aiChatResizeHandle"),
      aiChatInput: document.getElementById("aiChatInput"),
      aiChatAttachmentList: document.getElementById("aiChatAttachmentList"),
      aiBriefing: document.getElementById("aiBriefing"),
      eventTimeline: document.getElementById("eventTimeline"),
    };

    state.layout = {
      leftWidth: 320,
      rightWidth: 340,
      chatHeight: 420,
      volumePaneHeight: 170,
      dragKind: null,
      dragStartX: null,
      dragStartY: null,
      dragStartLeftWidth: null,
      dragStartRightWidth: null,
      dragStartChatHeight: null,
      dragStartVolumePaneHeight: null,
    };

    state.buildInFlight = false;
    state.autoBootstrapped = false;
    state.pendingChartRerender = false;
    state.liveStatusPollInFlight = false;
    state.liveTailPollInFlight = false;
    state.lastAutoRefreshStartedAt = 0;
    state.lastAutoCacheRefreshCompletedAt = 0;
    state.autoCacheRefreshIntervalMs = 60 * 1000;
    state.lastSessionSavedAt = 0;
    state.lastLiveStatusPollAt = 0;
    state.lastLiveTailPollAt = 0;
    state.sessionSaveIntervalMs = 5 * 1000;
    state.liveStatusPollIntervalMs = 3 * 1000;
    state.liveTailPollIntervalMs = 1 * 1000;

    // 图表：当前使用 Lightweight Charts。
    // - 1m 大窗口（例如 7 天）会有上万根 K 线；首次加载默认只展示最近 N 根，避免初次 fitContent 过度缩放。
    const CHART_INITIAL_SPAN_BARS = 420; // 首屏默认展示最近 420 根（约 7 小时 1m）

    // Lightweight Charts 状态
    state.lwc = {
      chart: null,
      volumeChart: null,
      candleSeries: null,
      volumeSeries: null,
      emaSeries: null,
      timeToIndex: new Map(),
      focusPriceLines: [],
      manualPriceLines: [],
      livePriceLine: null,
      initialized: false,
      initialRangeApplied: false,
      syncingVisibleRange: false,
      lastRenderedCandleCount: 0,
    };
    state.pendingSessionUiRestore = null;
    state.pendingSessionSaveTimer = null;
    state.gapBackfill = {
      lastFingerprint: "",
      lastRequestedAt: 0,
      lastRequestId: null,
      awaitingFreshHistory: false,
    };

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      let payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        payload = null;
      }
      if (!response.ok) {
        const message = payload?.detail || payload?.error || `request failed (${response.status})`;
        const error = new Error(message);
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload;
    }

    function normalizeAiServiceErrorMessage(error) {
      const rawMessage = String(error?.message || error || "请求失败").trim();
      const status = Number(error?.status || 0);
      const lowered = rawMessage.toLowerCase();

      if (
        lowered.includes("api key is not configured")
        || lowered.includes("openai_api_key")
        || lowered.includes("api key")
      ) {
        return "AI 服务未配置 OPENAI_API_KEY（或对应兼容接口密钥），请先在启动环境或 .env 中配置后重启服务。";
      }
      if (status === 503) {
        return `AI 服务当前不可用：${rawMessage}`;
      }
      if (status === 401) {
        return "AI 服务认证失败：请检查 OPENAI_API_KEY / OPENAI_BASE_URL / 模型配置是否正确。";
      }
      if (status === 403) {
        return "AI 服务被拒绝访问：请检查密钥权限、账户状态或接口供应商限制。";
      }
      if (status === 429) {
        return "AI 服务限流或额度不足：请稍后重试，或检查当前模型配额。";
      }
      if (status >= 500) {
        return `AI 服务发生后端错误：${rawMessage}`;
      }
      return rawMessage;
    }

    function parseUtcInputValue(value) {
      if (!value) {
        return null;
      }
      const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);
      if (!match) {
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime()) ? null : parsed;
      }
      const [, year, month, day, hour, minute, second = "0"] = match;
      return new Date(Date.UTC(
        Number(year),
        Number(month) - 1,
        Number(day),
        Number(hour),
        Number(minute),
        Number(second),
      ));
    }

    function pad2(value) {
      return String(value).padStart(2, "0");
    }

    function toUtcString(inputValue) {
      const parsed = parseUtcInputValue(inputValue);
      if (!parsed) {
        return null;
      }
      return parsed.toISOString();
    }

    function toUtcInputValue(value) {
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) {
        return "";
      }
      const year = date.getUTCFullYear();
      const month = pad2(date.getUTCMonth() + 1);
      const day = pad2(date.getUTCDate());
      const hour = pad2(date.getUTCHours());
      const minute = pad2(date.getUTCMinutes());
      return `${year}-${month}-${day}T${hour}:${minute}`;
    }

    function formatUtcDateTime(value, options = {}) {
      if (!value) {
        return "无";
      }
      const parsed = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(parsed.getTime())) {
        return String(value);
      }
      const includeYear = options.includeYear !== false;
      const includeSeconds = options.includeSeconds !== false;
      const year = parsed.getUTCFullYear();
      const month = pad2(parsed.getUTCMonth() + 1);
      const day = pad2(parsed.getUTCDate());
      const hour = pad2(parsed.getUTCHours());
      const minute = pad2(parsed.getUTCMinutes());
      const second = pad2(parsed.getUTCSeconds());
      const datePart = includeYear ? `${year}-${month}-${day}` : `${month}-${day}`;
      const timePart = includeSeconds ? `${hour}:${minute}:${second}` : `${hour}:${minute}`;
      return `${datePart} ${timePart} UTC`;
    }

    function buildCacheKey() {
      const symbol = (els.instrumentSymbol.value.trim() || "UNKNOWN").toUpperCase();
      const timeframe = els.displayTimeframe.value;
      const windowStart = toUtcString(els.windowStart.value) || "missing-start";
      const windowEnd = toUtcString(els.windowEnd.value) || "missing-end";
      return `${symbol}|${timeframe}|${windowStart}|${windowEnd}`;
    }

    function syncCacheKey() {
      els.cacheKey.value = buildCacheKey();
      if (els.instrumentSymbolClone) els.instrumentSymbolClone.value = els.instrumentSymbol.value.trim() || "NQ";
      if (els.displayTimeframeClone) els.displayTimeframeClone.value = timeframeLabel(els.displayTimeframe.value);
      if (els.windowStartClone) els.windowStartClone.value = formatUtcDateTime(toUtcString(els.windowStart.value), { includeSeconds: false });
      if (els.windowEndClone) els.windowEndClone.value = formatUtcDateTime(toUtcString(els.windowEnd.value), { includeSeconds: false });
    }

    function applyWindowPreset(timeframe, lookbackDays) {
      const now = new Date();
      const start = new Date(now.getTime() - (lookbackDays * 24 * 60 * 60 * 1000));
      els.displayTimeframe.value = timeframe;
      els.windowStart.value = toUtcInputValue(start);
      els.windowEnd.value = toUtcInputValue(now);
      syncCacheKey();
    }

    function scheduleChartRerender() {
      if (state.pendingChartRerender) {
        return;
      }
      state.pendingChartRerender = true;
      window.requestAnimationFrame(() => {
        state.pendingChartRerender = false;
        if (state.snapshot?.candles?.length) {
          renderChart();
        }
      });
    }

    function scheduleSessionStateSave(delayMs = 250) {
      if (state.pendingSessionSaveTimer != null) {
        window.clearTimeout(state.pendingSessionSaveTimer);
      }
      state.pendingSessionSaveTimer = window.setTimeout(() => {
        state.pendingSessionSaveTimer = null;
        saveSessionState();
      }, Math.max(0, delayMs));
    }

    function clampIndex(value, maxIndex) {
      if (!Number.isFinite(value)) {
        return 0;
      }
      return Math.max(0, Math.min(maxIndex, Math.round(value)));
    }

    function findNearestCandleIndexByStartedAt(snapshot, startedAt) {
      if (!snapshot?.candles?.length || !startedAt) {
        return null;
      }
      const targetTime = Date.parse(startedAt);
      if (Number.isNaN(targetTime)) {
        return null;
      }
      let nearestIndex = 0;
      let nearestDistance = Number.POSITIVE_INFINITY;
      snapshot.candles.forEach((candle, index) => {
        const currentTime = Date.parse(candle.started_at);
        if (Number.isNaN(currentTime)) {
          return;
        }
        const distance = Math.abs(currentTime - targetTime);
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestIndex = index;
        }
      });
      return nearestIndex;
    }

    function captureChartViewportState() {
      if (!state.lwc.chart || !state.snapshot?.candles?.length) {
        return null;
      }
      const logicalRange = state.lwc.chart.timeScale().getVisibleLogicalRange();
      if (!logicalRange) {
        return null;
      }
      const totalCandles = state.snapshot.candles.length;
      const lastIndex = Math.max(0, totalCandles - 1);
      const fromIndex = clampIndex(Math.floor(logicalRange.from), lastIndex);
      const toIndex = clampIndex(Math.ceil(logicalRange.to), lastIndex);
      const spanBars = Math.max(10, logicalRange.to - logicalRange.from);
      const pinnedToRight = logicalRange.to >= Math.max(0, lastIndex - 2);
      const viewport = {
        span_bars: Number(spanBars.toFixed(4)),
        pinned_to_right: pinnedToRight,
        right_offset_bars: Number((logicalRange.to - lastIndex).toFixed(4)),
        from_started_at: state.snapshot.candles[fromIndex]?.started_at || null,
        to_started_at: state.snapshot.candles[toIndex]?.started_at || null,
      };

      const chartHeight = Math.max(
        0,
        Math.round(els.chartContainer.getBoundingClientRect().height || els.chartContainer.clientHeight || 0),
      );
      if (state.lwc.candleSeries && chartHeight > 12) {
        const topPrice = state.lwc.candleSeries.coordinateToPrice(0);
        const bottomPrice = state.lwc.candleSeries.coordinateToPrice(chartHeight);
        if (Number.isFinite(topPrice) && Number.isFinite(bottomPrice)) {
          viewport.price_range = {
            min: Number(Math.min(topPrice, bottomPrice).toFixed(4)),
            max: Number(Math.max(topPrice, bottomPrice).toFixed(4)),
          };
        }
      }

      return viewport;
    }

    function captureSessionStatePayload() {
      return {
        ingestionId: state.currentReplayIngestionId,
        cacheKey: getActiveCacheKey(),
        timeframe: els.displayTimeframe.value,
        windowStart: els.windowStart.value,
        windowEnd: els.windowEnd.value,
        symbol: els.instrumentSymbol.value,
        controls: {
          chartInstanceId: els.chartInstanceId?.value || "",
          minContinuousMessages: els.minContinuousMessages?.value || "10",
          forceRebuild: Boolean(els.forceRebuild?.checked),
          aiModelOverride: els.aiModelOverride?.value || "",
          forceAiRefresh: Boolean(els.forceAiRefresh?.checked),
        },
        layout: {
          leftWidth: state.layout.leftWidth,
          rightWidth: state.layout.rightWidth,
          chatHeight: state.layout.chatHeight,
          volumePaneHeight: state.layout.volumePaneHeight,
          leftCollapsed: els.shellLayout.classList.contains("left-collapsed"),
          rightCollapsed: els.shellLayout.classList.contains("right-collapsed"),
        },
        layerVisibility: { ...state.layerVisibility },
        aiUi: {
          embeddedPrompt: els.embeddedPromptSelect?.value || "general",
          mainDraft: els.aiChatInput?.value || "",
          embeddedDraft: els.embeddedAiInput?.value || "",
        },
        selectedBarStartedAt: (
          state.selectedCandleIndex != null
          && state.snapshot?.candles?.[state.selectedCandleIndex]
            ? state.snapshot.candles[state.selectedCandleIndex].started_at
            : null
        ),
        chartViewport: captureChartViewportState(),
        ts: Date.now(),
      };
    }

    function applySavedLayoutState(savedSession) {
      const savedLayout = savedSession?.layout;
      if (!savedLayout) {
        return;
      }
      if (Number.isFinite(Number(savedLayout.leftWidth))) {
        state.layout.leftWidth = Math.max(260, Math.min(520, Number(savedLayout.leftWidth)));
      }
      if (Number.isFinite(Number(savedLayout.rightWidth))) {
        state.layout.rightWidth = Math.max(280, Math.min(560, Number(savedLayout.rightWidth)));
      }
      if (Number.isFinite(Number(savedLayout.chatHeight))) {
        state.layout.chatHeight = Math.max(220, Math.min(760, Number(savedLayout.chatHeight)));
      }
      if (Number.isFinite(Number(savedLayout.volumePaneHeight))) {
        state.layout.volumePaneHeight = Math.max(84, Math.min(420, Number(savedLayout.volumePaneHeight)));
      }
      applyLayoutWidths();
      setLeftPanelCollapsed(Boolean(savedLayout.leftCollapsed));
      setRightPanelCollapsed(Boolean(savedLayout.rightCollapsed));
    }

    function applySavedUiState(savedSession) {
      if (savedSession?.layerVisibility && typeof savedSession.layerVisibility === "object") {
        state.layerVisibility = {
          ...state.layerVisibility,
          ...savedSession.layerVisibility,
        };
        updateLayerButtons();
      }
      if (savedSession?.aiUi && typeof savedSession.aiUi === "object") {
        if (els.embeddedPromptSelect && savedSession.aiUi.embeddedPrompt) {
          els.embeddedPromptSelect.value = savedSession.aiUi.embeddedPrompt;
        }
        if (els.aiChatInput && typeof savedSession.aiUi.mainDraft === "string") {
          els.aiChatInput.value = savedSession.aiUi.mainDraft;
        }
        if (els.embeddedAiInput && typeof savedSession.aiUi.embeddedDraft === "string") {
          els.embeddedAiInput.value = savedSession.aiUi.embeddedDraft;
        }
      }
      if (savedSession?.controls && typeof savedSession.controls === "object") {
        if (els.chartInstanceId && typeof savedSession.controls.chartInstanceId === "string") {
          els.chartInstanceId.value = savedSession.controls.chartInstanceId;
        }
        if (els.minContinuousMessages && savedSession.controls.minContinuousMessages != null) {
          els.minContinuousMessages.value = String(savedSession.controls.minContinuousMessages);
        }
        if (els.forceRebuild) {
          els.forceRebuild.checked = Boolean(savedSession.controls.forceRebuild);
        }
        if (els.aiModelOverride && typeof savedSession.controls.aiModelOverride === "string") {
          els.aiModelOverride.value = savedSession.controls.aiModelOverride;
        }
        if (els.forceAiRefresh) {
          els.forceAiRefresh.checked = Boolean(savedSession.controls.forceAiRefresh);
        }
      }
    }

    function restoreChartViewportFromSession(snapshot) {
      const savedViewport = state.pendingSessionUiRestore?.chartViewport;
      if (!savedViewport || !state.lwc.chart || !snapshot?.candles?.length) {
        return false;
      }

      const totalCandles = snapshot.candles.length;
      const lastIndex = Math.max(0, totalCandles - 1);
      let from = null;
      let to = null;

      if (savedViewport.pinned_to_right) {
        const spanBars = Math.max(10, Number(savedViewport.span_bars || CHART_INITIAL_SPAN_BARS));
        const rightOffsetBars = Number.isFinite(Number(savedViewport.right_offset_bars))
          ? Math.min(Math.max(Number(savedViewport.right_offset_bars), 0), 1.25)
          : 0;
        to = lastIndex + rightOffsetBars;
        from = to - spanBars;
      } else {
        const fromIndex = findNearestCandleIndexByStartedAt(snapshot, savedViewport.from_started_at);
        const toIndex = findNearestCandleIndexByStartedAt(snapshot, savedViewport.to_started_at);
        const spanBars = Math.max(10, Number(savedViewport.span_bars || 0));
        if (fromIndex != null && toIndex != null && toIndex >= fromIndex) {
          from = fromIndex;
          to = toIndex;
        } else if (toIndex != null) {
          to = toIndex;
          from = to - spanBars;
        }
      }

      if (!Number.isFinite(from) || !Number.isFinite(to)) {
        return false;
      }

      state.lwc.chart.timeScale().setVisibleLogicalRange({ from, to });

      const rightPriceScale = typeof state.lwc.chart.priceScale === "function"
        ? state.lwc.chart.priceScale("right")
        : null;
      if (
        savedViewport.price_range
        && rightPriceScale
        && typeof rightPriceScale.setVisibleRange === "function"
        && Number.isFinite(Number(savedViewport.price_range.min))
        && Number.isFinite(Number(savedViewport.price_range.max))
      ) {
        rightPriceScale.setVisibleRange({
          from: Number(savedViewport.price_range.min),
          to: Number(savedViewport.price_range.max),
        });
      }

      state.pendingSessionUiRestore = null;
      state.lwc.initialRangeApplied = true;
      return true;
    }

    function setBuildProgress(active, percent = 0, label = "") {
      els.buildProgress.classList.toggle("active", active);
      els.buildProgressFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
      els.buildProgressPercent.textContent = `${Math.round(Math.max(0, Math.min(100, percent)))}%`;
      if (label) {
        els.buildProgressLabel.textContent = label;
      }
    }

    function timeframeLabel(value) {
      return {
        "1m": "1分",
        "5m": "5分",
        "15m": "15分",
        "30m": "30分",
        "1h": "1小时",
        "1d": "日线",
      }[value] || value;
    }

    function translateAction(action) {
      return {
        cache_hit: "命中缓存",
        built_from_local_history: "已从本地连续流重建",
        built_from_atas_history: "已从 ATAS 历史重建",
        atas_fetch_required: "需要补抓 ATAS 历史",
      }[action] || action;
    }

    function translateVerificationStatus(status) {
      return {
        unverified: "未核对",
        verified: "已核对",
        durable: "已固化",
        invalidated: "已作废",
      }[status] || status;
    }

    function translateAcquisitionMode(mode) {
      return {
        cache_reuse: "缓存复用",
        local_history: "本地连续流",
        atas_fetch: "ATAS 历史",
      }[mode] || mode;
    }

    function createThreadId() {
      return `thread-${Math.random().toString(16).slice(2, 10)}`;
    }

    function getActiveCacheKey() {
      return state.snapshot?.cache_key || els.cacheKey.value.trim() || buildCacheKey();
    }

    function getAiThreadStorageKey(options = {}) {
      if (typeof options === "string") {
        options = { ingestionId: options };
      }
      const cacheKey = options.cacheKey || state.snapshot?.cache_key || els.cacheKey.value.trim() || null;
      if (cacheKey) {
        return `atas_workbench_ai_threads:${cacheKey}`;
      }
      const effectiveIngestionId = options.ingestionId || state.currentReplayIngestionId || "default";
      return `atas_workbench_ai_threads:${effectiveIngestionId}`;
    }

    function saveAiThreadsToStorage() {
      try {
        const payload = {
          cacheKey: getActiveCacheKey(),
          ingestionId: state.currentReplayIngestionId,
          activeAiThreadId: state.activeAiThreadId || "main",
          aiThreads: (state.aiThreads || []).map((thread) => ({
            id: thread.id,
            title: thread.title,
            messages: Array.isArray(thread.messages) ? thread.messages : [],
            turns: Array.isArray(thread.turns) ? thread.turns : [],
          })),
          ts: Date.now(),
        };
        localStorage.setItem(getAiThreadStorageKey({ cacheKey: payload.cacheKey }), JSON.stringify(payload));
      } catch (error) {}
    }

    function loadAiThreadsFromStorage(ingestionId, cacheKey = null) {
      try {
        const storageKeys = [
          cacheKey ? getAiThreadStorageKey({ cacheKey }) : null,
          ingestionId ? getAiThreadStorageKey({ ingestionId }) : null,
        ].filter(Boolean);
        let raw = null;
        for (const key of storageKeys) {
          raw = localStorage.getItem(key);
          if (raw) {
            break;
          }
        }
        if (!raw) {
          return false;
        }
        const payload = JSON.parse(raw);
        const threads = Array.isArray(payload?.aiThreads) ? payload.aiThreads : [];
        state.aiThreads = threads.map((thread, index) => ({
          id: thread?.id || `thread-restored-${index + 1}`,
          title: thread?.title || `线程 ${index + 1}`,
          messages: Array.isArray(thread?.messages) ? thread.messages : [],
          turns: Array.isArray(thread?.turns) ? thread.turns : [],
        }));
        state.activeAiThreadId = payload?.activeAiThreadId || state.aiThreads[0]?.id || "main";
        if (!state.aiThreads.length) {
          ensureThread("main", "主线程");
        }
        return true;
      } catch (error) {
        return false;
      }
    }

    function resetAiThreadsState() {
      state.aiThreads = [];
      state.activeAiThreadId = "main";
      ensureThread("main", "主线程");
    }

    function ensureThread(threadId, title) {
      let thread = state.aiThreads.find((item) => item.id === threadId);
      if (!thread) {
        thread = {
          id: threadId,
          title,
          messages: [],
          turns: [],
        };
        state.aiThreads.push(thread);
      }
      return thread;
    }

    function getActiveThread() {
      if (!state.activeAiThreadId) {
        state.activeAiThreadId = "main";
      }
      return ensureThread(state.activeAiThreadId, "主线程");
    }

    function setActiveThread(threadId, title = "主线程") {
      const thread = ensureThread(threadId, title);
      state.activeAiThreadId = thread.id;
      saveAiThreadsToStorage();
      scheduleSessionStateSave();
      renderAiThreadTabs();
      renderAiChat();
      return thread;
    }

    function getPresetThreadMeta(preset) {
      return {
        recent_20_bars: { id: "recent-20-bars", title: "最近20根K线" },
        recent_20_minutes: { id: "recent-20-minutes", title: "最近20分钟" },
        focus_regions: { id: "focus-regions", title: "重点区域" },
        trapped_large_orders: { id: "trapped-large-orders", title: "被套大单" },
        live_depth: { id: "live-depth", title: "实时挂单" },
        general: { id: "main", title: "主线程" },
      }[preset] || { id: createThreadId(), title: "新线程" };
    }

    function renderAiThreadTabs() {
      const activeThread = getActiveThread();
      els.aiThreadTabs.innerHTML = "";
      state.aiThreads.forEach((thread) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `thread-tab ${thread.id === activeThread.id ? "active" : ""}`.trim();
        button.textContent = thread.title;
        button.addEventListener("click", () => {
          state.activeAiThreadId = thread.id;
          saveAiThreadsToStorage();
          scheduleSessionStateSave();
          renderAiThreadTabs();
          renderAiChat();
        });
        els.aiThreadTabs.appendChild(button);
      });
    }

    function appendAiChatMessage(role, content, meta = {}, threadId = null, threadTitle = "主线程") {
      const thread = ensureThread(threadId || state.activeAiThreadId || "main", threadTitle);
      thread.messages.push({ role, content, meta });
      if (!state.activeAiThreadId) {
        state.activeAiThreadId = thread.id;
      }
      saveAiThreadsToStorage();
      renderAiThreadTabs();
      renderAiChat();
    }

    function applyLayoutWidths() {
      els.shellLayout.style.setProperty("--left-panel-width", `${state.layout.leftWidth}px`);
      els.shellLayout.style.setProperty("--right-panel-width", `${state.layout.rightWidth}px`);
      els.shellLayout.style.setProperty("--chat-thread-height", `${state.layout.chatHeight}px`);
      els.chartFrame.style.setProperty("--volume-pane-height", `${state.layout.volumePaneHeight}px`);
      scheduleChartRerender();
      scheduleSessionStateSave();
    }

    function setLeftPanelCollapsed(collapsed) {
      els.shellLayout.classList.toggle("left-collapsed", collapsed);
      els.toggleLeftPanelButton.textContent = collapsed ? "▶" : "◀";
      els.restoreLeftPanelButton.setAttribute("aria-hidden", collapsed ? "false" : "true");
      scheduleChartRerender();
      scheduleSessionStateSave();
    }

    function setRightPanelCollapsed(collapsed) {
      els.shellLayout.classList.toggle("right-collapsed", collapsed);
      els.toggleRightPanelButton.textContent = collapsed ? "◀" : "▶";
      els.restoreRightPanelButton.setAttribute("aria-hidden", collapsed ? "false" : "true");
      scheduleChartRerender();
      scheduleSessionStateSave();
    }

    function beginLayoutDrag(kind, event) {
      event.preventDefault();
      event.stopPropagation();
      state.layout.dragKind = kind;
      state.layout.dragStartX = event.clientX;
      state.layout.dragStartY = event.clientY;
      state.layout.dragStartLeftWidth = state.layout.leftWidth;
      state.layout.dragStartRightWidth = state.layout.rightWidth;
      state.layout.dragStartChatHeight = state.layout.chatHeight;
      state.layout.dragStartVolumePaneHeight = state.layout.volumePaneHeight;
      if (kind === "left") {
        els.leftResizeHandle.classList.add("dragging");
      } else if (kind === "right") {
        els.rightResizeHandle.classList.add("dragging");
      } else if (kind === "chat") {
        els.aiChatResizeHandle.classList.add("dragging");
      } else if (kind === "volume-pane") {
        els.volumeChartResizeHandle.classList.add("dragging");
      }
      document.body.style.userSelect = "none";
      document.body.style.cursor = (kind === "chat" || kind === "volume-pane") ? "row-resize" : "col-resize";
    }

    function updateLayoutDrag(event) {
      if (!state.layout.dragKind) {
        return false;
      }
      if (state.layout.dragKind === "left") {
        const nextWidth = state.layout.dragStartLeftWidth + (event.clientX - state.layout.dragStartX);
        state.layout.leftWidth = Math.max(260, Math.min(520, nextWidth));
      } else if (state.layout.dragKind === "right") {
        const nextWidth = state.layout.dragStartRightWidth - (event.clientX - state.layout.dragStartX);
        state.layout.rightWidth = Math.max(280, Math.min(560, nextWidth));
      } else if (state.layout.dragKind === "chat") {
        const nextHeight = state.layout.dragStartChatHeight + (event.clientY - state.layout.dragStartY);
        state.layout.chatHeight = Math.max(220, Math.min(760, nextHeight));
      } else if (state.layout.dragKind === "volume-pane") {
        const nextHeight = state.layout.dragStartVolumePaneHeight + (event.clientY - state.layout.dragStartY);
        const chartFrameHeight = Math.max(360, Math.round(els.chartFrame.getBoundingClientRect().height || 0));
        const minHeight = 84;
        const maxHeight = Math.max(140, Math.floor(chartFrameHeight * 0.42));
        state.layout.volumePaneHeight = Math.max(minHeight, Math.min(maxHeight, nextHeight));
      }
      applyLayoutWidths();
      return true;
    }

    function finishLayoutDrag() {
      if (!state.layout.dragKind) {
        return;
      }
      els.leftResizeHandle.classList.remove("dragging");
      els.rightResizeHandle.classList.remove("dragging");
      els.aiChatResizeHandle.classList.remove("dragging");
      els.volumeChartResizeHandle.classList.remove("dragging");
      state.layout.dragKind = null;
      state.layout.dragStartX = null;
      state.layout.dragStartY = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    }

    function initializePanelToggles() {
      applyLayoutWidths();
      setLeftPanelCollapsed(els.shellLayout.classList.contains("left-collapsed"));
      setRightPanelCollapsed(els.shellLayout.classList.contains("right-collapsed"));

      els.toggleLeftPanelButton.addEventListener("click", () => {
        setLeftPanelCollapsed(!els.shellLayout.classList.contains("left-collapsed"));
      });
      els.toggleRightPanelButton.addEventListener("click", () => {
        setRightPanelCollapsed(!els.shellLayout.classList.contains("right-collapsed"));
      });
      els.restoreLeftPanelButton.addEventListener("click", () => {
        setLeftPanelCollapsed(false);
      });
      els.restoreRightPanelButton.addEventListener("click", () => {
        setRightPanelCollapsed(false);
      });
      els.leftResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("left", event));
      els.rightResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("right", event));
      els.aiChatResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("chat", event));
      els.volumeChartResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("volume-pane", event));
    }

    function initializeSectionToggles() {
      document.querySelectorAll(".sidebar .section").forEach((section) => {
        if (section.dataset.toggleReady === "true") {
          return;
        }
        const heading = section.querySelector(":scope > h3");
        if (!heading) {
          return;
        }
        const content = document.createElement("div");
        content.className = "section-content";
        while (heading.nextSibling) {
          content.appendChild(heading.nextSibling);
        }
        const header = document.createElement("div");
        header.className = "section-header";
        const title = document.createElement("h3");
        title.textContent = heading.textContent;
        header.appendChild(title);
        section.innerHTML = "";
        section.appendChild(header);
        section.appendChild(content);
        section.dataset.toggleReady = "true";
      });
    }

    function renderStatusStrip(items) {
      els.statusStrip.innerHTML = "";
      items.forEach((item) => {
        const chip = document.createElement("div");
        chip.className = `chip ${item.variant || ""}`.trim();
        chip.textContent = item.label;
        els.statusStrip.appendChild(chip);
      });
    }

    function renderLiveStatusStrip(items) {
      els.liveStatusStrip.innerHTML = "";
      items.forEach((item) => {
        const chip = document.createElement("div");
        chip.className = `chip ${item.variant || ""}`.trim();
        chip.textContent = item.label;
        els.liveStatusStrip.appendChild(chip);
      });
    }

    function buildGapSegmentsFromSnapshot(snapshot) {
      const gaps = Array.isArray(snapshot?.raw_features?.candle_gaps) ? snapshot.raw_features.candle_gaps : [];
      return gaps
        .map((item) => ({
          prev_ended_at: item.prev_ended_at || item.prevEndedAt || item.prev_started_at || item.prevStartedAt || null,
          next_started_at: item.next_started_at || item.nextStartedAt || null,
          missing_bar_count: Number(item.missing_bar_count ?? item.missingBarCount ?? 0),
        }))
        .filter((item) => item.next_started_at && Number.isFinite(item.missing_bar_count) && item.missing_bar_count > 0);
    }

    function buildGapBackfillFingerprint(payload) {
      const segments = (payload.missing_segments || [])
        .map((segment) => `${segment.prev_ended_at || "null"}>${segment.next_started_at}:${segment.missing_bar_count}`)
        .join("|");
      return [
        payload.cache_key || "",
        payload.instrument_symbol || "",
        payload.display_timeframe || "",
        payload.window_start || "",
        payload.window_end || "",
        payload.reason || "",
        segments,
      ].join("::");
    }

    async function requestAtasBackfill(payload, options = {}) {
      if (!payload?.instrument_symbol || !payload?.display_timeframe || !payload?.window_start || !payload?.window_end) {
        return null;
      }
      const fingerprint = buildGapBackfillFingerprint(payload);
      const now = Date.now();
      if (!options.force && fingerprint === state.gapBackfill.lastFingerprint && now - state.gapBackfill.lastRequestedAt < 90 * 1000) {
        return null;
      }

      const result = await fetchJson("/api/v1/workbench/atas-backfill-requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.gapBackfill.lastFingerprint = fingerprint;
      state.gapBackfill.lastRequestedAt = now;
      state.gapBackfill.lastRequestId = result?.request?.request_id || null;
      state.gapBackfill.awaitingFreshHistory = true;
      renderStatusStrip([
        {
          label: result?.reused_existing_request ? "已复用 ATAS 补数请求" : "已向 ATAS 发出自动补数请求",
          variant: "emphasis",
        },
      ]);
      return result;
    }

    async function maybeRequestSnapshotGapBackfill(snapshot) {
      const missingSegments = buildGapSegmentsFromSnapshot(snapshot);
      const gapCount = Number(snapshot?.raw_features?.candle_gap_count || 0);
      if (!missingSegments.length && gapCount <= 0) {
        return null;
      }
      return await requestAtasBackfill({
        cache_key: snapshot?.cache_key || getActiveCacheKey(),
        instrument_symbol: snapshot?.instrument?.symbol || els.instrumentSymbol.value.trim(),
        display_timeframe: snapshot?.display_timeframe || els.displayTimeframe.value,
        window_start: snapshot?.window_start || toUtcString(els.windowStart.value),
        window_end: snapshot?.window_end || toUtcString(els.windowEnd.value),
        chart_instance_id: els.chartInstanceId.value.trim() || null,
        missing_segments: missingSegments,
        reason: "candle_gap_detected",
        request_history_bars: true,
        request_history_footprint: true,
      });
    }

    async function maybeRequestBuildResultBackfill(result) {
      if (!result?.atas_fetch_request) {
        return null;
      }
      return await requestAtasBackfill({
        cache_key: result.cache_key || getActiveCacheKey(),
        instrument_symbol: result.atas_fetch_request.instrument_symbol || els.instrumentSymbol.value.trim(),
        display_timeframe: result.atas_fetch_request.display_timeframe || els.displayTimeframe.value,
        window_start: result.atas_fetch_request.window_start || toUtcString(els.windowStart.value),
        window_end: result.atas_fetch_request.window_end || toUtcString(els.windowEnd.value),
        chart_instance_id: result.atas_fetch_request.chart_instance_id || els.chartInstanceId.value.trim() || null,
        missing_segments: [],
        reason: "replay_build_missing_history",
        request_history_bars: true,
        request_history_footprint: true,
      });
    }

    function renderStreamAlertBanner(status) {
      const shouldShow = status && (status.stream_state === "stale" || status.stream_state === "offline");
      els.streamAlertBanner.classList.toggle("visible", shouldShow);
      if (!shouldShow) {
        els.streamAlertBannerMeta.textContent = "";
        return;
      }
      const lagText = status.latest_adapter_sync_lag_seconds != null
        ? `最后一次成功同步在 ${formatLagSeconds(status.latest_adapter_sync_lag_seconds)}`
        : "当前没有可用同步数据";
      const syncTimeText = status.latest_adapter_sync_at
        ? `同步时间：${formatShortDateTime(status.latest_adapter_sync_at)}`
        : "同步时间未知";
      els.streamAlertBannerMeta.textContent = `${lagText} · ${syncTimeText}`;
    }

    function formatLagSeconds(seconds) {
      if (seconds == null) {
        return "未知";
      }
      if (seconds < 60) {
        return `${seconds}秒前`;
      }
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      if (minutes < 60) {
        return remainder ? `${minutes}分${remainder}秒前` : `${minutes}分钟前`;
      }
      const hours = Math.floor(minutes / 60);
      const minuteRemainder = minutes % 60;
      return minuteRemainder ? `${hours}小时${minuteRemainder}分钟前` : `${hours}小时前`;
    }

    function formatShortDateTime(value) {
      return formatUtcDateTime(value, { includeYear: false, includeSeconds: true });
    }

    function buildLiveStatusChips(status) {
      if (!status) {
        return [{ label: "实时状态未检查", variant: "" }];
      }
      const stateVariant = {
        live: "good",
        delayed: "emphasis",
        stale: "warn",
        offline: "warn",
      }[status.stream_state] || "";
      const chips = [
        { label: `流状态：${status.stream_state}`, variant: stateVariant },
      ];
      if (status.latest_adapter_sync_lag_seconds != null) {
        chips.push({
          label: `最新同步：${formatLagSeconds(status.latest_adapter_sync_lag_seconds)}`,
          variant: status.latest_adapter_sync_lag_seconds <= 10 ? "good" : status.latest_adapter_sync_lag_seconds <= 60 ? "emphasis" : "warn",
        });
      } else {
        chips.push({ label: "最新同步：无数据", variant: "warn" });
      }
      if (status.latest_adapter_sync_at) {
        chips.push({ label: `同步时间：${formatShortDateTime(status.latest_adapter_sync_at)}`, variant: "" });
      }
      if (status.should_refresh_snapshot) {
        chips.push({
          label: "检测到更新：将刷新快照",
          variant: "emphasis",
        });
      } else if (status.stream_state === "stale" || status.stream_state === "offline") {
        chips.push({
          label: "当前快照仅跟到最后一次同步，实时流已陈旧/中断",
          variant: "warn",
        });
      } else {
        chips.push({
          label: "当前快照已跟到最新同步",
          variant: "good",
        });
      }
      return chips;
    }

    function buildRequestPayload() {
      syncCacheKey();
      return {
        cache_key: els.cacheKey.value.trim(),
        instrument_symbol: els.instrumentSymbol.value.trim(),
        display_timeframe: els.displayTimeframe.value,
        window_start: toUtcString(els.windowStart.value),
        window_end: toUtcString(els.windowEnd.value),
        chart_instance_id: els.chartInstanceId.value.trim() || null,
        force_rebuild: els.forceRebuild.checked,
        min_continuous_messages: Number(els.minContinuousMessages.value || 10),
      };
    }

    async function loadSnapshotByIngestionId(ingestionId) {
      const ingestion = await fetchJson(`/api/v1/ingestions/${encodeURIComponent(ingestionId)}`);
      const ingestionChanged = state.currentReplayIngestionId !== ingestionId;
      state.currentReplayIngestionId = ingestionId;
      state.snapshot = ingestion.observed_payload;
      state.liveTail = null;
      state.liveRenderedPrice = null;
      state.operatorEntries = [];
      state.manualRegions = [];
      state.aiReview = null;
      state.pendingAiAttachments = [];
      state.selectedCandleIndex = null;
      state.selectedFootprintBar = null;
      state.chartView = null;
      const effectiveCacheKey = ingestion.observed_payload?.cache_key || els.cacheKey.value.trim() || null;
      if (ingestionChanged || !state.aiThreads.length) {
        if (!loadAiThreadsFromStorage(ingestionId, effectiveCacheKey)) {
          resetAiThreadsState();
        }
      }
      await loadOperatorEntries();
      await loadManualRegions();
      syncEntryDefaultsFromSnapshot();
      renderSnapshot();
      await maybeRequestSnapshotGapBackfill(state.snapshot);
      const savedSelectedBarStartedAt = state.pendingSessionUiRestore?.selectedBarStartedAt || null;
      if (savedSelectedBarStartedAt) {
        const selectedIndex = findNearestCandleIndexByStartedAt(state.snapshot, savedSelectedBarStartedAt);
        if (selectedIndex != null) {
          await selectCandle(selectedIndex);
        }
      }
      await refreshLiveTail({ silently: true });
      scheduleSessionStateSave(0);
    }

    function cancelLivePriceAnimation() {
      if (state.livePriceAnimationFrame != null) {
        window.cancelAnimationFrame(state.livePriceAnimationFrame);
        state.livePriceAnimationFrame = null;
      }
    }

    function animateLivePriceTo(targetPrice) {
      if (!Number.isFinite(targetPrice)) {
        state.liveRenderedPrice = null;
        cancelLivePriceAnimation();
        updateLivePriceLine();
        return;
      }
      const startPrice = Number.isFinite(state.liveRenderedPrice) ? state.liveRenderedPrice : targetPrice;
      state.liveRenderedPrice = startPrice;
      state.livePriceAnimationFrom = startPrice;
      state.livePriceAnimationTarget = targetPrice;
      state.livePriceAnimationStartedAt = performance.now();
      cancelLivePriceAnimation();

      const durationMs = 850;
      const tick = (frameNow) => {
        const elapsed = frameNow - state.livePriceAnimationStartedAt;
        const progress = Math.max(0, Math.min(1, elapsed / durationMs));
        const eased = 1 - Math.pow(1 - progress, 3);
        state.liveRenderedPrice = state.livePriceAnimationFrom
          + ((state.livePriceAnimationTarget - state.livePriceAnimationFrom) * eased);
        updateLivePriceLine();
        if (progress < 1) {
          state.livePriceAnimationFrame = window.requestAnimationFrame(tick);
        } else {
          state.livePriceAnimationFrame = null;
          state.liveRenderedPrice = state.livePriceAnimationTarget;
          updateLivePriceLine();
        }
      };

      state.livePriceAnimationFrame = window.requestAnimationFrame(tick);
    }

    async function loadOperatorEntries() {
      if (!state.currentReplayIngestionId) {
        state.operatorEntries = [];
        return;
      }
      const result = await fetchJson(`/api/v1/workbench/operator-entries?replay_ingestion_id=${encodeURIComponent(state.currentReplayIngestionId)}`);
      state.operatorEntries = result.entries || [];
    }

    async function loadManualRegions() {
      if (!state.currentReplayIngestionId) {
        state.manualRegions = [];
        return;
      }
      const result = await fetchJson(`/api/v1/workbench/manual-regions?replay_ingestion_id=${encodeURIComponent(state.currentReplayIngestionId)}`);
      state.manualRegions = result.regions || [];
    }

    async function refreshLiveStatus(options = {}) {
      const autoRebuildIfNeeded = Boolean(options.autoRebuildIfNeeded);
      const silently = Boolean(options.silently);
      const allowImmediateRefresh = Boolean(options.allowImmediateRefresh);
      const refreshTail = options.refreshTail !== false;
      const symbol = (els.instrumentSymbol.value.trim() || state.snapshot?.instrument?.symbol || "").trim().toUpperCase();
      if (!symbol || state.liveStatusPollInFlight) {
        return state.liveStatus;
      }

      try {
        state.liveStatusPollInFlight = true;
        state.lastLiveStatusPollAt = Date.now();
        const params = new URLSearchParams({ instrument_symbol: symbol });
        if (state.currentReplayIngestionId) {
          params.set("replay_ingestion_id", state.currentReplayIngestionId);
        }
        const result = await fetchJson(`/api/v1/workbench/live-status?${params.toString()}`);
        state.liveStatus = result;
        renderStreamAlertBanner(result);
        renderLiveStatusStrip(buildLiveStatusChips(result));

        const latestHistoryBarsAt = result?.latest_history_bars?.latest_stored_at
          ? Date.parse(result.latest_history_bars.latest_stored_at)
          : Number.NaN;
        if (
          state.gapBackfill.awaitingFreshHistory
          && Number.isFinite(latestHistoryBarsAt)
          && latestHistoryBarsAt >= Math.max(0, state.gapBackfill.lastRequestedAt - 1000)
        ) {
          state.gapBackfill.awaitingFreshHistory = false;
          if (!state.buildInFlight && state.snapshot) {
            await handleBuildWithForceRefresh();
            return result;
          }
        }

        if (
          refreshTail
          && state.snapshot
          && !state.buildInFlight
          && (result.stream_state === "live" || result.stream_state === "delayed")
        ) {
          await refreshLiveTail({ silently: true });
        }

        if (
          autoRebuildIfNeeded
          && result.should_refresh_snapshot
          && !state.buildInFlight
          && (result.latest_adapter_sync_lag_seconds ?? Number.MAX_SAFE_INTEGER) <= 120
        ) {
          const now = Date.now();
          const canSyncCache =
            allowImmediateRefresh
            || !state.currentReplayIngestionId
            || state.lastAutoCacheRefreshCompletedAt === 0
            || (now - state.lastAutoCacheRefreshCompletedAt) >= state.autoCacheRefreshIntervalMs;
          if (canSyncCache && now - state.lastAutoRefreshStartedAt >= 5000) {
            state.lastAutoRefreshStartedAt = now;
            renderLiveStatusStrip([
              ...buildLiveStatusChips(result),
              {
                label: allowImmediateRefresh
                  ? "检测到页面快照落后，立即同步缓存中"
                  : "检测到新数据，按分钟节奏同步缓存中",
                variant: "emphasis",
              },
            ]);
            await handleBuildWithForceRefresh();
          }
        }

        return result;
      } catch (error) {
        renderStreamAlertBanner({ stream_state: "offline", latest_adapter_sync_lag_seconds: null, latest_adapter_sync_at: null });
        if (!silently) {
          renderLiveStatusStrip([{ label: `实时状态查询失败：${error.message || String(error)}`, variant: "warn" }]);
        }
        return null;
      } finally {
        state.liveStatusPollInFlight = false;
      }
    }

    function getActiveInstrumentSymbol() {
      return (state.snapshot?.instrument?.symbol || els.instrumentSymbol.value.trim() || "").trim().toUpperCase();
    }

    function getActiveDisplayTimeframe() {
      return (state.snapshot?.display_timeframe || els.displayTimeframe.value || "").trim();
    }

    function isChartPinnedToRight(totalCandles) {
      if (!state.chartView || !Number.isFinite(totalCandles) || totalCandles <= 0) {
        return true;
      }
      return state.chartView.endIndex >= Math.max(0, totalCandles - 3);
    }

    function mergeLiveTailIntoSnapshot(liveTail) {
      if (!state.snapshot || !Array.isArray(state.snapshot.candles) || !Array.isArray(liveTail?.candles) || !liveTail.candles.length) {
        return {
          changed: false,
          candleDataChanged: false,
          liveMetaChanged: false,
          selectedCandleChanged: false,
          shouldFullRender: false,
          tailCandles: [],
        };
      }

      const existingCandles = state.snapshot.candles;
      const previousLastCandle = existingCandles[existingCandles.length - 1] || null;
      const previousLastObservedAt = state.snapshot.raw_features?.live_tail_latest_observed_at || null;
      const previousLastPrice = state.snapshot.raw_features?.live_tail_latest_price ?? null;
      const selectedStartedAt = state.selectedCandleIndex != null
        ? existingCandles[state.selectedCandleIndex]?.started_at ?? null
        : null;
      const wasPinnedToRight = isChartPinnedToRight(existingCandles.length);
      const visibleSpan = state.chartView
        ? (state.chartView.endIndex - state.chartView.startIndex + 1)
        : existingCandles.length;

      const candleMap = new Map(existingCandles.map((candle) => [candle.started_at, candle]));
      const changedStartedAtSet = new Set();
      liveTail.candles.forEach((candle) => {
        const previous = candleMap.get(candle.started_at);
        const nextCandle = previous ? { ...previous, ...candle } : candle;
        candleMap.set(candle.started_at, nextCandle);
        if (JSON.stringify(previous) !== JSON.stringify(nextCandle)) {
          changedStartedAtSet.add(candle.started_at);
        }
      });

      const mergedCandles = Array.from(candleMap.values()).sort(
        (left, right) => new Date(left.started_at) - new Date(right.started_at),
      );

      const nextLastCandle = mergedCandles[mergedCandles.length - 1] || null;
      const rawFeatures = {
        ...(state.snapshot.raw_features || {}),
        live_tail_latest_price: liveTail.latest_price ?? null,
        live_tail_latest_observed_at: liveTail.latest_observed_at ?? null,
        live_tail_best_bid: liveTail.best_bid ?? null,
        live_tail_best_ask: liveTail.best_ask ?? null,
        live_tail_source_message_count: liveTail.source_message_count ?? 0,
      };

      const candleDataChanged = (
        mergedCandles.length !== existingCandles.length
        || changedStartedAtSet.size > 0
      );
      const liveMetaChanged = (
        previousLastObservedAt !== rawFeatures.live_tail_latest_observed_at
        || previousLastPrice !== rawFeatures.live_tail_latest_price
      );
      const changed = candleDataChanged || liveMetaChanged;

      state.snapshot.candles = mergedCandles;
      state.snapshot.window_start = mergedCandles[0]?.started_at || state.snapshot.window_start;
      state.snapshot.window_end = nextLastCandle?.ended_at || state.snapshot.window_end;
      state.snapshot.raw_features = rawFeatures;
      state.liveTail = liveTail;
      if (liveTail.latest_price != null) {
        animateLivePriceTo(Number(liveTail.latest_price));
      }

      if (selectedStartedAt) {
        const nextSelectedIndex = mergedCandles.findIndex((candle) => candle.started_at === selectedStartedAt);
        state.selectedCandleIndex = nextSelectedIndex >= 0 ? nextSelectedIndex : state.selectedCandleIndex;
      }

      if (state.chartView) {
        if (wasPinnedToRight) {
          const endIndex = mergedCandles.length - 1;
          const startIndex = Math.max(0, endIndex - Math.max(visibleSpan, 1) + 1);
          state.chartView = clampChartView(mergedCandles.length, startIndex, endIndex, state.chartView);
        } else {
          state.chartView = clampChartView(
            mergedCandles.length,
            state.chartView.startIndex,
            state.chartView.endIndex,
            state.chartView,
          );
        }
      }

      const changedIndices = Array.from(changedStartedAtSet)
        .map((startedAt) => mergedCandles.findIndex((candle) => candle.started_at === startedAt))
        .filter((index) => index >= 0)
        .sort((left, right) => left - right);
      const tailCompatible = changedIndices.length > 0
        && changedIndices[changedIndices.length - 1] === mergedCandles.length - 1
        && changedIndices.every((index, offset) => index === changedIndices[0] + offset);

      return {
        changed,
        candleDataChanged,
        liveMetaChanged,
        selectedCandleChanged: Boolean(selectedStartedAt && changedStartedAtSet.has(selectedStartedAt)),
        shouldFullRender: candleDataChanged && !tailCompatible,
        tailCandles: tailCompatible ? changedIndices.map((index) => mergedCandles[index]) : [],
      };
    }

    async function refreshLiveTail(options = {}) {
      const silently = Boolean(options.silently);
      if (!state.snapshot || state.buildInFlight || state.liveTailPollInFlight) {
        return state.liveTail;
      }

      const instrumentSymbol = getActiveInstrumentSymbol();
      const displayTimeframe = getActiveDisplayTimeframe();
      if (!instrumentSymbol || !displayTimeframe) {
        return state.liveTail;
      }

      try {
        state.liveTailPollInFlight = true;
        state.lastLiveTailPollAt = Date.now();
        // Request enough bars so timeframe switching is visually obvious.
        // (4 bars can look identical between 1m/5m when you are zoomed out)
        const params = new URLSearchParams({
          instrument_symbol: instrumentSymbol,
          display_timeframe: displayTimeframe,
          lookback_bars: "50",
        });
        const chartInstanceId = els.chartInstanceId.value.trim();
        if (chartInstanceId) {
          params.set("chart_instance_id", chartInstanceId);
        }
        const result = await fetchJson(`/api/v1/workbench/live-tail?${params.toString()}`);
        const mergeResult = mergeLiveTailIntoSnapshot(result);
        if (mergeResult.candleDataChanged) {
          await maybeRequestSnapshotGapBackfill(state.snapshot);
        }
        if (!mergeResult.changed) {
          return result;
        }

        if (mergeResult.candleDataChanged) {
          const incrementallySynced = !mergeResult.shouldFullRender && syncTailCandlesToChart(state.snapshot, mergeResult.tailCandles);
          if (!incrementallySynced) {
            renderChart();
          }
        } else if (mergeResult.liveMetaChanged) {
          updateLivePriceLine();
          renderChartViewportMeta(state.snapshot, state.snapshot?.candles?.length || 0);
        }

        if (mergeResult.selectedCandleChanged) {
          renderSelectedCandle();
          renderFootprintLadder();
        }
        return result;
      } catch (error) {
        if (!silently) {
          renderStatusStrip([{ label: `实时尾巴刷新失败：${error.message || String(error)}`, variant: "warn" }]);
        }
        return null;
      } finally {
        state.liveTailPollInFlight = false;
      }
    }

    function collectLiveTailBubbles(snapshot, liveTail, visibleStartTime, visibleEndTime) {
      if (!liveTail) {
        return [];
      }
      const tickSize = Number(snapshot?.instrument?.tick_size || 0.25);
      const latestObservedAt = liveTail.latest_observed_at ? new Date(liveTail.latest_observed_at).getTime() : null;
      const bubbles = [];
      const maxRealtimeSize = Math.max(
        1,
        ...((liveTail.significant_liquidity || []).map((item) => Number(item.current_size || 0))),
        ...((liveTail.same_price_replenishment || []).map((item) => Number(item.current_size || 0))),
      );
      const inWindow = (value) => {
        if (!value) {
          return latestObservedAt != null && latestObservedAt >= visibleStartTime && latestObservedAt <= visibleEndTime;
        }
        const timestamp = new Date(value).getTime();
        return timestamp >= visibleStartTime && timestamp <= visibleEndTime;
      };

      (liveTail.significant_liquidity || []).forEach((item) => {
        if (!inWindow(item.last_observed_at || liveTail.latest_observed_at)) {
          return;
        }
        bubbles.push({
          renderKind: "diamond",
          startedAt: item.last_observed_at || liveTail.latest_observed_at,
          side: item.side,
          price: Number(item.price),
          barVolume: Number(item.current_size || 0),
          volumeRatio: Number(item.current_size || 0) / maxRealtimeSize,
          label: String(item.current_size || 0),
          candleLow: Number(item.price) - tickSize,
          candleHigh: Number(item.price) + tickSize,
          metaText: `挂单 ${item.side === "buy" ? "买" : "卖"} / heat ${Number(item.heat_score || 0).toFixed(2)}`,
        });
      });

      (liveTail.same_price_replenishment || []).forEach((item) => {
        if (!inWindow(liveTail.latest_observed_at)) {
          return;
        }
        bubbles.push({
          renderKind: "circle",
          startedAt: liveTail.latest_observed_at,
          side: item.side,
          price: Number(item.price),
          barVolume: Number(item.current_size || 0),
          volumeRatio: Number(item.current_size || 0) / maxRealtimeSize,
          label: String(item.replenishment_count || 0),
          candleLow: Number(item.price) - tickSize,
          candleHigh: Number(item.price) + tickSize,
          metaText: `补单 ${item.replenishment_count || 0} / 触碰 ${item.touch_count || 0}`,
        });
      });

      if (liveTail.active_initiative_drive && inWindow(liveTail.latest_observed_at)) {
        const drive = liveTail.active_initiative_drive;
        const price = drive.side === "buy" ? Number(drive.price_high) : Number(drive.price_low);
        bubbles.push({
          renderKind: "circle",
          startedAt: liveTail.latest_observed_at,
          side: drive.side,
          price,
          barVolume: Number(drive.aggressive_volume || 0),
          volumeRatio: clampNumber(Number(drive.price_travel_ticks || 0) / 40, 0.35, 1.4),
          label: String(drive.price_travel_ticks || 0),
          candleLow: Number(drive.price_low),
          candleHigh: Number(drive.price_high),
          metaText: `主动 ${drive.side === "buy" ? "买" : "卖"} / Δ ${drive.net_delta || 0}`,
        });
      }

      if (liveTail.active_post_harvest_response && inWindow(liveTail.latest_observed_at)) {
        const response = liveTail.active_post_harvest_response;
        const price = (Number(response.harvested_price_low) + Number(response.harvested_price_high)) / 2;
        bubbles.push({
          renderKind: "diamond",
          startedAt: liveTail.latest_observed_at,
          side: response.harvest_side,
          price,
          barVolume: Number(response.reversal_ticks || response.pullback_ticks || 0),
          volumeRatio: clampNumber(Number(response.reversal_ticks || response.pullback_ticks || 0) / 20, 0.3, 1),
          label: String(response.pullback_ticks || 0),
          candleLow: Number(response.harvested_price_low),
          candleHigh: Number(response.harvested_price_high),
          metaText: `收割后反应 / 回撤 ${response.pullback_ticks || 0}`,
        });
      }

      return bubbles;
    }

    async function loadFootprintBarDetail(barStartedAt) {
      if (!state.currentReplayIngestionId || !barStartedAt) {
        state.selectedFootprintBar = null;
        return;
      }
      try {
        const result = await fetchJson(
          `/api/v1/workbench/footprint-bar?replay_ingestion_id=${encodeURIComponent(state.currentReplayIngestionId)}&bar_started_at=${encodeURIComponent(barStartedAt)}`,
        );
        state.selectedFootprintBar = result;
      } catch (error) {
        state.selectedFootprintBar = {
          error: error.message || String(error),
        };
      }
    }

    function syncEntryDefaultsFromSnapshot() {
      if (!state.snapshot) {
        return;
      }
      if (!els.entryExecutedAt.value) {
        els.entryExecutedAt.value = toUtcInputValue(state.snapshot.window_end);
      }
      if (!els.entryPrice.value && state.snapshot.candles?.length) {
        els.entryPrice.value = state.snapshot.candles[state.snapshot.candles.length - 1].close.toFixed(2);
      }
    }

    function renderBuildSummary() {
      const result = state.buildResponse;
      if (!result) {
        els.buildSummary.className = "empty-note";
        els.buildSummary.textContent = "还没有构建结果。";
        return;
      }

      const summaryParts = [
        `<div class="info-card"><h4>构建动作</h4><p class="mono">${escapeHtml(translateAction(result.action))}</p></div>`,
        `<div class="info-card"><h4>原因</h4><p>${escapeHtml(result.reason)}</p></div>`,
        `<div class="info-card"><h4>本地连续流消息</h4><p class="mono">${escapeHtml(String(result.local_message_count))}</p></div>`,
      ];

      if (result.summary) {
        summaryParts.push(
          `<div class="info-card"><h4>核对状态</h4><p class="mono">${escapeHtml(translateVerificationStatus(result.summary.verification_status))} / ${escapeHtml(String(result.summary.verification_count))}</p></div>`,
          `<div class="info-card"><h4>采集来源</h4><p class="mono">${escapeHtml(translateAcquisitionMode(result.summary.acquisition_mode))}</p></div>`,
          `<div class="info-card"><h4>K 线数量</h4><p class="mono">${escapeHtml(String(result.summary.candle_count))}</p></div>`
        );
      }

      const gapCount = state.snapshot?.raw_features?.candle_gap_count || 0;
      const gapMissingBars = state.snapshot?.raw_features?.candle_gap_missing_bar_count || 0;
      const gaps = Array.isArray(state.snapshot?.raw_features?.candle_gaps) ? state.snapshot.raw_features.candle_gaps : [];
      if (gapCount > 0 || gaps.length) {
        const rows = gaps.slice(0, 6).map((item) => {
          const prevEnd = item.prev_ended_at || item.prevEndedAt || item.prev_started_at || item.prevStartedAt;
          const nextStart = item.next_started_at || item.nextStartedAt;
          const missing = item.missing_bar_count ?? item.missingBarCount ?? "?";
          return `<li class="mono">${escapeHtml(formatShortDateTime(prevEnd))} → ${escapeHtml(formatShortDateTime(nextStart))} · 缺 ${escapeHtml(String(missing))} 根</li>`;
        }).join("");
        summaryParts.push(
          `<div class="info-card"><h4>时间缺口</h4><p class="mono">段数=${escapeHtml(String(gapCount || gaps.length))} 缺失=${escapeHtml(String(gapMissingBars))} 根</p>${rows ? `<ul>${rows}</ul>` : ""}<p style="margin-top:8px;color:rgba(248,113,113,0.92)">提示：缺口通常意味着本地历史/ATAS历史覆盖不足，图表已用“平盘填充”占位，分析时请谨慎。</p></div>`
        );
      }

      const digest = state.snapshot?.raw_features?.history_footprint_digest;
      if (digest) {
        summaryParts.push(
          `<div class="info-card"><h4>历史足迹摘要</h4><p class="mono">bars=${escapeHtml(String(digest.bar_count || 0))} price_levels=${escapeHtml(String(digest.price_level_count || 0))}</p></div>`
        );
      }

      if (result.atas_fetch_request) {
        summaryParts.push(
          `<div class="info-card"><h4>需要向 ATAS 补抓</h4><p class="mono">${escapeHtml(JSON.stringify(result.atas_fetch_request, null, 2))}</p></div>`
        );
      }

      els.buildSummary.className = "meta-grid";
      els.buildSummary.innerHTML = summaryParts.join("");
    }

    function renderFocusRegions() {
      const focusRegions = state.snapshot?.focus_regions || [];
      els.focusRegions.innerHTML = "";
      if (!focusRegions.length) {
        els.focusRegions.innerHTML = `<div class="empty-note">当前回放没有重点区域。</div>`;
        return;
      }
      focusRegions.forEach((region) => {
        const card = document.createElement("div");
        card.className = "info-card";
        card.innerHTML = `
          <h4>${escapeHtml(region.label)}</h4>
          <p class="mono">${escapeHtml(region.price_low.toFixed(2))} - ${escapeHtml(region.price_high.toFixed(2))}</p>
          <p>优先级=${escapeHtml(String(region.priority))}</p>
          ${renderList(region.reason_codes)}
          ${renderList(region.notes)}
        `;
        els.focusRegions.appendChild(card);
      });
    }

    function renderStrategyCandidates() {
      const candidates = state.snapshot?.strategy_candidates || [];
      els.strategyCandidates.innerHTML = "";
      if (!candidates.length) {
        els.strategyCandidates.innerHTML = `<div class="empty-note">当前 replay 没有匹配到策略卡片。</div>`;
        return;
      }
      candidates.forEach((candidate) => {
        const card = document.createElement("div");
        card.className = "info-card";
        card.innerHTML = `
          <h4>${escapeHtml(candidate.title)}</h4>
          <p class="mono">${escapeHtml(candidate.strategy_id)}</p>
          <p class="mono">${escapeHtml(candidate.source_path)}</p>
          ${renderList(candidate.why_relevant)}
        `;
        els.strategyCandidates.appendChild(card);
      });
    }

    function renderOperatorEntries() {
      const entries = state.operatorEntries || [];
      els.operatorEntries.innerHTML = "";
      if (!entries.length) {
        els.operatorEntries.innerHTML = `<div class="empty-note">当前 replay 还没有记录开仓。</div>`;
        return;
      }
      entries.forEach((entry) => {
        const card = document.createElement("div");
        card.className = "info-card";
        card.innerHTML = `
          <h4>${escapeHtml(entry.side === "buy" ? "多头" : "空头")} @ ${escapeHtml(entry.entry_price.toFixed(2))}</h4>
          <p class="mono">${escapeHtml(formatUtcDateTime(entry.executed_at))}</p>
          <p class="mono">数量=${escapeHtml(String(entry.quantity ?? ""))} 止损=${escapeHtml(entry.stop_price != null ? entry.stop_price.toFixed(2) : "n/a")}</p>
          <p>${escapeHtml(entry.thesis || "")}</p>
          ${renderList(entry.context_notes)}
        `;
        els.operatorEntries.appendChild(card);
      });
    }

    function renderManualRegions() {
      const regions = state.manualRegions || [];
      els.manualRegions.innerHTML = "";
      if (!regions.length) {
        els.manualRegions.innerHTML = `<div class="empty-note">当前还没有手工区域。点击“开始框选区域”，在图上拖出一个时间-价格区域后保存。</div>`;
        return;
      }
      regions.forEach((region) => {
        const card = document.createElement("div");
        card.className = "info-card";
        card.innerHTML = `
          <h4>${escapeHtml(region.label)}</h4>
          <p class="mono">${escapeHtml(Number(region.price_low).toFixed(2))} - ${escapeHtml(Number(region.price_high).toFixed(2))}</p>
          <p class="mono">${escapeHtml(formatUtcDateTime(region.started_at))} -> ${escapeHtml(formatUtcDateTime(region.ended_at))}</p>
          <p>${escapeHtml(region.thesis)}</p>
          ${renderList(region.notes)}
          ${renderList(region.tags)}
        `;
        els.manualRegions.appendChild(card);
      });
    }

    function renderSelectedCandle() {
      const snapshot = state.snapshot;
      const candle = snapshot?.candles?.[state.selectedCandleIndex ?? -1];
      if (!candle) {
        els.selectedCandle.className = "empty-note";
        els.selectedCandle.textContent = "点击图上的 K 线，查看该 bar 的 OHLC、bid/ask、delta 和 footprint 细节。";
        return;
      }
      const detail = state.selectedFootprintBar;
      els.selectedCandle.className = "card-list";
      els.selectedCandle.innerHTML = `
        <div class="info-card">
          <h4>${escapeHtml(formatUtcDateTime(candle.started_at))}</h4>
          <p class="mono">O ${escapeHtml(Number(candle.open).toFixed(2))} H ${escapeHtml(Number(candle.high).toFixed(2))} L ${escapeHtml(Number(candle.low).toFixed(2))} C ${escapeHtml(Number(candle.close).toFixed(2))}</p>
          <p class="mono">成交量=${escapeHtml(String(candle.volume ?? "n/a"))} Delta=${escapeHtml(String(candle.delta ?? "n/a"))} Bid=${escapeHtml(String(candle.bid_volume ?? "n/a"))} Ask=${escapeHtml(String(candle.ask_volume ?? "n/a"))}</p>
          ${detail?.price_levels ? `<p class="mono">足迹价位层数=${escapeHtml(String(detail.price_levels.length))}</p>` : ""}
          ${detail?.error ? `<p>${escapeHtml(detail.error)}</p>` : ""}
        </div>
      `;
    }

    function renderFootprintLadder() {
      const detail = state.selectedFootprintBar;
      if (!detail || detail.error) {
        els.footprintLadder.className = "empty-note";
        els.footprintLadder.textContent = detail?.error || "历史 footprint 细节会在选中 K 线后加载。";
        return;
      }
      const levels = detail.price_levels || [];
      if (!levels.length) {
        els.footprintLadder.className = "empty-note";
        els.footprintLadder.textContent = "当前 bar 没有历史 footprint 价位明细。";
        return;
      }
      const rows = levels.slice(0, 120).map((level) => `
        <div class="ladder-row">
          <span class="price">${escapeHtml(Number(level.price).toFixed(2))}</span>
          <span class="bid">${escapeHtml(String(level.bid_volume ?? 0))}</span>
          <span class="ask">${escapeHtml(String(level.ask_volume ?? 0))}</span>
          <span>${escapeHtml(String(level.delta ?? 0))}</span>
        </div>
      `).join("");
      els.footprintLadder.className = "ladder";
      els.footprintLadder.innerHTML = `
        <div class="ladder-header">
          <span>价位</span>
          <span>Bid</span>
          <span>Ask</span>
          <span>Delta</span>
        </div>
        ${rows}
      `;
    }

    function renderAiBriefing() {
      const briefing = state.snapshot?.ai_briefing;
      if (!briefing) {
        els.aiBriefing.className = "empty-note";
        els.aiBriefing.textContent = "当前回放还没有 AI 简报。";
        return;
      }
      els.aiBriefing.className = "card-list";
      els.aiBriefing.innerHTML = `
        <div class="info-card">
          <h4>任务目标</h4>
          <p>${escapeHtml(briefing.objective)}</p>
        </div>
        <div class="info-card">
          <h4>重点问题</h4>
          ${renderList(briefing.focus_questions)}
        </div>
        <div class="info-card">
          <h4>要求输出</h4>
          ${renderList(briefing.required_outputs)}
        </div>
        <div class="info-card">
          <h4>备注</h4>
          ${renderList(briefing.notes)}
        </div>
      `;
    }

    function renderAiReview() {
      const reviewResult = state.aiReview;
      if (!reviewResult) {
        els.aiReview.className = "empty-note";
        els.aiReview.textContent = state.currentReplayIngestionId
          ? "当前 replay 还没有 AI 复盘。点击“AI 分析”生成或复用。"
          : "当前还没有可分析的 replay。先构建回放。";
        return;
      }

      const review = reviewResult.review;
      const keyZonesHtml = review.key_zones?.length
        ? review.key_zones.map((zone) => `
            <div class="info-card">
              <h4>${escapeHtml(zone.label)}</h4>
              <p class="mono">${escapeHtml(zone.zone_low.toFixed(2))} - ${escapeHtml(zone.zone_high.toFixed(2))}</p>
              <p>角色=${escapeHtml(zone.role)} 强度=${escapeHtml(zone.strength_score.toFixed(2))}</p>
              ${renderList(zone.evidence)}
            </div>
          `).join("")
        : `<div class="empty-note">AI 没有返回重点区域。</div>`;
      const invalidationsHtml = review.invalidations?.length
        ? review.invalidations.map((item) => `
            <div class="info-card">
              <h4>${escapeHtml(item.label)}</h4>
              <p class="mono">${escapeHtml(item.price.toFixed(2))}</p>
              <p>${escapeHtml(item.reason)}</p>
            </div>
          `).join("")
        : `<div class="empty-note">AI 没有返回失效位。</div>`;
      const entryReviewsHtml = review.entry_reviews?.length
        ? review.entry_reviews.map((entryReview) => `
            <div class="info-card">
              <h4>${escapeHtml(entryReview.entry_id)} / ${escapeHtml(entryReview.verdict)}</h4>
              <p class="mono">上下文匹配=${escapeHtml(entryReview.context_alignment_score.toFixed(2))}</p>
              <h4>理由</h4>
              ${renderList(entryReview.rationale)}
              <h4>问题</h4>
              ${renderList(entryReview.mistakes)}
              <h4>更好条件</h4>
              ${renderList(entryReview.better_conditions)}
            </div>
          `).join("")
        : `<div class="empty-note">当前 AI 复盘还没有逐条开仓评价。</div>`;

      els.aiReview.className = "card-list";
      els.aiReview.innerHTML = `
        <div class="info-card">
          <h4>总结</h4>
          <p>${escapeHtml(review.narrative_summary)}</p>
        </div>
        <div class="info-card">
          <h4>优先剧本</h4>
          <p class="mono">${escapeHtml(review.script_review.preferred_script)}</p>
          <h4>偏好理由</h4>
          ${renderList(review.script_review.preferred_rationale)}
          <h4>延续条件</h4>
          ${renderList(review.script_review.continuation_case)}
          <h4>反转条件</h4>
          ${renderList(review.script_review.reversal_case)}
        </div>
        <div class="info-card">
          <h4>模型来源</h4>
          <p class="mono">${escapeHtml(reviewResult.provider)} / ${escapeHtml(reviewResult.model)}</p>
          <p class="mono">保存时间=${escapeHtml(formatUtcDateTime(reviewResult.stored_at))}</p>
        </div>
        ${entryReviewsHtml}
        ${keyZonesHtml}
        ${invalidationsHtml}
        <div class="info-card">
          <h4>禁止开仓提示</h4>
          ${renderList(review.no_trade_guidance)}
        </div>
        <div class="info-card">
          <h4>操作员关注点</h4>
          ${renderList(review.operator_focus)}
        </div>
        <div class="info-card">
          <h4>未解决冲突</h4>
          ${renderList(review.unresolved_conflicts)}
        </div>
      `;
    }

    function renderPendingAiAttachments() {
      const attachments = state.pendingAiAttachments || [];
      els.aiChatAttachmentList.innerHTML = "";
      els.embeddedAttachmentBadgeRow.innerHTML = "";
      syncEmbeddedSourceChips();
      scheduleSessionStateSave();
      if (!attachments.length) {
        return;
      }
      attachments.forEach((attachment, index) => {
        const sourceLabel = attachment.source_kind === "chart_screenshot"
          ? "K线图截图"
          : attachment.source_kind === "widget_screenshot"
            ? "外部截图"
            : "图片附件";
        const card = document.createElement("div");
        card.className = "chat-attachment-card";
        card.innerHTML = `
          <button class="chat-attachment-remove" type="button" title="移除图片">×</button>
          <img src="${escapeHtml(attachment.data_url)}" alt="attachment preview">
          <div class="chat-attachment-meta">${escapeHtml(attachment.name || `image_${index + 1}`)}<br>${escapeHtml(attachment.media_type)}<br>${escapeHtml(sourceLabel)}</div>
        `;
        card.querySelector(".chat-attachment-remove").addEventListener("click", () => {
          state.pendingAiAttachments.splice(index, 1);
          renderPendingAiAttachments();
        });
        els.aiChatAttachmentList.appendChild(card);

        const badge = document.createElement("span");
        badge.className = "attachment-badge";
        badge.textContent = `${sourceLabel} · ${attachment.name || `image_${index + 1}`}`;
        els.embeddedAttachmentBadgeRow.appendChild(badge);
      });
    }

    function renderEmbeddedAiChat() {
      const thread = getActiveThread();
      const messages = thread.messages || [];
      if (window.ReplayChatWindow) {
        window.ReplayChatWindow.renderThread(
          els.embeddedAiChatThread,
          messages,
          "这里会镜像当前线程。你可以直接在图表区提问，不必总看右栏。",
        );
      }
      syncEmbeddedSourceChips();
    }

    function renderAiChat() {
      renderAiThreadTabs();
      const thread = getActiveThread();
      const messages = thread.messages || [];
      if (window.ReplayChatWindow) {
        window.ReplayChatWindow.renderThread(
          els.aiChatThread,
          messages,
          "当前还没有 AI 对话。先构建回放，再点击预设按钮或直接提问。",
        );
      }
      renderPendingAiAttachments();
      renderEmbeddedAiChat();
    }

    function getEventKindCategory(eventKind) {
      const value = String(eventKind || "").toLowerCase();
      if (value.includes("iceberg")) return "iceberg";
      if (value.includes("absorp")) return "absorption";
      if (value.includes("replen")) return "replenishment";
      if (value.includes("large") || value.includes("block") || value.includes("sweep")) return "largeOrders";
      return "events";
    }

    function updateLayerButtons() {
      const mapping = {
        largeOrders: els.layerLargeOrders,
        absorption: els.layerAbsorption,
        iceberg: els.layerIceberg,
        replenishment: els.layerReplenishment,
        events: els.layerEvents,
        aiLevels: els.layerAiLevels,
        manualRegions: els.layerManualRegions,
        entries: els.layerEntries,
      };
      Object.entries(mapping).forEach(([key, button]) => {
        if (!button) return;
        button.classList.toggle("active", Boolean(state.layerVisibility[key]));
      });
    }

    function renderEventTimeline() {
      const events = state.snapshot?.event_annotations || [];
      els.eventTimeline.innerHTML = "";
      if (!events.length) {
        els.eventTimeline.innerHTML = `<div class="empty-note">当前 replay 没有事件标注。</div>`;
        return;
      }
      events.forEach((event) => {
        const card = document.createElement("div");
        card.className = "info-card";
        const priceText = event.price != null
          ? event.price.toFixed(2)
          : `${Number(event.price_low ?? 0).toFixed(2)} - ${Number(event.price_high ?? 0).toFixed(2)}`;
        card.innerHTML = `
          <h4>${escapeHtml(event.event_kind)}</h4>
          <p class="mono">${escapeHtml(formatUtcDateTime(event.observed_at))}</p>
          <p class="mono">${escapeHtml(priceText)}</p>
          ${renderList(event.notes)}
        `;
        els.eventTimeline.appendChild(card);
      });
    }

    function renderSnapshot() {
      renderBuildSummary();
      renderSelectedCandle();
      renderFootprintLadder();
      renderManualRegions();
      renderFocusRegions();
      renderStrategyCandidates();
      renderOperatorEntries();
      renderAiReview();
      renderAiChat();
      renderAiBriefing();
      renderEventTimeline();
      renderChart();
    }

    function clampChartView(totalCount, startIndex, endIndex, baseView = null) {
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

    function ensureChartView(snapshot) {
      const totalCount = snapshot?.candles?.length || 0;
      if (!totalCount) {
        state.chartView = null;
        return null;
      }
      if (!state.chartView) {
        const endIndex = totalCount - 1;
        const shouldShrinkInitial = (
          snapshot?.display_timeframe === "1m"
          && totalCount > CHART_INITIAL_SPAN_BARS + 50
        );
        const startIndex = shouldShrinkInitial
          ? Math.max(0, endIndex - CHART_INITIAL_SPAN_BARS + 1)
          : 0;
        state.chartView = { startIndex, endIndex };
      }
      state.chartView = clampChartView(totalCount, state.chartView.startIndex, state.chartView.endIndex, state.chartView);
      const visibleCandles = snapshot.candles.slice(state.chartView.startIndex, state.chartView.endIndex + 1);
      const envelope = derivePriceEnvelope(
        visibleCandles,
        snapshot.event_annotations || [],
        snapshot.focus_regions || [],
        state.manualRegions || [],
        state.operatorEntries || [],
      );
      if (state.chartView.yMin == null || state.chartView.yMax == null || state.chartView.yMax <= state.chartView.yMin) {
        state.chartView.yMin = envelope.min;
        state.chartView.yMax = envelope.max;
      }
      return state.chartView;
    }

    function formatAxisTime(value) {
      const date = new Date(value);
      const month = pad2(date.getUTCMonth() + 1);
      const day = pad2(date.getUTCDate());
      const hour = pad2(date.getUTCHours());
      const minute = pad2(date.getUTCMinutes());
      return `${month}/${day} ${hour}:${minute} UTC`;
    }

    function clampNumber(value, minimum, maximum) {
      return Math.max(minimum, Math.min(maximum, value));
    }

    function derivePriceEnvelope(visibleCandles, events = [], focusRegions = [], manualRegions = [], operatorEntries = [], bubbleMarks = []) {
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

    function computeEmaSeries(candles, period) {
      const alpha = 2 / (period + 1);
      let ema = null;
      return candles.map((bar) => {
        const close = Number(bar.close);
        ema = ema == null ? close : (close * alpha) + (ema * (1 - alpha));
        return ema;
      });
    }

    function aggregateCandlesForRendering(rawCandles, baseStartIndex, maxBars) {
      const total = rawCandles.length;
      if (total <= maxBars) {
        return { candles: rawCandles, rawCount: total, aggregated: false };
      }
      const bucketSize = Math.ceil(total / maxBars);
      const aggregated = [];
      for (let i = 0; i < total; i += bucketSize) {
        const bucket = rawCandles.slice(i, i + bucketSize);
        if (!bucket.length) {
          continue;
        }
        const first = bucket[0];
        const last = bucket[bucket.length - 1];
        const highs = bucket.map((b) => Number(b.high));
        const lows = bucket.map((b) => Number(b.low));
        const volumes = bucket.map((b) => Number(b.volume || 0));
        const deltas = bucket.map((b) => Number(b.delta || 0));
        const bidVolumes = bucket.map((b) => Number(b.bid_volume || 0));
        const askVolumes = bucket.map((b) => Number(b.ask_volume || 0));
        aggregated.push({
          ...first,
          started_at: first.started_at,
          ended_at: last.ended_at || last.endedAt || last.started_at,
          open: Number(first.open),
          close: Number(last.close),
          high: Math.max(...highs),
          low: Math.min(...lows),
          volume: volumes.reduce((a, b) => a + b, 0),
          delta: deltas.reduce((a, b) => a + b, 0),
          bid_volume: bidVolumes.reduce((a, b) => a + b, 0),
          ask_volume: askVolumes.reduce((a, b) => a + b, 0),
          __rangeStart: baseStartIndex + i,
          __rangeEnd: baseStartIndex + i + bucket.length - 1,
        });
      }
      return { candles: aggregated, rawCount: total, aggregated: true };
    }

    function collectFootprintBubbles(snapshot, visibleStartTime, visibleEndTime) {
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

    function isoToUtcSeconds(value) {
      if (!value) {
        return null;
      }
      const ms = Date.parse(value);
      if (Number.isNaN(ms)) {
        return null;
      }
      return Math.floor(ms / 1000);
    }

    function ensureLwcChart() {
      if (state.lwc.chart) {
        return state.lwc.chart;
      }

      // 确保容器可见
      els.chartStack.style.display = "flex";
      els.chartContainer.style.display = "block";
      els.volumeChartContainer.style.display = "block";

      const chart = LightweightCharts.createChart(els.chartContainer, {
        autoSize: true,
        localization: {
          timeFormatter: (businessDayOrTimestamp) => {
            const d = new Date(businessDayOrTimestamp * 1000);
            return `${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
          },
        },
        layout: {
          background: { type: "solid", color: "#131722" },
          textColor: "#d6deeb",
          fontFamily: '"Segoe UI", "Microsoft YaHei UI", sans-serif',
        },
        grid: {
          vertLines: { color: "rgba(138,148,166,0.09)" },
          horzLines: { color: "rgba(138,148,166,0.14)" },
        },
        rightPriceScale: {
          borderColor: "rgba(255,255,255,0.14)",
        },
        timeScale: {
          borderColor: "rgba(255,255,255,0.14)",
          timeVisible: true,
          secondsVisible: false,
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false,
        },
        handleScale: {
          mouseWheel: true,
          pinch: true,
          axisPressedMouseMove: true,
        },
      });

      const volumeChart = LightweightCharts.createChart(els.volumeChartContainer, {
        autoSize: true,
        localization: {
          timeFormatter: (businessDayOrTimestamp) => {
            const d = new Date(businessDayOrTimestamp * 1000);
            return `${String(d.getUTCMonth() + 1).padStart(2, "0")}/${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
          },
        },
        layout: {
          background: { type: "solid", color: "#10151f" },
          textColor: "#8d98ab",
          fontFamily: '"Segoe UI", "Microsoft YaHei UI", sans-serif',
        },
        grid: {
          vertLines: { color: "rgba(138,148,166,0.05)" },
          horzLines: { color: "rgba(138,148,166,0.08)" },
        },
        rightPriceScale: {
          borderColor: "rgba(255,255,255,0.12)",
          scaleMargins: { top: 0.08, bottom: 0.0 },
        },
        timeScale: {
          borderColor: "rgba(255,255,255,0.14)",
          timeVisible: true,
          secondsVisible: false,
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false,
        },
        handleScale: {
          mouseWheel: true,
          pinch: true,
          axisPressedMouseMove: false,
        },
      });

      const candleSeries = chart.addCandlestickSeries({
        upColor: "#22ab94",
        downColor: "#f23645",
        wickUpColor: "#22ab94",
        wickDownColor: "#f23645",
        borderVisible: false,
      });

      const volumeSeries = volumeChart.addHistogramSeries({
        priceFormat: { type: "volume" },
        color: "rgba(34,171,148,0.62)",
      });

      const emaSeries = chart.addLineSeries({
        color: "#3b82f6",
        lineWidth: 2,
      });

      const syncLogicalRange = (targetChart, logicalRange) => {
        if (!targetChart || !logicalRange || state.lwc.syncingVisibleRange) {
          return;
        }
        state.lwc.syncingVisibleRange = true;
        try {
          targetChart.timeScale().setVisibleLogicalRange(logicalRange);
        } finally {
          state.lwc.syncingVisibleRange = false;
        }
      };

      chart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
        syncLogicalRange(volumeChart, logicalRange);
        scheduleSessionStateSave(180);
      });
      volumeChart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
        syncLogicalRange(chart, logicalRange);
        scheduleSessionStateSave(180);
      });

      state.lwc.chart = chart;
      state.lwc.volumeChart = volumeChart;
      state.lwc.candleSeries = candleSeries;
      state.lwc.volumeSeries = volumeSeries;
      state.lwc.emaSeries = emaSeries;

      chart.subscribeClick((param) => {
        if (state.chartInteraction.regionMode) {
          return;
        }
        if (!param || param.time == null) {
          return;
        }
        const index = state.lwc.timeToIndex.get(Number(param.time));
        if (index == null) {
          return;
        }
        // async function，但这里不 await，避免阻塞图表线程
        selectCandle(index);
      });

      state.lwc.initialized = true;
      return chart;
    }

    function clearPriceLines(lines) {
      if (!state.lwc.candleSeries) {
        return;
      }
      (lines || []).forEach((line) => {
        try {
          state.lwc.candleSeries.removePriceLine(line);
        } catch (e) {}
      });
    }

    function syncRegionPriceLines(snapshot) {
      if (!snapshot || !state.lwc.candleSeries) {
        return;
      }

      clearPriceLines(state.lwc.focusPriceLines);
      clearPriceLines(state.lwc.manualPriceLines);
      state.lwc.focusPriceLines = [];
      state.lwc.manualPriceLines = [];

      if (state.layerVisibility.aiLevels) {
        (snapshot.focus_regions || []).slice(0, 6).forEach((region) => {
        state.lwc.focusPriceLines.push(state.lwc.candleSeries.createPriceLine({
          price: Number(region.price_low),
          color: "rgba(59,130,246,0.55)",
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: false,
          title: "",
        }));
        state.lwc.focusPriceLines.push(state.lwc.candleSeries.createPriceLine({
          price: Number(region.price_high),
          color: "rgba(59,130,246,0.55)",
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: false,
          title: "",
        }));
        });
      }

      if (state.layerVisibility.manualRegions) (state.manualRegions || []).slice(0, 6).forEach((region) => {
        state.lwc.manualPriceLines.push(state.lwc.candleSeries.createPriceLine({
          price: Number(region.price_low),
          color: "rgba(245,158,11,0.62)",
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Solid,
          axisLabelVisible: true,
          title: `${(region.label || "").slice(0, 10)} L`,
        }));
        state.lwc.manualPriceLines.push(state.lwc.candleSeries.createPriceLine({
          price: Number(region.price_high),
          color: "rgba(245,158,11,0.62)",
          lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Solid,
          axisLabelVisible: true,
          title: `${(region.label || "").slice(0, 10)} H`,
        }));
      });
    }

    function updateLivePriceLine() {
      if (!state.lwc.candleSeries) {
        return;
      }
      const raw = state.snapshot?.raw_features?.live_tail_latest_price ?? state.liveTail?.latest_price ?? null;
      const base = Number.isFinite(Number(raw)) ? Number(raw) : null;
      const displayed = Number.isFinite(Number(state.liveRenderedPrice)) ? Number(state.liveRenderedPrice) : base;

      if (state.lwc.livePriceLine) {
        try {
          state.lwc.candleSeries.removePriceLine(state.lwc.livePriceLine);
        } catch (e) {}
        state.lwc.livePriceLine = null;
      }

      if (displayed == null) {
        return;
      }

      state.lwc.livePriceLine = state.lwc.candleSeries.createPriceLine({
        price: displayed,
        color: "rgba(245,158,11,0.9)",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `实时价 ${displayed.toFixed(2)}`,
      });
    }

    function snapTimeToNearestCandle(targetTime) {
      if (!state.lwc.timeToIndex || state.lwc.timeToIndex.size === 0) {
        return null;
      }
      let nearestDist = Infinity;
      let nearestTime = null;
      for (const t of state.lwc.timeToIndex.keys()) {
        const dist = Math.abs(t - targetTime);
        if (dist < nearestDist) {
          nearestDist = dist;
          nearestTime = t;
        }
      }
      return nearestTime;
    }

    function syncChartMarkers(snapshot) {
      if (!snapshot || !state.lwc.candleSeries) {
        return;
      }

      const markers = [];

      (snapshot.event_annotations || []).forEach((event) => {
        const category = getEventKindCategory(event.event_kind);
        const canShow = state.layerVisibility.events || state.layerVisibility[category];
        if (!canShow) {
          return;
        }
        const t = isoToUtcSeconds(event.observed_at);
        if (t == null) {
          return;
        }
        const snappedTime = snapTimeToNearestCandle(t);
        if (snappedTime == null) {
          return;
        }
        markers.push({
          time: snappedTime,
          position: category === "absorption" || category === "replenishment" ? "belowBar" : "aboveBar",
          color: category === "iceberg" ? "#a855f7" : category === "absorption" ? "#22c55e" : category === "replenishment" ? "#3b82f6" : "#f59e0b",
          shape: category === "iceberg" ? "square" : "circle",
          text: String(event.event_kind || "event").slice(0, 20),
        });
      });

      if (state.layerVisibility.entries) {
        (state.operatorEntries || []).forEach((entry) => {
          const t = isoToUtcSeconds(entry.executed_at);
          if (t == null) {
            return;
          }
          const snappedTime = snapTimeToNearestCandle(t);
          if (snappedTime == null) {
            return;
          }
          markers.push({
            time: snappedTime,
            position: entry.side === "buy" ? "belowBar" : "aboveBar",
            color: "#8b5cf6",
            shape: entry.side === "buy" ? "arrowUp" : "arrowDown",
            text: `${entry.side === "buy" ? "多" : "空"} ${Number(entry.entry_price).toFixed(2)}`,
          });
        });
      }

      markers.sort((a, b) => Number(a.time) - Number(b.time));
      state.lwc.candleSeries.setMarkers(markers);
      updateLayerButtons();
    }

    function buildCandleSeriesPoint(bar) {
      const time = isoToUtcSeconds(bar?.started_at);
      if (time == null) {
        return null;
      }
      return {
        time,
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
      };
    }

    function buildVolumeSeriesPoint(bar) {
      const candlePoint = buildCandleSeriesPoint(bar);
      if (!candlePoint) {
        return null;
      }
      return {
        time: candlePoint.time,
        value: Number(bar.volume || 0),
        color: candlePoint.close >= candlePoint.open ? "rgba(34,171,148,0.58)" : "rgba(242,54,69,0.58)",
      };
    }

    function restoreChartRangeAfterDataChange(chart, previousLogicalRange, previousCandleDataCount, candleDataCount) {
      if (!chart) {
        return;
      }
      if (!previousLogicalRange || !state.lwc.initialRangeApplied) {
        applyInitialTimeRangeIfNeeded(state.snapshot, candleDataCount);
        return;
      }

      const previousLastIndex = Math.max(0, (previousCandleDataCount || candleDataCount) - 1);
      const nextLastIndex = Math.max(0, candleDataCount - 1);
      const span = Math.max(10, previousLogicalRange.to - previousLogicalRange.from);
      const wasPinnedToRight = previousLogicalRange.to >= Math.max(0, previousLastIndex - 2);
      if (!wasPinnedToRight) {
        chart.timeScale().setVisibleLogicalRange({
          from: previousLogicalRange.from,
          to: previousLogicalRange.to,
        });
        return;
      }

      // Preserve the current viewport width and only slide by newly appended bars.
      // Cap right offset so live updates do not leave a huge empty future area.
      const previousRightOffset = Math.max(0, previousLogicalRange.to - previousLastIndex);
      const preservedRightOffset = Math.min(previousRightOffset, 1.25);
      const nextTo = nextLastIndex + preservedRightOffset;
      chart.timeScale().setVisibleLogicalRange({
        from: nextTo - span,
        to: nextTo,
      });
    }

    function syncTailCandlesToChart(snapshot, tailCandles) {
      if (
        !snapshot
        || !state.lwc.chart
        || !state.lwc.candleSeries
        || !state.lwc.volumeSeries
        || !state.lwc.emaSeries
        || !Array.isArray(tailCandles)
        || !tailCandles.length
      ) {
        return false;
      }

      const previousLogicalRange = state.lwc.chart.timeScale().getVisibleLogicalRange();
      const previousCandleDataCount = state.lwc.lastRenderedCandleCount || snapshot.candles.length;
      const emaRaw = computeEmaSeries(snapshot.candles, 20);
      const candleIndexByStartedAt = new Map(snapshot.candles.map((bar, idx) => [bar.started_at, idx]));

      tailCandles.forEach((bar) => {
        const candlePoint = buildCandleSeriesPoint(bar);
        const volumePoint = buildVolumeSeriesPoint(bar);
        const barIndex = candleIndexByStartedAt.get(bar.started_at);
        if (!candlePoint || !volumePoint || barIndex == null) {
          return;
        }
        state.lwc.candleSeries.update(candlePoint);
        state.lwc.volumeSeries.update(volumePoint);
        state.lwc.emaSeries.update({
          time: candlePoint.time,
          value: Number(emaRaw[barIndex]),
        });
        state.lwc.timeToIndex.set(candlePoint.time, barIndex);
      });

      updateLivePriceLine();
      renderChartViewportMeta(snapshot, snapshot.candles.length);
      restoreChartRangeAfterDataChange(state.lwc.chart, previousLogicalRange, previousCandleDataCount, snapshot.candles.length);
      state.lwc.lastRenderedCandleCount = snapshot.candles.length;
      return true;
    }

    function renderChartViewportMeta(snapshot, candleCount) {
      const symbol = snapshot?.instrument?.symbol || els.instrumentSymbol.value.trim() || "";
      const timeframe = snapshot?.display_timeframe || els.displayTimeframe.value;
      const liveObservedAt = snapshot?.raw_features?.live_tail_latest_observed_at || state.liveTail?.latest_observed_at || null;
      const liveObservedText = liveObservedAt ? `ATAS时间 ${formatAxisTime(liveObservedAt)}` : "ATAS时间等待中";
      const liveRaw = snapshot?.raw_features?.live_tail_latest_price ?? state.liveTail?.latest_price ?? null;
      const live = Number.isFinite(Number(state.liveRenderedPrice))
        ? Number(state.liveRenderedPrice)
        : (Number.isFinite(Number(liveRaw)) ? Number(liveRaw) : null);
      const liveText = live != null ? `实时价 ${live.toFixed(2)}` : "实时价等待中";
      els.chartViewportMeta.textContent = `${symbol} / ${timeframe} / bars=${candleCount} / ${formatAxisTime(snapshot.window_start)} -> ${formatAxisTime(snapshot.window_end)} / ${liveText} / ${liveObservedText} / 鼠标滚轮缩放 / 拖拽平移 / 在价格轴拖动缩放价格`;
    }

    function applyInitialTimeRangeIfNeeded(snapshot, candleDataCount) {
      if (!state.lwc.chart || state.lwc.initialRangeApplied) {
        return;
      }
      const chart = state.lwc.chart;
      const is1m = (snapshot?.display_timeframe || "") === "1m";
      if (is1m && candleDataCount > CHART_INITIAL_SPAN_BARS + 50) {
        const to = candleDataCount - 1;
        const from = Math.max(0, to - CHART_INITIAL_SPAN_BARS + 1);
        chart.timeScale().setVisibleLogicalRange({ from, to });
      } else {
        chart.timeScale().fitContent();
      }
      state.lwc.initialRangeApplied = true;
    }

    function renderChart() {
      const snapshot = state.snapshot;
      if (!snapshot || !snapshot.candles || !snapshot.candles.length) {
        els.chartPlaceholder.style.display = "flex";
        els.chartStack.style.display = "none";
        els.chartViewportMeta.textContent = "视图未初始化";
        return;
      }

      els.chartPlaceholder.style.display = "none";
      els.chartStack.style.display = "flex";
      els.chartFrame.classList.toggle("region-mode", state.chartInteraction.regionMode);

      const chart = ensureLwcChart();
      const prevLogicalRange = chart.timeScale().getVisibleLogicalRange();
      const previousCandleDataCount = state.lwc.lastRenderedCandleCount || snapshot.candles.length;

      const candleData = [];
      const volumeData = [];
      const emaRaw = computeEmaSeries(snapshot.candles, 20);
      const emaData = [];
      state.lwc.timeToIndex = new Map();

      snapshot.candles.forEach((bar, idx) => {
        const t = isoToUtcSeconds(bar.started_at);
        if (t == null) {
          return;
        }
        const open = Number(bar.open);
        const high = Number(bar.high);
        const low = Number(bar.low);
        const close = Number(bar.close);
        candleData.push({ time: t, open, high, low, close });
        emaData.push({ time: t, value: Number(emaRaw[idx]) });
        volumeData.push({
          time: t,
          value: Number(bar.volume || 0),
          color: close >= open ? "rgba(34,171,148,0.58)" : "rgba(242,54,69,0.58)",
        });
        state.lwc.timeToIndex.set(t, idx);
      });

      state.lwc.candleSeries.setData(candleData);
      state.lwc.volumeSeries.setData(volumeData);
      state.lwc.emaSeries.setData(emaData);

      syncChartMarkers(snapshot);
      syncRegionPriceLines(snapshot);
      updateLivePriceLine();
      renderChartViewportMeta(snapshot, candleData.length);

      const restoredFromSession = restoreChartViewportFromSession(snapshot);
      if (!restoredFromSession) {
        applyInitialTimeRangeIfNeeded(snapshot, candleData.length);
      }

      // 尽可能保留用户当前视图（若用户没滚走则保持贴右）
      if (!restoredFromSession && prevLogicalRange && state.lwc.initialRangeApplied) {
        restoreChartRangeAfterDataChange(chart, prevLogicalRange, previousCandleDataCount, candleData.length);
      }
      state.lwc.lastRenderedCandleCount = candleData.length;
    }

    function visibleSpan() {
      if (!state.lwc.chart) {
        return 0;
      }
      const range = state.lwc.chart.timeScale().getVisibleLogicalRange();
      if (!range) {
        return 0;
      }
      return Math.max(0, Math.round(range.to - range.from));
    }

    function zoomChart(factor) {
      if (!state.lwc.chart) {
        return;
      }
      const ts = state.lwc.chart.timeScale();
      const range = ts.getVisibleLogicalRange();
      if (!range) {
        ts.fitContent();
        return;
      }
      const span = Math.max(20, range.to - range.from);
      const nextSpan = Math.max(20, span * factor);
      const center = (range.from + range.to) / 2;
      ts.setVisibleLogicalRange({ from: center - nextSpan / 2, to: center + nextSpan / 2 });
    }

    function zoomPriceAxis(factor) {
      // Lightweight Charts 的价格缩放更推荐：直接在价格轴上拖动（axisPressedMouseMove）
      // 这里按钮仅给提示，避免误导。
      renderStatusStrip([{ label: "提示：请在右侧价格轴上拖动缩放价格（或用触控板捏合）", variant: "emphasis" }]);
    }

    function resetChartView() {
      if (!state.lwc.chart || !state.snapshot?.candles?.length) {
        return;
      }
      // 重新应用首屏范围策略
      state.lwc.initialRangeApplied = false;
      renderChart();
    }


    async function selectCandle(globalIndex) {
      const snapshot = state.snapshot;
      const candle = snapshot?.candles?.[globalIndex];
      if (!candle) {
        return;
      }
      state.selectedCandleIndex = globalIndex;
      state.selectedFootprintBar = null;
      renderSelectedCandle();
      renderFootprintLadder();
      await loadFootprintBarDetail(candle.started_at);
      renderSelectedCandle();
      renderFootprintLadder();
      renderChart();
    }

    function regionPointerToModel(event) {
      if (!state.lwc.chart || !state.lwc.candleSeries) {
        return null;
      }
      const rect = els.chartContainer.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const time = state.lwc.chart.timeScale().coordinateToTime(x);
      const price = state.lwc.candleSeries.coordinateToPrice(y);
      if (time == null || price == null) {
        return null;
      }
      return {
        timeSec: Number(time),
        price: Number(price),
      };
    }

    function beginRegionDraft(event) {
      const model = regionPointerToModel(event);
      if (!model) {
        return;
      }
      state.chartInteraction.regionDragActive = true;
      state.chartInteraction.regionDragStart = model;
      state.chartInteraction.draftRegion = {
        started_at: new Date(model.timeSec * 1000).toISOString(),
        ended_at: new Date(model.timeSec * 1000).toISOString(),
        price_low: model.price,
        price_high: model.price,
      };
      renderStatusStrip([{ label: "开始框选区域：拖动鼠标，然后松开", variant: "emphasis" }]);
    }

    function updateRegionDraft(event) {
      if (!state.chartInteraction.regionDragActive) {
        return;
      }
      const model = regionPointerToModel(event);
      const draft = state.chartInteraction.draftRegion;
      const start = state.chartInteraction.regionDragStart;
      if (!model || !draft || !start) {
        return;
      }
      const startTimeMs = start.timeSec * 1000;
      const endTimeMs = model.timeSec * 1000;
      draft.started_at = new Date(Math.min(startTimeMs, endTimeMs)).toISOString();
      draft.ended_at = new Date(Math.max(startTimeMs, endTimeMs)).toISOString();
      draft.price_low = Math.min(start.price, model.price);
      draft.price_high = Math.max(start.price, model.price);
    }

    async function saveDraftRegion() {
      const draft = state.chartInteraction.draftRegion;
      if (!draft || !state.currentReplayIngestionId) {
        throw new Error("当前没有可保存的框选区域。");
      }
      const result = await fetchJson("/api/v1/workbench/manual-regions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          replay_ingestion_id: state.currentReplayIngestionId,
          label: els.regionLabel.value.trim() || "手工区域",
          thesis: els.regionThesis.value.trim() || "交易员手工标注区域",
          price_low: draft.price_low,
          price_high: draft.price_high,
          started_at: draft.started_at,
          ended_at: draft.ended_at,
          side_bias: els.regionSideBias.value || null,
          notes: (els.regionNotes.value || "").split("\n").map((item) => item.trim()).filter(Boolean),
          tags: (els.regionTags.value || "").split(",").map((item) => item.trim()).filter(Boolean),
        }),
      });
      state.manualRegions.push(result.region);
      state.manualRegions.sort((left, right) => new Date(left.started_at) - new Date(right.started_at));
      state.chartInteraction.draftRegion = null;
      state.chartInteraction.regionMode = false;
      renderStatusStrip([{ label: "手工区域已保存", variant: "good" }]);
      renderSnapshot();
    }

    async function handleBuild() {
      if (state.buildInFlight) {
        return;
      }
      try {
        state.buildInFlight = true;
        saveSessionState();
        state.pendingSessionUiRestore = captureSessionStatePayload();
        setBuildProgress(true, 8, "准备窗口与参数");
        const payload = buildRequestPayload();
        setBuildProgress(true, 28, "请求后端构建历史回放");
        const result = await fetchJson("/api/v1/workbench/replay-builder/build", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        state.buildResponse = result;
        state.snapshot = null;
        state.aiReview = null;
        state.currentReplayIngestionId = result.ingestion_id || null;
        renderStatusStrip(buildStatusChips(result));
        if (result.ingestion_id) {
          setBuildProgress(true, 72, "载入回放快照与足迹摘要");
          await loadSnapshotByIngestionId(result.ingestion_id);
          setBuildProgress(true, 94, "渲染图表与事件层");
        } else {
          await maybeRequestBuildResultBackfill(result);
          renderSnapshot();
        }
        state.lastAutoCacheRefreshCompletedAt = Date.now();
        await refreshLiveStatus({ autoRebuildIfNeeded: false, silently: true });
        setBuildProgress(true, 100, "加载完成");
        window.setTimeout(() => setBuildProgress(false, 0, "正在加载历史数据"), 420);
      } catch (error) {
        setBuildProgress(false, 0, "正在加载历史数据");
        renderError(error);
      } finally {
        state.buildInFlight = false;
      }
    }

    async function handleLookup() {
      try {
        const cacheKey = els.cacheKey.value.trim();
        const result = await fetchJson(`/api/v1/workbench/replay-cache?cache_key=${encodeURIComponent(cacheKey)}`);
        state.buildResponse = {
          action: result.record ? "cache_hit" : "atas_fetch_required",
          cache_key: result.cache_key,
          reason: result.record ? "已找到当前缓存记录。" : "当前没有命中缓存。",
          local_message_count: 0,
          replay_snapshot_id: result.record?.replay_snapshot_id || null,
          ingestion_id: result.record?.ingestion_id || null,
          summary: result.record ? {
            instrument_symbol: result.record.instrument_symbol,
            display_timeframe: result.record.display_timeframe,
            acquisition_mode: result.record.acquisition_mode,
            verification_status: result.record.verification_state.status,
            verification_count: result.record.verification_state.verification_count,
            locked_until_manual_reset: result.record.verification_state.locked_until_manual_reset,
            fetch_only_when_missing: result.record.cache_policy.fetch_only_when_missing,
            max_verifications_per_day: result.record.cache_policy.max_verifications_per_day,
            verification_passes_to_lock: result.record.cache_policy.verification_passes_to_lock,
            candle_count: result.record.candle_count,
            event_annotation_count: result.record.event_annotation_count,
            focus_region_count: result.record.focus_region_count,
            strategy_candidate_count: result.record.strategy_candidate_count,
            has_ai_briefing: result.record.has_ai_briefing,
          } : null,
          cache_record: result.record,
          atas_fetch_request: result.record ? null : { cache_key: result.cache_key, instrument_symbol: els.instrumentSymbol.value.trim() },
        };
        state.aiReview = null;
        state.currentReplayIngestionId = result.record?.ingestion_id || null;
        renderStatusStrip([
          { label: result.record ? "缓存已命中" : "缓存不存在", variant: result.record ? "good" : "warn" },
          { label: result.auto_fetch_allowed ? "允许自动补抓" : "当前禁止自动补抓", variant: result.auto_fetch_allowed ? "emphasis" : "" },
          { label: result.verification_due_now ? "当前需要核对" : "当前无需核对", variant: result.verification_due_now ? "emphasis" : "" },
        ]);
        if (result.record?.ingestion_id) {
          await loadSnapshotByIngestionId(result.record.ingestion_id);
        } else {
          state.snapshot = null;
          renderSnapshot();
        }
        await refreshLiveStatus({ autoRebuildIfNeeded: false, silently: true });
      } catch (error) {
        renderError(error);
      }
    }

    async function handleInvalidate() {
      try {
        const cacheKey = els.cacheKey.value.trim();
        const reason = els.invalidateReason.value.trim();
        const result = await fetchJson("/api/v1/workbench/replay-cache/invalidate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            cache_key: cacheKey,
            invalidation_reason: reason,
          }),
        });
        renderStatusStrip([
          { label: "缓存已作废", variant: "warn" },
          { label: translateVerificationStatus(result.verification_status), variant: "warn" },
        ]);
        state.snapshot = null;
        state.operatorEntries = [];
        state.aiReview = null;
        state.currentReplayIngestionId = null;
        state.buildResponse = {
          action: "atas_fetch_required",
          cache_key: result.cache_key,
          reason: `回放缓存已作废：${result.invalidation_reason}`,
          local_message_count: 0,
          replay_snapshot_id: result.replay_snapshot_id,
          ingestion_id: result.ingestion_id,
          summary: null,
          cache_record: null,
          atas_fetch_request: { cache_key: result.cache_key, manual_reimport_required: true },
        };
        renderSnapshot();
      } catch (error) {
        renderError(error);
      }
    }

    async function handleRecordEntry() {
      try {
        if (!state.currentReplayIngestionId) {
          throw new Error("没有可绑定的 replay。先构建回放。");
        }
        const result = await fetchJson("/api/v1/workbench/operator-entries", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            replay_ingestion_id: state.currentReplayIngestionId,
            executed_at: toUtcString(els.entryExecutedAt.value),
            side: els.entrySide.value,
            entry_price: Number(els.entryPrice.value),
            quantity: els.entryQuantity.value ? Number(els.entryQuantity.value) : null,
            stop_price: els.entryStopPrice.value ? Number(els.entryStopPrice.value) : null,
            timeframe_context: els.entryTimeframe.value || null,
            thesis: els.entryThesis.value.trim() || null,
            context_notes: els.entryThesis.value.trim() ? [els.entryThesis.value.trim()] : [],
            tags: ["manual_entry_review"],
          }),
        });
        state.operatorEntries.push(result.entry);
        state.operatorEntries.sort((left, right) => new Date(left.executed_at) - new Date(right.executed_at));
        state.aiReview = null;
        renderStatusStrip([
          { label: "开仓记录已保存", variant: "good" },
          { label: `${result.entry.side === "buy" ? "多" : "空"} ${Number(result.entry.entry_price).toFixed(2)}`, variant: "emphasis" },
        ]);
        renderSnapshot();
      } catch (error) {
        renderError(error, { preserveSnapshot: true });
      }
    }

    async function handleAiReview() {
      try {
        if (!state.currentReplayIngestionId) {
          throw new Error("没有可分析的 replay ingestion。先构建回放。");
        }
        renderStatusStrip([{ label: "AI 复盘生成中", variant: "emphasis" }]);
        const result = await fetchJson("/api/v1/workbench/replay-ai-review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            replay_ingestion_id: state.currentReplayIngestionId,
            model_override: els.aiModelOverride.value.trim() || null,
            force_refresh: els.forceAiRefresh.checked,
          }),
        });
        state.aiReview = result;
        renderStatusStrip([
          { label: "AI 复盘已完成", variant: "good" },
          { label: result.model, variant: "emphasis" },
        ]);
        renderSnapshot();
      } catch (error) {
        renderAiError(error);
      }
    }

    async function handleBuildWithForceRefresh() {
      const previous = els.forceRebuild.checked;
      els.forceRebuild.checked = true;
      try {
        await handleBuild();
      } finally {
        els.forceRebuild.checked = previous;
      }
    }

    async function handleAiChat(preset, userMessage, threadMeta = null, attachments = []) {
      try {
        const trimmedMessage = String(userMessage || "").trim();
        if (!trimmedMessage) {
          throw new Error("请输入要分析的问题。");
        }
        if (!state.currentReplayIngestionId) {
          throw new Error("没有可分析的 replay ingestion。先构建回放。");
        }
        const threadDescriptor = threadMeta || getPresetThreadMeta(preset);
        const thread = setActiveThread(threadDescriptor.id, threadDescriptor.title);
        const history = thread.messages.map((item) => ({
          role: item.role,
          content: item.content,
        }));
        appendAiChatMessage("user", trimmedMessage, {
          preset,
          attachment_summaries: attachments.map((item) => item.name || item.media_type),
        }, thread.id, thread.title);
        renderStatusStrip([{ label: "AI 对话生成中", variant: "emphasis" }]);
        const result = await fetchJson("/api/v1/workbench/replay-ai-chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            replay_ingestion_id: state.currentReplayIngestionId,
            preset,
            user_message: trimmedMessage,
            history,
            attachments,
            model_override: els.aiModelOverride.value.trim() || null,
            include_live_context: true,
          }),
        });
        thread.turns.push(result);
        appendAiChatMessage("assistant", result.reply_text, {
          preset: result.preset,
          provider: result.provider,
          model: result.model,
          referenced_strategy_ids: result.referenced_strategy_ids || [],
          live_context_summary: result.live_context_summary || [],
          follow_up_suggestions: result.follow_up_suggestions || [],
          attachment_summaries: result.attachment_summaries || [],
        }, thread.id, thread.title);
        renderStatusStrip([
          { label: "AI 对话已完成", variant: "good" },
          { label: result.model, variant: "emphasis" },
        ]);
      } catch (error) {
        const friendlyMessage = normalizeAiServiceErrorMessage(error);
        renderStatusStrip([{ label: "AI 对话失败", variant: "warn" }]);
        const threadDescriptor = threadMeta || getPresetThreadMeta(preset);
        appendAiChatMessage("assistant", friendlyMessage, { preset, provider: "local-error", model: "-" }, threadDescriptor.id, threadDescriptor.title);
      }
    }

    function syncEmbeddedSourceChips() {
      const attachments = state.pendingAiAttachments || [];
      const hasChart = attachments.some((item) => item.source_kind === "chart_screenshot");
      const hasWidget = attachments.some((item) => item.source_kind === "widget_screenshot");
      const hasContext = Boolean(getActiveThread()?.messages?.length);
      els.sourceChipChart.classList.toggle("active", hasChart);
      els.sourceChipWidget.classList.toggle("active", hasWidget);
      els.sourceChipContext.classList.toggle("active", hasContext);
    }

    function normalizeAttachmentName(name, fallbackIndex) {
      const trimmed = String(name || "").trim();
      return trimmed || `pasted_image_${fallbackIndex}.png`;
    }

    async function readFileAsDataUrl(file) {
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error(`读取图片失败: ${file.name || "unknown"}`));
        reader.readAsDataURL(file);
      });
    }

    async function addAiAttachmentsFromFiles(fileList, sourceKind = "widget_screenshot") {
      const files = Array.from(fileList || []).filter((file) => file && String(file.type || "").startsWith("image/"));
      if (!files.length) {
        return;
      }
      for (const file of files.slice(0, 4)) {
        const dataUrl = await readFileAsDataUrl(file);
        state.pendingAiAttachments.push({
          name: normalizeAttachmentName(file.name, state.pendingAiAttachments.length + 1),
          media_type: file.type || "image/png",
          data_url: dataUrl,
          source_kind: sourceKind,
        });
      }
      state.pendingAiAttachments = state.pendingAiAttachments.slice(0, 6);
      renderPendingAiAttachments();
      renderStatusStrip([{ label: `已添加 ${state.pendingAiAttachments.length} 张图片`, variant: "emphasis" }]);
    }

    async function captureChartScreenshotAttachment() {
      const svgNode = els.chartContainer.querySelector("svg");
      if (!svgNode) {
        throw new Error("当前图表还没有可抓取的画面。请先构建回放。");
      }
      const serializer = new XMLSerializer();
      const svgText = serializer.serializeToString(svgNode);
      const encoded = window.btoa(unescape(encodeURIComponent(svgText)));
      state.pendingAiAttachments.push({
        name: `chart_context_${Date.now()}.svg`,
        media_type: "image/svg+xml",
        data_url: `data:image/svg+xml;base64,${encoded}`,
        source_kind: "chart_screenshot",
      });
      state.pendingAiAttachments = state.pendingAiAttachments.slice(0, 6);
      renderPendingAiAttachments();
      renderStatusStrip([{ label: "已抓取当前 K 线图画面", variant: "good" }]);
    }

    async function handleAiChatSend() {
      const message = els.aiChatInput.value.trim();
      const attachments = [...(state.pendingAiAttachments || [])];
      if (!message) {
        if (attachments.length) {
          renderStatusStrip([{ label: "请输入文字问题后再发送图片。", variant: "warn" }]);
        }
        return;
      }
      els.aiChatInput.value = "";
      state.pendingAiAttachments = [];
      renderPendingAiAttachments();
      await handleAiChat("general", message, getActiveThread(), attachments);
    }

    async function handleEmbeddedAiSend() {
      const preset = els.embeddedPromptSelect.value || "general";
      const message = els.embeddedAiInput.value.trim();
      const attachments = [...(state.pendingAiAttachments || [])];
      if (!message) {
        renderStatusStrip([{ label: "请先输入图表区问题。", variant: "warn" }]);
        return;
      }
      els.embeddedAiInput.value = "";
      state.pendingAiAttachments = [];
      renderPendingAiAttachments();
      await handleAiChat(preset, message, getPresetThreadMeta(preset), attachments);
    }

    async function handlePresetAnalysis(preset, message) {
      await handleAiChat(preset, message, getPresetThreadMeta(preset), []);
    }

    function buildManualRegionAnalysisPrompt() {
      const latestRegion = state.manualRegions[state.manualRegions.length - 1];
      if (!latestRegion) {
        throw new Error("还没有已保存的区域。先在图上框选并保存一个区域。");
      }
      return `请重点分析我标注的区域 "${latestRegion.label}"。我的看法是：${latestRegion.thesis}。请结合当前 replay、历史 footprint、事件和上下文，判断这里是否真的是关键支撑/阻力转换点；如果价格回到此区，需要看到哪些反应才能开仓；哪些情况绝对不能开；止损、第一止盈、扩展止盈应如何规划。`;
    }

    function buildSelectedBarAnalysisPrompt() {
      if (state.selectedCandleIndex === null || !state.snapshot?.candles?.[state.selectedCandleIndex]) {
        throw new Error("还没有选中 K 线。先点击图上的一根 K 线。");
      }
      const candle = state.snapshot.candles[state.selectedCandleIndex];
      const footprint = state.selectedFootprintBar;
      const footprintFacts = footprint?.price_levels?.length
        ? `该 bar 有 ${footprint.price_levels.length} 个 footprint 价位，请结合 bid/ask、delta 和价位成交密度判断其含义。`
        : "当前没有完整 footprint 价位细节。";
      return `请分析我当前选中的 K 线。时间=${formatUtcDateTime(candle.started_at)}，O=${Number(candle.open).toFixed(2)} H=${Number(candle.high).toFixed(2)} L=${Number(candle.low).toFixed(2)} C=${Number(candle.close).toFixed(2)}，volume=${candle.volume ?? "n/a"} delta=${candle.delta ?? "n/a"}。${footprintFacts} 请判断这根 bar 在当前结构里代表主动发力、吸收、诱导还是衰竭，并说明下一次价格回到相关区域时的可做与不可做方案。`;
    }

    function injectPromptIntoEmbeddedInput(text) {
      const prefix = String(text || "").trim();
      if (!prefix) {
        return;
      }
      const current = els.embeddedAiInput.value.trim();
      els.embeddedAiInput.value = current ? `${current}\n\n${prefix}` : prefix;
      els.embeddedAiInput.focus();
    }

    function buildStatusChips(result) {
      const chips = [
        { label: translateAction(result.action), variant: result.action === "atas_fetch_required" ? "warn" : "good" },
      ];
      if (result.summary) {
        chips.push({ label: `核对：${translateVerificationStatus(result.summary.verification_status)}`, variant: result.summary.verification_status === "durable" ? "good" : "emphasis" });
        chips.push({ label: `${result.summary.verification_count}/${result.summary.verification_passes_to_lock} 次核对`, variant: "emphasis" });
      }
      if (result.local_message_count) {
        chips.push({ label: `${result.local_message_count} 条本地消息`, variant: "" });
      }
      return chips;
    }

    function renderError(error, options = {}) {
      const preserveSnapshot = Boolean(options.preserveSnapshot);
      state.aiReview = null;
      if (!preserveSnapshot) {
        state.snapshot = null;
        state.currentReplayIngestionId = null;
        state.manualRegions = [];
        state.selectedCandleIndex = null;
        state.selectedFootprintBar = null;
        state.chartView = null;
      }
      state.buildResponse = {
        action: "atas_fetch_required",
        cache_key: els.cacheKey.value.trim(),
        reason: error.message || String(error),
        local_message_count: 0,
        replay_snapshot_id: null,
        ingestion_id: null,
        summary: null,
        cache_record: null,
        atas_fetch_request: null,
      };
      renderStatusStrip([{ label: "请求失败", variant: "warn" }]);
      renderSnapshot();
    }

    function renderAiError(error) {
      state.aiReview = null;
      const friendlyMessage = normalizeAiServiceErrorMessage(error);
      renderStatusStrip([{ label: "AI 复盘失败", variant: "warn" }]);
      els.aiReview.className = "empty-note";
      els.aiReview.textContent = friendlyMessage;
    }

    async function handleSaveRegion() {
      try {
        await saveDraftRegion();
      } catch (error) {
        renderStatusStrip([{ label: "区域保存失败", variant: "warn" }]);
      }
    }

    function renderList(items) {
      if (!items || !items.length) {
        return `<p></p>`;
      }
      return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");
    }

    els.buildButton.addEventListener("click", handleBuildWithForceRefresh);
    if (els.buildButtonInline) els.buildButtonInline.addEventListener("click", handleBuildWithForceRefresh);
    if (els.aiReviewButtonInline) els.aiReviewButtonInline.addEventListener("click", handleAiReview);
    if (els.lookupButtonInline) els.lookupButtonInline.addEventListener("click", handleLookup);
    if (els.recordEntryButtonInline) els.recordEntryButtonInline.addEventListener("click", handleRecordEntry);
    els.preset7d1mButton.addEventListener("click", async () => {
      applyWindowPreset("1m", 7);
      await handleBuildWithForceRefresh();
    });
    els.preset3d5mButton.addEventListener("click", async () => {
      applyWindowPreset("5m", 7);
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
      const thread = setActiveThread(createThreadId(), `会话 ${state.aiThreads.length + 1}`);
      saveAiThreadsToStorage();
      renderStatusStrip([{ label: `已创建 ${thread.title}`, variant: "emphasis" }]);
    });
    els.aiChatSendButton.addEventListener("click", handleAiChatSend);
    els.aiChatAttachButton.addEventListener("click", () => els.aiChatImageInput.click());
    els.aiChatImageInput.addEventListener("change", async (event) => {
      try {
        await addAiAttachmentsFromFiles(event.target.files);
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      } finally {
        event.target.value = "";
      }
    });
    els.aiChatClearAttachmentsButton.addEventListener("click", () => {
      state.pendingAiAttachments = [];
      renderPendingAiAttachments();
      renderStatusStrip([{ label: "图片附件已清空", variant: "emphasis" }]);
    });
    els.aiChatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleAiChatSend();
      }
    });
    els.embeddedAiNewThreadButton.addEventListener("click", () => {
      const thread = setActiveThread(createThreadId(), `会话 ${state.aiThreads.length + 1}`);
      saveAiThreadsToStorage();
      renderStatusStrip([{ label: `已创建 ${thread.title}`, variant: "emphasis" }]);
    });
    els.embeddedUseSelectedBarButton.addEventListener("click", () => {
      try {
        injectPromptIntoEmbeddedInput(buildSelectedBarAnalysisPrompt());
        renderStatusStrip([{ label: "已把选中 K 线上下文带入图表区输入框", variant: "good" }]);
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });
    els.embeddedUseRegionButton.addEventListener("click", () => {
      try {
        injectPromptIntoEmbeddedInput(buildManualRegionAnalysisPrompt());
        renderStatusStrip([{ label: "已把手工区域上下文带入图表区输入框", variant: "good" }]);
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });
    els.embeddedAiChartShotButton.addEventListener("click", async () => {
      try {
        await captureChartScreenshotAttachment();
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });
    els.embeddedAiAttachWidgetButton.addEventListener("click", () => els.embeddedAiImageInput.click());
    els.embeddedAiImageInput.addEventListener("change", async (event) => {
      try {
        await addAiAttachmentsFromFiles(event.target.files, "widget_screenshot");
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      } finally {
        event.target.value = "";
      }
    });
    els.embeddedAiClearButton.addEventListener("click", () => {
      state.pendingAiAttachments = [];
      renderPendingAiAttachments();
      renderStatusStrip([{ label: "图表区附件已清空", variant: "emphasis" }]);
    });
    els.embeddedAiSendButton.addEventListener("click", handleEmbeddedAiSend);
    els.embeddedAiInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleEmbeddedAiSend();
      }
    });
    els.embeddedAiInput.addEventListener("paste", async (event) => {
      const clipboardItems = Array.from(event.clipboardData?.items || []);
      const imageFiles = clipboardItems
        .filter((item) => String(item.type || "").startsWith("image/"))
        .map((item) => item.getAsFile())
        .filter(Boolean);
      if (!imageFiles.length) {
        return;
      }
      event.preventDefault();
      try {
        await addAiAttachmentsFromFiles(imageFiles, "widget_screenshot");
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
    });

    window.addEventListener("blur", () => {
      state.chartInteraction.regionDragActive = false;
      state.chartInteraction.regionDragStart = null;
      finishLayoutDrag();
    });

    async function switchTimeframeInPlace(newTf) {
      els.displayTimeframe.value = newTf;
      syncCacheKey();
      if (state.currentReplayIngestionId) {
        await handleBuildWithForceRefresh();
      } else if (state.snapshot) {
        // LIVE mode: clear stale candles from previous timeframe and re-fetch
        state.snapshot.candles = [];
        state.snapshot.display_timeframe = newTf;
        scheduleChartRerender();
        await refreshLiveTail({ silently: false });
      }
    }
    document.getElementById("tfBtn1m").addEventListener("click", () => switchTimeframeInPlace("1m"));
    document.getElementById("tfBtn5m").addEventListener("click", () => switchTimeframeInPlace("5m"));
    document.getElementById("tfBtn15m").addEventListener("click", () => switchTimeframeInPlace("15m"));
    document.getElementById("tfBtn30m").addEventListener("click", () => switchTimeframeInPlace("30m"));

    function saveSessionState() {
      try {
        const data = captureSessionStatePayload();
        localStorage.setItem("atas_workbench_session", JSON.stringify(data));
      } catch (e) {}
    }
    function loadSessionState() {
      try {
        const raw = localStorage.getItem("atas_workbench_session");
        if (!raw) return null;
        const data = JSON.parse(raw);
        if (Date.now() - data.ts > 24 * 60 * 60 * 1000) return null;
        return data;
      } catch (e) { return null; }
    }

    [
      ["largeOrders", els.layerLargeOrders],
      ["absorption", els.layerAbsorption],
      ["iceberg", els.layerIceberg],
      ["replenishment", els.layerReplenishment],
      ["events", els.layerEvents],
      ["aiLevels", els.layerAiLevels],
      ["manualRegions", els.layerManualRegions],
      ["entries", els.layerEntries],
    ].forEach(([key, button]) => {
      if (!button) return;
      button.addEventListener("click", () => {
        state.layerVisibility[key] = !state.layerVisibility[key];
        updateLayerButtons();
        renderChart();
        scheduleSessionStateSave();
      });
    });

    if (window.ReplayChatWindow) {
      window.ReplayChatWindow.mountModule(document.getElementById("rightAiChatModule"));
      window.ReplayChatWindow.mountModule(document.getElementById("embeddedAiChatModule"));
    }

    initializePanelToggles();
    initializeSectionToggles();
    window.addEventListener("resize", scheduleChartRerender);
    els.aiChatInput.addEventListener("input", () => scheduleSessionStateSave());
    els.embeddedAiInput.addEventListener("input", () => scheduleSessionStateSave());
    els.embeddedPromptSelect.addEventListener("change", () => scheduleSessionStateSave());

    const savedSession = loadSessionState();
    if (savedSession?.ingestionId && savedSession.windowStart && savedSession.windowEnd) {
      els.instrumentSymbol.value = savedSession.symbol || "NQ";
      els.displayTimeframe.value = savedSession.timeframe || "1m";
      els.windowStart.value = savedSession.windowStart;
      els.windowEnd.value = savedSession.windowEnd;
      state.pendingSessionUiRestore = savedSession;
      syncCacheKey();
    } else {
      applyWindowPreset("1m", 7);
    }

    applySavedLayoutState(savedSession);
    applySavedUiState(savedSession);

    window.requestAnimationFrame(async () => {
      if (state.autoBootstrapped) {
        return;
      }
      state.autoBootstrapped = true;
      if (savedSession?.ingestionId) {
        try {
          setBuildProgress(true, 30, "恢复上次会话数据");
          await loadSnapshotByIngestionId(savedSession.ingestionId);
          setBuildProgress(true, 100, "恢复完成");
          window.setTimeout(() => setBuildProgress(false), 400);
          window.setTimeout(() => {
            refreshLiveStatus({ autoRebuildIfNeeded: false, silently: true, allowImmediateRefresh: false });
          }, 0);
          return;
        } catch (e) {}
      }
      await handleBuildWithForceRefresh();
    });

    async function runBackgroundRefreshTick() {
      const now = Date.now();
      if (state.currentReplayIngestionId && now - state.lastSessionSavedAt >= state.sessionSaveIntervalMs) {
        saveSessionState();
        state.lastSessionSavedAt = now;
      }

      if (document.visibilityState !== "visible" || !(state.currentReplayIngestionId || els.instrumentSymbol.value.trim())) {
        return;
      }

      if (now - state.lastLiveStatusPollAt >= state.liveStatusPollIntervalMs) {
        await refreshLiveStatus({ autoRebuildIfNeeded: false, silently: true, refreshTail: false });
      }

      const streamState = state.liveStatus?.stream_state || null;
      if (
        state.snapshot
        && (streamState === "live" || streamState === "delayed")
        && now - state.lastLiveTailPollAt >= state.liveTailPollIntervalMs
      ) {
        await refreshLiveTail({ silently: true });
      }
    }

    setInterval(() => {
      runBackgroundRefreshTick().catch(() => {});
    }, 500);

    window.addEventListener("beforeunload", () => {
      saveSessionState();
    });
    window.addEventListener("pagehide", () => {
      saveSessionState();
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible") {
        saveSessionState();
      }
    });
  
