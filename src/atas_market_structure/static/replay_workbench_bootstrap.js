import {
  clampChartView,
  createChartViewHelpers,
} from "./replay_workbench_chart_utils.js";
import {
  timeframeLabel,
  translateAction,
  translateVerificationStatus,
  translateAcquisitionMode,
  createThreadId,
  getPresetThreadMeta,
  renderList,
  escapeHtml,
} from "./replay_workbench_ui_utils.js";
import {
  fetchJson,
  toUtcString,
  toLocalInputValue,
  createCacheKeyHelpers,
} from "./replay_workbench_data_utils.js";
import { createAiThreadController } from "./replay_workbench_ai_threads.js";
import { createSidepaneRenderer } from "./replay_workbench_sidepanes.js";
import { createAiReviewRenderer } from "./replay_workbench_ai_review.js";
import { createChartInteractionController } from "./replay_workbench_chart_interactions.js";
import { createReplayLoader } from "./replay_workbench_replay_loader.js";
import { createWorkbenchActions } from "./replay_workbench_actions.js";
import { createAiChatController } from "./replay_workbench_ai_chat.js";
import { createWorkbenchFeedback } from "./replay_workbench_feedback.js";
import { createWorkbenchShell } from "./replay_workbench_shell.js";
import { createWorkbenchBindings } from "./replay_workbench_bindings.js";
import { createWorkbenchState } from "./replay_workbench_state.js";
import { createWorkbenchElements } from "./replay_workbench_dom.js";
import { createLayoutController } from "./replay_workbench_layout.js";
import { createSnapshotRenderer } from "./replay_workbench_snapshot.js";

export function bootReplayWorkbench({ renderChart, getRenderSnapshot, getBuildRequestPayload }) {
  const state = createWorkbenchState();
  const els = createWorkbenchElements(document);

  const {
    applyLayoutWidths,
    setLeftPanelCollapsed,
    setRightPanelCollapsed,
    beginLayoutDrag,
    updateLayoutDrag,
    finishLayoutDrag,
    initializePanelToggles,
  } = createLayoutController({
    els,
    state,
    scheduleChartRerender: (...args) => scheduleChartRerender(...args),
  });

  const { ensureChartView } = createChartViewHelpers({ state });
  const { buildCacheKey, syncCacheKey, applyWindowPreset } = createCacheKeyHelpers({ els });
  const {
    ensureThread,
    getActiveThread,
    setActiveThread,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
  } = createAiThreadController({ state, els, escapeHtml });

  const {
    renderBuildSummary,
    renderFocusRegions,
    renderStrategyCandidates,
    renderOperatorEntries,
    renderManualRegions,
    renderSelectedCandle,
    renderFootprintLadder,
    renderAiBriefing,
    renderEventTimeline,
  } = createSidepaneRenderer({
    state,
    els,
    escapeHtml,
    renderList,
    translateAction,
    translateVerificationStatus,
    translateAcquisitionMode,
  });

  const { renderAiReview } = createAiReviewRenderer({ state, els, escapeHtml, renderList });

  const {
    loadSnapshotByIngestionId,
    loadOperatorEntries,
    loadManualRegions,
    loadFootprintBarDetail,
    syncEntryDefaultsFromSnapshot,
  } = createReplayLoader({
    state,
    els,
    fetchJson,
    ensureThread,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
  });

  const {
    visibleSpan,
    zoomChart,
    zoomPriceAxis,
    resetChartView,
    chartMouseToModel,
    pickCandleIndexFromEvent,
    selectCandle,
    beginRegionDraft,
    updateRegionDraft,
  } = createChartInteractionController({
    state,
    els,
    renderChart,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    loadFootprintBarDetail,
    clampChartView,
  });

  const {
    renderStatusStrip,
    buildStatusChips,
    renderError,
    renderAiError,
  } = createWorkbenchFeedback({
    state,
    els,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    translateAction,
    translateVerificationStatus,
  });

  const {
    scheduleChartRerender,
    setBuildProgress,
    initializeSectionToggles,
    handleBuildWithForceRefresh,
  } = createWorkbenchShell({
    state,
    els,
    renderChart,
    getHandleBuild: () => handleBuild,
  });

  const {
    saveDraftRegion,
    handleBuild,
    handleLookup,
    handleInvalidate,
    handleRecordEntry,
    handleAiReview,
    handleSaveRegion,
  } = createWorkbenchActions({
    state,
    els,
    fetchJson,
    toUtcString,
    syncCacheKey,
    renderStatusStrip,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    renderError,
    renderAiError,
    setBuildProgress,
    buildRequestPayload: (...args) => getBuildRequestPayload()(...args),
    buildStatusChips,
    translateVerificationStatus,
    loadSnapshotByIngestionId,
  });

  const {
    handleAiChat,
    handleAiChatSend,
    handlePresetAnalysis,
    buildManualRegionAnalysisPrompt,
    buildSelectedBarAnalysisPrompt,
    createNewThread,
  } = createAiChatController({
    state,
    els,
    fetchJson,
    renderStatusStrip,
    getActiveThread,
    setActiveThread,
    appendAiChatMessage,
    getPresetThreadMeta,
    createThreadId,
  });

  const renderSnapshot = createSnapshotRenderer({
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
  });

  const { attachBindings, bootstrap } = createWorkbenchBindings({
    state,
    els,
    applyWindowPreset,
    handleBuildWithForceRefresh,
    handleAiReview,
    handlePresetAnalysis,
    buildManualRegionAnalysisPrompt,
    buildSelectedBarAnalysisPrompt,
    renderStatusStrip,
    createNewThread,
    handleAiChatSend,
    zoomChart,
    zoomPriceAxis,
    resetChartView,
    renderSnapshot,
    handleSaveRegion,
    handleRecordEntry,
    handleLookup,
    handleInvalidate,
    syncCacheKey,
    beginRegionDraft,
    updateLayoutDrag,
    updateRegionDraft,
    visibleSpan,
    clampChartView,
    pickCandleIndexFromEvent,
    selectCandle,
    finishLayoutDrag,
    renderChart,
    initializePanelToggles,
    initializeSectionToggles,
    scheduleChartRerender,
  });

  return {
    state,
    els,
    ensureChartView,
    buildCacheKey,
    syncCacheKey,
    applyWindowPreset,
    timeframeLabel,
    toLocalInputValue,
    renderSnapshot,
    attachBindings,
    bootstrap,
    applyLayoutWidths,
    setLeftPanelCollapsed,
    setRightPanelCollapsed,
    beginLayoutDrag,
    updateLayoutDrag,
    finishLayoutDrag,
    initializePanelToggles,
    ensureThread,
    getActiveThread,
    setActiveThread,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    renderBuildSummary,
    renderFocusRegions,
    renderStrategyCandidates,
    renderOperatorEntries,
    renderManualRegions,
    renderSelectedCandle,
    renderFootprintLadder,
    renderAiBriefing,
    renderEventTimeline,
    renderAiReview,
    loadSnapshotByIngestionId,
    loadOperatorEntries,
    loadManualRegions,
    loadFootprintBarDetail,
    syncEntryDefaultsFromSnapshot,
    visibleSpan,
    zoomChart,
    zoomPriceAxis,
    resetChartView,
    chartMouseToModel,
    pickCandleIndexFromEvent,
    selectCandle,
    beginRegionDraft,
    updateRegionDraft,
    renderStatusStrip,
    buildStatusChips,
    renderError,
    renderAiError,
    scheduleChartRerender,
    setBuildProgress,
    initializeSectionToggles,
    handleBuildWithForceRefresh,
    saveDraftRegion,
    handleBuild,
    handleLookup,
    handleInvalidate,
    handleRecordEntry,
    handleAiReview,
    handleSaveRegion,
    handleAiChat,
    handleAiChatSend,
    handlePresetAnalysis,
    buildManualRegionAnalysisPrompt,
    buildSelectedBarAnalysisPrompt,
    createNewThread,
  };
}
