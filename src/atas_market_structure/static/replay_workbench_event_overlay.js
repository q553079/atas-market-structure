const EVENT_KIND_META = {
  key_level: { label: "关键位", color: "#60a5fa" },
  price_zone: { label: "价格区", color: "#34d399" },
  market_event: { label: "市场事件", color: "#fbbf24" },
  thesis_fragment: { label: "观点", color: "#94a3b8" },
  plan_intent: { label: "计划", color: "#c084fc" },
  risk_note: { label: "风险", color: "#f87171" },
};

const EVENT_SOURCE_META = {
  manual: "手工",
  recognizer: "识别",
  orchestration: "编排",
  ai_reply_structured: "AI结构化",
  ai_reply_text: "AI文本",
  user_created: "人工",
};

const EVENT_LIFECYCLE_META = {
  candidate: "候选",
  confirmed: "已确认",
  mounted: "已上图",
  ignored: "已忽略",
  promoted_plan: "已转计划",
  expired: "已过期",
  archived: "已归档",
};

const PRESENTATION_PRIORITY = {
  hidden: 0,
  mounted: 1,
  pinned: 2,
  hover_spotlight: 3,
};

function coerceNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function toTimestampMs(value) {
  if (value == null || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return value > 1e12 ? value : value * 1000;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}

function clampValue(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function shortenLabel(value, limit = 18) {
  const text = String(value || "").trim();
  if (!text) {
    return "事件";
  }
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function formatLocalTime(value) {
  const timestamp = toTimestampMs(value);
  if (!timestamp) {
    return "时间未定";
  }
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPrice(value) {
  const numeric = coerceNumber(value);
  return numeric == null ? null : numeric.toFixed(2);
}

export function formatEventCandidatePriceSummary(candidate = {}) {
  const priceRef = formatPrice(candidate.price_ref);
  const priceLower = formatPrice(candidate.price_lower);
  const priceUpper = formatPrice(candidate.price_upper);
  if (priceLower && priceUpper) {
    return `${priceLower} - ${priceUpper}`;
  }
  if (priceRef) {
    return priceRef;
  }
  return "价格未定";
}

export function formatEventCandidateTimeSummary(candidate = {}) {
  const start = formatLocalTime(candidate.anchor_start_ts);
  const endTimestamp = toTimestampMs(candidate.anchor_end_ts);
  if (!endTimestamp) {
    return start;
  }
  return `${start} -> ${formatLocalTime(candidate.anchor_end_ts)}`;
}

export function getEventKindLabel(candidateKind) {
  return EVENT_KIND_META[String(candidateKind || "").trim()]?.label || "事件";
}

export function getEventSourceLabel(sourceType) {
  return EVENT_SOURCE_META[String(sourceType || "").trim()] || "来源未知";
}

export function getEventLifecycleLabel(lifecycleState) {
  return EVENT_LIFECYCLE_META[String(lifecycleState || "").trim()] || "未知状态";
}

export function getEventKindColor(candidateKind) {
  return EVENT_KIND_META[String(candidateKind || "").trim()]?.color || "#94a3b8";
}

export function isEventCandidateMountable(candidate = {}) {
  return ["key_level", "price_zone", "market_event", "risk_note"].includes(String(candidate.candidate_kind || "").trim());
}

export function canPromoteEventCandidate(candidate = {}) {
  return String(candidate.candidate_kind || "").trim() === "plan_intent";
}

function hasCommittedAnnotationProjection(candidate = {}, eventWorkbenchState = {}) {
  const eventId = String(candidate.event_id || "").trim();
  if (!eventId || String(candidate.lifecycle_state || "").trim() !== "mounted") {
    return false;
  }
  const items = Array.isArray(eventWorkbenchState.items) ? eventWorkbenchState.items : [];
  return items.some((entry) => {
    if (String(entry?.event_id || "").trim() !== eventId) {
      return false;
    }
    if (String(entry?.stream_action || "").trim() !== "promoted") {
      return false;
    }
    return String(entry?.metadata?.target || "").trim() === "annotation";
  });
}

export function getEventPresentationState(candidate = {}, eventWorkbenchState = {}) {
  const eventId = String(candidate.event_id || "").trim();
  if (!eventId || !isEventCandidateMountable(candidate)) {
    return "hidden";
  }
  const pinnedIds = new Set(Array.isArray(eventWorkbenchState.pinnedEventIds) ? eventWorkbenchState.pinnedEventIds : []);
  const mounted = hasCommittedAnnotationProjection(candidate, eventWorkbenchState);
  if (pinnedIds.has(eventId) && mounted) {
    return "pinned";
  }
  if (mounted) {
    return "mounted";
  }
  if (String(eventWorkbenchState.hoverEventId || "").trim() === eventId) {
    return "hover_spotlight";
  }
  return "hidden";
}

function selectStrongerPresentation(left, right) {
  return PRESENTATION_PRIORITY[right] > PRESENTATION_PRIORITY[left] ? right : left;
}

function buildCandidateOverlayDescriptor(candidate, presentationState) {
  return {
    eventId: String(candidate.event_id || "").trim(),
    candidateKind: String(candidate.candidate_kind || "").trim(),
    label: shortenLabel(candidate.title || candidate.summary || getEventKindLabel(candidate.candidate_kind)),
    detail: String(candidate.summary || "").trim(),
    priceRef: coerceNumber(candidate.price_ref),
    priceLower: coerceNumber(candidate.price_lower),
    priceUpper: coerceNumber(candidate.price_upper),
    anchorStartMs: toTimestampMs(candidate.anchor_start_ts),
    anchorEndMs: toTimestampMs(candidate.anchor_end_ts),
    presentationState,
    color: getEventKindColor(candidate.candidate_kind),
  };
}

function buildLegacyHoverDescriptor(legacyHoverItem = {}) {
  if (!legacyHoverItem || typeof legacyHoverItem !== "object") {
    return null;
  }
  return {
    eventId: "",
    candidateKind: "legacy",
    label: shortenLabel(legacyHoverItem.title || "事件"),
    detail: String(legacyHoverItem.detailText || "").trim(),
    priceRef: coerceNumber(legacyHoverItem.price),
    priceLower: coerceNumber(legacyHoverItem.priceLow),
    priceUpper: coerceNumber(legacyHoverItem.priceHigh),
    anchorStartMs: toTimestampMs(legacyHoverItem.observedAt || legacyHoverItem.started_at || legacyHoverItem.time),
    anchorEndMs: toTimestampMs(legacyHoverItem.ended_at),
    presentationState: "hover_spotlight",
    color: getEventKindColor(legacyHoverItem.candidate_kind || legacyHoverItem.type || legacyHoverItem.category || "market_event"),
  };
}

function buildOverlayDescriptors(candidates = [], eventWorkbenchState = {}, legacyHoverItem = null) {
  const byId = new Map();
  candidates.forEach((candidate) => {
    const eventId = String(candidate?.event_id || "").trim();
    if (!eventId) {
      return;
    }
    const presentationState = getEventPresentationState(candidate, eventWorkbenchState);
    if (presentationState === "hidden") {
      return;
    }
    const descriptor = buildCandidateOverlayDescriptor(candidate, presentationState);
    const existing = byId.get(eventId);
    if (!existing) {
      byId.set(eventId, descriptor);
      return;
    }
    existing.presentationState = selectStrongerPresentation(existing.presentationState, descriptor.presentationState);
    existing.detail = existing.detail || descriptor.detail;
  });
  const descriptors = Array.from(byId.values());
  if (!descriptors.length && legacyHoverItem) {
    const legacyDescriptor = buildLegacyHoverDescriptor(legacyHoverItem);
    if (legacyDescriptor) {
      descriptors.push(legacyDescriptor);
    }
  }
  return descriptors;
}

function resolveTimeWindow(descriptor, snapshot = {}) {
  const windowStart = toTimestampMs(snapshot.window_start) || null;
  const windowEnd = toTimestampMs(snapshot.window_end) || null;
  let startMs = descriptor.anchorStartMs;
  let endMs = descriptor.anchorEndMs;
  if (!startMs && !endMs) {
    if (descriptor.candidateKind === "market_event") {
      startMs = windowStart && windowEnd ? Math.round((windowStart + windowEnd) / 2) : null;
      endMs = startMs;
    } else {
      startMs = windowStart;
      endMs = windowEnd;
    }
  } else if (!startMs) {
    startMs = endMs;
  } else if (!endMs) {
    endMs = descriptor.candidateKind === "market_event"
      ? startMs
      : (windowEnd || startMs);
  }
  return { startMs, endMs };
}

function getVisualStyle(descriptor) {
  if (descriptor.presentationState === "hover_spotlight") {
    return { strokeWidth: 2.4, fillOpacity: 0.18, strokeOpacity: 0.96, dash: "", labelOpacity: 1 };
  }
  if (descriptor.presentationState === "pinned") {
    return { strokeWidth: 2.1, fillOpacity: 0.15, strokeOpacity: 0.94, dash: "", labelOpacity: 0.96 };
  }
  return { strokeWidth: 1.5, fillOpacity: 0.1, strokeOpacity: 0.82, dash: "6 5", labelOpacity: 0.88 };
}

function buildLabelMarkup({ x, y, descriptor, style, clampChartX, clampChartY, escapeHtml }) {
  const safeX = clampChartX(x, 18);
  const safeY = clampChartY(y, 20);
  return `
    <text
      x="${safeX}"
      y="${safeY}"
      class="event-overlay-label"
      fill="${descriptor.color}"
      opacity="${style.labelOpacity}"
      pointer-events="none"
    >${escapeHtml(descriptor.label)}</text>
  `;
}

function buildLineMarkup({ descriptor, style, x1, x2, y, clampChartX, clampChartY, escapeHtml }) {
  const startX = clampChartX(Math.min(x1, x2), 12);
  const endX = clampChartX(Math.max(x1, x2), 12);
  const safeY = clampChartY(y, 8);
  const hit = descriptor.eventId
    ? `<line x1="${startX}" y1="${safeY}" x2="${endX}" y2="${safeY}" class="event-overlay-hit" data-event-id="${escapeHtml(descriptor.eventId)}" stroke="transparent" stroke-width="14" />`
    : "";
  return `
    <line
      x1="${startX}"
      y1="${safeY}"
      x2="${endX}"
      y2="${safeY}"
      stroke="${descriptor.color}"
      stroke-width="${style.strokeWidth}"
      stroke-dasharray="${style.dash}"
      opacity="${style.strokeOpacity}"
      pointer-events="none"
    />
    <circle cx="${clampChartX(startX + ((endX - startX) * 0.5), 12)}" cy="${safeY}" r="${descriptor.presentationState === "hover_spotlight" ? 4.6 : 3.4}" fill="${descriptor.color}" opacity="${style.strokeOpacity}" pointer-events="none" />
    ${buildLabelMarkup({
      x: clampChartX(startX + 8, 18),
      y: clampChartY(safeY - 10, 20),
      descriptor,
      style,
      clampChartX,
      clampChartY,
      escapeHtml,
    })}
    ${hit}
  `;
}

function buildZoneMarkup({ descriptor, style, x1, x2, y1, y2, clampChartX, clampChartY, escapeHtml }) {
  const startX = clampChartX(Math.min(x1, x2), 10);
  const endX = clampChartX(Math.max(x1, x2), 10);
  const top = clampChartY(Math.min(y1, y2), 8);
  const bottom = clampChartY(Math.max(y1, y2), 8);
  const width = Math.max(8, endX - startX);
  const height = Math.max(10, bottom - top);
  const hit = descriptor.eventId
    ? `<rect x="${startX}" y="${top}" width="${width}" height="${height}" class="event-overlay-hit" data-event-id="${escapeHtml(descriptor.eventId)}" fill="transparent" />`
    : "";
  return `
    <rect
      x="${startX}"
      y="${top}"
      width="${width}"
      height="${height}"
      rx="8"
      fill="${descriptor.color}"
      opacity="${style.fillOpacity}"
      stroke="${descriptor.color}"
      stroke-width="${style.strokeWidth}"
      stroke-dasharray="${style.dash}"
      pointer-events="none"
    />
    ${buildLabelMarkup({
      x: startX + 8,
      y: top + 16,
      descriptor,
      style,
      clampChartX,
      clampChartY,
      escapeHtml,
    })}
    ${hit}
  `;
}

function buildMarketEventMarkup({ descriptor, style, x1, x2, topPad, chartHeight, clampChartX, clampChartY, escapeHtml }) {
  const startX = clampChartX(Math.min(x1, x2), 10);
  const endX = clampChartX(Math.max(x1, x2), 10);
  const bandWidth = Math.max(8, endX - startX);
  const y = clampChartY(topPad + Math.min(24, chartHeight * 0.08), 20);
  const hit = descriptor.eventId
    ? `<rect x="${startX}" y="${topPad}" width="${bandWidth}" height="${chartHeight}" class="event-overlay-hit" data-event-id="${escapeHtml(descriptor.eventId)}" fill="transparent" />`
    : "";
  return `
    <rect
      x="${startX}"
      y="${topPad}"
      width="${bandWidth}"
      height="${chartHeight}"
      fill="${descriptor.color}"
      opacity="${style.fillOpacity * 0.8}"
      stroke="${descriptor.color}"
      stroke-width="${style.strokeWidth}"
      stroke-dasharray="${style.dash}"
      pointer-events="none"
    />
    <circle cx="${startX + (bandWidth / 2)}" cy="${y}" r="${descriptor.presentationState === "hover_spotlight" ? 6 : 4}" fill="${descriptor.color}" opacity="${style.strokeOpacity}" pointer-events="none" />
    ${buildLabelMarkup({
      x: startX + 8,
      y,
      descriptor,
      style,
      clampChartX,
      clampChartY,
      escapeHtml,
    })}
    ${hit}
  `;
}

function buildRiskMarkup({ descriptor, style, x1, x2, y, clampChartX, clampChartY, escapeHtml }) {
  const base = buildLineMarkup({
    descriptor,
    style: { ...style, dash: style.dash || "5 4" },
    x1,
    x2,
    y,
    clampChartX,
    clampChartY,
    escapeHtml,
  });
  const labelX = clampChartX(Math.max(x1, x2) - 84, 18);
  const labelY = clampChartY(y - 18, 18);
  return `
    ${base}
    <text x="${labelX}" y="${labelY}" fill="${descriptor.color}" class="event-overlay-label" opacity="${style.labelOpacity}" pointer-events="none">风险</text>
  `;
}

export function focusChartViewOnEventCandidate({
  candidate,
  candles = [],
  currentView = null,
  clampChartView,
  minimumSpan = 36,
  maximumSpan = 140,
}) {
  if (!candidate || !Array.isArray(candles) || !candles.length || typeof clampChartView !== "function") {
    return null;
  }
  const anchorTimes = [candidate.anchor_start_ts, candidate.anchor_end_ts]
    .map((value) => toTimestampMs(value))
    .filter((value) => value != null);
  if (!anchorTimes.length) {
    return null;
  }
  const candleTimes = candles.map((bar) => toTimestampMs(bar?.started_at));
  const nearestIndexForTime = (targetTime) => {
    let nearestIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    candleTimes.forEach((barTime, index) => {
      if (barTime == null) {
        return;
      }
      const distance = Math.abs(barTime - targetTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });
    return nearestIndex;
  };
  const startIndex = nearestIndexForTime(anchorTimes[0]);
  const endIndex = nearestIndexForTime(anchorTimes[anchorTimes.length - 1]);
  const targetCenter = Math.round((startIndex + endIndex) / 2);
  const currentSpan = currentView
    ? Math.max(minimumSpan, currentView.endIndex - currentView.startIndex + 1)
    : Math.min(maximumSpan, Math.max(minimumSpan, candles.length));
  const eventSpan = Math.max(6, Math.abs(endIndex - startIndex) + 12);
  const targetSpan = clampValue(Math.max(currentSpan, eventSpan), minimumSpan, Math.min(maximumSpan, candles.length));
  const desiredStart = Math.max(0, targetCenter - Math.floor(targetSpan / 2));
  const desiredEnd = Math.min(candles.length - 1, desiredStart + targetSpan - 1);
  return clampChartView(candles.length, desiredStart, desiredEnd, currentView);
}

export function buildEventOverlayMarkup({
  candidates = [],
  eventWorkbenchState = {},
  snapshot = {},
  timeToX,
  priceToY,
  leftPad = 0,
  topPad = 0,
  chartWidth = 0,
  chartHeight = 0,
  clampChartX = (value) => value,
  clampChartY = (value) => value,
  escapeHtml,
  legacyHoverItem = null,
}) {
  const descriptors = buildOverlayDescriptors(candidates, eventWorkbenchState, legacyHoverItem);
  if (!descriptors.length) {
    return { markup: "", interactiveCount: 0 };
  }
  const safeEscape = typeof escapeHtml === "function" ? escapeHtml : ((value) => String(value || ""));
  const parts = [];
  let interactiveCount = 0;

  descriptors.forEach((descriptor) => {
    const style = getVisualStyle(descriptor);
    const { startMs, endMs } = resolveTimeWindow(descriptor, snapshot);
    const x1 = startMs != null ? timeToX(startMs) : leftPad;
    const x2 = endMs != null ? timeToX(endMs) : (leftPad + chartWidth);
    const refPrice = descriptor.priceRef;
    const lowPrice = descriptor.priceLower;
    const highPrice = descriptor.priceUpper;
    const kind = descriptor.candidateKind;

    if ((kind === "price_zone" || (kind === "risk_note" && lowPrice != null && highPrice != null)) && (lowPrice != null || highPrice != null)) {
      const zoneLow = lowPrice ?? refPrice ?? highPrice;
      const zoneHigh = highPrice ?? refPrice ?? lowPrice;
      const y1 = priceToY(zoneHigh);
      const y2 = priceToY(zoneLow);
      parts.push(buildZoneMarkup({
        descriptor,
        style,
        x1: Number.isFinite(x1) ? x1 : leftPad,
        x2: Number.isFinite(x2) ? x2 : (leftPad + chartWidth),
        y1,
        y2,
        clampChartX,
        clampChartY,
        escapeHtml: safeEscape,
      }));
      if (descriptor.eventId) {
        interactiveCount += 1;
      }
      return;
    }

    if (kind === "market_event") {
      parts.push(buildMarketEventMarkup({
        descriptor,
        style,
        x1: Number.isFinite(x1) ? x1 : leftPad + (chartWidth * 0.45),
        x2: Number.isFinite(x2) ? x2 : leftPad + (chartWidth * 0.55),
        topPad,
        chartHeight,
        clampChartX,
        clampChartY,
        escapeHtml: safeEscape,
      }));
      if (descriptor.eventId) {
        interactiveCount += 1;
      }
      return;
    }

    const y = refPrice != null ? priceToY(refPrice) : null;
    if (y == null || !Number.isFinite(y)) {
      return;
    }
    if (kind === "risk_note") {
      parts.push(buildRiskMarkup({
        descriptor,
        style,
        x1: Number.isFinite(x1) ? x1 : leftPad,
        x2: Number.isFinite(x2) ? x2 : (leftPad + chartWidth),
        y,
        clampChartX,
        clampChartY,
        escapeHtml: safeEscape,
      }));
    } else {
      parts.push(buildLineMarkup({
        descriptor,
        style,
        x1: Number.isFinite(x1) ? x1 : leftPad,
        x2: Number.isFinite(x2) ? x2 : (leftPad + chartWidth),
        y,
        clampChartX,
        clampChartY,
        escapeHtml: safeEscape,
      }));
    }
    if (descriptor.eventId) {
      interactiveCount += 1;
    }
  });

  return {
    markup: parts.join(""),
    interactiveCount,
  };
}

export function bindEventOverlayInteractions(svg, {
  onEventEnter = null,
  onEventLeave = null,
  onEventClick = null,
} = {}) {
  if (!svg || svg.__eventOverlayBindingsInstalled) {
    if (svg) {
      svg.__eventOverlayCallbacks = { onEventEnter, onEventLeave, onEventClick };
    }
    return;
  }
  svg.__eventOverlayBindingsInstalled = true;
  svg.__eventOverlayCallbacks = { onEventEnter, onEventLeave, onEventClick };
  svg.addEventListener("pointerover", (event) => {
    const target = event.target?.closest?.(".event-overlay-hit[data-event-id]");
    const eventId = String(target?.dataset?.eventId || "").trim();
    if (!eventId) {
      return;
    }
    svg.__eventOverlayCallbacks?.onEventEnter?.(eventId);
  });
  svg.addEventListener("pointerleave", () => {
    svg.__eventOverlayCallbacks?.onEventLeave?.();
  });
  svg.addEventListener("click", (event) => {
    const target = event.target?.closest?.(".event-overlay-hit[data-event-id]");
    const eventId = String(target?.dataset?.eventId || "").trim();
    if (!eventId) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    svg.__eventOverlayCallbacks?.onEventClick?.(eventId);
  });
}
