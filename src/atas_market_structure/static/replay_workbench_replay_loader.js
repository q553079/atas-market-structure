import { buildChartViewportKey } from "./replay_workbench_chart_utils.js";
import { normalizeReplaySnapshot, sanitizeReplayCandles } from "./replay_workbench_ui_utils.js";

function buildRelaxedChartScopeKey(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return "";
  }
  const instrument = snapshot.instrument && typeof snapshot.instrument === "object" ? snapshot.instrument : {};
  const contractSymbol = String(instrument.contract_symbol || snapshot.contract_symbol || "").trim().toUpperCase();
  const instrumentSymbol = String(snapshot.instrument_symbol || instrument.symbol || "").trim().toUpperCase();
  const timeframe = String(snapshot.display_timeframe || snapshot.timeframe || "").trim().toLowerCase();
  return [
    contractSymbol || "no-contract",
    instrumentSymbol || "no-symbol",
    timeframe || "no-timeframe",
  ].join("|");
}

function buildRelaxedChartScopeKeyFromViewportKey(viewportKey) {
  const parts = String(viewportKey || "").split("|");
  if (parts.length < 4) {
    return "";
  }
  return [
    parts[1] || "no-contract",
    parts[2] || "no-symbol",
    String(parts[3] || "").toLowerCase() || "no-timeframe",
  ].join("|");
}

function findSavedChartView(registry, nextChartKey, relaxedScopeKey) {
  if (!registry || typeof registry !== "object") {
    return null;
  }
  if (nextChartKey && registry[nextChartKey]) {
    return registry[nextChartKey];
  }
  if (!relaxedScopeKey) {
    return null;
  }
  const entries = Object.entries(registry);
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const [viewportKey, savedView] = entries[index];
    if (buildRelaxedChartScopeKeyFromViewportKey(viewportKey) === relaxedScopeKey && savedView) {
      return savedView;
    }
  }
  return null;
}

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

  async function loadReviewProjection() {
    const snapshot = state.snapshot;
    const instrumentSymbol = snapshot?.instrument_symbol || snapshot?.instrument?.symbol || "";
    if (!instrumentSymbol) {
      state.reviewProjection = null;
      return;
    }
    const params = new URLSearchParams({
      instrument_symbol: instrumentSymbol,
      limit: "80",
    });
    if (snapshot?.window_start) {
      params.set("window_start", snapshot.window_start);
    }
    if (snapshot?.window_end) {
      params.set("window_end", snapshot.window_end);
    }
    state.reviewProjection = await fetchJson(`/api/v1/workbench/review/projection?${params.toString()}`);
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
    const normalizedSnapshot = normalizeReplaySnapshot(snapshot, {
      context: `snapshot:${ingestionId}`,
    });
    const previousSnapshot = state.snapshot;
    const previousChartView = state.chartView ? { ...state.chartView } : null;
    const previousSelectedCandleIndex = state.selectedCandleIndex;
    const previousSelectedFootprintBar = state.selectedFootprintBar;
    const nextSymbol = normalizedSnapshot?.instrument_symbol || normalizedSnapshot?.instrument?.symbol || "";
    const nextTimeframe = normalizedSnapshot?.display_timeframe || "";
    const nextContractSymbol = String(normalizedSnapshot?.instrument?.contract_symbol || normalizedSnapshot?.contract_symbol || "").trim().toUpperCase();
    const previousSymbol = previousSnapshot?.instrument_symbol || previousSnapshot?.instrument?.symbol || "";
    const previousTimeframe = previousSnapshot?.display_timeframe || "";
    const previousContractSymbol = String(previousSnapshot?.instrument?.contract_symbol || previousSnapshot?.contract_symbol || "").trim().toUpperCase();
    const previousChartKey = buildChartViewportKey(previousSnapshot);
    const nextChartKey = buildChartViewportKey(normalizedSnapshot);
    const previousChartScopeKey = buildRelaxedChartScopeKey(previousSnapshot);
    const nextChartScopeKey = buildRelaxedChartScopeKey(normalizedSnapshot);
    const sameSymbol = previousSymbol === nextSymbol;
    const sameTimeframe = previousTimeframe === nextTimeframe;
    const sameContract = !!nextContractSymbol && nextContractSymbol === previousContractSymbol;
    const sameChartIdentity = !!nextChartKey && nextChartKey === previousChartKey;
    const sameChartScope = !!nextChartScopeKey && nextChartScopeKey === previousChartScopeKey;
    const sameScopeFallback = sameSymbol && sameTimeframe && (!nextContractSymbol || sameContract);
    const shouldPreserveChartView = !!preserveChartView && (sameChartIdentity || sameChartScope || sameScopeFallback);
    const shouldPreserveSelection = !!preserveSelection && (sameChartIdentity || sameChartScope || sameScopeFallback);
    const savedChartView = findSavedChartView(state.chartViewportRegistry, nextChartKey, nextChartScopeKey);

    state.currentReplayIngestionId = ingestionId;
    state.snapshot = normalizedSnapshot;
    state.integrity = normalizedSnapshot?.integrity || null;
    state.pendingBackfill = normalizedSnapshot?.latest_backfill_request || state.buildResponse?.atas_backfill_request || null;
    if (els.chartInstanceId) {
      els.chartInstanceId.value = String(
        normalizedSnapshot?.source?.chart_instance_id || state.pendingBackfill?.chart_instance_id || "",
      ).trim();
    }
    state.lastLiveTailIntegrityHash = state.integrity ? JSON.stringify(state.integrity) : null;
    state.reviewProjection = null;
    state.operatorEntries = [];
    state.manualRegions = [];
    state.aiReview = null;
    state.chartEventModel = null;
    state.selectedChartEventClusterKey = null;
    state.selectedCandleIndex = shouldPreserveSelection ? previousSelectedCandleIndex : null;
    state.selectedFootprintBar = shouldPreserveSelection ? previousSelectedFootprintBar : null;
    state.chartView = shouldPreserveChartView ? previousChartView : null;
    state.pendingChartViewRestore = shouldPreserveChartView ? null : (savedChartView ? { ...savedChartView } : null);
    state.lastChartViewportKey = nextChartKey || null;
    state.chartViewportResetPending = !shouldPreserveChartView;
    state.chartAutoScalePending = !(shouldPreserveChartView || savedChartView);
    state.lastSnapshotLoadReason = reason;
    state.fullHistoryLoaded = !normalizedSnapshot?.raw_features?.deferred_history_available;
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
    const currentCandles = sanitizeReplayCandles(state.snapshot.candles, {
      context: "full-history-current",
      log: false,
    });
    const nextCandles = sanitizeReplayCandles(snapshot.candles, {
      context: "full-history-next",
      log: false,
    });
    const currentFirstStartedAt = currentCandles[0]?.started_at;
    const mergedEarlierCandles = nextCandles.filter((bar) => bar?.started_at && (!currentFirstStartedAt || bar.started_at < currentFirstStartedAt));
    const nextTotal = Number(snapshot?.raw_features?.total_candle_count || nextCandles.length || 0);
    const currentTotal = Number(state.snapshot?.raw_features?.total_candle_count || currentCandles.length || 0);
    if (!mergedEarlierCandles.length && nextTotal <= currentTotal) {
      return false;
    }
    state.snapshot = normalizeReplaySnapshot({
      ...state.snapshot,
      candles: [...mergedEarlierCandles, ...currentCandles],
      window_start: snapshot.window_start,
      window_end: snapshot.window_end,
      raw_features: {
        ...(state.snapshot.raw_features || {}),
        ...(snapshot.raw_features || {}),
        deferred_history_available: false,
      },
    }, {
      context: "full-history-merged",
    });
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
      await Promise.all([loadOperatorEntries(), loadManualRegions(), loadReviewProjection()]);
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
    loadReviewProjection,
    loadFootprintBarDetail,
    syncEntryDefaultsFromSnapshot,
  };
}
