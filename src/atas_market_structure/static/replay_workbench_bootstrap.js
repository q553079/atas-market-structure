import { createWorkbenchState } from "./replay_workbench_state.js";
import { createWorkbenchElements } from "./replay_workbench_dom.js";
import { fetchJson, toLocalInputValue, createCacheKeyHelpers } from "./replay_workbench_data_utils.js";
import {
  timeframeLabel,
  getPresetThreadMeta,
  createThreadId,
  translateAction,
  translateVerificationStatus,
  translateAcquisitionMode,
  writeStorage,
  readStorage,
  summarizeText,
  escapeHtml,
} from "./replay_workbench_ui_utils.js";
import { createAiThreadController } from "./replay_workbench_ai_threads.js";
import { createAiChatController } from "./replay_workbench_ai_chat.js";
import { createReplayLoader } from "./replay_workbench_replay_loader.js";
import { createWorkbenchActions } from "./replay_workbench_actions.js";
import { createChartViewHelpers, clampChartView } from "./replay_workbench_chart_utils.js";
import { createPlanLifecycleEngine } from "./replay_workbench_plan_lifecycle.js";
import { createSessionMemoryEngine } from "./replay_workbench_session_memory.js";
import { createAnnotationPanelController } from "./replay_workbench_annotation_panel.js";
import { createAnnotationPopoverController } from "./replay_workbench_annotation_popover.js";
import { createModelSwitcherController } from "./replay_workbench_model_switcher.js";

function renderStatusStripFactory(els) {
  return function renderStatusStrip(chips = []) {
    if (!els.statusStrip) return;
    try {
      const safeChips = Array.isArray(chips) ? chips : [];
      els.statusStrip.innerHTML = safeChips.map((item) => {
        if (!item || typeof item !== "object") {
          const label = typeof item === "string" ? item : String(item || "");
          return `<span class="chip">${label}</span>`;
        }
        const variant = item.variant ? ` ${item.variant}` : "";
        const label = item.label || String(item || "");
        return `<span class="chip${variant}">${label}</span>`;
      }).join("");
    } catch (error) {
      console.error("renderStatusStrip 错误:", error, chips);
      els.statusStrip.innerHTML = `<span class="chip warn">状态显示错误</span>`;
    }
  };
}

function buildStatusChips(result) {
  if (!result) {
    return [];
  }
  const chips = [];
  if (result.action) {
    chips.push({ label: translateAction(result.action), variant: "good" });
  }
  if (result.summary?.verification_status) {
    chips.push({ label: translateVerificationStatus(result.summary.verification_status), variant: "emphasis" });
  }
  if (result.summary?.acquisition_mode) {
    chips.push({ label: translateAcquisitionMode(result.summary.acquisition_mode), variant: "" });
  }
  if (result.integrity?.status) {
    chips.push({ label: `完整性：${result.integrity.status}`, variant: result.integrity.status === "complete" ? "good" : "warn" });
  }
  if (result.atas_backfill_request?.status) {
    chips.push({ label: `补数：${result.atas_backfill_request.status}`, variant: "emphasis" });
  }
  return chips;
}

function renderGammaDrawer({ state, els }) {
  const gamma = state.optionsGamma || {};
  if (els.gammaCsvPath && document.activeElement !== els.gammaCsvPath) {
    els.gammaCsvPath.value = gamma.sourceCsvPath || "";
  }

  if (els.gammaSummaryContainer) {
    if (gamma.loading) {
      els.gammaSummaryContainer.innerHTML = `<div class="info-card"><h4>Gamma 分析</h4><p>加载中…</p></div>`;
    } else if (gamma.error) {
      els.gammaSummaryContainer.innerHTML = `<div class="info-card"><h4>Gamma 分析失败</h4><p>${escapeHtml(gamma.error)}</p></div>`;
    } else if (gamma.summary) {
      const summary = gamma.summary;
      const resistance = Array.isArray(summary.resistance_levels) ? summary.resistance_levels.slice(0, 3) : [];
      const support = Array.isArray(summary.support_levels) ? summary.support_levels.slice(0, 3) : [];
      els.gammaSummaryContainer.innerHTML = `
        <div class="drawer-card-grid">
          <div class="info-card">
            <h4>来源</h4>
            <p>${escapeHtml(gamma.sourceCsvPath || summary.source_file || "-")}</p>
            <p>${escapeHtml(summary.quote_time || gamma.lastLoadedAt || "-")}</p>
          </div>
          <div class="info-card">
            <h4>环境</h4>
            <p>Regime：${escapeHtml(summary.regime || "-")}</p>
            <p>Zero Gamma：${summary.zero_gamma_proxy ?? "-"}</p>
          </div>
          <div class="info-card">
            <h4>支撑 / 阻力</h4>
            <p>支撑：${escapeHtml(support.map((item) => item.es_equivalent ?? item.strike).join(" / ") || "-")}</p>
            <p>阻力：${escapeHtml(resistance.map((item) => item.es_equivalent ?? item.strike).join(" / ") || "-")}</p>
          </div>
        </div>
        ${gamma.textReport ? `<pre class="summary-preview">${escapeHtml(gamma.textReport)}</pre>` : ""}
      `;
    } else {
      els.gammaSummaryContainer.innerHTML = `<div class="empty-note">尚未加载 Gamma 分析。</div>`;
    }
  }

  if (els.gammaMapContainer) {
    if (gamma.artifacts?.svg_content) {
      els.gammaMapContainer.innerHTML = `
        <div class="info-card">
          <h4>Gamma Map</h4>
          <div class="gamma-map-shell">${gamma.artifacts.svg_content}</div>
          ${gamma.artifacts.svg_path ? `<p class="mono">SVG: ${escapeHtml(gamma.artifacts.svg_path)}</p>` : ""}
        </div>
      `;
    } else {
      els.gammaMapContainer.innerHTML = `<div class="empty-note">暂无 Gamma map。</div>`;
    }
  }

  if (els.gammaAiContainer) {
    if (gamma.aiInterpretation || gamma.aiAnalysisError) {
      els.gammaAiContainer.innerHTML = `
        <div class="info-card">
          <h4>AI 解读</h4>
          ${gamma.aiInterpretation ? `<pre class="summary-preview">${escapeHtml(gamma.aiInterpretation)}</pre>` : ""}
          ${gamma.aiAnalysisError ? `<p>AI 解读失败：${escapeHtml(gamma.aiAnalysisError)}</p>` : ""}
        </div>
      `;
    } else {
      els.gammaAiContainer.innerHTML = `<div class="empty-note">暂无 AI 解读。</div>`;
    }
  }

  if (els.gammaLoadButton) {
    els.gammaLoadButton.disabled = !!gamma.loading;
    els.gammaLoadButton.textContent = gamma.loading ? "加载中…" : "加载 / 刷新 Gamma";
  }
}

function renderDrawers({ state, els }) {
  const snapshot = state.snapshot;
  els.drawerContextPanel.innerHTML = snapshot
    ? `
      <div class="drawer-card-grid">
        <div class="info-card"><h4>回放上下文</h4><p>品种：${snapshot.instrument_symbol || state.topBar.symbol} / 周期：${timeframeLabel(snapshot.display_timeframe || state.topBar.timeframe)}</p></div>
        <div class="info-card"><h4>窗口</h4><p>${snapshot.window_start || "-"}<br>${snapshot.window_end || "-"}</p></div>
      </div>
    `
    : `<div class="empty-note">尚未加载图表，暂无上下文。</div>`;

  if (els.manualRegionList) {
    els.manualRegionList.innerHTML = state.manualRegions.length
      ? state.manualRegions.map((item) => `<div class="info-card compact-card"><h4>${item.label}</h4><p>${item.started_at} → ${item.ended_at}</p><p>${item.price_low} - ${item.price_high}</p></div>`).join("")
      : `<div class="empty-note">暂无手工区域。</div>`;
  }

  els.drawerFocusPanel.innerHTML = snapshot?.focus_regions?.length
    ? snapshot.focus_regions.map((item) => `<div class="info-card"><h4>${item.label}</h4><p>${item.price_low} - ${item.price_high}</p></div>`).join("")
    : `<div class="empty-note">暂无焦点区域。</div>`;

  els.drawerStrategyPanel.innerHTML = snapshot?.strategy_candidates?.length
    ? snapshot.strategy_candidates.map((item) => `<div class="info-card"><h4>${item.title || item.strategy_id}</h4><p>${summarizeText(item.thesis || item.summary || "", 180)}</p></div>`).join("")
    : `<div class="empty-note">暂无策略匹配结果。</div>`;

  if (els.operatorEntryList) {
    els.operatorEntryList.innerHTML = state.operatorEntries.length
      ? state.operatorEntries.map((item) => `<div class="info-card compact-card"><h4>${item.side === "buy" ? "多头开仓" : "空头开仓"}</h4><p>${item.executed_at}</p><p>${item.entry_price}</p></div>`).join("")
      : `<div class="empty-note">暂无开仓记录。</div>`;
  }

  els.drawerRecapPanel.innerHTML = state.aiReview
    ? `<div class="info-card"><h4>${state.aiReview.model || "AI复盘"}</h4><p>${summarizeText(state.aiReview.review || state.aiReview.reply_text || "", 600)}</p></div>`
    : `<div class="empty-note">暂无复盘简报。</div>`;

  renderGammaDrawer({ state, els });
}


export function bootReplayWorkbench({ renderChart, getRenderSnapshot, getBuildRequestPayload }) {
  const state = createWorkbenchState();
  const els = createWorkbenchElements(document);
  const { buildCacheKey, syncCacheKey, applyWindowPreset } = createCacheKeyHelpers({ els });
  const { ensureChartView } = createChartViewHelpers({ state });
  const renderStatusStrip = renderStatusStripFactory(els);
  const planLifecycleEngine = createPlanLifecycleEngine({ state });
  const sessionMemoryEngine = createSessionMemoryEngine({ state, els, fetchJson });

  function persistWorkbenchState() {
    writeStorage("workbench", {
      activeAiThreadId: state.activeAiThreadId,
      drawerState: state.drawerState,
      topBar: state.topBar,
      pinnedPlanId: state.pinnedPlanId,
    });
  }

  function formatSyncLabel(value) {
    if (!value) {
      return "最近同步：--";
    }
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) {
      return "最近同步：--";
    }
    return `最近同步：${date.toLocaleString("zh-CN", { hour12: false })}`;
  }

  function exportCurrentSettings() {
    const payload = {
      topBar: state.topBar,
      layout: state.layout,
      drawerState: state.drawerState,
      annotationFilters: state.annotationFilters,
      activeAiThreadId: state.activeAiThreadId,
      pinnedPlanId: state.pinnedPlanId,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `replay-workbench-settings-${Date.now()}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 300);
  }


  function jumpToMessage(messageId) {
    if (!messageId) {
      return;
    }
    scrollChatToBottom({ behavior: "auto", markRead: true, persist: false });
    const node = els.aiChatThread.querySelector(`[data-message-id="${messageId}"]`);
    if (!node) {
      return;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    const session = getActiveThread();
    session.autoFollowChat = false;
    session.hasUnreadChatBelow = false;
    session.scrollOffset = els.aiChatThread?.scrollTop || 0;
    node.classList.add("source-flash");
    window.setTimeout(() => node.classList.remove("source-flash"), 2200);
  }

  function getReplyAnnotations({ messageId, sessionId = null, planId = null } = {}) {
    return (state.aiAnnotations || []).filter((item) => {
      if (sessionId && item.session_id !== sessionId) return false;
      if (messageId && item.message_id === messageId) return true;
      if (planId && item.plan_id === planId) return true;
      return false;
    });
  }

  function syncMountedRepliesToServer(session, { messageId = null, mountedToChart = null, mountMode = "append", mountedObjectIds = [] } = {}) {
    if (!fetchJson || !session?.id) {
      return Promise.resolve();
    }
    return (async () => {
      try {
        await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mounted_reply_ids: Array.isArray(session.mountedReplyIds) ? session.mountedReplyIds : [],
          }),
        });
      } catch (error) {
        console.warn("同步 mounted replies 失败:", error);
      }
      if (!messageId || mountedToChart == null) {
        return;
      }
      try {
        await fetchJson(`/api/v1/workbench/chat/messages/${encodeURIComponent(messageId)}/mount`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mounted_to_chart: !!mountedToChart,
            mount_mode: mountMode,
            mounted_object_ids: Array.isArray(mountedObjectIds) ? mountedObjectIds : [],
          }),
        });
      } catch (error) {
        console.warn("同步回复挂载状态失败:", error);
      }
    })();
  }

  function syncPromptBlocksToServer(session, { selectedPromptBlockIds = null, pinnedContextBlockIds = null } = {}) {
    if (!fetchJson || !session?.id) {
      return Promise.resolve();
    }
    return fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_prompt_block_ids: Array.isArray(selectedPromptBlockIds) ? selectedPromptBlockIds : (Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : []),
        pinned_context_block_ids: Array.isArray(pinnedContextBlockIds) ? pinnedContextBlockIds : (Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : []),
      }),
    }).catch((error) => {
      console.warn("同步 prompt blocks 失败:", error);
    });
  }

  function mountReplyObjects(messageId, mode = "show", { sessionId = null, planId = null } = {}) {
    if (!messageId) {
      return [];
    }
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (!targetSession) {
      return [];
    }
    const mountedReplyIds = Array.isArray(targetSession.mountedReplyIds) ? targetSession.mountedReplyIds : [];
    if (mode === "replace") {
      targetSession.mountedReplyIds = [messageId];
    } else if (!mountedReplyIds.includes(messageId)) {
      targetSession.mountedReplyIds = [...mountedReplyIds, messageId];
    }
    const related = getReplyAnnotations({ messageId, sessionId: targetSession.id, planId });
    const mountedObjectIds = related.map((item) => item.id);
    targetSession.messages = (targetSession.messages || []).map((message) => {
      if (message.message_id !== messageId) {
        return mode === "replace"
          ? { ...message, mountedToChart: false, mountedObjectIds: [] }
          : message;
      }
      return {
        ...message,
        mountedToChart: true,
        mountedObjectIds,
      };
    });
    const mountMode = mode === "replace" ? "replace" : "append";
    void syncMountedRepliesToServer(targetSession, {
      messageId,
      mountedToChart: true,
      mountMode,
      mountedObjectIds,
    });
    queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    persistSessions();
    return mountedObjectIds;
  }

  function unmountReplyObjects(messageId, { sessionId = null } = {}) {
    if (!messageId) {
      return;
    }
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (!targetSession) {
      return;
    }
    targetSession.mountedReplyIds = (targetSession.mountedReplyIds || []).filter((id) => id !== messageId);
    targetSession.messages = (targetSession.messages || []).map((message) => message.message_id === messageId
      ? { ...message, mountedToChart: false, mountedObjectIds: [] }
      : message);
    void syncMountedRepliesToServer(targetSession, {
      messageId,
      mountedToChart: false,
      mountMode: "focus_only",
      mountedObjectIds: [],
    });
    queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    persistSessions();
  }

  function focusReplyObjects(messageId, { sessionId = null, planId = null, mode = "focus" } = {}) {
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    const related = getReplyAnnotations({ messageId, sessionId: targetSession?.id, planId });
    if (!related.length) {
      return [];
    }
    state.selectedAnnotationId = related[0].id;
    state.annotationFilters.onlyCurrentSession = false;
    state.annotationFilters.sessionIds = targetSession ? [targetSession.id] : [];
    state.annotationFilters.messageIds = messageId ? [messageId] : [];
    state.annotationFilters.annotationIds = mode === "focus" ? related.map((item) => item.id) : [];
    writeStorage("annotationFilters", state.annotationFilters);
    void syncMountedRepliesToServer(targetSession, {
      messageId,
      mountedToChart: true,
      mountMode: mode === "focus" ? "focus_only" : "append",
      mountedObjectIds: related.map((item) => item.id),
    });
    queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    return related;
  }

  function focusPlanOnChart({ action, planId, messageId, sessionId }) {
    const related = getReplyAnnotations({ messageId, sessionId, planId });
    if (action === "unmount") {
      unmountReplyObjects(messageId, { sessionId });
      if (messageId) {
        state.annotationFilters.annotationIds = (state.annotationFilters.annotationIds || []).filter((id) => {
          const annotation = state.aiAnnotations.find((item) => item.id === id);
          return annotation?.message_id !== messageId;
        });
      }
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
      return;
    }
    if (!related.length) {
      return;
    }
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (targetSession) {
      setActiveThread(targetSession.id, targetSession.title, {
        symbol: targetSession.symbol || targetSession.contractId || targetSession.memory?.symbol || state.topBar.symbol,
        contractId: targetSession.contractId || targetSession.symbol || targetSession.memory?.symbol || state.topBar.symbol,
        timeframe: targetSession.timeframe || targetSession.memory?.timeframe || state.topBar.timeframe,
        windowRange: targetSession.windowRange || targetSession.memory?.window_range || state.topBar.quickRange,
      });
    }
    state.selectedAnnotationId = related[0].id;
    const session = state.aiThreads.find((item) => item.id === (targetSession?.id || state.activeAiThreadId));
    if (session && messageId) {
      mountReplyObjects(messageId, action === "show" ? "show" : "replace", { sessionId: session.id, planId });
    }
    if (action === "focus") {
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "focus" });
    } else if (action === "show") {
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "show" });
    }
    writeStorage("annotationFilters", state.annotationFilters);
    if (action === "jump") {
      window.setTimeout(() => jumpToMessage(messageId), 60);
    }
    const candles = state.snapshot?.candles || [];
    const starts = related.map((item) => new Date(item.start_time || state.snapshot?.window_start).getTime()).filter(Number.isFinite);
    if (candles.length && starts.length) {
      const firstTime = Math.min(...starts);
      const centerIndex = Math.max(0, candles.findIndex((item) => new Date(item.started_at).getTime() >= firstTime));
      const span = Math.min(80, candles.length);
      state.chartView = clampChartView({
        startIndex: Math.max(0, centerIndex - Math.floor(span / 2)),
        endIndex: Math.min(candles.length - 1, centerIndex + Math.floor(span / 2)),
        yMin: state.chartView?.yMin,
        yMax: state.chartView?.yMax,
      }, candles.length);
    }
    persistSessions();
    renderSnapshot();
  }

  const threadController = createAiThreadController({
    state,
    els,
    onPlanAction: focusPlanOnChart,
    onMountedRepliesChanged: (session, nextIds) => {
      void syncMountedRepliesToServer(session);
      queueSessionMemoryRefresh([session.id], { forceServer: true, delay: 120 });
      if (Array.isArray(nextIds) && session.id === state.activeAiThreadId) {
        renderSnapshot();
      }
    },
    onPromptBlocksChanged: (session, { selectedPromptBlockIds, pinnedContextBlockIds } = {}) => {
      void syncPromptBlocksToServer(session, { selectedPromptBlockIds, pinnedContextBlockIds });
      if (session.id === state.activeAiThreadId) {
        renderAiChat();
      }
    },
    fetchJson,
    renderStatusStrip,
    onSessionActivated: () => renderSnapshot(),
  });
  const {
    ensureThread,
    getActiveThread,
    setActiveThread,
    syncSessionsFromServer,
    getOrCreateBlankSessionForSymbol,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    upsertPlanCardToSession,
    renameActiveThread,
    togglePinActiveThread,
    deleteActiveThread,
    addAttachments,
    clearAttachments,
    addPromptBlock,
    setMountedReplyIds,
    bindChatScrollBehavior,
    scrollChatToBottom,
    updateChatFollowState,
    persistSessions,
  } = threadController;

  const replayLoader = createReplayLoader({
    state,
    els,
    fetchJson,
    ensureThread,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
  });

  const actions = createWorkbenchActions({
    state,
    els,
    fetchJson,
    toUtcString: (value) => value ? new Date(value).toISOString() : null,
    syncCacheKey,
    renderStatusStrip,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    renderError: (error) => renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]),
    renderAiError: (error) => renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]),
    setBuildProgress: (active, percent, label) => {
      els.buildProgress.classList.toggle("active", !!active);
      els.buildProgressFill.style.width = `${percent || 0}%`;
      els.buildProgressPercent.textContent = `${percent || 0}%`;
      els.buildProgressLabel.textContent = label || "正在加载历史数据";
    },
    buildRequestPayload: (...args) => getBuildRequestPayload()(...args),
    buildStatusChips,
    translateVerificationStatus,
    loadSnapshotByIngestionId: replayLoader.loadSnapshotByIngestionId,
  });

  const aiChat = createAiChatController({
    state,
    els,
    fetchJson,
    renderStatusStrip,
    getActiveThread,
    setActiveThread,
    appendAiChatMessage,
    getPresetThreadMeta,
    createThreadId,
    upsertPlanCardToSession,
    persistSessions,
    sessionMemoryEngine,
    addPromptBlock,
    getOrCreateBlankSessionForSymbol,
    setMountedReplyIds,
  });
  aiChat.bindStreamingControls?.();
  const annotationPanelController = createAnnotationPanelController({
    state,
    els,
    persistWorkbenchState,
    setActiveThread,
    renderSnapshot: () => renderSnapshot(),
    jumpToMessage,
  });
  const annotationPopoverController = createAnnotationPopoverController({
    state,
    els,
    setActiveThread,
    renderSnapshot: () => renderSnapshot(),
    jumpToMessage,
  });
  const modelSwitcherController = createModelSwitcherController({
    state,
    els,
    getActiveThread,
    appendAiChatMessage,
    persistSessions,
    sessionMemoryEngine,
    renderSnapshot: () => renderSnapshot(),
  });

  function applyLayoutWidths() {
    els.chartWorkspace.style.minWidth = "0";
    els.chartWorkspace.style.width = `${state.layout.chartWidth}px`;
    els.rightPanel.style.width = `${state.layout.chatWidth}px`;
    els.aiChatThread.style.height = `${state.layout.chatHeight}px`;
    writeStorage("layout", state.layout);
    window.requestAnimationFrame(() => updateChatFollowState({ persist: false }));
  }

  function updateHeaderStatus() {
    state.topBar.symbol = els.instrumentSymbol.value.trim() || "NQ";
    state.topBar.timeframe = els.displayTimeframe.value;
    state.topBar.quickRange = els.quickRangeSelect.value;
    els.statusSymbolChip.textContent = state.topBar.symbol;
    els.statusTimeframeChip.textContent = timeframeLabel(state.topBar.timeframe);
    els.statusWindowChip.textContent = els.quickRangeSelect.options[els.quickRangeSelect.selectedIndex]?.text || "自定义";
    els.statusDataChip.textContent = `数据状态：${state.snapshot?.live_tail ? "实时" : state.snapshot ? "历史" : "未加载"}`;
    els.statusSyncChip.textContent = formatSyncLabel(state.topBar.lastSyncedAt);
    persistWorkbenchState();
  }


  function updateAnnotationLifecycle() {
    return planLifecycleEngine.updateAnnotationLifecycle();
  }

  let pendingMemoryRefreshTimer = null;
  const memoryRefreshQueue = new Set();

  function queueSessionMemoryRefresh(sessionIds = [], { forceServer = true, delay = 220 } = {}) {
    if (!sessionMemoryEngine?.refreshSessionMemory) {
      return;
    }
    (Array.isArray(sessionIds) ? sessionIds : [sessionIds]).filter(Boolean).forEach((id) => memoryRefreshQueue.add(id));
    if (!memoryRefreshQueue.size) {
      return;
    }
    if (pendingMemoryRefreshTimer) {
      clearTimeout(pendingMemoryRefreshTimer);
    }
    pendingMemoryRefreshTimer = window.setTimeout(async () => {
      const targetIds = Array.from(memoryRefreshQueue);
      memoryRefreshQueue.clear();
      pendingMemoryRefreshTimer = null;
      await Promise.all(targetIds.map(async (sessionId) => {
        const session = state.aiThreads.find((item) => item.id === sessionId || item.sessionId === sessionId);
        if (!session) {
          return;
        }
        try {
          await sessionMemoryEngine.refreshSessionMemory(session, { forceServer });
        } catch (error) {
          console.warn("刷新会话记忆失败:", error);
        }
      }));
      persistSessions();
      if (targetIds.includes(state.activeAiThreadId)) {
        renderAiThreadTabs();
        renderAiChat();
      }
    }, delay);
  }

  function updateDynamicAnalysisVisibility() {
    const hasManualRegions = !!state.manualRegions.length;
    const hasSelectedBar = state.selectedCandleIndex != null || state.selectedFootprintBar != null;
    const hasEntries = !!state.operatorEntries.length;
    const hasLiveDepth = !!state.snapshot?.live_tail;
    Array.from(els.analysisTypeSelect.options).forEach((option) => {
      const hidden = (option.value === "manual_region" && !hasManualRegions)
        || (option.value === "selected_bar" && !hasSelectedBar)
        || (option.value === "entry_review" && !hasEntries)
        || (option.value === "live_depth" && !hasLiveDepth);
      option.hidden = hidden;
    });
    Array.from(els.analysisRangeSelect.options).forEach((option) => {
      const hidden = (option.value === "selected_region" && !hasManualRegions)
        || (option.value === "selected_bar" && !hasSelectedBar)
        || (option.value === "latest_entry" && !hasEntries);
      option.hidden = hidden;
    });
  }

  let liveRefreshInterval = null;

  function getMaxBarsForTimeframe(timeframe) {
    const minutesByTimeframe = {
      "1m": 1,
      "5m": 5,
      "15m": 15,
      "30m": 30,
      "1h": 60,
      "1d": 1440,
    };
    const timeframeMinutes = minutesByTimeframe[timeframe] || 1;
    return Math.max(1, Math.ceil((7 * 24 * 60) / timeframeMinutes));
  }

  function mergeLiveTailIntoSnapshot(response, timeframe) {
    if (!state.snapshot?.candles?.length || !response?.candles?.length) {
      return false;
    }
    const existingCandles = Array.isArray(state.snapshot.candles) ? [...state.snapshot.candles] : [];
    const latestFromServer = response.candles[response.candles.length - 1];
    const lastExisting = existingCandles[existingCandles.length - 1];
    if (!lastExisting) {
      state.snapshot.candles = response.candles.slice();
      return true;
    }
    if (latestFromServer.started_at === lastExisting.started_at) {
      existingCandles[existingCandles.length - 1] = latestFromServer;
      state.snapshot.candles = existingCandles;
      return true;
    }
    if (new Date(latestFromServer.started_at) > new Date(lastExisting.started_at)) {
      existingCandles.push(latestFromServer);
      const maxBars = getMaxBarsForTimeframe(timeframe);
      state.snapshot.candles = existingCandles.slice(-maxBars);
      return true;
    }
    return false;
  }

  function startLiveRefresh() {
    if (liveRefreshInterval) {
      clearInterval(liveRefreshInterval);
    }
    liveRefreshInterval = setInterval(async () => {
      if (!state.followLatest || !state.snapshot?.candles?.length || state.buildInFlight) {
        return;
      }
      try {
        const symbol = els.instrumentSymbol?.value?.trim();
        const timeframe = els.displayTimeframe?.value;
        if (!symbol || !timeframe) return;

        const response = await fetchJson(`/api/v1/workbench/live-tail?instrument_symbol=${encodeURIComponent(symbol)}&display_timeframe=${encodeURIComponent(timeframe)}&lookback_bars=4`);
        const integrityHash = response?.integrity ? JSON.stringify(response.integrity) : null;
        const integrityChanged = integrityHash !== state.lastLiveTailIntegrityHash;
        state.integrity = response?.integrity || state.integrity;
        state.pendingBackfill = response?.latest_backfill_request || state.pendingBackfill;
        state.lastLiveTailIntegrityHash = integrityHash;

        if (response?.snapshot_refresh_required && state.currentReplayIngestionId) {
          await replayLoader.loadSnapshotByIngestionId(state.currentReplayIngestionId);
          return;
        }
        if (integrityChanged && state.currentReplayIngestionId) {
          await replayLoader.loadSnapshotByIngestionId(state.currentReplayIngestionId);
          return;
        }
        if (mergeLiveTailIntoSnapshot(response, timeframe)) {
          renderChart();
          const latestFromServer = response.candles?.[response.candles.length - 1];
          if (els.chartInfoTime && latestFromServer?.ended_at) {
            const lastTime = new Date(latestFromServer.ended_at);
            els.chartInfoTime.textContent = "UTC " + lastTime.toISOString().slice(0, 19).replace("T", " ");
          }
          if (els.statusDataChip) {
            els.statusDataChip.textContent = `数据状态：实时`;
          }
        }
      } catch (error) {
        console.warn("实时刷新失败:", error);
      }
    }, 5000);
  }

  function renderSnapshot() {
    const changedSessionIds = updateAnnotationLifecycle();
    if (changedSessionIds?.length) {
      queueSessionMemoryRefresh(changedSessionIds, { forceServer: true, delay: 260 });
    }
    renderChart();
    renderAiThreadTabs();
    renderAiChat();
    renderContractNav();
    renderDrawers({ state, els });
    annotationPanelController.renderAnnotationPanel();
    updateDynamicAnalysisVisibility();
    updateHeaderStatus();
    // 启动实时刷新
    if (state.snapshot?.candles?.length) {
      startLiveRefresh();
    }
  }

  async function handleBuildWithForceRefresh() {
    const previous = !!els.forceRebuild?.checked;
    if (els.forceRebuild) {
      els.forceRebuild.checked = true;
    }
    try {
      await actions.handleBuild();
      state.topBar.lastSyncedAt = new Date().toISOString();
      persistWorkbenchState();
      renderSnapshot();
    } finally {
      if (els.forceRebuild) {
        els.forceRebuild.checked = previous;
      }
    }
  }

  async function loadGammaAnalysis({ autoDiscoverLatest = false } = {}) {
    const gamma = state.optionsGamma;
    gamma.loading = true;
    gamma.error = null;
    if (els.gammaCsvPath && els.gammaCsvPath.value.trim()) {
      gamma.sourceCsvPath = els.gammaCsvPath.value.trim();
    }
    renderSnapshot();
    try {
      if (autoDiscoverLatest) {
        const latest = await fetchJson(`/api/v1/options/latest-csv?symbol=${encodeURIComponent(gamma.requestedSymbol || "SPX")}`);
        gamma.sourceCsvPath = latest.csv_path || "";
        gamma.discoveredAt = new Date().toISOString();
        if (els.gammaCsvPath) {
          els.gammaCsvPath.value = gamma.sourceCsvPath;
        }
      }
      const response = await fetchJson("/api/v1/options/gamma-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: gamma.requestedSymbol || "SPX",
          trade_date: gamma.requestedTradeDate,
          csv_path: gamma.sourceCsvPath || null,
          auto_discover_latest: !gamma.sourceCsvPath,
          include_ai_analysis: true,
          persist_artifacts: false,
        }),
      });
      gamma.summary = response.summary || null;
      gamma.textReport = response.text_report || "";
      gamma.artifacts = response.artifacts || null;
      gamma.aiInterpretation = response.ai_interpretation || "";
      gamma.aiAnalysisError = response.ai_analysis_error || null;
      gamma.sourceCsvPath = response.source?.csv_path || gamma.sourceCsvPath || "";
      gamma.lastLoadedAt = response.generated_at || new Date().toISOString();
      renderStatusStrip([{ label: "Gamma 已加载", variant: "good" }]);
    } catch (error) {
      gamma.error = error.message || String(error);
      renderStatusStrip([{ label: gamma.error, variant: "warn" }]);
    } finally {
      gamma.loading = false;
      renderSnapshot();
    }
  }

  function buildGammaPromptText() {
    const gamma = state.optionsGamma;
    if (!gamma?.summary) {
      throw new Error("还没有可发送的 Gamma 分析。");
    }
    const parts = [
      `以下是当前期权 Gamma 分析背景，请结合它回答后续问题。`,
      `来源 CSV: ${gamma.sourceCsvPath || gamma.summary.source_file || "-"}`,
      gamma.summary.quote_time ? `报价时间: ${gamma.summary.quote_time}` : "",
      gamma.summary.regime ? `Gamma 环境: ${gamma.summary.regime}` : "",
      gamma.summary.zero_gamma_proxy_es != null ? `Zero Gamma ES: ${gamma.summary.zero_gamma_proxy_es}` : "",
      gamma.textReport ? `\nSummary:\n${gamma.textReport}` : "",
      gamma.aiInterpretation ? `\nAI 解读:\n${gamma.aiInterpretation}` : "",
    ].filter(Boolean);
    return parts.join("\n");
  }

  async function sendGammaToChat(createNew = false) {
    const prompt = buildGammaPromptText();
    if (createNew) {
      await aiChat.handlePresetAnalysis("general", prompt, true);
      return;
    }
    els.aiChatInput.value = prompt;
    await aiChat.handleAiChatSend();
  }

  function resetAnnotationFilters() {
    state.annotationFilters = {
      onlyCurrentSession: true,
      hideCompleted: true,
      sessionIds: [],
      messageIds: [],
      annotationIds: [],
      objectTypes: ["entry_line", "stop_loss", "take_profit", "support_zone", "resistance_zone", "no_trade_zone"],
      showPaths: false,
      showInvalidated: false,
      selectedOnly: false,
    };
    writeStorage("annotationFilters", state.annotationFilters);
    renderSnapshot();
  }


  function toggleAiSidebar() {
    const isOpen = els.aiSidebar?.classList.contains("open");
    if (isOpen) {
      closeAiSidebar();
    } else {
      openAiSidebar();
    }
  }

  function openAiSidebar() {
    if (!els.aiSidebar) return;
    els.aiSidebar.classList.add("open");
    els.workbenchMain?.classList.add("ai-sidebar-open");
    els.aiSidebarTrigger?.classList.add("hidden");
    state.aiSidebarOpen = true;
    writeStorage("aiSidebarState", { open: true });
  }

  function closeAiSidebar() {
    if (!els.aiSidebar) return;
    els.aiSidebar.classList.remove("open");
    els.workbenchMain?.classList.remove("ai-sidebar-open");
    els.aiSidebarTrigger?.classList.remove("hidden");
    state.aiSidebarOpen = false;
    writeStorage("aiSidebarState", { open: false });
  }

  function renderContractNav() {
    if (!els.aiContractNav) return;
    const contracts = new Map();
    state.aiThreads.forEach((thread) => {
      const symbol = thread.symbol || thread.contractId || thread.memory?.symbol || state.topBar.symbol || "NQ";
      if (!contracts.has(symbol)) {
        contracts.set(symbol, {
          symbol,
          threads: [],
          active: false,
        });
      }
      contracts.get(symbol).threads.push(thread);
      if (thread.id === state.activeAiThreadId) {
        contracts.get(symbol).active = true;
      }
    });
    const contractArray = Array.from(contracts.values()).sort((a, b) => {
      if (a.active) return -1;
      if (b.active) return 1;
      return a.symbol.localeCompare(b.symbol);
    });
    els.aiContractNav.innerHTML = contractArray.map((contract) => {
      const unreadCount = contract.threads.reduce((sum, t) => sum + (t.unreadCount || 0), 0);
      const threadCount = contract.threads.length;
      return `
        <div class="ai-contract-card ${contract.active ? "active" : ""}" 
             data-contract-symbol="${contract.symbol}" 
             title="${contract.symbol} (${threadCount}个会话)">
          <div class="ai-contract-symbol">${contract.symbol}</div>
          ${unreadCount > 0 ? `<div class="ai-contract-badge">${unreadCount > 9 ? "9+" : unreadCount}</div>` : ""}
        </div>
      `;
    }).join("");
    els.aiContractNav.querySelectorAll(".ai-contract-card").forEach((card) => {
      card.addEventListener("click", () => {
        const symbol = card.dataset.contractSymbol;
        const contract = contractArray.find((c) => c.symbol === symbol);
        if (contract && contract.threads.length > 0) {
          const firstThread = contract.threads[0];
          setActiveThread(firstThread.id, firstThread.title);
          renderSnapshot();
        }
      });
    });
  }

  function initializeSkillPanel() {
    if (!els.aiSkillPanel || !els.aiSkillGrid) return;
    const skills = [
      { id: "kline_analysis", name: "K线分析", icon: "📊", prompt: "请分析当前K线图表并给出交易建议" },
      { id: "recent_bars", name: "最近20根K线", icon: "📈", prompt: "请分析最近20根K线并给出交易计划" },
      { id: "focus_regions", name: "重点区域", icon: "🎯", prompt: "请围绕当前重点区域给出计划" },
      { id: "live_depth", name: "实时挂单", icon: "📋", prompt: "请结合当前盘口结构给出建议" },
      { id: "manual_region", name: "手工区域", icon: "✏️", prompt: "请围绕手工区域做标准分析" },
      { id: "selected_bar", name: "选中K线", icon: "🔍", prompt: "请分析当前选中K线" },
    ];
    els.aiSkillGrid.innerHTML = skills.map((skill) => `
      <div class="ai-skill-card" data-skill-id="${skill.id}">
        <div class="ai-skill-icon">${skill.icon}</div>
        <div class="ai-skill-name">${skill.name}</div>
      </div>
    `).join("");
    els.aiSkillGrid.querySelectorAll(".ai-skill-card").forEach((card) => {
      card.addEventListener("click", () => {
        const skillId = card.dataset.skillId;
        const skill = skills.find((s) => s.id === skillId);
        if (skill) {
          els.aiChatInput.value = skill.prompt;
          els.aiSkillPanel.hidden = true;
          aiChat.handleAiChatSend();
          renderSnapshot();
        }
      });
    });
    if (els.aiSkillSearch) {
      els.aiSkillSearch.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();
        els.aiSkillGrid.querySelectorAll(".ai-skill-card").forEach((card) => {
          const name = card.querySelector(".ai-skill-name").textContent.toLowerCase();
          card.style.display = name.includes(query) ? "flex" : "none";
        });
      });
    }
  }

  function attachBindings() {
    applyLayoutWidths();
    bindChatScrollBehavior();

    // AI 侧边栏控制
    els.aiSidebarTrigger?.addEventListener("click", toggleAiSidebar);
    els.aiSidebarCloseButton?.addEventListener("click", closeAiSidebar);
    els.aiSidebarPinButton?.addEventListener("click", () => {
      state.aiSidebarPinned = !state.aiSidebarPinned;
      writeStorage("aiSidebarState", { pinned: state.aiSidebarPinned });
    });
    
    // 技能面板控制
    els.aiChatInput?.addEventListener("input", (e) => {
      const value = e.target.value;
      if (value.startsWith("@") || value.startsWith("/")) {
        els.aiSkillPanel.hidden = false;
      } else if (els.aiSkillPanel && !els.aiSkillPanel.hidden) {
        els.aiSkillPanel.hidden = true;
      }
    });
    
    // 快速操作按钮
    els.aiKlineAnalysisButton?.addEventListener("click", () => {
      aiChat.handlePresetAnalysis("recent_20_bars", "请分析当前K线图表并给出交易建议。", false);
      renderSnapshot();
    });
    
    // 初始化技能面板
    initializeSkillPanel();
    
    // 恢复侧边栏状态
    const sidebarState = readStorage("aiSidebarState", { open: false });
    if (sidebarState.open) {
      openAiSidebar();
    }
    els.timeframeTabs.forEach((button) => {
      button.addEventListener("click", () => {
        els.displayTimeframe.value = button.dataset.timeframe;
        els.timeframeTabs.forEach((item) => item.classList.toggle("active", item === button));
        syncCacheKey();
        updateHeaderStatus();
      });
    });
    els.displayTimeframe.addEventListener("change", () => {
      els.timeframeTabs.forEach((item) => item.classList.toggle("active", item.dataset.timeframe === els.displayTimeframe.value));
      syncCacheKey();
      updateHeaderStatus();
    });
    els.quickRangeSelect.addEventListener("change", () => {
      const preset = state.quickRanges.find((item) => item.value === els.quickRangeSelect.value);
      if (preset?.days) {
        applyWindowPreset(els.displayTimeframe.value, preset.days);
      }
      updateHeaderStatus();
    });
    els.instrumentSymbol.addEventListener("change", async () => {
      const nextSymbol = (els.instrumentSymbol.value || "").trim().toUpperCase() || "NQ";
      els.instrumentSymbol.value = nextSymbol;
      syncCacheKey();
      updateHeaderStatus();
      try {
        await syncSessionsFromServer({ symbol: nextSymbol, activateFirst: true });
        const matching = state.aiThreads.find((thread) => (thread.symbol || thread.memory?.symbol || "").toUpperCase() === nextSymbol);
        if (matching) {
          setActiveThread(matching.id, matching.title, matching);
        } else {
          await getOrCreateBlankSessionForSymbol(nextSymbol, nextSymbol);
        }
      } catch (error) {
        console.warn("切换品种同步会话失败:", error);
        await getOrCreateBlankSessionForSymbol(nextSymbol, nextSymbol);
      }
      // 切换品种时重新加载图表
      handleBuildWithForceRefresh();
    });
    
    // 启动时获取合约列表
    async function loadInstrumentsList() {
      try {
        const response = await fetchJson("/api/v1/workbench/instruments");
        if (response?.instruments?.length) {
          // 更新 datalist 选项
          let datalist = document.getElementById("symbolOptions");
          if (!datalist) {
            datalist = document.createElement("datalist");
            datalist.id = "symbolOptions";
            els.instrumentSymbol.setAttribute("list", "symbolOptions");
            els.instrumentSymbol.parentNode.appendChild(datalist);
          }
          datalist.innerHTML = response.instruments.map(s => `<option value="${s}">`).join("");
          
          // 如果当前品种不在列表中，添加到开头
          const currentSymbol = els.instrumentSymbol.value.trim().toUpperCase();
          if (currentSymbol && !response.instruments.includes(currentSymbol)) {
            const option = document.createElement("option");
            option.value = currentSymbol;
            datalist.prepend(option);
          }
        }
      } catch (error) {
        console.warn("获取合约列表失败:", error);
      }
    }
    loadInstrumentsList();
    els.windowStart.addEventListener("change", syncCacheKey);
    els.windowEnd.addEventListener("change", syncCacheKey);

    els.headerMoreButton?.addEventListener("click", () => {
      els.headerMoreMenu.hidden = !els.headerMoreMenu.hidden;
    });
    els.lookupCacheButton?.addEventListener("click", () => {
      openCacheViewer();
    });
    els.closeCacheViewerButton?.addEventListener("click", () => {
      els.cacheViewerModal.classList.add("is-hidden");
    });
    els.refreshCacheViewerButton?.addEventListener("click", () => {
      updateCacheViewer();
    });
    els.invalidateCacheButton?.addEventListener("click", () => {
      state.snapshot = null;
      state.currentReplayIngestionId = null;
      state.topBar.lastSyncedAt = null;
      els.chartSvg.innerHTML = "";
      renderStatusStrip([{ label: "缓存已重置", variant: "warn" }]);
      persistWorkbenchState();
      renderSnapshot();
    });
    els.exportSettingsButton?.addEventListener("click", () => {
      exportCurrentSettings();
      els.headerMoreMenu.hidden = true;
    });

    function openCacheViewer() {
      els.cacheViewerModal.classList.remove("is-hidden");
      updateCacheViewer();
      els.headerMoreMenu.hidden = true;
      const handleEsc = (e) => {
        if (e.key === "Escape") {
          els.cacheViewerModal.classList.add("is-hidden");
          document.removeEventListener("keydown", handleEsc);
        }
      };
      document.addEventListener("keydown", handleEsc);
      const handleBackgroundClick = (e) => {
        if (e.target === els.cacheViewerModal) {
          els.cacheViewerModal.classList.add("is-hidden");
          els.cacheViewerModal.removeEventListener("click", handleBackgroundClick);
          document.removeEventListener("keydown", handleEsc);
        }
      };
      els.cacheViewerModal.addEventListener("click", handleBackgroundClick);
    }

    function updateCacheViewer() {
      els.cacheViewerKey.textContent = els.cacheKey.value || "-";
      els.cacheViewerIngestionId.textContent = state.currentReplayIngestionId || "-";
      els.cacheViewerSnapshotStatus.textContent = state.snapshot ? "已加载" : "未加载";
      els.cacheViewerSnapshotStatus.style.color = state.snapshot ? "var(--green)" : "var(--text-soft)";
      
      if (state.snapshot) {
        const details = {
          instrument_symbol: state.snapshot.instrument_symbol || "-",
          display_timeframe: state.snapshot.display_timeframe || "-",
          window_start: state.snapshot.window_start || "-",
          window_end: state.snapshot.window_end || "-",
          candle_count: state.snapshot.candles?.length || 0,
          event_annotation_count: state.snapshot.event_annotations?.length || 0,
          focus_region_count: state.snapshot.focus_regions?.length || 0,
          strategy_candidate_count: state.snapshot.strategy_candidates?.length || 0,
          live_tail: state.snapshot.live_tail || false,
        };
        els.cacheViewerDetails.style.display = "block";
        els.cacheViewerDetailsJson.textContent = JSON.stringify(details, null, 2);
      } else {
        els.cacheViewerDetails.style.display = "none";
      }
    }

    els.buildButton.addEventListener("click", async () => {
      await actions.handleBuild();
      state.topBar.lastSyncedAt = new Date().toISOString();
      persistWorkbenchState();
      renderSnapshot();
    });
    els.refreshAllButton.addEventListener("click", async () => {
      await actions.handleBuild();
      state.topBar.lastSyncedAt = new Date().toISOString();
      persistWorkbenchState();
      renderSnapshot();
    });
    els.restoreLayoutButton.addEventListener("click", () => {
      const persistedLayout = readStorage("layout", null);
      if (persistedLayout) {
        state.layout = { ...state.layout, ...persistedLayout };
      }
      applyLayoutWidths();
      renderSnapshot();
    });

    els.aiNewThreadButton.addEventListener("click", () => {
      aiChat.createNewThread();
      renderSnapshot();
    });
    els.aiChatSendButton.addEventListener("click", async () => {
      await aiChat.handleAiChatSend();
      renderSnapshot();
    });
    els.aiChatInput.addEventListener("input", (event) => aiChat.handleComposerInput(event.target.value));
    els.aiChatInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await aiChat.handleAiChatSend();
        renderSnapshot();
      }
    });
    els.saveRegionButton?.addEventListener("click", async () => {
      await actions.handleSaveRegion();
      renderSnapshot();
    });
    els.recordEntryButton?.addEventListener("click", async () => {
      await actions.handleRecordEntry();
      renderSnapshot();
    });

    els.aiChatThread?.addEventListener("click", async (event) => {
      const button = event.target?.closest("button[data-message-action='regenerate']");
      if (!button) {
        return;
      }
      const messageId = button.dataset.messageId;
      if (!messageId) {
        return;
      }
      await aiChat.regenerateMessage(messageId);
      renderSnapshot();
    });

    els.analysisSendCurrentButton.addEventListener("click", async () => {
      const session = getActiveThread();
      session.analysisTemplate = {
        type: els.analysisTypeSelect.value,
        range: els.analysisRangeSelect.value,
        style: els.analysisStyleSelect.value,
        sendMode: "current",
      };
      persistSessions();
      await aiChat.handlePresetAnalysis(els.analysisTypeSelect.value, `请基于当前${els.analysisRangeSelect.value}做${els.analysisStyleSelect.value}风格分析。`, false);
      renderSnapshot();
    });
    els.analysisSendNewButton.addEventListener("click", async () => {
      await aiChat.handlePresetAnalysis(els.analysisTypeSelect.value, `请基于当前${els.analysisRangeSelect.value}做${els.analysisStyleSelect.value}风格分析。`, true);
      renderSnapshot();
    });
    els.gammaAutoDiscoverButton?.addEventListener("click", async () => {
      await loadGammaAnalysis({ autoDiscoverLatest: true });
    });
    els.gammaLoadButton?.addEventListener("click", async () => {
      await loadGammaAnalysis({ autoDiscoverLatest: false });
    });
    els.gammaSendCurrentButton?.addEventListener("click", async () => {
      await sendGammaToChat(false);
      renderSnapshot();
    });
    els.gammaSendNewButton?.addEventListener("click", async () => {
      await sendGammaToChat(true);
      renderSnapshot();
    });

    els.recent20BarsButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("recent_20_bars", "请分析最近20根K线并给出交易计划。", false));
    els.recent20MinutesButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("recent_20_minutes", "请分析最近20分钟并给出交易计划。", false));
    els.focusRegionsButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("focus_regions", "请围绕当前重点区域给出计划。", false));
    els.liveDepthButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("live_depth", "请结合当前盘口结构给出建议。", false));
    els.manualRegionButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("manual_region", aiChat.buildManualRegionAnalysisPrompt(), false));
    els.selectedBarButton.addEventListener("click", async () => aiChat.handlePresetAnalysis("selected_bar", aiChat.buildSelectedBarAnalysisPrompt(), false));

    els.annotationManagerButton.addEventListener("click", () => {
      state.annotationPanelOpen = true;
      renderSnapshot();
    });
    els.toggleAnnotationPanelButton.addEventListener("click", () => {
      state.annotationPanelOpen = !state.annotationPanelOpen;
      renderSnapshot();
    });
    els.closeAnnotationPanelButton.addEventListener("click", () => {
      state.annotationPanelOpen = false;
      renderSnapshot();
    });
    els.filterOnlyCurrentSession.addEventListener("change", () => {
      state.annotationFilters.onlyCurrentSession = els.filterOnlyCurrentSession.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterHideCompleted.addEventListener("change", () => {
      state.annotationFilters.hideCompleted = els.filterHideCompleted.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterShowPaths?.addEventListener("change", () => {
      state.annotationFilters.showPaths = els.filterShowPaths.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterShowInvalidated?.addEventListener("change", () => {
      state.annotationFilters.showInvalidated = els.filterShowInvalidated.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationShowSelectedOnlyButton?.addEventListener("click", () => {
      state.annotationFilters.selectedOnly = true;
      state.annotationFilters.annotationIds = state.selectedAnnotationId ? [state.selectedAnnotationId] : [];
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationHideAllButton?.addEventListener("click", () => {
      state.annotationFilters.onlyCurrentSession = false;
      state.annotationFilters.sessionIds = [];
      state.annotationFilters.messageIds = [];
      state.annotationFilters.annotationIds = ["__none__"];
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationShowPinnedButton?.addEventListener("click", () => {
      state.annotationFilters.onlyCurrentSession = false;
      state.annotationFilters.sessionIds = [];
      state.annotationFilters.messageIds = [];
      state.annotationFilters.annotationIds = state.aiAnnotations.filter((item) => item.pinned).map((item) => item.id);
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationFilterResetButton.addEventListener("click", resetAnnotationFilters);

    els.sessionRenameButton?.addEventListener("click", () => {
      const nextTitle = window.prompt("输入会话名称", getActiveThread().title);
      if (nextTitle && nextTitle.trim()) {
        renameActiveThread(nextTitle.trim());
        renderSnapshot();
      }
    });
    els.sessionPinButton?.addEventListener("click", () => {
      togglePinActiveThread();
      renderSnapshot();
    });
    els.sessionDeleteButton?.addEventListener("click", () => {
      if (window.confirm("确认删除当前会话？")) {
        deleteActiveThread();
        renderSnapshot();
      }
    });
    els.sessionMoreButton?.addEventListener("click", () => {
      els.sessionMoreMenu.hidden = !els.sessionMoreMenu.hidden;
    });
    els.clearPinnedPlanButton?.addEventListener("click", () => {
      state.pinnedPlanId = null;
      const session = getActiveThread();
      session.activePlanId = null;
      persistSessions();
      renderSnapshot();
    });

    els.addAttachmentButton?.addEventListener("click", () => els.attachmentInput?.click());
    els.attachmentInput?.addEventListener("change", async () => {
      const files = Array.from(els.attachmentInput.files || []);
      const mapped = await Promise.all(files.map(async (file) => ({
        name: file.name,
        kind: file.type || "file",
        size: file.size,
      })));
      addAttachments(mapped);
      els.attachmentInput.value = "";
      renderSnapshot();
    });
    els.chartScreenshotButton?.addEventListener("click", () => {
      addAttachments([{ name: `chart-${Date.now()}.png`, kind: "chart-screenshot" }]);
      renderSnapshot();
    });
    els.externalScreenshotButton?.addEventListener("click", () => {
      addAttachments([{ name: `external-${Date.now()}.png`, kind: "external-screenshot" }]);
      renderSnapshot();
    });
    els.clearAttachmentsButton?.addEventListener("click", () => {
      clearAttachments();
      renderSnapshot();
    });

    modelSwitcherController.bindModelSwitcherActions();
    annotationPopoverController.bindAnnotationPopoverActions();

    els.rightResizeHandle.addEventListener("mousedown", (event) => {
      const startX = event.clientX;
      const startWidth = state.layout.chatWidth;
      const onMove = (moveEvent) => {
        state.layout.chatWidth = Math.max(360, startWidth - (moveEvent.clientX - startX));
        applyLayoutWidths();
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
    els.aiChatResizeHandle.addEventListener("mousedown", (event) => {
      const startY = event.clientY;
      const startHeight = state.layout.chatHeight;
      const onMove = (moveEvent) => {
        state.layout.chatHeight = Math.max(220, startHeight + (moveEvent.clientY - startY));
        applyLayoutWidths();
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });

    const drawerButtons = [
      [els.drawerContextButton, els.drawerContextPanel, "context"],
      [els.drawerManualButton, els.drawerManualPanel, "manual"],
      [els.drawerFocusButton, els.drawerFocusPanel, "focus"],
      [els.drawerStrategyButton, els.drawerStrategyPanel, "strategy"],
      [els.drawerEntriesButton, els.drawerEntriesPanel, "entries"],
      [els.drawerRecapButton, els.drawerRecapPanel, "recap"],
      [els.drawerGammaButton, els.drawerGammaPanel, "gamma"],
    ];
    drawerButtons.forEach(([button, panel, key]) => {
      button?.addEventListener("click", () => {
        state.drawerState[key] = !state.drawerState[key];
        panel.style.display = state.drawerState[key] ? "block" : "none";
        writeStorage("workbench", {
          activeAiThreadId: state.activeAiThreadId,
          drawerState: state.drawerState,
          topBar: state.topBar,
        });
      });
      if (panel) {
        panel.style.display = state.drawerState[key] ? "block" : "none";
      }
    });

    [els.layerEvents, els.layerFocusRegions, els.layerManualRegions, els.layerOperatorEntries, els.layerAiAnnotations].forEach((input) => {
      input?.addEventListener("change", renderSnapshot);
    });

    // 按钮绑定已在 replay_workbench_bindings.js 中处理，这里只处理 sendViewportButton
    if (els.sendViewportButton) {
      els.sendViewportButton.addEventListener("click", () => {
        try {
          const summary = els.chartViewportMeta?.textContent || "当前可视区域";
          appendAiChatMessage("user", `请基于当前图表可视区域继续分析：${summary}`, { preset: "viewport" }, state.activeAiThreadId, getActiveThread().title);
          renderSnapshot();
        } catch (error) {
          console.error("发送可视区域按钮错误:", error);
          renderStatusStrip([{ label: "发送可视区域失败", variant: "warn" }]);
        }
      });
    }

    els.chartSvg.addEventListener("click", (event) => {
      const target = event.target.closest("[data-annotation-id]");
      if (!target) {
        annotationPopoverController.hideAnnotationPopover();
        return;
      }
      state.selectedAnnotationId = target.dataset.annotationId;
      annotationPopoverController.showAnnotationPopover(target.dataset.annotationId);
      renderSnapshot();
    });
  }

  async function bootstrap() {
    const now = new Date();
    const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    if (!els.windowStart.value) {
      els.windowStart.value = toLocalInputValue(start);
    }
    if (!els.windowEnd.value) {
      els.windowEnd.value = toLocalInputValue(now);
    }
    els.instrumentSymbol.value = state.topBar.symbol;
    els.displayTimeframe.value = state.topBar.timeframe;
    els.quickRangeSelect.value = state.topBar.quickRange;
    syncCacheKey();
    try {
      await syncSessionsFromServer({ activateFirst: true, symbol: state.topBar.symbol });
    } catch (error) {
      console.warn("从后端同步会话失败:", error);
    }
    renderAiThreadTabs();
    setActiveThread(state.activeAiThreadId || state.aiThreads[0].id, state.aiThreads[0].title, {
      symbol: state.topBar.symbol,
      contractId: state.topBar.symbol,
      timeframe: state.topBar.timeframe,
      windowRange: state.topBar.quickRange,
    });
    renderSnapshot();
  }

  return {
    state,
    els,
    ensureChartView,
    buildCacheKey,
    syncCacheKey,
    renderSnapshot,
    attachBindings,
    bootstrap,
    handleBuild: actions.handleBuild,
  };
}
