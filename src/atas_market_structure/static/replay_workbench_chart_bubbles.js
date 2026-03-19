export function appendChartBubbleMarkup({
  markupParts,
  visibleBubbleMarks,
  timeToX,
  clampNumber,
  viewportScale,
  priceViewportScale,
  priceToY,
  escapeHtml,
}) {
  visibleBubbleMarks.forEach((bubble) => {
    const x = timeToX(bubble.startedAt);
    const radiusBase = 6 + (bubble.volumeRatio * 12);
    const radius = clampNumber(radiusBase * viewportScale * priceViewportScale, 5, 42);
    const clampBubblePrice = (price) => {
      if (price == null) {
        return null;
      }
      if (bubble.candleLow == null || bubble.candleHigh == null) {
        return Number(price);
      }
      return clampNumber(Number(price), bubble.candleLow, bubble.candleHigh);
    };
    if (bubble.topVolumeLevel?.price != null) {
      const y = priceToY(clampBubblePrice(bubble.topVolumeLevel.price));
      const fill = (bubble.topVolumeLevel.delta || 0) >= 0 ? "rgba(34, 171, 148, 0.26)" : "rgba(242, 54, 69, 0.26)";
      const stroke = (bubble.topVolumeLevel.delta || 0) >= 0 ? "#22ab94" : "#f23645";
      markupParts.push(`<circle cx="${x}" cy="${y}" r="${radius.toFixed(2)}" fill="${fill}" stroke="${stroke}" stroke-width="1.4" />`);
      markupParts.push(`<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="${Math.max(10, radius * 0.55).toFixed(0)}" fill="#d7dde7" font-weight="700">${escapeHtml(String(Math.round(bubble.barVolume)))}</text>`);
    }
    if (bubble.topDeltaLevel?.price != null) {
      const y = priceToY(clampBubblePrice(bubble.topDeltaLevel.price));
      const diamond = `${x},${y - radius} ${x + radius},${y} ${x},${y + radius} ${x - radius},${y}`;
      const fill = (bubble.topDeltaLevel.delta || 0) >= 0 ? "rgba(34, 171, 148, 0.18)" : "rgba(242, 54, 69, 0.18)";
      const stroke = (bubble.topDeltaLevel.delta || 0) >= 0 ? "#22ab94" : "#f23645";
      markupParts.push(`<polygon points="${diamond}" fill="${fill}" stroke="${stroke}" stroke-width="1.6" />`);
    }
  });
}
