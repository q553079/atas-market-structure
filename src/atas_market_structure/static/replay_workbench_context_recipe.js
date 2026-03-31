import { escapeHtml, summarizeText } from "./replay_workbench_ui_utils.js";
import { updateRegionMarkup } from "./replay_workbench_render_stability.js";

function isPlainObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function pickFirstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && !(typeof value === "number" && Number.isNaN(value))) {
      return value;
    }
  }
  return undefined;
}

function normalizeString(value, fallback = "") {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function normalizeId(value) {
  return normalizeString(value, "");
}

function hasReplyWindowShape(value) {
  if (!isPlainObject(value)) {
    return false;
  }
  return [
    value.window_start,
    value.windowStart,
    value.window_end,
    value.windowEnd,
    value.reply_window_anchor,
    value.replyWindowAnchor,
  ].some((item) => normalizeString(item, ""));
}

function resolveReplyWindowSource({ workbenchUi = null, trace = null } = {}) {
  const candidates = [
    isPlainObject(workbenchUi?.reply_window) ? workbenchUi.reply_window : null,
    isPlainObject(workbenchUi?.replyWindow) ? workbenchUi.replyWindow : null,
    hasReplyWindowShape(workbenchUi) ? workbenchUi : null,
    isPlainObject(trace?.reply_window) ? trace.reply_window : null,
    isPlainObject(trace?.snapshot?.reply_window) ? trace.snapshot.reply_window : null,
    isPlainObject(trace?.metadata?.reply_window) ? trace.metadata.reply_window : null,
    hasReplyWindowShape(trace) ? trace : null,
    hasReplyWindowShape(trace?.snapshot) ? trace.snapshot : null,
    hasReplyWindowShape(trace?.metadata) ? trace.metadata : null,
  ];
  return candidates.find((candidate) => hasReplyWindowShape(candidate)) || null;
}

function resolveReplyWindowLabel({
  workbenchUi = null,
  trace = null,
  session = null,
  buildReplyWindowLabel = () => "未记录",
} = {}) {
  const replyWindowSource = resolveReplyWindowSource({ workbenchUi, trace });
  if (replyWindowSource) {
    const label = normalizeString(buildReplyWindowLabel(replyWindowSource), "");
    if (label && label !== "未记录") {
      return label;
    }
  }
  return normalizeString(session?.windowRange, "未记录");
}

function toPositiveInt(value, fallback = 1) {
  const next = Number.parseInt(value, 10);
  if (!Number.isFinite(next) || next < 1) {
    return fallback;
  }
  return next;
}

function formatBooleanLabel(value, positiveLabel, negativeLabel) {
  return value ? positiveLabel : negativeLabel;
}

function resolvePromptTraceRef(message = {}) {
  return {
    promptTraceId: normalizeId(
      message.promptTraceId
      || message.prompt_trace_id
      || message.meta?.promptTraceId
      || message.meta?.prompt_trace_id
    ) || null,
    messageId: normalizeId(message.message_id || message.id) || null,
  };
}

function getCurrentPromptBlockIndex(session = {}) {
  const index = new Map();
  const promptBlocks = Array.isArray(session.promptBlocks) ? session.promptBlocks : [];
  promptBlocks.forEach((block) => {
    const blockId = normalizeId(block?.blockId || block?.block_id || block?.id);
    if (blockId) {
      index.set(blockId, block);
    }
  });
  return index;
}

function normalizeContextRefs({ activeUi = null, trace = null, session = {} } = {}) {
  const traceBlocks = Array.isArray(trace?.context_blocks)
    ? trace.context_blocks
    : (Array.isArray(trace?.snapshot?.context_blocks)
      ? trace.snapshot.context_blocks
      : (Array.isArray(trace?.metadata?.block_version_refs) ? trace.metadata.block_version_refs : []));
  const uiBlocks = Array.isArray(activeUi?.context_blocks)
    ? activeUi.context_blocks
    : (Array.isArray(activeUi?.contextBlocks) ? activeUi.contextBlocks : []);
  let rawBlocks = traceBlocks.length ? traceBlocks : uiBlocks;
  if (!rawBlocks.length) {
    const selectedIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
    const blockIndex = getCurrentPromptBlockIndex(session);
    rawBlocks = selectedIds
      .map((blockId) => blockIndex.get(blockId))
      .filter(Boolean)
      .map((block) => ({
        block_id: block.blockId || block.block_id || block.id || null,
        block_version: pickFirstDefined(block.block_version, block.blockVersion, block.full_payload?.block_meta?.block_version, 1),
        source_kind: block.source_kind || block.sourceKind || block.kind || "system_policy",
        scope: block.scope || (block.ephemeral ? "request" : "session"),
        editable: !!block.editable,
        selected: true,
        pinned: !!block.pinned,
      }));
  }
  return rawBlocks
    .filter(isPlainObject)
    .map((item, index) => ({
      order: index + 1,
      blockId: normalizeId(item.block_id || item.blockId || item.id),
      blockVersion: toPositiveInt(item.block_version || item.blockVersion, 1),
      sourceKind: normalizeString(item.source_kind || item.sourceKind || item.kind, "system_policy"),
      scope: normalizeString(item.scope, "request"),
      editable: !!item.editable,
      selected: !!item.selected,
      pinned: !!item.pinned,
    }))
    .filter((item) => item.blockId);
}

function formatSourceKindLabel(sourceKind, fallbackKind = "") {
  const normalized = normalizeString(sourceKind || fallbackKind, "system_policy").toLowerCase();
  return {
    system_policy: "系统策略",
    memory_summary: "记忆摘要",
    recent_messages: "最近消息",
    session_chat: "会话上下文",
    replay_analysis: "回放分析",
    window_snapshot: "窗口快照",
    nearby_event_summary: "事件摘要",
    manual_region: "手动选区",
    selected_bar: "选中K线",
  }[normalized] || normalized;
}

function formatScopeLabel(scope, pinned = false) {
  const normalized = normalizeString(scope, pinned ? "session" : "request").toLowerCase();
  if (pinned) {
    return "固定";
  }
  if (normalized === "session") {
    return "会话";
  }
  if (normalized === "global") {
    return "全局";
  }
  return "临时";
}

function deriveGovernanceClass(record, replySessionDate) {
  const sourceKind = normalizeString(record?.sourceKind || record?.source_kind, "").toLowerCase();
  const title = normalizeString(record?.title, "").toLowerCase();
  const preview = normalizeString(record?.previewText || record?.preview_text, "").toLowerCase();
  const payloadSummary = isPlainObject(record?.payloadSummary) ? record.payloadSummary : {};
  const blockDate = normalizeString(
    payloadSummary.session_date
    || payloadSummary.sessionDate
    || payloadSummary.trade_date
    || payloadSummary.trading_date,
    "",
  );
  if (
    sourceKind.includes("cross_day")
    || title.includes("跨日")
    || preview.includes("跨日")
    || (blockDate && replySessionDate && blockDate !== replySessionDate)
  ) {
    return "跨日锚点";
  }
  if (
    record?.editable
    || record?.pinned
    || sourceKind.startsWith("user_")
    || sourceKind.includes("manual")
  ) {
    return "用户固定";
  }
  if (
    sourceKind === "window_snapshot"
    || sourceKind === "selected_bar"
    || sourceKind === "manual_region"
    || normalizeString(record?.scope, "").toLowerCase() === "request"
  ) {
    return "临时窗口生成";
  }
  return "系统自动挂载";
}

function buildBlockRecords({
  session,
  activeUi,
  trace,
  replySessionDate,
}) {
  const contextRefs = normalizeContextRefs({ activeUi, trace, session });
  const refIndex = new Map(contextRefs.map((item) => [item.blockId, item]));
  const currentBlockIndex = getCurrentPromptBlockIndex(session);
  const traceBlocks = Array.isArray(trace?.prompt_block_summaries) ? trace.prompt_block_summaries : [];
  const sourceBlocks = traceBlocks.length
    ? traceBlocks.map((block, index) => ({ ...block, __order: index + 1 }))
    : contextRefs.map((ref, index) => {
      const current = currentBlockIndex.get(ref.blockId);
      return {
        block_id: ref.blockId,
        title: current?.title || ref.blockId || "上下文块",
        preview_text: current?.previewText || current?.preview_text || "",
        payload_summary: isPlainObject(current?.payload_summary)
          ? current.payload_summary
          : (isPlainObject(current?.full_payload) ? current.full_payload : {}),
        kind: current?.kind || "context",
        source_kind: ref.sourceKind,
        scope: ref.scope,
        editable: ref.editable,
        selected: ref.selected,
        pinned: ref.pinned,
        block_version: ref.blockVersion,
        __order: index + 1,
      };
    });
  return sourceBlocks.map((block, index) => {
    const blockId = normalizeId(block.block_id || block.blockId || block.id);
    const ref = refIndex.get(blockId);
    const current = currentBlockIndex.get(blockId);
    const usedVersion = toPositiveInt(
      pickFirstDefined(block.block_version, block.blockVersion, ref?.blockVersion, current?.block_version, current?.blockVersion),
      1,
    );
    const latestVersionRaw = pickFirstDefined(
      current?.block_version,
      current?.blockVersion,
      current?.full_payload?.block_meta?.block_version,
      null,
    );
    const latestVersion = latestVersionRaw === null || latestVersionRaw === undefined ? null : toPositiveInt(latestVersionRaw, usedVersion);
    const pinned = !!pickFirstDefined(block.pinned, ref?.pinned, current?.pinned, false);
    const scope = normalizeString(pickFirstDefined(block.scope, ref?.scope, current?.scope, current?.ephemeral ? "request" : "session"), pinned ? "session" : "request");
    const editable = !!pickFirstDefined(block.editable, ref?.editable, current?.editable, false);
    const sourceKind = normalizeString(pickFirstDefined(block.source_kind, block.sourceKind, ref?.sourceKind, current?.source_kind, current?.sourceKind, block.kind), "system_policy");
    const record = {
      order: Number.isFinite(block.__order) ? block.__order : (ref?.order || index + 1),
      blockId,
      title: normalizeString(block.title, current?.title || blockId || "上下文块"),
      previewText: normalizeString(block.preview_text, current?.previewText || current?.preview_text || ""),
      payloadSummary: isPlainObject(block.payload_summary) ? block.payload_summary : {},
      kind: normalizeString(block.kind, current?.kind || "context"),
      sourceKind,
      scope,
      editable,
      selected: !!pickFirstDefined(block.selected, ref?.selected, true),
      pinned,
      blockVersion: usedVersion,
      latestVersion,
    };
    return {
      ...record,
      sourceLabel: formatSourceKindLabel(sourceKind, record.kind),
      governanceClass: deriveGovernanceClass(record, replySessionDate),
      scopeLabel: formatScopeLabel(scope, pinned),
      editableLabel: formatBooleanLabel(editable, "可编辑", "只读"),
      versionStatus: latestVersion && latestVersion !== usedVersion
        ? `当前最新 v${latestVersion}`
        : "当前仍是最新",
      hasVersionDrift: !!latestVersion && latestVersion !== usedVersion,
    };
  });
}

function buildTraceStatusMarkup({ loadingTrace, traceUnavailable, promptTraceId }) {
  if (loadingTrace) {
    return `<div class="attention-first-note context-recipe-status-note">正在对齐 Prompt Trace，补齐本轮回复的精确 block 版本与来源。</div>`;
  }
  if (traceUnavailable && promptTraceId) {
    return `<div class="attention-first-note context-recipe-status-note">Prompt Trace 当前不可用，先展示兼容摘要；旧 reply 的版本漂移信息可能不完整。</div>`;
  }
  return "";
}

function buildContextRecipeShellMarkup() {
  return `
    <div class="context-recipe-shell">
      <div data-context-recipe-region="head"></div>
      <div data-context-recipe-region="hero"></div>
      <div data-context-recipe-region="stats"></div>
      <div data-context-recipe-region="summary"></div>
      <div data-context-recipe-region="trace-status"></div>
      <div data-context-recipe-region="body"></div>
    </div>
  `;
}

export function createWorkbenchContextRecipeController({
  state,
  els,
  persistSessions = null,
  requestRender = null,
  getPromptTrace = null,
  ensurePromptTrace = null,
  onPromptTraceRequested = null,
  getWorkbenchUiMeta = (meta) => meta?.workbench_ui || meta?.workbenchUi || null,
  buildReplyWindowLabel = () => "未记录",
  buildAssistantReplyLabel = () => "AI 回复",
  buildReplySummaryText = (message) => summarizeText(message?.content || "", 120),
  getReplyObjectCount = () => 0,
} = {}) {
  const pendingTraceFetchKeys = new Set();
  const unavailableTraceKeys = new Set();
  let bindingsInstalled = false;
  let currentRenderState = {
    session: null,
    promptTraceId: null,
    messageId: null,
  };

  function ensureShell() {
    if (!els?.contextRecipePanel) {
      return null;
    }
    updateRegionMarkup(
      els.contextRecipePanel,
      buildContextRecipeShellMarkup(),
      "context-recipe-shell:v1",
    );
    return els.contextRecipePanel.querySelector(".context-recipe-shell");
  }

  function installBindings() {
    if (bindingsInstalled || !els?.contextRecipePanel) {
      return;
    }
    bindingsInstalled = true;
    els.contextRecipePanel.addEventListener("click", (event) => {
      const session = currentRenderState.session;
      const toggleButton = event.target?.closest?.("[data-context-recipe-toggle]");
      if (toggleButton) {
        if (!session) {
          return;
        }
        session.contextRecipeExpanded = !session.contextRecipeExpanded;
        persistSessions?.();
        requestRender?.();
        return;
      }
      const densityButton = event.target?.closest?.("[data-answer-density]");
      if (densityButton) {
        if (!session) {
          return;
        }
        const nextDensity = normalizeString(densityButton.dataset.answerDensity).toLowerCase();
        if (!["full", "compact", "skim"].includes(nextDensity) || session.answerCardDensity === nextDensity) {
          return;
        }
        session.answerCardDensity = nextDensity;
        persistSessions?.();
        requestRender?.();
        return;
      }
      const traceButton = event.target?.closest?.("[data-context-recipe-open-trace]");
      if (traceButton) {
        onPromptTraceRequested?.({
          promptTraceId: currentRenderState.promptTraceId,
          messageId: currentRenderState.messageId,
        });
      }
    });
  }

  function hide() {
    if (!els?.contextRecipePanel) {
      return;
    }
    currentRenderState = {
      session: null,
      promptTraceId: null,
      messageId: null,
    };
    els.contextRecipePanel.hidden = true;
    els.contextRecipePanel.setAttribute("aria-hidden", "true");
  }

  function requestTrace(activeMessage) {
    if (typeof ensurePromptTrace !== "function") {
      return;
    }
    const { promptTraceId, messageId } = resolvePromptTraceRef(activeMessage);
    const traceKey = promptTraceId || messageId;
    if (!traceKey || pendingTraceFetchKeys.has(traceKey) || unavailableTraceKeys.has(traceKey)) {
      return;
    }
    const cached = typeof getPromptTrace === "function" ? getPromptTrace({ promptTraceId, messageId }) : null;
    if (cached) {
      return;
    }
    pendingTraceFetchKeys.add(traceKey);
    Promise.resolve(ensurePromptTrace({ promptTraceId, messageId }))
      .then((trace) => {
        if (trace) {
          unavailableTraceKeys.delete(traceKey);
        } else {
          unavailableTraceKeys.add(traceKey);
        }
      })
      .catch(() => {
        unavailableTraceKeys.add(traceKey);
      })
      .finally(() => {
        pendingTraceFetchKeys.delete(traceKey);
        requestRender?.();
      });
  }

  function render({ session, activeMessage, activeUi = null } = {}) {
    if (!els?.contextRecipePanel || !session || !activeMessage) {
      hide();
      return;
    }
    installBindings();
    const shell = ensureShell();
    if (!shell) {
      return;
    }
    const { promptTraceId, messageId } = resolvePromptTraceRef(activeMessage);
    currentRenderState = {
      session,
      promptTraceId,
      messageId,
    };
    const trace = typeof getPromptTrace === "function" ? getPromptTrace({ promptTraceId, messageId }) : null;
    const traceKey = promptTraceId || messageId || "";
    const loadingTrace = !!traceKey && pendingTraceFetchKeys.has(traceKey);
    const traceUnavailable = !!traceKey && unavailableTraceKeys.has(traceKey) && !trace;
    const workbenchUi = isPlainObject(activeUi) ? activeUi : (getWorkbenchUiMeta(activeMessage.meta) || {});
    const density = ["full", "compact", "skim"].includes(normalizeString(session.answerCardDensity).toLowerCase())
      ? normalizeString(session.answerCardDensity).toLowerCase()
      : "compact";
    const showPreview = density !== "skim";
    const replyWindowLabel = resolveReplyWindowLabel({
      workbenchUi,
      trace,
      session,
      buildReplyWindowLabel,
    });
    const replySessionDate = normalizeString(
      pickFirstDefined(
        workbenchUi?.reply_session_date,
        workbenchUi?.replySessionDate,
        trace?.reply_session_date,
        trace?.snapshot?.reply_session_date,
        trace?.metadata?.reply_session_date,
      ),
      "未记录",
    );
    const contextVersion = normalizeString(
      pickFirstDefined(
        workbenchUi?.context_version,
        workbenchUi?.contextVersion,
        trace?.context_version,
        trace?.snapshot?.context_version,
        trace?.metadata?.context_version,
        session.lastContextVersion,
      ),
      "未记录",
    );
    const modelName = normalizeString(
      pickFirstDefined(
        workbenchUi?.model_name,
        workbenchUi?.modelName,
        activeMessage.model,
        trace?.model_name,
        session.activeModel,
        session.memory?.active_model,
      ),
      "未记录",
    );
    const includeMemorySummary = !!pickFirstDefined(
      workbenchUi?.include_memory_summary,
      workbenchUi?.includeMemorySummary,
      trace?.metadata?.include_memory_summary,
      session.includeMemorySummary,
      false,
    );
    const includeRecentMessages = !!pickFirstDefined(
      workbenchUi?.include_recent_messages,
      workbenchUi?.includeRecentMessages,
      trace?.metadata?.include_recent_messages,
      session.includeRecentMessages,
      false,
    );
    const blockRecords = buildBlockRecords({
      session,
      activeUi: workbenchUi,
      trace,
      replySessionDate,
    });
    const selectedBlockCount = Number.isFinite(Number(workbenchUi?.selected_block_count))
      ? Number(workbenchUi.selected_block_count)
      : (blockRecords.filter((item) => item.selected).length || blockRecords.length);
    const pinnedBlockCount = Number.isFinite(Number(workbenchUi?.pinned_block_count))
      ? Number(workbenchUi.pinned_block_count)
      : blockRecords.filter((item) => item.pinned).length;
    const objectCount = getReplyObjectCount(activeMessage);
    const activeReplyLabel = buildAssistantReplyLabel(activeMessage);
    const previewLimit = density === "full" ? 200 : 118;
    const staleBlockCount = blockRecords.filter((item) => item.hasVersionDrift).length;
    const summaryLead = [
      `${selectedBlockCount} 个 prompt block`,
      `${pinnedBlockCount} 个固定`,
      includeMemorySummary ? "含记忆摘要" : "无记忆摘要",
      includeRecentMessages ? "含最近消息" : "无最近消息",
    ].join(" · ");
    const blockMarkup = blockRecords.length
      ? blockRecords.map((block) => `
          <article class="context-recipe-block ${block.pinned ? "is-pinned" : ""} ${block.hasVersionDrift ? "has-version-drift" : ""}" data-context-recipe-block-id="${escapeHtml(block.blockId)}">
            <div class="context-recipe-block-head">
              <div>
                <strong>${escapeHtml(`${block.order}. ${block.title}`)}</strong>
                <div class="context-recipe-block-meta">
                  ${escapeHtml(`${block.governanceClass} · ${block.sourceLabel} · ${block.scopeLabel} · ${block.editableLabel}`)}
                </div>
              </div>
              <div class="context-recipe-block-chips">
                <span class="mini-chip">${escapeHtml(`v${block.blockVersion}`)}</span>
                <span class="mini-chip">${escapeHtml(block.blockId)}</span>
                ${block.selected ? `<span class="mini-chip">已选</span>` : ""}
                ${block.pinned ? `<span class="mini-chip emphasis">Pinned</span>` : `<span class="mini-chip">Ephemeral</span>`}
                ${block.hasVersionDrift ? `<span class="mini-chip warning">${escapeHtml(block.versionStatus)}</span>` : ""}
              </div>
            </div>
            ${showPreview && block.previewText ? `<div class="meta">${escapeHtml(summarizeText(block.previewText, previewLimit))}</div>` : ""}
            <div class="context-recipe-block-foot">
              <span>${escapeHtml(`source_kind=${block.sourceKind}`)}</span>
              <span>${escapeHtml(block.versionStatus)}</span>
            </div>
          </article>
        `).join("")
      : `<div class="attention-first-note">当前没有额外 prompt block，本轮上下文主要来自当前窗口、会话记忆与最近消息兼容摘要。</div>`;

    els.contextRecipePanel.hidden = false;
    els.contextRecipePanel.setAttribute("aria-hidden", "false");
    const headRegion = shell.querySelector('[data-context-recipe-region="head"]');
    const heroRegion = shell.querySelector('[data-context-recipe-region="hero"]');
    const statsRegion = shell.querySelector('[data-context-recipe-region="stats"]');
    const summaryRegion = shell.querySelector('[data-context-recipe-region="summary"]');
    const traceStatusRegion = shell.querySelector('[data-context-recipe-region="trace-status"]');
    const bodyRegion = shell.querySelector('[data-context-recipe-region="body"]');

    updateRegionMarkup(headRegion, `
      <div class="strip-head attention-first-panel-head">
        <span class="strip-title">当前回答上下文</span>
        <div class="attention-first-panel-actions">
          <button type="button" class="secondary tiny ${density === "skim" ? "is-active" : ""}" data-answer-density="skim">略读</button>
          <button type="button" class="secondary tiny ${density === "compact" ? "is-active" : ""}" data-answer-density="compact">紧凑</button>
          <button type="button" class="secondary tiny ${density === "full" ? "is-active" : ""}" data-answer-density="full">展开</button>
          ${promptTraceId || messageId ? '<button type="button" class="secondary tiny" data-context-recipe-open-trace="true">查看 Trace</button>' : ""}
          <button type="button" class="secondary tiny" data-context-recipe-toggle="true">${session.contextRecipeExpanded ? "收起配方" : "展开配方"}</button>
        </div>
      </div>
    `, JSON.stringify({
      density,
      expanded: !!session.contextRecipeExpanded,
      traceAvailable: !!(promptTraceId || messageId),
    }), {
      preserveState: true,
      stateOptions: {
        anchorSelector: "[data-answer-density], [data-context-recipe-open-trace], [data-context-recipe-toggle]",
      },
    });

    updateRegionMarkup(heroRegion, `
      <div class="answer-workspace-hero">
        <strong>${escapeHtml(activeReplyLabel)}</strong>
        <div class="meta">${escapeHtml(`${replyWindowLabel} · Context ${contextVersion} · ${modelName}`)}</div>
        <p>${escapeHtml(`${buildReplySummaryText(activeMessage, density === "full" ? 200 : 120)}${summaryLead ? ` · ${summaryLead}` : ""}`)}</p>
      </div>
    `, JSON.stringify({
      activeReplyLabel,
      replyWindowLabel,
      contextVersion,
      modelName,
      density,
      summaryLead,
      summary: buildReplySummaryText(activeMessage, density === "full" ? 200 : 120),
    }));

    updateRegionMarkup(statsRegion, `
      <div class="answer-workspace-grid">
        <article class="answer-workspace-stat">
          <span>当前窗口范围</span>
          <strong>${escapeHtml(replyWindowLabel)}</strong>
        </article>
        <article class="answer-workspace-stat">
          <span>Context 版本</span>
          <strong>${escapeHtml(contextVersion)}</strong>
        </article>
        <article class="answer-workspace-stat">
          <span>当前模型</span>
          <strong>${escapeHtml(modelName)}</strong>
        </article>
        <article class="answer-workspace-stat">
          <span>已选 Blocks</span>
          <strong>${escapeHtml(`${selectedBlockCount} 个`)}</strong>
        </article>
        <article class="answer-workspace-stat">
          <span>Pinned Blocks</span>
          <strong>${escapeHtml(`${pinnedBlockCount} 个`)}</strong>
        </article>
        <article class="answer-workspace-stat">
          <span>会话增强</span>
          <strong>${escapeHtml(`记忆 ${includeMemorySummary ? "开" : "关"} / 最近消息 ${includeRecentMessages ? "开" : "关"}`)}</strong>
        </article>
      </div>
    `, JSON.stringify({
      replyWindowLabel,
      contextVersion,
      modelName,
      selectedBlockCount,
      pinnedBlockCount,
      includeMemorySummary,
      includeRecentMessages,
    }));

    updateRegionMarkup(summaryRegion, `
      <div class="context-recipe-summary-strip">
        <span class="mini-chip">${escapeHtml(`对象 ${objectCount}`)}</span>
        <span class="mini-chip">${escapeHtml(replySessionDate)}</span>
        ${staleBlockCount > 0 ? `<span class="mini-chip warning">${escapeHtml(`${staleBlockCount} 个 block 已有更新`)}</span>` : ""}
      </div>
    `, JSON.stringify({
      objectCount,
      replySessionDate,
      staleBlockCount,
    }));

    updateRegionMarkup(
      traceStatusRegion,
      buildTraceStatusMarkup({ loadingTrace, traceUnavailable, promptTraceId }),
      JSON.stringify({
        loadingTrace,
        traceUnavailable,
        promptTraceId: promptTraceId || "",
      }),
    );

    updateRegionMarkup(bodyRegion, session.contextRecipeExpanded ? `
      <div class="context-recipe-body">
        <div class="context-recipe-section-head">
          <strong>本次发送配方</strong>
          <span class="meta">${escapeHtml("按本轮实际引用顺序展示来源、scope、editable、pinned 与 block version。")}</span>
        </div>
        <div class="context-recipe-block-list">
          ${blockMarkup}
        </div>
      </div>
    ` : "", JSON.stringify({
      expanded: !!session.contextRecipeExpanded,
      density,
      blockCount: blockRecords.length,
      staleBlockCount,
      blocks: blockRecords.map((block) => ({
        id: block.blockId,
        version: block.blockVersion,
        latestVersion: block.latestVersion,
        pinned: block.pinned,
        selected: block.selected,
        scope: block.scope,
        editable: block.editable,
      })),
    }), {
      preserveState: !!session.contextRecipeExpanded,
      stateOptions: {
        anchorSelector: "[data-context-recipe-block-id], .attention-first-note",
      },
    });

    if ((promptTraceId || messageId) && !trace) {
      requestTrace(activeMessage);
    }
  }

  return {
    hide,
    render,
  };
}
