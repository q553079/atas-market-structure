import { createPlanId, summarizeText, writeStorage } from "./replay_workbench_ui_utils.js";

function normalizeLifecycleStatus(status, type = "") {
  const raw = String(status || "").trim().toLowerCase();
  const normalizedType = String(type || "").trim().toLowerCase();
  const activeStatuses = new Set(["active", "triggered", "tp_hit"]);
  const terminalSuccessStatuses = new Set(["completed"]);
  const terminalFailureStatuses = new Set(["sl_hit", "invalidated", "expired", "archived"]);

  if (activeStatuses.has(raw)) {
    return {
      status: raw,
      lifecycle_stage: raw === "triggered" || raw === "tp_hit" ? "in_progress" : "active",
      lifecycle_bucket: "active",
      terminal: false,
      outcome: raw === "tp_hit" ? "partial_profit" : null,
      visual_state: raw === "tp_hit" ? "green_dot" : "blue_dot",
    };
  }
  if (terminalSuccessStatuses.has(raw)) {
    return {
      status: raw,
      lifecycle_stage: "closed",
      lifecycle_bucket: "completed",
      terminal: true,
      outcome: "completed",
      visual_state: "green_check",
    };
  }
  if (raw === "sl_hit") {
    return {
      status: raw,
      lifecycle_stage: "closed",
      lifecycle_bucket: "invalidated",
      terminal: true,
      outcome: "stop_loss_hit",
      visual_state: "red_cross",
    };
  }
  if (terminalFailureStatuses.has(raw)) {
    return {
      status: raw,
      lifecycle_stage: "closed",
      lifecycle_bucket: raw === "archived" ? "archived" : "invalidated",
      terminal: true,
      outcome: raw,
      visual_state: raw === "archived" ? "gray_cross" : "gray_dot",
    };
  }
  if (raw === "inactive_waiting_entry") {
    return {
      status: raw,
      lifecycle_stage: normalizedType === "stop_loss" || normalizedType === "take_profit" ? "pending_entry" : "draft",
      lifecycle_bucket: "pending",
      terminal: false,
      outcome: null,
      visual_state: "gray_dot",
    };
  }
  return {
    status: raw || "active",
    lifecycle_stage: raw === "draft" ? "draft" : "active",
    lifecycle_bucket: raw === "draft" ? "pending" : "active",
    terminal: false,
    outcome: null,
    visual_state: raw === "draft" ? "gray_dot" : "blue_dot",
  };
}

function normalizePlanCard(raw = {}) {
  return {
    id: raw.id || raw.plan_id || createPlanId(),
    title: raw.title || "AI计划卡",
    status: raw.status || "active",
    side: raw.side || "buy",
    entryPrice: raw.entryPrice ?? raw.entry_price ?? raw.entry_price_low ?? null,
    entryPriceLow: raw.entryPriceLow ?? raw.entry_price_low ?? null,
    entryPriceHigh: raw.entryPriceHigh ?? raw.entry_price_high ?? null,
    stopPrice: raw.stopPrice ?? raw.stop_price ?? null,
    targetPrice: raw.targetPrice ?? raw.target_price ?? null,
    targetPrice2: raw.targetPrice2 ?? raw.target_price_2 ?? null,
    take_profits: Array.isArray(raw.take_profits)
      ? raw.take_profits
      : [raw.targetPrice ?? raw.target_price, raw.targetPrice2 ?? raw.target_price_2]
          .filter((item) => item != null)
          .map((target_price, index) => ({ id: `${index + 1}`, tp_level: index + 1, target_price })),
    supporting_zones: raw.supporting_zones || raw.zones || [],
    invalidations: raw.invalidations || [],
    summary: raw.summary || raw.notes || "结构化交易计划",
    notes: raw.notes || "",
    confidence: raw.confidence ?? null,
    priority: raw.priority ?? null,
    time_validity: raw.time_validity || raw.expires_at || null,
  };
}

function normalizeAnnotation(raw = {}, { session, messageId, state, planId = null }) {
  const latestCandle = state.snapshot?.candles?.[state.snapshot.candles.length - 1];
  const startTime = raw.start_time || latestCandle?.started_at || state.snapshot?.window_start || new Date().toISOString();
  const endTime = raw.end_time || latestCandle?.ended_at || state.snapshot?.window_end || new Date().toISOString();
  const type = raw.type || raw.annotation_type || raw.subtype || "entry_line";
  const isPendingPlanChild = ["stop_loss", "take_profit"].includes(type) && raw.status == null;
  const createdAt = raw.created_at || raw.createdAt || startTime;
  const updatedAt = raw.updated_at || raw.updatedAt || endTime || createdAt;
  const normalizedLifecycle = normalizeLifecycleStatus(raw.status || (isPendingPlanChild ? "inactive_waiting_entry" : "active"), type);
  return {
    id: raw.id || `${planId || session.id}-${messageId}-${type}-${Math.random().toString(36).slice(2, 8)}`,
    annotation_id: raw.annotation_id || raw.id || null,
    object_id: raw.object_id || raw.annotation_id || raw.id || null,
    session_id: raw.session_id || session.id,
    message_id: raw.message_id || messageId,
    source_message_id: raw.source_message_id || raw.message_id || messageId,
    plan_id: raw.plan_id || planId || null,
    symbol: raw.symbol || state.topBar?.symbol || state.snapshot?.instrument_symbol || "",
    timeframe: raw.timeframe || state.topBar?.timeframe || state.snapshot?.display_timeframe || "",
    type,
    subtype: raw.subtype || null,
    label: raw.label || raw.title || "AI标记",
    reason: raw.reason || "",
    start_time: startTime,
    end_time: endTime,
    expires_at: raw.expires_at || null,
    status: normalizedLifecycle.status,
    lifecycle_stage: raw.lifecycle_stage || normalizedLifecycle.lifecycle_stage,
    lifecycle_bucket: raw.lifecycle_bucket || normalizedLifecycle.lifecycle_bucket,
    lifecycle_terminal: raw.lifecycle_terminal ?? normalizedLifecycle.terminal,
    lifecycle_outcome: raw.lifecycle_outcome || normalizedLifecycle.outcome,
    visual_state: raw.visual_state || normalizedLifecycle.visual_state,
    priority: raw.priority ?? null,
    confidence: raw.confidence ?? null,
    visible: raw.visible !== false,
    pinned: !!raw.pinned,
    source_kind: raw.source_kind || "replay_analysis",
    source_reply_title: raw.source_reply_title || raw.reply_title || raw.replyTitle || null,
    side: raw.side || null,
    entry_price: raw.entry_price ?? raw.entryPrice ?? null,
    stop_price: raw.stop_price ?? raw.stopPrice ?? null,
    target_price: raw.target_price ?? raw.targetPrice ?? null,
    tp_level: raw.tp_level ?? null,
    price_low: raw.price_low ?? raw.low ?? null,
    price_high: raw.price_high ?? raw.high ?? null,
    path_points: raw.path_points || [],
    created_at: createdAt,
    updated_at: updatedAt,
  };
}

function parsePlanCardsFromReply(replyText) {
  const text = String(replyText || "");
  const lines = text.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  const priceMatches = text.match(/\d{4,5}(?:\.\d{1,2})?/g) || [];
  if (!/止损|TP|止盈|入场|做多|做空/.test(text) || priceMatches.length < 2) {
    return [];
  }
  const side = /做空|空/.test(text) && !/做多/.test(text) ? "sell" : "buy";
  const values = priceMatches.map(Number).filter(Number.isFinite);
  const entry = values[0] ?? null;
  const stop = values[1] ?? null;
  const tp1 = values[2] ?? null;
  const tp2 = values[3] ?? null;
  return [{
    id: createPlanId(),
    title: side === "sell" ? `AI开空 ${entry ?? "待定"}` : `AI开多 ${entry ?? "待定"}`,
    status: "active",
    side,
    entryPrice: entry,
    stopPrice: stop,
    targetPrice: tp1,
    targetPrice2: tp2,
    take_profits: [tp1, tp2].filter((item) => item != null).map((target_price, index) => ({ id: `${index + 1}`, tp_level: index + 1, target_price })),
    summary: summarizeText(lines.slice(0, 3).join("；"), 160),
    notes: text,
  }];
}

function mergeByStableId(currentItems = [], nextItems = [], idSelector) {
  const map = new Map();
  [...currentItems, ...nextItems].forEach((item, index) => {
    if (!item) return;
    const stableId = idSelector(item) || `fallback-${index}`;
    map.set(stableId, { ...(map.get(stableId) || {}), ...item });
  });
  return Array.from(map.values());
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null) return [];
  return [value];
}

function unwrapEventData(eventData = {}) {
  if (!eventData || typeof eventData !== "object") {
    return {};
  }
  return eventData.payload || eventData.data || eventData.message || eventData.event_data || eventData;
}

function pickStreamText(eventData = {}) {
  const payload = unwrapEventData(eventData);
  return firstDefined(
    payload.delta,
    payload.token,
    payload.text,
    payload.content_delta,
    payload.contentDelta,
    payload.chunk,
    payload.content,
    "",
  ) || "";
}

function pickStreamStatus(eventData = {}, fallback = "streaming") {
  const payload = unwrapEventData(eventData);
  return firstDefined(payload.status, payload.state, payload.message_status, fallback) || fallback;
}

function pickStreamAnnotations(eventData = {}) {
  const payload = unwrapEventData(eventData);
  return toArray(firstDefined(payload.annotations, payload.annotation_list, payload.annotation_patch, payload.annotation, payload.objects));
}

function pickStreamPlanCards(eventData = {}) {
  const payload = unwrapEventData(eventData);
  return toArray(firstDefined(payload.plan_cards, payload.planCards, payload.cards, payload.plan_card, payload.plan));
}

function pickStreamMemory(eventData = {}) {
  const payload = unwrapEventData(eventData);
  return firstDefined(payload.memory, payload.session_memory, payload.memory_summary, payload.summary, payload);
}

function buildPromptBlockFromPreset(preset, message, session) {
  const now = Date.now();
  const titleMap = {
    recent_20_bars: "最近20根K线",
    recent_20_minutes: "最近20分钟",
    focus_regions: "重点区域",
    live_depth: "实时挂单",
    manual_region: "手工区域",
    selected_bar: "选中K线",
    general: "当前问题",
  };
  const sourceLabelMap = {
    recent_20_bars: "快捷分析",
    recent_20_minutes: "快捷分析",
    focus_regions: "重点区域",
    live_depth: "盘口上下文",
    manual_region: "手工选择",
    selected_bar: "选中K线",
    general: "用户问题",
  };
  return {
    blockId: `pb-${preset}-${now}`,
    kind: preset || "user_input",
    title: titleMap[preset] || titleMap.general,
    previewText: summarizeText(message, 60),
    sourceLabel: sourceLabelMap[preset] || "用户问题",
    symbol: session?.symbol || session?.memory?.symbol || "NQ",
    contractId: session?.contractId || session?.symbol || session?.memory?.symbol || "NQ",
    ephemeral: true,
  };
}

function normalizePromptBlock(raw = {}, session, fallback = {}) {
  const blockId = raw.block_id || raw.blockId || raw.id || fallback.blockId || `pb-${Date.now()}`;
  return {
    ...raw,
    id: raw.id || raw.block_id || raw.blockId || blockId,
    blockId,
    sessionId: raw.session_id || raw.sessionId || session?.id,
    symbol: raw.symbol || session?.symbol || session?.memory?.symbol || "NQ",
    contractId: raw.contract_id || raw.contractId || session?.contractId || session?.symbol || session?.memory?.symbol || "NQ",
    kind: raw.kind || fallback.kind || "user_input",
    title: raw.title || fallback.title || "上下文块",
    previewText: raw.preview_text || raw.previewText || fallback.previewText || "",
    preview_text: raw.preview_text || raw.previewText || fallback.previewText || "",
    sourceLabel: raw.source_label || raw.sourceLabel || fallback.sourceLabel || fallback.kind || "上下文块",
    ephemeral: raw.ephemeral ?? fallback.ephemeral ?? true,
    pinned: !!(raw.pinned ?? fallback.pinned),
    serverBacked: raw.serverBacked ?? fallback.serverBacked ?? true,
  };
}

function getServerBackedPromptBlockIds(session, blockIds = []) {
  const validIds = new Set(
    (session?.promptBlocks || [])
      .filter((block) => block?.serverBacked !== false)
      .map((block) => block.blockId || block.id)
      .filter(Boolean),
  );
  return (Array.isArray(blockIds) ? blockIds : []).filter((blockId) => validIds.has(blockId));
}

function resetPromptBlockSelection(session) {
  if (!session) {
    return;
  }
  const pinnedIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
  session.selectedPromptBlockIds = [...pinnedIds];
  session.promptBlocks = (session.promptBlocks || []).filter((block) => {
    const blockId = block.blockId || block.id;
    return pinnedIds.includes(blockId);
  });
  session.promptBlockPreviewCache = Object.fromEntries(
    Object.entries(session.promptBlockPreviewCache || {}).filter(([blockId]) => pinnedIds.includes(blockId)),
  );
}

function replacePendingAssistantMessage(session, pendingMessageId, content, meta = {}) {
  if (!session || !pendingMessageId) return null;
  const nextMessages = (session.messages || []).map((message) => {
    const localPendingId = message.meta?.localPendingMessageId || message.message_id;
    if (message.message_id !== pendingMessageId && localPendingId !== pendingMessageId) {
      return message;
    }
    return {
      ...message,
      message_id: meta.message_id || meta.messageId || message.message_id,
      content,
      status: meta.status || message.status || "completed",
      replyTitle: meta.replyTitle || meta.reply_title || message.replyTitle || null,
      model: meta.model || message.model || null,
      annotations: Array.isArray(meta.annotations) ? meta.annotations : (message.annotations || []),
      planCards: Array.isArray(meta.planCards) ? meta.planCards : (message.planCards || []),
      mountedToChart: meta.mountedToChart ?? message.mountedToChart ?? false,
      mountedObjectIds: Array.isArray(meta.mountedObjectIds) ? meta.mountedObjectIds : (message.mountedObjectIds || []),
      meta: {
        ...(message.meta || {}),
        localPendingMessageId: message.meta?.localPendingMessageId || pendingMessageId,
        ...meta,
      },
      updated_at: new Date().toISOString(),
    };
  });
  session.messages = nextMessages;
  session.turns = nextMessages.map((item) => ({ role: item.role, content: item.content, meta: item.meta || {} }));
  const resolvedMessageId = meta.message_id || meta.messageId || pendingMessageId;
  return nextMessages.find((item) => item.message_id === resolvedMessageId || item.meta?.localPendingMessageId === pendingMessageId) || null;
}

function mergeMessageAnnotations(state, session, messageId, planCards = [], explicitAnnotations = []) {
  state.aiAnnotations = [
    ...state.aiAnnotations.filter((item) => item.session_id !== session.id || item.message_id !== messageId),
    ...buildAnnotationBundle({ session, messageId, planCards, state, explicitAnnotations }),
  ];
}

function buildAnnotationBundle({ session, messageId, planCards = [], state, explicitAnnotations = [] }) {
  const latestCandle = state.snapshot?.candles?.[state.snapshot.candles.length - 1];
  const startTime = latestCandle?.started_at || state.snapshot?.window_start || new Date().toISOString();
  const endTime = latestCandle?.ended_at || state.snapshot?.window_end || new Date().toISOString();
  const annotations = [];

  explicitAnnotations.forEach((item) => {
    annotations.push(normalizeAnnotation(item, { session, messageId, state, planId: item.plan_id || null }));
  });

  planCards.forEach((plan) => {
    if (plan.entryPrice != null || (plan.entryPriceLow != null && plan.entryPriceHigh != null)) {
      annotations.push(normalizeAnnotation({
        id: `${plan.id}-entry`,
        plan_id: plan.id,
        type: "entry_line",
        label: plan.title,
        start_time: startTime,
        end_time: endTime,
        entry_price: plan.entryPrice,
        price_low: plan.entryPriceLow,
        price_high: plan.entryPriceHigh,
        side: plan.side,
        status: plan.status || "active",
        visible: true,
        confidence: plan.confidence,
        priority: plan.priority,
      }, { session, messageId, state, planId: plan.id }));
    }
    if (plan.stopPrice != null) {
      annotations.push(normalizeAnnotation({
        id: `${plan.id}-sl`,
        plan_id: plan.id,
        type: "stop_loss",
        label: `SL ${plan.stopPrice}`,
        start_time: startTime,
        end_time: endTime,
        stop_price: plan.stopPrice,
        status: "inactive_waiting_entry",
        visible: true,
      }, { session, messageId, state, planId: plan.id }));
    }
    (plan.take_profits || []).forEach((tp) => {
      annotations.push(normalizeAnnotation({
        id: `${plan.id}-tp-${tp.tp_level}`,
        plan_id: plan.id,
        type: "take_profit",
        label: `TP${tp.tp_level} ${tp.target_price}`,
        start_time: startTime,
        end_time: endTime,
        target_price: tp.target_price,
        tp_level: tp.tp_level,
        status: "inactive_waiting_entry",
        visible: true,
      }, { session, messageId, state, planId: plan.id }));
    });
    (plan.supporting_zones || []).forEach((zone, index) => {
      annotations.push(normalizeAnnotation({
        id: `${plan.id}-zone-${index + 1}`,
        plan_id: plan.id,
        type: zone.type || zone.zone_type || "support_zone",
        label: zone.label || `${zone.type === "resistance_zone" ? "阻力区" : zone.type === "no_trade_zone" ? "无交易区" : "支撑区"} ${zone.price_low}-${zone.price_high}`,
        start_time: zone.start_time || startTime,
        end_time: zone.end_time || endTime,
        price_low: zone.price_low,
        price_high: zone.price_high,
        status: zone.status || "active",
        visible: zone.visible !== false,
        reason: zone.reason || "",
      }, { session, messageId, state, planId: plan.id }));
    });
  });

  const dedup = new Map();
  annotations.forEach((item) => {
    dedup.set(item.id, item);
  });
  return Array.from(dedup.values());
}

function buildOutgoingAttachments(session) {
  const attachments = Array.isArray(session?.draftAttachments)
    ? session.draftAttachments
    : (Array.isArray(session?.attachments) ? session.attachments : []);
  return attachments
    .map((item) => ({
      name: item.name || null,
      media_type: item.media_type || item.kind || "application/octet-stream",
      data_url: item.data_url || item.preview_url || "",
    }))
    .filter((item) => item.data_url);
}

export function createAiChatController({
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
  sessionMemoryEngine = null,
  addPromptBlock = null,
  getOrCreateBlankSessionForSymbol = null,
  createNewAnalystSession = null,
  renderAiChat = null,
  scheduleDraftStateSync = null,
}) {
  let activeStreamController = null;
  let activeStreamMeta = null;

  function setStreamingUiState(streaming) {
    const nextStreaming = !!streaming;
    if (els.aiChatSendButton) {
      els.aiChatSendButton.dataset.busy = nextStreaming ? "true" : "false";
      els.aiChatSendButton.setAttribute("aria-busy", nextStreaming ? "true" : "false");
      els.aiChatSendButton.classList.toggle("is-active", nextStreaming);
      els.aiChatSendButton.disabled = nextStreaming;
    }
    if (els.aiChatStopButton) {
      els.aiChatStopButton.hidden = !nextStreaming;
      els.aiChatStopButton.disabled = !nextStreaming;
      els.aiChatStopButton.dataset.busy = "false";
      els.aiChatStopButton.setAttribute("aria-pressed", nextStreaming ? "true" : "false");
      els.aiChatStopButton.classList.toggle("is-active", nextStreaming);
    }
    const composer = els.aiChatInput?.closest(".chat-composer");
    if (composer) {
      composer.classList.toggle("is-streaming", nextStreaming);
    }
  }

  function refreshChatUi() {
    renderAiChat?.();
  }

  function isReplayRequiredPreset(preset) {
    return ["recent_20_bars", "selected_bar", "manual_region", "live_depth"].includes(preset);
  }

  function ensureReplayIngestionReady({ preserveInput = true, reason = "请先加载图表 / 回放数据，再发送 AI 问题" } = {}) {
    if (state.currentReplayIngestionId) {
      return true;
    }
    const currentValue = preserveInput ? String(els.aiChatInput?.value || "").trim() : "";
    if (preserveInput && currentValue && !els.aiChatInput.value) {
      els.aiChatInput.value = currentValue;
    }
    renderStatusStrip?.([{ label: reason, variant: "warn" }]);
    refreshChatUi();
    return false;
  }

  function buildPromptBlockCandidates({ preset, includeMemorySummary, includeRecentMessages, hasReplayContext }) {
    const candidates = [];
    if (hasReplayContext) {
      const presetMap = {
        recent_20_bars: "candles_20",
        recent_20_minutes: "event_summary",
        focus_regions: "event_summary",
        live_depth: "event_summary",
        manual_region: "manual_region",
        selected_bar: "selected_bar",
        general: "event_summary",
        viewport: "event_summary",
      };
      const primaryCandidate = presetMap[preset] || "event_summary";
      candidates.push(primaryCandidate);
    }
    if (includeMemorySummary) {
      candidates.push("session_summary");
    }
    if (includeRecentMessages) {
      candidates.push("recent_messages");
    }
    return Array.from(new Set(candidates));
  }

  async function buildPromptBlocks(session, request) {
    const payload = {
      candidates: buildPromptBlockCandidates({
        preset: request.preset,
        includeMemorySummary: request.includeMemorySummary,
        includeRecentMessages: request.includeRecentMessages,
        hasReplayContext: !!request.hasReplayContext,
      }),
    };

    if (fetchJson) {
      try {
        const response = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/prompt-blocks/build`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const blocks = Array.isArray(response?.prompt_blocks)
          ? response.prompt_blocks
          : Array.isArray(response?.blocks)
            ? response.blocks
            : [];
        if (blocks.length) {
          return blocks.map((block) => normalizePromptBlock(block, session, {
            kind: request.preset,
            title: request.fallbackTitle,
            previewText: summarizeText(request.userInput || "", 60),
            serverBacked: true,
          }));
        }
      } catch (error) {
        console.warn("构建 Prompt blocks 失败，回退本地 block:", error);
      }
    }

    return [normalizePromptBlock(buildPromptBlockFromPreset(request.preset, request.userInput || "", session), session, {
      kind: request.preset,
      title: request.fallbackTitle,
      previewText: summarizeText(request.userInput || "", 60),
      ephemeral: true,
      serverBacked: false,
    })];
  }

  async function stopActiveStream() {
    if (!activeStreamMeta) {
      return false;
    }
    const { sessionId, pendingMessageId, serverMessageId } = activeStreamMeta;
    const stopMessageId = serverMessageId || pendingMessageId;
    try {
      await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(stopMessageId)}/stop`, {
        method: "POST",
      });
    } catch (error) {
      console.warn("停止生成接口失败:", error);
    }
    if (activeStreamController) {
      activeStreamController.abort();
    }
    return true;
  }

  function resolveStreamingMessageId(session, pendingMessageId, runtime = {}, eventData = {}) {
    const payload = unwrapEventData(eventData);
    const candidateIds = [
      firstDefined(payload.message_id, payload.id, payload.assistant_message_id),
      runtime.serverMessageId,
      pendingMessageId,
    ].filter(Boolean);

    const currentMessages = Array.isArray(session.messages) ? session.messages : [];
    const matchedMessage = currentMessages.find((message) => candidateIds.includes(message.message_id));
    if (matchedMessage?.message_id) {
      return matchedMessage.message_id;
    }
    return pendingMessageId;
  }

  function syncStreamingMessage(session, pendingMessageId, patch = {}, runtime = {}, eventData = {}) {
    const resolvedMessageId = resolveStreamingMessageId(session, pendingMessageId, runtime, eventData);
    const next = replacePendingAssistantMessage(
      session,
      resolvedMessageId,
      patch.content ?? (session.messages || []).find((item) => item.message_id === resolvedMessageId)?.content ?? "",
      patch,
    );
    persistSessions();
    refreshChatUi();
    return next;
  }

  function applyTokenDelta(session, pendingMessageId, delta, runtime = {}, eventData = {}) {
    const resolvedMessageId = resolveStreamingMessageId(session, pendingMessageId, runtime, eventData);
    const current = (session.messages || []).find((item) => item.message_id === resolvedMessageId);
    const currentContent = current?.content === "正在思考中…" ? "" : (current?.content || "");
    syncStreamingMessage(session, resolvedMessageId, {
      content: `${currentContent}${delta || ""}`,
      status: "streaming",
    }, runtime, eventData);
  }

  function applyAnnotationPatch(session, pendingMessageId, annotations = [], runtime = {}, eventData = {}) {
    const resolvedMessageId = resolveStreamingMessageId(session, pendingMessageId, runtime, eventData);
    const current = (session.messages || []).find((item) => item.message_id === resolvedMessageId);
    const nextAnnotations = Array.isArray(annotations) ? annotations : [];
    const mergedAnnotations = mergeByStableId(current?.annotations || [], nextAnnotations, (item) => item?.id || item?.annotation_id);
    syncStreamingMessage(session, resolvedMessageId, {
      annotations: mergedAnnotations,
      status: current?.status || "streaming",
    }, runtime, eventData);
    mergeMessageAnnotations(state, session, resolvedMessageId, current?.planCards || [], mergedAnnotations);
  }

  function applyPlanCards(session, pendingMessageId, planCards = [], runtime = {}, eventData = {}) {
    const resolvedMessageId = resolveStreamingMessageId(session, pendingMessageId, runtime, eventData);
    const nextPlanCards = (Array.isArray(planCards) ? planCards : []).map((plan) => upsertPlanCardToSession(normalizePlanCard(plan), session.id, resolvedMessageId));
    const current = (session.messages || []).find((item) => item.message_id === resolvedMessageId);
    const mergedPlanCards = mergeByStableId(current?.planCards || [], nextPlanCards, (item) => item?.id || item?.plan_id);
    syncStreamingMessage(session, resolvedMessageId, {
      planCards: mergedPlanCards,
      status: current?.status || "streaming",
    }, runtime, eventData);
    mergeMessageAnnotations(state, session, resolvedMessageId, mergedPlanCards, current?.annotations || []);
  }

  function finishStreamingMessage(session, pendingMessageId, payload = {}, runtime = {}, eventData = {}) {
    const resolvedMessageId = resolveStreamingMessageId(session, pendingMessageId, runtime, eventData);
    const current = (session.messages || []).find((item) => item.message_id === resolvedMessageId);
    const assistantContent = payload.content ?? current?.content ?? "";
    const structuredPlanCards = Array.isArray(payload.planCards) ? payload.planCards : (current?.planCards || []);
    const structuredAnnotations = Array.isArray(payload.annotations) ? payload.annotations : (current?.annotations || []);
    const assistantMessage = syncStreamingMessage(session, resolvedMessageId, {
      content: assistantContent,
      planCards: structuredPlanCards,
      annotations: structuredAnnotations,
      replyTitle: payload.replyTitle || current?.replyTitle || structuredPlanCards[0]?.title || null,
      provider: payload.provider || current?.meta?.provider,
      model: payload.model || current?.model,
      session_only: payload.sessionOnly ?? payload.session_only ?? current?.meta?.session_only ?? false,
      live_context_summary: payload.liveContextSummary || current?.meta?.live_context_summary || [],
      follow_up_suggestions: payload.followUpSuggestions || current?.meta?.follow_up_suggestions || [],
      status: payload.status || "completed",
    }, runtime, eventData);
    mergeMessageAnnotations(state, session, resolvedMessageId, structuredPlanCards, structuredAnnotations);
    return assistantMessage;
  }


  function handleChatStreamEvent(session, pendingMessageId, eventName, eventData, runtime = {}) {
    const payload = unwrapEventData(eventData);
    const normalizedEventName = String(eventName || payload.event || payload.type || "message")
      .trim()
      .toLowerCase()
      .replace(/-/g, "_");
    const announcedMessageId = firstDefined(payload.message_id, payload.id, payload.assistant_message_id);
    if (announcedMessageId && activeStreamMeta?.sessionId === session.id && activeStreamMeta?.pendingMessageId === pendingMessageId) {
      activeStreamMeta.serverMessageId = announcedMessageId;
    }

    if (normalizedEventName === "message_start") {
      const messageId = announcedMessageId;
      if (messageId) {
        runtime.serverMessageId = messageId;
      }
      syncStreamingMessage(session, pendingMessageId, {
        message_id: runtime.serverMessageId || pendingMessageId,
        replyTitle: firstDefined(payload.reply_title, payload.replyTitle, payload.title, "AI 回复生成中"),
        model: firstDefined(payload.model, payload.model_name, runtime.model, null),
        provider: firstDefined(payload.provider, payload.vendor, runtime.provider, "stream"),
        session_only: firstDefined(payload.session_only, payload.sessionOnly, false),
        status: pickStreamStatus(payload, "pending"),
      }, runtime, payload);
      return;
    }
    if (normalizedEventName === "message_status") {
      syncStreamingMessage(session, pendingMessageId, {
        status: pickStreamStatus(payload, "streaming"),
      }, runtime, payload);
      return;
    }
    if (normalizedEventName === "token" || normalizedEventName === "content_delta") {
      applyTokenDelta(session, pendingMessageId, pickStreamText(payload), runtime, payload);
      return;
    }
    if (normalizedEventName === "annotation_patch" || normalizedEventName === "annotations") {
      applyAnnotationPatch(session, pendingMessageId, pickStreamAnnotations(payload), runtime, payload);
      return;
    }
    if (normalizedEventName === "plan_card" || normalizedEventName === "plan_cards") {
      applyPlanCards(session, pendingMessageId, pickStreamPlanCards(payload), runtime, payload);
      return;
    }
    if (normalizedEventName === "memory_updated" || normalizedEventName === "session_memory") {
      session.memory = {
        ...(session.memory || {}),
        ...(pickStreamMemory(payload) || {}),
      };
      persistSessions();
      return;
    }
    if (normalizedEventName === "message_end" || normalizedEventName === "done" || normalizedEventName === "completed") {
      const endPlanCards = pickStreamPlanCards(payload);
      finishStreamingMessage(session, pendingMessageId, {
        content: firstDefined(payload.content, payload.reply_text, payload.text, payload.final_content),
        replyTitle: firstDefined(payload.reply_title, payload.replyTitle, payload.title),
        planCards: endPlanCards.length
          ? endPlanCards.map((plan) => upsertPlanCardToSession(normalizePlanCard(plan), session.id, resolveStreamingMessageId(session, pendingMessageId, runtime, payload)))
          : undefined,
        annotations: pickStreamAnnotations(payload),
        provider: firstDefined(payload.provider, payload.vendor, runtime.provider),
        model: firstDefined(payload.model, payload.model_name, runtime.model),
        sessionOnly: firstDefined(payload.session_only, payload.sessionOnly, false),
        liveContextSummary: firstDefined(payload.live_context_summary, payload.liveContextSummary),
        followUpSuggestions: firstDefined(payload.follow_up_suggestions, payload.followUpSuggestions, payload.suggestions),
        status: pickStreamStatus(payload, "completed"),
      }, runtime, payload);
      return;
    }
    if (normalizedEventName === "error" || normalizedEventName === "stream_error") {
      throw new Error(firstDefined(payload.error, payload.message, payload.detail, "流式输出失败"));
    }
    if (normalizedEventName === "message") {
      if (pickStreamText(payload)) {
        applyTokenDelta(session, pendingMessageId, pickStreamText(payload), runtime, payload);
      }
    }
  }

  async function openChatStream(session, payload, pendingMessageId) {
    const controller = new AbortController();
    activeStreamController = controller;
    activeStreamMeta = { sessionId: session.id, pendingMessageId };
    setStreamingUiState(true);

    try {
      const response = await fetch(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`流式接口不可用 (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const runtime = { model: payload.model || null, provider: "stream" };
      activeStreamMeta = { sessionId: session.id, pendingMessageId, serverMessageId: null };

      const consumeChunk = (rawChunk) => {
        const lines = rawChunk.split(/\r?\n/);
        let eventName = "message";
        const dataLines = [];
        lines.forEach((line) => {
          if (line.startsWith(":")) {
            return;
          }
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trim());
          }
        });
        if (!dataLines.length) return;
        const raw = dataLines.join("\n");
        let parsed = {};
        try {
          parsed = raw ? JSON.parse(raw) : {};
        } catch {
          parsed = { content: raw, delta: raw };
        }
        handleChatStreamEvent(session, pendingMessageId, eventName, parsed, runtime);
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        chunks.forEach(consumeChunk);
      }

      if (buffer.trim()) {
        consumeChunk(buffer);
      }
    } finally {
      activeStreamController = null;
      activeStreamMeta = null;
      setStreamingUiState(false);
    }
  }
  let activeRegenerateMessageId = null;

  async function regenerateMessage(messageId) {
    const session = getActiveThread();
    if (!messageId || activeRegenerateMessageId === messageId) {
      return null;
    }
    activeRegenerateMessageId = messageId;
    renderStatusStrip([{ label: "正在重新生成…", variant: "emphasis" }]);
    try {
      const result = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/messages/${encodeURIComponent(messageId)}/regenerate`, {
        method: "POST",
      });
      const assistantContent = result.reply_text || result.assistant_message?.content || "";
      const planCards = Array.isArray(result.plan_cards || result.planCards)
        ? (result.plan_cards || result.planCards).map((plan) => upsertPlanCardToSession(normalizePlanCard(plan), session.id, result.assistant_message?.message_id))
        : [];
      const structuredAnnotations = Array.isArray(result.annotations) ? result.annotations : [];
      appendAiChatMessage("assistant", assistantContent, {
        preset: result.preset,
        provider: result.provider,
        model: result.model,
        planCards,
        annotations: structuredAnnotations,
        replyTitle: result.assistant_message?.reply_title || planCards[0]?.title || null,
        status: result.assistant_message?.status || "regenerated",
        parent_message_id: messageId,
      }, session.id, session.title);
      mergeMessageAnnotations(state, session, result.assistant_message?.message_id, planCards, structuredAnnotations);
      if (result.memory) {
        session.memory = {
          ...(session.memory || {}),
          ...result.memory,
        };
      }
      persistSessions();
      renderStatusStrip([{ label: "重新生成完成", variant: "good" }]);
      return result;
    } finally {
      activeRegenerateMessageId = null;
    }
  }

  async function handleAiChat(preset, userMessage, threadMeta = null) {
    const trimmedMessage = String(userMessage || "").trim();
    if (!trimmedMessage) {
      throw new Error("请输入要分析的问题。");
    }
    if (!state.currentReplayIngestionId && isReplayRequiredPreset(preset)) {
      renderStatusStrip?.([{ label: "此功能需要先加载图表。普通文字聊天可直接发送。", variant: "warn" }]);
      refreshChatUi();
      return { blocked: true };
    }
    const descriptor = threadMeta || getPresetThreadMeta(preset);
    const session = setActiveThread(descriptor.id, descriptor.title, {
      symbol: descriptor.symbol || threadMeta?.symbol || state.topBar?.symbol,
      contractId: descriptor.contractId || threadMeta?.contractId || descriptor.symbol || threadMeta?.symbol || state.topBar?.symbol,
      timeframe: descriptor.timeframe || threadMeta?.timeframe || state.topBar?.timeframe,
      windowRange: descriptor.windowRange || threadMeta?.windowRange || state.topBar?.quickRange,
    });
    const includeMemorySummary = !!session.includeMemorySummary;
    const includeRecentMessages = !!session.includeRecentMessages;
    const builtBlocks = await buildPromptBlocks(session, {
      preset,
      userInput: trimmedMessage,
      analysisType: session.analysisTemplate?.type,
      analysisRange: session.analysisTemplate?.range,
      analysisStyle: session.analysisTemplate?.style,
      includeMemorySummary,
      includeRecentMessages,
      attachments: buildOutgoingAttachments(session),
      hasReplayContext: !!state.currentReplayIngestionId,
    });
    resetPromptBlockSelection(session);
    builtBlocks.forEach((block) => {
      addPromptBlock?.(block, { selected: true, pinned: !!block.pinned });
    });
    const effectiveSelectedBlockIds = getServerBackedPromptBlockIds(session, session.selectedPromptBlockIds);
    const effectivePinnedBlockIds = getServerBackedPromptBlockIds(session, session.pinnedContextBlockIds);
    const outgoingAttachments = buildOutgoingAttachments(session);
    appendAiChatMessage("user", trimmedMessage, {
      preset,
      selected_block_ids: effectiveSelectedBlockIds,
      pinned_block_ids: effectivePinnedBlockIds,
      attachments: outgoingAttachments,
    }, session.id, session.title);
    const pendingAssistant = appendAiChatMessage("assistant", "正在思考中…", {
      preset,
      provider: "pending",
      model: session.activeModel || els.aiModelOverride.value.trim() || null,
      status: "pending",
      replyTitle: "AI 回复生成中",
      planCards: [],
      annotations: [],
      localPendingMessageId: null,
    }, session.id, session.title);
    if (pendingAssistant?.message_id) {
      pendingAssistant.meta = {
        ...(pendingAssistant.meta || {}),
        localPendingMessageId: pendingAssistant.message_id,
      };
    }
    renderStatusStrip([{ label: "AI 对话生成中", variant: "emphasis" }]);
    try {
      const selectedBlockIds = getServerBackedPromptBlockIds(session, session.selectedPromptBlockIds);
      const pinnedBlockIds = getServerBackedPromptBlockIds(session, session.pinnedContextBlockIds);
      const includeMemorySummary = !!session.includeMemorySummary;
      const includeRecentMessages = !!session.includeRecentMessages;
      const requestPayload = {
        replay_ingestion_id: state.currentReplayIngestionId || null,
        preset,
        user_input: trimmedMessage,
        selected_block_ids: selectedBlockIds,
        pinned_block_ids: pinnedBlockIds,
        include_memory_summary: includeMemorySummary,
        include_recent_messages: includeRecentMessages,
        analysis_type: session.analysisTemplate?.type || preset || "general",
        analysis_range: session.analysisTemplate?.range || "current_window",
        analysis_style: session.analysisTemplate?.style || "standard",
        model: session.activeModel || els.aiModelOverride.value.trim() || null,
        attachments: buildOutgoingAttachments(session),
      };
      let result;
      try {
        await openChatStream(session, requestPayload, pendingAssistant?.message_id);
        result = { streamed: true };
      } catch (streamError) {
        if (streamError?.name === "AbortError") {
          const interruptedMessageId = activeStreamMeta?.serverMessageId || pendingAssistant?.message_id;
          finishStreamingMessage(session, interruptedMessageId, {
            content: (session.messages || []).find((item) => item.message_id === interruptedMessageId || item.meta?.localPendingMessageId === pendingAssistant?.message_id)?.content || "",
            status: "interrupted",
            replyTitle: "AI 回复已中断",
          });
          const interruptedMessage = (session.messages || []).find((item) => item.message_id === interruptedMessageId || item.meta?.localPendingMessageId === pendingAssistant?.message_id);
          if (sessionMemoryEngine?.updateFromAssistantResult && interruptedMessage?.content) {
            sessionMemoryEngine.updateFromAssistantResult(session, {
              replyText: interruptedMessage.content,
              userMessage: trimmedMessage,
              liveContextSummary: interruptedMessage?.meta?.live_context_summary || [],
              model: interruptedMessage?.model || session.activeModel || "",
            });
          }
          renderStatusStrip([{ label: "已停止生成", variant: "warn" }]);
          persistSessions();
          refreshChatUi();
          writeStorage("annotationFilters", state.annotationFilters);
          return { interrupted: true };
        }
        result = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestPayload),
        });
      }
      if (result.session) {
        session.activeModel = result.session.active_model || session.activeModel || "";
      }
      if (result.memory) {
        session.memory = {
          ...session.memory,
          ...result.memory,
        };
      }
      if (result.streamed) {
        const streamedMessage = (session.messages || []).find((item) => item.message_id === pendingAssistant?.message_id || item.meta?.localPendingMessageId === pendingAssistant?.message_id);
        const streamedPlanCards = Array.isArray(streamedMessage?.planCards) ? streamedMessage.planCards : [];
        const streamedAnnotations = Array.isArray(streamedMessage?.annotations) ? streamedMessage.annotations : [];
        const streamedContent = streamedMessage?.content === "正在思考中…" ? "" : (streamedMessage?.content || "");
        if (sessionMemoryEngine?.updateFromAssistantResult) {
          sessionMemoryEngine.updateFromAssistantResult(session, {
            replyText: streamedContent,
            userMessage: trimmedMessage,
            liveContextSummary: streamedMessage?.meta?.live_context_summary || [],
            model: streamedMessage?.model || session.activeModel || "",
          });
        }
        renderStatusStrip([
          { label: "AI 流式输出完成", variant: "good" },
          { label: streamedMessage?.model || session.activeModel || "服务端默认", variant: "emphasis" },
        ]);
        persistSessions();
        refreshChatUi();
        writeStorage("annotationFilters", state.annotationFilters);
        return {
          streamed: true,
          reply_text: streamedContent,
          model: streamedMessage?.model || session.activeModel || null,
          annotations: streamedAnnotations,
          plan_cards: streamedPlanCards,
        };
      }
      const structuredPlanCards = Array.isArray(result.plan_cards || result.planCards)
        ? (result.plan_cards || result.planCards).map((plan) => normalizePlanCard(plan))
        : [];
      const assistantContent = result.reply_text || result.assistant_message?.content || "";
      const fallbackPlanCards = structuredPlanCards.length ? structuredPlanCards : parsePlanCardsFromReply(assistantContent).map((plan) => normalizePlanCard(plan));
      const planCards = fallbackPlanCards.map((plan) => upsertPlanCardToSession(plan, session.id));
      const structuredAnnotations = Array.isArray(result.annotations) ? result.annotations : [];
      const assistantMessage = replacePendingAssistantMessage(session, pendingAssistant?.message_id, assistantContent, {
        preset: result.preset,
        provider: result.provider,
        model: result.model,
        referenced_strategy_ids: result.referenced_strategy_ids || [],
        live_context_summary: result.live_context_summary || [],
        follow_up_suggestions: result.follow_up_suggestions || [],
        planCards,
        annotations: structuredAnnotations,
        replyTitle: result.assistant_message?.reply_title || fallbackPlanCards[0]?.title || null,
        mountedToChart: false,
        session_only: !!result.session_only,
        status: "completed",
      }) || appendAiChatMessage("assistant", assistantContent, {
        preset: result.preset,
        provider: result.provider,
        model: result.model,
        referenced_strategy_ids: result.referenced_strategy_ids || [],
        live_context_summary: result.live_context_summary || [],
        follow_up_suggestions: result.follow_up_suggestions || [],
        planCards,
        annotations: structuredAnnotations,
        replyTitle: result.assistant_message?.reply_title || fallbackPlanCards[0]?.title || null,
        mountedToChart: false,
        session_only: !!result.session_only,
      }, session.id, session.title);
      session.messages = session.messages.map((message) => message.message_id === assistantMessage.message_id
        ? {
            ...message,
            planCards,
            annotations: structuredAnnotations,
            meta: {
              ...(message.meta || {}),
              planCards,
              annotations: structuredAnnotations,
            },
          }
        : message);
      state.aiAnnotations = [
        ...state.aiAnnotations.filter((item) => item.session_id !== session.id || item.message_id !== assistantMessage.message_id),
        ...buildAnnotationBundle({ session, messageId: assistantMessage.message_id, planCards, state, explicitAnnotations: structuredAnnotations }),
      ];
      if (sessionMemoryEngine?.updateFromAssistantResult) {
        sessionMemoryEngine.updateFromAssistantResult(session, {
          replyText: assistantContent,
          userMessage: trimmedMessage,
          liveContextSummary: result.live_context_summary || [],
          model: result.model || session.activeModel || "",
        });
      } else {
        session.memory.active_model = result.model || session.activeModel || "";
        session.memory.latest_answer_summary = summarizeText(assistantContent, 180);
        session.memory.market_context_summary = summarizeText((result.live_context_summary || []).join("；"), 180);
        session.memory.current_user_intent = summarizeText(trimmedMessage, 100);
        session.memory.user_goal_summary = session.memory.user_goal_summary || summarizeText(trimmedMessage, 120);
        session.memory.symbol = session.symbol || state.topBar?.symbol || session.memory.symbol || "NQ";
        session.memory.timeframe = session.timeframe || state.topBar?.timeframe || session.memory.timeframe || "1m";
        session.memory.key_zones_summary = Array.from(new Set([
          ...(session.memory.key_zones_summary || []),
          ...state.aiAnnotations.filter((item) => item.session_id === session.id && ["support_zone", "resistance_zone", "no_trade_zone"].includes(item.type)).map((item) => item.label),
        ])).slice(-8);
        session.memory.selected_annotations = (state.aiAnnotations || []).filter((item) => item.session_id === session.id && item.status !== "archived").map((item) => item.id).slice(-12);
        session.memory.last_updated_at = new Date().toISOString();
      }
      renderStatusStrip([
        { label: "AI 对话已完成", variant: "good" },
        { label: result.model || "服务端默认", variant: "emphasis" },
      ]);
      persistSessions();
      refreshChatUi();
      writeStorage("annotationFilters", state.annotationFilters);
      return result;
    } catch (error) {
      replacePendingAssistantMessage(session, pendingAssistant?.message_id, error.message || String(error), {
        preset,
        provider: "local-error",
        model: "-",
        status: "failed",
        replyTitle: "AI 对话失败",
      });
      renderStatusStrip([{ label: "AI 对话失败", variant: "warn" }]);
      persistSessions();
      refreshChatUi();
      throw error;
    }
  }

  async function handleAiChatSend() {
    let session = getActiveThread();
    const draftText = els.aiChatInput.value;
    const message = draftText.trim();
    const composerPreset = "general";
    if (!message) {
      renderStatusStrip([{ label: "请先输入消息，再发送。", variant: "warn" }]);
      els.aiChatInput.focus();
      return;
    }
    if (!state.currentReplayIngestionId && isReplayRequiredPreset(composerPreset)) {
      if (!ensureReplayIngestionReady({ preserveInput: true, reason: "此功能需要先加载图表。普通文字聊天可直接发送。" })) {
        return;
      }
    }
    if (getOrCreateBlankSessionForSymbol && /^session-\d+$/i.test(String(session?.id || ""))) {
      session = await getOrCreateBlankSessionForSymbol(
        session?.symbol || state.topBar?.symbol || "NQ",
        session?.contractId || session?.symbol || state.topBar?.symbol || "NQ",
      );
    }
    const draftAttachmentsSnapshot = Array.isArray(session.draftAttachments)
      ? [...session.draftAttachments]
      : (Array.isArray(session.attachments) ? [...session.attachments] : []);
    try {
      await handleAiChat(composerPreset, message, session);
      session.draft = "";
      session.draftText = "";
      session.draftAttachments = [];
      session.attachments = [];
      els.aiChatInput.value = "";
      persistSessions();
      refreshChatUi();
    } catch (error) {
      session.draft = draftText;
      session.draftText = draftText;
      session.draftAttachments = draftAttachmentsSnapshot;
      session.attachments = [...draftAttachmentsSnapshot];
      els.aiChatInput.value = draftText;
      persistSessions();
      refreshChatUi();
      throw error;
    }
  }

  function handleComposerInput(value) {
    const session = getActiveThread();
    session.draft = value;
    session.draftText = value;
    persistSessions();
    scheduleDraftStateSync?.(session);
  }

  function bindStreamingControls() {
    els.aiChatStopButton?.addEventListener("click", () => {
      if (!activeStreamMeta) {
        renderStatusStrip([{ label: "当前没有正在生成的回复。", variant: "warn" }]);
        return;
      }
      els.aiChatStopButton.dataset.busy = "true";
      renderStatusStrip([{ label: "正在停止生成…", variant: "emphasis" }]);
      stopActiveStream().catch(() => {
        els.aiChatStopButton.dataset.busy = "false";
      });
    });
  }

  async function handlePresetAnalysis(preset, message, createNew = false) {
    if (isReplayRequiredPreset(preset) && !ensureReplayIngestionReady({ preserveInput: false, reason: "此功能需要先加载图表。普通文字聊天可直接发送。" })) {
      return { blocked: true };
    }
    const session = createNew
      ? (createNewAnalystSession
          ? await createNewAnalystSession({ activate: true })
          : (getOrCreateBlankSessionForSymbol
            ? getOrCreateBlankSessionForSymbol(state.topBar?.symbol || "NQ", state.topBar?.symbol || "NQ")
            : setActiveThread(createThreadId(), "新会话", {
                symbol: state.topBar?.symbol || "NQ",
                contractId: state.topBar?.symbol || "NQ",
                timeframe: state.topBar?.timeframe || "1m",
                windowRange: state.topBar?.quickRange || "最近7天",
              })))
      : getActiveThread();
    if (session?.analysisTemplate) {
      session.analysisTemplate = {
        ...session.analysisTemplate,
        type: preset || session.analysisTemplate.type || "general",
      };
    }
    await handleAiChat(preset, message, {
      id: session.id,
      title: session.title,
      symbol: session.symbol,
      contractId: session.contractId,
      timeframe: session.timeframe,
      windowRange: session.windowRange,
    });
  }

  function buildManualRegionAnalysisPrompt() {
    const latestRegion = state.manualRegions[state.manualRegions.length - 1];
    if (!latestRegion) {
      throw new Error("还没有手工区域。");
    }
    return `请围绕手工区域 ${latestRegion.label} 做标准分析，说明入场、止损、止盈和无效条件。`;
  }

  function buildSelectedBarAnalysisPrompt() {
    const candle = state.snapshot?.candles?.[state.selectedCandleIndex ?? -1];
    if (!candle) {
      throw new Error("还没有选中K线。");
    }
    return `请分析当前选中K线，时间=${new Date(candle.started_at).toLocaleString()} O=${candle.open} H=${candle.high} L=${candle.low} C=${candle.close}。请给出结构判断与交易建议。`;
  }

  async function createNewThread() {
    if (createNewAnalystSession) {
      try {
        return await createNewAnalystSession({ activate: true });
      } catch (error) {
        console.warn("新建会话失败:", error);
        renderStatusStrip?.([{ label: error?.message || String(error), variant: "warn" }]);
        return null;
      }
    }
    if (getOrCreateBlankSessionForSymbol) {
      return getOrCreateBlankSessionForSymbol(state.topBar?.symbol || "NQ", state.topBar?.symbol || "NQ");
    }
    const ordinal = String(state.aiThreads.length + 1).padStart(2, "0");
    return setActiveThread(`session-${ordinal}`, ordinal, {
      symbol: state.topBar?.symbol || "NQ",
      contractId: state.topBar?.symbol || "NQ",
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
    });
  }

  setStreamingUiState(false);

  return {
    handleAiChat,
    handleAiChatSend,
    handleComposerInput,
    handlePresetAnalysis,
    buildManualRegionAnalysisPrompt,
    buildSelectedBarAnalysisPrompt,
    createNewThread,
    bindStreamingControls,
    stopActiveStream,
    regenerateMessage,
  };
}
