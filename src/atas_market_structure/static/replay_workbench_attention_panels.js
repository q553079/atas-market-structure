import { escapeHtml } from "./replay_workbench_ui_utils.js";
import {
  canRenderStructuredAssistantMessage,
  renderStructuredAnswerCard,
} from "./replay_workbench_answer_cards.js";
import { updateRegionMarkup } from "./replay_workbench_render_stability.js";

function pickFirstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && !(typeof value === "number" && Number.isNaN(value))) {
      return value;
    }
  }
  return null;
}

function normalizeStringArray(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? "").trim())
      .filter(Boolean);
  }
  const text = String(value ?? "").trim();
  return text ? [text] : [];
}

function toFiniteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function buildActiveReplyWorkspaceSignature(activeMessage, activeUi = {}, getReplyObjectCount) {
  return JSON.stringify({
    messageId: activeMessage?.message_id || "",
    status: activeMessage?.status || "",
    updatedAt: activeMessage?.updated_at || activeMessage?.created_at || "",
    contentLength: String(activeMessage?.content || "").length,
    replyWindowAnchor: String(pickFirstDefined(activeUi?.reply_window_anchor, activeUi?.replyWindowAnchor) || "").trim(),
    contextVersion: String(pickFirstDefined(activeUi?.context_version, activeUi?.contextVersion) || "").trim(),
    promptTraceId: activeMessage?.promptTraceId || activeMessage?.meta?.promptTraceId || "",
    objectCount: getReplyObjectCount(activeMessage),
  });
}

function buildLegacyActiveReplyWorkspaceMarkup(activeMessage, activeUi = null, {
  buildAssistantReplyLabel,
  buildReplySummaryText,
  buildReplyWindowLabel,
} = {}) {
  const title = buildAssistantReplyLabel(activeMessage, 0);
  const summary = buildReplySummaryText(activeMessage, 220);
  const timeLabel = buildReplyWindowLabel(activeUi || {});
  return `
    <article class="answer-card answer-card-full" data-structured-answer-card="false" data-card-density="full">
      <header class="answer-card-head">
        <div class="answer-card-chip-row">
          <span class="answer-card-chip is-active">当前回复</span>
          <span class="answer-card-chip">Legacy</span>
        </div>
        <div class="answer-card-title-row">
          <div class="answer-card-title-copy">
            <span class="answer-card-kicker">${escapeHtml(title)}</span>
            <strong class="answer-card-title">${escapeHtml(summary || "当前回复")}</strong>
          </div>
          <div class="answer-card-time-meta">${escapeHtml(timeLabel || "未记录")}</div>
        </div>
      </header>
      <section class="answer-card-section" data-answer-section="note">
        <span class="answer-card-section-label">当前答复</span>
        <div class="answer-card-section-value">${escapeHtml(summary || String(activeMessage?.content || "").trim() || "未记录")}</div>
      </section>
    </article>
  `;
}

function buildActiveReplyWorkspaceMarkup(activeMessage, activeUi = null, {
  buildAssistantReplyLabel,
  buildReplySummaryText,
  buildReplyWindowLabel,
  getReplyObjectCount,
  buildLongTextMarkup,
} = {}) {
  if (!activeMessage) {
    return "";
  }
  if (canRenderStructuredAssistantMessage(activeMessage)) {
    return renderStructuredAnswerCard({
      message: {
        ...activeMessage,
        isActiveReply: true,
      },
      density: "full",
      expandedLongText: false,
      replyObjectCount: getReplyObjectCount(activeMessage),
      canProjectReply: false,
      includeMessageActions: false,
      includeAttachments: false,
      includePlanCards: false,
      renderLongTextMarkup: (text, options = {}) => buildLongTextMarkup(text, options),
    });
  }
  return buildLegacyActiveReplyWorkspaceMarkup(activeMessage, activeUi, {
    buildAssistantReplyLabel,
    buildReplySummaryText,
    buildReplyWindowLabel,
  });
}

function buildNearbyContextDockMarkup(activeMessage, activeUi = null, getReplyObjectCount) {
  const sourceEventIds = normalizeStringArray(pickFirstDefined(activeUi?.source_event_ids, activeUi?.sourceEventIds));
  const sourceObjectIds = normalizeStringArray(pickFirstDefined(activeUi?.source_object_ids, activeUi?.sourceObjectIds));
  const crossDayAnchorCount = toFiniteNumber(pickFirstDefined(activeUi?.cross_day_anchor_count, activeUi?.crossDayAnchorCount), 0);
  const alignmentState = String(pickFirstDefined(activeUi?.alignment_state, activeUi?.alignmentState) || "").trim() || "未记录";
  const assertionLevel = String(pickFirstDefined(activeUi?.assertion_level, activeUi?.assertionLevel) || "").trim() || "未记录";
  const replyWindowAnchor = String(pickFirstDefined(activeUi?.reply_window_anchor, activeUi?.replyWindowAnchor) || "").trim() || "未记录";
  const objectCount = getReplyObjectCount(activeMessage);
  const detailChips = [];
  if (sourceEventIds.length) {
    detailChips.push(...sourceEventIds.slice(0, 4).map((value) => `<span class="mini-chip">${escapeHtml(`事件 ${value}`)}</span>`));
    if (sourceEventIds.length > 4) {
      detailChips.push(`<span class="mini-chip">+${escapeHtml(String(sourceEventIds.length - 4))} 事件</span>`);
    }
  }
  if (sourceObjectIds.length) {
    detailChips.push(...sourceObjectIds.slice(0, 3).map((value) => `<span class="mini-chip">${escapeHtml(`对象 ${value}`)}</span>`));
    if (sourceObjectIds.length > 3) {
      detailChips.push(`<span class="mini-chip">+${escapeHtml(String(sourceObjectIds.length - 3))} 对象</span>`);
    }
  }
  return `
    <div class="nearby-context-summary-shell">
      <div class="nearby-context-summary-copy">
        <strong>事件流锚点 ${escapeHtml(replyWindowAnchor)}</strong>
        <p>默认先看事件卡；这里仅保留当前回答关联摘要。</p>
      </div>
      <div class="nearby-context-summary-strip">
        <span class="mini-chip emphasis">${escapeHtml(`${sourceEventIds.length} 条事件`)}</span>
        <span class="mini-chip">${escapeHtml(`${sourceObjectIds.length} 个对象`)}</span>
        <span class="mini-chip">${escapeHtml(`上图 ${objectCount}`)}</span>
        <span class="mini-chip">${escapeHtml(`对齐 ${alignmentState}`)}</span>
        <span class="mini-chip">${escapeHtml(`断言 ${assertionLevel}`)}</span>
        ${crossDayAnchorCount > 0 ? `<span class="mini-chip warning">${escapeHtml(`跨日 ${crossDayAnchorCount}`)}</span>` : ""}
      </div>
      ${detailChips.length ? `
        <div class="nearby-context-summary-strip is-secondary">
          ${detailChips.join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function buildNearbyContextDockSignature(activeMessage, activeUi = {}, getReplyObjectCount) {
  return JSON.stringify({
    messageId: activeMessage?.message_id || "",
    sourceEventIds: normalizeStringArray(pickFirstDefined(activeUi?.source_event_ids, activeUi?.sourceEventIds)),
    sourceObjectIds: normalizeStringArray(pickFirstDefined(activeUi?.source_object_ids, activeUi?.sourceObjectIds)),
    crossDayAnchorCount: toFiniteNumber(pickFirstDefined(activeUi?.cross_day_anchor_count, activeUi?.crossDayAnchorCount), 0),
    replyWindowAnchor: String(pickFirstDefined(activeUi?.reply_window_anchor, activeUi?.replyWindowAnchor) || "").trim(),
    objectCount: getReplyObjectCount(activeMessage),
    contextVersion: String(pickFirstDefined(activeUi?.context_version, activeUi?.contextVersion) || "").trim(),
  });
}

function resolveHasNearbyContext(session, activeMessage, activeUi, {
  hasVisibleNearbyContext = null,
  getReplyObjectCount = () => 0,
} = {}) {
  const sourceEventIds = normalizeStringArray(pickFirstDefined(activeUi?.source_event_ids, activeUi?.sourceEventIds));
  const sourceObjectIds = normalizeStringArray(pickFirstDefined(activeUi?.source_object_ids, activeUi?.sourceObjectIds));
  const crossDayAnchorCount = toFiniteNumber(pickFirstDefined(activeUi?.cross_day_anchor_count, activeUi?.crossDayAnchorCount), 0);
  const derivedNearbyContext = typeof hasVisibleNearbyContext === "function"
    ? hasVisibleNearbyContext(session, activeMessage, activeUi)
    : false;
  return !!activeMessage && (
    sourceEventIds.length > 0
    || sourceObjectIds.length > 0
    || crossDayAnchorCount > 0
    || getReplyObjectCount(activeMessage) > 0
    || !!String(pickFirstDefined(activeUi?.reply_window_anchor, activeUi?.replyWindowAnchor) || "").trim()
    || derivedNearbyContext
  );
}

export function createWorkbenchAttentionPanelsController({
  els,
  contextRecipeController,
  changeInspectorController,
  hasVisibleNearbyContext = null,
  buildAssistantReplyLabel,
  buildReplySummaryText,
  buildReplyWindowLabel,
  getReplyObjectCount,
  buildLongTextMarkup,
}) {
  function hide() {
    if (els.aiAnswerWorkspace) {
      els.aiAnswerWorkspace.hidden = true;
      els.aiAnswerWorkspace.setAttribute("aria-hidden", "true");
    }
    if (els.activeReplyWorkspaceCard) {
      els.activeReplyWorkspaceCard.hidden = true;
      els.activeReplyWorkspaceCard.setAttribute("aria-hidden", "true");
    }
    contextRecipeController.hide();
    changeInspectorController.hide();
    if (els.changeInspectorToggle) {
      els.changeInspectorToggle.hidden = true;
      els.changeInspectorToggle.setAttribute("aria-expanded", "false");
      els.changeInspectorToggle.classList.remove("is-active");
    }
    if (els.nearbyContextDock) {
      els.nearbyContextDock.hidden = true;
      els.nearbyContextDock.setAttribute("aria-hidden", "true");
    }
  }

  function render({ session, assistantMessages = [], activeMessage = null, activeUi = null } = {}) {
    if (!activeMessage) {
      hide();
      return;
    }

    if (els.activeReplyWorkspaceCard) {
      updateRegionMarkup(
        els.activeReplyWorkspaceCard,
        buildActiveReplyWorkspaceMarkup(activeMessage, activeUi, {
          buildAssistantReplyLabel,
          buildReplySummaryText,
          buildReplyWindowLabel,
          getReplyObjectCount,
          buildLongTextMarkup,
        }),
        buildActiveReplyWorkspaceSignature(activeMessage, activeUi || {}, getReplyObjectCount),
      );
      els.activeReplyWorkspaceCard.hidden = false;
      els.activeReplyWorkspaceCard.setAttribute("aria-hidden", "false");
    }

    contextRecipeController.render({ session, activeMessage, activeUi });
    changeInspectorController.render({ session, assistantMessages, activeMessage });

    const hasNearbyContext = resolveHasNearbyContext(session, activeMessage, activeUi, {
      hasVisibleNearbyContext,
      getReplyObjectCount,
    });
    if (els.nearbyContextDock) {
      els.nearbyContextDock.hidden = !hasNearbyContext;
      els.nearbyContextDock.setAttribute("aria-hidden", hasNearbyContext ? "false" : "true");
    }
    if (hasNearbyContext && els.nearbyContextDockSummary) {
      updateRegionMarkup(
        els.nearbyContextDockSummary,
        buildNearbyContextDockMarkup(activeMessage, activeUi, getReplyObjectCount),
        buildNearbyContextDockSignature(activeMessage, activeUi, getReplyObjectCount),
      );
    }

    const inspectorVisible = !els.changeInspectorPanel?.hidden;
    const showWorkspace = !!activeMessage || inspectorVisible;
    if (els.aiAnswerWorkspace) {
      els.aiAnswerWorkspace.hidden = !showWorkspace;
      els.aiAnswerWorkspace.setAttribute("aria-hidden", showWorkspace ? "false" : "true");
    }
  }

  return {
    hide,
    render,
  };
}
