export function appendChartAxesMarkup({
  markupParts,
  width,
  height,
  leftPad,
  rightPad,
  topPad,
  chartWidth,
  chartHeight,
  volumeTop,
  volumeHeight,
  yMin,
  yMax,
  priceToY,
  escapeHtml,
  axisTickCount,
  visibleCandles,
  candleSpacing,
  formatAxisTime,
}) {
  markupParts.push(`<rect x="0" y="0" width="${width}" height="${height}" fill="#131722" />`);
  markupParts.push(`<rect x="${leftPad}" y="${topPad}" width="${chartWidth}" height="${chartHeight}" fill="rgba(19,23,34,0.98)" rx="10" />`);
  markupParts.push(`<rect x="${leftPad}" y="${volumeTop}" width="${chartWidth}" height="${volumeHeight}" fill="rgba(19,23,34,0.98)" rx="10" />`);

  for (let step = 0; step < 6; step += 1) {
    const price = yMin + ((yMax - yMin) * step) / 5;
    const y = priceToY(price);
    markupParts.push(`<line x1="${leftPad}" y1="${y}" x2="${width - rightPad}" y2="${y}" stroke="rgba(138,148,166,0.14)" stroke-width="1" />`);
    markupParts.push(`<text x="${width - rightPad + 8}" y="${y + 4}" text-anchor="start" font-size="12" fill="#8a94a6">${escapeHtml(price.toFixed(2))}</text>`);
  }

  for (let step = 0; step < axisTickCount; step += 1) {
    const ratio = axisTickCount === 1 ? 0 : step / (axisTickCount - 1);
    const candleIndex = Math.min(visibleCandles.length - 1, Math.round(ratio * (visibleCandles.length - 1)));
    const x = leftPad + candleIndex * candleSpacing + (candleSpacing / 2);
    const label = formatAxisTime(visibleCandles[candleIndex].started_at);
    markupParts.push(`<line x1="${x}" y1="${topPad}" x2="${x}" y2="${volumeTop + volumeHeight}" stroke="rgba(138,148,166,0.09)" stroke-width="1" />`);
    markupParts.push(`<text x="${x}" y="${height - 12}" text-anchor="middle" font-size="11" fill="#8a94a6">${escapeHtml(label)}</text>`);
  }
}
