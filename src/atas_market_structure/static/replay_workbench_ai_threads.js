import { createMessageId, createPlanId, escapeHtml, formatPrice, summarizeText, writeStorage } from "./replay_workbench_ui_utils.js";

function isImageAttachment(attachment) {
  const kind = String(attachment?.kind || "").toLowerCase();
  const name = String(attachment?.name || "").toLowerCase();
  return kind.startsWith("image/") || kind.includes("screenshot") || /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name);
}

function buildAttachmentPreviewMarkup(attachment) {
  const label = escapeHtml(attachment.name || "附件");
  if (attachment.preview_url && isImageAttachment(attachment)) {
    return `
      <div class="attachment-thumb">
        <img src="${escapeHtml(attachment.preview_url)}" alt="${label}">
      </div>
    `;
  }
  return `<div class="attachment-thumb attachment-thumb-fallback">${escapeHtml((attachment.kind || "file").slice(0, 10))}</div>`;
}

function buildLongTextMarkup(text, limit = 220) {
  const safe = escapeHtml(text || "");
  if (!safe || safe.length <= limit) {
    return `<p>${safe}</p>`;
  }
  const preview = safe.slice(0, limit);
  return `
    <div class="longtext-block" data-longtext>
      <p class="longtext-preview">${preview}…</p>
      <p class="longtext-full" hidden>${safe}</p>
      <button type="button" class="secondary tiny longtext-toggle" data-longtext-toggle="expand">展开全文</button>
    </div>
  `;
}

function mapServerPlanCard(planCard, sessionId = null, messageId = null) {
  return {
    id: planCard.id || planCard.plan_id,
    title: planCard.title || "AI计划卡",
    status: planCard.status || "active",
    side: planCard.side || "buy",
    entryPrice: planCard.entryPrice ?? planCard.entry_price ?? null,
    entryPriceLow: planCard.entryPriceLow ?? planCard.entry_price_low ?? null,
    entryPriceHigh: planCard.entryPriceHigh ?? planCard.entry_price_high ?? null,
    stopPrice: planCard.stopPrice ?? planCard.stop_price ?? null,
    take_profits: Array.isArray(planCard.take_profits) ? planCard.take_profits : [],
    summary: planCard.summary || planCard.notes || "结构化交易计划",
    notes: planCard.notes || "",
    confidence: planCard.confidence ?? null,
    priority: planCard.priority ?? null,
    message_id: messageId || planCard.message_id || null,
    session_id: sessionId || planCard.session_id || null,
    plan_id: planCard.plan_id || planCard.id || null,
  };
}

function mapServerMessage(message, planCardsByMessage = new Map()) {
  const messageId = message.message_id || message.id || createMessageId();
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
  return normalizeSessionShape({
    ...fallback,
    id: sessionId,
    sessionId,
    title: serverSession.title || fallback.title || sessionId,
    pinned: !!serverSession.pinned,
    symbol,
    contractId: serverSession.contract_id || fallback.contractId || symbol,
    timeframe,
    windowRange,
    unreadCount: Number.isFinite(serverSession.unread_count) ? serverSession.unread_count : 0,
    selectedPromptBlockIds: Array.isArray(serverSession.selected_prompt_block_ids) ? serverSession.selected_prompt_block_ids : (fallback.selectedPromptBlockIds || []),
    pinnedContextBlockIds: Array.isArray(serverSession.pinned_context_block_ids) ? serverSession.pinned_context_block_ids : (fallback.pinnedContextBlockIds || []),
    mountedReplyIds: Array.isArray(serverSession.mounted_reply_ids) ? serverSession.mounted_reply_ids : (fallback.mountedReplyIds || []),
    activePlanId: serverSession.active_plan_id || fallback.activePlanId || null,
    scrollOffset: Number.isFinite(serverSession.scroll_offset) ? serverSession.scroll_offset : (fallback.scrollOffset || 0),
    draftText: serverSession.draft_text ?? fallback.draftText ?? fallback.draft ?? "",
    draft: serverSession.draft_text ?? fallback.draft ?? fallback.draftText ?? "",
    draftAttachments: Array.isArray(serverSession.draft_attachments) ? serverSession.draft_attachments : (fallback.draftAttachments || []),
    attachments: Array.isArray(fallback.attachments) ? fallback.attachments : [],
    activeModel: serverSession.active_model || fallback.activeModel || "",
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

function normalizeSessionShape(session, fallback = {}) {
  if (!session) return session;
  const symbol = session.symbol || session.memory?.symbol || fallback.symbol || "NQ";
  const timeframe = session.timeframe || session.memory?.timeframe || fallback.timeframe || "1m";
  const windowRange = session.windowRange || session.memory?.window_range || fallback.windowRange || "最近7天";
  session.sessionId = session.sessionId || session.id;
  session.symbol = symbol;
  session.contractId = session.contractId || symbol;
  session.timeframe = timeframe;
  session.windowRange = windowRange;
  session.unreadCount = Number.isFinite(session.unreadCount) ? session.unreadCount : 0;
  session.selectedPromptBlockIds = Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [];
  session.pinnedContextBlockIds = Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [];
  session.promptBlocks = Array.isArray(session.promptBlocks) ? session.promptBlocks : [];
  session.mountedReplyIds = Array.isArray(session.mountedReplyIds) ? session.mountedReplyIds : [];
  session.activePlanId = session.activePlanId || null;
  session.scrollOffset = Number.isFinite(session.scrollOffset) ? session.scrollOffset : 0;
  session.autoFollowChat = session.autoFollowChat ?? true;
  session.hasUnreadChatBelow = session.hasUnreadChatBelow ?? false;
  session.draftText = session.draftText ?? session.draft ?? "";
  session.draft = session.draftText;
  session.draftAttachments = Array.isArray(session.draftAttachments) ? session.draftAttachments : (Array.isArray(session.attachments) ? session.attachments : []);
  session.attachments = Array.isArray(session.attachments) ? session.attachments : [];
  session.handoffMode = session.handoffMode || "summary_only";
  session.memory = {
    ...(session.memory || {}),
    session_id: session.memory?.session_id || session.sessionId,
    symbol,
    timeframe,
    window_range: windowRange,
  };
  return session;
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
    session = {
      id: sessionId,
      sessionId: sessionId,
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
      promptBlocks: [],
      mountedReplyIds: [],
      activePlanId: null,
      scrollOffset: 0,
      autoFollowChat: true,
      hasUnreadChatBelow: false,
      messages: [],
      turns: [],
      draft: "",
      draftText: "",
      attachments: [],
      draftAttachments: [],
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

function buildPlanCardMarkup(planCard) {
  const metrics = [
    `方向 ${escapeHtml(planCard.side === "sell" ? "空" : planCard.side === "buy" ? "多" : "中性")}`,
    `入场 ${escapeHtml(formatPrice(planCard.entryPrice ?? planCard.entry_price ?? planCard.entryPriceLow ?? planCard.entry_price_low))}`,
    `止损 ${escapeHtml(formatPrice(planCard.stopPrice ?? planCard.stop_price))}`,
  ];
  const targets = planCard.take_profits || planCard.takeProfits || [];
  if (targets[0]?.target_price != null || planCard.targetPrice != null) {
    metrics.push(`TP1 ${escapeHtml(formatPrice(targets[0]?.target_price ?? planCard.targetPrice))}`);
  }
  if (targets[1]?.target_price != null || planCard.targetPrice2 != null) {
    metrics.push(`TP2 ${escapeHtml(formatPrice(targets[1]?.target_price ?? planCard.targetPrice2))}`);
  }
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
  const kind = escapeHtml(attachment.kind || "file");
  return `<div class="attachment-chip">${buildAttachmentPreviewMarkup(attachment)}<div class="attachment-chip-meta"><span>${label}</span><span class="meta">${kind}</span></div></div>`;
}

function renderMessage(message) {
  const metaChips = [];
  if (message.status) {
    metaChips.push(`<span class="chip ${escapeHtml(message.status)}">${escapeHtml(message.status)}</span>`);
  }
  if (message.meta?.preset) {
    metaChips.push(`<span class="chip">${escapeHtml(message.meta.preset)}</span>`);
  }
  if (message.meta?.model || message.meta?.provider) {
    metaChips.push(`<span class="chip emphasis">${escapeHtml([message.meta?.provider, message.meta?.model].filter(Boolean).join("/"))}</span>`);
  }
  const planCards = Array.isArray(message.meta?.planCards) ? message.meta.planCards : [];
  const attachments = Array.isArray(message.meta?.attachments) ? message.meta.attachments : [];
  return `
    <div class="chat-message ${escapeHtml(message.role)} ${escapeHtml(message.status || "")}" data-message-id="${escapeHtml(message.message_id || "")}">
      <div class="chat-bubble ${escapeHtml(message.role)} ${escapeHtml(message.status || "")}">
        <div class="chat-bubble-body">
          ${buildLongTextMarkup(message.content || "")}
          ${attachments.length ? `<div class="chat-attachment-list">${attachments.map((item) => renderAttachmentPreview(item)).join("")}</div>` : ""}
          ${metaChips.length ? `<div class="chat-meta">${metaChips.join("")}</div>` : ""}
          ${message.role === "assistant" ? `<div class="chat-message-actions"><button type="button" class="secondary tiny" data-message-action="regenerate" data-message-id="${escapeHtml(message.message_id || "")}">重新生成</button></div>` : ""}
          ${planCards.length ? `<div class="chat-plan-card-list">${planCards.map((item) => buildPlanCardMarkup(item)).join("")}</div>` : ""}
        </div>
      </div>
    </div>
  `;
}

function applyReplyMountState(session, messageId, { mounted = true, objectIds = [] } = {}) {
  if (!session || !messageId) {
    return null;
  }
  let updatedMessage = null;
  session.messages = (session.messages || []).map((message) => {
    if (message.message_id !== messageId) {
      return message;
    }
    updatedMessage = {
      ...message,
      mountedToChart: mounted,
      mountedObjectIds: Array.isArray(objectIds) ? objectIds : [],
      meta: {
        ...(message.meta || {}),
        mountedToChart: mounted,
        mountedObjectIds: Array.isArray(objectIds) ? objectIds : [],
      },
    };
    return updatedMessage;
  });
  return updatedMessage;
}

function buildPinnedPlanMarkup(planCard) {
  const targets = planCard.take_profits || [];
  const lines = [
    `${escapeHtml(planCard.title || "AI计划卡")}`,
    `方向：${escapeHtml(planCard.side === "sell" ? "做空" : "做多")}`,
    `入场：${escapeHtml(formatPrice(planCard.entryPrice ?? planCard.entry_price ?? planCard.entryPriceLow ?? planCard.entry_price_low))}`,
    `止损：${escapeHtml(formatPrice(planCard.stopPrice ?? planCard.stop_price))}`,
    targets[0]?.target_price != null ? `TP1：${escapeHtml(formatPrice(targets[0]?.target_price))}` : "",
    targets[1]?.target_price != null ? `TP2：${escapeHtml(formatPrice(targets[1]?.target_price))}` : "",
    planCard.summary ? escapeHtml(planCard.summary) : "",
  ].filter(Boolean);
  return lines.join("<br>");
}

function renderAuxiliaryStrips(session, els, state, onPlanAction = null, fetchJson = null) {
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
    els.sessionContextStrip.innerHTML = `
      <div class="strip-head"><span class="strip-title">会话主信息</span></div>
      <div class="meta">${parts.join(" | ") || "当前会话还没有形成主信息摘要。"}</div>
    `;
  }

  if (els.promptSelectionBar) {
    const selectedBlocks = selectedPromptBlockIds
      .map((blockId) => promptBlocks.find((item) => item.blockId === blockId || item.id === blockId))
      .filter(Boolean);
    const blockPreviewCache = session.promptBlockPreviewCache || {};
    const syncPromptBlockSelection = () => {
      session.selectedPromptBlockIds = selectedBlocks
        .map((block) => block.blockId || block.id)
        .filter(Boolean);
      session.pinnedContextBlockIds = (session.pinnedContextBlockIds || []).filter((blockId) => session.selectedPromptBlockIds.includes(blockId));
      persistSessions(state);
      renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson);
    };
    const loadPromptBlockDetail = async (blockId) => {
      if (!fetchJson || !blockId || blockPreviewCache[blockId]?.loaded) {
        return;
      }
      try {
        const envelope = await fetchJson(`/api/v1/workbench/chat/prompt-blocks/${encodeURIComponent(blockId)}`);
        const detail = envelope?.prompt_block || envelope?.block || envelope || {};
        blockPreviewCache[blockId] = {
          loaded: true,
          content: detail.full_payload != null
            ? JSON.stringify(detail.full_payload, null, 2)
            : detail.raw_text || detail.preview_text || detail.previewText || "暂无原始内容",
        };
        session.promptBlockPreviewCache = blockPreviewCache;
        persistSessions(state);
        renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson);
      } catch (error) {
        blockPreviewCache[blockId] = {
          loaded: true,
          content: `加载失败：${error.message || String(error)}`,
        };
        session.promptBlockPreviewCache = blockPreviewCache;
        persistSessions(state);
        renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson);
      }
    };
    const chips = selectedBlocks.map((block) => {
      const blockId = block.blockId || block.id;
      const label = block.title || block.preview_text || block.previewText || block.kind || blockId;
      const preview = block.previewText || block.preview_text || "";
      const pinned = Array.isArray(session.pinnedContextBlockIds) && session.pinnedContextBlockIds.includes(blockId);
      const isActive = Array.isArray(session.selectedPromptBlockIds) && session.selectedPromptBlockIds[session.selectedPromptBlockIds.length - 1] === blockId;
      const expanded = !!blockPreviewCache[blockId]?.loaded;
      const expandedContent = blockPreviewCache[blockId]?.content || "";
      return `
        <span class="strip-chip prompt-chip ${pinned ? "pinned" : ""} ${isActive ? "active" : ""}" data-prompt-block-id="${escapeHtml(blockId)}" title="${escapeHtml(preview || label)}">
          <span class="strip-chip-text">
            <span class="strip-chip-title">${escapeHtml(label)}</span>
            ${preview && preview !== label ? `<span class="strip-chip-meta">${escapeHtml(preview)}</span>` : ""}
            ${expandedContent ? `<span class="strip-chip-detail">${escapeHtml(expandedContent)}</span>` : ""}
          </span>
          <span class="strip-chip-actions">
            <button type="button" class="strip-chip-action" data-prompt-block-toggle-pin="${escapeHtml(blockId)}" aria-label="${pinned ? "取消固定" : "固定上下文"}">${pinned ? "取消固定" : "固定"}</button>
            <button type="button" class="strip-chip-action" data-prompt-block-expand="${escapeHtml(blockId)}" aria-label="查看原始内容">${expanded ? "刷新详情" : "查看详情"}</button>
            <button type="button" class="strip-chip-remove" data-prompt-block-remove="${escapeHtml(blockId)}" aria-label="移除上下文">×</button>
          </span>
        </span>
      `;
    });
    if (!chips.length) {
      chips.push(`<div class="strip-empty-state">当前还没有显式选择的 Prompt block。</div>`);
    }
    els.promptSelectionBar.hidden = false;
    if (chips.length) {
      els.promptSelectionBar.innerHTML = `
        <div class="strip-head"><span class="strip-title">本次发送上下文</span></div>
        <div class="strip-chip-row">${chips.join("")}</div>
      `;
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
          persistSessions(state);
          renderAuxiliaryStrips(session, els, state, onPlanAction, fetchJson);
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
    if (!chips.length) {
      chips.push(`<div class="strip-empty-state">当前没有挂载到图表的回复。</div>`);
    }
    els.mountedReplyStrip.hidden = false;
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
    const pinnedPlanId = state?.pinnedPlanId || null;
    const pinnedMessage = (session.messages || []).find((message) => Array.isArray(message.meta?.planCards) && message.meta.planCards.some((item) => (item.id || item.plan_id) === pinnedPlanId));
    const pinnedPlan = pinnedMessage?.meta?.planCards?.find((item) => (item.id || item.plan_id) === pinnedPlanId) || null;
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
  writeStorage("sessions", state.aiThreads);
  writeStorage("workbench", {
    activeAiThreadId: state.activeAiThreadId,
    drawerState: state.drawerState,
    topBar: state.topBar,
    pinnedPlanId: state.pinnedPlanId || null,
  });
}

export function createAiThreadController({ state, els, onPlanAction = null, onMountedRepliesChanged = null, fetchJson = null, renderStatusStrip = null, onSessionActivated = null }) {
  const CHAT_FOLLOW_THRESHOLD = 48;

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

  function renderSessionMoreMenu() {
    if (!els.sessionMoreMenu) {
      return;
    }
    const nonPinned = state.aiThreads.filter((item) => !item.pinned);
    els.sessionMoreMenu.innerHTML = nonPinned.length
      ? nonPinned.map((item) => `<button type="button" class="secondary tiny session-more-item" data-thread-id="${escapeHtml(item.id)}">${escapeHtml(item.title)}</button>`).join("")
      : `<div class="empty-note">暂无更多会话</div>`;
    els.sessionMoreMenu.querySelectorAll("button[data-thread-id]").forEach((button) => {
      button.addEventListener("click", () => {
        setActiveThread(button.dataset.threadId);
        els.sessionMoreMenu.hidden = true;
      });
    });
  }

  function renderAttachments(session) {
    if (!els.attachmentPreviewBar || !els.attachmentPreviewList) {
      return;
    }
    const attachments = Array.isArray(session.attachments) ? session.attachments : [];
    els.attachmentPreviewBar.hidden = attachments.length === 0;
    els.attachmentPreviewList.innerHTML = attachments.map((item, index) => `
      <div class="attachment-row">
        ${buildAttachmentPreviewMarkup(item)}
        <div class="attachment-row-main">
          <span>${escapeHtml(item.name || `附件${index + 1}`)}</span>
          <div class="button-row tight">
            <span class="meta">${escapeHtml(item.kind || "file")}</span>
            <button type="button" class="secondary tiny" data-attachment-remove="${index}">删除</button>
          </div>
        </div>
      </div>
    `).join("");
    els.attachmentPreviewList.querySelectorAll("button[data-attachment-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        attachments.splice(Number(button.dataset.attachmentRemove), 1);
        session.attachments = attachments;
        renderAttachments(session);
        persistSessions(state);
      });
    });
  }

  async function hydrateSessionFromServer(sessionId, { activate = false } = {}) {
    if (!fetchJson) {
      return getSessionById(state, sessionId);
    }
    const fallback = getSessionById(state, sessionId) || null;
    const sessionEnvelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(sessionId)}`);
    const serverSession = sessionEnvelope?.session;
    if (!serverSession) {
      return fallback;
    }
    const thread = mapServerSessionToThread(serverSession, fallback || {});
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
          annotations.push(...objects.annotations.map((item) => ({ ...item, id: item.annotation_id || item.id })));
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

  async function syncSessionsFromServer({ activateFirst = false, symbol = null } = {}) {
    if (!fetchJson) {
      return state.aiThreads;
    }
    const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
    const envelope = await fetchJson(`/api/v1/workbench/chat/sessions${query}`);
    const sessions = Array.isArray(envelope?.sessions) ? envelope.sessions : [];
    if (!sessions.length) {
      return state.aiThreads;
    }
    const mapped = sessions.map((item, index) => mapServerSessionToThread(item, state.aiThreads[index] || {}));
    state.aiThreads = mapped;
    if (activateFirst && mapped.length) {
      const currentId = state.activeAiThreadId;
      const next = mapped.find((item) => item.id === currentId) || mapped[0];
      state.activeAiThreadId = next.id;
      await hydrateSessionFromServer(next.id, { activate: true });
    }
    persistSessions(state);
    return state.aiThreads;
  }

  function setActiveThread(threadId, title = "01", overrides = {}) {
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
      session.loadingFromServer = true;
      renderAiChat();
      hydrateSessionFromServer(session.id, { activate: true })
        .then((hydrated) => {
          if (hydrated) {
            hydrated.loadingFromServer = false;
            renderAiThreadTabs();
            renderAiChat();
          }
        })
        .catch((error) => {
          session.loadingFromServer = false;
          console.warn("加载会话失败:", error);
          renderStatusStrip?.([{ label: error.message || String(error), variant: "warn" }]);
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

  async function createBackendSession({ title = "新会话", symbol = null, contractId = null, timeframe = null, windowRange = null, activate = true } = {}) {
    if (!fetchJson) {
      return createThread(title, { symbol, contractId, timeframe, windowRange });
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
    const thread = mapServerSessionToThread(serverSession, { symbol: sessionSymbol, contractId: contractId || sessionSymbol, timeframe: sessionTimeframe, windowRange });
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

  const getOrCreateBlankSessionForSymbol = (symbol, contractId = symbol) => {
    const normalizedSymbol = String(symbol || "").trim().toUpperCase() || "NQ";
    const existing = state.aiThreads.find((thread) => {
      const scope = getSessionScope(thread, state);
      return scope.symbol === normalizedSymbol && (!thread.messages?.length || !thread.memory?.latest_question);
    });
    if (existing) {
      return setActiveThread(existing.id, existing.title, { symbol: normalizedSymbol, contractId });
    }
    const title = `${normalizedSymbol}-${String(state.aiThreads.filter((thread) => getSessionScope(thread, state).symbol === normalizedSymbol).length + 1).padStart(2, "0")}`;
    if (fetchJson) {
      return createBackendSession({
        title,
        symbol: normalizedSymbol,
        contractId,
        timeframe: state.topBar?.timeframe || "1m",
        windowRange: state.topBar?.quickRange || "最近7天",
        activate: true,
      });
    }
    return createThread(title, {
      symbol: normalizedSymbol,
      contractId,
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
    });
  };

  function renderAiThreadTabs() {
    if (!els.aiThreadTabs) return;
    els.aiThreadTabs.innerHTML = "";
    const currentScope = getSessionScope(getActiveThread(), state);
    const currentSymbol = currentScope.symbol;
    const relevantThreads = state.aiThreads.filter((thread) => {
      const threadScope = getSessionScope(thread, state);
      return threadScope.symbol === currentSymbol;
    }).sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return (b.memory?.last_updated_at || "").localeCompare(a.memory?.last_updated_at || "");
    });
    relevantThreads.slice(0, 8).forEach((thread) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `thread-tab ${thread.id === state.activeAiThreadId ? "active" : ""}`.trim();
      button.textContent = thread.title;
      button.addEventListener("click", () => setActiveThread(thread.id, thread.title));
      els.aiThreadTabs.appendChild(button);
    });
    renderSessionMoreMenu();
  }

  function appendAiChatMessage(role, content, meta = {}, threadId = null, threadTitle = "01") {
    const session = ensureSession(state, threadId || state.activeAiThreadId, threadTitle);
    const mergedMeta = {
      ...meta,
      attachments: meta.attachments || (role === "user" ? [...(session.attachments || [])] : meta.attachments),
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
      session.draftAttachments = [];
      session.memory.latest_question = content;
      session.memory.current_user_intent = summarizeText(content, 80);
      session.attachments = [];
    } else {
      session.memory.latest_answer_summary = summarizeText(content, 160);
      session.memory.important_messages = session.messages.slice(-4).map((item) => summarizeText(item.content, 80));
    }
    session.memory.last_updated_at = new Date().toISOString();
    renderAiChat();
    renderAiThreadTabs();
    renderAttachments(session);
    persistSessions(state);
    return message;
  }

  function syncSessionMemorySummary(session) {
    els.currentSessionTitle.textContent = `当前会话：${session.title}`;
    els.currentSessionModelLabel.textContent = `模型：${session.activeModel || session.memory?.active_model || "服务端默认"}`;
    const memory = session.memory || {};
    const summaryParts = [
      memory.current_user_intent,
      memory.latest_answer_summary,
      Array.isArray(memory.active_plans_summary) && memory.active_plans_summary.length
        ? `活动计划：${memory.active_plans_summary.join("；")}`
        : "",
    ].filter(Boolean);
    els.sessionMemorySummary.textContent = summaryParts.join(" | ") || "当前会话还没有摘要。";
  }

  function renderAiChat() {
    const session = getActiveThread();
    const shouldAutoFollow = session.autoFollowChat !== false || isNearChatBottom();
    syncSessionMemorySummary(session);
    renderAuxiliaryStrips(session, els, state, onPlanAction);
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
      els.aiChatThread.innerHTML = `<div class="chat-empty-state">当前会话还没有消息。先发送问题，或用分析模板创建 AI 计划。</div>`;
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
        planCards: Array.isArray(message.planCards) && message.planCards.length ? message.planCards : message.meta?.planCards,
      },
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
          const plan = session.messages
            .flatMap((item) => item.meta?.planCards || [])
            .find((item) => (item.id || item.plan_id) === planId);
          const summary = [plan?.title, plan?.summary].filter(Boolean).join(" | ");
          if (summary && navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(summary).catch(() => {});
          }
          return;
        }
        if (action === "recap") {
          const plan = session.messages
            .flatMap((item) => item.meta?.planCards || [])
            .find((item) => (item.id || item.plan_id) === planId);
          if (plan) {
            state.aiReview = {
              model: session.activeModel || session.memory?.active_model || "AI计划卡",
              review: `${plan.title}\n${plan.summary || ""}`.trim(),
            };
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
        const expanded = button.dataset.longtextToggle === "collapse";
        if (preview) preview.hidden = !expanded;
        if (full) full.hidden = expanded;
        button.dataset.longtextToggle = expanded ? "expand" : "collapse";
        button.textContent = expanded ? "展开全文" : "收起";
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
    const normalized = {
      id: planCard.id || planCard.plan_id || createPlanId(),
      title: planCard.title || "AI计划卡",
      status: planCard.status || "active",
      side: planCard.side || "buy",
      entryPrice: planCard.entryPrice ?? planCard.entry_price ?? null,
      stopPrice: planCard.stopPrice ?? planCard.stop_price ?? null,
      take_profits: planCard.take_profits || [],
      summary: planCard.summary || planCard.notes || "结构化交易计划",
      message_id: messageId,
      session_id: session.id,
    };
    session.memory.active_plans_summary = Array.from(new Set([...(session.memory.active_plans_summary || []), `${normalized.title} ${normalized.status}`]));
    persistSessions(state);
    return normalized;
  }

  function renameActiveThread(nextTitle) {
    const session = getActiveThread();
    session.title = nextTitle || session.title;
    renderAiThreadTabs();
    renderAiChat();
    persistSessions(state);
  }

  function togglePinActiveThread() {
    const session = getActiveThread();
    session.pinned = !session.pinned;
    renderAiThreadTabs();
    persistSessions(state);
  }

  function deleteActiveThread() {
    if (state.aiThreads.length <= 1) {
      return false;
    }
    const currentId = state.activeAiThreadId;
    state.aiThreads = state.aiThreads.filter((item) => item.id !== currentId);
    state.activeAiThreadId = state.aiThreads[0].id;
    setActiveThread(state.activeAiThreadId, state.aiThreads[0].title);
    persistSessions(state);
    return true;
  }

  function addAttachments(items = []) {
    const session = getActiveThread();
    session.attachments = [...(session.attachments || []), ...items];
    renderAttachments(session);
    persistSessions(state);
  }

  function addPromptBlock(block, { selected = true, pinned = false } = {}) {
    const session = getActiveThread();
    if (!block) return null;
    const normalizedBlock = {
      ...block,
      id: block.id || block.blockId || block.block_id || `${block.kind || "block"}-${Date.now()}`,
      blockId: block.blockId || block.block_id || block.id || `${block.kind || "block"}-${Date.now()}`,
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
    session.attachments = [];
    session.draftAttachments = [];
    renderAttachments(session);
    persistSessions(state);
  }

  return {
    ensureThread: ensureSession,
    getActiveThread,
    setActiveThread,
    createBackendSession,
    hydrateSessionFromServer,
    syncSessionsFromServer,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    upsertPlanCardToSession,
    renameActiveThread,
    togglePinActiveThread,
    deleteActiveThread,
    addAttachments,
    clearAttachments,
    addPromptBlock,
    setMountedReplyIds,
    bindChatScrollBehavior,
    scrollChatToBottom,
    updateChatFollowState,
    persistSessions: () => persistSessions(state),
  };
}
