import {
  escapeHtml,
  formatPrice,
  summarizeText,
  translateVerificationStatus,
  writeStorage,
} from "./replay_workbench_ui_utils.js";
import { getAnnotationTypeLabel, isAnnotationDeleted } from "./replay_workbench_annotation_utils.js";

function shouldListAnnotation(item, filters, state) {
  if (!item || isAnnotationDeleted(item)) {
    return false;
  }
  if (Array.isArray(filters.annotationIds) && filters.annotationIds.includes("__none__")) {
    return false;
  }
  if (filters.onlyCurrentSession && item.session_id !== state.activeAiThreadId) {
    return false;
  }
  if (Array.isArray(filters.sessionIds) && filters.sessionIds.length && !filters.sessionIds.includes(item.session_id)) {
    return false;
  }
  if (Array.isArray(filters.messageIds) && filters.messageIds.length && !filters.messageIds.includes(item.message_id)) {
    return false;
  }
  if (Array.isArray(filters.annotationIds) && filters.annotationIds.length && !filters.annotationIds.includes(item.id)) {
    return false;
  }
  if (item.type === "path_arrow" && !filters.showPaths) {
    return false;
  }
  if (Array.isArray(filters.objectTypes) && filters.objectTypes.length && !filters.objectTypes.includes(item.type)) {
    return false;
  }
  if (!filters.showInvalidated && ["invalidated", "sl_hit"].includes(item.status)) {
    return false;
  }
  if (filters.hideCompleted && ["completed", "archived", "expired"].includes(item.status)) {
    return false;
  }
  if (filters.selectedOnly && state.selectedAnnotationId) {
    const selected = state.aiAnnotations?.find((node) => node.id === state.selectedAnnotationId);
    if (item.id !== state.selectedAnnotationId && item.plan_id !== selected?.plan_id) {
      return false;
    }
  }
  return true;
}

function buildAnnotationSummary(item) {
  if (item.entry_price != null) {
    return `入场 ${formatPrice(item.entry_price)}`;
  }
  if (item.stop_price != null) {
    return `止损 ${formatPrice(item.stop_price)}`;
  }
  if (item.target_price != null) {
    return `目标 ${formatPrice(item.target_price)}`;
  }
  if (item.price_low != null && item.price_high != null) {
    return `区间 ${formatPrice(item.price_low)} - ${formatPrice(item.price_high)}`;
  }
  if (item.reason) {
    return summarizeText(item.reason, 56);
  }
  return "点击查看对象详情与来源。";
}

function buildAnnotationRowMarkup(item, sessionMap, messageMap, selectedAnnotationId) {
  const sessionTitle = sessionMap.get(item.session_id)?.title || "--";
  const sourceMessage = messageMap.get(item.message_id) || null;
  const sourceReplyTitle = sourceMessage?.replyTitle || sourceMessage?.meta?.replyTitle || summarizeText(sourceMessage?.content || "", 22) || "未命名回复";
  const chips = [
    `<span class="annotation-object-chip">${escapeHtml(getAnnotationTypeLabel(item.type))}</span>`,
    `<span class="annotation-object-chip">${escapeHtml(translateVerificationStatus(item.status || "active"))}</span>`,
    item.visible === false ? `<span class="annotation-object-chip warn">已隐藏</span>` : "",
    item.pinned ? `<span class="annotation-object-chip good">已固定</span>` : "",
  ].filter(Boolean).join("");
  return `
    <div
      class="annotation-object-row ${selectedAnnotationId === item.id ? "active" : ""} ${item.visible === false ? "is-hidden" : ""} ${item.pinned ? "is-pinned" : ""}"
      data-annotation-id="${escapeHtml(item.id)}"
      role="button"
      tabindex="0"
    >
      <div class="annotation-object-main">
        <div class="annotation-object-head">
          <strong class="annotation-object-title">${escapeHtml(item.label || getAnnotationTypeLabel(item.type))}</strong>
          <div class="annotation-object-chip-row">${chips}</div>
        </div>
        <div class="annotation-object-meta">[${escapeHtml(sessionTitle)}] ${escapeHtml(sourceReplyTitle)}</div>
        <div class="annotation-object-summary">${escapeHtml(buildAnnotationSummary(item))}</div>
      </div>
      <div class="button-row tight annotation-object-actions">
        <button type="button" class="secondary tiny" data-annotation-action="locate" data-annotation-id="${escapeHtml(item.id)}">定位图表</button>
        <button type="button" class="secondary tiny" data-annotation-action="only" data-annotation-id="${escapeHtml(item.id)}">仅看此对象</button>
        <button type="button" class="secondary tiny" data-annotation-action="pin" data-annotation-id="${escapeHtml(item.id)}">${item.pinned ? "取消固定" : "固定"}</button>
        <button type="button" class="secondary tiny" data-annotation-action="source" data-annotation-id="${escapeHtml(item.id)}">来源消息</button>
        <button type="button" class="secondary tiny" data-annotation-action="toggle" data-annotation-id="${escapeHtml(item.id)}">${item.visible === false ? "显示" : "隐藏"}</button>
        <button type="button" class="secondary tiny" data-annotation-action="delete" data-annotation-id="${escapeHtml(item.id)}">删除</button>
      </div>
    </div>
  `;
}

export function createAnnotationPanelController({
  state,
  els,
  renderSnapshot,
  onAnnotationAction,
}) {
  function renderAnnotationPanel() {
    const filters = state.annotationFilters;
    if (state.annotationPanelOpen) {
      els.annotationPanel.classList.remove("is-hidden");
    } else {
      els.annotationPanel.classList.add("is-hidden");
    }
    els.filterOnlyCurrentSession.checked = !!filters.onlyCurrentSession;
    els.filterHideCompleted.checked = !!filters.hideCompleted;
    if (els.filterShowPaths) els.filterShowPaths.checked = !!filters.showPaths;
    if (els.filterShowInvalidated) els.filterShowInvalidated.checked = !!filters.showInvalidated;

    const sessions = state.aiThreads || [];
    const sessionMap = new Map(sessions.map((session) => [session.id, session]));
    const messageMap = new Map();
    sessions.forEach((session) => {
      (session.messages || []).forEach((message) => {
        messageMap.set(message.message_id, message);
      });
    });

    els.annotationSessionFilters.innerHTML = sessions.map((session) => `
      <label class="filter-item"><input type="checkbox" data-filter-kind="session" data-filter-id="${escapeHtml(session.id)}" ${filters.onlyCurrentSession ? session.id === state.activeAiThreadId ? "checked" : "" : (!filters.sessionIds.length || filters.sessionIds.includes(session.id)) ? "checked" : ""}>${escapeHtml(session.title)}</label>
    `).join("");

    const activeMessages = sessions.flatMap((session) => (session.messages || [])
      .filter((msg) => {
        const hasPlanCards = !!(msg.planCards?.length || msg.meta?.planCards?.length);
        const hasAnnotations = !!(msg.annotations?.length || msg.meta?.annotations?.length || (state.aiAnnotations || []).some((item) => item.message_id === msg.message_id && !isAnnotationDeleted(item)));
        return msg.role === "assistant" && (hasPlanCards || hasAnnotations);
      })
      .map((msg) => ({ session, msg })));
    els.annotationMessageFilters.innerHTML = activeMessages.length
      ? activeMessages.map(({ session, msg }) => {
          const childAnnotations = (state.aiAnnotations || []).filter((item) => item.message_id === msg.message_id && !isAnnotationDeleted(item));
          const checked = !filters.messageIds.length || filters.messageIds.includes(msg.message_id);
          return `
            <div class="filter-subgroup">
              <div class="filter-subgroup-head">
                <label class="filter-item"><input type="checkbox" data-filter-kind="message" data-filter-id="${escapeHtml(msg.message_id)}" ${checked ? "checked" : ""}>[${escapeHtml(session.title)}] ${escapeHtml(summarizeText(msg.content, 24))}</label>
              </div>
              <div class="filter-subgroup-items">
                ${childAnnotations.map((item) => `<label class="filter-item"><input type="checkbox" data-filter-kind="message-object" data-filter-id="${escapeHtml(item.id)}" ${!filters.annotationIds?.length || filters.annotationIds.includes(item.id) ? "checked" : ""}>${escapeHtml(item.label)}${item.visible === false ? "（已隐藏）" : item.pinned ? "（已固定）" : ""}</label>`).join("") || `<div class="empty-note">暂无对象</div>`}
              </div>
            </div>
          `;
        }).join("")
      : `<div class="empty-note">暂无计划消息。</div>`;

    const typeOptions = [
      ["entry_line", "开仓建议"],
      ["stop_loss", "止损止盈"],
      ["take_profit", "止损止盈"],
      ["support_zone", "支撑/阻力区"],
      ["resistance_zone", "支撑/阻力区"],
      ["no_trade_zone", "无交易区"],
      ["zone", "一般价格区"],
      ["path_arrow", "路径箭头"],
    ];
    els.annotationTypeFilters.innerHTML = typeOptions.map(([value, label]) => `<label class="filter-item"><input type="checkbox" data-filter-kind="type" data-filter-id="${escapeHtml(value)}" ${filters.objectTypes.includes(value) ? "checked" : ""}>${escapeHtml(label)}</label>`).join("");

    const filteredAnnotations = (state.aiAnnotations || []).filter((item) => shouldListAnnotation(item, filters, state));
    els.annotationObjectList.innerHTML = filteredAnnotations.length
      ? filteredAnnotations
          .map((item) => buildAnnotationRowMarkup(item, sessionMap, messageMap, state.selectedAnnotationId))
          .join("")
      : `<div class="empty-note">当前筛选条件下暂无 AI 标记对象。</div>`;

    bindFilterInputs();
    bindObjectActions();
  }

  function bindFilterInputs() {
    const filters = state.annotationFilters;
    els.annotationPanel.querySelectorAll("input[data-filter-kind]").forEach((input) => {
      input.onchange = () => {
        const kind = input.dataset.filterKind;
        if (kind === "session") {
          filters.onlyCurrentSession = false;
          filters.sessionIds = Array.from(els.annotationSessionFilters.querySelectorAll("input:checked")).map((node) => node.dataset.filterId);
        } else if (kind === "message") {
          filters.messageIds = Array.from(els.annotationMessageFilters.querySelectorAll('input[data-filter-kind="message"]:checked')).map((node) => node.dataset.filterId);
        } else if (kind === "message-object") {
          filters.annotationIds = Array.from(els.annotationMessageFilters.querySelectorAll('input[data-filter-kind="message-object"]:checked')).map((node) => node.dataset.filterId);
        } else if (kind === "type") {
          filters.objectTypes = Array.from(els.annotationTypeFilters.querySelectorAll("input:checked")).map((node) => node.dataset.filterId);
        }
        writeStorage("annotationFilters", filters);
        renderSnapshot();
      };
    });
  }

  function bindObjectActions() {
    els.annotationObjectList.onclick = (event) => {
      const button = event.target.closest("button[data-annotation-action]");
      if (button) {
        event.preventDefault();
        event.stopPropagation();
        onAnnotationAction?.(button.dataset.annotationAction, button.dataset.annotationId);
        return;
      }
      const row = event.target.closest(".annotation-object-row[data-annotation-id]");
      if (row) {
        onAnnotationAction?.("detail", row.dataset.annotationId);
      }
    };
    els.annotationObjectList.onkeydown = (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const row = event.target.closest(".annotation-object-row[data-annotation-id]");
      if (!row) {
        return;
      }
      event.preventDefault();
      onAnnotationAction?.("detail", row.dataset.annotationId);
    };
  }

  return {
    renderAnnotationPanel,
  };
}
