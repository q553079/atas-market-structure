import { isAnnotationDeleted } from "./replay_workbench_annotation_utils.js";

function shouldRenderAnnotation(item, state) {
  if (!item || item.visible === false || isAnnotationDeleted(item)) {
    return false;
  }
  const filters = state.annotationFilters || {};
  if (Array.isArray(filters.annotationIds) && filters.annotationIds.includes("__none__")) {
    return false;
  }
  if (filters.onlyCurrentSession && item.session_id !== state.activeAiThreadId) {
    return false;
  }
  if (Array.isArray(filters.sessionIds) && filters.sessionIds.length && !filters.sessionIds.includes(item.session_id)) {
    return false;
  }
  if (Array.isArray(filters.messageIds) && filters.messageIds.length && !filters.messageIds.includes(item.message_id)) {
    return false;
  }
  if (Array.isArray(filters.annotationIds) && filters.annotationIds.length && !filters.annotationIds.includes(item.id)) {
    return false;
  }
  if (item.type === "path_arrow" && !filters.showPaths) {
    return false;
  }
  if (Array.isArray(filters.objectTypes) && filters.objectTypes.length && !filters.objectTypes.includes(item.type)) {
    return false;
  }
  if (!filters.showInvalidated && ["invalidated", "sl_hit"].includes(item.status)) {
    return false;
  }
  if (filters.hideCompleted && ["completed", "archived", "expired"].includes(item.status)) {
    return false;
  }
  if (filters.selectedOnly && state.selectedAnnotationId && item.id !== state.selectedAnnotationId && item.plan_id !== state.aiAnnotations?.find((node) => node.id === state.selectedAnnotationId)?.plan_id) {
    return false;
  }
  return true;
}

export function appendChartOverlayMarkup({
  markupParts,
  focusRegions,
  manualRegions,
  operatorEntries,
  aiAnnotations = [],
  draft,
  snapshot,
  events,
  visibleCandles,
  visibleCandlesLength,
  withinVisibleWindow,
  timeToX,
  priceToY,
  topPad,
  leftPad,
  chartWidth,
  chartHeight,
  volumeTop,
  volumeHeight,
  escapeHtml,
  clampChartX,
  clampChartY,
  state,
}) {
  focusRegions.forEach((region) => {
    const regionEnd = region.ended_at || snapshot.window_end;
    if (!withinVisibleWindow(region.started_at) && !withinVisibleWindow(regionEnd)) {
      return;
    }
    const x1 = timeToX(region.started_at);
    const x2 = timeToX(regionEnd);
    const y1 = priceToY(region.price_high);
    const y2 = priceToY(region.price_low);
    markupParts.push(`<rect x="${Math.min(x1, x2)}" y="${y1}" width="${Math.max(2, Math.abs(x2 - x1))}" height="${Math.max(2, y2 - y1)}" fill="rgba(59,130,246,0.12)" stroke="rgba(59,130,246,0.30)" stroke-width="1.2" rx="8" />`);
    markupParts.push(`<text x="${Math.min(x1, x2) + 8}" y="${Math.max(topPad + 14, y1 + 14)}" font-size="12" fill="#93c5fd">${escapeHtml(region.label)}</text>`);
  });

  manualRegions.forEach((region) => {
    if (!withinVisibleWindow(region.started_at) && !withinVisibleWindow(region.ended_at)) {
      return;
    }
    const x1 = timeToX(region.started_at);
    const x2 = timeToX(region.ended_at);
    const y1 = priceToY(region.price_high);
    const y2 = priceToY(region.price_low);
    markupParts.push(`<rect x="${Math.min(x1, x2)}" y="${y1}" width="${Math.max(2, Math.abs(x2 - x1))}" height="${Math.max(2, y2 - y1)}" fill="rgba(245,158,11,0.12)" stroke="rgba(245,158,11,0.38)" stroke-width="1.4" rx="8" />`);
    markupParts.push(`<text x="${Math.min(x1, x2) + 8}" y="${Math.max(topPad + 14, y1 + 14)}" font-size="12" fill="#fcd34d">${escapeHtml(region.label)}</text>`);
  });

  events.forEach((event, index) => {
    if (!withinVisibleWindow(event.observed_at)) {
      return;
    }
    const x = timeToX(event.observed_at);
    const anchorPrice = event.price != null
      ? event.price
      : (event.price_low != null && event.price_high != null ? (event.price_low + event.price_high) / 2 : visibleCandles[visibleCandles.length - 1].close);
    const y = priceToY(anchorPrice);
    const labelY = Math.max(topPad + 18, y - (index % 2 === 0 ? 18 : -24));
    markupParts.push(`<circle cx="${x}" cy="${y}" r="4.2" fill="#f59e0b" stroke="#131722" stroke-width="1.6" />`);
    if (visibleCandlesLength <= 180) {
      markupParts.push(`<line x1="${x}" y1="${y}" x2="${x}" y2="${labelY}" stroke="rgba(245,158,11,0.45)" stroke-width="1.2" />`);
      markupParts.push(`<text x="${clampChartX(x + 8, 12)}" y="${clampChartY(labelY - 4, 12)}" font-size="11" fill="#fcd34d">${escapeHtml(event.event_kind)}</text>`);
    }
  });

  operatorEntries.forEach((entry, index) => {
    if (!withinVisibleWindow(entry.executed_at)) {
      return;
    }
    const x = clampChartX(timeToX(entry.executed_at), 10);
    const y = clampChartY(priceToY(entry.entry_price), 12);
    const color = entry.side === "buy" ? "#8b5cf6" : "#c084fc";
    const points = `${x},${y - 8} ${x + 8},${y} ${x},${y + 8} ${x - 8},${y}`;
    const labelY = clampChartY(y + 22 + ((index % 2) * 18), 16);
    markupParts.push(`<polygon points="${points}" fill="${color}" stroke="#d7dde7" stroke-width="1.5" />`);
    markupParts.push(`<line x1="${x}" y1="${y + 8}" x2="${x}" y2="${labelY - 10}" stroke="${color}" stroke-width="1.2" />`);
    markupParts.push(`<text x="${clampChartX(x + 8, 16)}" y="${labelY}" font-size="12" fill="${color}">${escapeHtml(entry.side === "buy" ? "多头开仓" : "空头开仓")}</text>`);
  });

  aiAnnotations.filter((item) => shouldRenderAnnotation(item, state)).forEach((item) => {
    const start = item.start_time || snapshot.window_start;
    const end = item.end_time || snapshot.window_end;
    const isSelected = state.selectedAnnotationId === item.id;
    const strokeWidth = isSelected ? 2.8 : 1.8;
    const opacity = item.status === "triggered" ? 1 : item.status === "invalidated" ? 0.38 : item.status === "completed" ? 0.48 : 0.86;
    const hit = `data-annotation-id="${escapeHtml(item.id)}" data-message-id="${escapeHtml(item.message_id || "")}" data-session-id="${escapeHtml(item.session_id || "")}" data-plan-id="${escapeHtml(item.plan_id || "")}" class="chart-annotation-hit ${isSelected ? "selected" : ""}"`;
    if (["entry_line", "stop_loss", "take_profit"].includes(item.type)) {
      const price = item.entry_price ?? item.stop_price ?? item.target_price;
      if (price == null) {
        return;
      }
      const x1 = clampChartX(timeToX(start), 8);
      const x2 = clampChartX(timeToX(end), 8);
      const y = clampChartY(priceToY(price), 8);
      const color = item.type === "entry_line"
        ? (item.side === "sell" ? "#f97316" : "#14b8a6")
        : item.type === "stop_loss"
          ? "#ef4444"
          : item.tp_level === 1 ? "#22c55e" : item.tp_level === 2 ? "#86efac" : "#bbf7d0";
      const dash = item.type === "stop_loss" ? "7 5" : item.type === "take_profit" && item.tp_level > 1 ? "5 5" : "";
      markupParts.push(`<line x1="${Math.min(x1, x2)}" y1="${y}" x2="${Math.max(x1, x2)}" y2="${y}" stroke="${color}" stroke-width="${strokeWidth}" opacity="${opacity}" ${dash ? `stroke-dasharray="${dash}"` : ""} />`);
      markupParts.push(`<line x1="${Math.min(x1, x2)}" y1="${y}" x2="${Math.max(x1, x2)}" y2="${y}" stroke="transparent" stroke-width="14" ${hit} />`);
      markupParts.push(`<text x="${Math.min(x1, x2) + 8}" y="${y - 8}" font-size="12" fill="${color}" opacity="${opacity}">${escapeHtml(item.label)}</text>`);
      if (["tp_hit", "sl_hit", "expired", "invalidated"].includes(item.status)) {
        const marker = item.status === "tp_hit" ? "●" : item.status === "sl_hit" ? "✕" : item.status === "expired" ? "•" : "✕";
        markupParts.push(`<text x="${Math.max(x1, x2) + 6}" y="${y + 4}" font-size="12" fill="${color}">${marker}</text>`);
      }
    }
    if (["support_zone", "resistance_zone", "no_trade_zone", "zone"].includes(item.type)) {
      const low = item.price_low;
      const high = item.price_high;
      if (low == null || high == null) {
        return;
      }
      const x1 = clampChartX(timeToX(start), 8);
      const x2 = clampChartX(timeToX(end), 8);
      const y1 = clampChartY(priceToY(high), 8);
      const y2 = clampChartY(priceToY(low), 8);
      const fill = item.type === "support_zone"
        ? "rgba(20,184,166,0.16)"
        : item.type === "resistance_zone"
          ? "rgba(249,115,22,0.14)"
          : item.type === "zone"
            ? "rgba(59,130,246,0.12)"
            : "rgba(239,68,68,0.12)";
      const stroke = item.type === "support_zone"
        ? "#14b8a6"
        : item.type === "resistance_zone"
          ? "#f97316"
          : item.type === "zone"
            ? "#3b82f6"
            : "#ef4444";
      markupParts.push(`<rect x="${Math.min(x1, x2)}" y="${Math.min(y1, y2)}" width="${Math.max(2, Math.abs(x2 - x1))}" height="${Math.max(2, Math.abs(y2 - y1))}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" rx="8" opacity="${opacity}" ${hit} />`);
      markupParts.push(`<text x="${Math.min(x1, x2) + 8}" y="${Math.min(y1, y2) + 14}" font-size="12" fill="${stroke}">${escapeHtml(item.label)}</text>`);
      if (["invalidated", "completed", "expired"].includes(item.status)) {
        const suffix = item.status === "invalidated" ? "已失效" : item.status === "completed" ? "已完成" : "已过期";
        markupParts.push(`<text x="${Math.min(x1, x2) + 8}" y="${Math.min(y1, y2) + 30}" font-size="11" fill="${stroke}" opacity="0.9">${suffix}</text>`);
      }
    }
    if (item.type === "path_arrow" && Array.isArray(item.path_points) && item.path_points.length >= 2) {
      const points = item.path_points.map((point) => `${clampChartX(timeToX(point.time || point.started_at || start), 8)},${clampChartY(priceToY(point.price), 8)}`).join(" ");
      const last = item.path_points[item.path_points.length - 1];
      const prev = item.path_points[item.path_points.length - 2];
      const lx = clampChartX(timeToX(last.time || last.started_at || end), 8);
      const ly = clampChartY(priceToY(last.price), 8);
      const px = clampChartX(timeToX(prev.time || prev.started_at || start), 8);
      const py = clampChartY(priceToY(prev.price), 8);
      const angle = Math.atan2(ly - py, lx - px);
      const ah = 10;
      const arrowPoints = `${lx},${ly} ${lx - ah * Math.cos(angle - Math.PI / 6)},${ly - ah * Math.sin(angle - Math.PI / 6)} ${lx - ah * Math.cos(angle + Math.PI / 6)},${ly - ah * Math.sin(angle + Math.PI / 6)}`;
      markupParts.push(`<polyline points="${points}" fill="none" stroke="rgba(147,197,253,0.75)" stroke-width="${strokeWidth}" stroke-dasharray="6 6" ${hit} />`);
      markupParts.push(`<polygon points="${arrowPoints}" fill="rgba(147,197,253,0.9)" />`);
      markupParts.push(`<text x="${lx + 8}" y="${ly - 8}" font-size="12" fill="#93c5fd">${escapeHtml(item.label)}</text>`);
    }
  });

  if (draft) {
    const x1 = timeToX(draft.started_at);
    const x2 = timeToX(draft.ended_at);
    const y1 = priceToY(draft.price_high);
    const y2 = priceToY(draft.price_low);
    markupParts.push(`<rect x="${Math.min(x1, x2)}" y="${y1}" width="${Math.max(2, Math.abs(x2 - x1))}" height="${Math.max(2, y2 - y1)}" fill="rgba(109,40,217,0.10)" stroke="rgba(109,40,217,0.55)" stroke-width="1.5" stroke-dasharray="6 4" rx="8" />`);
  }

  markupParts.push(`<rect x="${leftPad}" y="${topPad}" width="${chartWidth}" height="${chartHeight}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1.2" rx="12" />`);
  markupParts.push(`<rect x="${leftPad}" y="${volumeTop}" width="${chartWidth}" height="${volumeHeight}" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="1.1" rx="12" />`);
  markupParts.push(`<rect x="${leftPad}" y="${topPad}" width="${chartWidth}" height="${chartHeight}" fill="transparent" stroke="none" />`);
}
