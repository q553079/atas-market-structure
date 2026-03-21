import { summarizeText, writeStorage } from "./replay_workbench_ui_utils.js";

function shouldListAnnotation(item, filters, state) {
  if (!item || item.visible === false) {
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

export function createAnnotationPanelController({
  state,
  els,
  persistWorkbenchState,
  renderSnapshot,
  applyAnnotationScope,
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
    els.annotationSessionFilters.innerHTML = sessions.map((session) => `
      <label class="filter-item"><input type="checkbox" data-filter-kind="session" data-filter-id="${session.id}" ${filters.onlyCurrentSession ? session.id === state.activeAiThreadId ? "checked" : "" : (!filters.sessionIds.length || filters.sessionIds.includes(session.id)) ? "checked" : ""}>${session.title}</label>
    `).join("");

    const activeMessages = sessions.flatMap((session) => (session.messages || [])
      .filter((msg) => {
        const hasPlanCards = !!(msg.planCards?.length || msg.meta?.planCards?.length);
        const hasAnnotations = !!(msg.annotations?.length || msg.meta?.annotations?.length || (state.aiAnnotations || []).some((item) => item.message_id === msg.message_id));
        return msg.role === "assistant" && (hasPlanCards || hasAnnotations);
      })
      .map((msg) => ({ session, msg })));
    els.annotationMessageFilters.innerHTML = activeMessages.length
      ? activeMessages.map(({ session, msg }) => {
          const childAnnotations = (state.aiAnnotations || []).filter((item) => item.message_id === msg.message_id);
          const checked = !filters.messageIds.length || filters.messageIds.includes(msg.message_id);
          return `
            <div class="filter-subgroup">
              <div class="filter-subgroup-head">
                <label class="filter-item"><input type="checkbox" data-filter-kind="message" data-filter-id="${msg.message_id}" ${checked ? "checked" : ""}>[${session.title}] ${summarizeText(msg.content, 24)}</label>
              </div>
              <div class="filter-subgroup-items">
                ${childAnnotations.map((item) => `<label class="filter-item"><input type="checkbox" data-filter-kind="message-object" data-filter-id="${item.id}" ${!filters.annotationIds?.length || filters.annotationIds.includes(item.id) ? "checked" : ""}>${item.label}</label>`).join("") || `<div class="empty-note">暂无对象</div>`}
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
      ["path_arrow", "路径箭头"],
    ];
    els.annotationTypeFilters.innerHTML = typeOptions.map(([value, label]) => `<label class="filter-item"><input type="checkbox" data-filter-kind="type" data-filter-id="${value}" ${filters.objectTypes.includes(value) ? "checked" : ""}>${label}</label>`).join("");

    els.annotationObjectList.innerHTML = state.aiAnnotations.filter((item) => shouldListAnnotation(item, filters, state)).length
      ? state.aiAnnotations
          .filter((item) => shouldListAnnotation(item, filters, state))
          .map((item) => `<div class="annotation-object-row ${state.selectedAnnotationId === item.id ? "active" : ""}" data-annotation-id="${item.id}"><span>[${sessions.find((s) => s.id === item.session_id)?.title || "--"}] ${item.label}</span><span>${item.status}</span><div class="button-row tight"><button type="button" class="secondary tiny" data-annotation-action="locate" data-annotation-id="${item.id}">定位</button><button type="button" class="secondary tiny" data-annotation-action="only" data-annotation-id="${item.id}">仅看此对象</button><button type="button" class="secondary tiny" data-annotation-action="pin" data-annotation-id="${item.id}">${item.pinned ? "取消固定" : "固定"}</button><button type="button" class="secondary tiny" data-annotation-action="source" data-annotation-id="${item.id}">原回复</button><button type="button" class="secondary tiny" data-annotation-action="toggle" data-annotation-id="${item.id}">${item.visible === false ? "显示" : "隐藏"}</button><button type="button" class="secondary tiny" data-annotation-action="delete" data-annotation-id="${item.id}">删除</button></div></div>`).join("")
      : `<div class="empty-note">当前筛选条件下暂无 AI 标记对象。</div>`;

    bindFilterInputs();
    bindObjectActions(sessions);
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

  function bindObjectActions(sessions) {
    els.annotationObjectList.querySelectorAll("button[data-annotation-action]").forEach((button) => {
      button.onclick = () => {
        const id = button.dataset.annotationId;
        const action = button.dataset.annotationAction;
        const target = state.aiAnnotations.find((item) => item.id === id);
        if (!target) {
          return;
        }
        if (action === "locate") {
          applyAnnotationScope?.(id, {
            mode: "only",
            activateSession: true,
            jumpToSource: true,
            render: true,
          });
          return;
        }
        if (action === "only") {
          applyAnnotationScope?.(id, {
            mode: "only",
            activateSession: false,
            jumpToSource: false,
            render: true,
          });
          return;
        }
        if (action === "pin") {
          target.pinned = !target.pinned;
          persistWorkbenchState();
          renderSnapshot();
          return;
        }
        if (action === "source") {
          applyAnnotationScope?.(id, {
            mode: "reply",
            activateSession: true,
            jumpToSource: true,
            render: true,
          });
          return;
        }
        if (action === "toggle") {
          target.visible = target.visible === false;
          persistWorkbenchState();
          renderSnapshot();
          return;
        }
        if (action === "delete") {
          state.aiAnnotations = state.aiAnnotations.filter((item) => item.id !== id);
          if (state.selectedAnnotationId === id) {
            state.selectedAnnotationId = null;
          }
          persistWorkbenchState();
          renderSnapshot();
        }
      };
    });
  }

  return {
    renderAnnotationPanel,
  };
}
