/*
 * Facade-only event panel orchestration.
 * Purpose: coordinate event-stream state, nearby-context presentation, and mutation flows.
 * Do not add new DOM-decoration or message-linking logic here.
 * Put new card/message decoration behavior into focused modules such as
 * `replay_workbench_event_message_decorations.js` and nearby-context derivation modules.
 */
import { escapeHtml, summarizeText } from "./replay_workbench_ui_utils.js";
import {
  canPromoteEventCandidate,
  formatEventCandidatePriceSummary,
  formatEventCandidateTimeSummary,
  getEventKindLabel,
  getEventLifecycleLabel,
  getEventPresentationState,
  getEventSourceLabel,
  isEventCandidateMountable,
} from "./replay_workbench_event_overlay.js";
import {
  captureContainerState,
  reconcileKeyedChildren,
  restoreContainerState,
  updateRegionMarkup,
} from "./replay_workbench_render_stability.js";
import { createWorkbenchEventMessageDecorations } from "./replay_workbench_event_message_decorations.js";

function toTimestamp(value) {
  const timestamp = new Date(value || 0).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function cloneArray(items) {
  return Array.isArray(items) ? [...items] : [];
}

function byEventId(items = []) {
  return new Map(items.map((item) => [String(item?.event_id || "").trim(), item]).filter(([id]) => !!id));
}

function upsertById(items = [], nextItem = null, idField = "event_id") {
  if (!nextItem) {
    return cloneArray(items);
  }
  const targetId = String(nextItem?.[idField] || "").trim();
  const nextItems = cloneArray(items).filter((item) => String(item?.[idField] || "").trim() !== targetId);
  nextItems.unshift(nextItem);
  return nextItems;
}

function sortCandidates(items = [], eventWorkbenchState = {}) {
  const lifecycleRank = {
    pinned: 0,
    mounted: 1,
    candidate: 2,
    confirmed: 3,
    promoted_plan: 4,
    ignored: 5,
    expired: 6,
    archived: 7,
  };
  return cloneArray(items).sort((left, right) => {
    const resolveRank = (candidate) => {
      const presentation = getEventPresentationState(candidate, eventWorkbenchState);
      const lifecycle = String(candidate.lifecycle_state || "").trim();
      if (presentation === "pinned" || presentation === "mounted") {
        return lifecycleRank[presentation];
      }
      if (presentation === "hidden" && lifecycle === "mounted") {
        return lifecycleRank.candidate;
      }
      return lifecycleRank[lifecycle] ?? 9;
    };
    const leftRank = resolveRank(left);
    const rightRank = resolveRank(right);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return toTimestamp(right.updated_at || right.created_at) - toTimestamp(left.updated_at || left.created_at);
  });
}

function formatConfidence(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return `${Math.round(numeric * 100)}%`;
}

function getDisplayLifecycleLabel(candidate, eventWorkbenchState) {
  const presentationState = getEventPresentationState(candidate, eventWorkbenchState);
  if (presentationState === "pinned") {
    return "Pinned";
  }
  if (presentationState === "mounted") {
    return "已上图";
  }
  if (String(candidate?.lifecycle_state || "").trim() === "mounted") {
    return "待固定";
  }
  return getEventLifecycleLabel(candidate?.lifecycle_state);
}

function collectCounts(candidates = [], eventWorkbenchState = {}) {
  return candidates.reduce((acc, candidate) => {
    const presentationState = getEventPresentationState(candidate, eventWorkbenchState);
    const lifecycle = String(candidate.lifecycle_state || "").trim();
    acc.total += 1;
    if (presentationState === "mounted" || presentationState === "pinned") {
      acc.mounted += 1;
    }
    if (lifecycle === "ignored") {
      acc.ignored += 1;
    }
    if (presentationState === "pinned") {
      acc.pinned += 1;
    }
    return acc;
  }, {
    total: 0,
    mounted: 0,
    ignored: 0,
    pinned: 0,
  });
}

function getFilteredCandidates(candidates = [], filterKind = "all") {
  const normalizedFilter = String(filterKind || "all").trim();
  if (!normalizedFilter || normalizedFilter === "all") {
    return candidates;
  }
  return candidates.filter((candidate) => String(candidate.candidate_kind || "").trim() === normalizedFilter);
}

function buildContextChips(nearbyContextItem = null) {
  if (!nearbyContextItem) {
    return [];
  }
  const chips = [];
  if (nearbyContextItem.flags?.reply_linked) {
    chips.push({ label: "当前回答", kind: "reply" });
  }
  if (nearbyContextItem.flags?.object_linked) {
    chips.push({ label: "图上对象", kind: "object" });
  }
  if (nearbyContextItem.crossDayAnchor) {
    chips.push({ label: "跨日锚点", kind: "cross-day" });
  }
  if (nearbyContextItem.flags?.fixed_anchor && !nearbyContextItem.crossDayAnchor) {
    chips.push({ label: "固定锚点", kind: "fixed" });
  }
  if (nearbyContextItem.visibleReason) {
    chips.push({ label: nearbyContextItem.visibleReason, kind: "reason" });
  }
  return chips.slice(0, 4);
}

function buildDockGroupMarkup(group = {}, eventWorkbenchState = {}) {
  const items = Array.isArray(group?.items) ? group.items : [];
  if (!items.length) {
    return "";
  }
  return `
    <section class="nearby-context-cluster event-nearby-group" data-nearby-group="${escapeHtml(group.key || "")}">
      <div class="event-nearby-group-head">
        <div class="event-nearby-group-copy">
          <span class="nearby-context-cluster-title">${escapeHtml(group.title || "附近事件")}</span>
          ${group.description ? `<p class="meta">${escapeHtml(group.description)}</p>` : ""}
        </div>
        <span class="event-candidate-badge lifecycle">${escapeHtml(String(items.length))}</span>
      </div>
      <div class="event-nearby-group-list">
        ${items.map((item) => buildCardMarkup(item.candidate, eventWorkbenchState, item)).join("")}
      </div>
    </section>
  `;
}

function buildDockGroupHeadMarkup(group = {}) {
  const items = Array.isArray(group?.items) ? group.items : [];
  return `
    <div class="event-nearby-group-copy">
      <span class="nearby-context-cluster-title">${escapeHtml(group.title || "附近事件")}</span>
      ${group.description ? `<p class="meta">${escapeHtml(group.description)}</p>` : ""}
    </div>
    <span class="event-candidate-badge lifecycle">${escapeHtml(String(items.length))}</span>
  `;
}

function buildDockGroupShellMarkup(group = {}) {
  return `
    <section class="nearby-context-cluster event-nearby-group" data-nearby-group="${escapeHtml(group.key || "")}">
      <div class="event-nearby-group-head"></div>
      <div class="event-nearby-group-list"></div>
    </section>
  `;
}

function buildHistorySummaryLabel(historyItems = []) {
  if (!historyItems.length) {
    return "查看更多";
  }
  const historicalCount = historyItems.filter((item) => item?.primaryContextKind === "historical").length;
  return historicalCount ? `查看更多 / 历史 ${historyItems.length}` : `查看更多 ${historyItems.length}`;
}

function buildHistoryMarkup(historyItems = [], eventWorkbenchState = {}) {
  if (!historyItems.length) {
    return "";
  }
  return `
    <details class="nearby-context-history-shell" data-nearby-group="history">
      <summary class="nearby-context-history-summary">${escapeHtml(buildHistorySummaryLabel(historyItems))}</summary>
      <div class="nearby-context-history-list">
        ${historyItems.map((item) => buildCardMarkup(item.candidate, eventWorkbenchState, item)).join("")}
      </div>
    </details>
  `;
}

function buildHistoryShellMarkup(historyItems = []) {
  return `
    <details class="nearby-context-history-shell" data-nearby-group="history">
      <summary class="nearby-context-history-summary">${escapeHtml(buildHistorySummaryLabel(historyItems))}</summary>
      <div class="nearby-context-history-list"></div>
    </details>
  `;
}

function buildDockMarkup(model = {}, eventWorkbenchState = {}) {
  const groups = Array.isArray(model?.groups) ? model.groups : [];
  const historyItems = Array.isArray(model?.historyItems) ? model.historyItems : [];
  const groupMarkup = groups.map((group) => buildDockGroupMarkup(group, eventWorkbenchState)).join("");
  const historyMarkup = buildHistoryMarkup(historyItems, eventWorkbenchState);
  if (!groupMarkup && !historyMarkup) {
    return `<div class="event-stream-empty">${escapeHtml(model?.emptyMessage || "当前窗口和筛选条件下没有事件。")}</div>`;
  }
  return `
    <div class="event-nearby-dock">
      ${groupMarkup || `<div class="event-stream-empty">${escapeHtml(model?.emptyMessage || "当前窗口附近没有前台事件。")}</div>`}
      ${historyMarkup}
    </div>
  `;
}

function buildCardMarkup(candidate, eventWorkbenchState, nearbyContextItem = null) {
  const presentationState = getEventPresentationState(candidate, eventWorkbenchState);
  const selected = String(eventWorkbenchState.selectedEventId || "").trim() === candidate.event_id;
  const hovered = String(eventWorkbenchState.hoverEventId || "").trim() === candidate.event_id;
  const pinned = Array.isArray(eventWorkbenchState.pinnedEventIds) && eventWorkbenchState.pinnedEventIds.includes(candidate.event_id);
  const primaryContextKind = String(nearbyContextItem?.primaryContextKind || "historical").trim() || "historical";
  const sourceMessageId = nearbyContextItem?.presentation?.sourceMessageId || candidate.source_message_id || "";
  const disabledPromote = !canPromoteEventCandidate(candidate);
  const disabledMount = !isEventCandidateMountable(candidate);
  const confidenceText = formatConfidence(candidate.confidence);
  const sourceText = getEventSourceLabel(candidate.source_type);
  const lifecycleText = getDisplayLifecycleLabel(candidate, eventWorkbenchState);
  const priceText = formatEventCandidatePriceSummary(candidate);
  const timeText = formatEventCandidateTimeSummary(candidate);
  const title = candidate.title || `${getEventKindLabel(candidate.candidate_kind)}事件`;
  const contextChips = buildContextChips(nearbyContextItem);
  const cardClasses = [
    "event-candidate-card",
    `kind-${String(candidate.candidate_kind || "unknown").replace(/_/g, "-")}`,
    `state-${String(candidate.lifecycle_state || "candidate").replace(/_/g, "-")}`,
    selected ? "is-selected" : "",
    hovered ? "is-hovered" : "",
    pinned ? "is-pinned" : "",
    presentationState === "mounted" ? "is-mounted" : "",
    presentationState === "pinned" ? "is-presentation-pinned" : "",
    `context-${primaryContextKind.replace(/_/g, "-")}`,
  ].filter(Boolean).join(" ");
  return `
    <article
      class="${cardClasses}"
      data-event-id="${escapeHtml(candidate.event_id)}"
      data-candidate-kind="${escapeHtml(candidate.candidate_kind || "")}"
      data-presentation-state="${escapeHtml(presentationState)}"
      data-nearby-context-kind="${escapeHtml(primaryContextKind)}"
      data-source-message-id="${escapeHtml(sourceMessageId)}"
      title="${escapeHtml(`${title} · ${priceText} · ${timeText}`)}"
    >
      <div class="event-candidate-card-head">
        <div class="event-candidate-title-wrap">
          <strong>${escapeHtml(title)}</strong>
          <div class="event-candidate-kicker">${escapeHtml(getEventKindLabel(candidate.candidate_kind))}</div>
        </div>
        <div class="event-candidate-badge-row">
          <span class="event-candidate-badge lifecycle">${escapeHtml(lifecycleText)}</span>
          ${confidenceText ? `<span class="event-candidate-badge confidence">${escapeHtml(confidenceText)}</span>` : ""}
          ${pinned ? `<span class="event-candidate-badge pinned">Pinned</span>` : ""}
        </div>
      </div>
      <p class="event-candidate-summary">${escapeHtml(summarizeText(candidate.summary || "暂无摘要。", 160))}</p>
      ${contextChips.length ? `
        <div class="event-candidate-context-row">
          ${contextChips.map((chip) => `<span class="event-candidate-badge context ${escapeHtml(chip.kind || "context")}">${escapeHtml(chip.label)}</span>`).join("")}
        </div>
      ` : ""}
      <div class="event-candidate-meta-grid">
        <span>${escapeHtml(priceText)}</span>
        <span>${escapeHtml(timeText)}</span>
        <span>${escapeHtml(sourceText)}</span>
      </div>
      <div class="event-candidate-actions">
        <button type="button" class="secondary tiny" data-event-action="spotlight" data-event-id="${escapeHtml(candidate.event_id)}">高亮</button>
        <button type="button" class="secondary tiny" data-event-action="mount" data-event-id="${escapeHtml(candidate.event_id)}" ${disabledMount ? "disabled" : ""}>固定上图</button>
        <button type="button" class="secondary tiny" data-event-action="promote" data-event-id="${escapeHtml(candidate.event_id)}" ${disabledPromote ? "disabled" : ""}>转计划</button>
        <details class="event-candidate-menu">
          <summary class="secondary tiny">更多</summary>
          <div class="event-candidate-menu-sheet">
            <button type="button" class="secondary tiny" data-event-action="pin" data-event-id="${escapeHtml(candidate.event_id)}">${pinned ? "取消 Pin" : "Pin"}</button>
            <button type="button" class="secondary tiny" data-event-action="source" data-event-id="${escapeHtml(candidate.event_id)}" ${candidate.source_message_id ? "" : "disabled"}>查看来源</button>
            <button type="button" class="secondary tiny" data-event-action="prompt" data-event-id="${escapeHtml(candidate.event_id)}">查看 Prompt</button>
            <button type="button" class="secondary tiny" data-event-action="outcome" data-event-id="${escapeHtml(candidate.event_id)}">查看 Outcome</button>
            <button type="button" class="secondary tiny" data-event-action="ignore" data-event-id="${escapeHtml(candidate.event_id)}">忽略</button>
          </div>
        </details>
      </div>
    </article>
  `;
}

function buildMessageEventChipMarkup(candidate) {
  const lifecycleText = getEventLifecycleLabel(candidate.lifecycle_state);
  return `
    <button
      type="button"
      class="message-event-chip"
      data-message-event-id="${escapeHtml(candidate.event_id)}"
      title="${escapeHtml(`${candidate.title || getEventKindLabel(candidate.candidate_kind)} · ${lifecycleText}`)}"
    >${escapeHtml(candidate.title || getEventKindLabel(candidate.candidate_kind))}</button>
  `;
}

function buildMessageEventRowSignature(candidates = []) {
  return JSON.stringify((Array.isArray(candidates) ? candidates : []).map((candidate) => ({
    event_id: candidate?.event_id || "",
    lifecycle_state: candidate?.lifecycle_state || "",
    updated_at: candidate?.updated_at || "",
    title: candidate?.title || "",
  })));
}

export function createWorkbenchEventPanelController({
  state,
  els,
  eventApi,
  nearbyContext = null,
  renderStatusStrip,
  persistWorkbenchState,
  getActiveThread,
  ensureActiveSessionPersisted,
  focusEventCandidateOnChart,
  jumpToEventSource,
  afterMutation = null,
  onPromptTraceRequested = null,
  onOutcomeRequested = null,
  onSurfaceItemsChanged = null,
}) {
  let panelBindingsInstalled = false;
  let messageBindingsInstalled = false;
  let hoverDismissBindingsInstalled = false;
  let lastSurfaceItemsSignature = null;

  const decorationController = createWorkbenchEventMessageDecorations({
    els,
    getEventState,
    getCandidateById,
    getActiveThread,
    sortCandidates,
    buildMessageEventChipMarkup,
    buildMessageEventRowSignature,
  });
  let lastRenderedListSignature = "";
  let lastRenderedEmptyState = "";

  function getEventState() {
    return state.eventWorkbench || {};
  }

  function dispatchOverlayChanged() {
    window.dispatchEvent(new CustomEvent("replay-workbench:hover-item-changed"));
  }

  function buildCandidateRenderSignature(items = []) {
    return JSON.stringify(cloneArray(items).map((item) => {
      const candidate = item?.candidate || item;
      return {
        event_id: candidate?.event_id || "",
        updated_at: candidate?.updated_at || "",
        created_at: candidate?.created_at || "",
        lifecycle_state: candidate?.lifecycle_state || "",
        candidate_kind: candidate?.candidate_kind || "",
        title: candidate?.title || "",
        summary: candidate?.summary || "",
        confidence: candidate?.confidence ?? null,
        price_lower: candidate?.price_lower ?? null,
        price_upper: candidate?.price_upper ?? null,
        price_ref: candidate?.price_ref ?? null,
        anchor_start_ts: candidate?.anchor_start_ts || "",
        anchor_end_ts: candidate?.anchor_end_ts || "",
        source_type: candidate?.source_type || "",
        source_message_id: candidate?.source_message_id || "",
        source_prompt_trace_id: candidate?.source_prompt_trace_id || "",
        nearby_context_kind: item?.primaryContextKind || "historical",
        visible_reason: item?.visibleReason || "",
        cross_day_anchor: !!item?.crossDayAnchor,
        reply_linked: !!item?.flags?.reply_linked,
        object_linked: !!item?.flags?.object_linked,
      };
    }));
  }

  function buildDockTopLevelItems(nearbyContextModel = {}) {
    const groups = Array.isArray(nearbyContextModel?.groups) ? nearbyContextModel.groups : [];
    const historyItems = Array.isArray(nearbyContextModel?.historyItems) ? nearbyContextModel.historyItems : [];
    const items = groups.map((group) => ({
      key: group.key || "",
      signature: JSON.stringify({
        key: group.key || "",
        title: group.title || "",
        description: group.description || "",
        count: Array.isArray(group.items) ? group.items.length : 0,
      }),
      markup: buildDockGroupShellMarkup(group),
    }));
    if (historyItems.length) {
      items.push({
        key: "history",
        signature: JSON.stringify({
          key: "history",
          count: historyItems.length,
          label: buildHistorySummaryLabel(historyItems),
        }),
        markup: buildHistoryShellMarkup(historyItems),
      });
    }
    return items.filter((item) => item.key);
  }

  function ensureNearbyDockShell() {
    if (!els.eventStreamList) {
      return null;
    }
    if (els.eventStreamList.dataset.renderMode !== "nearby-dock") {
      const rendered = updateRegionMarkup(
        els.eventStreamList,
        '<div class="event-nearby-dock" data-render-key="event-nearby-dock"></div>',
        "nearby-dock-shell:v1",
      );
      if (rendered !== false || els.eventStreamList.querySelector(".event-nearby-dock")) {
        els.eventStreamList.dataset.renderMode = "nearby-dock";
      }
    }
    return els.eventStreamList.querySelector(".event-nearby-dock");
  }

  function renderNearbyDock(nearbyContextModel = {}, eventState = {}) {
    if (!els.eventStreamList) {
      return false;
    }
    const dockSnapshot = captureContainerState(els.eventStreamList, {
      keyAttribute: "data-event-id",
      anchorSelector: "[data-event-id], [data-nearby-group]",
      detailsSelector: "details.nearby-context-history-shell[data-nearby-group]",
    });
    const dock = ensureNearbyDockShell();
    if (!dock) {
      return false;
    }
    const groups = Array.isArray(nearbyContextModel?.groups) ? nearbyContextModel.groups : [];
    const historyItems = Array.isArray(nearbyContextModel?.historyItems) ? nearbyContextModel.historyItems : [];
    const topLevelItems = buildDockTopLevelItems(nearbyContextModel);
    reconcileKeyedChildren(dock, topLevelItems, {
      keyAttribute: "data-nearby-group",
      itemSelector: ".event-nearby-group[data-nearby-group], .nearby-context-history-shell[data-nearby-group]",
    });

    groups.forEach((group) => {
      const groupNode = dock.querySelector(`.event-nearby-group[data-nearby-group="${CSS.escape(String(group.key || ""))}"]`);
      if (!(groupNode instanceof HTMLElement)) {
        return;
      }
      const headNode = groupNode.querySelector(".event-nearby-group-head");
      const listNode = groupNode.querySelector(".event-nearby-group-list");
      if (headNode instanceof HTMLElement) {
        updateRegionMarkup(
          headNode,
          buildDockGroupHeadMarkup(group),
          JSON.stringify({
            title: group.title || "",
            description: group.description || "",
            count: Array.isArray(group.items) ? group.items.length : 0,
          }),
        );
      }
      if (listNode instanceof HTMLElement) {
        reconcileKeyedChildren(
          listNode,
          (Array.isArray(group.items) ? group.items : []).map((item) => ({
            key: item?.candidate?.event_id || "",
            signature: buildCandidateRenderSignature([item]),
            markup: buildCardMarkup(item.candidate, eventState, item),
          })).filter((item) => item.key),
          {
            keyAttribute: "data-event-id",
            itemSelector: ".event-candidate-card[data-event-id]",
          },
        );
      }
    });

    const historyNode = dock.querySelector('.nearby-context-history-shell[data-nearby-group="history"]');
    if (historyNode instanceof HTMLElement) {
      const summaryNode = historyNode.querySelector(".nearby-context-history-summary");
      const listNode = historyNode.querySelector(".nearby-context-history-list");
      if (summaryNode instanceof HTMLElement) {
        updateRegionMarkup(
          summaryNode,
          escapeHtml(buildHistorySummaryLabel(historyItems)),
          JSON.stringify({
            count: historyItems.length,
            label: buildHistorySummaryLabel(historyItems),
          }),
        );
      }
      if (listNode instanceof HTMLElement) {
        reconcileKeyedChildren(
          listNode,
          historyItems.map((item) => ({
            key: item?.candidate?.event_id || "",
            signature: buildCandidateRenderSignature([item]),
            markup: buildCardMarkup(item.candidate, eventState, item),
          })).filter((item) => item.key),
          {
            keyAttribute: "data-event-id",
            itemSelector: ".event-candidate-card[data-event-id]",
          },
        );
      }
    }

    restoreContainerState(els.eventStreamList, dockSnapshot, {
      keyAttribute: "data-event-id",
      detailsSelector: "details.nearby-context-history-shell[data-nearby-group]",
    });
    const restoredHistoryNode = dock.querySelector('.nearby-context-history-shell[data-nearby-group="history"]');
    if (restoredHistoryNode instanceof HTMLDetailsElement) {
      restoredHistoryNode.open = historyItems.length > 0 && eventState.historyExpanded === true;
    }
    return !els.eventStreamList.querySelector("[data-render-fallback]");
  }

  function buildNearbyContextModel(sortedCandidates = []) {
    if (nearbyContext?.buildEventPanelModel) {
      return nearbyContext.buildEventPanelModel({
        candidates: sortedCandidates,
        filterKind: state.eventStreamFilter || "all",
      });
    }
    const filteredCandidates = getFilteredCandidates(sortedCandidates, state.eventStreamFilter || "all");
    const items = sortedCandidates.map((candidate) => ({
      candidate,
      primaryContextKind: "nearby",
      visibleReason: "当前窗口发生",
      crossDayAnchor: false,
      flags: {
        nearby: true,
        influencing: false,
        fixed_anchor: false,
        historical: false,
        reply_linked: false,
        object_linked: false,
        visible_window: true,
      },
    }));
    const filteredItems = filteredCandidates.map((candidate) => ({
      candidate,
      primaryContextKind: "nearby",
      visibleReason: "当前窗口发生",
      crossDayAnchor: false,
      flags: {
        nearby: true,
        influencing: false,
        fixed_anchor: false,
        historical: false,
        reply_linked: false,
        object_linked: false,
        visible_window: true,
      },
    }));
    return {
      items,
      surfaceItems: items,
      filteredItems,
      visibleItems: filteredItems,
      historyItems: [],
      groups: [{
        key: "nearby",
        title: "刚发生",
        description: "当前窗口内事件。",
        items: filteredItems,
      }],
      summaryText: sortedCandidates.length
        ? `当前前台 ${sortedCandidates.length} 条事件。`
        : "当前会话还没有正式 EventCandidate。",
      emptyMessage: "当前窗口和筛选条件下没有事件。",
    };
  }

  function renderEmptyState(message) {
    const nextSignature = `empty:${message}`;
    if (
      els.eventStreamList?.dataset?.renderMode !== "empty"
      || lastRenderedEmptyState !== nextSignature
    ) {
      const rendered = updateRegionMarkup(els.eventStreamList, `<div class="event-stream-empty">${message}</div>`, nextSignature);
      if (rendered !== false || els.eventStreamList?.dataset?.renderSignature === nextSignature) {
        els.eventStreamList.dataset.renderMode = "empty";
        lastRenderedEmptyState = nextSignature;
        lastRenderedListSignature = "";
      }
    }
  }

  function setEventEnvelope(envelope = {}) {
    const eventState = getEventState();
    eventState.schemaVersion = envelope.schema_version || eventState.schemaVersion || null;
    eventState.sessionId = envelope.query?.session_id || eventState.sessionId || null;
    eventState.symbol = envelope.query?.symbol || eventState.symbol || null;
    eventState.timeframe = envelope.query?.timeframe || eventState.timeframe || null;
    eventState.candidates = cloneArray(envelope.candidates || []);
    eventState.items = cloneArray(envelope.items || []);
    eventState.memoryEntries = cloneArray(envelope.memory_entries || []);
    eventState.error = null;
    eventState.loading = false;
    eventState.loaded = true;
    eventState.dirty = false;
    eventState.lastLoadedAt = new Date().toISOString();
    const candidateIds = new Set(eventState.candidates.map((item) => item.event_id));
    eventState.pinnedEventIds = cloneArray(eventState.pinnedEventIds).filter((eventId) => candidateIds.has(eventId));
    if (!candidateIds.has(eventState.selectedEventId)) {
      eventState.selectedEventId = null;
    }
    if (!candidateIds.has(eventState.hoverEventId)) {
      eventState.hoverEventId = null;
    }
  }

  function applyMutationEnvelope(envelope = {}) {
    const eventState = getEventState();
    eventState.schemaVersion = envelope.schema_version || eventState.schemaVersion || null;
    eventState.sessionId = envelope.session_id || eventState.sessionId || null;
    if (envelope.candidate) {
      eventState.candidates = upsertById(eventState.candidates, envelope.candidate, "event_id");
    }
    if (envelope.stream_entry) {
      eventState.items = upsertById(eventState.items, envelope.stream_entry, "stream_entry_id");
    }
    if (envelope.memory_entry) {
      eventState.memoryEntries = upsertById(eventState.memoryEntries, envelope.memory_entry, "memory_entry_id");
    }
    eventState.error = null;
    eventState.loading = false;
    eventState.loaded = true;
    eventState.dirty = false;
    eventState.lastLoadedAt = new Date().toISOString();
  }

  async function resolveActiveSession() {
    if (typeof ensureActiveSessionPersisted === "function") {
      const ensured = await ensureActiveSessionPersisted();
      if (ensured?.id) {
        return ensured;
      }
    }
    return typeof getActiveThread === "function" ? getActiveThread() : null;
  }

  function getLatestAssistantMessageId(session) {
    return [...(session?.messages || [])]
      .reverse()
      .find((message) => message?.role === "assistant" && String(message?.message_id || "").trim())
      ?.message_id || null;
  }

  async function syncActiveSessionEventStream({ force = false, reason = "sync", sourceMessageId = null } = {}) {
    const eventState = getEventState();
    const session = await resolveActiveSession();
    if (!session?.id) {
      eventState.candidates = [];
      eventState.items = [];
      eventState.memoryEntries = [];
      eventState.loaded = false;
      eventState.loading = false;
      renderEventPanel();
      return null;
    }
    const sessionKey = `${session.id}|${session.symbol || ""}|${session.timeframe || ""}`;
    if (!force && !eventState.dirty && eventState.sessionKey === sessionKey && eventState.loaded) {
      return null;
    }
    eventState.loading = true;
    eventState.error = null;
    eventState.sessionKey = sessionKey;
    renderEventPanel();
    try {
      const envelope = await eventApi.listEventStream({
        sessionId: session.id,
        symbol: session.symbol || state.topBar?.symbol || null,
        timeframe: session.timeframe || state.topBar?.timeframe || null,
        sourceMessageId,
      });
      setEventEnvelope(envelope || {});
      renderEventPanel();
      decorationController.decorateChatMessages();
      dispatchOverlayChanged();
      return envelope;
    } catch (error) {
      eventState.loading = false;
      eventState.error = error?.message || String(error);
      renderEventPanel();
      renderStatusStrip?.([{ label: `事件流加载失败：${eventState.error}`, variant: "warn" }]);
      return null;
    } finally {
      persistWorkbenchState?.();
      if (reason === "reply-committed") {
        dispatchOverlayChanged();
      }
    }
  }

  function markDirty({ sourceMessageId = null } = {}) {
    const eventState = getEventState();
    eventState.dirty = true;
    if (sourceMessageId) {
      eventState.preferredSourceMessageId = sourceMessageId;
    }
  }

  function getCandidateById(eventId) {
    return byEventId(getEventState().candidates).get(String(eventId || "").trim()) || null;
  }

  function setHoveredEvent(eventId, { render = true } = {}) {
    const eventState = getEventState();
    const normalizedId = String(eventId || "").trim();
    if (eventState.hoverEventId === normalizedId) {
      return;
    }
    const previousHoverId = eventState.hoverEventId || null;
    eventState.hoverEventId = normalizedId || null;
    decorationController.syncCardClasses({ eventIds: [previousHoverId, eventState.hoverEventId] });
    if (render) {
      dispatchOverlayChanged();
    }
  }

  function clearHoveredEvent({ render = true } = {}) {
    const eventState = getEventState();
    if (!eventState.hoverEventId) {
      return;
    }
    const previousHoverId = eventState.hoverEventId;
    eventState.hoverEventId = null;
    decorationController.syncCardClasses({ eventIds: [previousHoverId] });
    if (render) {
      dispatchOverlayChanged();
    }
  }

  function selectEvent(eventId, { centerChart = false, scrollCard = true } = {}) {
    const eventState = getEventState();
    const candidate = getCandidateById(eventId);
    if (!candidate) {
      return;
    }
    const previousSelectedId = eventState.selectedEventId || null;
    eventState.selectedEventId = candidate.event_id;
    decorationController.syncCardClasses({ eventIds: [previousSelectedId, candidate.event_id] });
    if (scrollCard) {
      scrollEventCardIntoView(candidate.event_id);
    }
    if (centerChart) {
      focusEventCandidateOnChart?.(candidate, { centerChart: true, announce: false });
    }
    dispatchOverlayChanged();
    persistWorkbenchState?.();
  }

  function scrollEventCardIntoView(eventId) {
    const node = els.eventStreamList?.querySelector?.(`.event-candidate-card[data-event-id="${eventId}"]`);
    const details = node?.closest?.("details");
    if (details && !details.open) {
      details.open = true;
    }
    node?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  function togglePinnedEvent(eventId) {
    const eventState = getEventState();
    const nextPinned = new Set(Array.isArray(eventState.pinnedEventIds) ? eventState.pinnedEventIds : []);
    if (nextPinned.has(eventId)) {
      nextPinned.delete(eventId);
    } else {
      nextPinned.add(eventId);
    }
    eventState.pinnedEventIds = Array.from(nextPinned);
    decorationController.syncCardClasses({ eventIds: [eventId] });
    renderEventPanel();
    dispatchOverlayChanged();
    persistWorkbenchState?.();
  }

  async function runCandidateMutation(eventId, mutationFactory, {
    centerChart = false,
    successLabel = "",
  } = {}) {
    const candidate = getCandidateById(eventId);
    if (!candidate) {
      return;
    }
    try {
      const mutation = await mutationFactory(candidate);
      applyMutationEnvelope(mutation || {});
      renderEventPanel();
      decorationController.decorateChatMessages({
        messageIds: [
          candidate?.source_message_id,
          mutation?.candidate?.source_message_id,
        ],
      });
      selectEvent(eventId, { centerChart, scrollCard: false });
      if (typeof afterMutation === "function") {
        await afterMutation(mutation, candidate);
      }
      if (successLabel) {
        renderStatusStrip?.([{ label: successLabel, variant: "good" }]);
      }
      return mutation;
    } catch (error) {
      renderStatusStrip?.([{ label: error?.message || String(error), variant: "warn" }]);
      return null;
    } finally {
      persistWorkbenchState?.();
    }
  }

  async function mountEvent(eventId, { centerChart = true } = {}) {
    const candidate = getCandidateById(eventId);
    if (!candidate) {
      return null;
    }
    if (!isEventCandidateMountable(candidate)) {
      selectEvent(eventId, { centerChart: false, scrollCard: true });
      return null;
    }
    const presentationState = getEventPresentationState(candidate, getEventState());
    if (presentationState === "mounted" || presentationState === "pinned") {
      selectEvent(eventId, { centerChart, scrollCard: true });
      return null;
    }
    return runCandidateMutation(
      eventId,
      () => eventApi.mountCandidate(eventId),
      {
        centerChart,
        successLabel: "事件已固定上图。",
      },
    );
  }

  async function promoteEvent(eventId) {
    const candidate = getCandidateById(eventId);
    if (!candidate || !canPromoteEventCandidate(candidate)) {
      return null;
    }
    return runCandidateMutation(
      eventId,
      () => eventApi.promoteCandidate(eventId, "plan_card"),
      {
        centerChart: false,
        successLabel: "事件已转为计划。",
      },
    );
  }

  async function ignoreEvent(eventId) {
    return runCandidateMutation(
      eventId,
      () => eventApi.ignoreCandidate(eventId),
      {
        centerChart: false,
        successLabel: "事件已忽略。",
      },
    );
  }

  async function pinEvent(eventId) {
    const candidate = getCandidateById(eventId);
    if (!candidate) {
      return;
    }
    const presentationState = getEventPresentationState(candidate, getEventState());
    if (presentationState !== "mounted" && presentationState !== "pinned" && isEventCandidateMountable(candidate)) {
      await mountEvent(eventId, { centerChart: false });
    }
    togglePinnedEvent(eventId);
  }

  async function createManualEventCandidate(payload) {
    try {
      const session = await resolveActiveSession();
      if (!session?.id) {
        throw new Error("当前没有可写入的事件会话。");
      }
      const mutation = await eventApi.createCandidate({
        session_id: session.id,
        symbol: session.symbol || state.topBar?.symbol || null,
        timeframe: session.timeframe || state.topBar?.timeframe || null,
        source_message_id: payload.source_message_id || getLatestAssistantMessageId(session),
        ...payload,
      });
      applyMutationEnvelope(mutation || {});
      renderEventPanel();
      decorationController.decorateChatMessages({
        messageIds: [payload.source_message_id, mutation?.candidate?.source_message_id],
      });
      selectEvent(mutation?.candidate?.event_id, { centerChart: false, scrollCard: true });
      if (typeof afterMutation === "function") {
        await afterMutation(mutation, mutation?.candidate || null);
      }
      renderStatusStrip?.([{ label: "手工事件已保存。", variant: "good" }]);
      persistWorkbenchState?.();
      return mutation;
    } catch (error) {
      renderStatusStrip?.([{ label: error?.message || String(error), variant: "warn" }]);
      return null;
    }
  }

  function focusNearbyCandidate(eventId) {
    const candidate = getCandidateById(eventId);
    if (!candidate) {
      return false;
    }
    setHoveredEvent(eventId, { render: true });
    selectEvent(eventId, { centerChart: false, scrollCard: true });
    if (jumpToEventSource?.(candidate)) {
      return true;
    }
    focusEventCandidateOnChart?.(candidate, { centerChart: true, announce: false });
    return true;
  }

  function renderEventPanel() {
    const eventState = getEventState();
    const sortedCandidates = sortCandidates(eventState.candidates || [], eventState);
    const nearbyContextModel = buildNearbyContextModel(sortedCandidates);
    const surfaceItems = Array.isArray(nearbyContextModel?.surfaceItems) ? nearbyContextModel.surfaceItems : [];
    const visibleItems = Array.isArray(nearbyContextModel?.visibleItems) ? nearbyContextModel.visibleItems : [];
    const historyItems = Array.isArray(nearbyContextModel?.historyItems) ? nearbyContextModel.historyItems : [];
    if (!historyItems.length) {
      eventState.historyExpanded = false;
    }
    const visibleCandidates = visibleItems.map((item) => item.candidate);
    const totalCounts = collectCounts(sortedCandidates, eventState);
    const visibleCounts = collectCounts(visibleCandidates, eventState);
    state.eventStreamItems = visibleCandidates;
    const nextSurfaceItemsSignature = visibleCandidates.map((candidate) => String(candidate?.event_id || "").trim()).join("|");
    if (nextSurfaceItemsSignature !== lastSurfaceItemsSignature) {
      lastSurfaceItemsSignature = nextSurfaceItemsSignature;
      onSurfaceItemsChanged?.(visibleCandidates);
    }

    if (eventState.hoverEventId && !surfaceItems.some((item) => item?.candidate?.event_id === eventState.hoverEventId)) {
      eventState.hoverEventId = null;
      dispatchOverlayChanged();
    }

    els.eventStreamFilterBar?.querySelectorAll?.("[data-event-stream-filter]")?.forEach?.((button) => {
      button.classList.toggle("is-active", button.dataset.eventStreamFilter === (state.eventStreamFilter || "all"));
    });

    if (els.eventStreamSummary) {
      if (eventState.loading) {
        els.eventStreamSummary.textContent = "正在同步事件流…";
      } else if (eventState.error) {
        els.eventStreamSummary.textContent = `事件流加载失败：${eventState.error}`;
      } else if (!sortedCandidates.length) {
        els.eventStreamSummary.textContent = "当前会话还没有正式 EventCandidate。";
      } else {
        els.eventStreamSummary.textContent = nearbyContextModel?.summaryText
          || `当前前台 ${visibleCounts.total} 条事件${totalCounts.total > visibleCounts.total ? `，后台 ${totalCounts.total} 条` : ""}。`;
      }
    }

    if (!els.eventStreamList) {
      return;
    }
    if (eventState.loading && !sortedCandidates.length) {
      renderEmptyState("正在从后端 event-stream 读取正式事件对象…");
      return;
    }
    if (eventState.error && !sortedCandidates.length) {
      renderEmptyState("事件流读取失败。旧 reply extraction 仍保留为 legacy fallback。");
      return;
    }
    if (!sortedCandidates.length) {
      renderEmptyState("当前会话还没有正式 EventCandidate。旧文本提取仅保留为 legacy fallback，不再作为主路径。");
      return;
    }
    const nextListSignature = JSON.stringify({
      filter: state.eventStreamFilter || "all",
      items: buildCandidateRenderSignature(visibleItems),
      history: buildCandidateRenderSignature(historyItems),
    });
    if (
      els.eventStreamList.dataset.renderMode !== "nearby-dock"
      || lastRenderedListSignature !== nextListSignature
    ) {
      const rendered = renderNearbyDock(nearbyContextModel, eventState);
      if (rendered) {
        lastRenderedListSignature = nextListSignature;
        lastRenderedEmptyState = "";
      }
    }
    decorationController.syncCardClasses();
  }

  function installPanelBindings() {
    if (panelBindingsInstalled) {
      return;
    }
    panelBindingsInstalled = true;
    els.eventStreamFilterBar?.addEventListener("click", (event) => {
      const button = event.target?.closest?.("[data-event-stream-filter]");
      if (!button) {
        return;
      }
      state.eventStreamFilter = button.dataset.eventStreamFilter || "all";
      renderEventPanel();
      persistWorkbenchState?.();
    });
    els.eventStreamList?.addEventListener("mouseover", (event) => {
      const card = event.target?.closest?.(".event-candidate-card[data-event-id]");
      if (!card) {
        return;
      }
      setHoveredEvent(card.dataset.eventId);
    });
    els.eventStreamList?.addEventListener("mouseout", (event) => {
      const currentCard = event.target?.closest?.(".event-candidate-card[data-event-id]");
      if (!currentCard) {
        return;
      }
      const nextCard = event.relatedTarget?.closest?.(".event-candidate-card[data-event-id]");
      if (nextCard && nextCard.dataset.eventId === currentCard.dataset.eventId) {
        return;
      }
      clearHoveredEvent();
    });
    els.eventStreamList?.addEventListener("mouseleave", () => {
      clearHoveredEvent();
    });
    els.eventStreamList?.addEventListener("toggle", (event) => {
      const historyShell = event.target;
      if (!(historyShell instanceof HTMLDetailsElement)) {
        return;
      }
      if (!historyShell.matches('.nearby-context-history-shell[data-nearby-group="history"]')) {
        return;
      }
      getEventState().historyExpanded = historyShell.open;
      persistWorkbenchState?.();
    });
    els.eventStreamList?.addEventListener("click", async (event) => {
      const actionButton = event.target?.closest?.("[data-event-action][data-event-id]");
      if (actionButton) {
        const eventId = actionButton.dataset.eventId;
        const action = actionButton.dataset.eventAction;
        if (action === "spotlight") {
          setHoveredEvent(eventId);
          selectEvent(eventId, { centerChart: true, scrollCard: false });
          return;
        }
        if (action === "mount") {
          await mountEvent(eventId, { centerChart: true });
          return;
        }
        if (action === "promote") {
          await promoteEvent(eventId);
          return;
        }
        if (action === "pin") {
          await pinEvent(eventId);
          return;
        }
        if (action === "ignore") {
          await ignoreEvent(eventId);
          return;
        }
        if (action === "source") {
          const candidate = getCandidateById(eventId);
          if (candidate) {
            jumpToEventSource?.(candidate);
          }
          return;
        }
        if (action === "prompt") {
          const candidate = getCandidateById(eventId);
          if (candidate) {
            if (!onPromptTraceRequested?.(candidate)) {
              renderStatusStrip?.([{
                label: candidate.source_prompt_trace_id
                  ? `Prompt Trace 入口待接后端，trace_id=${candidate.source_prompt_trace_id}`
                  : "当前事件没有 Prompt Trace。",
                variant: "emphasis",
              }]);
            }
          }
          return;
        }
        if (action === "outcome") {
          const candidate = getCandidateById(eventId);
          if (candidate) {
            if (!onOutcomeRequested?.(candidate)) {
              renderStatusStrip?.([{ label: "Outcome Ledger 入口待接后端。", variant: "emphasis" }]);
            }
          }
          return;
        }
      }
      if (event.target?.closest?.(".event-candidate-menu")) {
        return;
      }
      const card = event.target?.closest?.(".event-candidate-card[data-event-id]");
      if (!card) {
        return;
      }
      focusNearbyCandidate(card.dataset.eventId);
    });
  }

  function installMessageBindings() {
    if (messageBindingsInstalled) {
      return;
    }
    messageBindingsInstalled = true;
    els.aiChatThread?.addEventListener("mouseover", (event) => {
      const chip = event.target?.closest?.("[data-message-event-id]");
      if (!chip) {
        return;
      }
      setHoveredEvent(chip.dataset.messageEventId, { render: true });
    });
    els.aiChatThread?.addEventListener("mouseout", (event) => {
      const chip = event.target?.closest?.("[data-message-event-id]");
      if (!chip) {
        return;
      }
      const nextChip = event.relatedTarget?.closest?.("[data-message-event-id]");
      if (nextChip && nextChip.dataset.messageEventId === chip.dataset.messageEventId) {
        return;
      }
      clearHoveredEvent({ render: true });
    });
    els.aiChatThread?.addEventListener("mouseleave", () => {
      clearHoveredEvent({ render: true });
    });
    els.aiChatThread?.addEventListener("click", (event) => {
      const chip = event.target?.closest?.("[data-message-event-id]");
      if (!chip) {
        return;
      }
      selectEvent(chip.dataset.messageEventId, { centerChart: true, scrollCard: true });
    });
  }

  function installHoverDismissBindings() {
    if (hoverDismissBindingsInstalled) {
      return;
    }
    hoverDismissBindingsInstalled = true;
    document.addEventListener("mouseover", (event) => {
      if (!getEventState().hoverEventId) {
        return;
      }
      if (decorationController.isHoverSurfaceTarget(event.target)) {
        return;
      }
      clearHoveredEvent({ render: true });
    });
    document.addEventListener("focusin", (event) => {
      if (!getEventState().hoverEventId) {
        return;
      }
      if (decorationController.isHoverSurfaceTarget(event.target)) {
        return;
      }
      clearHoveredEvent({ render: true });
    });
  }

  function handleOverlayEventClick(eventId) {
    selectEvent(eventId, { centerChart: false, scrollCard: true });
  }

  function handleOverlayEventEnter(eventId) {
    setHoveredEvent(eventId, { render: false });
  }

  function handleOverlayEventLeave() {
    clearHoveredEvent({ render: false });
  }

  installPanelBindings();
  installMessageBindings();
  installHoverDismissBindings();

  return {
    renderEventPanel,
    decorateChatMessages: (options = {}) => decorationController.decorateChatMessages(options),
    syncActiveSessionEventStream,
    markDirty,
    setHoveredEvent,
    clearHoveredEvent,
    selectEvent,
    getCandidateById,
    createManualEventCandidate,
    handleOverlayEventClick,
    handleOverlayEventEnter,
    handleOverlayEventLeave,
  };
}
