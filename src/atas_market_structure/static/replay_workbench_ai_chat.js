import { createPlanId, summarizeText, writeStorage } from "./replay_workbench_ui_utils.js";

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
  return {
    id: raw.id || `${planId || session.id}-${messageId}-${type}-${Math.random().toString(36).slice(2, 8)}`,
    session_id: raw.session_id || session.id,
    message_id: raw.message_id || messageId,
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
    status: raw.status || (isPendingPlanChild ? "inactive_waiting_entry" : "active"),
    priority: raw.priority ?? null,
    confidence: raw.confidence ?? null,
    visible: raw.visible !== false,
    pinned: !!raw.pinned,
    source_kind: raw.source_kind || "replay_analysis",
    side: raw.side || null,
    entry_price: raw.entry_price ?? raw.entryPrice ?? null,
    stop_price: raw.stop_price ?? raw.stopPrice ?? null,
    target_price: raw.target_price ?? raw.targetPrice ?? null,
    tp_level: raw.tp_level ?? null,
    price_low: raw.price_low ?? raw.low ?? null,
    price_high: raw.price_high ?? raw.high ?? null,
    path_points: raw.path_points || [],
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
  return {
    blockId: `pb-${preset}-${now}`,
    kind: preset || "user_input",
    title: titleMap[preset] || titleMap.general,
    previewText: summarizeText(message, 60),
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
    ephemeral: raw.ephemeral ?? fallback.ephemeral ?? true,
    pinned: !!(raw.pinned ?? fallback.pinned),
  };
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
}) {
  let activeStreamController = null;
  let activeStreamMeta = null;

  async function buildPromptBlocks(session, request) {
    const payload = {
      replay_ingestion_id: state.currentReplayIngestionId,
      preset: request.preset || "general",
      symbol: session.symbol || state.topBar?.symbol || "NQ",
      contract_id: session.contractId || session.symbol || state.topBar?.symbol || "NQ",
      timeframe: session.timeframe || state.topBar?.timeframe || "1m",
      user_input: request.userInput || "",
      analysis_type: request.analysisType || session.analysisTemplate?.type || request.preset || "general",
      analysis_range: request.analysisRange || session.analysisTemplate?.range || "current_window",
      analysis_style: request.analysisStyle || session.analysisTemplate?.style || "standard",
      include_memory_summary: !!request.includeMemorySummary,
      include_recent_messages: !!request.includeRecentMessages,
      attachments: Array.isArray(request.attachments) ? request.attachments : [],
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
      live_context_summary: payload.liveContextSummary || current?.meta?.live_context_summary || [],
      follow_up_suggestions: payload.followUpSuggestions || current?.meta?.follow_up_suggestions || [],
      status: payload.status || "completed",
    }, runtime, eventData);
    mergeMessageAnnotations(state, session, resolvedMessageId, structuredPlanCards, structuredAnnotations);
    return assistantMessage;
  }

  function failStreamingMessage(session, pendingMessageId, error, runtime = {}, eventData = {}) {
    return syncStreamingMessage(session, pendingMessageId, {
      content: error?.message || String(error || "流式输出失败"),
      provider: "local-error",
      model: "-",
      replyTitle: "AI 对话失败",
      status: "failed",
    }, runtime, eventData);
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
  async function regenerateMessage(messageId) {
    const session = getActiveThread();
    if (!messageId) {
      return null;
    }
    renderStatusStrip([{ label: "正在重新生成…", variant: "emphasis" }]);
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
  }

  async function handleAiChat(preset, userMessage, threadMeta = null) {
    const trimmedMessage = String(userMessage || "").trim();
    if (!trimmedMessage) {
      throw new Error("请输入要分析的问题。");
    }
    if (!state.currentReplayIngestionId) {
      throw new Error("没有可分析的 replay ingestion。先加载图表。");
    }
    const descriptor = threadMeta || getPresetThreadMeta(preset);
    const session = setActiveThread(descriptor.id, descriptor.title, {
      symbol: descriptor.symbol || threadMeta?.symbol || state.topBar?.symbol,
      contractId: descriptor.contractId || threadMeta?.contractId || descriptor.symbol || threadMeta?.symbol || state.topBar?.symbol,
      timeframe: descriptor.timeframe || threadMeta?.timeframe || state.topBar?.timeframe,
      windowRange: descriptor.windowRange || threadMeta?.windowRange || state.topBar?.quickRange,
    });
    const includeMemorySummary = !!(session.memory?.user_goal_summary || session.memory?.market_context_summary || session.memory?.latest_answer_summary);
    const includeRecentMessages = Array.isArray(session.messages) && session.messages.length > 1;
    const builtBlocks = await buildPromptBlocks(session, {
      preset,
      userInput: trimmedMessage,
      analysisType: session.analysisTemplate?.type,
      analysisRange: session.analysisTemplate?.range,
      analysisStyle: session.analysisTemplate?.style,
      includeMemorySummary,
      includeRecentMessages,
      attachments: Array.isArray(session.attachments)
        ? session.attachments
            .map((item) => ({
              name: item.name || null,
              media_type: item.kind || item.media_type || "image/png",
              data_url: item.data_url || item.preview_url || "",
            }))
            .filter((item) => item.data_url)
        : [],
    });
    const selectedBlockIds = [];
    builtBlocks.forEach((block, index) => {
      const normalizedBlock = addPromptBlock?.(block, { selected: true, pinned: !!block.pinned }) || block;
      if (index === 0 && normalizedBlock?.blockId) {
        selectedBlockIds.push(normalizedBlock.blockId);
      }
    });
    const effectiveSelectedBlockIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : selectedBlockIds;
    const effectivePinnedBlockIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
    appendAiChatMessage("user", trimmedMessage, {
      preset,
      selected_block_ids: effectiveSelectedBlockIds,
      pinned_block_ids: effectivePinnedBlockIds,
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
      const baseHistory = session.messages.map((item) => ({ role: item.role, content: item.content }));
      const selectedBlockIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
      const pinnedBlockIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
      const includeMemorySummary = !!(session.memory?.user_goal_summary || session.memory?.market_context_summary || session.memory?.latest_answer_summary);
      const includeRecentMessages = baseHistory.length > 1;
      const requestPayload = {
        replay_ingestion_id: state.currentReplayIngestionId,
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
        attachments: Array.isArray(session.attachments)
          ? session.attachments
              .map((item) => ({
                name: item.name || null,
                media_type: item.kind || item.media_type || "image/png",
                data_url: item.data_url || item.preview_url || "",
              }))
              .filter((item) => item.data_url)
          : [],
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
      throw error;
    }
  }

  async function handleAiChatSend() {
    const session = getActiveThread();
    const message = els.aiChatInput.value.trim();
    if (!message) {
      return;
    }
    session.draft = "";
    session.draftText = "";
    els.aiChatInput.value = "";
    persistSessions();
    await handleAiChat(session.analysisTemplate?.type || "general", message, session);
  }

  function handleComposerInput(value) {
    const session = getActiveThread();
    session.draft = value;
    session.draftText = value;
    persistSessions();
  }

  function bindStreamingControls() {
    els.aiChatStopButton?.addEventListener("click", () => {
      stopActiveStream();
    });
  }

  async function handlePresetAnalysis(preset, message, createNew = false) {
    const session = createNew
      ? (getOrCreateBlankSessionForSymbol
          ? getOrCreateBlankSessionForSymbol(state.topBar?.symbol || "NQ", state.topBar?.symbol || "NQ")
          : setActiveThread(createThreadId(), "新会话", {
              symbol: state.topBar?.symbol || "NQ",
              contractId: state.topBar?.symbol || "NQ",
              timeframe: state.topBar?.timeframe || "1m",
              windowRange: state.topBar?.quickRange || "最近7天",
            }))
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

  function createNewThread() {
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
