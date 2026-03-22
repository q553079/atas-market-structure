import { createMessageId, createPlanId, escapeHtml, formatPrice, summarizeText, writeStorage } from "./replay_workbench_ui_utils.js";
import {
  applyAnnotationPreferences,
  isAnnotationDeleted,
  normalizeWorkbenchPlanCard,
} from "./replay_workbench_annotation_utils.js";

function isImageAttachment(attachment) {
  const kind = String(attachment?.kind || "").toLowerCase();
  const name = String(attachment?.name || "").toLowerCase();
  return kind.startsWith("image/") || kind.includes("screenshot") || /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name);
}

function normalizeAttachmentItem(attachment, fallback = {}) {
  if (!attachment || typeof attachment !== "object") {
    return null;
  }
  const name = typeof attachment.name === "string" && attachment.name.trim()
    ? attachment.name.trim()
    : (typeof fallback.name === "string" ? fallback.name : "");
  const mediaType = String(
    attachment.media_type
    || attachment.mediaType
    || attachment.kind
    || fallback.media_type
    || fallback.mediaType
    || fallback.kind
    || "application/octet-stream"
  );
  const previewUrl = typeof attachment.preview_url === "string" && attachment.preview_url
    ? attachment.preview_url
    : (typeof attachment.previewUrl === "string" && attachment.previewUrl
      ? attachment.previewUrl
      : (typeof attachment.data_url === "string" && attachment.data_url
        ? attachment.data_url
        : (typeof attachment.dataUrl === "string" ? attachment.dataUrl : "")));
  const dataUrl = typeof attachment.data_url === "string" && attachment.data_url
    ? attachment.data_url
    : (typeof attachment.dataUrl === "string" && attachment.dataUrl
      ? attachment.dataUrl
      : previewUrl);
  const sizeValue = Number(attachment.size ?? attachment.byte_size ?? attachment.bytes ?? fallback.size ?? 0);
  return {
    ...attachment,
    name,
    kind: String(attachment.kind || mediaType || "file"),
    media_type: mediaType,
    preview_url: previewUrl,
    data_url: dataUrl,
    size: Number.isFinite(sizeValue) && sizeValue > 0 ? sizeValue : 0,
  };
}

function normalizeAttachmentList(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => normalizeAttachmentItem(item, { name: `附件${index + 1}` }))
    .filter(Boolean);
}

function buildAttachmentPreviewMarkup(attachment) {
  const label = escapeHtml(attachment.name || "附件");
  const previewUrl = attachment?.preview_url || attachment?.data_url || "";
  if (previewUrl && isImageAttachment(attachment)) {
    return `
      <div class="attachment-thumb">
        <img src="${escapeHtml(previewUrl)}" alt="${label}">
      </div>
    `;
  }
  return `<div class="attachment-thumb attachment-thumb-fallback">${escapeHtml((attachment.kind || attachment.media_type || "file").slice(0, 10))}</div>`;
}

function sanitizeAttachmentForStorage(attachment) {
  if (!attachment || typeof attachment !== "object") {
    return attachment;
  }
  const next = { ...attachment };
  if (typeof next.data_url === "string" && next.data_url.startsWith("data:")) {
    delete next.data_url;
  }
  if (typeof next.preview_url === "string" && next.preview_url.startsWith("data:")) {
    delete next.preview_url;
  }
  return next;
}

function buildServerAttachmentPayloads(items = []) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      name: item?.name || null,
      media_type: item?.media_type || item?.kind || "application/octet-stream",
      data_url: item?.data_url || item?.preview_url || "",
    }))
    .filter((item) => typeof item.data_url === "string" && item.data_url.startsWith("data:"));
}

function formatAttachmentSize(size) {
  const bytes = Number(size || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = value >= 100 || unitIndex === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1")} ${units[unitIndex]}`;
}

function buildAttachmentSummary(items = []) {
  const attachments = Array.isArray(items) ? items : [];
  if (!attachments.length) {
    return "暂无附件";
  }
  const imageCount = attachments.filter((item) => isImageAttachment(item)).length;
  const totalSize = attachments.reduce((sum, item) => sum + Number(item?.size || 0), 0);
  const parts = [`${attachments.length} 个附件`];
  if (imageCount) {
    parts.push(`${imageCount} 张图片`);
  }
  const sizeLabel = formatAttachmentSize(totalSize);
  if (sizeLabel) {
    parts.push(sizeLabel);
  }
  return parts.join(" · ");
}

function buildAttachmentCollapsedSummaryMarkup(items = []) {
  const attachments = Array.isArray(items) ? items : [];
  const chips = attachments.slice(0, 3).map((item, index) => {
    const name = escapeHtml(item?.name || `附件${index + 1}`);
    return `<span class="attachment-mini-chip" title="${name}">${name}</span>`;
  });
  const remaining = attachments.length - chips.length;
  if (remaining > 0) {
    chips.push(`<span class="attachment-mini-chip meta">+${remaining}</span>`);
  }
  return `
    <div class="attachment-mini-chip-row">${chips.join("")}</div>
    <div class="meta">${escapeHtml(buildAttachmentSummary(attachments))}</div>
  `;
}

function clonePlainData(value, fallback = null) {
  if (value == null) {
    return fallback;
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return fallback;
  }
}

function buildLongTextMarkup(text, { limit = 220, expanded = false, messageId = "" } = {}) {
  const raw = String(text || "").replace(/\r\n/g, "\n");
  const safe = escapeHtml(raw);
  if (!raw || raw.length <= limit) {
    return `<p>${safe}</p>`;
  }
  const preview = escapeHtml(raw.slice(0, limit));
  const normalizedMessageId = escapeHtml(String(messageId || ""));
  return `
    <div class="longtext-block ${expanded ? "is-expanded" : ""}" data-longtext data-longtext-message-id="${normalizedMessageId}">
      <p class="longtext-preview"${expanded ? " hidden" : ""}>${preview}…</p>
      <p class="longtext-full"${expanded ? "" : " hidden"}>${safe}</p>
      <button
        type="button"
        class="secondary tiny longtext-toggle"
        data-longtext-toggle="${expanded ? "collapse" : "expand"}"
        data-longtext-message-id="${normalizedMessageId}"
        aria-expanded="${expanded ? "true" : "false"}"
      >${expanded ? "收起" : "展开全文"}</button>
    </div>
  `;
}

function mapServerPlanCard(planCard, sessionId = null, messageId = null) {
  return normalizeWorkbenchPlanCard(planCard, {
    sessionId: sessionId || planCard.session_id || null,
    messageId: messageId || planCard.message_id || null,
  });
}

function mapServerMessage(message, planCardsByMessage = new Map()) {
  const messageId = message.message_id || message.id || createMessageId();
  const attachments = normalizeAttachmentList(message.attachments);
  return {
    message_id: messageId,
    sessionId: message.session_id || message.sessionId || null,
    role: message.role,
    content: message.content || "",
    status: message.status || (message.role === "assistant" ? "completed" : "sent"),
    replyTitle: message.reply_title || message.replyTitle || null,
    model: message.model || null,
    annotations: Array.isArray(message.annotations) ? message.annotations : [],
    planCards: planCardsByMessage.get(messageId) || [],
    mountedToChart: !!message.mounted_to_chart,
    mountedObjectIds: Array.isArray(message.mounted_object_ids) ? message.mounted_object_ids : [],
    meta: {
      model: message.model || null,
      replyTitle: message.reply_title || message.replyTitle || null,
      attachments,
      planCards: planCardsByMessage.get(messageId) || [],
    },
    created_at: message.created_at || new Date().toISOString(),
    updated_at: message.updated_at || message.created_at || new Date().toISOString(),
  };
}

function mapServerSessionToThread(serverSession, fallback = {}) {
  const sessionId = serverSession.session_id || serverSession.id || fallback.id;
  const symbol = serverSession.symbol || fallback.symbol || "NQ";
  const timeframe = serverSession.timeframe || fallback.timeframe || "1m";
  const windowRange = serverSession.window_range?.label || fallback.windowRange || fallback.memory?.window_range || "最近7天";
  const workspaceRole = fallback.workspaceRole || serverSession.workspace_role || serverSession.workspaceRole || "analyst";
  return normalizeSessionShape({
    ...fallback,
    id: sessionId,
    sessionId,
    workspaceRole,
    title: serverSession.title || fallback.title || sessionId,
    pinned: !!serverSession.pinned,
    symbol,
    contractId: serverSession.contract_id || fallback.contractId || symbol,
    timeframe,
    windowRange,
    status: serverSession.status || fallback.status || "active",
    unreadCount: Number.isFinite(serverSession.unread_count) ? serverSession.unread_count : 0,
    selectedPromptBlockIds: Array.isArray(serverSession.selected_prompt_block_ids) ? serverSession.selected_prompt_block_ids : (fallback.selectedPromptBlockIds || []),
    pinnedContextBlockIds: Array.isArray(serverSession.pinned_context_block_ids) ? serverSession.pinned_context_block_ids : (fallback.pinnedContextBlockIds || []),
    includeMemorySummary: typeof serverSession.include_memory_summary === "boolean"
      ? serverSession.include_memory_summary
      : !!fallback.includeMemorySummary,
    includeRecentMessages: typeof serverSession.include_recent_messages === "boolean"
      ? serverSession.include_recent_messages
      : !!fallback.includeRecentMessages,
    mountedReplyIds: Array.isArray(serverSession.mounted_reply_ids) ? serverSession.mounted_reply_ids : (fallback.mountedReplyIds || []),
    activePlanId: serverSession.active_plan_id || fallback.activePlanId || null,
    scrollOffset: Number.isFinite(serverSession.scroll_offset) ? serverSession.scroll_offset : (fallback.scrollOffset || 0),
    draftText: serverSession.draft_text ?? fallback.draftText ?? fallback.draft ?? "",
    draft: serverSession.draft_text ?? fallback.draft ?? fallback.draftText ?? "",
    draftAttachments: normalizeAttachmentList(Array.isArray(serverSession.draft_attachments) ? serverSession.draft_attachments : (fallback.draftAttachments || [])),
    attachments: normalizeAttachmentList(Array.isArray(fallback.attachments) ? fallback.attachments : []),
    activeModel: serverSession.active_model || fallback.activeModel || "",
    createdAt: serverSession.created_at || fallback.createdAt || fallback.memory?.last_updated_at || new Date().toISOString(),
    updatedAt: serverSession.updated_at || fallback.updatedAt || fallback.memory?.last_updated_at || serverSession.created_at || new Date().toISOString(),
    memory: {
      ...(fallback.memory || {}),
      session_id: sessionId,
      active_model: serverSession.active_model || fallback.memory?.active_model || fallback.activeModel || "",
      symbol,
      timeframe,
      window_range: windowRange,
    },
    backendLoaded: !!fallback.backendLoaded,
  }, fallback);
}

function normalizeMessageShape(message) {
  if (!message || typeof message !== "object") {
    return message;
  }
  const meta = message.meta && typeof message.meta === "object" ? message.meta : {};
  return {
    ...message,
    meta: {
      ...meta,
      attachments: normalizeAttachmentList(
        Array.isArray(meta.attachments) ? meta.attachments : (Array.isArray(message.attachments) ? message.attachments : [])
      ),
    },
  };
}

function normalizeRecapItem(item, session = {}, index = 0) {
  if (!item || typeof item !== "object") {
    return null;
  }
  const targetLabels = Array.isArray(item.targetLabels)
    ? item.targetLabels.map((label) => String(label || "").trim()).filter(Boolean)
    : [];
  const structuredSummary = String(item.structuredSummary || item.summary || item.notes || "").trim();
  return {
    ...item,
    id: item.id || `${session?.sessionId || session?.id || "session"}-recap-${index + 1}`,
    title: item.title || "AI计划卡",
    planId: item.planId || item.plan_id || null,
    plan_id: item.plan_id || item.planId || null,
    messageId: item.messageId || item.message_id || null,
    message_id: item.message_id || item.messageId || null,
    sessionId: item.sessionId || item.session_id || session?.sessionId || session?.id || null,
    session_id: item.session_id || item.sessionId || session?.sessionId || session?.id || null,
    side: item.side || "",
    status: item.status || "",
    entryLabel: item.entryLabel || "",
    stopLabel: item.stopLabel || "",
    targetLabels,
    summary: item.summary || item.notes || "",
    notes: item.notes || item.summary || "",
    structuredSummary,
    sourceModel: item.sourceModel || item.model || "",
    addedAt: item.addedAt || item.created_at || item.updated_at || new Date().toISOString(),
  };
}

function normalizeSessionShape(session, fallback = {}) {
  if (!session) return session;
  const symbol = session.symbol || session.memory?.symbol || fallback.symbol || "NQ";
  const timeframe = session.timeframe || session.memory?.timeframe || fallback.timeframe || "1m";
  const windowRange = session.windowRange || session.memory?.window_range || fallback.windowRange || "最近7天";
  const workspaceRole = session.workspaceRole || fallback.workspaceRole || "analyst";
  session.sessionId = session.sessionId || session.id;
  session.workspaceRole = workspaceRole;
  session.symbol = symbol;
  session.contractId = session.contractId || symbol;
  session.timeframe = timeframe;
  session.windowRange = windowRange;
  session.status = session.status || fallback.status || "active";
  session.unreadCount = Number.isFinite(session.unreadCount) ? session.unreadCount : 0;
  session.selectedPromptBlockIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
  session.pinnedContextBlockIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
  session.promptBlocks = Array.isArray(session.promptBlocks) ? session.promptBlocks : [];
  session.promptBlockPreviewCache = session.promptBlockPreviewCache && typeof session.promptBlockPreviewCache === "object"
    ? session.promptBlockPreviewCache
    : {};
  session.includeMemorySummary = !!session.includeMemorySummary;
  session.includeRecentMessages = !!session.includeRecentMessages;
  session.mountedReplyIds = Array.isArray(session.mountedReplyIds) ? session.mountedReplyIds : [];
  session.activePlanId = session.activePlanId || null;
  session.recapItems = Array.isArray(session.recapItems)
    ? session.recapItems.map((item, index) => normalizeRecapItem(item, session, index)).filter(Boolean)
    : [];
  session.scrollOffset = Number.isFinite(session.scrollOffset) ? session.scrollOffset : 0;
  session.autoFollowChat = session.autoFollowChat ?? true;
  session.hasUnreadChatBelow = session.hasUnreadChatBelow ?? false;
  session.messages = Array.isArray(session.messages) ? session.messages.map((message) => normalizeMessageShape(message)).filter(Boolean) : [];
  session.turns = Array.isArray(session.turns) ? session.turns : [];
  session.draftText = session.draftText ?? session.draft ?? "";
  session.draft = session.draftText;
  session.draftAttachments = normalizeAttachmentList(
    Array.isArray(session.draftAttachments) ? session.draftAttachments : (Array.isArray(session.attachments) ? session.attachments : [])
  );
  session.attachments = normalizeAttachmentList(Array.isArray(session.attachments) ? session.attachments : [...session.draftAttachments]);
  session.attachmentPreviewCollapsed = !!session.attachmentPreviewCollapsed;
  session.expandedLongTextMessageIds = Array.isArray(session.expandedLongTextMessageIds)
    ? Array.from(new Set(session.expandedLongTextMessageIds.map((item) => String(item || "").trim()).filter(Boolean)))
    : [];
  session.analysisTemplate = session.analysisTemplate && typeof session.analysisTemplate === "object"
    ? {
        type: session.analysisTemplate.type || "recent_20_bars",
        range: session.analysisTemplate.range || "current_window",
        style: session.analysisTemplate.style || "standard",
        sendMode: session.analysisTemplate.sendMode || "current",
      }
    : {
        type: "recent_20_bars",
        range: "current_window",
        style: "standard",
        sendMode: "current",
      };
  session.handoffMode = session.handoffMode || "summary_only";
  session.handoffSummary = session.handoffSummary || "";
  session.handoffPreviewSummary = session.handoffPreviewSummary || session.handoffSummary || "";
  session.handoffPreviewPacket = session.handoffPreviewPacket || null;
  session.handoffPreviewAt = session.handoffPreviewAt || null;
  session.handoffPreviewTargetModel = session.handoffPreviewTargetModel || "";
  session.handoffPreviewMode = session.handoffPreviewMode || session.handoffMode;
  session.lastHandoffSummary = session.lastHandoffSummary || "";
  session.lastHandoffPacket = session.lastHandoffPacket || null;
  session.lastHandoffAt = session.lastHandoffAt || null;
  session.lastHandoffTargetModel = session.lastHandoffTargetModel || "";
  session.lastHandoffMode = session.lastHandoffMode || session.handoffMode;
  session.backendLoaded = !!session.backendLoaded;
  session.loadingFromServer = !!session.loadingFromServer;
  session.createdAt = session.createdAt || fallback.createdAt || session.memory?.last_updated_at || new Date().toISOString();
  session.updatedAt = session.updatedAt || fallback.updatedAt || session.memory?.last_updated_at || session.createdAt;
  session.memory = {
    ...(session.memory || {}),
    session_id: session.memory?.session_id || session.sessionId,
    symbol,
    timeframe,
    window_range: windowRange,
  };
  return session;
}

function getDraftAttachments(session) {
  if (!session) {
    return [];
  }
  const attachments = normalizeAttachmentList(Array.isArray(session.draftAttachments)
    ? session.draftAttachments
    : (Array.isArray(session.attachments) ? session.attachments : []));
  session.draftAttachments = [...attachments];
  session.attachments = [...attachments];
  return session.draftAttachments;
}

function setDraftAttachments(session, items = []) {
  const nextItems = normalizeAttachmentList(items);
  session.draftAttachments = nextItems;
  session.attachments = [...nextItems];
  return session.draftAttachments;
}

function getExpandedLongTextMessageIds(session) {
  if (!session) {
    return [];
  }
  session.expandedLongTextMessageIds = Array.isArray(session.expandedLongTextMessageIds)
    ? Array.from(new Set(session.expandedLongTextMessageIds.map((item) => String(item || "").trim()).filter(Boolean)))
    : [];
  return session.expandedLongTextMessageIds;
}

function isTrulyBlankSession(thread) {
  const attachments = getDraftAttachments(thread);
  return !(thread.messages?.length)
    && !String(thread.draftText || thread.draft || "").trim()
    && attachments.length === 0
    && !(thread.selectedPromptBlockIds?.length)
    && !(thread.mountedReplyIds?.length);
}

function isSyntheticSessionId(sessionId) {
  return /^session-\d+$/i.test(String(sessionId || ""));
}

function getSessionById(state, sessionId) {
  return state.aiThreads.find((item) => item.id === sessionId || item.sessionId === sessionId) || null;
}

function ensureSession(state, sessionId, title = "01", overrides = {}) {
  let session = getSessionById(state, sessionId);
  if (!session) {
    const topBar = state?.topBar || {};
    const activeSession = state.activeAiThreadId ? getSessionById(state, state.activeAiThreadId) : null;
    const scopedSymbol = overrides.symbol || topBar.symbol || activeSession?.symbol || activeSession?.memory?.symbol || "NQ";
    const scopedTimeframe = overrides.timeframe || topBar.timeframe || activeSession?.timeframe || activeSession?.memory?.timeframe || "1m";
    const scopedWindowRange = overrides.windowRange || topBar.quickRange || activeSession?.windowRange || activeSession?.memory?.window_range || "最近7天";
    const workspaceRole = overrides.workspaceRole || activeSession?.workspaceRole || "analyst";
    session = {
      id: sessionId,
      sessionId: sessionId,
      workspaceRole,
      title,
      pinned: state.aiThreads.length < 3,
      preset: activeSession?.preset || "general",
      symbol: scopedSymbol,
      contractId: overrides.contractId || scopedSymbol,
      timeframe: scopedTimeframe,
      windowRange: scopedWindowRange,
      unreadCount: 0,
      selectedPromptBlockIds: [],
      pinnedContextBlockIds: [],
      includeMemorySummary: false,
      includeRecentMessages: false,
      promptBlocks: [],
      mountedReplyIds: [],
      activePlanId: null,
      recapItems: [],
      scrollOffset: 0,
      autoFollowChat: true,
      hasUnreadChatBelow: false,
      messages: [],
      turns: [],
      draft: "",
      draftText: "",
      attachments: [],
      draftAttachments: [],
      attachmentPreviewCollapsed: false,
      expandedLongTextMessageIds: [],
      analysisTemplate: {
        type: activeSession?.analysisTemplate?.type || "recent_20_bars",
        range: activeSession?.analysisTemplate?.range || "current_window",
        style: activeSession?.analysisTemplate?.style || "standard",
        sendMode: activeSession?.analysisTemplate?.sendMode || "current",
      },
      activeModel: activeSession?.activeModel || "",
      handoffMode: activeSession?.handoffMode || "summary_only",
      memory: {
        session_id: sessionId,
        summary_version: 1,
        active_model: activeSession?.activeModel || "",
        symbol: scopedSymbol,
        timeframe: scopedTimeframe,
        window_range: scopedWindowRange,
        user_goal_summary: "",
        market_context_summary: "",
        key_zones_summary: [],
        active_plans_summary: [],
        invalidated_plans_summary: [],
        important_messages: [],
        current_user_intent: "",
        latest_question: "",
        latest_answer_summary: "",
        selected_annotations: [],
        last_updated_at: null,
      },
    };
    state.aiThreads.push(session);
  }
  return normalizeSessionShape(session, overrides);
}

function getSessionScope(session, state) {
  return {
    symbol: session?.symbol || session?.memory?.symbol || state?.topBar?.symbol || "NQ",
    contractId: session?.contractId || session?.symbol || session?.memory?.symbol || state?.topBar?.symbol || "NQ",
    timeframe: session?.timeframe || session?.memory?.timeframe || state?.topBar?.timeframe || "1m",
    windowRange: session?.windowRange || session?.memory?.window_range || state?.topBar?.quickRange || "最近7天",
  };
}

function collectSessionPlanCards(session) {
  return (session?.messages || []).flatMap((message) => (
    Array.isArray(message.meta?.planCards)
      ? message.meta.planCards
      : (Array.isArray(message.planCards) ? message.planCards : [])
  ));
}

function findPlanInSession(session, planId = null) {
  if (!session || !planId) {
    return { plan: null, message: null };
  }
  const message = (session.messages || []).find((item) => {
    const plans = Array.isArray(item.meta?.planCards)
      ? item.meta.planCards
      : (Array.isArray(item.planCards) ? item.planCards : []);
    return plans.some((plan) => (plan.id || plan.plan_id) === planId);
  }) || null;
  const plans = Array.isArray(message?.meta?.planCards)
    ? message.meta.planCards
    : (Array.isArray(message?.planCards) ? message.planCards : []);
  return {
    plan: plans.find((item) => (item.id || item.plan_id) === planId) || null,
    message,
  };
}

function resolvePinnedPlanContext(session, state) {
  const candidateIds = [];
  if (session?.activePlanId) {
    candidateIds.push(session.activePlanId);
  }
  if (state?.pinnedPlanId && state.pinnedPlanId !== session?.activePlanId) {
    candidateIds.push(state.pinnedPlanId);
  }
  for (const planId of candidateIds) {
    const context = findPlanInSession(session, planId);
    if (context.plan) {
      return { ...context, planId };
    }
  }
  return { plan: null, message: null, planId: null };
}

function formatPlanSideLabel(side) {
  const normalized = String(side || "").trim().toLowerCase();
  if (normalized === "buy" || normalized === "long") {
    return "做多";
  }
  if (normalized === "sell" || normalized === "short") {
    return "做空";
  }
  if (!normalized) {
    return "--";
  }
  return normalized;
}

function formatPlanStatusLabel(status) {
  const normalized = String(status || "").trim().toLowerCase();
  const statusLabels = {
    active: "进行中",
    pending: "待观察",
    executed: "已执行",
    completed: "已完成",
    invalidated: "已失效",
    cancelled: "已取消",
  };
  if (!normalized) {
    return "--";
  }
  return statusLabels[normalized] || String(status || "");
}

function buildPlanEntryLabel(planCard) {
  const entryPrice = planCard.entryPrice ?? planCard.entry_price ?? null;
  const entryLow = planCard.entryPriceLow ?? planCard.entry_price_low ?? null;
  const entryHigh = planCard.entryPriceHigh ?? planCard.entry_price_high ?? null;
  if (entryLow != null && entryHigh != null) {
    const lowLabel = formatPrice(entryLow);
    const highLabel = formatPrice(entryHigh);
    return lowLabel === highLabel ? lowLabel : `${lowLabel} ~ ${highLabel}`;
  }
  if (entryPrice != null) {
    return formatPrice(entryPrice);
  }
  if (entryLow != null) {
    return formatPrice(entryLow);
  }
  if (entryHigh != null) {
    return formatPrice(entryHigh);
  }
  return "--";
}

function buildPlanTargetLabels(planCard) {
  const explicitTargets = Array.isArray(planCard.take_profits)
    ? planCard.take_profits
    : (Array.isArray(planCard.takeProfits) ? planCard.takeProfits : []);
  const targets = explicitTargets.length
    ? explicitTargets
    : [
        planCard.targetPrice != null ? { target_price: planCard.targetPrice } : null,
        planCard.targetPrice2 != null ? { target_price: planCard.targetPrice2 } : null,
      ].filter(Boolean);
  return targets.map((target, index) => {
    const price = target?.target_price ?? target?.targetPrice ?? target?.price ?? null;
    const baseLabel = String(target?.label || target?.name || `TP${index + 1}`).trim() || `TP${index + 1}`;
    if (price == null) {
      return baseLabel;
    }
    return `${baseLabel} ${formatPrice(price)}`;
  }).filter(Boolean);
}

function buildPlanStructuredSummary(planCard) {
  const summary = String(planCard?.summary || planCard?.notes || "").trim();
  const notes = String(planCard?.notes || "").trim();
  const targetLabels = buildPlanTargetLabels(planCard);
  const lines = [
    `计划：${planCard?.title || "AI计划卡"}`,
    `方向：${formatPlanSideLabel(planCard?.side)}`,
    `入场：${buildPlanEntryLabel(planCard)}`,
    `止损：${formatPrice(planCard?.stopPrice ?? planCard?.stop_price ?? null)}`,
    `止盈：${targetLabels.length ? targetLabels.join(" / ") : "--"}`,
    `状态：${formatPlanStatusLabel(planCard?.status)}`,
  ];
  if (summary) {
    lines.push(`摘要：${summary}`);
  }
  if (notes && notes !== summary) {
    lines.push(`备注：${notes}`);
  }
  return lines.join("\n");
}

function buildPlanRecapItem(planCard, session) {
  const targetLabels = buildPlanTargetLabels(planCard);
  return normalizeRecapItem({
    id: `recap-${createPlanId()}`,
    title: planCard?.title || "AI计划卡",
    planId: planCard?.id || planCard?.plan_id || null,
    messageId: planCard?.message_id || null,
    sessionId: session?.id || session?.sessionId || null,
    side: planCard?.side || "",
    status: planCard?.status || "",
    entryLabel: buildPlanEntryLabel(planCard),
    stopLabel: formatPrice(planCard?.stopPrice ?? planCard?.stop_price ?? null),
    targetLabels,
    summary: String(planCard?.summary || planCard?.notes || "").trim(),
    notes: String(planCard?.notes || "").trim(),
    structuredSummary: buildPlanStructuredSummary(planCard),
    sourceModel: session?.activeModel || session?.memory?.active_model || "AI计划卡",
    addedAt: new Date().toISOString(),
  }, session);
}

function upsertSessionRecapItem(session, recapItem) {
  const nextItem = normalizeRecapItem(recapItem, session, 0);
  if (!nextItem) {
    return null;
  }
  const currentItems = Array.isArray(session?.recapItems) ? session.recapItems : [];
  const nextPlanId = nextItem.planId || nextItem.plan_id || null;
  const filteredItems = currentItems.filter((item) => {
    if (nextPlanId) {
      return (item.planId || item.plan_id) !== nextPlanId;
    }
    return item.id !== nextItem.id;
  });
  session.recapItems = [nextItem, ...filteredItems].slice(0, 12);
  return nextItem;
}

function buildPlanCardMarkup(planCard) {
  const metrics = [
    `方向 ${escapeHtml(planCard.side === "sell" ? "空" : planCard.side === "buy" ? "多" : "中性")}`,
    `入场 ${escapeHtml(buildPlanEntryLabel(planCard))}`,
    `止损 ${escapeHtml(formatPrice(planCard.stopPrice ?? planCard.stop_price))}`,
  ];
  buildPlanTargetLabels(planCard).slice(0, 2).forEach((label) => {
    metrics.push(escapeHtml(label));
  });
  return `
    <div class="chat-plan-card" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">
      <div class="chat-plan-card-head">
        <strong>${escapeHtml(planCard.title || "AI计划卡")}</strong>
        <span class="plan-chip status">${escapeHtml(planCard.status || "active")}</span>
      </div>
      <div class="chat-plan-card-summary">${escapeHtml(planCard.summary || planCard.notes || "结构化交易计划")}</div>
      <div class="chat-plan-card-metrics">${metrics.map((item) => `<span class="plan-chip">${item}</span>`).join("")}</div>
      <div class="chat-plan-card-actions">
        <button type="button" class="plan-action" data-plan-action="show" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">上图</button>
        <button type="button" class="plan-action" data-plan-action="focus" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">只看此计划</button>
        <button type="button" class="plan-action" data-plan-action="jump" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">查看图表</button>
        <button type="button" class="plan-action" data-plan-action="pin" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">固定顶部</button>
        <button type="button" class="plan-action" data-plan-action="copy" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">复制摘要</button>
        <button type="button" class="plan-action" data-plan-action="recap" data-plan-id="${escapeHtml(planCard.id || planCard.plan_id || "")}">加入复盘</button>
      </div>
    </div>
  `;
}

function renderAttachmentPreview(attachment) {
  const label = escapeHtml(attachment.name || "附件");
  const kind = escapeHtml(attachment.kind || attachment.media_type || "file");
  return `<div class="attachment-chip">${buildAttachmentPreviewMarkup(attachment)}<div class="attachment-chip-meta"><span>${label}</span><span class="meta">${kind}</span></div></div>`;
}

function renderMessage(message, { expandedLongText = false } = {}) {
  const metaChips = [];
  if (message.status && message.role === "assistant") {
    metaChips.push(`<span class="chip ${escapeHtml(message.status)}">${escapeHtml(message.status)}</span>`);
  }
  if (message.parent_message_id || message.meta?.parent_message_id) {
    metaChips.push(`<span class="chip emphasis">重新生成</span>`);
  }
  if (message.meta?.preset) {
    metaChips.push(`<span class="chip">${escapeHtml(message.meta.preset)}</span>`);
  }
  if (message.role === "assistant") {
    const modeLabel = message.meta?.session_only ? "session-only" : "replay-aware";
    const modeClass = message.meta?.session_only ? "warn" : "good";
    metaChips.push(`<span class="chip ${modeClass}">${escapeHtml(modeLabel)}</span>`);
  }
  if (message.meta?.model || message.meta?.provider) {
    metaChips.push(`<span class="chip emphasis">${escapeHtml([message.meta?.provider, message.meta?.model].filter(Boolean).join("/"))}</span>`);
  }
  const planCards = Array.isArray(message.meta?.planCards) ? message.meta.planCards : [];
  const attachments = Array.isArray(message.meta?.attachments) ? message.meta.attachments : [];
  const replyObjectCount = Number(message.meta?.annotationCount ?? message.meta?.objectCount ?? message.annotations?.length ?? 0);
  const canProjectReply = message.role === "assistant" && replyObjectCount > 0;
  const messageActionMarkup = message.role === "assistant"
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
        <button type="button" class="secondary tiny" data-message-action="regenerate" data-message-id="${escapeHtml(message.message_id || "")}">重新生成</button>
      </div>
    `
    : "";
  if (canProjectReply) {
    metaChips.push(`<span class="chip">${escapeHtml(`对象 ${replyObjectCount}`)}</span>`);
  }
  return `
    <div class="chat-message ${escapeHtml(message.role)} ${escapeHtml(message.status || "")}" data-message-id="${escapeHtml(message.message_id || "")}">
      <div class="chat-bubble ${escapeHtml(message.role)} ${escapeHtml(message.status || "")}">
        <div class="chat-bubble-body">
          ${buildLongTextMarkup(message.content || "", {
            expanded: expandedLongText,
            messageId: message.message_id || "",
          })}
          ${(message.parent_message_id || message.meta?.parent_message_id) ? `<div class="chat-regenerate-note">由上一条回复重新生成</div>` : ""}
          ${attachments.length ? `<div class="chat-attachment-list">${attachments.map((item) => renderAttachmentPreview(item)).join("")}</div>` : ""}
          ${metaChips.length ? `<div class="chat-meta">${metaChips.join("")}</div>` : ""}
          ${messageActionMarkup}
          ${planCards.length ? `<div class="chat-plan-card-list">${planCards.map((item) => buildPlanCardMarkup(item)).join("")}</div>` : ""}
        </div>
      </div>
    </div>
  `;
}

function buildPinnedPlanMarkup(planCard) {
  const targetLabels = buildPlanTargetLabels(planCard);
  const lines = [
    `${escapeHtml(planCard.title || "AI计划卡")}`,
    `方向：${escapeHtml(formatPlanSideLabel(planCard.side))}`,
    `入场：${escapeHtml(buildPlanEntryLabel(planCard))}`,
    `止损：${escapeHtml(formatPrice(planCard.stopPrice ?? planCard.stop_price))}`,
    targetLabels.length ? `止盈：${escapeHtml(targetLabels.join(" / "))}` : "",
    planCard.status ? `状态：${escapeHtml(formatPlanStatusLabel(planCard.status))}` : "",
    planCard.summary ? escapeHtml(planCard.summary) : "",
  ].filter(Boolean);
  return lines.join("<br>");
}

function renderAuxiliaryStrips(session, els, state, onPlanAction = null, fetchJson = null, onPromptBlocksChanged = null) {
  const memory = session.memory || {};
  const promptBlocks = Array.isArray(session.promptBlocks) ? session.promptBlocks : [];
  const selectedPromptBlockIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
  const mountedReplyIds = Array.isArray(session.mountedReplyIds) ? session.mountedReplyIds : [];
  if (els.sessionContextStrip) {
    const parts = [
      memory.user_goal_summary ? `目标：${escapeHtml(memory.user_goal_summary)}` : "",
      memory.market_context_summary ? `市场：${escapeHtml(memory.market_context_summary)}` : "",
      Array.isArray(memory.key_zones_summary) && memory.key_zones_summary.length ? `区域：${escapeHtml(memory.key_zones_summary.slice(-3).join("；"))}` : "",
    ].filter(Boolean);
    els.sessionContextStrip.hidden = parts.length === 0;
    els.sessionContextStrip.innerHTML = `
      <div class="strip-head"><span class="strip-title">会话摘要</span></div>
      <div class="meta">${parts.join(" | ") || "无摘要。"}</div>
    `;
  }

  if (els.promptSelectionBar) {
    const includeMemorySummary = !!session.includeMemorySummary;
    const includeRecentMessages = !!session.includeRecentMessages;
    const selectedBlocks = selectedPromptBlockIds
      .map((blockId) => promptBlocks.find((item) => item.blockId === blockId || item.id === blockId))
      .filter(Boolean);
    const blockPreviewCache = session.promptBlockPreviewCache || {};
    const syncPromptBlockSelection = () => {
      session.selectedPromptBlockIds = selectedBlocks
        .map((block) => block.blockId || block.id)
        .filter(Boolean);
      session.promptBlocks = (session.promptBlocks || []).filter((block) => session.selectedPromptBlockIds.includes(block.blockId || block.id));
      session.promptBlockPreviewCache = Object.fromEntries(
        Object.entries(blockPreviewCache).filter(([blockId]) => session.selectedPromptBlockIds.includes(blockId)),
      );
      session.pinnedContextBlockIds = (session.pinnedContextBlockIds || []).filter((blockId) => session.selectedPromptBlockIds.includes(blockId));
      onPromptBlocksChanged?.(session, {
        selectedPromptBlockIds: session.selectedPromptBlockIds,
        pinnedContextBlockIds: session.pinnedContextBlockIds,
        includeMemorySummary: session.includeMemorySummary,
        includeRecentMessages: session.includeRecentMessages,
      });
      persistSessions(state);
      renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
    };
    const loadPromptBlockDetail = async (blockId) => {
      if (!fetchJson || !blockId || blockPreviewCache[blockId]?.loaded) {
        return;
      }
      try {
        const envelope = await fetchJson(`/api/v1/workbench/chat/prompt-blocks/${encodeURIComponent(blockId)}`);
        const detail = envelope?.prompt_block || envelope?.block || envelope?.blocks?.[0] || envelope || {};
        blockPreviewCache[blockId] = {
          loaded: true,
          content: detail.full_payload != null
            ? JSON.stringify(detail.full_payload, null, 2)
            : detail.raw_text || detail.preview_text || detail.previewText || "暂无原始内容",
        };
        session.promptBlockPreviewCache = blockPreviewCache;
        persistSessions(state);
        renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
      } catch (error) {
        blockPreviewCache[blockId] = {
          loaded: true,
          content: `加载失败：${error.message || String(error)}`,
        };
        session.promptBlockPreviewCache = blockPreviewCache;
        persistSessions(state);
        renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
      }
    };
    const orderedBlocks = [...selectedBlocks].sort((a, b) => {
      const aId = a.blockId || a.id;
      const bId = b.blockId || b.id;
      return session.selectedPromptBlockIds.indexOf(aId) - session.selectedPromptBlockIds.indexOf(bId);
    });
    const movePromptBlock = (blockId, direction) => {
      const currentIds = [...(session.selectedPromptBlockIds || [])];
      const currentIndex = currentIds.indexOf(blockId);
      if (currentIndex < 0) {
        return;
      }
      const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
      const isPinned = pinnedIds.includes(blockId);
      const candidateIndex = currentIndex + direction;
      if (candidateIndex < 0 || candidateIndex >= currentIds.length) {
        return;
      }
      const neighborId = currentIds[candidateIndex];
      const neighborPinned = pinnedIds.includes(neighborId);
      if (isPinned !== neighborPinned) {
        return;
      }
      [currentIds[currentIndex], currentIds[candidateIndex]] = [currentIds[candidateIndex], currentIds[currentIndex]];
      session.selectedPromptBlockIds = currentIds;
      onPromptBlocksChanged?.(session, {
        selectedPromptBlockIds: session.selectedPromptBlockIds,
        pinnedContextBlockIds: session.pinnedContextBlockIds,
        includeMemorySummary: session.includeMemorySummary,
        includeRecentMessages: session.includeRecentMessages,
      });
      persistSessions(state);
      renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
    };
    const clearEphemeralPromptBlocks = () => {
      const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
      session.selectedPromptBlockIds = (session.selectedPromptBlockIds || []).filter((id) => pinnedIds.includes(id));
      session.promptBlocks = (session.promptBlocks || []).filter((block) => pinnedIds.includes(block.blockId || block.id));
      session.promptBlockPreviewCache = Object.fromEntries(
        Object.entries(session.promptBlockPreviewCache || {}).filter(([blockId]) => pinnedIds.includes(blockId)),
      );
      onPromptBlocksChanged?.(session, {
        selectedPromptBlockIds: session.selectedPromptBlockIds,
        pinnedContextBlockIds: session.pinnedContextBlockIds,
        includeMemorySummary: session.includeMemorySummary,
        includeRecentMessages: session.includeRecentMessages,
      });
      persistSessions(state);
      renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
    };
    const clearPinnedPromptBlocks = () => {
      const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
      session.selectedPromptBlockIds = (session.selectedPromptBlockIds || []).filter((id) => !pinnedIds.includes(id));
      session.promptBlocks = (session.promptBlocks || []).filter((block) => !pinnedIds.includes(block.blockId || block.id));
      session.promptBlockPreviewCache = Object.fromEntries(
        Object.entries(session.promptBlockPreviewCache || {}).filter(([blockId]) => !pinnedIds.includes(blockId)),
      );
      session.pinnedContextBlockIds = [];
      onPromptBlocksChanged?.(session, {
        selectedPromptBlockIds: session.selectedPromptBlockIds,
        pinnedContextBlockIds: session.pinnedContextBlockIds,
        includeMemorySummary: session.includeMemorySummary,
        includeRecentMessages: session.includeRecentMessages,
      });
      persistSessions(state);
      renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
    };
    const buildBlockChip = (block, group) => {
      const blockId = block.blockId || block.id;
      const label = block.title || block.preview_text || block.previewText || block.kind || blockId;
      const preview = block.previewText || block.preview_text || "";
      const sourceLabel = block.sourceLabel || block.source_label || block.kind || "上下文块";
      const pinned = Array.isArray(session.pinnedContextBlockIds) && session.pinnedContextBlockIds.includes(blockId);
      const isActive = Array.isArray(session.selectedPromptBlockIds) && session.selectedPromptBlockIds[session.selectedPromptBlockIds.length - 1] === blockId;
      const expanded = !!blockPreviewCache[blockId]?.loaded;
      const expandedContent = blockPreviewCache[blockId]?.content || "";
      const sameGroupIds = (session.selectedPromptBlockIds || []).filter((id) => ((session.pinnedContextBlockIds || []).includes(id)) === (group === "pinned"));
      const groupIndex = sameGroupIds.indexOf(blockId);
      const canMoveUp = groupIndex > 0;
      const canMoveDown = groupIndex >= 0 && groupIndex < sameGroupIds.length - 1;
      return `
        <span class="strip-chip prompt-chip ${pinned ? "pinned" : ""} ${isActive ? "active" : ""}" data-prompt-block-id="${escapeHtml(blockId)}" title="${escapeHtml(preview || label)}">
          <span class="strip-chip-text">
            <span class="strip-chip-title-row">
              <span class="strip-chip-title">${escapeHtml(label)}</span>
              <span class="strip-chip-kind">${escapeHtml(sourceLabel)}</span>
            </span>
            ${preview && preview !== label ? `<span class="strip-chip-meta">${escapeHtml(preview)}</span>` : ""}
            ${expandedContent ? `<span class="strip-chip-detail">${escapeHtml(expandedContent)}</span>` : ""}
          </span>
          <span class="strip-chip-actions">
            <button type="button" class="strip-chip-action" data-prompt-block-move-up="${escapeHtml(blockId)}" ${canMoveUp ? "" : "disabled"} aria-label="上移">↑</button>
            <button type="button" class="strip-chip-action" data-prompt-block-move-down="${escapeHtml(blockId)}" ${canMoveDown ? "" : "disabled"} aria-label="下移">↓</button>
            <button type="button" class="strip-chip-action" data-prompt-block-toggle-pin="${escapeHtml(blockId)}" aria-label="${pinned ? "取消固定" : "固定上下文"}">${pinned ? "取消固定" : "固定"}</button>
            <button type="button" class="strip-chip-action" data-prompt-block-expand="${escapeHtml(blockId)}" aria-label="查看原始内容">${expanded ? "刷新详情" : "查看详情"}</button>
            <button type="button" class="strip-chip-remove" data-prompt-block-remove="${escapeHtml(blockId)}" aria-label="移除上下文">×</button>
          </span>
        </span>
      `;
    };
    const pinnedChips = orderedBlocks
      .filter((block) => (session.pinnedContextBlockIds || []).includes(block.blockId || block.id))
      .map((block) => buildBlockChip(block, "pinned"));
    const ephemeralChips = orderedBlocks
      .filter((block) => !(session.pinnedContextBlockIds || []).includes(block.blockId || block.id))
      .map((block) => buildBlockChip(block, "ephemeral"));
    const chipSections = [];
    if (pinnedChips.length) {
      chipSections.push(`
        <div class="prompt-chip-group">
          <div class="prompt-chip-group-head">
            <div class="prompt-chip-group-title">固定上下文</div>
            <button type="button" class="secondary tiny" data-prompt-clear-pinned="true">清空固定上下文</button>
          </div>
          <div class="strip-chip-row">${pinnedChips.join("")}</div>
        </div>
      `);
    }
    if (ephemeralChips.length) {
      chipSections.push(`
        <div class="prompt-chip-group">
          <div class="prompt-chip-group-head">
            <div class="prompt-chip-group-title">本次临时上下文</div>
            <button type="button" class="secondary tiny" data-prompt-clear-ephemeral="true">清空临时上下文</button>
          </div>
          <div class="strip-chip-row">${ephemeralChips.join("")}</div>
        </div>
      `);
    }
    const hasPromptSummary = chipSections.length > 0 || includeMemorySummary || includeRecentMessages;
    els.promptSelectionBar.hidden = !hasPromptSummary;
    if (hasPromptSummary) {
      els.promptSelectionBar.innerHTML = `
        <div class="strip-head"><span class="strip-title">本次发送上下文</span></div>
        <div class="meta">${[
          `Prompt blocks ${selectedBlocks.length || 0} 个`,
          `记忆摘要 ${includeMemorySummary ? "开启" : "关闭"}`,
          `最近消息 ${includeRecentMessages ? "开启" : "关闭"}`,
        ].join(" | ")}</div>
        <div class="strip-chip-row prompt-send-flags">
          <button type="button" class="secondary tiny ${includeMemorySummary ? "is-active" : ""}" data-prompt-toggle-memory="true">记忆摘要</button>
          <button type="button" class="secondary tiny ${includeRecentMessages ? "is-active" : ""}" data-prompt-toggle-recent="true">最近消息</button>
        </div>
        ${chipSections.join("")}
      `;
      els.promptSelectionBar.querySelectorAll("button[data-prompt-clear-pinned]").forEach((button) => {
        button.addEventListener("click", () => {
          clearPinnedPromptBlocks();
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-clear-ephemeral]").forEach((button) => {
        button.addEventListener("click", () => {
          clearEphemeralPromptBlocks();
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-toggle-memory]").forEach((button) => {
        button.addEventListener("click", () => {
          session.includeMemorySummary = !session.includeMemorySummary;
          onPromptBlocksChanged?.(session, {
            selectedPromptBlockIds: session.selectedPromptBlockIds,
            pinnedContextBlockIds: session.pinnedContextBlockIds,
            includeMemorySummary: session.includeMemorySummary,
            includeRecentMessages: session.includeRecentMessages,
          });
          persistSessions(state);
          renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-toggle-recent]").forEach((button) => {
        button.addEventListener("click", () => {
          session.includeRecentMessages = !session.includeRecentMessages;
          onPromptBlocksChanged?.(session, {
            selectedPromptBlockIds: session.selectedPromptBlockIds,
            pinnedContextBlockIds: session.pinnedContextBlockIds,
            includeMemorySummary: session.includeMemorySummary,
            includeRecentMessages: session.includeRecentMessages,
          });
          persistSessions(state);
          renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-block-move-up]").forEach((button) => {
        button.addEventListener("click", () => {
          movePromptBlock(button.dataset.promptBlockMoveUp, -1);
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-block-move-down]").forEach((button) => {
        button.addEventListener("click", () => {
          movePromptBlock(button.dataset.promptBlockMoveDown, 1);
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-block-remove]").forEach((button) => {
        button.addEventListener("click", () => {
          const blockId = button.dataset.promptBlockRemove;
          const blockIndex = selectedBlocks.findIndex((item) => (item.blockId || item.id) === blockId);
          if (blockIndex >= 0) {
            selectedBlocks.splice(blockIndex, 1);
          }
          delete blockPreviewCache[blockId];
          session.promptBlockPreviewCache = blockPreviewCache;
          syncPromptBlockSelection();
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-block-toggle-pin]").forEach((button) => {
        button.addEventListener("click", () => {
          const blockId = button.dataset.promptBlockTogglePin;
          const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
          session.pinnedContextBlockIds = pinnedIds.includes(blockId)
            ? pinnedIds.filter((id) => id !== blockId)
            : [...pinnedIds, blockId];
          onPromptBlocksChanged?.(session, {
            selectedPromptBlockIds: session.selectedPromptBlockIds,
            pinnedContextBlockIds: session.pinnedContextBlockIds,
            includeMemorySummary: session.includeMemorySummary,
            includeRecentMessages: session.includeRecentMessages,
          });
          persistSessions(state);
          renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
        });
      });
      els.promptSelectionBar.querySelectorAll("button[data-prompt-block-expand]").forEach((button) => {
        button.addEventListener("click", () => {
          const blockId = button.dataset.promptBlockExpand;
          loadPromptBlockDetail(blockId);
        });
      });
    }
  }

  if (els.mountedReplyStrip) {
    const mountedMessages = mountedReplyIds
      .map((messageId) => (session.messages || []).find((item) => item.message_id === messageId && item.role === "assistant"))
      .filter(Boolean);
    const chips = mountedMessages.map((item) => {
      const objectCount = (state.aiAnnotations || []).filter((annotation) => annotation.session_id === session.id && annotation.message_id === item.message_id).length;
      const label = item.meta?.replyTitle || item.replyTitle || summarizeText(item.content, 42);
      const preview = summarizeText(item.content, 72);
      const selectedAnnotation = state.aiAnnotations?.find((annotation) => annotation.id === state.selectedAnnotationId);
      const isActive = item.message_id === selectedAnnotation?.message_id;
      return `
        <span class="strip-chip mounted mounted-reply-chip ${isActive ? "active" : ""}" data-mounted-message-id="${escapeHtml(item.message_id)}" title="${escapeHtml(preview || label)}">
          <span class="strip-chip-text">
            <span class="strip-chip-title">${escapeHtml(label)}</span>
            <span class="strip-chip-meta">${objectCount ? `${objectCount} 个对象` : "无对象"}</span>
          </span>
          <button type="button" class="strip-chip-remove" data-mounted-reply-remove="${escapeHtml(item.message_id)}" aria-label="取消挂载">×</button>
        </span>
      `;
    });
    els.mountedReplyStrip.hidden = chips.length === 0;
    if (chips.length) {
      els.mountedReplyStrip.innerHTML = `
        <div class="strip-head"><span class="strip-title">已挂载回复</span></div>
        <div class="strip-chip-row">${chips.join("")}</div>
      `;
      els.mountedReplyStrip.querySelectorAll("[data-mounted-message-id]").forEach((node) => {
        node.addEventListener("click", (event) => {
          if (event.target?.closest("button[data-mounted-reply-remove]")) {
            return;
          }
          const messageId = node.dataset.mountedMessageId;
          session.activePlanId = null;
          onPlanAction?.({ action: "show", messageId, sessionId: session.id, planId: null });
        });
      });
      els.mountedReplyStrip.querySelectorAll("button[data-mounted-reply-remove]").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          const messageId = button.dataset.mountedReplyRemove;
          onPlanAction?.({ action: "unmount", messageId, sessionId: session.id, planId: null });
        });
      });
    }
  }

  if (els.pinnedPlanCard && els.pinnedPlanCardBody && els.pinnedPlanCardActions) {
    const { planId: pinnedPlanId, plan: pinnedPlan, message: pinnedMessage } = resolvePinnedPlanContext(session, state);
    const selectedAnnotation = state.aiAnnotations?.find((annotation) => annotation.id === state.selectedAnnotationId) || null;
    const pinnedPlanAnnotations = pinnedPlanId
      ? (state.aiAnnotations || []).filter((annotation) => annotation.plan_id === pinnedPlanId && annotation.session_id === session.id)
      : [];
    const pinnedPlanIsActive = !!pinnedPlan && (
      session.activePlanId === pinnedPlanId
      || selectedAnnotation?.plan_id === pinnedPlanId
      || pinnedPlanAnnotations.some((annotation) => annotation.id === state.selectedAnnotationId)
    );
    els.pinnedPlanCard.hidden = !pinnedPlan;
    if (pinnedPlan) {
      els.pinnedPlanCard.classList.toggle("active", pinnedPlanIsActive);
      els.pinnedPlanCardBody.innerHTML = buildPinnedPlanMarkup(pinnedPlan);
      els.pinnedPlanCardActions.innerHTML = `
        <button type="button" class="secondary tiny ${pinnedPlanIsActive ? "is-active" : ""}" data-pinned-plan-action="show" data-plan-id="${escapeHtml(pinnedPlan.id || pinnedPlan.plan_id || "")}" data-message-id="${escapeHtml(pinnedMessage?.message_id || "")}">上图</button>
        <button type="button" class="secondary tiny ${session.activePlanId === pinnedPlanId ? "is-active" : ""}" data-pinned-plan-action="focus" data-plan-id="${escapeHtml(pinnedPlan.id || pinnedPlan.plan_id || "")}" data-message-id="${escapeHtml(pinnedMessage?.message_id || "")}">只看此计划</button>
        <button type="button" class="secondary tiny" data-pinned-plan-action="jump" data-plan-id="${escapeHtml(pinnedPlan.id || pinnedPlan.plan_id || "")}" data-message-id="${escapeHtml(pinnedMessage?.message_id || "")}">查看图表</button>
      `;
      els.pinnedPlanCardActions.querySelectorAll("button[data-pinned-plan-action]").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.dataset.pinnedPlanAction === "focus") {
            session.activePlanId = pinnedPlanId;
            persistSessions(state);
          }
          onPlanAction?.({
            action: button.dataset.pinnedPlanAction,
            planId: button.dataset.planId,
            messageId: button.dataset.messageId,
            sessionId: session.id,
          });
        });
      });
    } else {
      els.pinnedPlanCard.classList.remove("active");
      els.pinnedPlanCardBody.textContent = "暂无固定计划";
      els.pinnedPlanCardActions.innerHTML = "";
    }
  }
}

function persistSessions(state) {
  writeStorage("sessions", state.aiThreads.map((session) => {
    const promptBlocks = Array.isArray(session.promptBlocks) ? session.promptBlocks : [];
    const selectedIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
    const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
    const draftAttachments = getDraftAttachments(session).map((item) => sanitizeAttachmentForStorage(item));
    return {
      ...session,
      attachments: draftAttachments,
      draftAttachments,
      messages: (session.messages || []).map((message) => ({
        ...message,
        meta: {
          ...(message.meta || {}),
          attachments: Array.isArray(message.meta?.attachments)
            ? message.meta.attachments.map((item) => sanitizeAttachmentForStorage(item))
            : [],
        },
      })),
      promptBlocks: promptBlocks.filter((block) => selectedIds.includes(block.blockId || block.id)),
      promptBlockPreviewCache: Object.fromEntries(
        Object.entries(session.promptBlockPreviewCache || {}).filter(([blockId]) => selectedIds.includes(blockId)),
      ),
      pinnedContextBlockIds: pinnedIds.filter((blockId) => selectedIds.includes(blockId)),
      includeMemorySummary: !!session.includeMemorySummary,
      includeRecentMessages: !!session.includeRecentMessages,
    };
  }));
  writeStorage("workbench", {
    activeAiThreadId: state.activeAiThreadId,
    drawerState: state.drawerState,
    topBar: state.topBar,
    pinnedPlanId: state.pinnedPlanId || null,
    layerState: state.layerState || null,
  });
}

export function createAiThreadController({ state, els, onPlanAction = null, onMountedRepliesChanged = null, onPromptBlocksChanged = null, fetchJson = null, renderStatusStrip = null, onSessionActivated = null, onPlanMetaAction = null }) {
  const CHAT_FOLLOW_THRESHOLD = 48;
  const DRAFT_SYNC_DELAY_MS = 420;
  const draftSyncTimers = new Map();
  let sessionWorkspaceQuery = "";

  function getWorkspaceRole(session, fallback = "analyst") {
    return String(session?.workspaceRole || fallback || "analyst").trim().toLowerCase() || "analyst";
  }

  function listSessionsByRole(role = "analyst") {
    const normalizedRole = getWorkspaceRole({ workspaceRole: role });
    return (state.aiThreads || []).filter((thread) => getWorkspaceRole(thread) === normalizedRole);
  }

  function getSessionTimestamp(session) {
    const candidates = [
      session?.updatedAt,
      session?.memory?.last_updated_at,
      session?.messages?.[session.messages.length - 1]?.updated_at,
      session?.messages?.[session.messages.length - 1]?.created_at,
      session?.createdAt,
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
  }

  function hasSessionDraft(session) {
    return !!String(session?.draftText || session?.draft || "").trim() || getDraftAttachments(session).length > 0;
  }

  function shouldSurfaceSession(session, { includeActiveBlank = true } = {}) {
    if (!session) {
      return false;
    }
    if (!isTrulyBlankSession(session)) {
      return true;
    }
    if (!includeActiveBlank) {
      return false;
    }
    return (session.id || session.sessionId) === state.activeAiThreadId;
  }

  function getSessionPreviewText(session) {
    const latestAssistant = [...(session?.messages || [])].reverse().find((item) => item.role === "assistant" && String(item.content || "").trim());
    const latestUser = [...(session?.messages || [])].reverse().find((item) => item.role === "user" && String(item.content || "").trim());
    const draftText = String(session?.draftText || session?.draft || "").trim();
    return summarizeText(
      latestAssistant?.replyTitle
        || latestAssistant?.meta?.replyTitle
        || session?.memory?.latest_answer_summary
        || latestAssistant?.content
        || latestUser?.content
        || draftText
        || session?.memory?.current_user_intent
        || "无摘要",
      80,
    );
  }

  function formatSessionUpdatedLabel(session) {
    const timestamp = getSessionTimestamp(session);
    if (!timestamp) {
      return "";
    }
    const value = new Date(timestamp);
    if (Number.isNaN(value.getTime())) {
      return "";
    }
    const now = new Date();
    const sameDay = value.getFullYear() === now.getFullYear()
      && value.getMonth() === now.getMonth()
      && value.getDate() === now.getDate();
    const hours = String(value.getHours()).padStart(2, "0");
    const minutes = String(value.getMinutes()).padStart(2, "0");
    return sameDay ? `${hours}:${minutes}` : `${value.getMonth() + 1}/${value.getDate()} ${hours}:${minutes}`;
  }

  function compareSessionsByPriority(a, b, { preferredSymbol = null } = {}) {
    const aScope = getSessionScope(a, state);
    const bScope = getSessionScope(b, state);
    const aDraft = hasSessionDraft(a);
    const bDraft = hasSessionDraft(b);
    const aActive = a.id === state.activeAiThreadId;
    const bActive = b.id === state.activeAiThreadId;
    if (aActive !== bActive) {
      return aActive ? -1 : 1;
    }
    if (preferredSymbol) {
      const aMatches = aScope.symbol === preferredSymbol;
      const bMatches = bScope.symbol === preferredSymbol;
      if (aMatches !== bMatches) {
        return aMatches ? -1 : 1;
      }
    }
    if (shouldSurfaceSession(a) !== shouldSurfaceSession(b)) {
      return shouldSurfaceSession(a) ? -1 : 1;
    }
    if (a.pinned !== b.pinned) {
      return a.pinned ? -1 : 1;
    }
    if (!!a.activePlanId !== !!b.activePlanId) {
      return a.activePlanId ? -1 : 1;
    }
    if (aDraft !== bDraft) {
      return aDraft ? -1 : 1;
    }
    if ((a.unreadCount || 0) !== (b.unreadCount || 0)) {
      return (b.unreadCount || 0) - (a.unreadCount || 0);
    }
    const timestampDiff = getSessionTimestamp(b) - getSessionTimestamp(a);
    if (timestampDiff !== 0) {
      return timestampDiff;
    }
    return String(a.title || "").localeCompare(String(b.title || ""), "zh-Hans-CN");
  }

  function getPreferredSessionForSymbol(symbol, { workspaceRole = "analyst" } = {}) {
    const normalizedSymbol = String(symbol || "").trim().toUpperCase();
    const normalizedRole = getWorkspaceRole({ workspaceRole });
    return listSessionsByRole(normalizedRole)
      .filter((thread) => getSessionScope(thread, state).symbol === normalizedSymbol)
      .sort((a, b) => compareSessionsByPriority(a, b, { preferredSymbol: normalizedSymbol }))[0] || null;
  }

  function buildSessionSearchText(session) {
    const scope = getSessionScope(session, state);
    return [
      session?.title,
      getWorkspaceRole(session) === "scribe" ? "事件整理 记录 scribe" : "行情分析 analyst",
      scope.symbol,
      scope.timeframe,
      scope.windowRange,
      getSessionPreviewText(session),
      session?.memory?.current_user_intent,
      session?.memory?.latest_answer_summary,
      session?.activeModel,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  async function patchSessionOnServer(session, updates = {}) {
    if (!fetchJson || !session || isSyntheticSessionId(session.id)) {
      return null;
    }
    try {
      return await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
    } catch (error) {
      console.warn("同步会话变更失败:", error);
      return null;
    }
  }

  async function archiveSessionOnServer(session) {
    if (!fetchJson || !session || isSyntheticSessionId(session.id)) {
      return null;
    }
    try {
      return await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/archive`, {
        method: "POST",
      });
    } catch (error) {
      console.warn("归档会话失败:", error);
      return null;
    }
  }

  async function syncDraftStateToServer(session) {
    if (!session) {
      return null;
    }
    draftSyncTimers.delete(session.id);
    return patchSessionOnServer(session, {
      draft_text: session.draftText ?? session.draft ?? "",
      draft_attachments: buildServerAttachmentPayloads(getDraftAttachments(session)),
      scroll_offset: Number.isFinite(session.scrollOffset) ? session.scrollOffset : 0,
    });
  }

  function scheduleDraftStateSync(session, { immediate = false } = {}) {
    if (!fetchJson || !session || isSyntheticSessionId(session.id)) {
      return;
    }
    const existingTimer = draftSyncTimers.get(session.id);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
      draftSyncTimers.delete(session.id);
    }
    if (immediate) {
      void syncDraftStateToServer(session);
      return;
    }
    const timer = window.setTimeout(() => {
      void syncDraftStateToServer(session);
    }, DRAFT_SYNC_DELAY_MS);
    draftSyncTimers.set(session.id, timer);
  }

  function buildBranchTitle(baseTitle) {
    const normalizedBase = String(baseTitle || "会话").trim() || "会话";
    const existingTitles = new Set((state.aiThreads || []).map((item) => item.title));
    let index = 1;
    let candidate = `${normalizedBase} 分支`;
    while (existingTitles.has(candidate)) {
      index += 1;
      candidate = `${normalizedBase} 分支${index}`;
    }
    return candidate;
  }

  async function cloneMessagesToBackend(targetSessionId, sourceMessages = []) {
    const messageIdMap = new Map();
    if (!fetchJson || !targetSessionId) {
      return messageIdMap;
    }
    for (const message of sourceMessages) {
      if (!message?.role || !message?.content) {
        continue;
      }
      try {
        const response = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(targetSessionId)}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            role: message.role,
            content: message.content,
            attachments: buildServerAttachmentPayloads(message.meta?.attachments || []),
            selected_block_ids: Array.isArray(message.meta?.selected_block_ids) ? message.meta.selected_block_ids : [],
          }),
        });
        const storedMessages = Array.isArray(response?.messages) ? response.messages : [];
        const latest = storedMessages[storedMessages.length - 1];
        if (latest?.message_id && message?.message_id) {
          messageIdMap.set(message.message_id, latest.message_id);
        }
      } catch (error) {
        console.warn("复制会话消息到后端失败:", error);
      }
    }
    return messageIdMap;
  }

  function getActiveThread() {
    const fallback = state.aiThreads[0];
    return ensureSession(state, state.activeAiThreadId || fallback.id, fallback.title);
  }

  function isNearChatBottom() {
    const node = els.aiChatThread;
    if (!node) return true;
    return node.scrollHeight - (node.scrollTop + node.clientHeight) <= CHAT_FOLLOW_THRESHOLD;
  }

  function getScrollToBottomLabel(session) {
    if (session.hasUnreadChatBelow) {
      return "有新回复，回到底部";
    }
    return "回到底部";
  }

  function updateChatFollowState({ persist = false } = {}) {
    const session = getActiveThread();
    const nearBottom = isNearChatBottom();
    session.autoFollowChat = nearBottom;
    if (nearBottom) {
      session.hasUnreadChatBelow = false;
    }
    session.scrollOffset = els.aiChatThread?.scrollTop || 0;
    if (els.aiChatScrollToBottomButton) {
      els.aiChatScrollToBottomButton.hidden = nearBottom || !session.messages?.length;
      els.aiChatScrollToBottomButton.textContent = getScrollToBottomLabel(session);
      els.aiChatScrollToBottomButton.classList.toggle("has-unread", !!session.hasUnreadChatBelow && !nearBottom);
    }
    if (persist) {
      persistSessions(state);
    }
    return nearBottom;
  }

  function scrollChatToBottom({ behavior = "auto", markRead = true, persist = false } = {}) {
    const session = getActiveThread();
    const node = els.aiChatThread;
    if (!node) return;
    if (behavior === "smooth") {
      node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    } else {
      node.scrollTop = node.scrollHeight;
    }
    session.scrollOffset = node.scrollTop;
    session.autoFollowChat = true;
    if (markRead) {
      session.hasUnreadChatBelow = false;
    }
    if (els.aiChatScrollToBottomButton) {
      els.aiChatScrollToBottomButton.hidden = true;
      els.aiChatScrollToBottomButton.textContent = getScrollToBottomLabel(session);
      els.aiChatScrollToBottomButton.classList.remove("has-unread");
    }
    if (persist) {
      persistSessions(state);
    }
  }

  function restoreChatScroll(session) {
    if (!els.aiChatThread) {
      return;
    }
    if (session.autoFollowChat !== false) {
      scrollChatToBottom({ behavior: "auto", markRead: true, persist: false });
      return;
    }
    els.aiChatThread.scrollTop = session.scrollOffset || 0;
    if (els.aiChatScrollToBottomButton) {
      els.aiChatScrollToBottomButton.hidden = !session.messages?.length;
      els.aiChatScrollToBottomButton.textContent = getScrollToBottomLabel(session);
      els.aiChatScrollToBottomButton.classList.toggle("has-unread", !!session.hasUnreadChatBelow);
    }
  }

  function bindChatScrollBehavior() {
    els.aiChatThread?.addEventListener("scroll", () => {
      updateChatFollowState({ persist: false });
    });
    els.aiChatScrollToBottomButton?.addEventListener("click", () => {
      scrollChatToBottom({ behavior: "smooth", markRead: true, persist: true });
    });
  }

  function bindThreadTabsOverflowBehavior() {
    const node = els.aiThreadTabs;
    if (!node || node.dataset.scrollBound === "true") {
      return;
    }
    node.dataset.scrollBound = "true";
    node.addEventListener("wheel", (event) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
        return;
      }
      if (node.scrollWidth <= node.clientWidth + 4) {
        return;
      }
      node.scrollLeft += event.deltaY;
      event.preventDefault();
    }, { passive: false });
  }

  function buildSessionWorkspaceCardMarkup(session) {
    const scope = getSessionScope(session, state);
    const active = session.id === state.activeAiThreadId;
    const attachments = getDraftAttachments(session);
    const preview = getSessionPreviewText(session);
    const updatedLabel = formatSessionUpdatedLabel(session);
    const chips = [];
    if (active) {
      chips.push(`<span class="session-workspace-chip active">当前</span>`);
    }
    if (session.pinned) {
      chips.push(`<span class="session-workspace-chip">固定</span>`);
    }
    if (session.activePlanId) {
      chips.push(`<span class="session-workspace-chip emphasis">主计划</span>`);
    }
    if (session.mountedReplyIds?.length) {
      chips.push(`<span class="session-workspace-chip">上图 ${escapeHtml(String(session.mountedReplyIds.length))}</span>`);
    }
    if ((session.unreadCount || 0) > 0) {
      chips.push(`<span class="session-workspace-chip warn">未读 ${escapeHtml(String(session.unreadCount))}</span>`);
    }
    if (String(session.draftText || session.draft || "").trim()) {
      chips.push(`<span class="session-workspace-chip good">草稿中</span>`);
    }
    if (attachments.length) {
      chips.push(`<span class="session-workspace-chip">附件 ${escapeHtml(String(attachments.length))}</span>`);
    }
    return `
      <article class="session-workspace-card ${active ? "active" : ""}" data-session-card="${escapeHtml(session.id)}">
        <button type="button" class="session-workspace-card-main" data-session-open="${escapeHtml(session.id)}">
          <div class="session-workspace-card-head">
            <strong class="session-workspace-card-title">${escapeHtml(session.title || scope.symbol || "会话")}</strong>
            <span class="session-workspace-card-time">${escapeHtml(updatedLabel ? `更新 ${updatedLabel}` : "")}</span>
          </div>
          <div class="session-workspace-card-meta">${escapeHtml(`${scope.symbol} · ${scope.timeframe} · ${scope.windowRange}`)}</div>
          <div class="session-workspace-card-preview">${escapeHtml(preview)}</div>
          ${chips.length ? `<div class="session-workspace-card-chips">${chips.join("")}</div>` : ""}
        </button>
        <div class="session-workspace-card-actions">
          <button type="button" class="secondary tiny" data-session-pin="${escapeHtml(session.id)}">${session.pinned ? "取消固定" : "固定"}</button>
          <button type="button" class="secondary tiny" data-session-clone="${escapeHtml(session.id)}">复制分支</button>
          <button type="button" class="secondary tiny" data-session-archive="${escapeHtml(session.id)}">归档</button>
        </div>
      </article>
    `;
  }

  function buildSessionWorkspaceSectionMarkup(title, sessions, emptyNote = "") {
    if (!sessions.length) {
      return emptyNote
        ? `
          <section class="session-workspace-section">
            <div class="session-workspace-section-head">
              <strong>${escapeHtml(title)}</strong>
            </div>
            <div class="session-workspace-empty">${escapeHtml(emptyNote)}</div>
          </section>
        `
        : "";
    }
    return `
      <section class="session-workspace-section">
        <div class="session-workspace-section-head">
          <strong>${escapeHtml(title)}</strong>
          <span class="meta">${escapeHtml(`${sessions.length} 条`)}</span>
        </div>
        <div class="session-workspace-list">
          ${sessions.map((session) => buildSessionWorkspaceCardMarkup(session)).join("")}
        </div>
      </section>
    `;
  }

  function renderSessionMoreMenu() {
    if (!els.sessionMoreMenu) {
      return;
    }
    const activeSession = getActiveThread();
    const activeScope = getSessionScope(activeSession, state);
    const normalizedQuery = String(sessionWorkspaceQuery || "").trim().toLowerCase();
    const visibleSessions = [...listSessionsByRole("analyst")]
      .filter((session) => session.status !== "archived")
      .filter((session) => shouldSurfaceSession(session))
      .filter((session) => !normalizedQuery || buildSessionSearchText(session).includes(normalizedQuery))
      .sort((a, b) => compareSessionsByPriority(a, b, { preferredSymbol: activeScope.symbol }));
    const currentSymbolSessions = visibleSessions.filter((session) => getSessionScope(session, state).symbol === activeScope.symbol);
    const otherSymbolGroups = new Map();
    visibleSessions
      .filter((session) => getSessionScope(session, state).symbol !== activeScope.symbol)
      .forEach((session) => {
        const symbol = getSessionScope(session, state).symbol;
        if (!otherSymbolGroups.has(symbol)) {
          otherSymbolGroups.set(symbol, []);
        }
        otherSymbolGroups.get(symbol).push(session);
      });
    const otherSymbolMarkup = Array.from(otherSymbolGroups.entries())
      .sort((a, b) => a[0].localeCompare(b[0], "zh-Hans-CN"))
      .map(([symbol, sessions]) => buildSessionWorkspaceSectionMarkup(`其他品种 · ${symbol}`, sessions))
      .join("");

    els.sessionMoreMenu.innerHTML = `
      <div class="session-workspace-shell">
        <div class="session-workspace-toolbar">
          <div class="session-workspace-search">
            <input
              type="search"
              class="session-workspace-search-input"
              data-session-search-input="true"
              placeholder="搜索会话 / 品种 / 摘要"
              value="${escapeHtml(sessionWorkspaceQuery)}"
            >
            <button type="button" class="secondary tiny" data-session-command="clear-search">清空</button>
          </div>
          <div class="button-row tight">
            <button type="button" class="secondary tiny" data-session-command="clone">复制当前分支</button>
            <button type="button" class="secondary tiny" data-session-command="archive">归档当前会话</button>
            <button type="button" class="secondary tiny" data-session-command="close">收起</button>
          </div>
        </div>
        <div class="session-workspace-summary">
          <span>${escapeHtml(`当前品种 ${activeScope.symbol}`)}</span>
          <span class="meta">${escapeHtml(`共 ${visibleSessions.length} 条结果`)}</span>
        </div>
        ${visibleSessions.length
          ? `
            ${buildSessionWorkspaceSectionMarkup(`当前品种 · ${activeScope.symbol}`, currentSymbolSessions, "当前品种下还没有命中的会话。")}
            ${otherSymbolMarkup || ""}
          `
          : `<div class="session-workspace-empty">没有匹配的会话。可尝试按品种、标题或摘要搜索。</div>`}
      </div>
    `;

    const searchInput = els.sessionMoreMenu.querySelector("[data-session-search-input]");
    searchInput?.addEventListener("input", () => {
      sessionWorkspaceQuery = searchInput.value || "";
      renderSessionMoreMenu();
      const nextInput = els.sessionMoreMenu.querySelector("[data-session-search-input]");
      nextInput?.focus();
      nextInput?.setSelectionRange(sessionWorkspaceQuery.length, sessionWorkspaceQuery.length);
    });

    els.sessionMoreMenu.querySelectorAll("button[data-session-open]").forEach((button) => {
      button.addEventListener("click", () => {
        const threadId = button.dataset.sessionOpen;
        if (!threadId) {
          return;
        }
        setActiveThread(threadId);
        els.sessionMoreMenu.hidden = true;
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-pin]").forEach((button) => {
      button.addEventListener("click", () => {
        const threadId = button.dataset.sessionPin;
        if (!threadId) {
          return;
        }
        toggleThreadPin(threadId);
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-clone]").forEach((button) => {
      button.addEventListener("click", async () => {
        const threadId = button.dataset.sessionClone;
        if (!threadId) {
          return;
        }
        await cloneActiveThreadBranch(threadId);
        els.sessionMoreMenu.hidden = true;
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-archive]").forEach((button) => {
      button.addEventListener("click", () => {
        const threadId = button.dataset.sessionArchive;
        if (!threadId || !window.confirm("确认归档这个会话？")) {
          return;
        }
        archiveThread(threadId);
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-command='clear-search']").forEach((button) => {
      button.addEventListener("click", () => {
        sessionWorkspaceQuery = "";
        renderSessionMoreMenu();
        els.sessionMoreMenu.querySelector("[data-session-search-input]")?.focus();
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-command='close']").forEach((button) => {
      button.addEventListener("click", () => {
        els.sessionMoreMenu.hidden = true;
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-command='clone']").forEach((button) => {
      button.addEventListener("click", async () => {
        await cloneActiveThreadBranch();
        els.sessionMoreMenu.hidden = true;
      });
    });
    els.sessionMoreMenu.querySelectorAll("button[data-session-command='archive']").forEach((button) => {
      button.addEventListener("click", () => {
        if (!window.confirm("确认归档当前会话？")) {
          return;
        }
        archiveActiveThread();
        els.sessionMoreMenu.hidden = true;
      });
    });
  }

  function renderAttachments(session) {
    if (!els.attachmentPreviewBar || !els.attachmentPreviewList) {
      return;
    }
    const attachments = getDraftAttachments(session);
    if (!attachments.length) {
      session.attachmentPreviewCollapsed = false;
    }
    const collapsed = !!session.attachmentPreviewCollapsed && attachments.length > 0;
    const summaryText = buildAttachmentSummary(attachments);
    els.attachmentPreviewBar.hidden = attachments.length === 0;
    els.attachmentPreviewBar.classList.toggle("is-collapsed", collapsed);
    if (els.attachmentPreviewMeta) {
      els.attachmentPreviewMeta.textContent = summaryText;
    }
    if (els.toggleAttachmentPreviewButton) {
      els.toggleAttachmentPreviewButton.disabled = attachments.length === 0;
      els.toggleAttachmentPreviewButton.textContent = collapsed ? "展开" : "折叠";
      els.toggleAttachmentPreviewButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
      els.toggleAttachmentPreviewButton.onclick = () => {
        if (!attachments.length) {
          return;
        }
        session.attachmentPreviewCollapsed = !session.attachmentPreviewCollapsed;
        persistSessions(state);
        renderAttachments(session);
      };
    }
    if (els.clearAttachmentsButton) {
      els.clearAttachmentsButton.disabled = attachments.length === 0;
    }
    if (els.attachmentPreviewCollapsedSummary) {
      els.attachmentPreviewCollapsedSummary.hidden = !collapsed;
      els.attachmentPreviewCollapsedSummary.innerHTML = collapsed ? buildAttachmentCollapsedSummaryMarkup(attachments) : "";
    }
    els.attachmentPreviewList.hidden = collapsed;
    els.attachmentPreviewList.innerHTML = attachments.map((item, index) => `
      <div class="attachment-row">
        ${buildAttachmentPreviewMarkup(item)}
        <div class="attachment-row-main">
          <span class="attachment-row-title">${escapeHtml(item.name || `附件${index + 1}`)}</span>
          <div class="button-row tight">
            <span class="meta">${escapeHtml([item.kind || item.media_type || "file", formatAttachmentSize(item.size)].filter(Boolean).join(" · "))}</span>
            <button type="button" class="secondary tiny" data-attachment-remove="${index}">删除</button>
          </div>
        </div>
      </div>
    `).join("");
    els.attachmentPreviewList.querySelectorAll("button[data-attachment-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        attachments.splice(Number(button.dataset.attachmentRemove), 1);
        setDraftAttachments(session, attachments);
        renderAttachments(session);
        persistSessions(state);
        scheduleDraftStateSync(session);
      });
    });
  }

  async function hydrateSessionFromServer(sessionId, { activate = false } = {}) {
    if (!fetchJson) {
      return getSessionById(state, sessionId);
    }
    const fallback = getSessionById(state, sessionId) || null;
    const localDraftText = fallback?.draftText ?? fallback?.draft ?? "";
    const localDraftAttachments = fallback ? getDraftAttachments(fallback) : [];
    const localSelectedPromptBlockIds = Array.isArray(fallback?.selectedPromptBlockIds) ? [...fallback.selectedPromptBlockIds] : [];
    const localMountedReplyIds = Array.isArray(fallback?.mountedReplyIds) ? [...fallback.mountedReplyIds] : [];
    const sessionEnvelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}`);
    const serverSession = sessionEnvelope?.session;
    if (!serverSession) {
      return fallback;
    }
    const thread = mapServerSessionToThread(serverSession, fallback || {});
    if (fallback) {
      if (localDraftText) {
        thread.draftText = localDraftText;
        thread.draft = localDraftText;
      }
      if (localDraftAttachments.length) {
        setDraftAttachments(thread, localDraftAttachments);
      }
      if (localSelectedPromptBlockIds.length) {
        thread.selectedPromptBlockIds = localSelectedPromptBlockIds;
      }
      if (localMountedReplyIds.length) {
        thread.mountedReplyIds = localMountedReplyIds;
      }
    }
    const messagesEnvelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
    const memoryEnvelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}/memory`);
    thread.memory = {
      ...(thread.memory || {}),
      ...(memoryEnvelope?.memory || {}),
    };

    const messages = Array.isArray(messagesEnvelope?.messages) ? messagesEnvelope.messages : [];
    const planCardsByMessage = new Map();
    const annotations = [];
    for (const message of messages) {
      const messageId = message.message_id || message.id;
      if (!messageId) continue;
      try {
        const objects = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/objects`);
        const plans = Array.isArray(objects?.plan_cards) ? objects.plan_cards.map((item) => mapServerPlanCard(item, sessionId, messageId)) : [];
        planCardsByMessage.set(messageId, plans);
        if (Array.isArray(objects?.annotations)) {
          annotations.push(...objects.annotations.map((item) => applyAnnotationPreferences({
            ...item,
            id: item.annotation_id || item.id,
            annotation_id: item.annotation_id || item.id || null,
            object_id: item.object_id || item.annotation_id || item.id || null,
            session_id: item.session_id || sessionId,
            message_id: item.message_id || messageId,
            visible: item.visible !== false,
            pinned: !!item.pinned,
            deleted: !!item.deleted,
          }, state.annotationPreferences || {}, {
            sessionId: item.session_id || sessionId,
            messageId: item.message_id || messageId,
            planId: item.plan_id || null,
          })));
        }
      } catch (error) {
        console.warn("加载会话对象失败:", error);
      }
    }
    thread.messages = messages.map((message) => mapServerMessage(message, planCardsByMessage));
    thread.turns = thread.messages.map((item) => ({ role: item.role, content: item.content, meta: item.meta || {} }));
    thread.backendLoaded = true;
    const existingIndex = state.aiThreads.findIndex((item) => item.id === thread.id || item.sessionId === thread.sessionId);
    if (existingIndex >= 0) {
      state.aiThreads.splice(existingIndex, 1, thread);
    } else {
      state.aiThreads.push(thread);
    }
    state.aiAnnotations = [
      ...(state.aiAnnotations || []).filter((item) => item.session_id !== thread.id),
      ...annotations,
    ];
    if (activate) {
      state.activeAiThreadId = thread.id;
      onSessionActivated?.(thread);
    }
    thread.loadingFromServer = false;
    persistSessions(state);
    return thread;
  }

  async function syncSessionsFromServer({ activateFirst = false, symbol = null, includeArchived = false, workspaceRole = null } = {}) {
    if (!fetchJson) {
      return state.aiThreads;
    }
    const queryParts = [];
    if (symbol) {
      queryParts.push(`symbol=${encodeURIComponent(symbol)}`);
    }
    if (includeArchived) {
      queryParts.push("include_archived=true");
    }
    const query = queryParts.length ? `?${queryParts.join("&")}` : "";
    const envelope = await fetchJson(`/api/v1/workbench/chat/sessions${query}`);
    const sessions = Array.isArray(envelope?.sessions) ? envelope.sessions : [];
    const normalizedSymbol = symbol ? String(symbol).trim().toUpperCase() : null;
    /** 同一 session_id 只保留一条，避免接口重复行导致前端会话爆炸 */
    const mappedById = new Map();
    sessions.forEach((item) => {
      const sessionId = item.session_id || item.id;
      if (!sessionId) {
        return;
      }
      const fallback = state.aiThreads.find((existing) => existing.id === sessionId || existing.sessionId === sessionId) || {};
      mappedById.set(sessionId, mapServerSessionToThread(item, fallback));
    });
    const mapped = Array.from(mappedById.values());
    const mappedIds = new Set(mapped.map((item) => item.id || item.sessionId));
    const syntheticThreads = state.aiThreads.filter((item) => isSyntheticSessionId(item.id));
    const preservedThreads = state.aiThreads.filter((item) => {
      if (isSyntheticSessionId(item.id)) {
        return false;
      }
      if (!normalizedSymbol) {
        return false;
      }
      const scope = getSessionScope(item, state);
      return scope.symbol !== normalizedSymbol && !mappedIds.has(item.id || item.sessionId);
    });
    state.aiThreads = [
      ...preservedThreads,
      ...mapped,
      ...syntheticThreads.filter((item) => !mapped.some((mappedItem) => mappedItem.id === item.id || mappedItem.sessionId === item.sessionId)),
    ];
    if (activateFirst && state.aiThreads.length) {
      const currentId = state.activeAiThreadId;
      const currentSession = currentId ? getSessionById(state, currentId) : null;
      const preferredRole = workspaceRole || getWorkspaceRole(currentSession);
      const next = state.aiThreads.find((item) => item.id === currentId)
        || (normalizedSymbol ? getPreferredSessionForSymbol(normalizedSymbol, { workspaceRole: preferredRole }) : null)
        || [...state.aiThreads].sort((a, b) => compareSessionsByPriority(a, b))[0];
      if (!next) {
        persistSessions(state);
        return state.aiThreads;
      }
      state.activeAiThreadId = next.id;
      if (!next.backendLoaded) {
        await hydrateSessionFromServer(next.id, { activate: true });
      } else {
        onSessionActivated?.(next);
      }
    }
    persistSessions(state);
    return state.aiThreads;
  }

  function setActiveThread(threadId, title = "01", overrides = {}) {
    const previousSession = state.activeAiThreadId ? getSessionById(state, state.activeAiThreadId) : null;
    if (previousSession && previousSession.id !== threadId) {
      scheduleDraftStateSync(previousSession, { immediate: true });
    }
    const session = ensureSession(state, threadId, title, overrides);
    state.activeAiThreadId = session.id;
    els.aiChatInput.value = session.draftText || session.draft || "";
    if (session.analysisTemplate) {
      if (els.analysisTypeSelect) els.analysisTypeSelect.value = session.analysisTemplate.type || els.analysisTypeSelect.value;
      if (els.analysisRangeSelect) els.analysisRangeSelect.value = session.analysisTemplate.range || els.analysisRangeSelect.value;
      if (els.analysisStyleSelect) els.analysisStyleSelect.value = session.analysisTemplate.style || els.analysisStyleSelect.value;
    }
    if (els.aiModelOverride) {
      els.aiModelOverride.value = session.activeModel || "";
    }
    renderAiThreadTabs();
    renderAiChat();
    renderAttachments(session);
    persistSessions(state);
    if (fetchJson && !session.backendLoaded) {
      if (isSyntheticSessionId(session.id)) {
        onSessionActivated?.(session);
        return session;
      }
      session.loadingFromServer = true;
      renderAiChat();
      hydrateSessionFromServer(session.id, { activate: true })
        .then((hydrated) => {
          if (hydrated) {
            hydrated.loadingFromServer = false;
            if (state.activeAiThreadId === hydrated.id) {
              els.aiChatInput.value = hydrated.draftText || hydrated.draft || "";
            }
            renderAiThreadTabs();
            renderAiChat();
            renderAttachments(hydrated);
          }
        })
        .catch((error) => {
          session.loadingFromServer = false;
          console.warn("加载会话失败:", error);
          renderStatusStrip?.([{ label: error.message || String(error), variant: "warn" }]);
          renderAiThreadTabs();
          renderAiChat();
          renderAttachments(session);
        });
    } else {
      onSessionActivated?.(session);
    }
    return session;
  }

  function createThread(title = null, overrides = {}) {
    const ordinal = String(state.aiThreads.length + 1).padStart(2, "0");
    return setActiveThread(`session-${ordinal}`, title || ordinal, overrides);
  }

  async function createBackendSession({ title = "新会话", symbol = null, contractId = null, timeframe = null, windowRange = null, activate = true, workspaceRole = "analyst" } = {}) {
    if (!fetchJson) {
      return createThread(title, { symbol, contractId, timeframe, windowRange, workspaceRole });
    }
    const sessionSymbol = symbol || state.topBar?.symbol || "NQ";
    const sessionTimeframe = timeframe || state.topBar?.timeframe || "1m";
    const end = new Date();
    const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
    const envelope = await fetchJson("/api/v1/workbench/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace_id: "replay_main",
        title,
        symbol: sessionSymbol,
        contract_id: contractId || sessionSymbol,
        timeframe: sessionTimeframe,
        window_range: {
          start: start.toISOString(),
          end: end.toISOString(),
        },
        active_model: els.aiModelOverride?.value?.trim() || null,
        start_blank: true,
      }),
    });
    const serverSession = envelope?.session;
    if (!serverSession) {
      throw new Error("创建会话失败");
    }
    const thread = mapServerSessionToThread(serverSession, {
      symbol: sessionSymbol,
      contractId: contractId || sessionSymbol,
      timeframe: sessionTimeframe,
      windowRange,
      workspaceRole,
    });
    thread.backendLoaded = false;
    const existingIndex = state.aiThreads.findIndex((item) => item.id === thread.id || item.sessionId === thread.sessionId);
    if (existingIndex >= 0) {
      state.aiThreads.splice(existingIndex, 1, thread);
    } else {
      state.aiThreads.push(thread);
    }
    persistSessions(state);
    if (activate) {
      return setActiveThread(thread.id, thread.title, thread);
    }
    return thread;
  }

  async function materializeSyntheticSession(session, { activate = true } = {}) {
    if (!fetchJson || !session || !isSyntheticSessionId(session.id)) {
      return session;
    }
    const localDraftText = session.draftText || session.draft || "";
    const localDraftAttachments = getDraftAttachments(session);
    const localAnalysisTemplate = session.analysisTemplate ? { ...session.analysisTemplate } : null;
    const localPinned = !!session.pinned;
    const localTitle = session.title || "新会话";
    const localScope = getSessionScope(session, state);
    const localRole = getWorkspaceRole(session);

    state.aiThreads = state.aiThreads.filter((item) => item.id !== session.id);
    if (state.activeAiThreadId === session.id) {
      state.activeAiThreadId = null;
    }

    const created = await createBackendSession({
      title: localTitle,
      symbol: localScope.symbol,
      contractId: localScope.contractId,
      timeframe: localScope.timeframe,
      windowRange: localScope.windowRange,
      activate,
      workspaceRole: localRole,
    });

    if (created) {
      created.pinned = localPinned;
      if (localAnalysisTemplate) {
        created.analysisTemplate = {
          ...created.analysisTemplate,
          ...localAnalysisTemplate,
        };
      }
      if (localDraftText) {
        created.draftText = localDraftText;
        created.draft = localDraftText;
      }
      if (localDraftAttachments.length) {
        setDraftAttachments(created, localDraftAttachments);
      }
      scheduleDraftStateSync(created, { immediate: true });
      persistSessions(state);
    }
    return created;
  }

  const getOrCreateBlankSessionForSymbol = (symbol, contractId = symbol, options = {}) => {
    const normalizedSymbol = String(symbol || "").trim().toUpperCase() || "NQ";
    const normalizedRole = getWorkspaceRole({ workspaceRole: options.workspaceRole || "analyst" });
    const activate = options.activate !== false;
    const existing = state.aiThreads.find((thread) => {
      const scope = getSessionScope(thread, state);
      return scope.symbol === normalizedSymbol
        && getWorkspaceRole(thread) === normalizedRole
        && isTrulyBlankSession(thread);
    });
    if (existing) {
      if (fetchJson && isSyntheticSessionId(existing.id)) {
        return materializeSyntheticSession(existing, { activate });
      }
      return activate
        ? setActiveThread(existing.id, existing.title, { symbol: normalizedSymbol, contractId, workspaceRole: normalizedRole })
        : normalizeSessionShape(existing, { symbol: normalizedSymbol, contractId, workspaceRole: normalizedRole });
    }
    const titlePrefix = normalizedRole === "scribe" ? `${normalizedSymbol}-事件` : normalizedSymbol;
    const title = `${titlePrefix}-${String(state.aiThreads.filter((thread) => {
      const scope = getSessionScope(thread, state);
      return scope.symbol === normalizedSymbol && getWorkspaceRole(thread) === normalizedRole;
    }).length + 1).padStart(2, "0")}`;
    if (fetchJson) {
      return createBackendSession({
        title,
        symbol: normalizedSymbol,
        contractId,
        timeframe: state.topBar?.timeframe || "1m",
        windowRange: state.topBar?.quickRange || "最近7天",
        activate,
        workspaceRole: normalizedRole,
      });
    }
    return createThread(title, {
      symbol: normalizedSymbol,
      contractId,
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
      workspaceRole: normalizedRole,
    });
  };

  /** 下一个行情分析会话标题（NQ-03），按当前品种下同角色会话数量递增 */
  function buildNextAnalystSessionTitle(normalizedSymbol) {
    const sym = String(normalizedSymbol || "NQ").trim().toUpperCase() || "NQ";
    const count = state.aiThreads.filter((thread) => {
      const scope = getSessionScope(thread, state);
      return scope.symbol === sym
        && getWorkspaceRole(thread) === "analyst"
        && shouldSurfaceSession(thread);
    }).length;
    return `${sym}-${String(count + 1).padStart(2, "0")}`;
  }

  /** 始终新建一条行情分析会话（用于「+」与底部「新会话」，不复用空白会话） */
  async function createNewAnalystSession({ activate = true } = {}) {
    const normalizedSymbol = String(
      state.topBar?.symbol || getSessionScope(getActiveThread(), state).symbol || "NQ",
    ).trim().toUpperCase() || "NQ";
    const title = buildNextAnalystSessionTitle(normalizedSymbol);
    if (fetchJson) {
      return createBackendSession({
        title,
        symbol: normalizedSymbol,
        contractId: normalizedSymbol,
        timeframe: state.topBar?.timeframe || "1m",
        windowRange: state.topBar?.quickRange || "最近7天",
        activate,
        workspaceRole: "analyst",
      });
    }
    return createThread(title, {
      symbol: normalizedSymbol,
      contractId: normalizedSymbol,
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
      workspaceRole: "analyst",
    });
  }

  function renderAiThreadTabs() {
    if (!els.aiThreadTabs) return;
    bindThreadTabsOverflowBehavior();
    els.aiThreadTabs.innerHTML = "";
    const currentScope = getSessionScope(getActiveThread(), state);
    const currentSymbol = currentScope.symbol;
    const relevantThreads = listSessionsByRole("analyst").filter((thread) => {
      const threadScope = getSessionScope(thread, state);
      return threadScope.symbol === currentSymbol && shouldSurfaceSession(thread);
    }).sort((a, b) => compareSessionsByPriority(a, b, { preferredSymbol: currentSymbol }));
    const canArchiveFromTabs = relevantThreads.length > 1;
    relevantThreads.forEach((thread, index) => {
      const wrap = document.createElement("div");
      wrap.className = `thread-tab-wrap ${canArchiveFromTabs ? "" : "single-visible"}`.trim();
      const button = document.createElement("button");
      button.type = "button";
      const hasDraft = hasSessionDraft(thread);
      button.className = `thread-tab ${thread.id === state.activeAiThreadId ? "active" : ""} ${thread.pinned ? "pinned" : ""} ${hasDraft ? "drafting" : ""}`.trim();
      const displayLabel = `${currentSymbol} · ${String(index + 1).padStart(2, "0")}`;
      button.textContent = displayLabel;
      button.title = [
        thread.title || displayLabel,
        thread.pinned ? "固定会话" : "",
        hasDraft ? "草稿中" : "",
        getSessionScope(thread, state).timeframe,
        getSessionPreviewText(thread),
        String(thread.id || "").slice(0, 12),
      ].filter(Boolean).join(" · ");
      button.addEventListener("click", () => setActiveThread(thread.id, thread.title));
      const closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "thread-tab-close";
      closeBtn.setAttribute("aria-label", "删除会话");
      closeBtn.textContent = "×";
      closeBtn.title = "删除此会话";
      closeBtn.hidden = !canArchiveFromTabs;
      closeBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        event.preventDefault();
        if (!window.confirm("确认归档并删除此聊天会话？")) {
          return;
        }
        archiveThread(thread.id);
      });
      wrap.appendChild(button);
      wrap.appendChild(closeBtn);
      els.aiThreadTabs.appendChild(wrap);
    });
    const addWrap = document.createElement("div");
    addWrap.className = "thread-tab-add-wrap";
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "thread-tab thread-tab-add";
    addBtn.textContent = "+";
    addBtn.title = "新建行情分析会话";
    addBtn.setAttribute("aria-label", "新建行情分析会话");
    addBtn.addEventListener("click", async () => {
      try {
        await createNewAnalystSession({ activate: true });
      } catch (error) {
        console.warn("新建会话失败:", error);
        renderStatusStrip?.([{ label: error?.message || String(error), variant: "warn" }]);
      }
    });
    addWrap.appendChild(addBtn);
    els.aiThreadTabs.appendChild(addWrap);
    window.requestAnimationFrame(() => {
      const activeTab = els.aiThreadTabs?.querySelector(".thread-tab.active");
      activeTab?.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    renderSessionMoreMenu();
  }

  function appendAiChatMessage(role, content, meta = {}, threadId = null, threadTitle = "01") {
    const session = ensureSession(state, threadId || state.activeAiThreadId, threadTitle);
    const activeDraftAttachments = getDraftAttachments(session);
    const mergedMeta = {
      ...meta,
      attachments: normalizeAttachmentList(meta.attachments || (role === "user" ? activeDraftAttachments : [])),
    };
    const message = {
      message_id: createMessageId(),
      sessionId: session.id,
      role,
      content,
      status: mergedMeta.status || (role === "assistant" ? "completed" : "sent"),
      replyTitle: mergedMeta.replyTitle || mergedMeta.reply_title || null,
      model: mergedMeta.model || null,
      annotations: Array.isArray(mergedMeta.annotations) ? mergedMeta.annotations : [],
      planCards: Array.isArray(mergedMeta.planCards) ? mergedMeta.planCards : [],
      mountedToChart: !!mergedMeta.mountedToChart,
      mountedObjectIds: Array.isArray(mergedMeta.mountedObjectIds) ? mergedMeta.mountedObjectIds : [],
      meta: mergedMeta,
      created_at: new Date().toISOString(),
    };
    session.messages.push(message);
    session.turns.push({ role, content, meta: mergedMeta });
    if (role === "user") {
      session.draft = "";
      session.draftText = "";
      setDraftAttachments(session, []);
      session.memory.latest_question = content;
      session.memory.current_user_intent = summarizeText(content, 80);
      scheduleDraftStateSync(session, { immediate: true });
    } else {
      session.memory.latest_answer_summary = summarizeText(content, 160);
      session.memory.important_messages = session.messages.slice(-4).map((item) => summarizeText(item.content, 80));
    }
    session.memory.last_updated_at = new Date().toISOString();
    session.updatedAt = session.memory.last_updated_at;
    renderAiChat();
    renderAiThreadTabs();
    renderAttachments(session);
    persistSessions(state);
    return message;
  }

  function syncSessionMemorySummary(session) {
    els.currentSessionTitle.textContent = `会话：${session.title}`;
    const latestAssistant = [...(session.messages || [])].reverse().find((item) => item.role === "assistant") || null;
    const latestModeLabel = latestAssistant?.meta?.session_only ? "session-only" : "replay-aware";
    els.currentSessionModelLabel.textContent = `模型：${session.activeModel || session.memory?.active_model || "服务端默认"} / ${latestModeLabel}`;
    const memory = session.memory || {};
    const summaryParts = [
      memory.current_user_intent,
      memory.latest_answer_summary,
      Array.isArray(memory.active_plans_summary) && memory.active_plans_summary.length
        ? `活动计划：${memory.active_plans_summary.join("；")}`
        : "",
    ].filter(Boolean);
    const summaryText = summaryParts.join(" | ");
    els.sessionMemorySummary.hidden = !summaryText;
    els.sessionMemorySummary.textContent = summaryText || "";
  }

  function renderAiChat() {
    const session = getActiveThread();
    const shouldAutoFollow = session.autoFollowChat !== false || isNearChatBottom();
    const expandedLongTextMessageIds = new Set(getExpandedLongTextMessageIds(session));
    syncSessionMemorySummary(session);
    renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson, onPromptBlocksChanged);
    renderAttachments(session);
    if (session.loadingFromServer) {
      els.aiChatThread.innerHTML = `<div class="chat-empty-state">正在从后端加载会话内容…</div>`;
      if (els.aiChatScrollToBottomButton) {
        els.aiChatScrollToBottomButton.hidden = true;
        els.aiChatScrollToBottomButton.textContent = getScrollToBottomLabel(session);
        els.aiChatScrollToBottomButton.classList.remove("has-unread");
      }
      return;
    }
    if (!session.messages.length) {
      els.aiChatThread.innerHTML = `<div class="chat-empty-state">还没有消息。可直接发送；需要图表分析时先加载图表。</div>`;
      if (els.aiChatScrollToBottomButton) {
        els.aiChatScrollToBottomButton.hidden = true;
        els.aiChatScrollToBottomButton.textContent = getScrollToBottomLabel(session);
        els.aiChatScrollToBottomButton.classList.remove("has-unread");
      }
      return;
    }
    els.aiChatThread.innerHTML = session.messages.map((message) => renderMessage({
      ...message,
      meta: {
        ...(message.meta || {}),
        annotationCount: (state.aiAnnotations || []).filter((annotation) => annotation.session_id === session.id && annotation.message_id === message.message_id).length,
        planCards: Array.isArray(message.planCards) && message.planCards.length ? message.planCards : message.meta?.planCards,
      },
    }, {
      expandedLongText: expandedLongTextMessageIds.has(String(message.message_id || "")),
    })).join("");
    els.aiChatThread.querySelectorAll("button[data-plan-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const planId = button.dataset.planId;
        const action = button.dataset.planAction;
        const messageNode = button.closest(".chat-message");
        const messageId = messageNode?.dataset.messageId || null;
        if (action === "pin") {
          state.pinnedPlanId = planId;
          session.activePlanId = planId || null;
          persistSessions(state);
          if (messageId) {
            onPlanAction?.({ action: "show", planId, messageId, sessionId: session.id });
          }
          renderAiChat();
          return;
        }
        if (action === "copy") {
          const { plan } = findPlanInSession(session, planId);
          const summary = plan ? buildPlanStructuredSummary(plan) : "";
          if (summary && navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(summary)
              .then(() => {
                onPlanMetaAction?.({
                  type: "copy",
                  ok: true,
                  plan,
                  planId,
                  summary,
                  session,
                });
              })
              .catch((error) => {
                onPlanMetaAction?.({
                  type: "copy",
                  ok: false,
                  error,
                  plan,
                  planId,
                  summary,
                  session,
                });
              });
          } else {
            onPlanMetaAction?.({
              type: "copy",
              ok: false,
              error: new Error("当前环境不支持剪贴板写入"),
              plan,
              planId,
              summary,
              session,
            });
          }
          return;
        }
        if (action === "recap") {
          const { plan } = findPlanInSession(session, planId);
          if (plan) {
            const recapItem = upsertSessionRecapItem(session, buildPlanRecapItem(plan, session));
            persistSessions(state);
            onPlanMetaAction?.({
              type: "recap",
              ok: true,
              plan,
              summary: recapItem?.structuredSummary || "",
              recapItem,
              planId,
              session,
            });
          } else {
            onPlanMetaAction?.({
              type: "recap",
              ok: false,
              error: new Error("未找到对应计划卡"),
              plan: null,
              planId,
              session,
            });
          }
          return;
        }
        if (typeof onPlanAction === "function") {
          if (action === "focus") {
            session.activePlanId = planId || null;
            persistSessions(state);
          }
          onPlanAction({ action, planId, messageId, sessionId: session.id });
        }
      });
    });
    els.aiChatThread.querySelectorAll("button[data-longtext-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const block = button.closest("[data-longtext]");
        if (!block) return;
        const preview = block.querySelector(".longtext-preview");
        const full = block.querySelector(".longtext-full");
        const currentlyExpanded = button.dataset.longtextToggle === "collapse";
        const nextExpanded = !currentlyExpanded;
        const messageId = String(button.dataset.longtextMessageId || block.dataset.longtextMessageId || "").trim();
        if (preview) preview.hidden = nextExpanded;
        if (full) full.hidden = !nextExpanded;
        block.classList.toggle("is-expanded", nextExpanded);
        button.dataset.longtextToggle = nextExpanded ? "collapse" : "expand";
        button.textContent = nextExpanded ? "收起" : "展开全文";
        button.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
        if (messageId) {
          const nextIds = new Set(getExpandedLongTextMessageIds(session));
          if (nextExpanded) {
            nextIds.add(messageId);
          } else {
            nextIds.delete(messageId);
          }
          session.expandedLongTextMessageIds = Array.from(nextIds);
          persistSessions(state);
        }
      });
    });
    if (shouldAutoFollow) {
      scrollChatToBottom({ behavior: "auto", markRead: true, persist: false });
    } else {
      session.hasUnreadChatBelow = true;
      restoreChatScroll(session);
    }
  }

  function upsertPlanCardToSession(planCard, sessionId = null, messageId = null) {
    const session = ensureSession(state, sessionId || state.activeAiThreadId, getActiveThread().title);
    const normalized = mapServerPlanCard({
      ...planCard,
      id: planCard.id || planCard.plan_id || createPlanId(),
      plan_id: planCard.plan_id || planCard.id || null,
      message_id: messageId || planCard.message_id || null,
      session_id: session.id,
    }, session.id, messageId);
    session.memory.active_plans_summary = Array.from(new Set([...(session.memory.active_plans_summary || []), `${normalized.title} ${normalized.status}`]));
    persistSessions(state);
    return normalized;
  }

  async function cloneActiveThreadBranch(sourceThreadId = null) {
    const sourceSession = sourceThreadId ? getSessionById(state, sourceThreadId) : getActiveThread();
    if (!sourceSession) {
      return null;
    }
    const branchTitle = buildBranchTitle(sourceSession.title);
    const sourceScope = getSessionScope(sourceSession, state);
    const sourceMessages = clonePlainData(sourceSession.messages, []) || [];
    const sourceDraftAttachments = clonePlainData(getDraftAttachments(sourceSession), []) || [];
    const sourceMemory = clonePlainData(sourceSession.memory, {}) || {};
    const sourceAnalysisTemplate = clonePlainData(sourceSession.analysisTemplate, null);
    const sourceAnnotations = clonePlainData(
      (state.aiAnnotations || []).filter((item) => item.session_id === sourceSession.id),
      [],
    ) || [];

    let branchSession = fetchJson
      ? await createBackendSession({
          title: branchTitle,
          symbol: sourceScope.symbol,
          contractId: sourceScope.contractId,
          timeframe: sourceScope.timeframe,
          windowRange: sourceScope.windowRange,
          activate: false,
        })
      : createThread(branchTitle, sourceScope);

    if (!branchSession) {
      return null;
    }

    const messageIdMap = fetchJson
      ? await cloneMessagesToBackend(branchSession.id, sourceMessages)
      : new Map(sourceMessages.map((message, index) => [message.message_id, `${branchSession.id}-msg-${index + 1}`]));
    const planIdMap = new Map();
    sourceMessages.forEach((message, messageIndex) => {
      const plans = Array.isArray(message.meta?.planCards) ? message.meta.planCards : (Array.isArray(message.planCards) ? message.planCards : []);
      plans.forEach((plan, planIndex) => {
        const currentPlanId = plan?.id || plan?.plan_id;
        if (!currentPlanId || planIdMap.has(currentPlanId)) {
          return;
        }
        planIdMap.set(currentPlanId, `${branchSession.id}-plan-${messageIndex + 1}-${planIndex + 1}`);
      });
    });

    const clonedMessages = sourceMessages.map((message, messageIndex) => {
      const nextMessageId = messageIdMap.get(message.message_id) || `${branchSession.id}-msg-${messageIndex + 1}`;
      const clonedPlanCards = (Array.isArray(message.meta?.planCards) ? message.meta.planCards : (Array.isArray(message.planCards) ? message.planCards : []))
        .map((plan, planIndex) => {
          const mappedPlanId = planIdMap.get(plan?.id || plan?.plan_id) || `${branchSession.id}-plan-${messageIndex + 1}-${planIndex + 1}`;
          return {
            ...clonePlainData(plan, {}),
            id: mappedPlanId,
            plan_id: mappedPlanId,
            message_id: nextMessageId,
            session_id: branchSession.id,
          };
        });
      return {
        ...message,
        message_id: nextMessageId,
        parent_message_id: message.parent_message_id ? (messageIdMap.get(message.parent_message_id) || message.parent_message_id) : null,
        sessionId: branchSession.id,
        mountedToChart: false,
        mountedObjectIds: [],
        planCards: clonedPlanCards,
        meta: {
          ...(clonePlainData(message.meta, {}) || {}),
          attachments: clonePlainData(message.meta?.attachments, []) || [],
          planCards: clonedPlanCards,
          localPendingMessageId: undefined,
        },
      };
    });
    const clonedRecapItems = (clonePlainData(sourceSession.recapItems, []) || [])
      .map((item, index) => normalizeRecapItem({
        ...item,
        id: `${branchSession.id}-recap-${index + 1}`,
        planId: item?.planId || item?.plan_id
          ? (planIdMap.get(item.planId || item.plan_id) || null)
          : null,
        plan_id: item?.planId || item?.plan_id
          ? (planIdMap.get(item.planId || item.plan_id) || null)
          : null,
        messageId: item?.messageId || item?.message_id
          ? (messageIdMap.get(item.messageId || item.message_id) || null)
          : null,
        message_id: item?.messageId || item?.message_id
          ? (messageIdMap.get(item.messageId || item.message_id) || null)
          : null,
        sessionId: branchSession.id,
        session_id: branchSession.id,
      }, { id: branchSession.id, sessionId: branchSession.id }, index))
      .filter(Boolean);

    const remappedAnnotations = sourceAnnotations
      .filter((annotation) => !isAnnotationDeleted(annotation))
      .map((annotation, index) => applyAnnotationPreferences({
        ...annotation,
        id: `${branchSession.id}-ann-${index + 1}`,
        preference_key: undefined,
        session_id: branchSession.id,
        message_id: annotation.message_id ? (messageIdMap.get(annotation.message_id) || annotation.message_id) : annotation.message_id,
        plan_id: annotation.plan_id ? (planIdMap.get(annotation.plan_id) || annotation.plan_id) : null,
        visible: annotation.visible !== false,
        pinned: !!annotation.pinned,
        deleted: false,
      }, state.annotationPreferences || {}, {
        sessionId: branchSession.id,
        messageId: annotation.message_id ? (messageIdMap.get(annotation.message_id) || annotation.message_id) : annotation.message_id,
        planId: annotation.plan_id ? (planIdMap.get(annotation.plan_id) || annotation.plan_id) : null,
      }));

    branchSession = normalizeSessionShape({
      ...branchSession,
      title: branchTitle,
      pinned: false,
      symbol: sourceScope.symbol,
      contractId: sourceScope.contractId,
      timeframe: sourceScope.timeframe,
      windowRange: sourceScope.windowRange,
      unreadCount: 0,
      selectedPromptBlockIds: [],
      pinnedContextBlockIds: [],
      includeMemorySummary: !!sourceSession.includeMemorySummary,
      includeRecentMessages: !!sourceSession.includeRecentMessages,
      promptBlocks: [],
      mountedReplyIds: [],
      activePlanId: sourceSession.activePlanId ? (planIdMap.get(sourceSession.activePlanId) || null) : null,
      recapItems: clonedRecapItems,
      scrollOffset: 0,
      messages: clonedMessages,
      turns: clonedMessages.map((item) => ({ role: item.role, content: item.content, meta: item.meta || {} })),
      draftText: sourceSession.draftText || sourceSession.draft || "",
      draft: sourceSession.draftText || sourceSession.draft || "",
      draftAttachments: sourceDraftAttachments,
      attachments: sourceDraftAttachments,
      analysisTemplate: sourceAnalysisTemplate || branchSession.analysisTemplate,
      activeModel: sourceSession.activeModel || branchSession.activeModel || "",
      handoffMode: sourceSession.handoffMode || branchSession.handoffMode || "summary_only",
      backendLoaded: true,
      loadingFromServer: false,
      memory: {
        ...sourceMemory,
        session_id: branchSession.id,
      },
    });

    const branchIndex = state.aiThreads.findIndex((item) => item.id === branchSession.id || item.sessionId === branchSession.sessionId);
    if (branchIndex >= 0) {
      state.aiThreads.splice(branchIndex, 1, branchSession);
    } else {
      state.aiThreads.push(branchSession);
    }
    state.aiAnnotations = [
      ...(state.aiAnnotations || []).filter((item) => item.session_id !== branchSession.id),
      ...remappedAnnotations,
    ];
    state.activeAiThreadId = branchSession.id;
    branchSession.updatedAt = new Date().toISOString();

    if (fetchJson) {
      void patchSessionOnServer(branchSession, {
        active_model: branchSession.activeModel || null,
        pinned: false,
        include_memory_summary: !!branchSession.includeMemorySummary,
        include_recent_messages: !!branchSession.includeRecentMessages,
        draft_text: branchSession.draftText || "",
        draft_attachments: buildServerAttachmentPayloads(branchSession.draftAttachments),
        mounted_reply_ids: [],
        scroll_offset: 0,
      });
    }

    renderAiThreadTabs();
    renderAiChat();
    renderAttachments(branchSession);
    persistSessions(state);
    onSessionActivated?.(branchSession);
    return branchSession;
  }

  function renameActiveThread(nextTitle) {
    const session = getActiveThread();
    session.title = nextTitle || session.title;
    session.updatedAt = new Date().toISOString();
    renderAiThreadTabs();
    renderAiChat();
    persistSessions(state);
    void patchSessionOnServer(session, { title: session.title });
  }

  function toggleThreadPin(threadId = null) {
    const session = threadId ? getSessionById(state, threadId) : getActiveThread();
    if (!session) {
      return false;
    }
    session.pinned = !session.pinned;
    session.updatedAt = new Date().toISOString();
    renderAiThreadTabs();
    if (session.id === state.activeAiThreadId) {
      renderAiChat();
    }
    persistSessions(state);
    void patchSessionOnServer(session, { pinned: session.pinned });
    return session.pinned;
  }

  function togglePinActiveThread() {
    return toggleThreadPin();
  }

  function archiveThread(threadId = null) {
    const targetId = threadId || state.activeAiThreadId;
    const targetSession = getSessionById(state, targetId);
    if (!targetSession) {
      return false;
    }
    const wasActive = state.activeAiThreadId === targetId;
    const targetScope = getSessionScope(targetSession, state);
    void archiveSessionOnServer(targetSession);
    state.aiThreads = state.aiThreads.filter((item) => item.id !== targetId);
    if (!state.aiThreads.length) {
      createThread(`${targetScope.symbol}-${String(1).padStart(2, "0")}`, targetScope);
      return true;
    }
    if (wasActive) {
      const nextSession = getPreferredSessionForSymbol(targetScope.symbol, { workspaceRole: getWorkspaceRole(targetSession) })
        || [...listSessionsByRole(getWorkspaceRole(targetSession))].sort((a, b) => compareSessionsByPriority(a, b))[0]
        || [...state.aiThreads].sort((a, b) => compareSessionsByPriority(a, b))[0];
      if (nextSession) {
        state.activeAiThreadId = nextSession.id;
        setActiveThread(nextSession.id, nextSession.title, targetScope);
      }
    } else {
      renderAiThreadTabs();
      renderAttachments(getActiveThread());
    }
    persistSessions(state);
    return true;
  }

  function archiveActiveThread() {
    return archiveThread();
  }

  function deleteActiveThread() {
    return archiveActiveThread();
  }

  function addAttachments(items = []) {
    const session = getActiveThread();
    setDraftAttachments(session, [...getDraftAttachments(session), ...items]);
    session.attachmentPreviewCollapsed = false;
    renderAttachments(session);
    persistSessions(state);
    scheduleDraftStateSync(session);
  }

  function addPromptBlock(block, { selected = true, pinned = false } = {}) {
    const session = getActiveThread();
    if (!block) return null;
    const generatedId = `${block.kind || "block"}-${Date.now()}`;
    const normalizedBlock = {
      ...block,
      id: block.id || block.blockId || block.block_id || generatedId,
      blockId: block.blockId || block.block_id || block.id || generatedId,
      sessionId: block.sessionId || block.session_id || session.id,
      symbol: block.symbol || session.symbol,
      contractId: block.contractId || block.contract_id || session.contractId,
      previewText: block.previewText || block.preview_text || "",
      preview_text: block.preview_text || block.previewText || "",
      title: block.title || block.kind || "上下文块",
      pinned: !!(block.pinned ?? pinned),
    };
    session.promptBlocks = [...(session.promptBlocks || []).filter((item) => (item.blockId || item.block_id || item.id) !== normalizedBlock.blockId), normalizedBlock];
    if (selected && !session.selectedPromptBlockIds.includes(normalizedBlock.blockId)) {
      session.selectedPromptBlockIds = [...session.selectedPromptBlockIds, normalizedBlock.blockId];
    }
    if ((pinned || normalizedBlock.pinned) && !session.pinnedContextBlockIds.includes(normalizedBlock.blockId)) {
      session.pinnedContextBlockIds = [...session.pinnedContextBlockIds, normalizedBlock.blockId];
    }
    onPromptBlocksChanged?.(session, {
      selectedPromptBlockIds: session.selectedPromptBlockIds,
      pinnedContextBlockIds: session.pinnedContextBlockIds,
    });
    persistSessions(state);
    return normalizedBlock;
  }

  function setMountedReplyIds(messageIds = []) {
    const session = getActiveThread();
    const nextIds = Array.from(new Set((messageIds || []).filter(Boolean)));
    session.mountedReplyIds = nextIds;
    const mountedSet = new Set(nextIds);
    session.messages = (session.messages || []).map((message) => {
      if (message.role !== "assistant") {
        return message;
      }
      const objectIds = mountedSet.has(message.message_id)
        ? (state.aiAnnotations || [])
            .filter((annotation) => annotation.session_id === session.id && annotation.message_id === message.message_id)
            .map((annotation) => annotation.id)
        : [];
      return {
        ...message,
        mountedToChart: mountedSet.has(message.message_id),
        mountedObjectIds: objectIds,
        meta: {
          ...(message.meta || {}),
          mountedToChart: mountedSet.has(message.message_id),
          mountedObjectIds: objectIds,
        },
      };
    });
    onMountedRepliesChanged?.(session, nextIds);
    persistSessions(state);
    return session.mountedReplyIds;
  }

  function clearAttachments() {
    const session = getActiveThread();
    setDraftAttachments(session, []);
    session.attachmentPreviewCollapsed = false;
    renderAttachments(session);
    persistSessions(state);
    scheduleDraftStateSync(session, { immediate: true });
  }

  return {
    ensureThread: ensureSession,
    getActiveThread,
    setActiveThread,
    createBackendSession,
    getOrCreateBlankSessionForSymbol,
    hydrateSessionFromServer,
    syncSessionsFromServer,
    getPreferredSessionForSymbol,
    createNewAnalystSession,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    upsertPlanCardToSession,
    cloneActiveThreadBranch,
    renameActiveThread,
    togglePinActiveThread,
    archiveActiveThread,
    deleteActiveThread,
    addAttachments,
    clearAttachments,
    addPromptBlock,
    setMountedReplyIds,
    bindChatScrollBehavior,
    scrollChatToBottom,
    updateChatFollowState,
    scheduleDraftStateSync,
    persistSessions: () => persistSessions(state),
  };
}
