export function createWorkbenchState() {
  const state = {
    buildResponse: null,
    snapshot: null,
    operatorEntries: [],
    manualRegions: [],
    aiReview: null,
    aiThreads: [],
    activeAiThreadId: null,
    currentReplayIngestionId: null,
    selectedCandleIndex: null,
    selectedFootprintBar: null,
    chartView: null,
    chartMetrics: null,
    chartInteraction: {
      regionMode: false,
      draftRegion: null,
      panStartX: null,
      panStartY: null,
      panStartView: null,
      panStartPriceRange: null,
    },
  };

  state.layout = {
    leftWidth: 320,
    rightWidth: 340,
    chatHeight: 420,
    dragKind: null,
    dragStartX: null,
    dragStartY: null,
    dragStartLeftWidth: null,
    dragStartRightWidth: null,
    dragStartChatHeight: null,
  };

  state.buildInFlight = false;
  state.autoBootstrapped = false;
  state.pendingChartRerender = false;

  return state;
}
