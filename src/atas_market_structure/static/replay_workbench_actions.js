export function createWorkbenchActions({
  state,
  els,
  fetchJson,
  toUtcString,
  syncCacheKey,
  renderStatusStrip,
  renderSnapshot,
  renderCoreSnapshot,
  renderError,
  renderAiError,
  setBuildProgress,
  buildRequestPayload,
  buildStatusChips,
  translateVerificationStatus,
  loadSnapshotByIngestionId,
  applySnapshotToState,
  loadSidebarDataInBackground,
  loadHistoryDepthInBackground,
  loadDeferredEnhancements,
}) {
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

  function resetReplaySurfaceState({ preserveBuildResponse = true } = {}) {
    if (!preserveBuildResponse) {
      state.buildResponse = null;
    }
    state.snapshot = null;
    state.operatorEntries = [];
    state.manualRegions = [];
    state.aiReview = null;
    state.currentReplayIngestionId = null;
    state.integrity = null;
    state.pendingBackfill = null;
    state.lastLiveTailIntegrityHash = null;
    state.lastChartUpdateType = null;
    state.chartEventModel = null;
    state.historyBackfillLoading = false;
    state.fullHistoryLoaded = false;
    state.enrichmentInFlight = false;
    state.selectedChartEventClusterKey = null;
    state.selectedCandleIndex = null;
    state.selectedFootprintBar = null;
    state.chartView = null;
  }

  function resolveSnapshotIdentity(snapshot) {
    const instrument = snapshot?.instrument && typeof snapshot.instrument === "object"
      ? snapshot.instrument
      : {};
    return {
      symbol: String(snapshot?.instrument_symbol || instrument.symbol || "").trim().toUpperCase(),
      timeframe: String(snapshot?.display_timeframe || snapshot?.timeframe || "").trim().toLowerCase(),
      contractSymbol: String(snapshot?.contract_symbol || instrument.contract_symbol || "").trim().toUpperCase(),
    };
  }

  function sameSnapshotScope(left, right) {
    const leftIdentity = resolveSnapshotIdentity(left);
    const rightIdentity = resolveSnapshotIdentity(right);
    if (!leftIdentity.symbol || !leftIdentity.timeframe || !rightIdentity.symbol || !rightIdentity.timeframe) {
      return false;
    }
    if (leftIdentity.symbol !== rightIdentity.symbol || leftIdentity.timeframe !== rightIdentity.timeframe) {
      return false;
    }
    if (leftIdentity.contractSymbol && rightIdentity.contractSymbol && leftIdentity.contractSymbol !== rightIdentity.contractSymbol) {
      return false;
    }
    return true;
  }

  function pickEarlierIso(...values) {
    const candidates = values
      .map((value) => {
        if (!value) {
          return null;
        }
        const timestamp = Date.parse(value);
        return Number.isFinite(timestamp) ? { value, timestamp } : null;
      })
      .filter(Boolean);
    if (!candidates.length) {
      return values.find(Boolean) || null;
    }
    candidates.sort((left, right) => left.timestamp - right.timestamp);
    return candidates[0].value;
  }

  function pickLaterIso(...values) {
    const candidates = values
      .map((value) => {
        if (!value) {
          return null;
        }
        const timestamp = Date.parse(value);
        return Number.isFinite(timestamp) ? { value, timestamp } : null;
      })
      .filter(Boolean);
    if (!candidates.length) {
      return values.find(Boolean) || null;
    }
    candidates.sort((left, right) => right.timestamp - left.timestamp);
    return candidates[0].value;
  }

  function resolveSnapshotWindowBounds(snapshot, candles) {
    const orderedCandles = Array.isArray(candles) ? candles : [];
    const firstCandle = orderedCandles[0] || null;
    const lastCandle = orderedCandles[orderedCandles.length - 1] || null;
    const startCandidates = [
      snapshot?.window_start,
      firstCandle?.started_at || null,
    ]
      .map((value) => {
        const timestamp = Date.parse(value || "");
        return Number.isFinite(timestamp) ? timestamp : null;
      })
      .filter((value) => value != null);
    const endCandidates = [
      snapshot?.window_end,
      lastCandle?.ended_at || lastCandle?.started_at || null,
    ]
      .map((value) => {
        const timestamp = Date.parse(value || "");
        return Number.isFinite(timestamp) ? timestamp : null;
      })
      .filter((value) => value != null);
    if (!startCandidates.length || !endCandidates.length) {
      return null;
    }
    return {
      startMs: Math.min(...startCandidates),
      endMs: Math.max(...endCandidates),
    };
  }

  function snapshotsHaveMergeableWindows(leftSnapshot, rightSnapshot) {
    const leftWindow = resolveSnapshotWindowBounds(
      leftSnapshot,
      Array.isArray(leftSnapshot?.candles) ? leftSnapshot.candles : [],
    );
    const rightWindow = resolveSnapshotWindowBounds(
      rightSnapshot,
      Array.isArray(rightSnapshot?.candles) ? rightSnapshot.candles : [],
    );
    if (!leftWindow || !rightWindow) {
      return false;
    }
    return leftWindow.startMs <= rightWindow.endMs && rightWindow.startMs <= leftWindow.endMs;
  }

  function mergeSnapshotCandles(baseSnapshot, currentSnapshot) {
    if (!baseSnapshot || !currentSnapshot || !sameSnapshotScope(baseSnapshot, currentSnapshot)) {
      return baseSnapshot;
    }
    if (!snapshotsHaveMergeableWindows(baseSnapshot, currentSnapshot)) {
      return baseSnapshot;
    }
    const baseCandles = Array.isArray(baseSnapshot.candles) ? baseSnapshot.candles : [];
    const currentCandles = Array.isArray(currentSnapshot.candles) ? currentSnapshot.candles : [];
    if (!baseCandles.length || !currentCandles.length) {
      return baseSnapshot;
    }
    const authoritativeWindow = resolveSnapshotWindowBounds(baseSnapshot, baseCandles);
    const mergedByStartedAt = new Map();
    currentCandles.forEach((bar) => {
      if (!bar?.started_at) {
        return;
      }
      const startedAtMs = Date.parse(bar.started_at);
      if (
        authoritativeWindow
        && Number.isFinite(startedAtMs)
        && startedAtMs >= authoritativeWindow.startMs
        && startedAtMs <= authoritativeWindow.endMs
      ) {
        return;
      }
      mergedByStartedAt.set(bar.started_at, bar);
    });
    baseCandles.forEach((bar) => {
      if (bar?.started_at) {
        mergedByStartedAt.set(bar.started_at, bar);
      }
    });
    const mergedCandles = Array.from(mergedByStartedAt.values())
      .sort((left, right) => new Date(left.started_at) - new Date(right.started_at));
    const firstMergedCandle = mergedCandles[0] || null;
    const lastMergedCandle = mergedCandles[mergedCandles.length - 1] || null;
    const nextRawFeatures = {
      ...(currentSnapshot.raw_features || {}),
      ...(baseSnapshot.raw_features || {}),
      total_candle_count: Math.max(
        mergedCandles.length,
        Number(currentSnapshot?.raw_features?.total_candle_count || 0),
        Number(baseSnapshot?.raw_features?.total_candle_count || 0),
      ),
    };
    return {
      ...baseSnapshot,
      source: {
        ...(currentSnapshot.source || {}),
        ...(baseSnapshot.source || {}),
      },
      raw_features: nextRawFeatures,
      live_tail: currentSnapshot.live_tail || baseSnapshot.live_tail || null,
      candles: mergedCandles,
      window_start: pickEarlierIso(
        baseSnapshot.window_start,
        currentSnapshot.window_start,
        firstMergedCandle?.started_at || null,
      ),
      window_end: pickLaterIso(
        currentSnapshot.window_end,
        baseSnapshot.window_end,
        lastMergedCandle?.ended_at || lastMergedCandle?.started_at || null,
      ),
    };
  }

  function mergeFastChartSnapshotIntoCurrent(fastSnapshot, currentSnapshot) {
    if (!fastSnapshot || !currentSnapshot || !sameSnapshotScope(fastSnapshot, currentSnapshot)) {
      return fastSnapshot;
    }
    const mergedSnapshot = mergeSnapshotCandles(fastSnapshot, currentSnapshot);
    return {
      ...currentSnapshot,
      ...mergedSnapshot,
      instrument: {
        ...(currentSnapshot.instrument || {}),
        ...(mergedSnapshot?.instrument || {}),
      },
      source: {
        ...(currentSnapshot.source || {}),
        ...(mergedSnapshot?.source || {}),
      },
      raw_features: {
        ...(currentSnapshot.raw_features || {}),
        ...(mergedSnapshot?.raw_features || {}),
      },
      event_annotations: Array.isArray(currentSnapshot.event_annotations)
        ? currentSnapshot.event_annotations
        : (Array.isArray(mergedSnapshot?.event_annotations) ? mergedSnapshot.event_annotations : []),
      focus_regions: Array.isArray(currentSnapshot.focus_regions)
        ? currentSnapshot.focus_regions
        : (Array.isArray(mergedSnapshot?.focus_regions) ? mergedSnapshot.focus_regions : []),
      strategy_candidates: Array.isArray(currentSnapshot.strategy_candidates)
        ? currentSnapshot.strategy_candidates
        : (Array.isArray(mergedSnapshot?.strategy_candidates) ? mergedSnapshot.strategy_candidates : []),
      integrity: currentSnapshot.integrity || mergedSnapshot?.integrity || null,
      latest_backfill_request: currentSnapshot.latest_backfill_request || mergedSnapshot?.latest_backfill_request || null,
      live_tail: currentSnapshot.live_tail || mergedSnapshot?.live_tail || null,
    };
  }

  function buildFastChartSnapshot(payload, result) {
    if (!result || typeof result !== "object") {
      return null;
    }
    const currentInstrument = state.snapshot?.instrument && typeof state.snapshot.instrument === "object"
      ? state.snapshot.instrument
      : {};
    const requestedSymbol = String(result.symbol || payload.instrument_symbol || "").trim().toUpperCase();
    const currentSymbol = String(state.snapshot?.instrument_symbol || currentInstrument.symbol || "").trim().toUpperCase();
    const carriedContractSymbol = currentSymbol && currentSymbol === requestedSymbol
      ? String(currentInstrument.contract_symbol || state.snapshot?.contract_symbol || "").trim().toUpperCase()
      : "";
    const carriedRootSymbol = currentSymbol && currentSymbol === requestedSymbol
      ? String(currentInstrument.root_symbol || "").trim().toUpperCase()
      : "";
    return {
      instrument_symbol: requestedSymbol,
      display_timeframe: String(result.timeframe || payload.display_timeframe || "").trim(),
      timeframe: String(result.timeframe || payload.display_timeframe || "").trim(),
      contract_symbol: carriedContractSymbol || null,
      instrument: {
        symbol: requestedSymbol,
        contract_symbol: carriedContractSymbol || null,
        root_symbol: carriedRootSymbol || null,
      },
      source: {
        chart_backend: "clickhouse",
        snapshot_mode: "chart-candles-fast-path",
        chart_instance_id: String(payload.chart_instance_id || "").trim() || null,
      },
      window_start: result.window_start || payload.window_start || null,
      window_end: result.window_end || payload.window_end || null,
      candles: Array.isArray(result.candles) ? result.candles : [],
      event_annotations: [],
      focus_regions: [],
      strategy_candidates: [],
      integrity: null,
      latest_backfill_request: null,
      live_tail: state.snapshot?.live_tail || null,
      raw_features: {
        total_candle_count: Number(result.count || (Array.isArray(result.candles) ? result.candles.length : 0) || 0),
        deferred_history_available: false,
        chart_data_source: "clickhouse",
      },
    };
  }

  async function loadFastChartSnapshot(payload) {
    if (!payload?.instrument_symbol || !payload?.display_timeframe || !payload?.window_start || !payload?.window_end) {
      return null;
    }
    const query = new URLSearchParams({
      symbol: String(payload.instrument_symbol).trim().toUpperCase(),
      timeframe: String(payload.display_timeframe).trim(),
      window_start: String(payload.window_start).trim(),
      window_end: String(payload.window_end).trim(),
    });
    const startedAt = performance.now();
    const result = await fetchJson(`/api/v1/workbench/chart-candles?${query.toString()}`);
    const snapshot = buildFastChartSnapshot(payload, result);
    if (!snapshot) {
      return null;
    }
    return {
      snapshot,
      count: Array.isArray(snapshot.candles) ? snapshot.candles.length : 0,
      elapsedMs: Math.round(performance.now() - startedAt),
    };
  }

  function alignPayloadWindowToObservedAt(payload, latestObservedAt) {
    if (!payload || !latestObservedAt) {
      return payload;
    }
    const observedAtMs = Date.parse(latestObservedAt);
    const payloadStartMs = Date.parse(payload.window_start);
    const payloadEndMs = Date.parse(payload.window_end);
    if (
      !state.followLatest
      || !Number.isFinite(observedAtMs)
      || !Number.isFinite(payloadStartMs)
      || !Number.isFinite(payloadEndMs)
      || observedAtMs <= payloadEndMs
    ) {
      return payload;
    }
    const spanMs = Math.max(0, payloadEndMs - payloadStartMs);
    return {
      ...payload,
      window_start: new Date(observedAtMs - spanMs).toISOString(),
      window_end: new Date(observedAtMs).toISOString(),
    };
  }

  function applyBuildResponseMeta(result) {
    state.buildResponse = result;
    state.integrity = result.integrity || null;
    state.pendingBackfill = result.atas_backfill_request || null;
    if (els.chartInstanceId) {
      els.chartInstanceId.value = String(
        result.core_snapshot?.source?.chart_instance_id || result.atas_backfill_request?.chart_instance_id || "",
      ).trim();
    }
    state.lastLiveTailIntegrityHash = state.integrity ? JSON.stringify(state.integrity) : null;
    state.aiReview = null;
    state.currentReplayIngestionId = result.ingestion_id || null;
  }

  async function handleBuild() {
    if (state.buildInFlight || state.enrichmentInFlight) {
      return;
    }
    let fastSnapshotApplied = false;
    try {
      state.buildInFlight = true;
      state.enrichmentInFlight = true;
      setBuildProgress(true, 6, "准备图表窗口");
      const payload = buildRequestPayload();
      const buildStartedAt = performance.now();
      state.perf.loadStartedAt = buildStartedAt;
      state.perf.lastReason = "build";
      state.buildResponse = null;
      state.integrity = null;
      state.pendingBackfill = null;
      state.lastLiveTailIntegrityHash = null;
      state.currentReplayIngestionId = null;
      const buildPromise = fetchJson("/api/v1/workbench/replay-builder/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setBuildProgress(true, 18, "ClickHouse 主图预加载");
      let fastChartResult = null;
      try {
        fastChartResult = await loadFastChartSnapshot(payload);
      } catch (error) {
        console.warn("CK 主图快路径加载失败，继续等待完整 build", error);
      }
      if (fastChartResult?.snapshot) {
        state.perf.coreSnapshotLoadMs = fastChartResult.elapsedMs;
        state.perf.lastReason = "clickhouse-chart-fast-path";
        applySnapshotToState(null, fastChartResult.snapshot, {
          preserveChartView: true,
          preserveSelection: true,
          reason: "clickhouse-chart-fast-path",
        });
        fastSnapshotApplied = true;
        state.buildInFlight = false;
        state.topBar.lastSyncedAt = fastChartResult.snapshot.window_end || new Date().toISOString();
        setBuildProgress(
          true,
          44,
          fastChartResult.count > 0
            ? `CK 主图已就绪 · ${fastChartResult.count} 根K线`
            : "CK 当前窗口暂无K线，继续后台补全",
        );
        renderSnapshot();
        loadDeferredEnhancements();
      } else {
        setBuildProgress(true, 24, "等待完整回放构建返回");
      }
      let result;
      try {
        result = await buildPromise;
      } catch (error) {
        if (fastSnapshotApplied) {
          setBuildProgress(false, 100, "主图已就绪，后台补全失败");
          renderStatusStrip([{ label: `主图已从 CK 加载，后台补全失败：${error.message || String(error)}`, variant: "warn" }]);
          return;
        }
        throw error;
      }
      state.lastBuildResponseMs = Math.round(performance.now() - buildStartedAt);
      state.perf.buildResponseMs = state.lastBuildResponseMs;
      setBuildProgress(true, fastSnapshotApplied ? 74 : 42, fastSnapshotApplied ? "后台回放上下文已返回" : "后端已返回首屏数据");
      applyBuildResponseMeta(result);
      renderStatusStrip(buildStatusChips(result));
      if (result.core_snapshot && result.ingestion_id) {
        const mergedSnapshot = mergeSnapshotCandles(result.core_snapshot, state.snapshot);
        setBuildProgress(true, fastSnapshotApplied ? 84 : 68, fastSnapshotApplied ? "正在无感补全事件与侧栏" : "正在渲染首屏K线");
        applySnapshotToState(result.ingestion_id, mergedSnapshot, {
          preserveChartView: true,
          preserveSelection: true,
          reason: fastSnapshotApplied ? "build-enrichment-merge" : "build-inline-core",
        });
        renderSnapshot();
        const sidebarPromise = loadSidebarDataInBackground(result.ingestion_id);
        if (typeof loadHistoryDepthInBackground === "function") {
          void loadHistoryDepthInBackground(result.ingestion_id);
        }
        loadDeferredEnhancements();
        setBuildProgress(true, fastSnapshotApplied ? 92 : 82, fastSnapshotApplied ? "侧栏与上下文补全中" : "首屏K线已就绪");
        await Promise.allSettled([sidebarPromise]);
        setBuildProgress(true, 96, "侧栏与上下文已同步");
      } else if (result.ingestion_id) {
        setBuildProgress(true, fastSnapshotApplied ? 82 : 58, fastSnapshotApplied ? "正在载入完整回放上下文" : "正在载入回放快照");
        await loadSnapshotByIngestionId(result.ingestion_id, {
          preserveChartView: true,
          preserveSelection: true,
          reason: fastSnapshotApplied ? "build-fetch-core-after-fast-path" : "build-fetch-core",
        });
        setBuildProgress(true, 90, "图表与侧栏已就绪");
      } else {
        renderSnapshot();
      }
      setBuildProgress(false, 100, fastSnapshotApplied ? "主图与上下文已就绪" : "图表已就绪");
    } catch (error) {
      setBuildProgress(false, 0, "界面加载已中断");
      renderError(error);
    } finally {
      state.buildInFlight = false;
      state.enrichmentInFlight = false;
      renderSnapshot();
    }
  }

  async function handleFastChartRefresh({ latestObservedAt = null, silent = true } = {}) {
    if (state.buildInFlight || state.enrichmentInFlight) {
      return false;
    }
    const payload = alignPayloadWindowToObservedAt(buildRequestPayload(), latestObservedAt);
    let fastChartResult = null;
    try {
      fastChartResult = await loadFastChartSnapshot(payload);
    } catch (error) {
      console.warn("CK 主图轻量刷新失败，准备回退完整 build", error);
      return false;
    }
    if (!fastChartResult?.snapshot) {
      return false;
    }
    const preservedOperatorEntries = Array.isArray(state.operatorEntries) ? [...state.operatorEntries] : [];
    const preservedManualRegions = Array.isArray(state.manualRegions) ? [...state.manualRegions] : [];
    const preservedReviewProjection = state.reviewProjection || null;
    const preservedChartEventModel = state.chartEventModel || null;
    const preservedSelectedClusterKey = state.selectedChartEventClusterKey || null;
    const preservedAiReview = state.aiReview || null;
    const preservedBuildResponse = state.buildResponse || null;
    const preservedIntegrity = state.integrity || null;
    const preservedPendingBackfill = state.pendingBackfill || null;
    const mergedSnapshot = mergeFastChartSnapshotIntoCurrent(fastChartResult.snapshot, state.snapshot);
    applySnapshotToState(state.currentReplayIngestionId, mergedSnapshot, {
      preserveChartView: true,
      preserveSelection: true,
      reason: "clickhouse-chart-refresh",
    });
    state.operatorEntries = preservedOperatorEntries;
    state.manualRegions = preservedManualRegions;
    state.reviewProjection = preservedReviewProjection;
    state.chartEventModel = preservedChartEventModel;
    state.selectedChartEventClusterKey = preservedSelectedClusterKey;
    state.aiReview = preservedAiReview;
    state.buildResponse = preservedBuildResponse;
    state.integrity = preservedIntegrity || mergedSnapshot?.integrity || null;
    state.pendingBackfill = preservedPendingBackfill || mergedSnapshot?.latest_backfill_request || null;
    state.lastLiveTailIntegrityHash = state.integrity ? JSON.stringify(state.integrity) : null;
    state.topBar.lastSyncedAt = latestObservedAt || mergedSnapshot?.window_end || new Date().toISOString();
    state.perf.coreSnapshotLoadMs = fastChartResult.elapsedMs;
    state.perf.lastReason = "clickhouse-chart-refresh";
    state.lastChartUpdateType = "chart_refresh";
    if (!silent) {
      renderStatusStrip([{
        label: fastChartResult.count > 0 ? `CK 主图轻量刷新 · ${fastChartResult.count} 根K线` : "CK 主图轻量刷新完成",
        variant: "good",
      }]);
    }
    renderSnapshot();
    return true;
  }

  async function handleLookup() {
    try {
      syncCacheKey();
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
        atas_backfill_request: null,
        integrity: result.record?.integrity || null,
      };
      state.integrity = state.buildResponse.integrity;
      state.pendingBackfill = state.buildResponse.atas_backfill_request;
      if (els.chartInstanceId) {
        els.chartInstanceId.value = String(
          state.buildResponse?.record?.source?.chart_instance_id || state.buildResponse?.atas_backfill_request?.chart_instance_id || "",
        ).trim();
      }
      state.lastLiveTailIntegrityHash = state.integrity ? JSON.stringify(state.integrity) : null;
      state.aiReview = null;
      state.currentReplayIngestionId = result.record?.ingestion_id || null;
      renderStatusStrip([
        { label: result.record ? "缓存已命中" : "缓存不存在", variant: result.record ? "good" : "warn" },
        { label: result.auto_fetch_allowed ? "允许自动补抓" : "当前禁止自动补抓", variant: result.auto_fetch_allowed ? "emphasis" : "" },
        { label: result.verification_due_now ? "当前需要核对" : "当前无需核对", variant: result.verification_due_now ? "emphasis" : "" },
      ]);
      if (result.record?.ingestion_id) {
        await loadSnapshotByIngestionId(result.record.ingestion_id, {
          preserveChartView: true,
          preserveSelection: true,
          reason: "lookup-cache-hit",
        });
      } else {
        resetReplaySurfaceState({ preserveBuildResponse: true });
        renderSnapshot();
      }
      return result;
    } catch (error) {
      renderError(error);
      return null;
    }
  }

  async function handleInvalidate() {
    try {
      syncCacheKey();
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
      resetReplaySurfaceState({ preserveBuildResponse: true });
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
        atas_backfill_request: null,
        integrity: null,
      };
      renderSnapshot();
      return result;
    } catch (error) {
      renderError(error);
      return null;
    }
  }

  async function handleRepairCurrentWindow() {
    syncCacheKey();
    const cacheKey = (els.cacheKey?.value || "").trim();
    const windowStart = toUtcString(els.windowStart?.value);
    const windowEnd = toUtcString(els.windowEnd?.value);
    if (!cacheKey) {
      throw new Error("当前窗口还没有可修复的缓存键。");
    }
    if (!windowStart || !windowEnd) {
      throw new Error("修复当前图表前需要完整的开始和结束时间。");
    }

    const snapshotInstrument = state.snapshot?.instrument || {};
    const pending = state.pendingBackfill || {};
    const instrumentSymbol = String(
      snapshotInstrument.symbol || state.snapshot?.instrument_symbol || els.instrumentSymbol?.value || "",
    ).trim().toUpperCase();
    if (!instrumentSymbol) {
      throw new Error("当前没有可修复的品种标识。");
    }

    const contractSymbol = String(
      snapshotInstrument.contract_symbol || pending.contract_symbol || pending.target_contract_symbol || "",
    ).trim().toUpperCase() || null;
    const rootSymbol = String(
      snapshotInstrument.root_symbol || pending.root_symbol || pending.target_root_symbol || els.instrumentSymbol?.value || "",
    ).trim().toUpperCase() || null;
    const chartInstanceId = String(
      els.chartInstanceId?.value || state.snapshot?.source?.chart_instance_id || pending.chart_instance_id || "",
    ).trim() || null;

    const result = await fetchJson("/api/v1/workbench/atas-backfill-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cache_key: cacheKey,
        instrument_symbol: instrumentSymbol,
        contract_symbol: contractSymbol,
        root_symbol: rootSymbol,
        target_contract_symbol: contractSymbol,
        target_root_symbol: rootSymbol,
        display_timeframe: els.displayTimeframe?.value || state.topBar?.timeframe || "1m",
        window_start: windowStart,
        window_end: windowEnd,
        chart_instance_id: chartInstanceId,
        reason: "manual_chart_repair",
        request_history_bars: true,
        request_history_footprint: false,
        replace_existing_history: true,
      }),
    });

    state.pendingBackfill = result?.request || null;
    if (els.chartInstanceId) {
      els.chartInstanceId.value = result?.request?.chart_instance_id || chartInstanceId || "";
    }
    renderStatusStrip([
      {
        label: result?.reused_existing_request ? "已有修复任务，继续等待 ATAS 重发" : "已清空目标窗口，等待 ATAS 重发",
        variant: result?.reused_existing_request ? "emphasis" : "warn",
      },
      {
        label: chartInstanceId ? `chart_instance_id=${chartInstanceId}` : "未绑定图表实例，按当前品种窗口修复",
        variant: chartInstanceId ? "good" : "warn",
      },
    ]);
    renderSnapshot();
    return result;
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

  async function handleSaveRegion() {
    try {
      await saveDraftRegion();
    } catch (error) {
      renderStatusStrip([{ label: "区域保存失败", variant: "warn" }]);
    }
  }

  return {
    saveDraftRegion,
    handleBuild,
    handleFastChartRefresh,
    handleLookup,
    handleInvalidate,
    handleRepairCurrentWindow,
    handleRecordEntry,
    handleAiReview,
    handleSaveRegion,
  };
}
