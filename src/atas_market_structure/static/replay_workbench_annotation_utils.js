export const DEFAULT_ANNOTATION_FILTERS = Object.freeze({
  onlyCurrentSession: true,
  hideCompleted: true,
  sessionIds: [],
  messageIds: [],
  annotationIds: [],
  objectTypes: ["entry_line", "stop_loss", "take_profit", "support_zone", "resistance_zone", "no_trade_zone", "zone"],
  showPaths: false,
  showInvalidated: false,
  selectedOnly: false,
});

const ANNOTATION_TYPE_LABELS = Object.freeze({
  entry_line: "开仓建议",
  stop_loss: "止损",
  take_profit: "止盈",
  support_zone: "支撑区",
  resistance_zone: "阻力区",
  no_trade_zone: "无交易区",
  zone: "价格区间",
  path_arrow: "路径箭头",
});

function toCleanString(value) {
  return String(value || "").trim();
}

function toFiniteNumber(value) {
  if (value == null || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toArray(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (value == null) {
    return [];
  }
  return [value];
}

function buildGeneratedId(prefix = "item") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizePlanTakeProfitItem(item, index = 0) {
  const raw = item && typeof item === "object"
    ? item
    : { target_price: item };
  const level = toFiniteNumber(raw.tp_level ?? raw.level ?? raw.index ?? index + 1) ?? index + 1;
  const price = toFiniteNumber(raw.target_price ?? raw.targetPrice ?? raw.price ?? raw.value);
  const label = toCleanString(raw.label || raw.name || "");
  if (price == null && !label) {
    return null;
  }
  return {
    ...raw,
    id: toCleanString(raw.id || raw.take_profit_id || "") || `tp-${level}`,
    level,
    tp_level: level,
    price,
    target_price: price,
    targetPrice: price,
    label: label || null,
    status: toCleanString(raw.status || raw.state || "active") || "active",
  };
}

function normalizeSupportingZone(zone, index = 0) {
  if (!zone || typeof zone !== "object") {
    return zone;
  }
  const priceLow = toFiniteNumber(zone.price_low ?? zone.priceLow ?? zone.low);
  const priceHigh = toFiniteNumber(zone.price_high ?? zone.priceHigh ?? zone.high);
  return {
    ...zone,
    id: toCleanString(zone.id || zone.zone_id || "") || `zone-${index + 1}`,
    type: toCleanString(zone.type || zone.zone_type || "support_zone") || "support_zone",
    price_low: priceLow,
    price_high: priceHigh,
    priceLow: priceLow,
    priceHigh: priceHigh,
    label: toCleanString(zone.label || zone.title || ""),
    reason: toCleanString(zone.reason || zone.notes || zone.summary || ""),
  };
}

function normalizeInvalidationItem(item, index = 0) {
  if (item == null) {
    return null;
  }
  if (typeof item !== "object") {
    const reason = toCleanString(item);
    return reason ? { id: `invalidation-${index + 1}`, type: "note", price: null, reason } : null;
  }
  return {
    ...item,
    id: toCleanString(item.id || item.invalidation_id || "") || `invalidation-${index + 1}`,
    type: toCleanString(item.type || item.kind || "rule") || "rule",
    price: toFiniteNumber(item.price ?? item.level ?? item.threshold),
    reason: toCleanString(item.reason || item.note || item.summary || ""),
  };
}

function buildTimeValidity(raw = {}) {
  const source = raw.time_validity && typeof raw.time_validity === "object"
    ? raw.time_validity
    : {};
  const expiresAt = toCleanString(raw.expires_at || source.expires_at || "");
  const minutes = toFiniteNumber(source.minutes);
  const mode = toCleanString(source.mode || (expiresAt ? "timestamp" : minutes != null ? "duration" : ""));
  if (!mode && minutes == null && !expiresAt) {
    return null;
  }
  return {
    ...source,
    mode: mode || null,
    minutes,
    expires_at: expiresAt || null,
  };
}

function deriveAnnotationEventKind(type = "", planId = null) {
  if (planId) {
    return "plan";
  }
  if (["support_zone", "resistance_zone", "zone"].includes(type)) {
    return "zone";
  }
  if (["no_trade_zone", "stop_loss"].includes(type)) {
    return "risk";
  }
  if (type === "path_arrow") {
    return "path";
  }
  return "price";
}

function buildFallbackPreferenceSignature(annotation = {}, fallback = {}) {
  const type = toCleanString(annotation.type || annotation.annotation_type || annotation.subtype || "annotation");
  const sessionId = toCleanString(annotation.session_id || fallback.sessionId || "");
  const messageId = toCleanString(annotation.message_id || fallback.messageId || "");
  const planId = toCleanString(annotation.plan_id || fallback.planId || "");
  const tpLevel = annotation.tp_level != null ? `tp-${annotation.tp_level}` : "";
  const priceAnchor = [
    annotation.entry_price,
    annotation.stop_price,
    annotation.target_price,
    annotation.price_low,
    annotation.price_high,
  ].find((value) => value != null);
  const label = toCleanString(annotation.label || annotation.title || "");
  return [
    planId || messageId || sessionId || "annotation",
    type,
    tpLevel,
    priceAnchor != null ? String(priceAnchor) : "",
    label,
  ].filter(Boolean).join(":");
}

export function resolveChartViewTimeWindow(state = null) {
  const candles = Array.isArray(state?.snapshot?.candles) ? state.snapshot.candles : [];
  const maxIndex = Math.max(0, candles.length - 1);
  const snapshotWindowStart = state?.snapshot?.window_start || null;
  const snapshotWindowEnd = state?.snapshot?.window_end || null;
  if (candles.length && state?.chartView) {
    const rawStartIndex = Number(state.chartView.startIndex);
    const rawEndIndex = Number(state.chartView.endIndex);
    const startIndex = Math.max(0, Math.min(Number.isFinite(rawStartIndex) ? Math.floor(rawStartIndex) : maxIndex, maxIndex));
    const endIndex = Math.max(
      startIndex,
      Math.min(Number.isFinite(rawEndIndex) ? Math.ceil(rawEndIndex) : maxIndex, maxIndex),
    );
    const startTime = candles[startIndex]?.started_at || candles[startIndex]?.ended_at || snapshotWindowStart;
    const endTime = candles[endIndex]?.ended_at || candles[endIndex]?.started_at || snapshotWindowEnd || startTime;
    if (startTime || endTime) {
      return {
        startTime: startTime || endTime || new Date().toISOString(),
        endTime: endTime || startTime || new Date().toISOString(),
        startIndex,
        endIndex,
      };
    }
  }
  const latestCandle = candles.length ? candles[candles.length - 1] : null;
  const startTime = latestCandle?.started_at || snapshotWindowStart || new Date().toISOString();
  const endTime = latestCandle?.ended_at || latestCandle?.started_at || snapshotWindowEnd || startTime;
  return {
    startTime,
    endTime,
    startIndex: candles.length ? maxIndex : null,
    endIndex: candles.length ? maxIndex : null,
  };
}

export function createDefaultAnnotationFilters() {
  return {
    ...DEFAULT_ANNOTATION_FILTERS,
    sessionIds: [...DEFAULT_ANNOTATION_FILTERS.sessionIds],
    messageIds: [...DEFAULT_ANNOTATION_FILTERS.messageIds],
    annotationIds: [...DEFAULT_ANNOTATION_FILTERS.annotationIds],
    objectTypes: [...DEFAULT_ANNOTATION_FILTERS.objectTypes],
  };
}

export function normalizeAnnotationPreferences(value = {}) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.entries(value).reduce((acc, [key, item]) => {
    const normalizedKey = toCleanString(key);
    if (!normalizedKey || !item || typeof item !== "object") {
      return acc;
    }
    acc[normalizedKey] = {
      visible: item.visible !== false,
      pinned: !!item.pinned,
      deleted: !!item.deleted,
    };
    return acc;
  }, {});
}

export function buildAnnotationPreferenceKey(annotation = {}, fallback = {}) {
  const sessionId = toCleanString(annotation.session_id || fallback.sessionId || "global");
  const stableId = toCleanString(
    annotation.preference_key
    || annotation.annotation_preference_key
    || annotation.annotation_id
    || annotation.object_id
    || annotation.id,
  );
  if (stableId) {
    return `${sessionId}::${stableId}`;
  }
  return `${sessionId}::${buildFallbackPreferenceSignature(annotation, fallback) || "annotation"}`;
}

export function applyAnnotationPreferences(annotation = {}, preferences = {}, fallback = {}) {
  const preferenceKey = annotation.preference_key || buildAnnotationPreferenceKey(annotation, fallback);
  const record = preferences?.[preferenceKey];
  return {
    ...annotation,
    preference_key: preferenceKey,
    visible: record && Object.prototype.hasOwnProperty.call(record, "visible")
      ? record.visible !== false
      : annotation.visible !== false,
    pinned: record && Object.prototype.hasOwnProperty.call(record, "pinned")
      ? !!record.pinned
      : !!annotation.pinned,
    deleted: record && Object.prototype.hasOwnProperty.call(record, "deleted")
      ? !!record.deleted
      : !!annotation.deleted,
  };
}

export function updateAnnotationPreference(preferences = {}, annotation = {}, patch = {}) {
  const nextPreferences = normalizeAnnotationPreferences(preferences);
  const preferenceKey = annotation.preference_key || buildAnnotationPreferenceKey(annotation, {
    sessionId: annotation.session_id,
    messageId: annotation.message_id,
    planId: annotation.plan_id,
  });
  const current = nextPreferences[preferenceKey] || {
    visible: annotation.visible !== false,
    pinned: !!annotation.pinned,
    deleted: !!annotation.deleted,
  };
  nextPreferences[preferenceKey] = {
    ...current,
    ...patch,
    visible: Object.prototype.hasOwnProperty.call(patch, "visible")
      ? patch.visible !== false
      : current.visible !== false,
    pinned: Object.prototype.hasOwnProperty.call(patch, "pinned")
      ? !!patch.pinned
      : !!current.pinned,
    deleted: Object.prototype.hasOwnProperty.call(patch, "deleted")
      ? !!patch.deleted
      : !!current.deleted,
  };
  return nextPreferences;
}

export function normalizeLifecycleStatus(status, type = "") {
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

export function normalizeWorkbenchPlanCard(raw = {}, fallback = {}) {
  const planId = toCleanString(raw.id || raw.plan_id || fallback.planId || "") || buildGeneratedId("plan");
  const sessionId = toCleanString(raw.session_id || raw.sessionId || fallback.sessionId || "") || null;
  const messageId = toCleanString(raw.message_id || raw.messageId || fallback.messageId || "") || null;
  const entryPriceLow = toFiniteNumber(raw.entryPriceLow ?? raw.entry_price_low);
  const entryPriceHigh = toFiniteNumber(raw.entryPriceHigh ?? raw.entry_price_high);
  const explicitEntryPrice = toFiniteNumber(raw.entryPrice ?? raw.entry_price);
  const entryPrice = explicitEntryPrice ?? (entryPriceLow != null && entryPriceHigh != null && entryPriceLow === entryPriceHigh ? entryPriceLow : null);
  const stopPrice = toFiniteNumber(raw.stopPrice ?? raw.stop_price);
  const takeProfits = (
    Array.isArray(raw.take_profits) ? raw.take_profits : (
      Array.isArray(raw.takeProfits) ? raw.takeProfits : [raw.targetPrice ?? raw.target_price, raw.targetPrice2 ?? raw.target_price_2]
    )
  )
    .map((item, index) => normalizePlanTakeProfitItem(item, index))
    .filter(Boolean);
  const targetPrice = takeProfits[0]?.target_price ?? toFiniteNumber(raw.targetPrice ?? raw.target_price);
  const targetPrice2 = takeProfits[1]?.target_price ?? toFiniteNumber(raw.targetPrice2 ?? raw.target_price_2);
  const supportingZones = toArray(raw.supporting_zones ?? raw.supportingZones ?? raw.zones)
    .map((item, index) => normalizeSupportingZone(item, index))
    .filter(Boolean);
  const invalidations = toArray(raw.invalidations)
    .map((item, index) => normalizeInvalidationItem(item, index))
    .filter(Boolean);
  const timeValidity = buildTimeValidity(raw);
  const expiresAt = toCleanString(raw.expires_at || timeValidity?.expires_at || "") || null;
  const summary = String(raw.summary || raw.notes || fallback.summary || fallback.notes || "结构化交易计划").trim() || "结构化交易计划";
  const notes = String(raw.notes || fallback.notes || "").trim();
  const sourceKind = toCleanString(raw.source_kind || raw.sourceKind || fallback.sourceKind || "replay_analysis") || "replay_analysis";
  const annotationRefs = toArray(raw.annotation_refs ?? raw.annotationRefs).map((item) => toCleanString(item)).filter(Boolean);
  const confidence = toFiniteNumber(raw.confidence ?? fallback.confidence);
  const riskReward = toFiniteNumber(raw.risk_reward ?? raw.riskReward ?? fallback.risk_reward ?? fallback.riskReward);
  return {
    ...raw,
    id: planId,
    plan_id: planId,
    session_id: sessionId,
    message_id: messageId,
    title: String(raw.title || fallback.title || "AI计划卡").trim() || "AI计划卡",
    side: toCleanString(raw.side || fallback.side || "buy") || "buy",
    entry_type: toCleanString(raw.entry_type || raw.entryType || (entryPriceLow != null && entryPriceHigh != null ? "zone" : "point")) || "point",
    entryPrice,
    entry_price: entryPrice,
    entryPriceLow: entryPriceLow,
    entry_price_low: entryPriceLow,
    entryPriceHigh: entryPriceHigh,
    entry_price_high: entryPriceHigh,
    stopPrice,
    stop_price: stopPrice,
    targetPrice,
    target_price: targetPrice,
    targetPrice2,
    target_price_2: targetPrice2,
    take_profits: takeProfits,
    supporting_zones: supportingZones,
    invalidations,
    time_validity: timeValidity,
    expires_at: expiresAt,
    risk_reward: riskReward,
    confidence,
    priority: raw.priority ?? fallback.priority ?? null,
    status: toCleanString(raw.status || fallback.status || "active") || "active",
    source_kind: sourceKind,
    notes,
    summary,
    annotation_refs: annotationRefs,
  };
}

export function normalizeWorkbenchAnnotation(raw = {}, {
  session = null,
  sessionId = null,
  messageId = null,
  state = null,
  planId = null,
  defaultSourceKind = "replay_analysis",
  defaultType = "entry_line",
  defaultStatus = null,
  sourceReplyTitle = null,
} = {}) {
  const resolvedSessionId = toCleanString(raw.session_id || raw.sessionId || sessionId || session?.id || session?.sessionId || "") || null;
  const resolvedMessageId = toCleanString(raw.message_id || raw.messageId || messageId || "") || null;
  const resolvedPlanId = toCleanString(raw.plan_id || raw.planId || planId || "") || null;
  const chartWindow = resolveChartViewTimeWindow(state);
  const now = new Date().toISOString();
  const startTime = raw.start_time || chartWindow.startTime || state?.snapshot?.window_start || now;
  const endTime = raw.end_time || chartWindow.endTime || state?.snapshot?.window_end || startTime;
  const type = toCleanString(raw.type || raw.annotation_type || raw.subtype || defaultType) || "entry_line";
  const isPendingPlanChild = ["stop_loss", "take_profit"].includes(type) && raw.status == null && !!resolvedPlanId;
  const normalizedLifecycle = normalizeLifecycleStatus(raw.status || defaultStatus || (isPendingPlanChild ? "inactive_waiting_entry" : "active"), type);
  const createdAt = raw.created_at || raw.createdAt || startTime;
  const updatedAt = raw.updated_at || raw.updatedAt || endTime || createdAt;
  const symbol = toCleanString(raw.symbol || session?.symbol || session?.memory?.symbol || state?.topBar?.symbol || state?.snapshot?.instrument_symbol || "") || "";
  const timeframe = toCleanString(raw.timeframe || session?.timeframe || session?.memory?.timeframe || state?.topBar?.timeframe || state?.snapshot?.display_timeframe || "") || "";
  const expiresAt = toCleanString(raw.expires_at || raw.time_validity?.expires_at || "") || null;
  const entryPrice = toFiniteNumber(raw.entry_price ?? raw.entryPrice);
  const stopPrice = toFiniteNumber(raw.stop_price ?? raw.stopPrice);
  const targetPrice = toFiniteNumber(raw.target_price ?? raw.targetPrice);
  const priceLow = toFiniteNumber(raw.price_low ?? raw.priceLow ?? raw.low);
  const priceHigh = toFiniteNumber(raw.price_high ?? raw.priceHigh ?? raw.high);
  const price = toFiniteNumber(raw.price ?? entryPrice ?? stopPrice ?? targetPrice);
  const triggerMode = toCleanString(raw.trigger_mode || raw.triggerMode || (["support_zone", "resistance_zone", "zone", "no_trade_zone"].includes(type) ? "range_touch" : "touch")) || "touch";
  const lifecycle = raw.lifecycle && typeof raw.lifecycle === "object"
    ? raw.lifecycle
    : {
        terminate_on_touch: ["entry_line", "stop_loss", "take_profit"].includes(type),
        terminate_on_time: !!expiresAt,
        terminate_on_invalidation: !!resolvedPlanId || ["support_zone", "resistance_zone", "zone", "no_trade_zone"].includes(type),
      };
  const generatedId = raw.id
    || raw.annotation_id
    || raw.object_id
    || `${resolvedPlanId || resolvedSessionId || "annotation"}-${resolvedMessageId || "message"}-${type}-${Math.random().toString(36).slice(2, 8)}`;
  return applyAnnotationPreferences({
    ...raw,
    id: generatedId,
    annotation_id: raw.annotation_id || raw.id || generatedId,
    object_id: raw.object_id || raw.annotation_id || raw.id || generatedId,
    preference_key: buildAnnotationPreferenceKey(raw, {
      sessionId: resolvedSessionId,
      messageId: resolvedMessageId,
      planId: resolvedPlanId,
    }),
    session_id: resolvedSessionId,
    message_id: resolvedMessageId,
    source_message_id: toCleanString(raw.source_message_id || raw.message_id || resolvedMessageId) || null,
    plan_id: resolvedPlanId,
    symbol,
    timeframe,
    type,
    subtype: toCleanString(raw.subtype || "") || null,
    label: toCleanString(raw.label || raw.title || raw.name || "AI标记") || "AI标记",
    reason: String(raw.reason || raw.notes || raw.summary || "").trim(),
    start_time: startTime,
    end_time: endTime,
    expires_at: expiresAt,
    price,
    trigger_mode: triggerMode,
    status: normalizedLifecycle.status,
    lifecycle_stage: raw.lifecycle_stage || normalizedLifecycle.lifecycle_stage,
    lifecycle_bucket: raw.lifecycle_bucket || normalizedLifecycle.lifecycle_bucket,
    lifecycle_terminal: raw.lifecycle_terminal ?? normalizedLifecycle.terminal,
    lifecycle_outcome: raw.lifecycle_outcome || normalizedLifecycle.outcome,
    visual_state: raw.visual_state || normalizedLifecycle.visual_state,
    priority: raw.priority ?? null,
    confidence: toFiniteNumber(raw.confidence),
    visible: raw.visible !== false,
    pinned: !!raw.pinned,
    deleted: !!raw.deleted,
    source_kind: toCleanString(raw.source_kind || raw.sourceKind || defaultSourceKind) || "replay_analysis",
    event_kind: toCleanString(raw.event_kind || deriveAnnotationEventKind(type, resolvedPlanId)) || "price",
    source_reply_title: raw.source_reply_title || raw.reply_title || raw.replyTitle || sourceReplyTitle || null,
    side: toCleanString(raw.side || "") || null,
    entry_price: entryPrice,
    stop_price: stopPrice,
    target_price: targetPrice,
    tp_level: toFiniteNumber(raw.tp_level ?? raw.level),
    price_low: priceLow,
    price_high: priceHigh,
    path_points: Array.isArray(raw.path_points) ? raw.path_points : [],
    lifecycle,
    created_at: createdAt,
    updated_at: updatedAt,
  }, state?.annotationPreferences || {}, {
    sessionId: resolvedSessionId,
    messageId: resolvedMessageId,
    planId: resolvedPlanId,
  });
}

export function getAnnotationTypeLabel(type = "") {
  return ANNOTATION_TYPE_LABELS[type] || type || "AI 标记";
}

export function isAnnotationDeleted(annotation = {}) {
  return !!annotation?.deleted;
}
