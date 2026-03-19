export function createSnapshotRenderer({
  renderBuildSummary,
  renderSelectedCandle,
  renderFootprintLadder,
  renderManualRegions,
  renderFocusRegions,
  renderStrategyCandidates,
  renderOperatorEntries,
  renderAiReview,
  renderAiChat,
  renderAiBriefing,
  renderEventTimeline,
  renderChart,
}) {
  return function renderSnapshot() {
    renderBuildSummary();
    renderSelectedCandle();
    renderFootprintLadder();
    renderManualRegions();
    renderFocusRegions();
    renderStrategyCandidates();
    renderOperatorEntries();
    renderAiReview();
    renderAiChat();
    renderAiBriefing();
    renderEventTimeline();
    renderChart();
  };
}
