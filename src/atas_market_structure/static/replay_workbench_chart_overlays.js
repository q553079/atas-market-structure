export function appendChartOverlayMarkup({
  markupParts,
  focusRegions,
  manualRegions,
  operatorEntries,
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
