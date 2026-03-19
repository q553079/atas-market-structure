export function createChartViewportContext({
  state,
  width,
  height,
  visibleCandles,
  candles,
  clampNumber,
}) {
  const leftPad = 18;
  const rightPad = 78;
  const topPad = 20;
  const bottomPad = 42;
  const volumeGap = 14;
  const volumeHeight = Math.max(84, Math.round(height * 0.16));
  const priceChartHeight = height - topPad - bottomPad - volumeGap - volumeHeight;
  const volumeTop = topPad + priceChartHeight + volumeGap;
  const chartWidth = width - leftPad - rightPad;
  const chartHeight = priceChartHeight;
  const visibleStartTime = new Date(visibleCandles[0].started_at).getTime();
  const visibleEndTime = new Date(visibleCandles[visibleCandles.length - 1].ended_at).getTime();
  const candleSpacing = chartWidth / Math.max(visibleCandles.length, 1);
  const candleWidth = Math.max(1.2, candleSpacing * 0.7);

  const withinVisibleWindow = (value) => {
    const timestamp = new Date(value).getTime();
    return timestamp >= visibleStartTime && timestamp <= visibleEndTime;
  };

  const timeToX = (value) => {
    const timestamp = new Date(value).getTime();
    if (visibleEndTime === visibleStartTime) {
      return leftPad + chartWidth / 2;
    }
    return leftPad + ((timestamp - visibleStartTime) / (visibleEndTime - visibleStartTime)) * chartWidth;
  };

  const createPriceMappers = ({ yMin, yMax }) => {
    const priceToY = (value) => topPad + ((yMax - value) / (yMax - yMin)) * chartHeight;
    const xToTime = (x) => {
      const ratio = Math.max(0, Math.min(1, (x - leftPad) / chartWidth));
      return new Date(visibleStartTime + ratio * (visibleEndTime - visibleStartTime)).toISOString();
    };
    const yToPrice = (y) => yMax - ((y - topPad) / chartHeight) * (yMax - yMin);
    const clampChartX = (value, padding = 0) => clampNumber(value, leftPad + padding, leftPad + chartWidth - padding);
    const clampChartY = (value, padding = 0) => clampNumber(value, topPad + padding, topPad + chartHeight - padding);

    state.chartMetrics = {
      width,
      height,
      leftPad,
      rightPad,
      topPad,
      bottomPad,
      volumeTop,
      volumeHeight,
      chartWidth,
      chartHeight,
      visibleStartTime,
      visibleEndTime,
      yMin,
      yMax,
      candleSpacing,
      candles,
    };

    return {
      priceToY,
      xToTime,
      yToPrice,
      clampChartX,
      clampChartY,
    };
  };

  return {
    leftPad,
    rightPad,
    topPad,
    bottomPad,
    volumeGap,
    volumeHeight,
    priceChartHeight,
    volumeTop,
    chartWidth,
    chartHeight,
    visibleStartTime,
    visibleEndTime,
    candleSpacing,
    candleWidth,
    withinVisibleWindow,
    timeToX,
    createPriceMappers,
  };
}
