export function appendChartSeriesMarkup({
  markupParts,
  visibleCandles,
  view,
  leftPad,
  topPad,
  chartHeight,
  candleSpacing,
  candleWidth,
  priceToY,
  volumeTop,
  volumeHeight,
  volumeMax,
  emaSeries,
  state,
}) {
  visibleCandles.forEach((bar, localIndex) => {
    const globalIndex = view.startIndex + localIndex;
    const x = leftPad + localIndex * candleSpacing + (candleSpacing - candleWidth) / 2;
    const openY = priceToY(bar.open);
    const closeY = priceToY(bar.close);
    const highY = priceToY(bar.high);
    const lowY = priceToY(bar.low);
    const color = bar.close >= bar.open ? "#22ab94" : "#f23645";
    const bodyY = Math.min(openY, closeY);
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
    const centerX = x + candleWidth / 2;
    const selected = globalIndex === state.selectedCandleIndex;
    if (selected) {
      markupParts.push(`<rect x="${x - 3}" y="${topPad}" width="${candleWidth + 6}" height="${chartHeight}" fill="rgba(59,130,246,0.10)" rx="8" />`);
    }
    markupParts.push(`<line x1="${centerX}" y1="${highY}" x2="${centerX}" y2="${lowY}" stroke="${color}" stroke-width="${selected ? 2.2 : 1.2}" />`);
    markupParts.push(`<rect x="${x}" y="${bodyY}" width="${candleWidth}" height="${bodyHeight}" fill="${color}" rx="2" />`);

    const volume = Number(bar.volume || 0);
    const volumeBarHeight = (volume / volumeMax) * (volumeHeight - 18);
    const volumeY = volumeTop + volumeHeight - volumeBarHeight;
    markupParts.push(`<rect x="${x}" y="${volumeY}" width="${candleWidth}" height="${Math.max(1, volumeBarHeight)}" fill="${bar.close >= bar.open ? 'rgba(34,171,148,0.58)' : 'rgba(242,54,69,0.58)'}" rx="1" />`);
  });

  let emaPath = "";
  visibleCandles.forEach((bar, localIndex) => {
    const globalIndex = view.startIndex + localIndex;
    const emaPoint = emaSeries[globalIndex];
    const emaValue = typeof emaPoint === "object" && emaPoint !== null ? emaPoint.value : emaPoint;
    const restart = !!(typeof emaPoint === "object" && emaPoint !== null && emaPoint.restart);
    if (!Number.isFinite(emaValue)) {
      return;
    }
    const x = leftPad + localIndex * candleSpacing + (candleSpacing / 2);
    const y = priceToY(emaValue);
    emaPath += `${localIndex === 0 || restart ? "M" : "L"} ${x} ${y} `;
  });
  if (emaPath.trim()) {
    markupParts.push(`<path d="${emaPath.trim()}" fill="none" stroke="#3b82f6" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" />`);
  }
}
