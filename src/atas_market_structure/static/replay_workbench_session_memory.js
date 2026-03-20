import { summarizeText } from "./replay_workbench_ui_utils.js";

function normalizeHandoffMode(mode) {
  if (mode === "minimal" || mode === "question_only") {
    return "question_only";
  }
  if (mode === "recent_3" || mode === "summary_plus_recent_3") {
    return "summary_plus_recent_3";
  }
  return "summary_only";
}

export function createSessionMemoryEngine({ state, els, fetchJson }) {
  function ensureSessionMemory(session) {
    session.memory = session.memory || {};
    session.memory.session_id = session.id;
    session.memory.summary_version = session.memory.summary_version || 1;
    session.memory.active_model = session.activeModel || session.memory.active_model || "";
    session.memory.symbol = state.topBar?.symbol || session.memory.symbol || "NQ";
    session.memory.timeframe = state.topBar?.timeframe || session.memory.timeframe || "1m";
    session.memory.window_range = els?.statusWindowChip?.textContent || state.topBar?.quickRange || session.memory.window_range || "最近7天";
    session.memory.user_goal_summary = session.memory.user_goal_summary || "";
    session.memory.market_context_summary = session.memory.market_context_summary || "";
    session.memory.key_zones_summary = Array.isArray(session.memory.key_zones_summary) ? session.memory.key_zones_summary : [];
    session.memory.active_plans_summary = Array.isArray(session.memory.active_plans_summary) ? session.memory.active_plans_summary : [];
    session.memory.invalidated_plans_summary = Array.isArray(session.memory.invalidated_plans_summary) ? session.memory.invalidated_plans_summary : [];
    session.memory.important_messages = Array.isArray(session.memory.important_messages) ? session.memory.important_messages : [];
    session.memory.current_user_intent = session.memory.current_user_intent || "";
    session.memory.latest_question = session.memory.latest_question || "";
    session.memory.latest_answer_summary = session.memory.latest_answer_summary || "";
    session.memory.selected_annotations = Array.isArray(session.memory.selected_annotations) ? session.memory.selected_annotations : [];
    session.memory.last_updated_at = session.memory.last_updated_at || null;
    return session.memory;
  }

  async function loadSessionMemory(session, { force = false } = {}) {
    if (!session) {
      return null;
    }
    const memory = ensureSessionMemory(session);
    if (!fetchJson) {
      return refreshSessionMemory(session);
    }
    if (!force && session.memoryLoadedFromServer && memory.last_updated_at) {
      return memory;
    }
    try {
      const envelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/memory`);
      const serverMemory = envelope?.memory;
      if (serverMemory && typeof serverMemory === "object") {
        session.memory = {
          ...memory,
          ...serverMemory,
        };
        session.memoryLoadedFromServer = true;
        return ensureSessionMemory(session);
      }
    } catch (error) {
      console.warn("加载会话记忆失败，回退本地摘要:", error);
    }
    return refreshSessionMemory(session);
  }

  async function refreshSessionMemory(session, { forceServer = false } = {}) {
    const memory = ensureSessionMemory(session);
    const sessionAnnotations = (state.aiAnnotations || []).filter((item) => item.session_id === session.id);
    memory.active_model = session.activeModel || memory.active_model || "";
    memory.symbol = session.symbol || state.topBar?.symbol || memory.symbol || "NQ";
    memory.contract_id = session.contractId || memory.contract_id || memory.symbol || "NQ";
    memory.timeframe = session.timeframe || state.topBar?.timeframe || memory.timeframe || "1m";
    memory.window_range = session.windowRange || els?.statusWindowChip?.textContent || state.topBar?.quickRange || memory.window_range || "最近7天";
    memory.key_zones_summary = Array.from(new Set([
      ...(memory.key_zones_summary || []),
      ...sessionAnnotations
        .filter((item) => ["support_zone", "resistance_zone", "no_trade_zone"].includes(item.type))
        .map((item) => item.label)
        .filter(Boolean),
    ])).slice(-8);
    memory.selected_annotations = sessionAnnotations
      .filter((item) => item.status !== "archived")
      .map((item) => item.id)
      .slice(-12);
    memory.important_messages = (session.messages || []).slice(-4).map((item) => summarizeText(item.content, 80));
    memory.last_updated_at = new Date().toISOString();

    if (forceServer && fetchJson) {
      try {
        const envelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/memory/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: session.activeModel || null,
            handoff_mode: normalizeHandoffMode(session.handoffMode),
          }),
        });
        const serverMemory = envelope?.memory;
        if (serverMemory && typeof serverMemory === "object") {
          session.memory = {
            ...memory,
            ...serverMemory,
          };
          session.memoryLoadedFromServer = true;
          return ensureSessionMemory(session);
        }
      } catch (error) {
        console.warn("刷新会话记忆失败，保留本地摘要:", error);
      }
    }
    return memory;
  }

  function updateFromAssistantResult(session, { replyText = "", userMessage = "", liveContextSummary = [], model = "" } = {}) {
    const memory = ensureSessionMemory(session);
    memory.active_model = model || session.activeModel || memory.active_model || "";
    memory.symbol = session.symbol || state.topBar?.symbol || memory.symbol || "NQ";
    memory.contract_id = session.contractId || memory.contract_id || memory.symbol || "NQ";
    memory.timeframe = session.timeframe || state.topBar?.timeframe || memory.timeframe || "1m";
    memory.window_range = session.windowRange || els?.statusWindowChip?.textContent || state.topBar?.quickRange || memory.window_range || "最近7天";
    const sessionAnnotations = (state.aiAnnotations || []).filter((item) => item.session_id === session.id);
    memory.key_zones_summary = Array.from(new Set([
      ...(memory.key_zones_summary || []),
      ...sessionAnnotations
        .filter((item) => ["support_zone", "resistance_zone", "no_trade_zone"].includes(item.type))
        .map((item) => item.label)
        .filter(Boolean),
    ])).slice(-8);
    memory.selected_annotations = sessionAnnotations
      .filter((item) => item.status !== "archived")
      .map((item) => item.id)
      .slice(-12);
    memory.important_messages = (session.messages || []).slice(-4).map((item) => summarizeText(item.content, 80));
    memory.latest_answer_summary = summarizeText(replyText, 180);
    memory.market_context_summary = summarizeText((liveContextSummary || []).join("；"), 180);
    memory.current_user_intent = summarizeText(userMessage, 100);
    memory.user_goal_summary = memory.user_goal_summary || summarizeText(userMessage, 120);
    memory.latest_question = userMessage || memory.latest_question || "";
    memory.last_updated_at = new Date().toISOString();
    return memory;
  }

  function buildLocalHandoffPacket(session) {
    const memory = ensureSessionMemory(session);
    const activeAnnotations = (state.aiAnnotations || []).filter((item) => item.session_id === session.id && item.visible !== false);
    const activePlans = memory.active_plans_summary || [];
    const recentTurns = (session.messages || []).slice(-3).map((item) => `${item.role}: ${item.content}`).join("\n");
    const mode = normalizeHandoffMode(session.handoffMode);

    if (mode === "question_only") {
      return [
        `当前会话极简交接：`,
        `- 品种：${session.symbol || state.topBar?.symbol || "NQ"}`,
        `- 周期：${session.timeframe || state.topBar?.timeframe || "1m"}`,
        `- 当前问题：${memory.latest_question || memory.current_user_intent || "无"}`,
      ].join("\n");
    }

    return [
      `当前会话交接摘要：`,
      `- 品种：${session.symbol || state.topBar?.symbol || "NQ"}`,
      `- 周期：${session.timeframe || state.topBar?.timeframe || "1m"}`,
      `- 窗口：${session.windowRange || els?.statusWindowChip?.textContent || memory.window_range || "-"}`,
      `- 用户当前目标：${memory.current_user_intent || memory.user_goal_summary || "待补充"}`,
      `- 市场摘要：${memory.market_context_summary || "待补充"}`,
      `- 关键区域：${(memory.key_zones_summary || []).join("；") || activeAnnotations.filter((item) => ["support_zone", "resistance_zone", "no_trade_zone"].includes(item.type)).map((item) => item.label).join("；") || "无"}`,
      `- 当前活动计划：${activePlans.join("；") || "无"}`,
      `- 关键对象状态：${activeAnnotations.map((item) => `${item.label}(${item.status})`).join("；") || "无"}`,
      mode === "summary_plus_recent_3" ? `- 最近3轮原文：\n${recentTurns || "无"}` : "",
      `- 用户最新问题：${memory.latest_question || "无"}`,
    ].filter(Boolean).join("\n");
  }

  async function buildHandoffPacket(session, { forceServer = false } = {}) {
    if (!session) {
      return "";
    }
    session.handoffMode = normalizeHandoffMode(session.handoffMode);
    await loadSessionMemory(session, { force: forceServer });
    await refreshSessionMemory(session, { forceServer });
    const localPreview = buildLocalHandoffPacket(session);
    if (!fetchJson) {
      session.handoffSummary = localPreview;
      return localPreview;
    }
    try {
      const envelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/handoff`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: session.activeModel || null,
          handoff_mode: session.handoffMode,
        }),
      });
      const packet = envelope?.handoff_packet || envelope?.preview || envelope?.handoff || envelope?.summary;
      const text = typeof packet === "string"
        ? packet
        : typeof packet?.content === "string"
          ? packet.content
          : typeof envelope?.summary === "string"
            ? envelope.summary
            : localPreview;
      session.handoffSummary = text || localPreview;
      if (envelope?.memory && typeof envelope.memory === "object") {
        session.memory = {
          ...ensureSessionMemory(session),
          ...envelope.memory,
        };
        session.memoryLoadedFromServer = true;
      }
      return session.handoffSummary;
    } catch (error) {
      console.warn("加载交接摘要失败，回退本地摘要:", error);
      session.handoffSummary = localPreview;
      return localPreview;
    }
  }

  return {
    ensureSessionMemory,
    loadSessionMemory,
    refreshSessionMemory,
    updateFromAssistantResult,
    buildLocalHandoffPacket,
    buildHandoffPacket,
    normalizeHandoffMode,
  };
}
