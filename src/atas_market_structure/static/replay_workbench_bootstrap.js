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

function formatCompactLocalDateTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hour}:${minute}`;
}

function renderClusterItemsMarkup(cluster) {
  const items = Array.isArray(cluster?.items) ? cluster.items.slice(0, 5) : [];
  if (!items.length) {
    return `<p class="empty-note">当前没有事件明细。</p>`;
  }
  return `
    <div class="context-event-list">
      ${items.map((item) => `
        <div class="context-event-item">
          <strong>${escapeHtml(item.shortLabel || item.title || item.eventKind || "事件")}</strong>
          <p>${escapeHtml(item.metaText || item.priceText || "无附加说明")}</p>
          ${item.notePreviewText ? `<p>${escapeHtml(item.notePreviewText)}</p>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderEventPreviewMarkup(clusters = []) {
  if (!clusters.length) {
    return `<p class="empty-note">当前可视区域没有关键事件。</p>`;
  }
  return `
    <div class="context-event-list">
      ${clusters.slice(0, 4).map((cluster) => `
        <div class="context-event-item">
          <strong>${escapeHtml(cluster.timeLabel || "--")} · ${escapeHtml(cluster.summaryText || "事件")}</strong>
          <p>${escapeHtml(cluster.priceText || "价格未知")}</p>
          ${cluster.notePreviewText ? `<p>${escapeHtml(cluster.notePreviewText)}</p>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderDrawers({ state, els }) {
  const snapshot = state.snapshot;
  const eventModel = state.chartEventModel || null;
  const selectedCluster = eventModel?.selectedCluster || null;
  const topVisibleClusters = Array.isArray(eventModel?.topVisibleClusters) ? eventModel.topVisibleClusters : [];
  els.drawerContextPanel.innerHTML = snapshot
    ? `
      <div class="drawer-card-grid">
        <div class="info-card"><h4>回放上下文</h4><p>品种：${snapshot.instrument_symbol || state.topBar.symbol} / 周期：${timeframeLabel(snapshot.display_timeframe || state.topBar.timeframe)}</p></div>
        <div class="info-card"><h4>窗口</h4><p>${snapshot.window_start || "-"}<br>${snapshot.window_end || "-"}</p></div>
        <div class="info-card"><h4>事件视图</h4><p>当前可见 ${eventModel?.visibleClusterCount || 0} 个事件簇 / 主图显示 ${eventModel?.shownClusterCount || 0} 个 / 折叠 ${eventModel?.hiddenVisibleClusterCount || 0} 个</p></div>
        <div class="info-card"><h4>最近同步</h4><p>${formatCompactLocalDateTime(state.topBar.lastSyncedAt)}</p></div>
      </div>
      <div class="drawer-card-grid">
        <div class="info-card">
          <h4>${selectedCluster ? `事件详情 · ${escapeHtml(selectedCluster.timeLabel || "--")}` : "当前视图关键事件"}</h4>
          <p>${escapeHtml(selectedCluster?.summaryText || eventModel?.viewportSummary || "当前还没有关键事件摘要。")}</p>
          ${selectedCluster ? `<p>${escapeHtml(selectedCluster.priceText || "价格未知")}</p>` : ""}
          ${selectedCluster ? renderClusterItemsMarkup(selectedCluster) : renderEventPreviewMarkup(topVisibleClusters)}
        </div>
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
  const { ensureChartView, createDefaultChartView } = createChartViewHelpers({ state });
  const renderStatusStrip = renderStatusStripFactory(els);
  const planLifecycleEngine = createPlanLifecycleEngine({ state });
  const sessionMemoryEngine = createSessionMemoryEngine({ state, els, fetchJson });
  const MOBILE_AI_BREAKPOINT = 1000;
  const DESKTOP_SIDEBAR_MIN = 400;
  const DESKTOP_SIDEBAR_MAX = 560;

  function collectLayerStateFromInputs() {
    return {
      largeOrders: !!els.layerLargeOrders?.checked,
      absorption: !!els.layerAbsorption?.checked,
      iceberg: !!els.layerIceberg?.checked,
      replenishment: !!els.layerReplenishment?.checked,
      events: !!els.layerEvents?.checked,
      focusRegions: !!els.layerFocusRegions?.checked,
      manualRegions: !!els.layerManualRegions?.checked,
      operatorEntries: !!els.layerOperatorEntries?.checked,
      aiAnnotations: !!els.layerAiAnnotations?.checked,
    };
  }

  function applyLayerStateToInputs() {
    const layerState = state.layerState || {};
    if (els.layerLargeOrders) els.layerLargeOrders.checked = !!layerState.largeOrders;
    if (els.layerAbsorption) els.layerAbsorption.checked = !!layerState.absorption;
    if (els.layerIceberg) els.layerIceberg.checked = !!layerState.iceberg;
    if (els.layerReplenishment) els.layerReplenishment.checked = !!layerState.replenishment;
    if (els.layerEvents) els.layerEvents.checked = layerState.events !== false;
    if (els.layerFocusRegions) els.layerFocusRegions.checked = layerState.focusRegions !== false;
    if (els.layerManualRegions) els.layerManualRegions.checked = layerState.manualRegions !== false;
    if (els.layerOperatorEntries) els.layerOperatorEntries.checked = layerState.operatorEntries !== false;
    if (els.layerAiAnnotations) els.layerAiAnnotations.checked = layerState.aiAnnotations !== false;
    state.layerState = collectLayerStateFromInputs();
  }

  function persistLayerState() {
    state.layerState = collectLayerStateFromInputs();
    persistWorkbenchState();
  }

  function persistWorkbenchState() {
    writeStorage("workbench", {
      activeAiThreadId: state.activeAiThreadId,
      drawerState: state.drawerState,
      topBar: state.topBar,
      pinnedPlanId: state.pinnedPlanId,
      layerState: state.layerState || collectLayerStateFromInputs(),
      symbolWorkspaceState: state.symbolWorkspaceState || {},
      eventStreamFilter: state.eventStreamFilter || "all",
      replyExtractionState: state.replyExtractionState || { filter: "all", showIgnored: false, bySymbol: {} },
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

  function applyHeaderChipState(element, { label = "", variant = "", title = "" } = {}) {
    if (!element) {
      return;
    }
    element.className = variant ? `status-chip ${variant}` : "status-chip";
    element.textContent = label;
    element.title = title || label;
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
      return false;
    }
    scrollChatToBottom({ behavior: "auto", markRead: true, persist: false });
    const node = els.aiChatThread.querySelector(`[data-message-id="${messageId}"]`);
    if (!node) {
      return false;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    const session = getActiveThread();
    session.autoFollowChat = false;
    session.hasUnreadChatBelow = false;
    session.scrollOffset = els.aiChatThread?.scrollTop || 0;
    node.classList.add("source-flash");
    window.setTimeout(() => node.classList.remove("source-flash"), 2200);
    return true;
  }

  function jumpToMessageWhenReady(messageId, { retries = 12, delay = 80 } = {}) {
    if (!messageId) {
      return;
    }
    let attempts = 0;
    const tryJump = () => {
      if (jumpToMessage(messageId)) {
        return;
      }
      attempts += 1;
      if (attempts >= retries) {
        return;
      }
      window.setTimeout(tryJump, delay);
    };
    tryJump();
  }

  function jumpToSecondaryMessage(messageId) {
    if (!messageId || !els.eventScribeThread) {
      return false;
    }
    const node = els.eventScribeThread.querySelector(`[data-secondary-message-id="${messageId}"]`);
    if (!node) {
      return false;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("source-flash");
    window.setTimeout(() => node.classList.remove("source-flash"), 2200);
    return true;
  }

  function jumpToSecondaryMessageWhenReady(messageId, { retries = 12, delay = 80 } = {}) {
    if (!messageId) {
      return;
    }
    let attempts = 0;
    const tryJump = () => {
      if (jumpToSecondaryMessage(messageId)) {
        return;
      }
      attempts += 1;
      if (attempts >= retries) {
        return;
      }
      window.setTimeout(tryJump, delay);
    };
    tryJump();
  }

  function resolveAnnotationScope(annotationId, mode = "only") {
    const annotations = Array.isArray(state.aiAnnotations) ? state.aiAnnotations : [];
    const target = annotations.find((item) => item.id === annotationId);
    if (!target) {
      return null;
    }
    const scopedAnnotationIds = mode === "source" && target.plan_id
      ? annotations.filter((item) => item.plan_id === target.plan_id).map((item) => item.id)
      : mode === "reply" && target.message_id
        ? annotations
          .filter((item) => item.message_id === target.message_id && item.session_id === target.session_id)
          .map((item) => item.id)
        : [annotationId];
    return {
      target,
      filters: {
        onlyCurrentSession: false,
        sessionIds: target.session_id ? [target.session_id] : [],
        messageIds: target.message_id ? [target.message_id] : [],
        annotationIds: scopedAnnotationIds,
        selectedOnly: false,
      },
    };
  }

  function applyAnnotationScope(annotationId, {
    mode = "only",
    activateSession = false,
    jumpToSource = false,
    render = true,
  } = {}) {
    const scope = resolveAnnotationScope(annotationId, mode);
    if (!scope) {
      return null;
    }
    const { target, filters } = scope;
    state.selectedAnnotationId = annotationId;
    state.annotationFilters.onlyCurrentSession = filters.onlyCurrentSession;
    state.annotationFilters.sessionIds = filters.sessionIds;
    state.annotationFilters.messageIds = filters.messageIds;
    state.annotationFilters.annotationIds = filters.annotationIds;
    state.annotationFilters.selectedOnly = filters.selectedOnly;
    writeStorage("annotationFilters", state.annotationFilters);
    if (activateSession && target.session_id) {
      const session = state.aiThreads.find((item) => item.id === target.session_id);
      setActiveThread(target.session_id, session?.title || "会话");
    }
    if (render) {
      renderSnapshot();
    }
    if (jumpToSource && target.message_id) {
      const targetSession = target.session_id
        ? state.aiThreads.find((item) => item.id === target.session_id)
        : null;
      if (targetSession && getWorkspaceRole(targetSession) === "scribe") {
        rememberSymbolWorkspaceSession(targetSession);
        renderEventScribePanel();
        jumpToSecondaryMessageWhenReady(target.message_id);
      } else {
        jumpToMessageWhenReady(target.message_id);
      }
    }
    return scope;
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

  function syncPromptBlocksToServer(session, { selectedPromptBlockIds = null, pinnedContextBlockIds = null, includeMemorySummary = null, includeRecentMessages = null } = {}) {
    if (!fetchJson || !session?.id) {
      return Promise.resolve();
    }
    return fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_prompt_block_ids: Array.isArray(selectedPromptBlockIds) ? selectedPromptBlockIds : (Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : []),
        pinned_context_block_ids: Array.isArray(pinnedContextBlockIds) ? pinnedContextBlockIds : (Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : []),
        include_memory_summary: includeMemorySummary ?? !!session.includeMemorySummary,
        include_recent_messages: includeRecentMessages ?? !!session.includeRecentMessages,
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
    const related = getReplyAnnotations({ messageId, sessionId: targetSession.id, planId });
    const mountedObjectIds = related.map((item) => item.id);
    const mountedReplyIds = Array.isArray(targetSession.mountedReplyIds) ? targetSession.mountedReplyIds : [];
    if (mode === "replace") {
      targetSession.mountedReplyIds = [messageId];
    } else if (mode === "show") {
      targetSession.mountedReplyIds = mountedReplyIds.includes(messageId)
        ? mountedReplyIds
        : [...mountedReplyIds, messageId];
    }
    targetSession.messages = (targetSession.messages || []).map((message) => {
      if (message.message_id === messageId) {
        return {
          ...message,
          mountedToChart: true,
          mountedObjectIds,
        };
      }
      if (mode === "replace") {
        return { ...message, mountedToChart: false, mountedObjectIds: [] };
      }
      return message;
    });
    const mountMode = mode === "replace" ? "replace" : mode === "focus" ? "focus_only" : "append";
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
      mountMode: "append",
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
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (targetSession) {
      setActiveThread(targetSession.id, targetSession.title, {
        symbol: targetSession.symbol || targetSession.contractId || targetSession.memory?.symbol || state.topBar.symbol,
        contractId: targetSession.contractId || targetSession.symbol || targetSession.memory?.symbol || state.topBar.symbol,
        timeframe: targetSession.timeframe || targetSession.memory?.timeframe || state.topBar.timeframe,
        windowRange: targetSession.windowRange || targetSession.memory?.window_range || state.topBar.quickRange,
      });
    }
    const related = getReplyAnnotations({ messageId, sessionId: targetSession?.id || sessionId, planId });
    if (action === "unmount") {
      unmountReplyObjects(messageId, { sessionId: targetSession?.id || sessionId });
      if (messageId) {
        state.annotationFilters.annotationIds = (state.annotationFilters.annotationIds || []).filter((id) => {
          const annotation = state.aiAnnotations.find((item) => item.id === id);
          return annotation?.message_id !== messageId;
        });
      }
      writeStorage("annotationFilters", state.annotationFilters);
      renderStatusStrip([{ label: "已从图表取消挂载回复对象。", variant: "good" }]);
      renderSnapshot();
      return;
    }
    if (!related.length) {
      if (action === "jump" && messageId) {
        jumpToMessageWhenReady(messageId);
      }
      renderStatusStrip([{ label: "当前回复还没有可上图对象，已保留在会话里。", variant: "warn" }]);
      renderSnapshot();
      return;
    }
    state.selectedAnnotationId = related[0].id;
    const session = state.aiThreads.find((item) => item.id === (targetSession?.id || state.activeAiThreadId));
    if (action === "focus") {
      if (session && messageId) {
        mountReplyObjects(messageId, "focus", { sessionId: session.id, planId });
      }
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "focus" });
    } else if (action === "show") {
      if (session && messageId) {
        mountReplyObjects(messageId, "show", { sessionId: session.id, planId });
      }
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "show" });
    } else if (session && messageId) {
      mountReplyObjects(messageId, "replace", { sessionId: session.id, planId });
    }
    writeStorage("annotationFilters", state.annotationFilters);
    if (action === "jump") {
      jumpToMessageWhenReady(messageId);
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

  function getWorkspaceRole(session, fallback = "analyst") {
    return String(session?.workspaceRole || fallback || "analyst").trim().toLowerCase() || "analyst";
  }

  function getSymbolWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    if (!state.symbolWorkspaceState || typeof state.symbolWorkspaceState !== "object") {
      state.symbolWorkspaceState = {};
    }
    if (!state.symbolWorkspaceState[normalizedSymbol]) {
      state.symbolWorkspaceState[normalizedSymbol] = {
        analystSessionId: null,
        scribeSessionId: null,
        lastActiveAt: null,
      };
    }
    return state.symbolWorkspaceState[normalizedSymbol];
  }

  function rememberSymbolWorkspaceSession(session) {
    if (!session) {
      return;
    }
    const symbol = String(session.symbol || session.contractId || session.memory?.symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const workspace = getSymbolWorkspace(symbol);
    const role = getWorkspaceRole(session);
    if (role === "scribe") {
      workspace.scribeSessionId = session.id;
    } else {
      workspace.analystSessionId = session.id;
    }
    workspace.lastActiveAt = new Date().toISOString();
    persistWorkbenchState();
  }

  function getSessionByRole(symbol, role = "analyst") {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const normalizedRole = getWorkspaceRole({ workspaceRole: role });
    const workspace = getSymbolWorkspace(normalizedSymbol);
    const sessionId = normalizedRole === "scribe" ? workspace.scribeSessionId : workspace.analystSessionId;
    const remembered = sessionId
      ? state.aiThreads.find((item) => item.id === sessionId && getWorkspaceRole(item) === normalizedRole)
      : null;
    if (remembered) {
      return remembered;
    }
    return null;
  }

  function getReplyExtractionState() {
    if (!state.replyExtractionState || typeof state.replyExtractionState !== "object") {
      state.replyExtractionState = {
        filter: "all",
        showIgnored: false,
        bySymbol: {},
      };
    }
    if (!state.replyExtractionState.bySymbol || typeof state.replyExtractionState.bySymbol !== "object") {
      state.replyExtractionState.bySymbol = {};
    }
    if (!state.replyExtractionState.filter) {
      state.replyExtractionState.filter = "all";
    }
    state.replyExtractionState.showIgnored = !!state.replyExtractionState.showIgnored;
    return state.replyExtractionState;
  }

  function getReplyExtractionWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const extractionState = getReplyExtractionState();
    if (!extractionState.bySymbol[normalizedSymbol]) {
      extractionState.bySymbol[normalizedSymbol] = {
        candidateMeta: {},
        lastTouchedAt: null,
      };
    }
    const workspace = extractionState.bySymbol[normalizedSymbol];
    if (!workspace.candidateMeta || typeof workspace.candidateMeta !== "object") {
      workspace.candidateMeta = {};
    }
    return workspace;
  }

  function getReplyCandidateKey(item = {}) {
    return String(item?.stableKey || item?.candidateKey || item?.id || "").trim() || null;
  }

  function updateReplyCandidateMeta(symbol, itemOrKey, patch = {}) {
    const candidateKey = typeof itemOrKey === "string" ? itemOrKey : getReplyCandidateKey(itemOrKey);
    if (!candidateKey) {
      return null;
    }
    const workspace = getReplyExtractionWorkspace(symbol);
    workspace.candidateMeta[candidateKey] = {
      ...(workspace.candidateMeta[candidateKey] || {}),
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    workspace.lastTouchedAt = workspace.candidateMeta[candidateKey].updatedAt;
    persistWorkbenchState();
    return workspace.candidateMeta[candidateKey];
  }

  function hydrateReplyCandidateState(symbol, item = {}) {
    const candidateKey = getReplyCandidateKey(item);
    const workspace = getReplyExtractionWorkspace(symbol);
    const meta = candidateKey ? (workspace.candidateMeta[candidateKey] || {}) : {};
    return {
      ...item,
      candidateKey,
      status: meta.status || item.status || "candidate",
      pinned: !!meta.pinned,
      ignored: (meta.status || item.status) === "ignored",
    };
  }

  async function activateSymbolWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    let analystSession = getSessionByRole(normalizedSymbol, "analyst");
    if (!analystSession) {
      analystSession = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
        workspaceRole: "analyst",
        activate: false,
      });
    }
    let scribeSession = getSessionByRole(normalizedSymbol, "scribe");
    if (!scribeSession) {
      scribeSession = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
        workspaceRole: "scribe",
        activate: false,
      });
    }
    if (scribeSession) {
      rememberSymbolWorkspaceSession(scribeSession);
    }
    if (analystSession) {
      rememberSymbolWorkspaceSession(analystSession);
      setActiveThread(analystSession.id, analystSession.title, {
        symbol: normalizedSymbol,
        contractId: analystSession.contractId || normalizedSymbol,
        timeframe: analystSession.timeframe || state.topBar?.timeframe || "1m",
        windowRange: analystSession.windowRange || state.topBar?.quickRange || "最近7天",
        workspaceRole: "analyst",
      });
    }
    return { analystSession, scribeSession };
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
    onPromptBlocksChanged: (session, { selectedPromptBlockIds, pinnedContextBlockIds, includeMemorySummary, includeRecentMessages } = {}) => {
      void syncPromptBlocksToServer(session, { selectedPromptBlockIds, pinnedContextBlockIds, includeMemorySummary, includeRecentMessages });
      if (session.id === state.activeAiThreadId) {
        renderAiChat();
      }
    },
    fetchJson,
    renderStatusStrip,
    onSessionActivated: (session) => {
      if (getWorkspaceRole(session) === "analyst") {
        rememberSymbolWorkspaceSession(session);
      }
      renderSnapshot();
    },
  });
  const {
    ensureThread,
    getActiveThread,
    setActiveThread,
    hydrateSessionFromServer,
    syncSessionsFromServer,
    createBackendSession,
    getOrCreateBlankSessionForSymbol,
    createNewAnalystSession,
    getPreferredSessionForSymbol,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    upsertPlanCardToSession,
    cloneActiveThreadBranch,
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
    scheduleDraftStateSync,
    persistSessions,
  } = threadController;

  const replayLoader = createReplayLoader({
    state,
    els,
    fetchJson,
    ensureThread,
    renderCoreSnapshot: () => renderCoreSnapshot(),
    renderSidebarSnapshot: () => renderSidebarSnapshot(),
    renderDeferredSurfaces: () => renderDeferredSurfaces(),
  });

  const actions = createWorkbenchActions({
    state,
    els,
    fetchJson,
    toUtcString: (value) => value ? new Date(value).toISOString() : null,
    syncCacheKey,
    renderStatusStrip,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    renderCoreSnapshot: () => renderCoreSnapshot(),
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
    applySnapshotToState: replayLoader.applySnapshotToState,
    loadSidebarDataInBackground: replayLoader.loadSidebarDataInBackground,
    loadDeferredEnhancements: replayLoader.loadDeferredEnhancements,
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
    createNewAnalystSession,
    renderAiChat,
    scheduleDraftStateSync,
    setMountedReplyIds,
  });
  aiChat.bindStreamingControls?.();
  const annotationPanelController = createAnnotationPanelController({
    state,
    els,
    persistWorkbenchState,
    renderSnapshot: () => renderSnapshot(),
    applyAnnotationScope,
  });
  const annotationPopoverController = createAnnotationPopoverController({
    state,
    els,
    renderSnapshot: () => renderSnapshot(),
    applyAnnotationScope,
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
  const buttonFeedbackTimers = new WeakMap();
  const defaultAttachmentAccept = els.attachmentInput?.getAttribute("accept") || "";
  const voiceCaptureState = {
    recognition: null,
    listening: false,
    stopRequested: false,
    errorMessage: "",
    transcriptCaptured: false,
    baseText: "",
  };

  function isDockedAiLayout() {
    return window.innerWidth > MOBILE_AI_BREAKPOINT;
  }

  function syncAiSidebarViewportState({ persist = true } = {}) {
    if (!els.aiSidebar) {
      return;
    }
    const docked = isDockedAiLayout();
    const shouldOpen = docked ? true : !!state.aiSidebarOpen;
    els.aiSidebar.classList.toggle("open", shouldOpen);
    els.workbenchMain?.classList.toggle("ai-sidebar-open", shouldOpen);
    if (els.aiSidebarTrigger) {
      els.aiSidebarTrigger.classList.toggle("hidden", shouldOpen);
    }
    if (docked) {
      state.aiSidebarOpen = true;
    }
    if (persist) {
      writeStorage("aiSidebarState", {
        open: state.aiSidebarOpen,
        pinned: state.aiSidebarPinned,
      });
    }
  }

  function syncBottomDrawerVisibility() {
    if (!els.bottomContextDrawer) {
      return;
    }
    const hasOpenDrawer = Object.values(state.drawerState || {}).some(Boolean);
    els.bottomContextDrawer.hidden = !hasOpenDrawer;
  }

  function getDrawerPanel(key) {
    return {
      context: els.drawerContextPanel,
      manual: els.drawerManualPanel,
      focus: els.drawerFocusPanel,
      strategy: els.drawerStrategyPanel,
      entries: els.drawerEntriesPanel,
      recap: els.drawerRecapPanel,
      gamma: els.drawerGammaPanel,
    }[key] || null;
  }

  function getDrawerButton(key) {
    return {
      context: els.drawerContextButton,
      manual: els.drawerManualButton,
      focus: els.drawerFocusButton,
      strategy: els.drawerStrategyButton,
      entries: els.drawerEntriesButton,
      recap: els.drawerRecapButton,
      gamma: els.drawerGammaButton,
    }[key] || null;
  }

  function syncDrawerTabState() {
    ["context", "manual", "focus", "strategy", "entries", "recap", "gamma"].forEach((key) => {
      const button = getDrawerButton(key);
      if (!button) {
        return;
      }
      const isActive = !!state.drawerState[key];
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function setDrawerOpen(key, open) {
    const panel = getDrawerPanel(key);
    state.drawerState[key] = !!open;
    if (panel) {
      panel.style.display = open ? "block" : "none";
    }
    syncDrawerTabState();
    syncBottomDrawerVisibility();
    persistWorkbenchState();
  }

  function focusChartOnEventCluster(cluster) {
    const candles = state.snapshot?.candles || [];
    if (!cluster || !candles.length) {
      return;
    }
    const targetTime = Number(cluster.time || 0) * 1000;
    let targetIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    candles.forEach((bar, index) => {
      const barTime = new Date(bar.started_at).getTime();
      const distance = Math.abs(barTime - targetTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        targetIndex = index;
      }
    });
    const span = state.chartView
      ? Math.max(24, state.chartView.endIndex - state.chartView.startIndex + 1)
      : Math.min(120, candles.length);
    const startIndex = Math.max(0, targetIndex - Math.floor(span / 2));
    const endIndex = Math.min(candles.length - 1, startIndex + span - 1);
    const nextView = clampChartView(candles.length, startIndex, endIndex, state.chartView);
    state.chartView = nextView;
    const liveChart = window._lwChartState?.chartInstance;
    if (liveChart?.timeScale?.setVisibleLogicalRange) {
      try {
        liveChart.timeScale().setVisibleLogicalRange({
          from: nextView.startIndex,
          to: nextView.endIndex,
        });
      } catch (error) {
        console.warn("聚焦事件簇时同步图表视窗失败:", error);
      }
    }
  }

  function selectChartEventCluster(clusterKey, { centerChart = false, openContext = true, announce = false } = {}) {
    const cluster = state.chartEventModel?.clusterIndex?.[clusterKey];
    if (!cluster) {
      return false;
    }
    state.selectedChartEventClusterKey = clusterKey;
    if (centerChart) {
      focusChartOnEventCluster(cluster);
    }
    if (openContext) {
      setDrawerOpen("context", true);
    }
    if (announce) {
      renderStatusStrip([{ label: `事件详情：${cluster.timeLabel || "--"} · ${cluster.summaryText || "事件"}`, variant: "emphasis" }]);
    }
    renderSnapshot();
    return true;
  }

  function applyLayoutWidths() {
    const nextSidebarWidth = Math.max(
      DESKTOP_SIDEBAR_MIN,
      Math.min(DESKTOP_SIDEBAR_MAX, Number(state.layout.chatWidth) || 440),
    );
    state.layout.chatWidth = nextSidebarWidth;
    els.shellLayout?.style.setProperty("--sidebar-width", `${nextSidebarWidth}px`);
    els.chartWorkspace.style.minWidth = "0";
    els.chartWorkspace.style.width = "";
    els.rightPanel.style.width = "";
    els.aiSidebar.style.width = "";
    els.aiChatThread.style.height = "";
    syncAiSidebarViewportState({ persist: false });
    writeStorage("layout", state.layout);
    window.requestAnimationFrame(() => updateChatFollowState({ persist: false }));
  }

  function setButtonBusy(button, busy) {
    if (!button) {
      return;
    }
    button.dataset.busy = busy ? "true" : "false";
    button.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function pulseButton(button) {
    if (!button) {
      return;
    }
    button.dataset.pressed = "true";
    const previousTimer = buttonFeedbackTimers.get(button);
    if (previousTimer) {
      window.clearTimeout(previousTimer);
    }
    const timer = window.setTimeout(() => {
      delete button.dataset.pressed;
      buttonFeedbackTimers.delete(button);
    }, 150);
    buttonFeedbackTimers.set(button, timer);
  }

  function installButtonFeedback() {
    document.addEventListener("pointerdown", (event) => {
      const button = event.target?.closest("button");
      if (!button || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const button = document.activeElement;
      if (!(button instanceof HTMLElement) || !button.matches("button") || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
  }

  function focusComposerInput() {
    if (!els.aiChatInput) {
      return;
    }
    els.aiChatInput.focus();
    const end = els.aiChatInput.value.length;
    if (typeof els.aiChatInput.setSelectionRange === "function") {
      els.aiChatInput.setSelectionRange(end, end);
    }
  }

  function updateComposerDraft(value) {
    if (!els.aiChatInput) {
      return;
    }
    els.aiChatInput.value = value;
    aiChat.handleComposerInput(value);
  }

  function syncAiSidebarPinButtonState() {
    if (!els.aiSidebarPinButton) {
      return;
    }
    els.aiSidebarPinButton.classList.toggle("is-active", !!state.aiSidebarPinned);
    els.aiSidebarPinButton.setAttribute("aria-pressed", state.aiSidebarPinned ? "true" : "false");
    els.aiSidebarPinButton.title = state.aiSidebarPinned ? "取消固定侧栏偏好" : "固定侧栏偏好";
  }

  function syncQuickActionButtonState() {
    const skillPanelOpen = !!els.aiSkillPanel && !els.aiSkillPanel.hidden;
    if (els.aiMoreButton) {
      els.aiMoreButton.classList.toggle("is-active", skillPanelOpen);
      els.aiMoreButton.setAttribute("aria-expanded", skillPanelOpen ? "true" : "false");
    }
    [els.aiVoiceButton, els.aiVoiceInputButton].forEach((button) => {
      if (!button) {
        return;
      }
      button.classList.toggle("is-active", !!voiceCaptureState.listening);
      button.setAttribute("aria-pressed", voiceCaptureState.listening ? "true" : "false");
      setButtonBusy(button, false);
    });
  }

  function setSkillPanelVisible(visible, { announce = false } = {}) {
    if (!els.aiSkillPanel) {
      return;
    }
    const nextVisible = !!visible;
    const previousVisible = !els.aiSkillPanel.hidden;
    els.aiSkillPanel.hidden = !nextVisible;
    syncQuickActionButtonState();
    if (!announce || previousVisible === nextVisible) {
      return;
    }
    renderStatusStrip([{ label: nextVisible ? "已打开快捷技能面板" : "已收起快捷技能面板", variant: "emphasis" }]);
    if (nextVisible) {
      els.aiSkillSearch?.focus();
    } else {
      focusComposerInput();
    }
  }

  function openAttachmentPicker({ accept = defaultAttachmentAccept, statusLabel = "选择要附加的文件" } = {}) {
    if (!els.attachmentInput) {
      renderStatusStrip([{ label: "当前页面还没有可用的附件入口。", variant: "warn" }]);
      return;
    }
    els.attachmentInput.setAttribute("accept", accept || defaultAttachmentAccept);
    renderStatusStrip([{ label: statusLabel, variant: "emphasis" }]);
    els.attachmentInput.click();
  }

  function addQuickAttachment(item, statusLabel) {
    addAttachments([item]);
    renderStatusStrip([{ label: statusLabel, variant: "good" }]);
    renderSnapshot();
    focusComposerInput();
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error(`读取文件失败: ${file?.name || "unknown"}`));
      reader.readAsDataURL(file);
    });
  }

  async function mapFileToAttachment(file) {
    const mediaType = file?.type || "application/octet-stream";
    const dataUrl = await readFileAsDataUrl(file);
    return {
      name: file?.name || `attachment-${Date.now()}`,
      kind: mediaType,
      media_type: mediaType,
      size: Number(file?.size || 0),
      data_url: dataUrl,
      preview_url: mediaType.startsWith("image/") ? dataUrl : "",
    };
  }

  function loadImageFromUrl(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("加载图片失败"));
      image.src = url;
    });
  }

  async function captureChartFrameDataUrl() {
    if (!els.chartFrame || !state.snapshot?.candles?.length) {
      throw new Error("请先加载图表，再生成图表截图。");
    }
    const frameRect = els.chartFrame.getBoundingClientRect();
    const width = Math.max(1, Math.round(frameRect.width));
    const height = Math.max(1, Math.round(frameRect.height));
    if (width < 4 || height < 4) {
      throw new Error("图表还未完成渲染。");
    }

    const output = document.createElement("canvas");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    output.width = Math.round(width * dpr);
    output.height = Math.round(height * dpr);
    const ctx = output.getContext("2d");
    if (!ctx) {
      throw new Error("当前浏览器无法生成截图。");
    }
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#101827";
    ctx.fillRect(0, 0, width, height);

    let hasLayer = false;
    const visibleCanvases = Array.from(els.chartFrame.querySelectorAll("canvas")).filter((node) => {
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    });
    visibleCanvases.forEach((canvasNode) => {
      const rect = canvasNode.getBoundingClientRect();
      ctx.drawImage(canvasNode, rect.left - frameRect.left, rect.top - frameRect.top, rect.width, rect.height);
      hasLayer = true;
    });

    if (els.chartSvg && els.chartSvg.style.display !== "none" && els.chartSvg.innerHTML.trim()) {
      const serialized = new XMLSerializer().serializeToString(els.chartSvg);
      const svgMarkup = serialized.includes("xmlns=")
        ? serialized
        : serialized.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
      const blobUrl = URL.createObjectURL(new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" }));
      try {
        const image = await loadImageFromUrl(blobUrl);
        const rect = els.chartSvg.getBoundingClientRect();
        ctx.drawImage(image, rect.left - frameRect.left, rect.top - frameRect.top, rect.width, rect.height);
        hasLayer = true;
      } finally {
        URL.revokeObjectURL(blobUrl);
      }
    }

    if (!hasLayer) {
      throw new Error("当前图表没有可截图的可视内容。");
    }
    return output.toDataURL("image/png");
  }

  async function addChartScreenshotAttachment(statusLabel = "已把图表截图加入当前会话附件。") {
    const dataUrl = await captureChartFrameDataUrl();
    addQuickAttachment({
      name: `chart-${Date.now()}.png`,
      kind: "chart-screenshot",
      media_type: "image/png",
      data_url: dataUrl,
      preview_url: dataUrl,
    }, statusLabel);
  }

  function normalizeVoiceError(errorCode) {
    const mapping = {
      "aborted": "已中断",
      "audio-capture": "没有检测到可用麦克风",
      "network": "网络异常",
      "not-allowed": "没有获得麦克风权限",
      "service-not-allowed": "浏览器禁止使用语音服务",
      "no-speech": "没有识别到语音",
    };
    return mapping[errorCode] || errorCode || "未知错误";
  }

  function applyVoiceDraft(transcript) {
    const normalized = String(transcript || "").trim();
    const nextDraft = normalized
      ? `${voiceCaptureState.baseText}${voiceCaptureState.baseText ? "\n" : ""}${normalized}`.trim()
      : voiceCaptureState.baseText;
    updateComposerDraft(nextDraft);
  }

  function stopVoiceCapture({ announce = true } = {}) {
    if (!voiceCaptureState.listening || !voiceCaptureState.recognition) {
      return false;
    }
    voiceCaptureState.stopRequested = true;
    if (announce) {
      renderStatusStrip([{ label: "正在停止语音输入…", variant: "emphasis" }]);
    }
    try {
      voiceCaptureState.recognition.stop();
      return true;
    } catch (error) {
      console.warn("停止语音输入失败:", error);
      return false;
    }
  }

  function startVoiceCapture() {
    if (voiceCaptureState.listening) {
      stopVoiceCapture();
      return;
    }
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      renderStatusStrip([{ label: "当前浏览器不支持语音输入，已聚焦消息输入框。", variant: "warn" }]);
      focusComposerInput();
      return;
    }
    voiceCaptureState.baseText = (els.aiChatInput?.value || "").trimEnd();
    voiceCaptureState.stopRequested = false;
    voiceCaptureState.errorMessage = "";
    voiceCaptureState.transcriptCaptured = false;
    const recognition = new SpeechRecognitionCtor();
    voiceCaptureState.recognition = recognition;
    recognition.lang = "zh-CN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      voiceCaptureState.listening = true;
      syncQuickActionButtonState();
      renderStatusStrip([{ label: "正在语音输入，再点一次可停止。", variant: "emphasis" }]);
      focusComposerInput();
    };
    recognition.onresult = (event) => {
      let mergedTranscript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        const segment = event.results[index]?.[0]?.transcript || "";
        mergedTranscript += segment;
        if (event.results[index]?.isFinal && segment.trim()) {
          voiceCaptureState.transcriptCaptured = true;
        }
      }
      if (mergedTranscript.trim()) {
        applyVoiceDraft(mergedTranscript);
      }
    };
    recognition.onerror = (event) => {
      voiceCaptureState.errorMessage = normalizeVoiceError(event.error);
    };
    recognition.onend = () => {
      const hadTranscript = voiceCaptureState.transcriptCaptured;
      const errorMessage = voiceCaptureState.errorMessage;
      const stopRequested = voiceCaptureState.stopRequested;
      voiceCaptureState.recognition = null;
      voiceCaptureState.listening = false;
      voiceCaptureState.stopRequested = false;
      voiceCaptureState.errorMessage = "";
      voiceCaptureState.transcriptCaptured = false;
      syncQuickActionButtonState();
      if (errorMessage) {
        renderStatusStrip([{ label: `语音输入失败：${errorMessage}`, variant: "warn" }]);
      } else if (hadTranscript) {
        renderStatusStrip([{ label: "语音内容已写入输入框。", variant: "good" }]);
        focusComposerInput();
      } else if (stopRequested) {
        renderStatusStrip([{ label: "语音输入已停止。", variant: "emphasis" }]);
        focusComposerInput();
      } else {
        renderStatusStrip([{ label: "没有识别到语音内容。", variant: "warn" }]);
        focusComposerInput();
      }
    };
    try {
      renderStatusStrip([{ label: "正在请求语音权限…", variant: "emphasis" }]);
      recognition.start();
    } catch (error) {
      voiceCaptureState.recognition = null;
      voiceCaptureState.listening = false;
      syncQuickActionButtonState();
      renderStatusStrip([{ label: `语音输入无法启动：${error.message || String(error)}`, variant: "warn" }]);
      focusComposerInput();
    }
  }

  async function runButtonAction(button, action, { silentError = false } = {}) {
    if (button?.dataset.busy === "true") {
      return null;
    }
    setButtonBusy(button, true);
    try {
      return await action();
    } catch (error) {
      console.error("按钮动作失败:", error);
      if (!silentError) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
      return null;
    } finally {
      setButtonBusy(button, false);
    }
  }

  function updateHeaderStatus() {
    state.topBar.symbol = els.instrumentSymbol.value.trim() || "NQ";
    state.topBar.timeframe = els.displayTimeframe.value;
    state.topBar.quickRange = els.quickRangeSelect.value;
    applyHeaderChipState(els.statusSymbolChip, { label: state.topBar.symbol });
    applyHeaderChipState(els.statusTimeframeChip, { label: timeframeLabel(state.topBar.timeframe) });
    const perfParts = [];
    if (Number.isFinite(state.perf.buildResponseMs)) perfParts.push(`build ${state.perf.buildResponseMs}ms`);
    if (Number.isFinite(state.perf.coreSnapshotLoadMs)) perfParts.push(`core-load ${state.perf.coreSnapshotLoadMs}ms`);
    if (Number.isFinite(state.perf.coreRenderMs)) perfParts.push(`core-render ${state.perf.coreRenderMs}ms`);
    if (Number.isFinite(state.perf.sidebarLoadMs)) perfParts.push(`sidebar-load ${state.perf.sidebarLoadMs}ms`);
    if (Number.isFinite(state.perf.sidebarRenderMs)) perfParts.push(`sidebar-render ${state.perf.sidebarRenderMs}ms`);
    if (state.historyBackfillLoading) perfParts.push("history loading");
    else if (state.fullHistoryLoaded) perfParts.push("history ready");
    const quickRangeLabel = els.quickRangeSelect.options[els.quickRangeSelect.selectedIndex]?.text || "自定义";
    applyHeaderChipState(els.statusWindowChip, {
      label: perfParts.length ? `${quickRangeLabel} · ${perfParts.join(" / ")}` : quickRangeLabel,
      title: perfParts.length ? `${quickRangeLabel}\n${perfParts.join(" / ")}` : quickRangeLabel,
    });

    applyHeaderChipState(els.statusDataChip, {
      label: `数据状态：${state.snapshot?.live_tail ? "实时尾流" : state.snapshot ? "历史快照" : "未加载"}`,
      variant: state.snapshot?.live_tail ? "emphasis" : "",
    });

    const integrity = state.integrity || state.snapshot?.integrity || state.buildResponse?.integrity || null;
    let integrityLabel = "完整性：待评估";
    let integrityVariant = "";
    if (integrity?.status) {
      const gapCount = Number(integrity.gap_count || 0);
      const missingBarCount = Number(integrity.missing_bar_count || 0);
      integrityLabel = gapCount || missingBarCount
        ? `完整性：${integrity.status} / 缺 ${missingBarCount} / gap ${gapCount}`
        : `完整性：${integrity.status}`;
      integrityVariant = integrity.status === "complete" && !gapCount && !missingBarCount
        ? "good"
        : (gapCount || missingBarCount ? "warn" : "emphasis");
    }
    applyHeaderChipState(els.statusIntegrityChip, {
      label: integrityLabel,
      variant: integrityVariant,
    });

    const buildAction = state.buildResponse?.action || null;
    const acquisitionMode = state.snapshot?.acquisition_mode || state.buildResponse?.summary?.acquisition_mode || null;
    let cacheLabel = "缓存：待构建";
    let cacheVariant = "";
    if (buildAction === "cache_hit" || acquisitionMode === "cache_reuse") {
      cacheLabel = "缓存：命中 / 复用";
      cacheVariant = "good";
    } else if (buildAction === "built_from_local_history" || acquisitionMode === "local_history") {
      cacheLabel = "来源：本地连续流";
      cacheVariant = "emphasis";
    } else if (buildAction === "built_from_atas_history" || acquisitionMode === "atas_fetch") {
      cacheLabel = "来源：ATAS 历史";
      cacheVariant = "emphasis";
    } else if (buildAction === "atas_fetch_required") {
      cacheLabel = "缓存：未命中";
      cacheVariant = "warn";
    }
    applyHeaderChipState(els.statusCacheChip, {
      label: cacheLabel,
      variant: cacheVariant,
    });

    let backfillLabel = "补数：无需";
    let backfillVariant = "good";
    if (state.pendingBackfill?.status) {
      backfillLabel = `补数：${state.pendingBackfill.status}`;
      backfillVariant = ["pending", "dispatched"].includes(String(state.pendingBackfill.status)) ? "emphasis" : "good";
    } else if (state.historyBackfillLoading) {
      backfillLabel = "补数：后台补齐中";
      backfillVariant = "emphasis";
    } else if (integrity && (Number(integrity.gap_count || 0) > 0 || Number(integrity.missing_bar_count || 0) > 0)) {
      backfillLabel = "补数：仍有缺口";
      backfillVariant = "warn";
    } else if (state.fullHistoryLoaded) {
      backfillLabel = "补数：历史已补齐";
      backfillVariant = "good";
    }
    applyHeaderChipState(els.statusBackfillChip, {
      label: backfillLabel,
      variant: backfillVariant,
    });

    const viewportSummary = state.chartEventModel?.viewportSummary
      || (state.snapshot?.candles?.length ? (els.chartViewportMeta?.textContent || "视图已初始化") : "视图：未初始化");
    applyHeaderChipState(els.statusViewportChip, {
      label: `视图：${viewportSummary.replace(/^视图：/, "")}`,
      variant: state.chartEventModel?.shownClusterCount ? "emphasis" : "",
      title: els.chartViewportMeta?.textContent || viewportSummary,
    });

    applyHeaderChipState(els.statusSyncChip, {
      label: formatSyncLabel(state.topBar.lastSyncedAt),
    });
    persistWorkbenchState();
  }


  function updateAnnotationLifecycle() {
    return planLifecycleEngine.updateAnnotationLifecycle();
  }

  let pendingMemoryRefreshTimer = null;
  let pendingAnnotationLifecycleTimer = null;
  const memoryRefreshQueue = new Set();

  function queueSessionMemoryRefresh(sessionIds = [], { forceServer = true, delay = 220 } = {}) {
    if (state.snapshotLoading) {
      return;
    }
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

  function queueAnnotationLifecycleRefresh({ delay = 1200, refreshMemory = true, forceServer = true } = {}) {
    if (state.snapshotLoading) {
      return;
    }
    if (pendingAnnotationLifecycleTimer) {
      clearTimeout(pendingAnnotationLifecycleTimer);
    }
    pendingAnnotationLifecycleTimer = window.setTimeout(() => {
      const startedAt = performance.now();
      pendingAnnotationLifecycleTimer = null;
      const changedSessionIds = updateAnnotationLifecycle();
      if (refreshMemory && changedSessionIds?.length) {
        queueSessionMemoryRefresh(changedSessionIds, { forceServer, delay: 260 });
      }
      annotationPanelController.renderAnnotationPanel();
      state.perf.deferredAnnotationMs = Math.round(performance.now() - startedAt);
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
    [els.analysisTypeSelect, els.analysisRangeSelect].forEach((select) => {
      const currentOption = select?.selectedOptions?.[0];
      if (currentOption && currentOption.hidden) {
        const fallback = Array.from(select.options).find((option) => !option.hidden);
        if (fallback) {
          select.value = fallback.value;
        }
      }
    });
    [
      [els.manualRegionButton, hasManualRegions],
      [els.selectedBarButton, hasSelectedBar],
      [els.liveDepthButton, hasLiveDepth],
    ].forEach(([button, visible]) => {
      if (!button) {
        return;
      }
      button.hidden = !visible;
      button.disabled = !visible;
    });
  }

  let liveRefreshInterval = null;

  function getTimeframeMinutes(timeframe) {
    const minutesByTimeframe = {
      "1m": 1,
      "5m": 5,
      "15m": 15,
      "30m": 30,
      "1h": 60,
      "1d": 1440,
    };
    return minutesByTimeframe[timeframe] || 1;
  }

  function getMaxBarsForTimeframe(timeframe) {
    const timeframeMinutes = getTimeframeMinutes(timeframe);
    return Math.max(1, Math.ceil((7 * 24 * 60) / timeframeMinutes));
  }

  function buildCandleSignature(candle) {
    if (!candle) {
      return "";
    }
    return [
      candle.started_at || "",
      candle.open ?? "",
      candle.high ?? "",
      candle.low ?? "",
      candle.close ?? "",
      candle.volume ?? "",
    ].join(":");
  }

  function applyLiveResponseMeta(response) {
    const integrityHash = response?.integrity ? JSON.stringify(response.integrity) : null;
    const integrityChanged = integrityHash !== state.lastLiveTailIntegrityHash;
    state.integrity = response?.integrity || state.integrity;
    state.pendingBackfill = response?.latest_backfill_request || state.pendingBackfill;
    state.lastLiveTailIntegrityHash = integrityHash;
    return { integrityChanged };
  }

  function shouldReloadSnapshotForLiveResponse(response, merged) {
    if (!response) {
      return false;
    }
    if (response.snapshot_refresh_required || response.reload_snapshot) {
      return true;
    }
    if (response.integrity_changed && !merged) {
      return true;
    }
    return false;
  }

  function mergeLiveTailIntoSnapshot(response, timeframe) {
    if (!state.snapshot?.candles?.length || !response?.candles?.length) {
      return { merged: false, requiresReload: false, updateType: "full_reset" };
    }
    const preservedEventAnnotations = (Array.isArray(state.snapshot.event_annotations) ? state.snapshot.event_annotations : [])
      .filter((item) => item?.source_kind !== "collector");
    const liveEventAnnotations = Array.isArray(response.event_annotations) ? response.event_annotations : [];
    const preservedFocusRegions = (Array.isArray(state.snapshot.focus_regions) ? state.snapshot.focus_regions : [])
      .filter((item) => !(typeof item?.region_id === "string" && item.region_id.startsWith("focus-")));
    const liveFocusRegions = Array.isArray(response.focus_regions) ? response.focus_regions : [];
    const previousLiveTail = state.snapshot?.live_tail && typeof state.snapshot.live_tail === "object"
      ? state.snapshot.live_tail
      : {};
    const nextLiveTail = {
      ...previousLiveTail,
      instrument_symbol: response.instrument_symbol ?? previousLiveTail.instrument_symbol ?? state.snapshot.instrument_symbol ?? null,
      display_timeframe: response.display_timeframe ?? previousLiveTail.display_timeframe ?? state.snapshot.display_timeframe ?? null,
      latest_observed_at: response.latest_observed_at ?? previousLiveTail.latest_observed_at ?? null,
      latest_price: response.latest_price ?? previousLiveTail.latest_price ?? null,
      best_bid: response.best_bid ?? previousLiveTail.best_bid ?? null,
      best_ask: response.best_ask ?? previousLiveTail.best_ask ?? null,
      source_message_count: response.source_message_count ?? previousLiveTail.source_message_count ?? 0,
      trade_summary: response.trade_summary ?? previousLiveTail.trade_summary ?? null,
      significant_liquidity: Array.isArray(response.significant_liquidity)
        ? response.significant_liquidity
        : (Array.isArray(previousLiveTail.significant_liquidity) ? previousLiveTail.significant_liquidity : []),
      same_price_replenishment: Array.isArray(response.same_price_replenishment)
        ? response.same_price_replenishment
        : (Array.isArray(previousLiveTail.same_price_replenishment) ? previousLiveTail.same_price_replenishment : []),
      active_initiative_drive: response.active_initiative_drive ?? previousLiveTail.active_initiative_drive ?? null,
      active_post_harvest_response: response.active_post_harvest_response ?? previousLiveTail.active_post_harvest_response ?? null,
      integrity: response.integrity ?? previousLiveTail.integrity ?? null,
    };
    const existingCandles = Array.isArray(state.snapshot.candles) ? [...state.snapshot.candles] : [];
    const incomingCandles = response.candles.filter((item) => item?.started_at);
    if (!existingCandles.length || !incomingCandles.length) {
      return { merged: false, requiresReload: false, updateType: "full_reset" };
    }
    const alignedIndex = existingCandles.findIndex((bar) => bar.started_at === incomingCandles[0].started_at);
    if (alignedIndex < 0) {
      const lastExisting = existingCandles[existingCandles.length - 1];
      if (!lastExisting || new Date(incomingCandles[0].started_at) <= new Date(lastExisting.started_at)) {
        return { merged: false, requiresReload: true, updateType: "full_reset" };
      }
      const seamGapMs = new Date(incomingCandles[0].started_at).getTime() - new Date(lastExisting.ended_at || lastExisting.started_at).getTime();
      const maxSeamGapMs = getTimeframeMinutes(timeframe) * 2 * 60 * 1000;
      if (Number.isFinite(seamGapMs) && seamGapMs > maxSeamGapMs) {
        return { merged: false, requiresReload: true, updateType: "full_reset" };
      }
      existingCandles.push(...incomingCandles);
    } else {
      existingCandles.splice(alignedIndex, existingCandles.length - alignedIndex, ...incomingCandles);
    }
    const deduped = [];
    const seen = new Set();
    existingCandles.forEach((bar) => {
      if (!bar?.started_at || seen.has(bar.started_at)) {
        return;
      }
      seen.add(bar.started_at);
      deduped.push(bar);
    });
    deduped.sort((left, right) => new Date(left.started_at) - new Date(right.started_at));
    const previousCandles = state.snapshot.candles;
    const previousLength = previousCandles.length;
    const previousLastSignature = buildCandleSignature(previousCandles[previousCandles.length - 1]);
    const nextCandles = deduped.slice(-getMaxBarsForTimeframe(timeframe));
    state.snapshot = {
      ...state.snapshot,
      live_tail: nextLiveTail,
      candles: nextCandles,
      event_annotations: [...preservedEventAnnotations, ...liveEventAnnotations],
      focus_regions: [...preservedFocusRegions, ...liveFocusRegions],
      window_end: response.latest_observed_at ?? state.snapshot.window_end,
    };
    const nextLastSignature = buildCandleSignature(nextCandles[nextCandles.length - 1]);
    const updateType = (nextCandles.length === previousLength || nextCandles.length === previousLength + 1)
      && previousLastSignature !== nextLastSignature
      ? "tail_update"
      : "full_reset";
    return { merged: true, requiresReload: false, updateType };
  }

  function syncRelativeWindowToNow() {
    const preset = state.quickRanges.find((item) => item.value === els.quickRangeSelect?.value);
    if (preset?.days) {
      applyWindowPreset(els.displayTimeframe.value, preset.days);
      return true;
    }
    syncCacheKey();
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
        const { integrityChanged } = applyLiveResponseMeta(response);
        const mergeResult = mergeLiveTailIntoSnapshot(response, timeframe);
        const needsReload = shouldReloadSnapshotForLiveResponse(response, mergeResult.merged) || mergeResult.requiresReload;

        if (needsReload) {
          await handleBuildWithForceRefresh({ syncRelativeWindow: true });
          return;
        }
        if (integrityChanged && !mergeResult.merged) {
          await handleBuildWithForceRefresh({ syncRelativeWindow: true });
          return;
        }
        if (mergeResult.merged) {
          state.lastChartUpdateType = mergeResult.updateType;
          state.topBar.lastSyncedAt = response.latest_observed_at || new Date().toISOString();
          renderChart();
          renderSidebarSnapshot();
        }
      } catch (error) {
        console.warn("实时刷新失败:", error);
      }
    }, 5000);
  }

  function renderCoreSnapshot() {
    const startedAt = performance.now();
    renderChart();
    updateDynamicAnalysisVisibility();
    updateHeaderStatus();
    state.perf.coreRenderMs = Math.round(performance.now() - startedAt);
    if (state.snapshot?.candles?.length) {
      startLiveRefresh();
    }
  }

  function renderViewportDerivedSurfaces() {
    renderDrawers({ state, els });
    updateHeaderStatus();
  }

  function renderSidebarSnapshot() {
    const startedAt = performance.now();
    renderViewportDerivedSurfaces();
    updateDynamicAnalysisVisibility();
    state.perf.sidebarRenderMs = Math.round(performance.now() - startedAt);
  }

  function renderAiSurface() {
    renderAiThreadTabs();
    renderAiChat();
    renderEventScribePanel();
    renderReplyExtractionPanel();
    renderContractNav();
  }

  function renderAnnotationSurface({ skipLifecycle = false } = {}) {
    if (!skipLifecycle) {
      queueAnnotationLifecycleRefresh({ delay: 1200, refreshMemory: true, forceServer: true });
      return;
    }
    annotationPanelController.renderAnnotationPanel();
  }

  function renderDeferredSurfaces() {
    renderAiSurface();
    renderAnnotationSurface({ skipLifecycle: false });
  }

  function renderSnapshot() {
    renderCoreSnapshot();
    renderSidebarSnapshot();
    renderDeferredSurfaces();
  }

  async function runBuildFlow({ forceRefresh = false, syncRelativeWindow = false } = {}) {
    const previous = !!els.forceRebuild?.checked;
    if (syncRelativeWindow) {
      syncRelativeWindowToNow();
    }
    if (els.forceRebuild) {
      els.forceRebuild.checked = !!forceRefresh;
    }
    try {
      await actions.handleBuild();
      state.topBar.lastSyncedAt = new Date().toISOString();
      persistWorkbenchState();
      renderAiSurface();
    } finally {
      if (els.forceRebuild) {
        els.forceRebuild.checked = previous;
      }
    }
  }

  async function handleBuildWithForceRefresh({ syncRelativeWindow = true } = {}) {
    await runBuildFlow({ forceRefresh: true, syncRelativeWindow });
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
    if (isDockedAiLayout()) {
      openAiSidebar();
      return;
    }
    const isOpen = els.aiSidebar?.classList.contains("open");
    if (isOpen) {
      closeAiSidebar();
    } else {
      openAiSidebar();
    }
  }

  function openAiSidebar() {
    if (!els.aiSidebar) return;
    state.aiSidebarOpen = true;
    syncAiSidebarViewportState();
  }

  function closeAiSidebar() {
    if (!els.aiSidebar) return;
    if (isDockedAiLayout()) {
      openAiSidebar();
      return;
    }
    state.aiSidebarOpen = false;
    syncAiSidebarViewportState();
  }

  function getLatestAssistantMessage(session) {
    return [...(session?.messages || [])].reverse().find((item) => item.role === "assistant" && String(item.content || "").trim()) || null;
  }

  function getLatestUserMessage(session) {
    return [...(session?.messages || [])].reverse().find((item) => item.role === "user" && String(item.content || "").trim()) || null;
  }

  function buildSecondaryMessageMarkup(message) {
    const role = message?.role === "assistant" ? "assistant" : "user";
    const title = role === "assistant"
      ? (message?.replyTitle || message?.meta?.replyTitle || "事件判断")
      : "你";
    return `
      <article class="secondary-chat-message ${role}" data-secondary-message-id="${escapeHtml(message?.message_id || "")}">
        <div class="secondary-chat-head">
          <strong>${escapeHtml(title)}</strong>
          <span class="meta">${escapeHtml(role === "assistant" ? "Event Scribe AI" : "用户")}</span>
        </div>
        <div class="secondary-chat-body">${escapeHtml(String(message?.content || "").trim() || (role === "assistant" ? "事件整理中…" : ""))}</div>
      </article>
    `;
  }

  function extractReplyCandidatesFromText(text, meta = {}) {
    const content = String(text || "").trim();
    if (!content) {
      return [];
    }
    const items = [];
    const seen = new Set();
    const priceValues = [];
    const pushItem = (item) => {
      if (!item) {
        return;
      }
      const key = item.stableKey || `${item.type}:${item.price ?? ""}:${item.priceLow ?? ""}:${item.priceHigh ?? ""}:${item.sessionId ?? ""}:${item.messageId ?? ""}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      items.push(item);
    };
    const messageScopeId = meta.messageId || meta.sessionId || "msg";
    const sourceRole = meta.sourceRole || "analyst";
    const sourceActor = meta.sourceActor || (sourceRole === "scribe" ? "事件判断 AI" : "行情分析 AI");
    const sourceTitle = meta.sourceTitle || "AI 提取";
    const observedAt = meta.observedAt || null;
    const summary = summarizeText(content, 120);
    const rangeRegex = /(\d{3,6}(?:\.\d+)?)[\s]*(?:-|~|到|至)[\s]*(\d{3,6}(?:\.\d+)?)/g;
    let rangeMatch;
    while ((rangeMatch = rangeRegex.exec(content)) !== null) {
      const low = Number(rangeMatch[1]);
      const high = Number(rangeMatch[2]);
      if (!Number.isFinite(low) || !Number.isFinite(high)) {
        continue;
      }
      const priceLow = Math.min(low, high);
      const priceHigh = Math.max(low, high);
      pushItem({
        id: `${meta.messageId || meta.sessionId || "msg"}-zone-${rangeMatch.index}-${priceLow}-${priceHigh}`,
        stableKey: `${messageScopeId}:zone:${priceLow}:${priceHigh}`,
        type: "zone",
        label: /支撑|需求|回踩/.test(content) ? "支撑区域" : /阻力|压力|供给/.test(content) ? "阻力区域" : "候选区域",
        priceLow,
        priceHigh,
        category: /风险|失效|放弃|谨慎/.test(content) ? "trapped" : "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summary,
      });
    }
    const priceRegex = /\d{3,6}(?:\.\d+)?/g;
    let priceMatch;
    while ((priceMatch = priceRegex.exec(content)) !== null) {
      const price = Number(priceMatch[0]);
      if (!Number.isFinite(price)) {
        continue;
      }
      priceValues.push(price);
      pushItem({
        id: `${messageScopeId}-price-${priceMatch.index}-${price}`,
        stableKey: `${messageScopeId}:price:${price}`,
        type: /止损|失效|风险/.test(content) ? "risk" : "price",
        label: /止损/.test(content)
          ? "止损位"
          : /止盈|目标/.test(content)
            ? "目标位"
            : /入场|回踩/.test(content)
              ? "入场位"
              : /失效|跌破|站不上|风险/.test(content)
                ? "风险位"
                : "关键价位",
        price,
        category: /止损|失效|跌破|站不上|风险/.test(content) ? "trapped" : "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summary,
      });
    }
    const riskHint = content.match(/(?:风险|失效|谨慎|放弃|跌破|站不上|不能追|不要追)[^。；\n]*/);
    if (riskHint) {
      pushItem({
        id: `${messageScopeId}-risk-${riskHint.index || 0}`,
        stableKey: `${messageScopeId}:risk:${riskHint[0]}`,
        type: "risk",
        label: "风险提示",
        price: priceValues[0] ?? null,
        category: "trapped",
        sourceRole,
        sourceActor,
        sourceTitle,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summarizeText(riskHint[0], 96),
      });
    }
    const planHint = content.match(/(?:做多|做空|观望|等待确认|突破跟随|回踩接多|反抽做空|计划|脚本)[^。；\n]*/);
    if (planHint) {
      pushItem({
        id: `${messageScopeId}-plan-${planHint.index || 0}`,
        stableKey: `${messageScopeId}:plan:${planHint[0]}`,
        type: "plan",
        label: /观望|等待/.test(planHint[0]) ? "观望计划" : /做空|反抽/.test(planHint[0]) ? "空头计划" : "多头计划",
        price: priceValues[0] ?? null,
        category: "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summarizeText(planHint[0], 96),
      });
    }
    return items;
  }

  function buildReplyExtractionItems() {
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const sessions = [
      getSessionByRole(symbol, "analyst"),
      getSessionByRole(symbol, "scribe"),
    ].filter(Boolean);
    const candidateMap = new Map();
    const pushCandidate = (item) => {
      if (!item?.id) {
        return;
      }
      if (!candidateMap.has(item.id)) {
        candidateMap.set(item.id, item);
      }
    };

    sessions.forEach((session) => {
      const sessionRole = getWorkspaceRole(session);
      (state.aiAnnotations || [])
        .filter((annotation) => annotation.session_id === session.id)
        .forEach((annotation) => {
          const annotationType = String(annotation.type || "").toLowerCase();
          const normalizedType = annotation.price_low != null || annotation.price_high != null
            ? (/no_trade|risk|invalid/.test(annotationType) ? "risk" : "zone")
            : (/stop|risk|invalid/.test(annotationType) ? "risk" : /plan|entry|profit|target/.test(annotationType) ? "plan" : "price");
          pushCandidate({
            id: `annotation-${annotation.id}`,
            stableKey: `annotation:${annotation.id}`,
            type: normalizedType,
            label: annotation.label || annotation.type || "AI 标记",
            price: annotation.entry_price ?? annotation.target_price ?? annotation.stop_price ?? null,
            priceLow: annotation.price_low ?? null,
            priceHigh: annotation.price_high ?? null,
            category: normalizedType === "risk" ? "trapped" : "events",
            excerpt: summarizeText(annotation.reason || annotation.label || "", 100),
            sourceRole: sessionRole,
            sourceActor: sessionRole === "scribe" ? "事件判断 AI" : "行情分析 AI",
            sourceTitle: session.title || (sessionRole === "scribe" ? "事件整理 AI" : "行情分析 AI"),
            messageId: annotation.message_id || null,
            sessionId: session.id,
            observedAt: annotation.started_at || annotation.created_at || annotation.updated_at || null,
          });
        });
      [...(session.messages || [])]
        .filter((message) => message.role === "assistant" || message.role === "user")
        .slice(-6)
        .forEach((message) => {
          extractReplyCandidatesFromText(message.content, {
            sessionId: session.id,
            messageId: message.message_id,
            sourceRole: sessionRole,
            sourceActor: message.role === "user"
              ? "交易员"
              : (sessionRole === "scribe" ? "事件判断 AI" : "行情分析 AI"),
            sourceTitle: message.role === "user"
              ? `${session.title || "会话"} / 用户消息`
              : (message.replyTitle || session.title || (sessionRole === "scribe" ? "事件整理 AI" : "行情分析 AI")),
            observedAt: message.created_at || message.updated_at || null,
          }).forEach(pushCandidate);
        });
    });
    return Array.from(candidateMap.values())
      .map((item) => hydrateReplyCandidateState(symbol, item))
      .sort((left, right) => {
        if (left.ignored !== right.ignored) {
          return left.ignored ? 1 : -1;
        }
        if ((left.pinned || false) !== (right.pinned || false)) {
          return left.pinned ? -1 : 1;
        }
        const rightTime = Date.parse(right.observedAt || "") || 0;
        const leftTime = Date.parse(left.observedAt || "") || 0;
        return rightTime - leftTime;
      })
      .slice(0, 36);
  }

  function setHoverOverlayItem(item = null) {
    state.eventStreamHoverItem = item || null;
    window.dispatchEvent(new CustomEvent("replay-workbench:hover-item-changed"));
  }

  async function ensureScribeSessionForSymbol(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const existing = getSessionByRole(normalizedSymbol, "scribe");
    if (existing) {
      rememberSymbolWorkspaceSession(existing);
      return existing;
    }
    const created = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
      workspaceRole: "scribe",
      activate: false,
    });
    rememberSymbolWorkspaceSession(created);
    return created;
  }

  async function createFreshScribeSession(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const count = state.aiThreads.filter((item) => {
      const itemSymbol = String(item.symbol || item.contractId || item.memory?.symbol || "").trim().toUpperCase();
      return itemSymbol === normalizedSymbol && getWorkspaceRole(item) === "scribe";
    }).length + 1;
    const title = `${normalizedSymbol}-事件-${String(count).padStart(2, "0")}`;
    const session = await createBackendSession({
      title,
      symbol: normalizedSymbol,
      contractId: normalizedSymbol,
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
      activate: false,
      workspaceRole: "scribe",
    });
    rememberSymbolWorkspaceSession(session);
    return session;
  }

  async function sendEventScribeMessage() {
    const message = String(els.eventScribeInput?.value || "").trim();
    if (!message) {
      renderStatusStrip([{ label: "请先输入事件整理问题。", variant: "warn" }]);
      els.eventScribeInput?.focus();
      return;
    }
    const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
    session.draftText = "";
    session.draft = "";
    session.loadingFromServer = true;
    renderEventScribePanel();
    try {
      const analystSession = getSessionByRole(state.topBar?.symbol, "analyst");
      const latestAnalystReply = getLatestAssistantMessage(analystSession);
      const latestAnalystQuestion = getLatestUserMessage(analystSession);
      await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          replay_ingestion_id: state.currentReplayIngestionId || null,
          preset: "general",
          user_input: message,
          selected_block_ids: [],
          pinned_block_ids: [],
          include_memory_summary: true,
          include_recent_messages: true,
          analysis_type: "event_timeline",
          analysis_range: "current_window",
          analysis_style: "standard",
          model: session.activeModel || null,
          attachments: [],
          extra_context: {
            analyst_latest_question: latestAnalystQuestion?.content || "",
            analyst_latest_reply: latestAnalystReply?.content || "",
          },
        }),
      });
      const hydrated = await hydrateSessionFromServer(session.id, { activate: false });
      if (hydrated) {
        hydrated.loadingFromServer = false;
        rememberSymbolWorkspaceSession(hydrated);
      }
      renderStatusStrip([{ label: "事件整理 AI 已更新。", variant: "good" }]);
    } catch (error) {
      session.loadingFromServer = false;
      session.draftText = message;
      session.draft = message;
      renderStatusStrip([{ label: error.message || "事件整理 AI 发送失败。", variant: "warn" }]);
    }
    renderSnapshot();
  }

  function renderEventScribePanel() {
    if (!els.eventScribePanel) {
      return;
    }
    const session = getSessionByRole(state.topBar?.symbol, "scribe");
    const latestAnalystReply = getLatestAssistantMessage(getSessionByRole(state.topBar?.symbol, "analyst"));
    if (els.eventScribeSessionLabel) {
      els.eventScribeSessionLabel.textContent = session?.title || "尚未建立事件整理会话";
    }
    if (els.eventScribeInput && document.activeElement !== els.eventScribeInput) {
      els.eventScribeInput.value = session?.draftText || session?.draft || "";
    }
    if (els.eventScribeSendButton) {
      els.eventScribeSendButton.disabled = !session || !!session.loadingFromServer;
      els.eventScribeSendButton.textContent = session?.loadingFromServer ? "整理中…" : "发送到事件判断 AI";
    }
    if (els.eventScribeMirrorButton) {
      els.eventScribeMirrorButton.disabled = !latestAnalystReply;
    }
    if (!session) {
      els.eventScribeThread.innerHTML = `<div class="secondary-chat-empty">当前品种还没有事件整理会话。</div>`;
      return;
    }
    if (session.loadingFromServer) {
      els.eventScribeThread.innerHTML = `
        ${(session.messages || []).slice(-4).map((message) => buildSecondaryMessageMarkup(message)).join("")}
        <div class="secondary-chat-empty">事件判断 AI 正在整理关键事件…</div>
      `;
      return;
    }
    const messages = (session.messages || []).slice(-8);
    els.eventScribeThread.innerHTML = messages.length
      ? messages.map((message) => buildSecondaryMessageMarkup(message)).join("")
      : `<div class="secondary-chat-empty">可向事件判断 AI 发送“整理关键价位 / 区域 / 风险 / 事件时间线”等问题。</div>`;
  }

  function renderReplyExtractionPanel() {
    if (!els.replyExtractionPanel || !els.replyExtractionList || !els.replyExtractionSummary) {
      return;
    }
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const extractionState = getReplyExtractionState();
    const filter = extractionState.filter || "all";
    const showIgnored = !!extractionState.showIgnored;
    const allItems = buildReplyExtractionItems();
    const counts = {
      price: allItems.filter((item) => item.type === "price").length,
      zone: allItems.filter((item) => item.type === "zone").length,
      risk: allItems.filter((item) => item.type === "risk").length,
      plan: allItems.filter((item) => item.type === "plan").length,
      ignored: allItems.filter((item) => item.ignored).length,
    };
    const items = allItems.filter((item) => {
      if (!showIgnored && item.ignored) {
        return false;
      }
      return filter === "all" ? true : item.type === filter;
    });
    els.replyExtractionFilterBar?.querySelectorAll("[data-reply-extraction-filter]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.replyExtractionFilter === filter);
    });
    if (els.replyExtractionShowIgnoredButton) {
      els.replyExtractionShowIgnoredButton.classList.toggle("is-active", showIgnored);
      els.replyExtractionShowIgnoredButton.textContent = showIgnored ? "隐藏已忽略" : "显示已忽略";
    }
    els.replyExtractionSummary.textContent = allItems.length
      ? `${symbol} 已提取 ${allItems.length} 条候选，当前显示 ${items.length} 条。价位 ${counts.price} / 区域 ${counts.zone} / 风险 ${counts.risk} / 计划 ${counts.plan}${counts.ignored ? ` / 已忽略 ${counts.ignored}` : ""}。`
      : "等待 AI 回复后提取关键价位、区域与风险位置。";
    if (!items.length) {
      els.replyExtractionList.innerHTML = `<div class="reply-extraction-empty">${allItems.length ? "当前筛选条件下没有候选项。" : "暂无候选提取结果。"}</div>`;
      return;
    }
    const typeLabelMap = {
      price: "价位",
      zone: "区域",
      risk: "风险",
      plan: "计划",
    };
    els.replyExtractionList.innerHTML = items.map((item) => {
      const priceLabel = item.type === "zone"
        ? `${item.priceLow?.toFixed?.(2) ?? item.priceLow} - ${item.priceHigh?.toFixed?.(2) ?? item.priceHigh}`
        : (item.price != null ? `${item.price?.toFixed?.(2) ?? item.price}` : "未定位价格");
      const sourceRoleLabel = item.sourceActor || (item.sourceRole === "scribe" ? "事件判断 AI" : "行情分析 AI");
      const ignoredClass = item.ignored ? " is-ignored" : "";
      return `
        <article class="reply-extraction-item${ignoredClass}" data-extraction-id="${escapeHtml(item.id)}" data-candidate-key="${escapeHtml(item.candidateKey || item.id)}">
          <div class="reply-extraction-head">
            <strong>${escapeHtml(item.label || (item.type === "zone" ? "候选区域" : "关键价位"))}</strong>
            <div class="reply-extraction-chip-row">
              <span class="chip">${escapeHtml(typeLabelMap[item.type] || "候选")}</span>
              <span class="chip">${escapeHtml(sourceRoleLabel)}</span>
            </div>
          </div>
          <div class="reply-extraction-price">${escapeHtml(priceLabel)}</div>
          <div class="reply-extraction-meta">${escapeHtml(item.sourceTitle || "AI 提取")}</div>
          <p>${escapeHtml(item.excerpt || "等待确认")}</p>
          <div class="reply-extraction-actions">
            <button type="button" class="secondary tiny" data-extraction-action="source" data-extraction-id="${escapeHtml(item.id)}">来源</button>
            <button type="button" class="secondary tiny" data-extraction-action="ignore" data-extraction-id="${escapeHtml(item.id)}">${item.ignored ? "恢复" : "忽略"}</button>
          </div>
        </article>
      `;
    }).join("");
    const openExtractionSource = (item) => {
      if (!item?.messageId) {
        return;
      }
      const targetSession = item.sessionId
        ? state.aiThreads.find((entry) => entry.id === item.sessionId)
        : null;
      if (!targetSession) {
        return;
      }
      if (getWorkspaceRole(targetSession) === "analyst") {
        setActiveThread(targetSession.id, targetSession.title, targetSession);
        jumpToMessageWhenReady(item.messageId);
        return;
      }
      rememberSymbolWorkspaceSession(targetSession);
      renderEventScribePanel();
      jumpToSecondaryMessageWhenReady(item.messageId);
    };
    els.replyExtractionList.querySelectorAll("[data-extraction-id]").forEach((node) => {
      const item = items.find((entry) => entry.id === node.dataset.extractionId);
      node.addEventListener("mouseenter", () => setHoverOverlayItem(item));
      node.addEventListener("mouseleave", () => setHoverOverlayItem(null));
      node.addEventListener("click", (event) => {
        const actionButton = event.target?.closest("[data-extraction-action]");
        if (actionButton) {
          if (!item) {
            return;
          }
          if (actionButton.dataset.extractionAction === "source") {
            openExtractionSource(item);
            return;
          }
          if (actionButton.dataset.extractionAction === "ignore") {
            updateReplyCandidateMeta(symbol, item.candidateKey || item.id, {
              status: item.ignored ? "candidate" : "ignored",
            });
            renderReplyExtractionPanel();
          }
          return;
        }
        openExtractionSource(item);
      });
    });
  }

  function renderContractNav() {
    if (!els.aiContractNav) return;
    const getThreadTimestamp = (thread) => {
      const candidates = [
        thread?.updatedAt,
        thread?.memory?.last_updated_at,
        thread?.messages?.[thread.messages.length - 1]?.updated_at,
        thread?.messages?.[thread.messages.length - 1]?.created_at,
        thread?.createdAt,
      ];
      for (const candidate of candidates) {
        if (!candidate) {
          continue;
        }
        const timestamp = Date.parse(candidate);
        if (Number.isFinite(timestamp)) {
          return timestamp;
        }
      }
      return 0;
    };
    const hasThreadDraft = (thread) => {
      const textDraft = String(thread?.draftText || thread?.draft || "").trim();
      const attachmentDraft = Array.isArray(thread?.draftAttachments)
        ? thread.draftAttachments.length
        : (Array.isArray(thread?.attachments) ? thread.attachments.length : 0);
      return !!textDraft || attachmentDraft > 0;
    };
    const isBlankThread = (thread) => {
      const attachmentCount = Array.isArray(thread?.draftAttachments)
        ? thread.draftAttachments.length
        : (Array.isArray(thread?.attachments) ? thread.attachments.length : 0);
      return !(thread?.messages?.length)
        && !String(thread?.draftText || thread?.draft || "").trim()
        && attachmentCount === 0
        && !(thread?.selectedPromptBlockIds?.length)
        && !(thread?.mountedReplyIds?.length);
    };
    const shouldSurfaceAnalystThread = (thread) => {
      if (!thread) {
        return false;
      }
      if (!isBlankThread(thread)) {
        return true;
      }
      return thread.id === state.activeAiThreadId;
    };
    const sortThreads = (a, b, symbol = null) => {
      const aActive = a.id === state.activeAiThreadId;
      const bActive = b.id === state.activeAiThreadId;
      if (aActive !== bActive) {
        return aActive ? -1 : 1;
      }
      if (symbol) {
        const aMatches = (a.symbol || a.contractId || a.memory?.symbol || "") === symbol;
        const bMatches = (b.symbol || b.contractId || b.memory?.symbol || "") === symbol;
        if (aMatches !== bMatches) {
          return aMatches ? -1 : 1;
        }
      }
      if (!!a.pinned !== !!b.pinned) {
        return a.pinned ? -1 : 1;
      }
      if (!!a.activePlanId !== !!b.activePlanId) {
        return a.activePlanId ? -1 : 1;
      }
      if (hasThreadDraft(a) !== hasThreadDraft(b)) {
        return hasThreadDraft(a) ? -1 : 1;
      }
      if ((a.unreadCount || 0) !== (b.unreadCount || 0)) {
        return (b.unreadCount || 0) - (a.unreadCount || 0);
      }
      return getThreadTimestamp(b) - getThreadTimestamp(a);
    };
    const contracts = new Map();
    state.aiThreads
      .filter((thread) => getWorkspaceRole(thread) === "analyst")
      .filter((thread) => shouldSurfaceAnalystThread(thread))
      .forEach((thread) => {
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
    contractArray.forEach((contract) => {
      contract.threads.sort((a, b) => sortThreads(a, b, contract.symbol));
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
          const preferredThread = [...contract.threads].sort((a, b) => sortThreads(a, b, symbol))[0];
          if (preferredThread) {
            rememberSymbolWorkspaceSession(preferredThread);
          }
          els.instrumentSymbol.value = symbol;
          state.topBar.symbol = symbol;
          void activateSymbolWorkspace(symbol).then(() => renderSnapshot());
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
      card.addEventListener("click", async () => {
        const skillId = card.dataset.skillId;
        const skill = skills.find((s) => s.id === skillId);
        if (skill) {
          updateComposerDraft(skill.prompt);
          setSkillPanelVisible(false);
          await aiChat.handleAiChatSend();
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
    installButtonFeedback();
    syncQuickActionButtonState();

    // AI 侧边栏控制
    els.aiSidebarTrigger?.addEventListener("click", toggleAiSidebar);
    els.aiSidebarCloseButton?.addEventListener("click", closeAiSidebar);
    els.aiSidebarPinButton?.addEventListener("click", () => {
      state.aiSidebarPinned = !state.aiSidebarPinned;
      writeStorage("aiSidebarState", { open: state.aiSidebarOpen, pinned: state.aiSidebarPinned });
      syncAiSidebarPinButtonState();
      renderStatusStrip([{ label: state.aiSidebarPinned ? "AI 侧栏固定偏好已开启" : "AI 侧栏固定偏好已关闭", variant: "emphasis" }]);
    });

    // 技能面板控制
    els.aiChatInput?.addEventListener("input", (e) => {
      const value = e.target.value;
      if (value.startsWith("@") || value.startsWith("/")) {
        setSkillPanelVisible(true);
      } else if (els.aiSkillPanel && !els.aiSkillPanel.hidden) {
        setSkillPanelVisible(false);
      }
    });

    // 快速操作按钮
    els.aiKlineAnalysisButton?.addEventListener("click", async () => {
      setButtonBusy(els.aiKlineAnalysisButton, true);
      try {
        await aiChat.handlePresetAnalysis("recent_20_bars", "请分析当前K线图表并给出交易建议。", false);
        renderSnapshot();
      } catch (error) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      } finally {
        setButtonBusy(els.aiKlineAnalysisButton, false);
      }
    });
    els.aiMoreButton?.addEventListener("click", () => {
      setSkillPanelVisible(els.aiSkillPanel?.hidden ?? true, { announce: true });
    });
    els.aiAttachmentButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择文件后会附加到当前会话。", accept: defaultAttachmentAccept });
    });
    els.aiScreenshotButton?.addEventListener("click", async () => {
      try {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      } catch (error) {
        renderStatusStrip([{ label: error.message || "图表截图失败。", variant: "warn" }]);
      }
    });
    els.aiVoiceButton?.addEventListener("click", startVoiceCapture);
    els.aiVoiceInputButton?.addEventListener("click", startVoiceCapture);

    // 初始化技能面板
    initializeSkillPanel();

    // 恢复侧边栏状态
    const sidebarState = readStorage("aiSidebarState", { open: false, pinned: false });
    state.aiSidebarOpen = !!sidebarState.open;
    state.aiSidebarPinned = !!sidebarState.pinned;
    syncAiSidebarViewportState({ persist: false });
    syncAiSidebarPinButtonState();
    syncQuickActionButtonState();
    let resizeTimer = null;
    window.addEventListener("resize", () => {
      if (resizeTimer) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(() => {
        applyLayoutWidths();
        renderSnapshot();
      }, 120);
    });
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
      state.topBar.symbol = nextSymbol;
      persistWorkbenchState();
      syncCacheKey();
      updateHeaderStatus();
      try {
        await syncSessionsFromServer({ symbol: nextSymbol, activateFirst: false });
        await activateSymbolWorkspace(nextSymbol);
      } catch (error) {
        console.warn("切换品种同步会话失败:", error);
        await activateSymbolWorkspace(nextSymbol);
      }
      // 切换品种时重新加载图表
      void handleBuildWithForceRefresh({ syncRelativeWindow: true });
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

    function zoomTimeAxis(factor) {
      const chart = window._lwChartState?.chartInstance;
      if (chart) {
        const range = chart.timeScale().getVisibleLogicalRange?.();
        if (!range) {
          chart.timeScale().fitContent();
          return;
        }
        const center = (range.from + range.to) / 2;
        const span = Math.max(10, (range.to - range.from) * factor);
        chart.timeScale().setVisibleLogicalRange({
          from: center - span / 2,
          to: center + span / 2,
        });
        return;
      }
      if (!state.snapshot?.candles?.length || !state.chartView) {
        return;
      }
      const total = state.snapshot.candles.length;
      const currentSpan = Math.max(20, state.chartView.endIndex - state.chartView.startIndex + 1);
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
      renderChart();
      renderViewportDerivedSurfaces();
    }

    function zoomPriceAxis(factor) {
      if (!state.snapshot?.candles?.length || !state.chartView || state.chartView.yMin == null || state.chartView.yMax == null) {
        return;
      }
      const currentSpan = state.chartView.yMax - state.chartView.yMin;
      const targetSpan = Math.max(0.5, currentSpan * factor);
      const center = (state.chartView.yMin + state.chartView.yMax) / 2;
      state.chartView.yMin = center - targetSpan / 2;
      state.chartView.yMax = center + targetSpan / 2;
      renderChart();
      renderViewportDerivedSurfaces();
    }

    function resetChartView() {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      state.chartView = createDefaultChartView(state.snapshot.candles.length);
      const chart = window._lwChartState?.chartInstance;
      if (chart) {
        chart.timeScale().setVisibleLogicalRange({
          from: state.chartView.startIndex,
          to: state.chartView.endIndex,
        });
      }
      renderChart();
      renderViewportDerivedSurfaces();
    }

    els.zoomInButton?.addEventListener("click", () => zoomTimeAxis(0.6));
    els.zoomOutButton?.addEventListener("click", () => zoomTimeAxis(1.6));
    els.zoomPriceInButton?.addEventListener("click", () => zoomPriceAxis(0.84));
    els.zoomPriceOutButton?.addEventListener("click", () => zoomPriceAxis(1.2));
    els.resetViewButton?.addEventListener("click", () => resetChartView());
    els.chartContainer?.addEventListener("wheel", (event) => {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      event.preventDefault();
      if (event.shiftKey) {
        zoomPriceAxis(event.deltaY < 0 ? 0.84 : 1.2);
        return;
      }
      zoomTimeAxis(event.deltaY < 0 ? 0.8 : 1.25);
    }, { passive: false });

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
      renderStatusStrip([{ label: "当前工作台设置已导出。", variant: "good" }]);
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
      await runButtonAction(els.buildButton, async () => {
        await runBuildFlow({ forceRefresh: false, syncRelativeWindow: false });
      }, { silentError: true });
    });
    els.refreshAllButton.addEventListener("click", async () => {
      await runButtonAction(els.refreshAllButton, async () => {
        await runBuildFlow({ forceRefresh: true, syncRelativeWindow: true });
      }, { silentError: true });
    });
    els.restoreLayoutButton.addEventListener("click", () => {
      const persistedLayout = readStorage("layout", null);
      if (persistedLayout) {
        state.layout = { ...state.layout, ...persistedLayout };
        renderStatusStrip([{ label: "已恢复上次布局。", variant: "good" }]);
      } else {
        renderStatusStrip([{ label: "还没有可恢复的历史布局。", variant: "warn" }]);
      }
      applyLayoutWidths();
      renderSnapshot();
    });

    els.aiNewThreadButton.addEventListener("click", async () => {
      await aiChat.createNewThread();
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
    els.eventScribeSendButton?.addEventListener("click", async () => {
      await sendEventScribeMessage();
    });
    els.eventScribeInput?.addEventListener("input", async (event) => {
      const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
      session.draftText = event.target.value;
      session.draft = event.target.value;
      rememberSymbolWorkspaceSession(session);
      renderEventScribePanel();
    });
    els.eventScribeInput?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await sendEventScribeMessage();
      }
    });
    els.eventScribeMirrorButton?.addEventListener("click", async () => {
      const analystSession = getSessionByRole(state.topBar?.symbol, "analyst");
      const latestAssistantReply = getLatestAssistantMessage(analystSession);
      const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
      if (!latestAssistantReply) {
        renderStatusStrip([{ label: "当前还没有可整理的行情分析回复。", variant: "warn" }]);
        return;
      }
      const nextDraft = `请提取下面这条回复中的关键价位、区域、风险、事件顺序，并整理成可审阅候选项：\n\n${latestAssistantReply.content}`;
      session.draftText = nextDraft;
      session.draft = nextDraft;
      rememberSymbolWorkspaceSession(session);
      if (els.eventScribeInput) {
        els.eventScribeInput.value = nextDraft;
        els.eventScribeInput.focus();
      }
      renderEventScribePanel();
    });
    els.eventScribeNewSessionButton?.addEventListener("click", async () => {
      await createFreshScribeSession(state.topBar?.symbol);
      renderSnapshot();
    });
    els.eventStreamFilterBar?.querySelectorAll("[data-event-stream-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        state.eventStreamFilter = button.dataset.eventStreamFilter || "all";
        persistWorkbenchState();
        renderChart();
      });
    });
    els.replyExtractionFilterBar?.querySelectorAll("[data-reply-extraction-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        getReplyExtractionState().filter = button.dataset.replyExtractionFilter || "all";
        persistWorkbenchState();
        renderReplyExtractionPanel();
      });
    });
    els.replyExtractionShowIgnoredButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      extractionState.showIgnored = !extractionState.showIgnored;
      persistWorkbenchState();
      renderReplyExtractionPanel();
    });
    els.saveRegionButton?.addEventListener("click", async () => {
      await runButtonAction(els.saveRegionButton, async () => {
        await actions.handleSaveRegion();
        renderSnapshot();
      }, { silentError: true });
    });
    els.saveRegionQuickButton?.addEventListener("click", async () => {
      await runButtonAction(els.saveRegionQuickButton, async () => {
        await actions.handleSaveRegion();
        renderSnapshot();
      }, { silentError: true });
    });
    els.recordEntryButton?.addEventListener("click", async () => {
      await runButtonAction(els.recordEntryButton, async () => {
        await actions.handleRecordEntry();
        renderSnapshot();
      }, { silentError: true });
    });

    els.aiChatThread?.addEventListener("click", async (event) => {
      const button = event.target?.closest("button[data-message-action]");
      if (!button) {
        return;
      }
      const action = button.dataset.messageAction;
      const messageId = button.dataset.messageId;
      if (!messageId || !action) {
        return;
      }
      if (action === "regenerate") {
        await aiChat.regenerateMessage(messageId);
        renderSnapshot();
        return;
      }
      if (["show", "focus", "jump", "unmount"].includes(action)) {
        focusPlanOnChart({
          action,
          messageId,
          sessionId: getActiveThread()?.id || state.activeAiThreadId,
          planId: null,
        });
        return;
      }
      renderSnapshot();
    });

    els.analysisSendCurrentButton.addEventListener("click", async () => {
      await runButtonAction(els.analysisSendCurrentButton, async () => {
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
    });
    els.analysisSendNewButton.addEventListener("click", async () => {
      await runButtonAction(els.analysisSendNewButton, async () => {
        await aiChat.handlePresetAnalysis(els.analysisTypeSelect.value, `请基于当前${els.analysisRangeSelect.value}做${els.analysisStyleSelect.value}风格分析。`, true);
        renderSnapshot();
      });
    });
    els.gammaAutoDiscoverButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaAutoDiscoverButton, async () => {
        await loadGammaAnalysis({ autoDiscoverLatest: true });
      }, { silentError: true });
    });
    els.gammaLoadButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaLoadButton, async () => {
        await loadGammaAnalysis({ autoDiscoverLatest: false });
      }, { silentError: true });
    });
    els.gammaSendCurrentButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaSendCurrentButton, async () => {
        await sendGammaToChat(false);
        renderSnapshot();
      });
    });
    els.gammaSendNewButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaSendNewButton, async () => {
        await sendGammaToChat(true);
        renderSnapshot();
      });
    });

    els.recent20BarsButton.addEventListener("click", async () => {
      await aiChat.handlePresetAnalysis("recent_20_bars", "请分析最近20根K线并给出交易计划。", false);
      renderSnapshot();
    });
    els.recent20MinutesButton.addEventListener("click", async () => {
      await aiChat.handlePresetAnalysis("recent_20_minutes", "请分析最近20分钟并给出交易计划。", false);
      renderSnapshot();
    });
    els.focusRegionsButton.addEventListener("click", async () => {
      await aiChat.handlePresetAnalysis("focus_regions", "请围绕当前重点区域给出计划。", false);
      renderSnapshot();
    });
    els.liveDepthButton.addEventListener("click", async () => {
      await aiChat.handlePresetAnalysis("live_depth", "请结合当前盘口结构给出建议。", false);
      renderSnapshot();
    });
    els.manualRegionButton.addEventListener("click", async () => {
      await runButtonAction(els.manualRegionButton, async () => {
        await aiChat.handlePresetAnalysis("manual_region", aiChat.buildManualRegionAnalysisPrompt(), false);
        renderSnapshot();
      });
    });
    els.selectedBarButton.addEventListener("click", async () => {
      await runButtonAction(els.selectedBarButton, async () => {
        await aiChat.handlePresetAnalysis("selected_bar", aiChat.buildSelectedBarAnalysisPrompt(), false);
        renderSnapshot();
      });
    });

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
      if (window.confirm("确认归档当前会话？")) {
        deleteActiveThread();
        renderSnapshot();
      }
    });
    els.sessionMoreButton?.addEventListener("click", async () => {
      if (!els.sessionMoreMenu) {
        return;
      }
      const willOpen = els.sessionMoreMenu.hidden;
      if (!willOpen) {
        els.sessionMoreMenu.hidden = true;
        return;
      }
      els.sessionMoreMenu.hidden = false;
      renderSnapshot();
      if (syncSessionsFromServer) {
        try {
          await syncSessionsFromServer({ activateFirst: false });
          renderSnapshot();
          els.sessionMoreMenu.hidden = false;
        } catch (error) {
          console.warn("刷新会话工作区失败:", error);
        }
      }
      els.sessionMoreMenu.querySelector("[data-session-search-input]")?.focus();
    });
    els.clearPinnedPlanButton?.addEventListener("click", () => {
      state.pinnedPlanId = null;
      const session = getActiveThread();
      session.activePlanId = null;
      persistSessions();
      renderSnapshot();
    });

    els.addAttachmentButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择要附加到当前会话的文件。", accept: defaultAttachmentAccept });
    });
    els.attachmentInput?.addEventListener("change", async () => {
      const files = Array.from(els.attachmentInput.files || []);
      try {
        const mapped = await Promise.all(files.map((file) => mapFileToAttachment(file)));
        addAttachments(mapped);
        renderStatusStrip([{ label: mapped.length ? `已添加 ${mapped.length} 个附件。` : "未选择附件。", variant: mapped.length ? "good" : "warn" }]);
        renderSnapshot();
        focusComposerInput();
      } catch (error) {
        renderStatusStrip([{ label: error.message || "读取附件失败。", variant: "warn" }]);
      } finally {
        els.attachmentInput.value = "";
        els.attachmentInput.setAttribute("accept", defaultAttachmentAccept);
      }
    });
    els.chartScreenshotButton?.addEventListener("click", async () => {
      try {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      } catch (error) {
        renderStatusStrip([{ label: error.message || "图表截图失败。", variant: "warn" }]);
      }
    });
    els.chartToolbarScreenshotButton?.addEventListener("click", async () => {
      try {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      } catch (error) {
        renderStatusStrip([{ label: error.message || "图表截图失败。", variant: "warn" }]);
      }
    });
    els.externalScreenshotButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择一张外部截图图片。", accept: "image/*" });
    });
    els.clearAttachmentsButton?.addEventListener("click", () => {
      clearAttachments();
      renderStatusStrip([{ label: "当前会话附件已清空。", variant: "emphasis" }]);
      renderSnapshot();
    });

    modelSwitcherController.bindModelSwitcherActions();
    annotationPopoverController.bindAnnotationPopoverActions();

    els.rightResizeHandle.addEventListener("mousedown", (event) => {
      if (!isDockedAiLayout()) {
        return;
      }
      const startX = event.clientX;
      const startWidth = state.layout.chatWidth;
      const onMove = (moveEvent) => {
        state.layout.chatWidth = Math.max(
          DESKTOP_SIDEBAR_MIN,
          Math.min(DESKTOP_SIDEBAR_MAX, startWidth - (moveEvent.clientX - startX)),
        );
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
        setDrawerOpen(key, !state.drawerState[key]);
      });
      if (panel) {
        panel.style.display = state.drawerState[key] ? "block" : "none";
      }
    });
    syncDrawerTabState();
    syncBottomDrawerVisibility();

    els.chartEventRail?.addEventListener("click", (event) => {
      const button = event.target?.closest("[data-event-cluster-key]");
      if (!button) {
        return;
      }
      const clusterKey = button.dataset.eventClusterKey;
      if (!clusterKey) {
        return;
      }
      selectChartEventCluster(clusterKey, {
        centerChart: true,
        openContext: true,
        announce: true,
      });
    });

    [
      els.layerLargeOrders,
      els.layerAbsorption,
      els.layerIceberg,
      els.layerReplenishment,
      els.layerEvents,
      els.layerFocusRegions,
      els.layerManualRegions,
      els.layerOperatorEntries,
      els.layerAiAnnotations,
    ].forEach((input) => {
      input?.addEventListener("change", () => {
        persistLayerState();
        renderSnapshot();
      });
    });

    // 按钮绑定已在 replay_workbench_bindings.js 中处理，这里只处理 sendViewportButton
    if (els.sendViewportButton) {
      els.sendViewportButton.addEventListener("click", async () => {
        await runButtonAction(els.sendViewportButton, async () => {
          const summary = els.chartViewportMeta?.textContent || "当前可视区域";
          const session = getActiveThread();
          await aiChat.handleAiChat("general", `请基于当前图表可视区域继续分析：${summary}`, {
            id: session.id,
            title: session.title,
            symbol: session.symbol,
            contractId: session.contractId,
            timeframe: session.timeframe,
            windowRange: session.windowRange,
          });
          renderSnapshot();
        });
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
    applyLayerStateToInputs();
    syncCacheKey();
    try {
      await syncSessionsFromServer({ activateFirst: false, symbol: state.topBar.symbol });
    } catch (error) {
      console.warn("从后端同步会话失败:", error);
    }
    const restoredActiveSession = state.aiThreads.find((item) => item.id === state.activeAiThreadId);
    if (restoredActiveSession && getWorkspaceRole(restoredActiveSession) === "analyst") {
      rememberSymbolWorkspaceSession(restoredActiveSession);
    }
    try {
      await activateSymbolWorkspace(state.topBar.symbol);
    } catch (error) {
      console.warn("初始化按品种工作区失败:", error);
      const fallbackSession = getPreferredSessionForSymbol(state.topBar.symbol, { workspaceRole: "analyst" }) || state.aiThreads[0];
      if (fallbackSession) {
        setActiveThread(fallbackSession.id, fallbackSession.title, fallbackSession);
      }
    }
    renderSnapshot();
  }

  return {
    state,
    els,
    ensureChartView,
    buildCacheKey,
    syncCacheKey,
    renderSnapshot,
    updateHeaderStatus,
    renderViewportDerivedSurfaces,
    selectChartEventCluster,
    attachBindings,
    bootstrap,
    handleBuild: actions.handleBuild,
  };
}
