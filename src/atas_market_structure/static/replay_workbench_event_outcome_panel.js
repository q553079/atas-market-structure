import { escapeHtml } from "./replay_workbench_ui_utils.js";

function cloneArray(items) {
  return Array.isArray(items) ? [...items] : [];
}

function normalizeOutcomeLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return "pending";
  }
  return normalized;
}

function formatRate(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "--";
  }
  return `${Math.round(numeric * 100)}%`;
}

function buildOutcomeBadge(label, { compact = false } = {}) {
  const normalized = normalizeOutcomeLabel(label);
  return `<span class="event-outcome-badge ${compact ? "compact " : ""}${escapeHtml(normalized)}" data-outcome-badge="true">${escapeHtml(normalized)}</span>`;
}

function buildBucketList(title, buckets = []) {
  const items = cloneArray(buckets).slice(0, 4);
  if (!items.length) {
    return "";
  }
  return `
    <section class="event-outcome-section">
      <h4>${escapeHtml(title)}</h4>
      <div class="event-outcome-bucket-list">
        ${items.map((item) => `
          <div class="event-outcome-bucket">
            <strong>${escapeHtml(item.bucket_label || item.bucket_key || "--")}</strong>
            <span>${escapeHtml(`${item.success_count}/${item.settled_count || 0}`)}</span>
            <span>${escapeHtml(formatRate(item.accuracy_rate))}</span>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function resolvePlanEventId(plan = {}) {
  return String(
    plan?.event_id
    || plan?.source_event_id
    || plan?.payload?.event_id
    || plan?.raw_payload?.event_id
    || ""
  ).trim() || null;
}

export function createWorkbenchEventOutcomePanelController({
  state,
  els,
  eventApi,
  renderStatusStrip,
  persistWorkbenchState,
  getActiveThread,
  jumpToMessage = null,
  onPromptTraceRequested = null,
  onEventSelected = null,
}) {
  let bindingsInstalled = false;

  function getOutcomeState() {
    if (!state.eventOutcomeWorkbench || typeof state.eventOutcomeWorkbench !== "object") {
      state.eventOutcomeWorkbench = {
        sessionKey: null,
        loading: false,
        loaded: false,
        dirty: true,
        error: null,
        outcomes: [],
        summary: null,
        byKind: [],
        byTimeWindow: [],
        byAnalysisPreset: [],
        byModel: [],
        focusedEventId: null,
        lastLoadedAt: null,
      };
    }
    return state.eventOutcomeWorkbench;
  }

  function getOutcomeByEventId(eventId) {
    return cloneArray(getOutcomeState().outcomes).find((item) => String(item?.event_id || "").trim() === String(eventId || "").trim()) || null;
  }

  function markDirty() {
    getOutcomeState().dirty = true;
  }

  async function syncActiveSessionOutcomes({ force = false } = {}) {
    const outcomeState = getOutcomeState();
    const session = typeof getActiveThread === "function" ? getActiveThread() : null;
    if (!session?.id) {
      outcomeState.outcomes = [];
      outcomeState.summary = null;
      outcomeState.byKind = [];
      outcomeState.byTimeWindow = [];
      outcomeState.byAnalysisPreset = [];
      outcomeState.byModel = [];
      outcomeState.loaded = false;
      outcomeState.loading = false;
      renderOutcomeSurfaces();
      return null;
    }
    const sessionKey = `${session.id}|${session.symbol || ""}|${session.timeframe || ""}`;
    if (!force && !outcomeState.dirty && outcomeState.loaded && outcomeState.sessionKey === sessionKey) {
      return null;
    }
    outcomeState.loading = true;
    outcomeState.error = null;
    outcomeState.sessionKey = sessionKey;
    renderOutcomeSurfaces();
    try {
      const [outcomes, summary, byKind, byTimeWindow, byAnalysisPreset, byModel] = await Promise.all([
        eventApi.listEventOutcomes({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
        eventApi.getEventStatsSummary({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
        eventApi.getEventStatsByKind({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
        eventApi.getEventStatsByTimeWindow({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
        eventApi.getEventStatsByAnalysisPreset({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
        eventApi.getEventStatsByModel({ sessionId: session.id, symbol: session.symbol, timeframe: session.timeframe }),
      ]);
      outcomeState.outcomes = cloneArray(outcomes?.outcomes || []);
      outcomeState.summary = summary?.summary || null;
      outcomeState.byKind = cloneArray(byKind?.buckets || []);
      outcomeState.byTimeWindow = cloneArray(byTimeWindow?.buckets || []);
      outcomeState.byAnalysisPreset = cloneArray(byAnalysisPreset?.buckets || []);
      outcomeState.byModel = cloneArray(byModel?.buckets || []);
      outcomeState.loading = false;
      outcomeState.loaded = true;
      outcomeState.dirty = false;
      outcomeState.lastLoadedAt = new Date().toISOString();
      renderOutcomeSurfaces();
      return outcomeState.outcomes;
    } catch (error) {
      outcomeState.loading = false;
      outcomeState.error = error?.message || String(error);
      renderOutcomeSurfaces();
      renderStatusStrip?.([{ label: `Outcome Ledger 读取失败：${outcomeState.error}`, variant: "warn" }]);
      return null;
    } finally {
      persistWorkbenchState?.();
    }
  }

  function focusOutcomeForCandidate(candidate = null) {
    const outcomeState = getOutcomeState();
    outcomeState.focusedEventId = candidate?.event_id || null;
    renderOutcomeSurfaces();
    if (candidate?.event_id && !getOutcomeByEventId(candidate.event_id)) {
      void syncActiveSessionOutcomes({ force: true });
    }
    persistWorkbenchState?.();
    return true;
  }

  function focusOutcomeByEventId(eventId = null) {
    const outcomeState = getOutcomeState();
    outcomeState.focusedEventId = String(eventId || "").trim() || null;
    renderOutcomeSurfaces();
    if (outcomeState.focusedEventId && !getOutcomeByEventId(outcomeState.focusedEventId)) {
      void syncActiveSessionOutcomes({ force: true });
    }
    persistWorkbenchState?.();
    return true;
  }

  function renderSummaryPanel() {
    const outcomeState = getOutcomeState();
    if (!els.eventOutcomeSummary) {
      return;
    }
    if (outcomeState.loading && !outcomeState.loaded) {
      els.eventOutcomeSummary.innerHTML = `<div class="event-outcome-empty">正在刷新 Outcome Ledger…</div>`;
      return;
    }
    if (outcomeState.error && !outcomeState.loaded) {
      els.eventOutcomeSummary.innerHTML = `<div class="event-outcome-empty">Outcome Ledger 暂不可用。</div>`;
      return;
    }
    const summary = outcomeState.summary;
    if (!summary) {
      els.eventOutcomeSummary.innerHTML = `<div class="event-outcome-empty">当前会话还没有可统计的 outcome。</div>`;
      return;
    }
    els.eventOutcomeSummary.innerHTML = `
      <section class="event-outcome-section">
        <h4>Outcome Ledger</h4>
        <div class="event-outcome-metric-row">
          <span><strong>${escapeHtml(String(summary.total_count || 0))}</strong> tracked</span>
          <span><strong>${escapeHtml(String(summary.settled_count || 0))}</strong> settled</span>
          <span><strong>${escapeHtml(String(summary.open_count || 0))}</strong> open</span>
          <span><strong>${escapeHtml(formatRate(summary.accuracy_rate))}</strong> accuracy</span>
        </div>
        <div class="event-outcome-chip-row">
          ${buildOutcomeBadge("success", { compact: true })}<span>${escapeHtml(String(summary.success_count || 0))}</span>
          ${buildOutcomeBadge("failure", { compact: true })}<span>${escapeHtml(String(summary.failure_count || 0))}</span>
          ${buildOutcomeBadge("timeout", { compact: true })}<span>${escapeHtml(String(summary.timeout_count || 0))}</span>
          ${buildOutcomeBadge("inconclusive", { compact: true })}<span>${escapeHtml(String(summary.inconclusive_count || 0))}</span>
        </div>
      </section>
      ${buildBucketList("按事件类型", outcomeState.byKind)}
      ${buildBucketList("按时间段", outcomeState.byTimeWindow)}
      ${buildBucketList("按 Preset", outcomeState.byAnalysisPreset)}
      ${buildBucketList("按模型", outcomeState.byModel)}
    `;
  }

  function renderFocusPanel() {
    const outcomeState = getOutcomeState();
    if (!els.eventOutcomeFocus) {
      return;
    }
    const outcome = getOutcomeByEventId(outcomeState.focusedEventId);
    els.eventOutcomeFocus.hidden = !outcome;
    if (!outcome) {
      els.eventOutcomeFocus.innerHTML = "";
      return;
    }
    els.eventOutcomeFocus.innerHTML = `
      <div class="event-outcome-focus-card">
        <div class="event-outcome-focus-head">
          <div>
            <strong>${escapeHtml(outcome.event_id)}</strong>
            ${buildOutcomeBadge(outcome.outcome_label)}
          </div>
          <button type="button" class="secondary tiny" data-outcome-panel-action="close-focus">收起</button>
        </div>
        <div class="event-outcome-kv-grid">
          <span>kind</span><strong>${escapeHtml(outcome.event_kind || "--")}</strong>
          <span>preset</span><strong>${escapeHtml(outcome.analysis_preset || "--")}</strong>
          <span>model</span><strong>${escapeHtml(outcome.model_name || "--")}</strong>
          <span>window</span><strong>${escapeHtml(`${outcome.evaluation_window_start || "--"} -> ${outcome.evaluation_window_end || "--"}`)}</strong>
          <span>MFE / MAE</span><strong>${escapeHtml(`${outcome.mfe ?? "--"} / ${outcome.mae ?? "--"}`)}</strong>
          <span>reason</span><strong>${escapeHtml(outcome.metadata?.resolution_reason || "--")}</strong>
        </div>
        <div class="event-outcome-action-row">
          <button type="button" class="secondary tiny" data-outcome-panel-action="focus-event" data-event-id="${escapeHtml(outcome.event_id)}">定位事件</button>
          <button type="button" class="secondary tiny" data-outcome-panel-action="jump-source" data-message-id="${escapeHtml(outcome.source_message_id || "")}" ${outcome.source_message_id ? "" : "disabled"}>查看来源</button>
          <button type="button" class="secondary tiny" data-outcome-panel-action="open-prompt" data-event-id="${escapeHtml(outcome.event_id)}" ${outcome.source_prompt_trace_id ? "" : "disabled"}>查看 Prompt</button>
        </div>
      </div>
    `;
  }

  function decorateEventCards() {
    const outcomes = new Map(cloneArray(getOutcomeState().outcomes).map((item) => [String(item?.event_id || "").trim(), item]));
    els.eventStreamList?.querySelectorAll?.(".event-candidate-card[data-event-id]")?.forEach?.((node) => {
      node.querySelectorAll("[data-outcome-badge]").forEach((item) => item.remove());
      const badgeRow = node.querySelector(".event-candidate-badge-row");
      const outcome = outcomes.get(String(node.dataset.eventId || "").trim());
      if (!badgeRow || !outcome) {
        return;
      }
      badgeRow.insertAdjacentHTML("beforeend", buildOutcomeBadge(outcome.outcome_label, { compact: true }));
    });
  }

  function decoratePlanCards() {
    const outcomes = new Map(cloneArray(getOutcomeState().outcomes).map((item) => [String(item?.event_id || "").trim(), item]));
    const session = typeof getActiveThread === "function" ? getActiveThread() : null;
    const planById = new Map();
    cloneArray(session?.messages || []).forEach((message) => {
      const plans = Array.isArray(message?.meta?.planCards) ? message.meta.planCards : (Array.isArray(message?.planCards) ? message.planCards : []);
      cloneArray(plans).forEach((plan) => {
        const planId = String(plan?.id || plan?.plan_id || "").trim();
        if (planId) {
          planById.set(planId, plan);
        }
      });
    });
    els.aiChatThread?.querySelectorAll?.(".chat-plan-card[data-plan-id]")?.forEach?.((node) => {
      node.querySelectorAll("[data-outcome-badge]").forEach((item) => item.remove());
      const plan = planById.get(String(node.dataset.planId || "").trim());
      const eventId = resolvePlanEventId(plan);
      const outcome = eventId ? outcomes.get(eventId) : null;
      const head = node.querySelector(".chat-plan-card-head");
      if (!head || !outcome) {
        return;
      }
      head.insertAdjacentHTML("beforeend", buildOutcomeBadge(outcome.outcome_label, { compact: true }));
    });
  }

  function renderOutcomeSurfaces() {
    renderSummaryPanel();
    renderFocusPanel();
    decorateEventCards();
    decoratePlanCards();
  }

  function bindActions() {
    if (bindingsInstalled) {
      return;
    }
    bindingsInstalled = true;
    els.eventOutcomeFocus?.addEventListener("click", (event) => {
      const button = event.target?.closest?.("[data-outcome-panel-action]");
      if (!button) {
        return;
      }
      const action = button.dataset.outcomePanelAction;
      if (action === "close-focus") {
        getOutcomeState().focusedEventId = null;
        renderOutcomeSurfaces();
        return;
      }
      if (action === "focus-event") {
        onEventSelected?.(button.dataset.eventId);
        return;
      }
      if (action === "jump-source") {
        jumpToMessage?.(button.dataset.messageId);
        return;
      }
      if (action === "open-prompt") {
        const outcome = getOutcomeByEventId(button.dataset.eventId);
        if (outcome) {
          onPromptTraceRequested?.({
            source_prompt_trace_id: outcome.source_prompt_trace_id,
            source_message_id: outcome.source_message_id,
          });
        }
      }
    });
  }

  bindActions();

  return {
    markDirty,
    syncActiveSessionOutcomes,
    renderOutcomeSurfaces,
    focusOutcomeForCandidate,
    focusOutcomeByEventId,
    getOutcomeByEventId,
  };
}
