import { escapeHtml, summarizeText } from "./replay_workbench_ui_utils.js";
import { deriveStructuredSections } from "./replay_workbench_answer_cards.js";
import { updateRegionMarkup } from "./replay_workbench_render_stability.js";

function isPlainObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function mergePlainObjects(base = {}, patch = {}) {
  const merged = { ...(isPlainObject(base) ? base : {}) };
  Object.entries(isPlainObject(patch) ? patch : {}).forEach(([key, value]) => {
    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergePlainObjects(merged[key], value);
      return;
    }
    merged[key] = value;
  });
  return merged;
}

function pickFirstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && !(typeof value === "number" && Number.isNaN(value))) {
      return value;
    }
  }
  return null;
}

function normalizeString(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function normalizeStringArray(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeString(item))
      .filter(Boolean);
  }
  const text = normalizeString(value);
  return text ? [text] : [];
}

function parseTimestamp(value) {
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp : null;
}

function getWorkbenchUiMeta(meta = {}) {
  const merged = mergePlainObjects(
    isPlainObject(meta?.workbenchUi) ? meta.workbenchUi : {},
    isPlainObject(meta?.workbench_ui) ? meta.workbench_ui : {},
  );
  return Object.keys(merged).length ? merged : null;
}

function normalizeChangeInspectorMode(mode, { open = false } = {}) {
  const normalized = normalizeString(mode).toLowerCase();
  if (normalized === "peek" || normalized === "expanded") {
    return normalized;
  }
  if (open && (normalized === "semantic" || normalized === "text")) {
    return "expanded";
  }
  return "peek";
}

function buildReplyWindowDescriptor(workbenchUi = {}) {
  const replyWindow = isPlainObject(workbenchUi?.reply_window)
    ? workbenchUi.reply_window
    : (isPlainObject(workbenchUi?.replyWindow) ? workbenchUi.replyWindow : {});
  const startedAt = pickFirstDefined(
    replyWindow.window_start,
    replyWindow.windowStart,
    workbenchUi.window_start,
    workbenchUi.windowStart,
  );
  const endedAt = pickFirstDefined(
    replyWindow.window_end,
    replyWindow.windowEnd,
    workbenchUi.window_end,
    workbenchUi.windowEnd,
  );
  const startMs = parseTimestamp(startedAt);
  const endMs = parseTimestamp(endedAt);
  return {
    raw: replyWindow,
    startedAt: normalizeString(startedAt),
    endedAt: normalizeString(endedAt),
    startMs,
    endMs,
    durationMs: startMs != null && endMs != null ? Math.max(endMs - startMs, 0) : 0,
  };
}

function normalizeAssertionLevel(value = "") {
  const normalized = normalizeString(value).toLowerCase();
  return normalized || "unknown";
}

function buildComparableRecord(message, index, {
  getReplyObjectCount,
  buildReplyWindowLabel,
  buildAssistantReplyLabel,
} = {}) {
  const workbenchUi = getWorkbenchUiMeta(message?.meta);
  if (!workbenchUi) {
    return null;
  }
  const blockRefs = Array.isArray(workbenchUi.context_blocks)
    ? workbenchUi.context_blocks
    : (Array.isArray(workbenchUi.contextBlocks) ? workbenchUi.contextBlocks : []);
  return {
    message,
    index,
    id: normalizeString(message?.message_id),
    label: typeof buildAssistantReplyLabel === "function"
      ? buildAssistantReplyLabel(message, index)
      : normalizeString(message?.replyTitle, `AI 回复 ${index + 1}`),
    summary: summarizeText(message?.content || message?.replyTitle || message?.meta?.replyTitle || "暂无摘要", 120),
    workbenchUi,
    symbol: normalizeString(pickFirstDefined(workbenchUi.symbol, workbenchUi.instrument_symbol)).toUpperCase(),
    timeframe: normalizeString(pickFirstDefined(workbenchUi.timeframe, workbenchUi.display_timeframe)).toLowerCase(),
    sessionDate: normalizeString(pickFirstDefined(workbenchUi.reply_session_date, workbenchUi.replySessionDate)),
    anchor: normalizeString(pickFirstDefined(workbenchUi.reply_window_anchor, workbenchUi.replyWindowAnchor)),
    replyWindow: buildReplyWindowDescriptor(workbenchUi),
    replyWindowLabel: typeof buildReplyWindowLabel === "function" ? buildReplyWindowLabel(workbenchUi) : "未记录",
    assertionLevel: normalizeAssertionLevel(pickFirstDefined(workbenchUi.assertion_level, workbenchUi.assertionLevel, message?.meta?.assertion_level)),
    contextVersion: normalizeString(pickFirstDefined(workbenchUi.context_version, workbenchUi.contextVersion)),
    selectedBlockCount: Number.isFinite(Number(workbenchUi?.selected_block_count))
      ? Number(workbenchUi.selected_block_count)
      : blockRefs.filter((item) => item?.selected !== false).length,
    pinnedBlockCount: Number.isFinite(Number(workbenchUi?.pinned_block_count))
      ? Number(workbenchUi.pinned_block_count)
      : blockRefs.filter((item) => !!item?.pinned).length,
    includeMemorySummary: !!pickFirstDefined(workbenchUi.include_memory_summary, workbenchUi.includeMemorySummary, false),
    includeRecentMessages: !!pickFirstDefined(workbenchUi.include_recent_messages, workbenchUi.includeRecentMessages, false),
    modelName: normalizeString(pickFirstDefined(workbenchUi.model_name, workbenchUi.modelName, message?.model)),
    sourceEventIds: normalizeStringArray(pickFirstDefined(workbenchUi.source_event_ids, workbenchUi.sourceEventIds)),
    sourceObjectIds: normalizeStringArray(pickFirstDefined(workbenchUi.source_object_ids, workbenchUi.sourceObjectIds)),
    mountedObjectIds: normalizeStringArray(message?.mountedObjectIds),
    replyObjectCount: typeof getReplyObjectCount === "function" ? getReplyObjectCount(message) : 0,
    blockRefs,
  };
}

function computeWindowOverlapRatio(baseWindow, compareWindow) {
  if (!baseWindow || !compareWindow) {
    return 0;
  }
  if (baseWindow.startMs == null || baseWindow.endMs == null || compareWindow.startMs == null || compareWindow.endMs == null) {
    return 0;
  }
  const overlapMs = Math.min(baseWindow.endMs, compareWindow.endMs) - Math.max(baseWindow.startMs, compareWindow.startMs);
  if (overlapMs <= 0) {
    return 0;
  }
  const shorterDuration = Math.min(
    Math.max(baseWindow.durationMs, 1),
    Math.max(compareWindow.durationMs, 1),
  );
  return Math.min(overlapMs / shorterDuration, 1);
}

function assessPairEligibility(baselineRecord, compareRecord) {
  if (!baselineRecord || !compareRecord) {
    return { eligible: false, reason: "缺少可比较 reply。", reasonCode: "missing_pair" };
  }
  if (baselineRecord.id === compareRecord.id) {
    return { eligible: false, reason: "同一条 reply 不能自比。", reasonCode: "same_message" };
  }
  if (baselineRecord.symbol !== compareRecord.symbol) {
    return { eligible: false, reason: "不同 symbol 的 reply 不可比较。", reasonCode: "symbol_mismatch" };
  }
  if (baselineRecord.timeframe !== compareRecord.timeframe) {
    return { eligible: false, reason: "不同 timeframe 的 reply 不可比较。", reasonCode: "timeframe_mismatch" };
  }
  if (baselineRecord.sessionDate && compareRecord.sessionDate && baselineRecord.sessionDate !== compareRecord.sessionDate) {
    return { eligible: false, reason: "不同交易日的 reply 不做直接比较。", reasonCode: "session_date_mismatch" };
  }
  if (baselineRecord.assertionLevel === "insufficient_context" && compareRecord.assertionLevel === "insufficient_context") {
    return { eligible: false, reason: "两条 reply 都是上下文不足，不做语义 diff。", reasonCode: "double_insufficient_context" };
  }
  const sameAnchor = !!baselineRecord.anchor && baselineRecord.anchor === compareRecord.anchor;
  const overlapRatio = computeWindowOverlapRatio(baselineRecord.replyWindow, compareRecord.replyWindow);
  if (!sameAnchor && overlapRatio < 0.35) {
    return {
      eligible: false,
      reason: "reply_window_anchor 不同且 reply_window 重叠不足，避免弱语义误比。",
      reasonCode: "anchor_window_mismatch",
      overlapRatio,
    };
  }
  return {
    eligible: true,
    reason: sameAnchor ? `同 reply_window_anchor：${compareRecord.anchor}` : `reply_window 重叠 ${Math.round(overlapRatio * 100)}%`,
    reasonCode: sameAnchor ? "same_anchor" : "overlap",
    sameAnchor,
    overlapRatio,
    strength: sameAnchor ? "strong" : "weak",
  };
}

function scoreBaselineCandidate(entry, compareRecord) {
  let score = 0;
  if (entry.eligibility.sameAnchor) {
    score += 1000;
  }
  score += Math.round((entry.eligibility.overlapRatio || 0) * 100);
  const distance = Math.abs((compareRecord?.index ?? 0) - (entry.record?.index ?? 0));
  score += Math.max(0, 120 - distance * 10);
  if ((entry.record?.index ?? 0) < (compareRecord?.index ?? 0)) {
    score += 40;
  }
  return score;
}

function getEligibleBaselineEntries(records = [], compareRecord = null) {
  if (!compareRecord) {
    return [];
  }
  return records
    .filter((record) => record && record.id !== compareRecord.id)
    .map((record) => ({
      record,
      eligibility: assessPairEligibility(record, compareRecord),
    }))
    .filter((entry) => entry.eligibility.eligible)
    .sort((left, right) => scoreBaselineCandidate(right, compareRecord) - scoreBaselineCandidate(left, compareRecord));
}

function findFallbackPair(records = [], preferredCompareId = null) {
  const compareCandidates = [];
  const preferredCompare = records.find((record) => record.id === preferredCompareId) || null;
  if (preferredCompare) {
    compareCandidates.push(preferredCompare);
  }
  records.slice().reverse().forEach((record) => {
    if (!compareCandidates.some((item) => item.id === record.id)) {
      compareCandidates.push(record);
    }
  });
  for (const compareRecord of compareCandidates) {
    const baselineEntries = getEligibleBaselineEntries(records, compareRecord);
    if (baselineEntries.length) {
      return {
        compareRecord,
        baselineRecord: baselineEntries[0].record,
        baselineEntries,
      };
    }
  }
  return null;
}

function diffStringArrays(beforeValues = [], afterValues = []) {
  const before = new Set(normalizeStringArray(beforeValues));
  const after = new Set(normalizeStringArray(afterValues));
  return {
    added: [...after].filter((item) => !before.has(item)),
    removed: [...before].filter((item) => !after.has(item)),
  };
}

function formatBooleanDelta(beforeValue, afterValue, enabledLabel, disabledLabel) {
  return `${beforeValue ? enabledLabel : disabledLabel} -> ${afterValue ? enabledLabel : disabledLabel}`;
}

function formatDeltaSummary(label, beforeValue, afterValue) {
  return `${label}：${normalizeString(beforeValue, "未记录")} -> ${normalizeString(afterValue, "未记录")}`;
}

function formatArrayDelta(label, delta) {
  const parts = [];
  if (delta.added.length) {
    parts.push(`新增 ${delta.added.join("、")}`);
  }
  if (delta.removed.length) {
    parts.push(`移除 ${delta.removed.join("、")}`);
  }
  return parts.length ? `${label}：${parts.join("；")}` : "";
}

function buildContextSnapshot(record) {
  return {
    contextVersion: record.contextVersion || "未记录",
    selectedBlockCount: record.selectedBlockCount,
    pinnedBlockCount: record.pinnedBlockCount,
    includeMemorySummary: !!record.includeMemorySummary,
    includeRecentMessages: !!record.includeRecentMessages,
    modelName: record.modelName || "未记录",
  };
}

function buildSemanticGroups({
  baselineRecord,
  compareRecord,
  buildReplyWindowLabel,
} = {}) {
  const baselineSections = deriveStructuredSections(baselineRecord.message, baselineRecord.workbenchUi, {
    replyObjectCount: baselineRecord.replyObjectCount,
  });
  const compareSections = deriveStructuredSections(compareRecord.message, compareRecord.workbenchUi, {
    replyObjectCount: compareRecord.replyObjectCount,
  });
  const groups = [];

  const replyChanges = [];
  [
    ["conclusion", "结论", baselineSections.conclusion, compareSections.conclusion],
    ["time_window", "时间窗口", buildReplyWindowLabel?.(baselineRecord.workbenchUi) || baselineRecord.replyWindowLabel, buildReplyWindowLabel?.(compareRecord.workbenchUi) || compareRecord.replyWindowLabel],
    ["objects", "对象", baselineSections.objectSummary, compareSections.objectSummary],
    ["risk", "风险", baselineSections.risk, compareSections.risk],
    ["invalidation", "失效条件", baselineSections.invalidation, compareSections.invalidation],
  ].forEach(([key, label, beforeValue, afterValue]) => {
    if (normalizeString(beforeValue) === normalizeString(afterValue)) {
      return;
    }
    replyChanges.push({
      key,
      label,
      summary: formatDeltaSummary(label, beforeValue, afterValue),
      before: normalizeString(beforeValue, "未记录"),
      after: normalizeString(afterValue, "未记录"),
    });
  });
  if (replyChanges.length) {
    groups.push({ key: "reply", title: "回复变化", items: replyChanges });
  }

  const contextChanges = [];
  const beforeContext = buildContextSnapshot(baselineRecord);
  const afterContext = buildContextSnapshot(compareRecord);
  [
    ["context_version", "Context 版本", beforeContext.contextVersion, afterContext.contextVersion],
    ["selected_blocks", "已选 block", `${beforeContext.selectedBlockCount} 个`, `${afterContext.selectedBlockCount} 个`],
    ["pinned_blocks", "Pinned block", `${beforeContext.pinnedBlockCount} 个`, `${afterContext.pinnedBlockCount} 个`],
    ["model_name", "模型", beforeContext.modelName, afterContext.modelName],
  ].forEach(([key, label, beforeValue, afterValue]) => {
    if (normalizeString(beforeValue) === normalizeString(afterValue)) {
      return;
    }
    contextChanges.push({
      key,
      label,
      summary: formatDeltaSummary(label, beforeValue, afterValue),
      before: normalizeString(beforeValue, "未记录"),
      after: normalizeString(afterValue, "未记录"),
    });
  });
  if (beforeContext.includeMemorySummary !== afterContext.includeMemorySummary) {
    contextChanges.push({
      key: "memory_summary",
      label: "记忆摘要",
      summary: `上下文：${formatBooleanDelta(beforeContext.includeMemorySummary, afterContext.includeMemorySummary, "含记忆摘要", "无记忆摘要")}`,
      before: beforeContext.includeMemorySummary ? "含记忆摘要" : "无记忆摘要",
      after: afterContext.includeMemorySummary ? "含记忆摘要" : "无记忆摘要",
    });
  }
  if (beforeContext.includeRecentMessages !== afterContext.includeRecentMessages) {
    contextChanges.push({
      key: "recent_messages",
      label: "最近消息",
      summary: `上下文：${formatBooleanDelta(beforeContext.includeRecentMessages, afterContext.includeRecentMessages, "含最近消息", "无最近消息")}`,
      before: beforeContext.includeRecentMessages ? "含最近消息" : "无最近消息",
      after: afterContext.includeRecentMessages ? "含最近消息" : "无最近消息",
    });
  }
  if (contextChanges.length) {
    groups.push({ key: "context", title: "上下文变化", items: contextChanges });
  }

  const eventChanges = [];
  const eventDelta = diffStringArrays(baselineRecord.sourceEventIds, compareRecord.sourceEventIds);
  const eventSummary = formatArrayDelta("事件", eventDelta);
  if (eventSummary) {
    eventChanges.push({
      key: "source_event_ids",
      label: "事件",
      summary: eventSummary,
      before: baselineRecord.sourceEventIds.join("、") || "未记录",
      after: compareRecord.sourceEventIds.join("、") || "未记录",
    });
  }
  if (eventChanges.length) {
    groups.push({ key: "events", title: "事件变化", items: eventChanges });
  }

  const objectChanges = [];
  if (baselineRecord.replyObjectCount !== compareRecord.replyObjectCount) {
    objectChanges.push({
      key: "object_count",
      label: "图上对象",
      summary: `对象：${baselineRecord.replyObjectCount} -> ${compareRecord.replyObjectCount}`,
      before: String(baselineRecord.replyObjectCount),
      after: String(compareRecord.replyObjectCount),
    });
  }
  const sourceObjectSummary = formatArrayDelta("对象引用", diffStringArrays(baselineRecord.sourceObjectIds, compareRecord.sourceObjectIds));
  if (sourceObjectSummary) {
    objectChanges.push({
      key: "source_object_ids",
      label: "对象引用",
      summary: sourceObjectSummary,
      before: baselineRecord.sourceObjectIds.join("、") || "未记录",
      after: compareRecord.sourceObjectIds.join("、") || "未记录",
    });
  }
  const mountedSummary = formatArrayDelta("挂载对象", diffStringArrays(baselineRecord.mountedObjectIds, compareRecord.mountedObjectIds));
  if (mountedSummary) {
    objectChanges.push({
      key: "mounted_object_ids",
      label: "挂载对象",
      summary: mountedSummary,
      before: baselineRecord.mountedObjectIds.join("、") || "未记录",
      after: compareRecord.mountedObjectIds.join("、") || "未记录",
    });
  }
  if (objectChanges.length) {
    groups.push({ key: "objects", title: "对象变化", items: objectChanges });
  }

  return {
    groups,
    changeCount: groups.reduce((sum, group) => sum + group.items.length, 0),
  };
}

function buildReplyOptionMarkup(records = [], selectedId = null) {
  return records
    .map((record) => {
      const recordId = normalizeString(record?.id);
      return `<option value="${escapeHtml(recordId)}"${recordId === selectedId ? " selected" : ""}>${escapeHtml(record?.label || recordId)}</option>`;
    })
    .join("");
}

function buildPeekMarkup(comparison) {
  const topChanges = comparison.semantic.groups.flatMap((group) => group.items).slice(0, 3);
  return `
    <div class="change-inspector-hero">
      <strong>${escapeHtml(comparison.compareRecord.label)}</strong>
      <div class="meta">${escapeHtml(`相对 ${comparison.baselineRecord.label} · ${comparison.eligibility.reason}`)}</div>
      <p>${escapeHtml(`当前共检测到 ${comparison.semantic.changeCount} 条语义变化。Change Inspector 只做结构化比较，不展示原始长文本 diff。`)}</p>
    </div>
    <div class="change-inspector-chip-row">
      <span class="mini-chip ${comparison.eligibility.strength === "strong" ? "emphasis" : ""}">${escapeHtml(comparison.eligibility.sameAnchor ? "同锚点比较" : "弱比较")}</span>
      <span class="mini-chip">${escapeHtml(comparison.compareRecord.replyWindowLabel)}</span>
      <span class="mini-chip">${escapeHtml(comparison.compareRecord.contextVersion || "Context 未记录")}</span>
      ${comparison.pinned ? `<span class="mini-chip warning">Pinned</span>` : `<span class="mini-chip">跟随当前</span>`}
    </div>
    ${topChanges.length
      ? `
        <div class="change-inspector-peek-list" data-change-group="peek">
          ${topChanges.map((item) => `
            <article class="change-inspector-peek-item" data-change-record-field="${escapeHtml(item.key)}">
              <strong>${escapeHtml(item.label)}</strong>
              <p>${escapeHtml(summarizeText(item.summary, 140))}</p>
            </article>
          `).join("")}
        </div>
      `
      : `<div class="attention-first-note">这两条可比较 reply 的关键语义目前没有明显差异。</div>`}
  `;
}

function buildExpandedMarkup(comparison) {
  return `
    <div class="change-inspector-controls">
      <div class="change-inspector-mode-switch">
        <button type="button" class="secondary tiny ${comparison.mode === "peek" ? "is-active" : ""}" data-change-inspector-mode="peek">Peek</button>
        <button type="button" class="secondary tiny ${comparison.mode === "expanded" ? "is-active" : ""}" data-change-inspector-mode="expanded">Expanded</button>
      </div>
      <label class="field compact change-inspector-select">
        <span class="meta">基线</span>
        <select data-change-inspector-select="baseline">
          ${buildReplyOptionMarkup(comparison.baselineOptions, comparison.baselineRecord.id)}
        </select>
      </label>
      <label class="field compact change-inspector-select">
        <span class="meta">当前对比</span>
        <select data-change-inspector-select="compare">
          ${buildReplyOptionMarkup(comparison.compareOptions, comparison.compareRecord.id)}
        </select>
      </label>
    </div>
    <div class="change-inspector-summary meta">${escapeHtml(`当前共检测到 ${comparison.semantic.changeCount} 条语义变化。${comparison.eligibility.reason}。`)}</div>
    <div class="change-inspector-expanded-groups">
      ${comparison.semantic.groups.length
        ? comparison.semantic.groups.map((group) => `
            <section class="change-inspector-group" data-change-group="${escapeHtml(group.key)}">
              <div class="change-inspector-group-head">
                <strong>${escapeHtml(group.title)}</strong>
                <span class="meta">${escapeHtml(`${group.items.length} 条`)}</span>
              </div>
              <div class="change-inspector-record-list">
                ${group.items.map((item) => `
                  <article class="change-inspector-record" data-change-record-field="${escapeHtml(item.key)}">
                    <strong>${escapeHtml(item.label)}</strong>
                    <p>${escapeHtml(item.summary)}</p>
                    <div class="change-inspector-record-values">
                      <span>${escapeHtml(`之前：${summarizeText(item.before, 80)}`)}</span>
                      <span>${escapeHtml(`当前：${summarizeText(item.after, 80)}`)}</span>
                    </div>
                  </article>
                `).join("")}
              </div>
            </section>
          `).join("")
        : `<div class="attention-first-note">当前两条 reply 在结论、上下文、事件和对象层面没有提取到明显变化。</div>`}
    </div>
  `;
}

function buildPanelHeadMarkup(comparison) {
  return `
    <div class="strip-head attention-first-panel-head">
      <span class="strip-title">Change Inspector</span>
      <div class="attention-first-panel-actions">
        ${comparison?.eligible ? `<button type="button" class="secondary tiny ${comparison.pinned ? "is-active" : ""}" data-change-inspector-pin="true">${comparison.pinned ? "固定对比" : "跟随当前"}</button>` : ""}
        ${comparison?.eligible && comparison.panelMode === "peek" ? '<button type="button" class="secondary tiny" data-change-inspector-mode="expanded">展开细看</button>' : ""}
        <button type="button" class="secondary tiny" data-change-inspector-close="true" aria-label="关闭变化对比">关闭</button>
      </div>
    </div>
  `;
}

function buildPanelBodyMarkup(comparison) {
  const panelMode = comparison?.panelMode || "peek";
  const bodyMarkup = comparison?.eligible
    ? (panelMode === "expanded" ? buildExpandedMarkup(comparison) : buildPeekMarkup(comparison))
    : `
        <div class="change-inspector-hero is-ineligible">
          <strong>当前 reply 不可比较</strong>
          <p>${escapeHtml(comparison?.reason || "缺少满足条件的结构化 reply，Change Inspector 保持折叠。")}</p>
        </div>
      `;
  return `
    <div class="change-inspector-panel-body">
      ${bodyMarkup}
    </div>
  `;
}

function buildChangeInspectorShellMarkup() {
  return `
    <div class="change-inspector-shell">
      <div data-change-inspector-region="head"></div>
      <div data-change-inspector-region="body"></div>
    </div>
  `;
}

function hideInspectorPanel(panel) {
  if (!panel) {
    return;
  }
  panel.hidden = true;
  panel.setAttribute("aria-hidden", "true");
  panel.classList.add("is-collapsed");
  panel.dataset.mode = "collapsed";
}

export { normalizeChangeInspectorMode };

export function createWorkbenchChangeInspectorController({
  state,
  els,
  persistState = null,
  requestRender = null,
  focusReply = null,
  buildReplyWindowLabel = null,
  buildAssistantReplyLabel = null,
  getReplyObjectCount = null,
} = {}) {
  let bindingsInstalled = false;
  let currentRenderContext = {
    session: null,
    comparisonState: null,
    comparison: null,
    assistantMessages: [],
    activeMessage: null,
  };

  function ensureShell() {
    if (!els?.changeInspectorPanel) {
      return null;
    }
    updateRegionMarkup(
      els.changeInspectorPanel,
      buildChangeInspectorShellMarkup(),
      "change-inspector-shell:v1",
    );
    return els.changeInspectorPanel.querySelector(".change-inspector-shell");
  }

  function installBindings() {
    if (bindingsInstalled) {
      return;
    }
    bindingsInstalled = true;
    els?.changeInspectorToggle?.addEventListener("click", () => {
      const comparisonState = currentRenderContext.comparisonState;
      if (!comparisonState?.canToggle) {
        return;
      }
      if (state.changeInspector?.open) {
        state.changeInspector.open = false;
        persistState?.();
        requestRender?.();
        return;
      }
      const nextPair = resolveComparisonState({
        assistantMessages: currentRenderContext.assistantMessages,
        activeMessage: currentRenderContext.activeMessage,
      });
      if (!nextPair.eligibility.eligible) {
        return;
      }
      state.changeInspector.open = true;
      state.changeInspector.mode = normalizeChangeInspectorMode(state.changeInspector?.mode, { open: false });
      state.changeInspector.compareReplyId = nextPair.compareRecord.id;
      state.changeInspector.baselineReplyId = nextPair.baselineRecord.id;
      persistState?.();
      requestRender?.();
    });
    els?.changeInspectorPanel?.addEventListener("click", (event) => {
      const closeButton = event.target?.closest?.("[data-change-inspector-close]");
      if (closeButton) {
        state.changeInspector.open = false;
        persistState?.();
        requestRender?.();
        return;
      }
      const modeButton = event.target?.closest?.("[data-change-inspector-mode]");
      if (modeButton) {
        const nextMode = normalizeChangeInspectorMode(modeButton.dataset.changeInspectorMode, { open: true });
        if (state.changeInspector.mode === nextMode) {
          return;
        }
        state.changeInspector.mode = nextMode;
        state.changeInspector.open = true;
        persistState?.();
        requestRender?.();
        return;
      }
      const pinButton = event.target?.closest?.("[data-change-inspector-pin]");
      if (pinButton) {
        state.changeInspector.pinned = !state.changeInspector.pinned;
        persistState?.();
        requestRender?.();
      }
    });
    els?.changeInspectorPanel?.addEventListener("change", (event) => {
      const select = event.target?.closest?.("select[data-change-inspector-select]");
      if (!(select instanceof HTMLSelectElement)) {
        return;
      }
      const selectedId = normalizeString(select.value) || null;
      if (!selectedId) {
        return;
      }
      if (select.dataset.changeInspectorSelect === "baseline") {
        state.changeInspector.baselineReplyId = selectedId;
        state.changeInspector.open = true;
        persistState?.();
        requestRender?.();
        return;
      }
      state.changeInspector.compareReplyId = selectedId;
      state.changeInspector.open = true;
      focusReply?.(currentRenderContext.session, selectedId, { render: false });
      persistState?.();
      requestRender?.();
    });
  }

  function resolveComparisonState({ assistantMessages = [], activeMessage = null } = {}) {
    const records = (Array.isArray(assistantMessages) ? assistantMessages : [])
      .map((message, index) => buildComparableRecord(message, index, {
        getReplyObjectCount,
        buildReplyWindowLabel,
        buildAssistantReplyLabel,
      }))
      .filter(Boolean);
    const recordById = new Map(records.map((record) => [record.id, record]));
    const activeRecord = recordById.get(normalizeString(activeMessage?.message_id)) || null;
    const rawInspectorState = isPlainObject(state?.changeInspector) ? state.changeInspector : {};
    const normalizedMode = normalizeChangeInspectorMode(rawInspectorState.mode, { open: !!rawInspectorState.open });
    const requestedCompareId = rawInspectorState.pinned
      ? normalizeString(rawInspectorState.compareReplyId)
      : normalizeString(activeRecord?.id);
    let fallbackPair = findFallbackPair(records, requestedCompareId);
    if (!fallbackPair && requestedCompareId) {
      fallbackPair = findFallbackPair(records);
    }
    const requestedCompare = recordById.get(requestedCompareId) || null;
    let compareRecord = requestedCompare || fallbackPair?.compareRecord || null;
    let baselineEntries = getEligibleBaselineEntries(records, compareRecord);
    if (!baselineEntries.length && fallbackPair) {
      compareRecord = fallbackPair.compareRecord;
      baselineEntries = fallbackPair.baselineEntries || getEligibleBaselineEntries(records, compareRecord);
    }
    const requestedBaselineId = normalizeString(rawInspectorState.baselineReplyId);
    let baselineRecord = baselineEntries.find((entry) => entry.record.id === requestedBaselineId)?.record || null;
    if (!baselineRecord && baselineEntries.length) {
      baselineRecord = baselineEntries[0].record;
    }
    const eligibility = assessPairEligibility(baselineRecord, compareRecord);
    const compareOptions = records.filter((record) => getEligibleBaselineEntries(records, record).length > 0);
    const canInspectFromActive = !!activeRecord && getEligibleBaselineEntries(records, activeRecord).length > 0;
    const pinnedComparable = !!rawInspectorState.pinned && eligibility.eligible;
    const canToggle = compareOptions.length > 0 && (canInspectFromActive || pinnedComparable);
    const statePatch = {};
    if (rawInspectorState.mode !== normalizedMode) {
      statePatch.mode = normalizedMode;
    }
    if (eligibility.eligible && compareRecord && rawInspectorState.compareReplyId !== compareRecord.id) {
      statePatch.compareReplyId = compareRecord.id;
    }
    if (eligibility.eligible && baselineRecord && rawInspectorState.baselineReplyId !== baselineRecord.id) {
      statePatch.baselineReplyId = baselineRecord.id;
    }
    return {
      compareRecord,
      baselineRecord,
      compareOptions,
      baselineOptions: baselineEntries.map((entry) => entry.record),
      eligibility,
      canToggle,
      statePatch,
      panelMode: normalizedMode,
    };
  }

  function applyStatePatch(statePatch = {}) {
    if (!Object.keys(statePatch).length) {
      return false;
    }
    state.changeInspector = {
      ...(isPlainObject(state.changeInspector) ? state.changeInspector : {}),
      ...statePatch,
    };
    return true;
  }

  function render({ session, assistantMessages = [], activeMessage = null } = {}) {
    const panel = els?.changeInspectorPanel;
    const toggle = els?.changeInspectorToggle;
    if (!panel) {
      return;
    }
    installBindings();
    const comparisonState = resolveComparisonState({ assistantMessages, activeMessage });
    currentRenderContext = {
      session,
      comparisonState,
      comparison: null,
      assistantMessages,
      activeMessage,
    };
    const stateChanged = applyStatePatch(comparisonState.statePatch);
    if (toggle) {
      toggle.hidden = !comparisonState.canToggle;
      toggle.setAttribute("aria-expanded", state.changeInspector?.open && comparisonState.canToggle ? "true" : "false");
      toggle.classList.toggle("is-active", !!state.changeInspector?.open && comparisonState.canToggle);
      toggle.textContent = state.changeInspector?.open && comparisonState.canToggle ? "收起对比" : "变化对比";
    }
    if (stateChanged) {
      persistState?.();
    }
    if (!state.changeInspector?.open || !comparisonState.canToggle) {
      hideInspectorPanel(panel);
      return;
    }
    const comparison = comparisonState.eligibility.eligible
      ? {
        eligible: true,
        mode: comparisonState.panelMode,
        panelMode: comparisonState.panelMode,
        pinned: !!state.changeInspector?.pinned,
        compareRecord: comparisonState.compareRecord,
        baselineRecord: comparisonState.baselineRecord,
        compareOptions: comparisonState.compareOptions,
        baselineOptions: comparisonState.baselineOptions,
        eligibility: comparisonState.eligibility,
        semantic: buildSemanticGroups({
          baselineRecord: comparisonState.baselineRecord,
          compareRecord: comparisonState.compareRecord,
          buildReplyWindowLabel,
        }),
      }
      : {
        eligible: false,
        panelMode: comparisonState.panelMode,
        reason: comparisonState.eligibility.reason,
      };
    currentRenderContext.comparison = comparison;
    panel.hidden = false;
    panel.setAttribute("aria-hidden", "false");
    panel.classList.remove("is-collapsed");
    panel.dataset.mode = comparison.panelMode;
    const shell = ensureShell();
    const headRegion = shell?.querySelector?.('[data-change-inspector-region="head"]');
    const bodyRegion = shell?.querySelector?.('[data-change-inspector-region="body"]');
    updateRegionMarkup(headRegion, buildPanelHeadMarkup(comparison), JSON.stringify({
      eligible: !!comparison.eligible,
      pinned: !!comparison.pinned,
      panelMode: comparison.panelMode,
    }), {
      preserveState: true,
      stateOptions: {
        anchorSelector: "[data-change-inspector-pin], [data-change-inspector-mode], [data-change-inspector-close]",
      },
    });
    updateRegionMarkup(bodyRegion, buildPanelBodyMarkup(comparison), JSON.stringify({
      eligible: !!comparison.eligible,
      panelMode: comparison.panelMode,
      pinned: !!comparison.pinned,
      reason: comparison.reason || "",
      compareId: comparison.compareRecord?.id || "",
      baselineId: comparison.baselineRecord?.id || "",
      changeCount: comparison.semantic?.changeCount || 0,
      groups: comparison.semantic?.groups?.map((group) => ({
        key: group.key,
        size: group.items.length,
        items: group.items.map((item) => ({
          key: item.key,
          before: item.before,
          after: item.after,
        })),
      })) || [],
    }), {
      preserveState: true,
      stateOptions: {
        anchorSelector: "[data-change-inspector-select], [data-change-group], [data-change-record-field], .change-inspector-hero",
      },
    });
  }

  return {
    render,
    hide() {
      hideInspectorPanel(els?.changeInspectorPanel);
    },
  };
}
