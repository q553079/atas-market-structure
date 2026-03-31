import { escapeHtml, summarizeText } from "./replay_workbench_ui_utils.js";

const ASSERTION_META = {
  observational: {
    label: "观察性",
    tone: "observational",
    caution: false,
  },
  conditional: {
    label: "条件性",
    tone: "conditional",
    caution: true,
  },
  high_uncertainty: {
    label: "高不确定",
    tone: "high-uncertainty",
    caution: true,
  },
  insufficient_context: {
    label: "上下文不足",
    tone: "insufficient-context",
    caution: true,
  },
};

const ALIGNMENT_LABELS = {
  aligned: "已对齐",
  ambiguous: "模糊",
  out_of_bounds: "超出窗口",
  pending_confirmation: "待确认",
  partial: "部分对齐",
};

const STALE_LABELS = {
  current_window: "当前窗口",
  stale_window: "旧窗口",
  cross_day_anchor: "跨日锚点",
  refresh_needed: "需刷新",
};

const RISK_PATTERN = /(风险|失效|跌破|失守|守不住|回撤|止损|无效|破坏|谨防)/i;
const INVALIDATION_PATTERN = /(失效|无效|若.*跌破|若.*失守|守不住|破坏|否则)/i;
const UNCERTAINTY_PATTERN = /(不确定|需确认|待确认|样本不足|上下文不足|缺少|无法判断|可能|观察后再定)/i;
const EVIDENCE_PATTERN = /(证据|依据|观察到|来自|因为|由于|量能|成交|对象|事件)/i;
const NEXT_PATTERN = /(下一步|继续观察|观察|关注|等待|确认|留意)/i;
const OBJECT_PATTERN = /(对象|关键位|价位|区域|事件|支撑|阻力|锚点)/i;

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

function toFiniteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function getWorkbenchUiMeta(meta = {}) {
  const merged = mergePlainObjects(
    isPlainObject(meta?.workbenchUi) ? meta.workbenchUi : {},
    isPlainObject(meta?.workbench_ui) ? meta.workbench_ui : {},
  );
  return Object.keys(merged).length ? merged : null;
}

function normalizeStringArray(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  const text = String(value ?? "").trim();
  return text ? [text] : [];
}

function formatCompactDateTime(value) {
  const timestamp = Date.parse(String(value || ""));
  if (!Number.isFinite(timestamp)) {
    return "--";
  }
  const date = new Date(timestamp);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hours}:${minutes}`;
}

function buildReplyWindowLabel(workbenchUi = {}) {
  const replyWindow = isPlainObject(workbenchUi?.reply_window)
    ? workbenchUi.reply_window
    : (isPlainObject(workbenchUi?.replyWindow) ? workbenchUi.replyWindow : {});
  const startTime = pickFirstDefined(
    replyWindow.window_start,
    replyWindow.windowStart,
    workbenchUi.window_start,
    workbenchUi.windowStart,
  );
  const endTime = pickFirstDefined(
    replyWindow.window_end,
    replyWindow.windowEnd,
    workbenchUi.window_end,
    workbenchUi.windowEnd,
  );
  if (startTime || endTime) {
    return `${formatCompactDateTime(startTime)} -> ${formatCompactDateTime(endTime)}`;
  }
  const anchor = String(pickFirstDefined(workbenchUi.reply_window_anchor, workbenchUi.replyWindowAnchor) || "").trim();
  return anchor || "未记录";
}

function splitTextFragments(content = "") {
  const raw = String(content || "").replace(/\r\n/g, "\n").trim();
  const lines = raw
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const sentences = [];
  lines.forEach((line) => {
    line
      .split(/(?<=[。！？!?；;])/)
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((item) => sentences.push(item));
  });
  if (!sentences.length && raw) {
    sentences.push(raw);
  }
  return { raw, lines, sentences };
}

function extractHeadingValue(lines = [], headings = []) {
  for (const line of lines) {
    for (const heading of headings) {
      const regex = new RegExp(`^${heading}[：:：\\-\\s]+(.+)$`, "i");
      const match = line.match(regex);
      if (match?.[1]) {
        return match[1].trim();
      }
    }
  }
  return "";
}

function findSentence(sentences = [], pattern, exclude = new Set()) {
  return sentences.find((sentence) => !exclude.has(sentence) && pattern.test(sentence)) || "";
}

function formatFallbackLabel(value = "") {
  return String(value || "").trim().replace(/[_-]+/g, " ") || "未标注";
}

function normalizeAssertionLevel(value = "") {
  const normalized = String(value || "").trim().toLowerCase().replace(/[_\s]+/g, "_");
  if (ASSERTION_META[normalized]) {
    return normalized;
  }
  if (["grounded", "ground"].includes(normalized)) {
    return "observational";
  }
  if (["review", "needs_review"].includes(normalized)) {
    return "high_uncertainty";
  }
  return normalized || "";
}

function getAssertionMeta(value = "") {
  const normalized = normalizeAssertionLevel(value);
  if (ASSERTION_META[normalized]) {
    return {
      value: normalized,
      label: ASSERTION_META[normalized].label,
      tone: ASSERTION_META[normalized].tone,
      caution: ASSERTION_META[normalized].caution,
    };
  }
  return {
    value: normalized,
    label: formatFallbackLabel(normalized),
    tone: "legacy",
    caution: false,
  };
}

function buildObjectChips(workbenchUi = {}, replyObjectCount = 0) {
  const objectCount = Math.max(
    toFiniteNumber(pickFirstDefined(workbenchUi.object_count, workbenchUi.objectCount), 0),
    toFiniteNumber(replyObjectCount, 0),
  );
  const sourceEventIds = normalizeStringArray(pickFirstDefined(workbenchUi.source_event_ids, workbenchUi.sourceEventIds));
  const sourceObjectIds = normalizeStringArray(pickFirstDefined(workbenchUi.source_object_ids, workbenchUi.sourceObjectIds));
  const chips = [];
  if (objectCount > 0) {
    chips.push(`图上对象 ${objectCount}`);
  }
  if (sourceEventIds.length) {
    chips.push(`引用事件 ${sourceEventIds.length}`);
  }
  if (sourceObjectIds.length) {
    chips.push(`绑定对象 ${sourceObjectIds.length}`);
  }
  const alignmentState = String(pickFirstDefined(workbenchUi.alignment_state, workbenchUi.alignmentState) || "").trim().toLowerCase();
  if (alignmentState) {
    chips.push(`对齐 ${ALIGNMENT_LABELS[alignmentState] || formatFallbackLabel(alignmentState)}`);
  }
  return chips;
}

function buildUsedTextSet(values = []) {
  return new Set(values.map((item) => String(item || "").trim()).filter(Boolean));
}

export function deriveStructuredSections(message = {}, workbenchUi = null, { replyObjectCount = 0 } = {}) {
  const fragments = splitTextFragments(message.content || "");
  const headingConclusion = extractHeadingValue(fragments.lines, ["结论", "核心结论", "判断", "结论摘要"]);
  const headingRisk = extractHeadingValue(fragments.lines, ["风险", "主要风险"]);
  const headingInvalidation = extractHeadingValue(fragments.lines, ["失效条件", "无效条件", "失效", "条件失效"]);
  const headingUncertainty = extractHeadingValue(fragments.lines, ["不确定性", "需确认", "上下文不足", "缺少上下文"]);
  const headingEvidence = extractHeadingValue(fragments.lines, ["证据", "依据", "观察依据"]);
  const headingNext = extractHeadingValue(fragments.lines, ["下一步观察", "下一步", "继续观察", "关注点"]);
  const headingTime = extractHeadingValue(fragments.lines, ["时间", "窗口", "时间窗口"]);
  const headingObjects = extractHeadingValue(fragments.lines, ["对象", "关键对象", "结构对象"]);
  const assertionMeta = getAssertionMeta(pickFirstDefined(workbenchUi?.assertion_level, workbenchUi?.assertionLevel, message.meta?.assertion_level));
  const pendingShell = ["pending", "streaming"].includes(String(message.status || "").trim().toLowerCase());
  const insufficientContext = assertionMeta.value === "insufficient_context";
  const highUncertainty = assertionMeta.value === "high_uncertainty";
  const conditional = assertionMeta.value === "conditional";

  const used = buildUsedTextSet([
    headingConclusion,
    headingRisk,
    headingInvalidation,
    headingUncertainty,
    headingEvidence,
    headingNext,
    headingTime,
    headingObjects,
  ]);

  const invalidation = headingInvalidation
    || findSentence(fragments.sentences, INVALIDATION_PATTERN, used)
    || (conditional ? "需失效条件" : "");
  if (invalidation) {
    used.add(invalidation);
  }

  const uncertainty = headingUncertainty
    || findSentence(fragments.sentences, UNCERTAINTY_PATTERN, used)
    || (highUncertainty ? "不确定性高，当前窗口不足以支撑稳定方向判断。" : "")
    || (insufficientContext ? "缺少足够的窗口、对象或上下文，暂不形成方向性结论。" : "");
  if (uncertainty) {
    used.add(uncertainty);
  }

  const risk = headingRisk
    || findSentence(fragments.sentences, RISK_PATTERN, used)
    || invalidation
    || (highUncertainty ? "当前高不确定，风险在于把观察性变化误读成稳定脚本。" : "")
    || (insufficientContext ? "当前上下文不足，强行下结论的主要风险是误判。" : "")
    || "未提取到明确风险提示。";
  if (risk) {
    used.add(risk);
  }

  const evidence = headingEvidence || findSentence(fragments.sentences, EVIDENCE_PATTERN, used) || "";
  if (evidence) {
    used.add(evidence);
  }

  const nextObservation = headingNext || findSentence(fragments.sentences, NEXT_PATTERN, used) || "";
  if (nextObservation) {
    used.add(nextObservation);
  }

  const conclusion = headingConclusion
    || (!insufficientContext
      ? fragments.sentences.find((sentence) => !used.has(sentence) && !RISK_PATTERN.test(sentence) && !UNCERTAINTY_PATTERN.test(sentence))
      : "")
    || (insufficientContext ? "当前上下文不足，暂不形成方向性结论。" : "")
    || (pendingShell ? "正在整理当前窗口的结构、对象与风险。" : "")
    || summarizeText(message.content || message.replyTitle || "暂无结论", 140);
  if (conclusion) {
    used.add(conclusion);
  }

  const noteSource = fragments.lines.filter((line) => !used.has(line)).join("\n");
  const shortNote = summarizeText(
    noteSource || message.content || message.replyTitle || "",
    220,
  );

  const timeLabel = headingTime || buildReplyWindowLabel(workbenchUi || {});
  const replySessionDate = String(pickFirstDefined(workbenchUi?.reply_session_date, workbenchUi?.replySessionDate) || "").trim();
  const objectChips = buildObjectChips(workbenchUi || {}, replyObjectCount);
  const objectSummary = headingObjects || (objectChips.length ? objectChips.join(" · ") : "当前未记录图上对象。");
  const staleState = String(pickFirstDefined(workbenchUi?.stale_state, workbenchUi?.staleState) || "").trim().toLowerCase();

  return {
    assertionMeta,
    pendingShell,
    insufficientContext,
    highUncertainty,
    conditional,
    conclusion,
    timeLabel,
    replySessionDate: replySessionDate || "未记录",
    objectSummary,
    objectChips,
    risk,
    invalidation,
    uncertainty,
    evidence,
    nextObservation,
    shortNote,
    staleLabel: staleState ? (STALE_LABELS[staleState] || formatFallbackLabel(staleState)) : "",
  };
}

function renderSection(label, value, { sectionKey = "", compact = false, skeleton = false } = {}) {
  const safeValue = String(value || "").trim();
  return `
    <section class="answer-card-section ${compact ? "is-compact" : ""}"${sectionKey ? ` data-answer-section="${escapeHtml(sectionKey)}"` : ""}>
      <span class="answer-card-section-label">${escapeHtml(label)}</span>
      ${skeleton
        ? `<div class="answer-card-skeleton-block"><span class="answer-card-skeleton-line wide"></span><span class="answer-card-skeleton-line"></span></div>`
        : `<div class="answer-card-section-value">${escapeHtml(safeValue || "未提供")}</div>`}
    </section>
  `;
}

function renderChip(text, extraClass = "") {
  return `<span class="answer-card-chip ${escapeHtml(extraClass)}">${escapeHtml(text)}</span>`;
}

function renderObjectChip(text) {
  return `<span class="answer-card-object-chip">${escapeHtml(text)}</span>`;
}

function buildMetaChipMarkup(message = {}, sections = {}, replyObjectCount = 0) {
  const chips = [];
  const status = String(message.status || "").trim().toLowerCase();
  if (status) {
    chips.push(renderChip(status, `status-${status}`));
  }
  if (message.isActiveReply) {
    chips.push(renderChip("当前回复", "is-active"));
  }
  if (message.parent_message_id || message.meta?.parent_message_id) {
    chips.push(renderChip("重新生成", "is-regenerated"));
  }
  if (message.meta?.session_only) {
    chips.push(renderChip("session-only", "is-session-only"));
  }
  if (message.meta?.provider || message.meta?.model) {
    chips.push(renderChip([message.meta?.provider, message.meta?.model].filter(Boolean).join("/"), "is-model"));
  }
  if (replyObjectCount > 0) {
    chips.push(renderChip(`对象 ${replyObjectCount}`, "is-objects"));
  }
  if (sections.assertionMeta.label) {
    chips.push(renderChip(sections.assertionMeta.label, `assertion-${sections.assertionMeta.tone}`));
  }
  if (sections.staleLabel) {
    chips.push(renderChip(sections.staleLabel, "is-stale"));
  }
  return chips.join("");
}

function renderCautionBlock(sections = {}) {
  if (sections.conditional && sections.invalidation) {
    return `
      <section class="answer-card-caution caution-conditional" data-answer-section="invalidation">
        <span class="answer-card-section-label">失效条件</span>
        <div class="answer-card-section-value">${escapeHtml(sections.invalidation)}</div>
      </section>
    `;
  }
  if (sections.highUncertainty && sections.uncertainty) {
    return `
      <section class="answer-card-caution caution-high-uncertainty" data-answer-section="uncertainty">
        <span class="answer-card-section-label">不确定性</span>
        <div class="answer-card-section-value">${escapeHtml(sections.uncertainty)}</div>
      </section>
    `;
  }
  if (sections.insufficientContext && sections.uncertainty) {
    return `
      <section class="answer-card-caution caution-insufficient-context" data-answer-section="uncertainty">
        <span class="answer-card-section-label">缺失上下文</span>
        <div class="answer-card-section-value">${escapeHtml(sections.uncertainty)}</div>
      </section>
    `;
  }
  return "";
}

function renderFullCard({
  message,
  sections,
  replyTitle,
  replyObjectCount,
  longTextMarkup,
  attachmentsMarkup,
  messageActionMarkup,
  planCardsMarkup,
}) {
  const skeleton = sections.pendingShell && (!message.content || message.content === "正在思考中…");
  return `
    <article
      class="answer-card answer-card-full ${sections.insufficientContext ? "is-insufficient-context" : ""}"
      data-structured-answer-card="true"
      data-card-density="full"
      data-assertion-level="${escapeHtml(sections.assertionMeta.value || "unknown")}"
    >
      <header class="answer-card-head">
        <div class="answer-card-chip-row">${buildMetaChipMarkup(message, sections, replyObjectCount)}</div>
        <div class="answer-card-title-row">
          <div class="answer-card-title-copy">
            <span class="answer-card-kicker">${escapeHtml(replyTitle)}</span>
            <strong class="answer-card-title ${sections.insufficientContext ? "is-muted" : ""}">${escapeHtml(sections.insufficientContext ? "上下文不足" : sections.conclusion)}</strong>
          </div>
          <div class="answer-card-time-meta">${escapeHtml(sections.timeLabel)}</div>
        </div>
      </header>
      <div class="answer-card-grid">
        ${renderSection("结论", sections.conclusion, { sectionKey: "conclusion", skeleton })}
        ${renderSection("时间", `${sections.timeLabel} · ${sections.replySessionDate}`, { sectionKey: "time", skeleton })}
        <section class="answer-card-section" data-answer-section="objects">
          <span class="answer-card-section-label">对象</span>
          <div class="answer-card-object-row">
            ${sections.objectChips.length
              ? sections.objectChips.map((item) => renderObjectChip(item)).join("")
              : `<span class="answer-card-section-value">${escapeHtml(sections.objectSummary)}</span>`}
          </div>
        </section>
        ${renderSection("风险", sections.risk, { sectionKey: "risk", skeleton })}
      </div>
      ${renderCautionBlock(sections)}
      ${sections.evidence ? renderSection("证据", sections.evidence, { sectionKey: "evidence", compact: true }) : ""}
      ${sections.nextObservation ? renderSection("下一步观察", sections.nextObservation, { sectionKey: "next_observation", compact: true }) : ""}
      ${!sections.pendingShell && sections.shortNote && sections.shortNote !== sections.conclusion && sections.shortNote !== sections.risk
        ? `
          <section class="answer-card-section answer-card-note" data-answer-section="note">
            <span class="answer-card-section-label">简短说明</span>
            <div class="answer-card-longtext">${longTextMarkup}</div>
          </section>
        `
        : ""}
      ${attachmentsMarkup}
      ${messageActionMarkup}
      ${planCardsMarkup}
    </article>
  `;
}

function renderCompactCard({
  message,
  sections,
  replyTitle,
  replyObjectCount,
  messageActionMarkup,
}) {
  const cautionText = sections.conditional
    ? sections.invalidation
    : (sections.highUncertainty || sections.insufficientContext ? sections.uncertainty : "");
  return `
    <article
      class="answer-card answer-card-compact ${sections.insufficientContext ? "is-insufficient-context" : ""}"
      data-structured-answer-card="true"
      data-card-density="compact"
      data-assertion-level="${escapeHtml(sections.assertionMeta.value || "unknown")}"
    >
      <header class="answer-card-head compact">
        <div class="answer-card-chip-row">${buildMetaChipMarkup(message, sections, replyObjectCount)}</div>
        <div class="answer-card-title-row">
          <div class="answer-card-title-copy">
            <span class="answer-card-kicker">${escapeHtml(replyTitle)}</span>
            <strong class="answer-card-title ${sections.insufficientContext ? "is-muted" : ""}" data-answer-section="conclusion">${escapeHtml(summarizeText(sections.conclusion, 72))}</strong>
          </div>
          <div class="answer-card-time-meta">${escapeHtml(sections.timeLabel)}</div>
        </div>
      </header>
      <div class="answer-card-compact-meta">
        <span data-answer-section="time">${escapeHtml(sections.replySessionDate)}</span>
        <span data-answer-section="risk">${escapeHtml(summarizeText(sections.risk, 42))}</span>
      </div>
      ${cautionText ? `<div class="answer-card-compact-caution" ${sections.conditional ? 'data-answer-section="invalidation"' : 'data-answer-section="uncertainty"'}>${escapeHtml(summarizeText(cautionText, 70))}</div>` : ""}
      ${messageActionMarkup}
    </article>
  `;
}

function renderSkimCard({
  message,
  sections,
  replyTitle,
  replyObjectCount,
  messageActionMarkup,
}) {
  const cautionText = sections.conditional
    ? "需失效条件"
    : (sections.highUncertainty ? "不确定性高" : (sections.insufficientContext ? "上下文不足" : ""));
  return `
    <article
      class="answer-card answer-card-skim ${sections.insufficientContext ? "is-insufficient-context" : ""}"
      data-structured-answer-card="true"
      data-card-density="skim"
      data-assertion-level="${escapeHtml(sections.assertionMeta.value || "unknown")}"
    >
      <header class="answer-card-skim-head">
        <span class="answer-card-skim-title">${escapeHtml(summarizeText(replyTitle || sections.conclusion, 20))}</span>
        <span class="answer-card-skim-time" data-answer-section="time">${escapeHtml(sections.timeLabel)}</span>
      </header>
      <div class="answer-card-skim-meta">
        ${buildMetaChipMarkup(message, sections, replyObjectCount)}
        ${cautionText ? `<span class="answer-card-skim-note" ${sections.conditional ? 'data-answer-section="invalidation"' : 'data-answer-section="uncertainty"'}>${escapeHtml(cautionText)}</span>` : ""}
      </div>
      ${messageActionMarkup}
    </article>
  `;
}

export function buildAssistantDensityMap(messages = [], activeReplyId = null) {
  const assistantMessages = (Array.isArray(messages) ? messages : []).filter((message) => message?.role === "assistant");
  const densityMap = new Map();
  if (!assistantMessages.length) {
    return densityMap;
  }
  const fallbackActiveId = String(activeReplyId || "").trim() || String(assistantMessages[assistantMessages.length - 1]?.message_id || "").trim();
  if (fallbackActiveId) {
    densityMap.set(fallbackActiveId, "full");
  }
  const newestNonActive = [...assistantMessages]
    .reverse()
    .find((message) => String(message?.message_id || "").trim() && String(message?.message_id || "").trim() !== fallbackActiveId);
  if (newestNonActive?.message_id) {
    densityMap.set(String(newestNonActive.message_id), "compact");
  }
  assistantMessages.forEach((message) => {
    const messageId = String(message?.message_id || "").trim();
    if (!messageId || densityMap.has(messageId)) {
      return;
    }
    densityMap.set(messageId, "skim");
  });
  return densityMap;
}

export function canRenderStructuredAssistantMessage(message = {}) {
  if (message?.role !== "assistant") {
    return false;
  }
  if (getWorkbenchUiMeta(message.meta)) {
    return true;
  }
  const status = String(message.status || "").trim().toLowerCase();
  const localPendingMessageId = String(message.meta?.localPendingMessageId || "").trim();
  if (status === "pending" || status === "streaming") {
    return true;
  }
  return !!localPendingMessageId && ["failed", "interrupted"].includes(status);
}

export function renderStructuredAnswerCard({
  message,
  density = "full",
  expandedLongText = false,
  replyObjectCount = 0,
  canProjectReply = false,
  includeMessageActions = false,
  includeAttachments = false,
  includePlanCards = false,
  renderLongTextMarkup,
  renderAttachmentPreview,
  buildPlanCardMarkup,
}) {
  const workbenchUi = getWorkbenchUiMeta(message.meta);
  const resolvedDensity = ["full", "compact", "skim"].includes(String(density || "").trim().toLowerCase())
    ? String(density || "").trim().toLowerCase()
    : "full";
  const sections = deriveStructuredSections(message, workbenchUi, { replyObjectCount });
  const replyTitle = String(message.replyTitle || message.meta?.replyTitle || "结构化答复卡").trim() || "结构化答复卡";
  const attachments = Array.isArray(message.meta?.attachments) ? message.meta.attachments : [];
  const planCards = Array.isArray(message.meta?.planCards) ? message.meta.planCards : [];
  const allowPlanCards = !sections.insufficientContext;
  const attachmentsMarkup = includeAttachments && attachments.length && resolvedDensity === "full" && typeof renderAttachmentPreview === "function"
    ? `<div class="chat-attachment-list">${attachments.map((item) => renderAttachmentPreview(item)).join("")}</div>`
    : "";
  const messageActionMarkup = includeMessageActions
    ? `
      <div class="chat-message-actions">
        <button
          type="button"
          class="secondary tiny"
          data-message-action="${message.mountedToChart ? "unmount" : "show"}"
          data-message-id="${escapeHtml(message.message_id || "")}"
          ${canProjectReply ? "" : "disabled"}
        >${message.mountedToChart ? "取消上图" : "上图"}</button>
        <button
          type="button"
          class="secondary tiny"
          data-message-action="focus"
          data-message-id="${escapeHtml(message.message_id || "")}"
          ${canProjectReply ? "" : "disabled"}
        >仅本条</button>
        <button
          type="button"
          class="secondary tiny"
          data-message-action="jump"
          data-message-id="${escapeHtml(message.message_id || "")}"
          ${canProjectReply ? "" : "disabled"}
        >查看图表</button>
        <button
          type="button"
          class="secondary tiny"
          data-message-action="prompt-trace"
          data-message-id="${escapeHtml(message.message_id || "")}"
          data-prompt-trace-id="${escapeHtml(message.promptTraceId || message.meta?.promptTraceId || "")}"
        >查看 Prompt Trace</button>
        <button type="button" class="secondary tiny" data-message-action="regenerate" data-message-id="${escapeHtml(message.message_id || "")}">重新生成</button>
      </div>
    `
    : "";
  const planCardsMarkup = includePlanCards && allowPlanCards && planCards.length && resolvedDensity === "full" && typeof buildPlanCardMarkup === "function"
    ? `<div class="chat-plan-card-list">${planCards.map((item) => buildPlanCardMarkup(item)).join("")}</div>`
    : "";
  const longTextMarkup = typeof renderLongTextMarkup === "function"
    ? renderLongTextMarkup(message.content || "", {
      expanded: expandedLongText,
      messageId: message.message_id || "",
      limit: 260,
    })
    : `<p>${escapeHtml(message.content || "")}</p>`;
  let cardMarkup = "";
  if (resolvedDensity === "skim") {
    cardMarkup = renderSkimCard({
      message,
      sections,
      replyTitle,
      replyObjectCount,
      messageActionMarkup,
    });
  } else if (resolvedDensity === "compact") {
    cardMarkup = renderCompactCard({
      message,
      sections,
      replyTitle,
      replyObjectCount,
      messageActionMarkup,
      });
  } else {
    cardMarkup = renderFullCard({
      message,
      sections,
      replyTitle,
      replyObjectCount,
      longTextMarkup,
      attachmentsMarkup,
      messageActionMarkup,
      planCardsMarkup,
    });
  }
  return cardMarkup;
}

export function renderStructuredAssistantMessage({
  message,
  density = "full",
  expandedLongText = false,
  replyObjectCount = 0,
  canProjectReply = false,
  renderLongTextMarkup,
  renderAttachmentPreview,
  buildPlanCardMarkup,
}) {
  const cardMarkup = renderStructuredAnswerCard({
    message,
    density,
    expandedLongText,
    replyObjectCount,
    canProjectReply,
    includeMessageActions: true,
    includeAttachments: true,
    includePlanCards: true,
    renderLongTextMarkup,
    renderAttachmentPreview,
    buildPlanCardMarkup,
  });
  const workbenchUi = getWorkbenchUiMeta(message.meta);
  const sections = deriveStructuredSections(message, workbenchUi, { replyObjectCount });
  const resolvedDensity = ["full", "compact", "skim"].includes(String(density || "").trim().toLowerCase())
    ? String(density || "").trim().toLowerCase()
    : "full";
  return `
    <div class="chat-message ${escapeHtml(message.role)} ${escapeHtml(message.status || "")} structured-answer-message ${message.isActiveReply ? "is-reply-focus" : ""}" data-message-id="${escapeHtml(message.message_id || "")}">
      <div class="chat-bubble ${escapeHtml(message.role)} ${escapeHtml(message.status || "")} answer-card-shell density-${escapeHtml(resolvedDensity)} assertion-${escapeHtml(sections.assertionMeta.tone || "legacy")}">
        <div class="chat-bubble-body">
          ${cardMarkup}
          ${(message.parent_message_id || message.meta?.parent_message_id) ? `<div class="chat-regenerate-note">由上一条回复重新生成</div>` : ""}
        </div>
      </div>
    </div>
  `;
}
