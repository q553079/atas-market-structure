export function createWorkbenchActions({
  state,
  els,
  fetchJson,
  toUtcString,
  syncCacheKey,
  renderStatusStrip,
  renderSnapshot,
  renderError,
  renderAiError,
  setBuildProgress,
  buildRequestPayload,
  buildStatusChips,
  translateVerificationStatus,
  loadSnapshotByIngestionId,
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

  async function handleBuild() {
    if (state.buildInFlight) {
      return;
    }
    try {
      state.buildInFlight = true;
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
        renderSnapshot();
      }
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
    } catch (error) {
      renderError(error);
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
    handleLookup,
    handleInvalidate,
    handleRecordEntry,
    handleAiReview,
    handleSaveRegion,
  };
}
