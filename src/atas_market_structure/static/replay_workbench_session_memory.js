import { summarizeText } from "./replay_workbench_ui_utils.js";

const ACTIVE_PLAN_STATUSES = new Set(["active", "triggered", "tp_hit", "inactive_waiting_entry", "draft", "pending"]);
const INVALIDATED_PLAN_STATUSES = new Set(["invalidated", "sl_hit", "expired", "archived"]);
const COMPLETED_PLAN_STATUSES = new Set(["completed"]);
const KEY_ZONE_TYPES = new Set(["support_zone", "resistance_zone", "no_trade_zone", "zone"]);
const KEY_ANNOTATION_LIMIT = 8;
const ACTIVE_PLAN_LIMIT = 4;
const INVALIDATED_PLAN_LIMIT = 4;
const RECENT_EXCHANGE_LIMIT = 3;
const RECENT_MESSAGE_LIMIT = RECENT_EXCHANGE_LIMIT * 2;

function normalizeHandoffMode(mode) {
  if (mode === "minimal" || mode === "question_only") {
    return "question_only";
  }
  if (mode === "recent_3" || mode === "summary_plus_recent_3") {
    return "summary_plus_recent_3";
  }
  return "summary_only";
}

function cleanText(value) {
  return String(value || "").trim();
}

function hasValue(value) {
  if (value == null) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.values(value).some((item) => hasValue(item));
  }
  return cleanText(value).length > 0;
}

function uniqueBy(items = [], keySelector) {
  const map = new Map();
  items.forEach((item, index) => {
    if (!item) {
      return;
    }
    const key = keySelector(item) || `fallback-${index}`;
    map.set(key, item);
  });
  return Array.from(map.values());
}

function formatPriceValue(value) {
  if (value == null || value === "") {
    return "";
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric}` : cleanText(value);
}

function getRoleLabel(role) {
  return role === "assistant" ? "assistant" : role === "user" ? "user" : (role || "unknown");
}

function getMessagePlanCards(message = {}) {
  if (Array.isArray(message.planCards) && message.planCards.length) {
    return message.planCards;
  }
  if (Array.isArray(message.meta?.planCards) && message.meta.planCards.length) {
    return message.meta.planCards;
  }
  return [];
}

function listConversationMessages(session, { includePending = false } = {}) {
  return (session?.messages || [])
    .filter((item) => {
      const role = String(item?.role || "").trim().toLowerCase();
      if (!["user", "assistant"].includes(role)) {
        return false;
      }
      if (!includePending && item?.status === "pending") {
        return false;
      }
      const content = cleanText(item?.content);
      return !!content && content !== "正在思考中…";
    })
    .map((item) => ({
      message_id: item.message_id || null,
      role: String(item.role || "").trim().toLowerCase(),
      content: cleanText(item.content),
      summary: summarizeText(cleanText(item.content), item.role === "assistant" ? 120 : 100),
      model: item.model || item.meta?.model || null,
      reply_title: item.replyTitle || item.meta?.replyTitle || null,
      created_at: item.created_at || null,
      updated_at: item.updated_at || item.created_at || null,
    }));
}

function collectRecentConversation(session, { exchangeLimit = RECENT_EXCHANGE_LIMIT } = {}) {
  const limit = Math.max(exchangeLimit * 2, 2);
  return listConversationMessages(session).slice(-limit);
}

function normalizePlanLifecycle(status) {
  const raw = cleanText(status).toLowerCase() || "active";
  if (ACTIVE_PLAN_STATUSES.has(raw)) {
    return {
      status: raw,
      bucket: raw === "draft" || raw === "inactive_waiting_entry" || raw === "pending" ? "pending" : "active",
      label: raw === "inactive_waiting_entry" ? "待触发" : raw,
    };
  }
  if (INVALIDATED_PLAN_STATUSES.has(raw)) {
    return {
      status: raw,
      bucket: "invalidated",
      label: raw === "sl_hit" ? "止损触发" : raw,
    };
  }
  if (COMPLETED_PLAN_STATUSES.has(raw)) {
    return {
      status: raw,
      bucket: "completed",
      label: "completed",
    };
  }
  return {
    status: raw,
    bucket: "active",
    label: raw,
  };
}

function formatEntryPrice(plan = {}) {
  const low = formatPriceValue(plan.entryPriceLow ?? plan.entry_price_low);
  const high = formatPriceValue(plan.entryPriceHigh ?? plan.entry_price_high);
  if (low && high) {
    return `${low}-${high}`;
  }
  return formatPriceValue(plan.entryPrice ?? plan.entry_price);
}

function formatTargets(plan = {}) {
  const takeProfits = Array.isArray(plan.take_profits)
    ? plan.take_profits.map((item) => formatPriceValue(item?.target_price ?? item?.targetPrice)).filter(Boolean)
    : [];
  if (takeProfits.length) {
    return takeProfits.map((item, index) => `TP${index + 1} ${item}`).join(" / ");
  }
  const target1 = formatPriceValue(plan.targetPrice ?? plan.target_price);
  const target2 = formatPriceValue(plan.targetPrice2 ?? plan.target_price_2);
  return [target1 ? `TP1 ${target1}` : "", target2 ? `TP2 ${target2}` : ""].filter(Boolean).join(" / ");
}

function formatPlanSummary(plan = {}) {
  const lifecycle = normalizePlanLifecycle(plan.status);
  const side = cleanText(plan.side) === "sell" ? "空" : cleanText(plan.side) === "buy" ? "多" : "";
  const entry = formatEntryPrice(plan);
  const stop = formatPriceValue(plan.stopPrice ?? plan.stop_price);
  const targets = formatTargets(plan);
  return [
    cleanText(plan.title) || "AI计划卡",
    side ? `方向 ${side}` : "",
    entry ? `入场 ${entry}` : "",
    stop ? `止损 ${stop}` : "",
    targets,
    `状态 ${lifecycle.label}`,
  ].filter(Boolean).join("，");
}

function collectSessionPlanCards(session) {
  const messages = Array.isArray(session?.messages) ? session.messages : [];
  const collected = [];
  messages.forEach((message) => {
    getMessagePlanCards(message).forEach((plan) => {
      const planId = plan?.id || plan?.plan_id;
      if (!planId) {
        return;
      }
      collected.push({
        ...plan,
        id: planId,
        plan_id: plan?.plan_id || planId,
        message_id: plan?.message_id || message?.message_id || null,
        source_message_id: plan?.source_message_id || message?.message_id || null,
        updated_at: plan?.updated_at || message?.updated_at || message?.created_at || null,
      });
    });
  });
  return uniqueBy(collected, (plan) => plan.plan_id || plan.id)
    .sort((a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime());
}

function isPlanActive(plan) {
  const bucket = normalizePlanLifecycle(plan?.status).bucket;
  return bucket === "active" || bucket === "pending";
}

function isPlanInvalidated(plan) {
  return normalizePlanLifecycle(plan?.status).bucket === "invalidated";
}

function mapPlanForHandoff(plan = {}) {
  const lifecycle = normalizePlanLifecycle(plan.status);
  return {
    plan_id: plan.plan_id || plan.id || null,
    message_id: plan.message_id || null,
    title: cleanText(plan.title) || "AI计划卡",
    status: lifecycle.status,
    lifecycle_bucket: lifecycle.bucket,
    side: plan.side || null,
    entry_price: formatEntryPrice(plan) || null,
    stop_price: formatPriceValue(plan.stopPrice ?? plan.stop_price) || null,
    targets: formatTargets(plan) || null,
    summary: formatPlanSummary(plan),
    notes_summary: summarizeText(cleanText(plan.summary || plan.notes || ""), 120),
    confidence: plan.confidence ?? null,
    priority: plan.priority ?? null,
    updated_at: plan.updated_at || null,
  };
}

function listSessionAnnotations(state, session) {
  return (state?.aiAnnotations || [])
    .filter((item) => item?.session_id === session?.id && !item?.deleted)
    .map((item) => ({
      ...item,
      updated_at: item.updated_at || item.created_at || null,
      lifecycle_bucket: item.lifecycle_bucket || "active",
      lifecycle_stage: item.lifecycle_stage || "active",
    }))
    .sort((a, b) => {
      const scoreA = (a.pinned ? 100 : 0)
        + (a.visible === false ? 20 : 0)
        + (a.lifecycle_bucket === "active" ? 50 : 0)
        + (a.lifecycle_bucket === "pending" ? 40 : 0)
        + (KEY_ZONE_TYPES.has(cleanText(a.type).toLowerCase()) ? 10 : 0);
      const scoreB = (b.pinned ? 100 : 0)
        + (b.visible === false ? 20 : 0)
        + (b.lifecycle_bucket === "active" ? 50 : 0)
        + (b.lifecycle_bucket === "pending" ? 40 : 0)
        + (KEY_ZONE_TYPES.has(cleanText(b.type).toLowerCase()) ? 10 : 0);
      if (scoreA !== scoreB) {
        return scoreB - scoreA;
      }
      return new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime();
    });
}

function buildAnnotationPriceSummary(annotation = {}) {
  const low = formatPriceValue(annotation.price_low);
  const high = formatPriceValue(annotation.price_high);
  if (low && high) {
    return `${low}-${high}`;
  }
  const entry = formatPriceValue(annotation.entry_price);
  if (entry) {
    return entry;
  }
  const stop = formatPriceValue(annotation.stop_price);
  if (stop) {
    return stop;
  }
  const target = formatPriceValue(annotation.target_price);
  if (target) {
    return target;
  }
  return "";
}

function formatAnnotationSummary(annotation = {}) {
  const price = buildAnnotationPriceSummary(annotation);
  const status = cleanText(annotation.status) || cleanText(annotation.lifecycle_bucket) || "active";
  return [
    cleanText(annotation.label) || cleanText(annotation.annotation_id) || cleanText(annotation.id) || "AI对象",
    price,
    `状态 ${status}`,
    annotation.visible === false ? "隐藏" : "",
    annotation.pinned ? "已固定" : "",
  ].filter(Boolean).join("，");
}

function isKeyAnnotation(annotation = {}) {
  if (!annotation || annotation.deleted) {
    return false;
  }
  if (annotation.lifecycle_bucket === "archived" || annotation.status === "archived") {
    return false;
  }
  if (annotation.lifecycle_bucket === "active" || annotation.lifecycle_bucket === "pending") {
    return true;
  }
  if (annotation.pinned || annotation.visible === false) {
    return true;
  }
  return KEY_ZONE_TYPES.has(cleanText(annotation.type).toLowerCase());
}

function mapAnnotationForHandoff(annotation = {}) {
  return {
    annotation_id: annotation.annotation_id || annotation.id || null,
    object_id: annotation.object_id || annotation.annotation_id || annotation.id || null,
    message_id: annotation.message_id || null,
    plan_id: annotation.plan_id || null,
    type: annotation.type || null,
    event_kind: annotation.event_kind || null,
    label: cleanText(annotation.label) || "AI对象",
    status: cleanText(annotation.status) || "active",
    lifecycle_bucket: cleanText(annotation.lifecycle_bucket) || "active",
    lifecycle_stage: cleanText(annotation.lifecycle_stage) || "active",
    visible: annotation.visible !== false,
    pinned: !!annotation.pinned,
    price_hint: buildAnnotationPriceSummary(annotation) || null,
    summary: formatAnnotationSummary(annotation),
    updated_at: annotation.updated_at || annotation.created_at || null,
  };
}

function collectKeyAnnotations(state, session) {
  return listSessionAnnotations(state, session)
    .filter((item) => isKeyAnnotation(item))
    .slice(0, KEY_ANNOTATION_LIMIT)
    .map((item) => mapAnnotationForHandoff(item));
}

function buildDerivedMemory({ session, state, els, memory, replyText = "", userMessage = "", liveContextSummary = [], model = "" }) {
  const conversation = listConversationMessages(session);
  const latestUserTurn = [...conversation].reverse().find((item) => item.role === "user") || null;
  const latestAssistantTurn = [...conversation].reverse().find((item) => item.role === "assistant") || null;
  const annotations = listSessionAnnotations(state, session);
  const activeAnnotations = annotations.filter((item) => isKeyAnnotation(item));
  const zoneSummaries = activeAnnotations
    .filter((item) => KEY_ZONE_TYPES.has(cleanText(item.type).toLowerCase()))
    .slice(0, 8)
    .map((item) => summarizeText(formatAnnotationSummary(item), 100));
  const plans = collectSessionPlanCards(session);
  const activePlans = plans.filter((item) => isPlanActive(item)).slice(0, ACTIVE_PLAN_LIMIT);
  const invalidatedPlans = plans.filter((item) => isPlanInvalidated(item)).slice(0, INVALIDATED_PLAN_LIMIT);
  const latestQuestion = cleanText(userMessage) || latestUserTurn?.content || cleanText(memory.latest_question);
  const latestAnswerText = cleanText(replyText) || latestAssistantTurn?.content || "";
  const liveMarketSummary = summarizeText((Array.isArray(liveContextSummary) ? liveContextSummary : []).filter(Boolean).join("；"), 180);
  const fallbackMarketSummary = latestAssistantTurn ? summarizeText(latestAssistantTurn.content, 180) : "";
  return {
    active_model: model || session.activeModel || memory.active_model || "",
    symbol: session.symbol || state.topBar?.symbol || memory.symbol || "NQ",
    contract_id: session.contractId || memory.contract_id || session.symbol || state.topBar?.symbol || "NQ",
    timeframe: session.timeframe || state.topBar?.timeframe || memory.timeframe || "1m",
    window_range: session.windowRange || els?.statusWindowChip?.textContent || state.topBar?.quickRange || memory.window_range || "最近7天",
    user_goal_summary: cleanText(memory.user_goal_summary) || summarizeText(latestUserTurn?.content || latestQuestion, 120),
    market_context_summary: liveMarketSummary || cleanText(memory.market_context_summary) || fallbackMarketSummary,
    key_zones_summary: zoneSummaries.length
      ? zoneSummaries
      : (Array.isArray(memory.key_zones_summary) ? memory.key_zones_summary.slice(0, 8) : []),
    active_plans_summary: activePlans.map((item) => formatPlanSummary(item)).slice(0, 6),
    invalidated_plans_summary: invalidatedPlans.map((item) => formatPlanSummary(item)).slice(0, 6),
    important_messages: conversation.slice(-4).map((item) => `${item.role}: ${item.summary}`),
    current_user_intent: summarizeText(latestQuestion || cleanText(memory.current_user_intent), 100),
    latest_question: latestQuestion || cleanText(memory.latest_question),
    latest_answer_summary: latestAnswerText
      ? summarizeText(latestAnswerText, 180)
      : (cleanText(memory.latest_answer_summary) || fallbackMarketSummary),
    selected_annotations: activeAnnotations
      .slice(0, 12)
      .map((item) => item.id || item.annotation_id)
      .filter(Boolean),
    last_updated_at: new Date().toISOString(),
  };
}

function buildLocalHandoffPacketObject({ session, state, memory, targetModel = null, mode = "summary_only" }) {
  const normalizedMode = normalizeHandoffMode(mode);
  const plans = collectSessionPlanCards(session);
  const activePlans = plans
    .filter((item) => isPlanActive(item))
    .slice(0, ACTIVE_PLAN_LIMIT)
    .map((item) => mapPlanForHandoff(item));
  const invalidatedPlans = plans
    .filter((item) => isPlanInvalidated(item))
    .slice(0, INVALIDATED_PLAN_LIMIT)
    .map((item) => mapPlanForHandoff(item));
  const keyAnnotations = collectKeyAnnotations(state, session);
  const recentMessages = normalizedMode === "summary_plus_recent_3"
    ? collectRecentConversation(session).map((item) => ({
        message_id: item.message_id,
        role: item.role,
        content: item.content,
        summary: item.summary,
        model: item.model,
        reply_title: item.reply_title,
      }))
    : [];
  const latestQuestion = cleanText(memory.latest_question) || cleanText(memory.current_user_intent);
  if (normalizedMode === "question_only") {
    return {
      session_meta: {
        session_id: session.id,
        title: session.title || session.id,
        symbol: session.symbol || memory.symbol || "NQ",
        contract_id: session.contractId || memory.contract_id || session.symbol || memory.symbol || "NQ",
        timeframe: session.timeframe || memory.timeframe || "1m",
        window_range: session.windowRange || memory.window_range || "最近7天",
        target_model: targetModel || session.activeModel || memory.active_model || null,
        handoff_mode: normalizedMode,
      },
      memory_summary: {
        latest_question: latestQuestion || "",
        current_user_intent: cleanText(memory.current_user_intent) || latestQuestion || "",
        user_goal_summary: cleanText(memory.user_goal_summary) || "",
      },
      recent_messages: [],
      active_annotations: [],
      active_plans: [],
      invalidated_plans: [],
    };
  }
  return {
    session_meta: {
      session_id: session.id,
      title: session.title || session.id,
      symbol: session.symbol || memory.symbol || "NQ",
      contract_id: session.contractId || memory.contract_id || session.symbol || memory.symbol || "NQ",
      timeframe: session.timeframe || memory.timeframe || "1m",
      window_range: session.windowRange || memory.window_range || "最近7天",
      target_model: targetModel || session.activeModel || memory.active_model || null,
      handoff_mode: normalizedMode,
    },
    memory_summary: {
      ...memory,
      active_plans_summary: activePlans.map((item) => item.summary).slice(0, 6),
      invalidated_plans_summary: invalidatedPlans.map((item) => item.summary).slice(0, 6),
      selected_annotations: keyAnnotations.map((item) => item.annotation_id || item.object_id).filter(Boolean).slice(0, 12),
    },
    recent_messages: recentMessages,
    active_annotations: keyAnnotations,
    active_plans: activePlans,
    invalidated_plans: invalidatedPlans,
  };
}

function buildHandoffPreviewFromPacket(packet) {
  if (!packet || typeof packet !== "object") {
    return "";
  }
  const sessionMeta = packet.session_meta || {};
  const memory = packet.memory_summary || {};
  const recentMessages = Array.isArray(packet.recent_messages) ? packet.recent_messages : [];
  const activeAnnotations = Array.isArray(packet.active_annotations) ? packet.active_annotations : [];
  const activePlans = Array.isArray(packet.active_plans) ? packet.active_plans : [];
  const handoffMode = normalizeHandoffMode(sessionMeta.handoff_mode || "summary_only");

  if (handoffMode === "question_only") {
    return [
      "当前会话极简交接：",
      `- 品种：${sessionMeta.symbol || memory.symbol || "NQ"}`,
      `- 周期：${sessionMeta.timeframe || memory.timeframe || "1m"}`,
      `- 窗口：${sessionMeta.window_range || memory.window_range || "-"}`,
      `- 当前问题：${memory.latest_question || memory.current_user_intent || "无"}`,
    ].join("\n");
  }

  return [
    "当前会话交接摘要：",
    `- 品种：${sessionMeta.symbol || memory.symbol || "NQ"}`,
    `- 周期：${sessionMeta.timeframe || memory.timeframe || "1m"}`,
    `- 窗口：${sessionMeta.window_range || memory.window_range || "-"}`,
    `- 会话：${sessionMeta.title || sessionMeta.session_id || "未命名会话"}`,
    memory.user_goal_summary ? `- 用户目标：${memory.user_goal_summary}` : "",
    memory.current_user_intent ? `- 当前意图：${memory.current_user_intent}` : "",
    memory.market_context_summary ? `- 市场摘要：${memory.market_context_summary}` : "",
    Array.isArray(memory.key_zones_summary) && memory.key_zones_summary.length
      ? `- 关键区域：${memory.key_zones_summary.join("；")}`
      : "",
    activePlans.length
      ? `- 当前活动计划：\n${activePlans.map((item, index) => `  ${index + 1}. ${item.summary || item.title || item.plan_id}`).join("\n")}`
      : "- 当前活动计划：无",
    activeAnnotations.length
      ? `- 关键对象：\n${activeAnnotations.map((item, index) => `  ${index + 1}. ${item.summary || item.label || item.annotation_id}`).join("\n")}`
      : "- 关键对象：无",
    recentMessages.length
      ? `- 最近${Math.ceil(recentMessages.length / 2)}轮问答：\n${recentMessages.map((item) => `  ${getRoleLabel(item.role)}: ${item.summary || summarizeText(item.content || "", 90)}`).join("\n")}`
      : "",
    memory.latest_question ? `- 用户最新问题：${memory.latest_question}` : "",
    memory.latest_answer_summary ? `- 最近回答摘要：${memory.latest_answer_summary}` : "",
  ].filter(Boolean).join("\n");
}

function mergeHandoffPackets(localPacket, serverPacket, { targetModel = null, mode = "summary_only" } = {}) {
  if (!serverPacket || typeof serverPacket !== "object") {
    return localPacket;
  }
  const normalizedMode = normalizeHandoffMode(mode);
  return {
    ...localPacket,
    ...serverPacket,
    session_meta: {
      ...(localPacket.session_meta || {}),
      ...(serverPacket.session_meta || {}),
      target_model: targetModel
        || serverPacket.session_meta?.target_model
        || localPacket.session_meta?.target_model
        || null,
      handoff_mode: normalizedMode,
    },
    memory_summary: {
      ...(localPacket.memory_summary || {}),
      ...(serverPacket.memory_summary || {}),
    },
    recent_messages: Array.isArray(serverPacket.recent_messages) && serverPacket.recent_messages.length
      ? serverPacket.recent_messages
      : (localPacket.recent_messages || []),
    active_annotations: Array.isArray(serverPacket.active_annotations) && serverPacket.active_annotations.length
      ? serverPacket.active_annotations
      : (localPacket.active_annotations || []),
    active_plans: Array.isArray(serverPacket.active_plans) && serverPacket.active_plans.length
      ? serverPacket.active_plans
      : (localPacket.active_plans || []),
    invalidated_plans: Array.isArray(serverPacket.invalidated_plans) && serverPacket.invalidated_plans.length
      ? serverPacket.invalidated_plans
      : (localPacket.invalidated_plans || []),
  };
}

function compactRecentTurnsForContext(recentMessages = []) {
  return recentMessages
    .slice(-RECENT_MESSAGE_LIMIT)
    .map((item) => `${getRoleLabel(item.role)}: ${item.summary || summarizeText(item.content || "", 90)}`)
    .filter(Boolean);
}

function compactPlanSummariesForContext(plans = []) {
  return plans
    .slice(0, ACTIVE_PLAN_LIMIT)
    .map((item) => item.summary || item.title || item.plan_id)
    .filter(Boolean);
}

function compactAnnotationSummariesForContext(annotations = []) {
  return annotations
    .slice(0, KEY_ANNOTATION_LIMIT)
    .map((item) => item.summary || item.label || item.annotation_id)
    .filter(Boolean);
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

  function refreshStoredHandoffCaches(session) {
    if (session?.handoffPreviewTargetModel) {
      const previewPacket = buildLocalHandoffPacketObject({
        session,
        state,
        memory: ensureSessionMemory(session),
        targetModel: session.handoffPreviewTargetModel,
        mode: session.handoffPreviewMode || session.handoffMode,
      });
      session.handoffPreviewPacket = previewPacket;
      session.handoffPreviewSummary = buildHandoffPreviewFromPacket(previewPacket);
      session.handoffSummary = session.handoffPreviewSummary;
    }
    if (session?.lastHandoffTargetModel) {
      const committedPacket = buildLocalHandoffPacketObject({
        session,
        state,
        memory: ensureSessionMemory(session),
        targetModel: session.lastHandoffTargetModel,
        mode: session.lastHandoffMode || session.handoffMode,
      });
      session.lastHandoffPacket = committedPacket;
      session.lastHandoffSummary = buildHandoffPreviewFromPacket(committedPacket);
    }
  }

  function storeHandoffArtifacts(session, { packet, summary, targetModel = null, mode = "summary_only", commit = false }) {
    const normalizedMode = normalizeHandoffMode(mode);
    const generatedAt = new Date().toISOString();
    session.handoffSummary = summary || "";
    session.handoffPreviewPacket = packet || null;
    session.handoffPreviewSummary = summary || "";
    session.handoffPreviewAt = generatedAt;
    session.handoffPreviewTargetModel = targetModel || session.activeModel || session.memory?.active_model || "";
    session.handoffPreviewMode = normalizedMode;
    if (commit) {
      session.lastHandoffPacket = packet || null;
      session.lastHandoffSummary = summary || "";
      session.lastHandoffAt = generatedAt;
      session.lastHandoffTargetModel = targetModel || session.activeModel || session.memory?.active_model || "";
      session.lastHandoffMode = normalizedMode;
    }
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
    const localDerivedMemory = buildDerivedMemory({
      session,
      state,
      els,
      memory,
      model: session.activeModel || memory.active_model || "",
    });
    session.memory = {
      ...memory,
      ...localDerivedMemory,
    };

    if (forceServer && fetchJson) {
      try {
        const envelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/memory/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_model: session.activeModel || null,
            mode: normalizeHandoffMode(session.handoffMode),
          }),
        });
        const serverMemory = envelope?.memory;
        if (serverMemory && typeof serverMemory === "object") {
          session.memory = {
            ...session.memory,
            ...serverMemory,
          };
          session.memoryLoadedFromServer = true;
        }
      } catch (error) {
        console.warn("刷新会话记忆失败，保留本地摘要:", error);
      }
    }

    refreshStoredHandoffCaches(session);
    return ensureSessionMemory(session);
  }

  function updateFromAssistantResult(session, { replyText = "", userMessage = "", liveContextSummary = [], model = "" } = {}) {
    const memory = ensureSessionMemory(session);
    session.memory = {
      ...memory,
      ...buildDerivedMemory({
        session,
        state,
        els,
        memory,
        replyText,
        userMessage,
        liveContextSummary,
        model: model || session.activeModel || memory.active_model || "",
      }),
    };
    refreshStoredHandoffCaches(session);
    return ensureSessionMemory(session);
  }

  function buildLocalHandoffPacket(session, { targetModel = null, mode = null } = {}) {
    const normalizedMode = normalizeHandoffMode(mode || session?.handoffMode);
    const memory = ensureSessionMemory(session);
    const packet = buildLocalHandoffPacketObject({
      session,
      state,
      memory,
      targetModel,
      mode: normalizedMode,
    });
    return buildHandoffPreviewFromPacket(packet);
  }

  async function buildHandoffPacket(session, { forceServer = false, targetModel = null, commit = false } = {}) {
    if (!session) {
      return "";
    }
    const normalizedMode = normalizeHandoffMode(session.handoffMode);
    session.handoffMode = normalizedMode;
    await loadSessionMemory(session, { force: forceServer });
    await refreshSessionMemory(session, { forceServer });

    const localPacket = buildLocalHandoffPacketObject({
      session,
      state,
      memory: ensureSessionMemory(session),
      targetModel,
      mode: normalizedMode,
    });
    const localPreview = buildHandoffPreviewFromPacket(localPacket);

    if (!fetchJson) {
      storeHandoffArtifacts(session, {
        packet: localPacket,
        summary: localPreview,
        targetModel,
        mode: normalizedMode,
        commit,
      });
      return localPreview;
    }

    try {
      const envelope = await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/handoff`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_model: targetModel || session.activeModel || null,
          mode: normalizedMode,
        }),
      });
      const rawPacket = envelope?.handoff_packet || envelope?.preview || envelope?.handoff || envelope?.summary;
      const mergedPacket = typeof rawPacket === "object" && rawPacket !== null
        ? mergeHandoffPackets(localPacket, rawPacket, { targetModel, mode: normalizedMode })
        : localPacket;
      const preview = typeof rawPacket === "string"
        ? rawPacket
        : buildHandoffPreviewFromPacket(mergedPacket)
          || (typeof envelope?.summary === "string" ? envelope.summary : localPreview);
      if (rawPacket?.memory_summary && typeof rawPacket.memory_summary === "object") {
        session.memory = {
          ...ensureSessionMemory(session),
          ...rawPacket.memory_summary,
        };
        session.memoryLoadedFromServer = true;
      }
      storeHandoffArtifacts(session, {
        packet: mergedPacket,
        summary: preview || localPreview,
        targetModel,
        mode: normalizedMode,
        commit,
      });
      return preview || localPreview;
    } catch (error) {
      console.warn("加载交接摘要失败，回退本地摘要:", error);
      storeHandoffArtifacts(session, {
        packet: localPacket,
        summary: localPreview,
        targetModel,
        mode: normalizedMode,
        commit,
      });
      return localPreview;
    }
  }

  function buildOutgoingHandoffContext(session, { targetModel = null } = {}) {
    if (!session?.lastHandoffPacket) {
      return null;
    }
    const resolvedModel = cleanText(targetModel) || cleanText(session.activeModel) || cleanText(session.memory?.active_model);
    const handoffTargetModel = cleanText(session.lastHandoffTargetModel);
    if (resolvedModel && handoffTargetModel && resolvedModel !== handoffTargetModel) {
      return null;
    }
    const packet = session.lastHandoffPacket;
    const memory = packet.memory_summary || ensureSessionMemory(session);
    const recentMessages = Array.isArray(packet.recent_messages) ? packet.recent_messages : [];
    const activePlans = Array.isArray(packet.active_plans) ? packet.active_plans : [];
    const activeAnnotations = Array.isArray(packet.active_annotations) ? packet.active_annotations : [];
    const mode = normalizeHandoffMode(session.lastHandoffMode || packet.session_meta?.handoff_mode || session.handoffMode);
    const context = {
      model_handoff_annotations: compactAnnotationSummariesForContext(activeAnnotations),
      model_handoff_focus: {
        user_goal: cleanText(memory.user_goal_summary) || null,
        current_user_intent: cleanText(memory.current_user_intent) || null,
        latest_question: cleanText(memory.latest_question) || null,
        latest_answer_summary: cleanText(memory.latest_answer_summary) || null,
      },
      model_handoff_generated_at: session.lastHandoffAt || null,
      model_handoff_market: cleanText(memory.market_context_summary) || null,
      model_handoff_mode: mode,
      model_handoff_plans: compactPlanSummariesForContext(activePlans),
      model_handoff_session: {
        session_id: packet.session_meta?.session_id || session.id,
        session_title: packet.session_meta?.title || session.title || null,
        symbol: packet.session_meta?.symbol || memory.symbol || session.symbol || "NQ",
        timeframe: packet.session_meta?.timeframe || memory.timeframe || session.timeframe || "1m",
        window_range: packet.session_meta?.window_range || memory.window_range || session.windowRange || null,
        target_model: resolvedModel || handoffTargetModel || null,
      },
      model_handoff_summary: summarizeText(session.lastHandoffSummary || buildHandoffPreviewFromPacket(packet), 560),
    };
    if (mode === "summary_plus_recent_3" && recentMessages.length) {
      context.model_handoff_recent_turns = compactRecentTurnsForContext(recentMessages);
    }
    return Object.fromEntries(
      Object.entries(context).filter(([, value]) => hasValue(value)),
    );
  }

  return {
    ensureSessionMemory,
    loadSessionMemory,
    refreshSessionMemory,
    updateFromAssistantResult,
    buildLocalHandoffPacket,
    buildHandoffPacket,
    buildOutgoingHandoffContext,
    normalizeHandoffMode,
  };
}
