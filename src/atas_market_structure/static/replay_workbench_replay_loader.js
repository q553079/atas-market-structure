export function createReplayLoader({
  state,
  els,
  fetchJson,
  ensureThread,
  renderSnapshot,
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

  async function loadSnapshotByIngestionId(ingestionId) {
    const ingestion = await fetchJson(`/api/v1/ingestions/${encodeURIComponent(ingestionId)}`);
    state.currentReplayIngestionId = ingestionId;
    state.snapshot = ingestion.observed_payload;
    state.operatorEntries = [];
    state.manualRegions = [];
    state.aiReview = null;
    state.aiThreads = [];
    state.activeAiThreadId = "main";
    state.selectedCandleIndex = null;
    state.selectedFootprintBar = null;
    state.chartView = null;
    ensureThread("main", "主线程");
    await loadOperatorEntries();
    await loadManualRegions();
    syncEntryDefaultsFromSnapshot();
    renderSnapshot();
  }

  return {
    loadSnapshotByIngestionId,
    loadOperatorEntries,
    loadManualRegions,
    loadFootprintBarDetail,
    syncEntryDefaultsFromSnapshot,
  };
}
