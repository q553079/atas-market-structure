export function createReplayLoader({
  state,
  els,
  fetchJson,
  ensureThread,
  renderCoreSnapshot,
  renderSidebarSnapshot,
  renderDeferredSurfaces,
}) {
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
    const windowEnd = new Date(state.snapshot.window_end);
    const localValue = `${windowEnd.getFullYear()}-${String(windowEnd.getMonth() + 1).padStart(2, "0")}-${String(windowEnd.getDate()).padStart(2, "0")}T${String(windowEnd.getHours()).padStart(2, "0")}:${String(windowEnd.getMinutes()).padStart(2, "0")}`;
    if (!els.entryExecutedAt.value) {
      els.entryExecutedAt.value = localValue;
    }
    if (!els.entryPrice.value && state.snapshot.candles?.length) {
      els.entryPrice.value = state.snapshot.candles[state.snapshot.candles.length - 1].close.toFixed(2);
    }
  }

  function applySnapshotToState(ingestionId, snapshot, options = {}) {
    const {
      preserveChartView = false,
      preserveSelection = false,
      reason = "default",
    } = options || {};
    const previousSnapshot = state.snapshot;
    const previousChartView = state.chartView ? { ...state.chartView } : null;
    const previousSelectedCandleIndex = state.selectedCandleIndex;
    const previousSelectedFootprintBar = state.selectedFootprintBar;
    const nextSymbol = snapshot?.instrument_symbol || snapshot?.instrument?.symbol || "";
    const nextTimeframe = snapshot?.display_timeframe || "";
    const previousSymbol = previousSnapshot?.instrument_symbol || previousSnapshot?.instrument?.symbol || "";
    const previousTimeframe = previousSnapshot?.display_timeframe || "";
    const sameSymbol = previousSymbol === nextSymbol;
    const sameTimeframe = previousTimeframe === nextTimeframe;
    const shouldPreserveChartView = !!preserveChartView && sameSymbol && sameTimeframe;
    const shouldPreserveSelection = !!preserveSelection && sameSymbol && sameTimeframe;

    state.currentReplayIngestionId = ingestionId;
    state.snapshot = snapshot;
    state.integrity = snapshot?.integrity || null;
    state.pendingBackfill = snapshot?.latest_backfill_request || state.buildResponse?.atas_backfill_request || null;
    state.lastLiveTailIntegrityHash = state.integrity ? JSON.stringify(state.integrity) : null;
    state.operatorEntries = [];
    state.manualRegions = [];
    state.aiReview = null;
    state.chartEventModel = null;
    state.selectedChartEventClusterKey = null;
    state.selectedCandleIndex = shouldPreserveSelection ? previousSelectedCandleIndex : null;
    state.selectedFootprintBar = shouldPreserveSelection ? previousSelectedFootprintBar : null;
    state.chartView = shouldPreserveChartView ? previousChartView : null;
    state.lastSnapshotLoadReason = reason;
    state.fullHistoryLoaded = !snapshot?.raw_features?.deferred_history_available;
    if (!state.aiThreads?.length) {
      ensureThread("session-01", "01");
      state.activeAiThreadId = "session-01";
    }
    syncEntryDefaultsFromSnapshot();
  }

  function applyFullHistoryCandles(snapshot) {
    if (!state.snapshot || !snapshot?.candles?.length) {
      return false;
    }
    const currentCandles = Array.isArray(state.snapshot.candles) ? state.snapshot.candles : [];
    const nextCandles = Array.isArray(snapshot.candles) ? snapshot.candles : [];
    const currentFirstStartedAt = currentCandles[0]?.started_at;
    const mergedEarlierCandles = nextCandles.filter((bar) => bar?.started_at && (!currentFirstStartedAt || bar.started_at < currentFirstStartedAt));
    const nextTotal = Number(snapshot?.raw_features?.total_candle_count || nextCandles.length || 0);
    const currentTotal = Number(state.snapshot?.raw_features?.total_candle_count || currentCandles.length || 0);
    if (!mergedEarlierCandles.length && nextTotal <= currentTotal) {
      return false;
    }
    state.snapshot = {
      ...state.snapshot,
      candles: [...mergedEarlierCandles, ...currentCandles],
      window_start: snapshot.window_start,
      window_end: snapshot.window_end,
      raw_features: {
        ...(state.snapshot.raw_features || {}),
        ...(snapshot.raw_features || {}),
        deferred_history_available: false,
      },
    };
    state.fullHistoryLoaded = true;
    return mergedEarlierCandles.length > 0;
  }

  async function loadCoreSnapshot(ingestionId, options = {}) {
    state.snapshotLoading = true;
    const startedAt = performance.now();
    try {
      const ingestion = await fetchJson(`/api/v1/ingestions/${encodeURIComponent(ingestionId)}`);
      applySnapshotToState(ingestionId, ingestion.observed_payload, options);
      state.perf.coreSnapshotLoadMs = Math.round(performance.now() - startedAt);
      state.perf.lastReason = options?.reason || "core-snapshot";
      renderCoreSnapshot();
      return ingestion.observed_payload;
    } finally {
      state.snapshotLoading = false;
    }
  }

  async function loadSidebarDataInBackground(ingestionId) {
    if (!ingestionId || ingestionId !== state.currentReplayIngestionId) {
      return;
    }
    state.sidebarLoading = true;
    const startedAt = performance.now();
    try {
      await Promise.all([loadOperatorEntries(), loadManualRegions()]);
      if (ingestionId !== state.currentReplayIngestionId) {
        return;
      }
      state.lastSidebarLoadMs = Math.round(performance.now() - startedAt);
      state.perf.sidebarLoadMs = state.lastSidebarLoadMs;
      renderSidebarSnapshot();
    } catch (error) {
      console.warn("加载 sidebar 数据失败:", error);
    } finally {
      state.sidebarLoading = false;
    }
  }

  async function loadHistoryDepthInBackground(ingestionId) {
    if (!ingestionId || ingestionId !== state.currentReplayIngestionId || state.historyBackfillLoading || state.fullHistoryLoaded) {
      return;
    }
    if (!state.snapshot?.raw_features?.deferred_history_available) {
      return;
    }
    state.historyBackfillLoading = true;
    try {
      const ingestion = await fetchJson(`/api/v1/ingestions/${encodeURIComponent(ingestionId)}`);
      if (ingestionId !== state.currentReplayIngestionId) {
        return;
      }
      if (applyFullHistoryCandles(ingestion.observed_payload)) {
        state.lastChartUpdateType = "prepend_history";
        renderCoreSnapshot();
      }
    } catch (error) {
      console.warn("后台补齐完整历史失败:", error);
    } finally {
      state.historyBackfillLoading = false;
    }
  }

  function loadDeferredEnhancements() {
    if (state.deferredRefreshScheduled || state.snapshotLoading) {
      return;
    }
    state.deferredRefreshScheduled = true;
    window.setTimeout(() => {
      state.deferredRefreshScheduled = false;
      if (state.snapshotLoading) {
        return;
      }
      renderDeferredSurfaces();
    }, 1200);
  }

  async function loadSnapshotByIngestionId(ingestionId, options = {}) {
    await loadCoreSnapshot(ingestionId, options);
    void loadSidebarDataInBackground(ingestionId);
    void loadHistoryDepthInBackground(ingestionId);
    loadDeferredEnhancements();
  }

  return {
    applySnapshotToState,
    applyFullHistoryCandles,
    loadSnapshotByIngestionId,
    loadCoreSnapshot,
    loadSidebarDataInBackground,
    loadHistoryDepthInBackground,
    loadDeferredEnhancements,
    loadOperatorEntries,
    loadManualRegions,
    loadFootprintBarDetail,
    syncEntryDefaultsFromSnapshot,
  };
}
