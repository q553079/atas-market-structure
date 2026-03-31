import { resolveChartViewTimeWindow } from "./replay_workbench_annotation_utils.js";

const NEARBY_CONTEXT_LOOKBACK_MIN_MS = 15 * 60 * 1000;
const NEARBY_CONTEXT_LOOKBACK_MAX_MS = 90 * 60 * 1000;
const NEARBY_CONTEXT_SURFACE_LIMIT = 8;
const GROUP_ORDER = ["nearby", "influencing", "fixed_anchor"];
const GROUP_META = {
  nearby: {
    key: "nearby",
    title: "刚发生",
    description: "当前窗口或紧贴窗口前沿的事件。",
  },
  influencing: {
    key: "influencing",
    title: "仍在影响当前窗口",
    description: "通过当前回答或图上对象仍与当前窗口相关。",
  },
  fixed_anchor: {
    key: "fixed_anchor",
    title: "固定锚点",
    description: "被明确固定保留的锚点，不随普通窗口滚动消失。",
  },
};

function cleanString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function normalizeStringList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => cleanString(item))
    .filter(Boolean);
}

function toFiniteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function toTimestampMs(value) {
  if (value == null || value === "") {
    return null;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function midpoint(priceLower, priceUpper) {
  if (priceLower == null || priceUpper == null) {
    return null;
  }
  return Number(((priceLower + priceUpper) / 2).toFixed(6));
}

function isPlainObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function clampNumber(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function rangesOverlap(leftStart, leftEnd, rightStart, rightEnd) {
  const start = Number.isFinite(leftStart) ? leftStart : leftEnd;
  const end = Number.isFinite(leftEnd) ? leftEnd : leftStart;
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(rightStart) || !Number.isFinite(rightEnd)) {
    return false;
  }
  return end >= rightStart && start <= rightEnd;
}

function hasIntersection(leftValues, rightValues) {
  if (!leftValues.length || !rightValues.length) {
    return false;
  }
  const rightSet = new Set(rightValues);
  return leftValues.some((value) => rightSet.has(value));
}

function buildUtcDayKey(value) {
  const timestamp = toTimestampMs(value);
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  return new Date(timestamp).toISOString().slice(0, 10);
}

export function normalizeEventPresentation(candidate = {}) {
  const metadata = isPlainObject(candidate.metadata) ? candidate.metadata : {};
  const presentation = isPlainObject(metadata.presentation) ? metadata.presentation : {};
  const priceLower = toFiniteNumber(candidate.price_lower);
  const priceUpper = toFiniteNumber(candidate.price_upper);
  const anchorPrice = toFiniteNumber(
    presentation.anchor_price ?? candidate.price_ref ?? midpoint(priceLower, priceUpper),
  );
  const anchorTime = cleanString(presentation.anchor_time || candidate.anchor_start_ts || candidate.anchor_end_ts);
  const anchorStartMs = toTimestampMs(candidate.anchor_start_ts || anchorTime);
  const anchorEndMs = toTimestampMs(candidate.anchor_end_ts || anchorTime);
  const objectIds = normalizeStringList([
    ...normalizeStringList(presentation.source_object_ids),
    candidate.promoted_projection_id,
    candidate.metadata?.compat_annotation_id,
  ]);
  return {
    sourceMessageId: cleanString(presentation.source_message_id || candidate.source_message_id),
    sourcePromptTraceId: cleanString(presentation.source_prompt_trace_id || candidate.source_prompt_trace_id),
    replyWindowAnchor: cleanString(presentation.reply_window_anchor || candidate.metadata?.reply_window_anchor),
    anchorTime,
    anchorPrice,
    anchorStartMs,
    anchorEndMs,
    isFixedAnchor: presentation.is_fixed_anchor === true,
    sourceObjectIds: objectIds,
    visibleReason: cleanString(presentation.visible_reason || presentation.visibleReason),
    presentationClass: cleanString(presentation.presentation_class || presentation.presentationClass),
    hasPresentationMetadata: Object.keys(presentation).length > 0,
  };
}

function resolveChartVisibleWindow(state = {}) {
  const windowRange = resolveChartViewTimeWindow(state);
  const startMs = toTimestampMs(windowRange?.startTime);
  const endMs = toTimestampMs(windowRange?.endTime);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) {
    return null;
  }
  return {
    startMs: Math.min(startMs, endMs),
    endMs: Math.max(startMs, endMs),
  };
}

function resolveNearbyLookbackMs(chartVisibleWindow = null) {
  if (!chartVisibleWindow) {
    return 0;
  }
  const spanMs = Math.max(0, Number(chartVisibleWindow.endMs - chartVisibleWindow.startMs) || 0);
  if (!spanMs) {
    return NEARBY_CONTEXT_LOOKBACK_MIN_MS;
  }
  return clampNumber(
    Math.round(spanMs * 0.5),
    NEARBY_CONTEXT_LOOKBACK_MIN_MS,
    NEARBY_CONTEXT_LOOKBACK_MAX_MS,
  );
}

function buildNearbyWindow(chartVisibleWindow = null, lookbackMs = 0) {
  if (!chartVisibleWindow) {
    return null;
  }
  return {
    startMs: chartVisibleWindow.startMs - Math.max(0, Number(lookbackMs) || 0),
    endMs: chartVisibleWindow.endMs,
  };
}

function collectMountedObjectIds(session = null) {
  if (!session || !Array.isArray(session.messages)) {
    return [];
  }
  return normalizeStringList(
    session.messages.flatMap((message) => (
      Array.isArray(message?.mountedObjectIds) ? message.mountedObjectIds : []
    )),
  );
}

function collectVisibleObjectIds(state = {}, session = null, activeReplyUi = {}) {
  const sessionId = cleanString(session?.id || session?.sessionId);
  const visibleAnnotationIds = Array.isArray(state.aiAnnotations)
    ? state.aiAnnotations
      .filter((item) => {
        if (!item || item.visible === false || item.deleted) {
          return false;
        }
        if (!sessionId) {
          return true;
        }
        return cleanString(item.session_id || item.sessionId) === sessionId;
      })
      .map((item) => item.annotation_id || item.id)
    : [];
  return normalizeStringList([
    ...visibleAnnotationIds,
    ...normalizeStringList(activeReplyUi?.source_object_ids),
  ]);
}

function resolveActiveReplyContext(session = null) {
  if (!session || !Array.isArray(session.messages)) {
    return {
      replyId: null,
      replyWindowAnchor: null,
      ui: {},
    };
  }
  const replyId = cleanString(session.activeReplyId);
  const activeMessage = session.messages.find((message) => cleanString(message?.message_id) === replyId) || null;
  const activeUi = isPlainObject(activeMessage?.meta?.workbench_ui) ? activeMessage.meta.workbench_ui : {};
  return {
    replyId,
    replyWindowAnchor: cleanString(session.activeReplyWindowAnchor || activeUi.reply_window_anchor),
    ui: activeUi,
  };
}

function hasStablePresentationFacts(presentation = {}) {
  return !!(
    presentation.hasPresentationMetadata
    && (
      presentation.sourceMessageId
      || presentation.sourcePromptTraceId
      || presentation.replyWindowAnchor
      || presentation.visibleReason
      || presentation.anchorPrice != null
      || presentation.isFixedAnchor
      || presentation.sourceObjectIds.length
    )
  );
}

function isCrossDayAnchor(anchorTime, chartVisibleWindow = null) {
  if (!chartVisibleWindow) {
    return false;
  }
  const anchorDay = buildUtcDayKey(anchorTime);
  const startDay = buildUtcDayKey(chartVisibleWindow.startMs);
  const endDay = buildUtcDayKey(chartVisibleWindow.endMs);
  if (!anchorDay || !startDay || !endDay) {
    return false;
  }
  return anchorDay < startDay || anchorDay > endDay;
}

function resolveVisibleReason({
  presentation,
  flags,
  chartVisibleWindow,
  overlapsVisibleWindow,
  crossDayAnchor,
}) {
  if (presentation.visibleReason) {
    return presentation.visibleReason;
  }
  if (flags.fixed_anchor) {
    return crossDayAnchor ? "跨日固定锚点" : "固定锚点";
  }
  if (flags.reply_linked && flags.object_linked) {
    return "当前回答 + 图上对象";
  }
  if (flags.reply_linked) {
    return "当前回答仍引用";
  }
  if (flags.object_linked) {
    return "图上对象仍可见";
  }
  if (!chartVisibleWindow) {
    return "会话事件";
  }
  if (flags.nearby) {
    return overlapsVisibleWindow
      ? (presentation.hasPresentationMetadata ? "当前窗口发生" : "时间窗口回退")
      : "窗口前沿";
  }
  if (flags.influencing) {
    return "仍在影响";
  }
  return "后台历史";
}

function compareContextItems(left, right) {
  const boolWeight = (value) => (value ? 1 : 0);
  const comparisons = [
    boolWeight(right?.flags?.reply_linked) - boolWeight(left?.flags?.reply_linked),
    boolWeight(right?.flags?.object_linked) - boolWeight(left?.flags?.object_linked),
    boolWeight(right?.flags?.visible_window) - boolWeight(left?.flags?.visible_window),
    boolWeight(right?.crossDayAnchor) - boolWeight(left?.crossDayAnchor),
  ];
  for (const comparison of comparisons) {
    if (comparison !== 0) {
      return comparison;
    }
  }
  return (Number(right?.sortTimeMs) || 0) - (Number(left?.sortTimeMs) || 0);
}

function buildRenderableItems(items = [], chartVisibleWindow = null) {
  if (chartVisibleWindow) {
    return items;
  }
  return items.map((item) => {
    if (item.primaryContextKind !== "historical") {
      return item;
    }
    return {
      ...item,
      primaryContextKind: "nearby",
      visibleReason: "会话事件",
      flags: {
        ...item.flags,
        nearby: true,
        historical: false,
      },
    };
  });
}

function buildDockGroups(items = []) {
  const buckets = GROUP_ORDER.reduce((acc, key) => {
    acc[key] = [];
    return acc;
  }, {});
  items.forEach((item) => {
    if (buckets[item?.primaryContextKind]) {
      buckets[item.primaryContextKind].push(item);
    }
  });
  GROUP_ORDER.forEach((key) => {
    buckets[key].sort(compareContextItems);
  });
  return GROUP_ORDER.map((key) => ({
    ...GROUP_META[key],
    items: buckets[key],
  }));
}

function capDockGroups(groups = [], limit = NEARBY_CONTEXT_SURFACE_LIMIT) {
  const workingGroups = groups.map((group) => ({
    ...group,
    items: Array.isArray(group.items) ? [...group.items] : [],
  })).filter((group) => group.items.length);
  const cappedGroups = workingGroups.map((group) => ({
    ...group,
    items: [],
  }));
  let remaining = Math.max(0, Number(limit) || 0);
  if (!remaining) {
    return {
      groups: [],
      visibleItems: [],
    };
  }
  for (let index = 0; index < workingGroups.length && remaining > 0; index += 1) {
    if (!workingGroups[index].items.length) {
      continue;
    }
    cappedGroups[index].items.push(workingGroups[index].items.shift());
    remaining -= 1;
  }
  while (remaining > 0) {
    let progressed = false;
    for (let index = 0; index < workingGroups.length && remaining > 0; index += 1) {
      if (!workingGroups[index].items.length) {
        continue;
      }
      cappedGroups[index].items.push(workingGroups[index].items.shift());
      remaining -= 1;
      progressed = true;
    }
    if (!progressed) {
      break;
    }
  }
  const visibleItems = cappedGroups.flatMap((group) => group.items);
  return {
    groups: cappedGroups.filter((group) => group.items.length),
    visibleItems,
  };
}

function summarizeByPrimaryKind(items = []) {
  return items.reduce((acc, item) => {
    const key = item?.primaryContextKind || "historical";
    acc.total += 1;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {
    total: 0,
    nearby: 0,
    influencing: 0,
    fixed_anchor: 0,
    historical: 0,
  });
}

function buildSummaryText({
  chartVisibleWindow,
  totalItems,
  visibleItems,
  visibleCounts,
}) {
  if (!totalItems.length) {
    return "当前会话还没有正式 EventCandidate。";
  }
  if (!chartVisibleWindow) {
    return `当前视图未初始化，先展示会话内全部 ${totalItems.length} 条事件。`;
  }
  if (!visibleItems.length) {
    return `当前窗口附近没有前台事件，后台仍保留 ${totalItems.length} 条历史事件。`;
  }
  const parts = [`当前前台 ${visibleItems.length} 条`];
  if (visibleCounts.nearby) {
    parts.push(`刚发生 ${visibleCounts.nearby}`);
  }
  if (visibleCounts.influencing) {
    parts.push(`影响中 ${visibleCounts.influencing}`);
  }
  if (visibleCounts.fixed_anchor) {
    parts.push(`固定锚点 ${visibleCounts.fixed_anchor}`);
  }
  if (totalItems.length > visibleItems.length) {
    parts.push(`后台 ${totalItems.length} 条`);
  }
  return `${parts.join("，")}。`;
}

function buildEmptyMessage({ chartVisibleWindow, totalItems, historyItems }) {
  if (!totalItems.length) {
    return "当前会话还没有正式 EventCandidate。旧文本提取仅保留为 legacy fallback，不再作为主路径。";
  }
  if (!chartVisibleWindow) {
    return "当前视图未初始化，先展示会话内全部事件。";
  }
  if (historyItems.length) {
    return "当前窗口附近没有前台事件。历史仍保留在折叠区，拖动图表或切换当前回答会重新派生。";
  }
  return "当前窗口和筛选条件下没有事件。";
}

function classifyCandidate({
  candidate,
  chartVisibleWindow,
  activeReply,
  mountedObjectIds,
  visibleObjectIds,
}) {
  const presentation = normalizeEventPresentation(candidate);
  const candidateStartMs = Number.isFinite(presentation.anchorStartMs) ? presentation.anchorStartMs : presentation.anchorEndMs;
  const candidateEndMs = Number.isFinite(presentation.anchorEndMs) ? presentation.anchorEndMs : presentation.anchorStartMs;
  const stablePresentationFacts = hasStablePresentationFacts(presentation);
  const nearbyWindow = chartVisibleWindow
    ? buildNearbyWindow(chartVisibleWindow, stablePresentationFacts ? resolveNearbyLookbackMs(chartVisibleWindow) : 0)
    : null;
  const overlapsVisibleWindow = !!chartVisibleWindow && rangesOverlap(
    candidateStartMs,
    candidateEndMs,
    chartVisibleWindow.startMs,
    chartVisibleWindow.endMs,
  );
  const nearbyByWindow = !!nearbyWindow && rangesOverlap(
    candidateStartMs,
    candidateEndMs,
    nearbyWindow.startMs,
    nearbyWindow.endMs,
  );
  const replyLinked = (
    (activeReply.replyId && presentation.sourceMessageId === activeReply.replyId)
    || (activeReply.replyWindowAnchor && presentation.replyWindowAnchor === activeReply.replyWindowAnchor)
  );
  const objectLinked = hasIntersection(
    presentation.sourceObjectIds,
    normalizeStringList([...mountedObjectIds, ...visibleObjectIds]),
  );
  const fixedAnchor = presentation.isFixedAnchor === true;
  const nearby = chartVisibleWindow
    ? nearbyByWindow
    : !fixedAnchor && !replyLinked && !objectLinked;
  const influencing = !fixedAnchor && !nearby && (replyLinked || objectLinked);
  const historical = !fixedAnchor && !nearby && !influencing;
  const primaryContextKind = fixedAnchor
    ? "fixed_anchor"
    : nearby
      ? "nearby"
      : influencing
        ? "influencing"
        : "historical";
  const crossDayAnchor = fixedAnchor && isCrossDayAnchor(presentation.anchorTime, chartVisibleWindow);
  const flags = {
    nearby,
    influencing,
    fixed_anchor: fixedAnchor,
    historical,
    reply_linked: replyLinked,
    object_linked: objectLinked,
    visible_window: overlapsVisibleWindow,
  };
  return {
    candidate,
    presentation,
    primaryContextKind,
    crossDayAnchor,
    visibleReason: resolveVisibleReason({
      presentation,
      flags,
      chartVisibleWindow,
      overlapsVisibleWindow,
      crossDayAnchor,
    }),
    flags,
    sortTimeMs: [
      toTimestampMs(candidate.updated_at),
      toTimestampMs(candidate.created_at),
      presentation.anchorEndMs,
      presentation.anchorStartMs,
    ].find((value) => Number.isFinite(value)) || 0,
  };
}

export function createWorkbenchNearbyContextController({ state, getActiveThread }) {
  function buildEventPanelModel({ candidates = [], filterKind = "all" } = {}) {
    const session = typeof getActiveThread === "function" ? getActiveThread() : null;
    const activeReply = resolveActiveReplyContext(session);
    const chartVisibleWindow = resolveChartVisibleWindow(state);
    const mountedObjectIds = collectMountedObjectIds(session);
    const visibleObjectIds = collectVisibleObjectIds(state, session, activeReply.ui);
    const items = candidates.map((candidate) => classifyCandidate({
      candidate,
      chartVisibleWindow,
      activeReply,
      mountedObjectIds,
      visibleObjectIds,
    }));
    const normalizedFilter = String(filterKind || "all").trim();
    const filteredItems = normalizedFilter === "all"
      ? items
      : items.filter((item) => String(item.candidate?.candidate_kind || "").trim() === normalizedFilter);
    const renderableItems = buildRenderableItems(filteredItems, chartVisibleWindow);
    const surfaceItems = renderableItems.filter((item) => item.primaryContextKind !== "historical");
    const dockGroups = buildDockGroups(surfaceItems);
    const cappedDock = capDockGroups(dockGroups, NEARBY_CONTEXT_SURFACE_LIMIT);
    const visibleItemIds = new Set(cappedDock.visibleItems.map((item) => String(item?.candidate?.event_id || "").trim()));
    const historyItems = renderableItems
      .filter((item) => !visibleItemIds.has(String(item?.candidate?.event_id || "").trim()))
      .sort(compareContextItems);
    const visibleCounts = summarizeByPrimaryKind(cappedDock.visibleItems);
    return {
      chartVisibleWindow,
      activeReplyId: activeReply.replyId,
      activeReplyWindowAnchor: activeReply.replyWindowAnchor,
      items,
      filteredItems,
      surfaceItems,
      visibleItems: cappedDock.visibleItems,
      historyItems,
      groups: cappedDock.groups,
      counts: summarizeByPrimaryKind(items),
      filteredCounts: summarizeByPrimaryKind(filteredItems),
      summaryText: buildSummaryText({
        chartVisibleWindow,
        totalItems: filteredItems,
        visibleItems: cappedDock.visibleItems,
        visibleCounts,
      }),
      emptyMessage: buildEmptyMessage({
        chartVisibleWindow,
        totalItems: filteredItems,
        historyItems,
      }),
    };
  }

  return {
    buildEventPanelModel,
  };
}
