import { deriveSessionOrdinal, pickModelOptions, readStorage } from "./replay_workbench_ui_utils.js";

function createDefaultSession(index = 0) {
  const ordinal = deriveSessionOrdinal(index);
  const sessionId = `session-${ordinal}`;
  return {
    id: sessionId,
    sessionId,
    workspaceRole: "analyst",
    title: ordinal,
    pinned: index < 3,
    preset: "general",
    symbol: "NQ",
    contractId: "NQ",
    timeframe: "1m",
    windowRange: "最近7天",
    unreadCount: 0,
    selectedPromptBlockIds: [],
    pinnedContextBlockIds: [],
    includeMemorySummary: false,
    includeRecentMessages: false,
    promptBlocks: [],
    mountedReplyIds: [],
    activePlanId: null,
    scrollOffset: 0,
    messages: [],
    turns: [],
    draft: "",
    draftText: "",
    attachments: [],
    draftAttachments: [],
    analysisTemplate: {
      type: "recent_20_bars",
      range: "current_window",
      style: "standard",
      sendMode: "current",
    },
    activeModel: "",
    handoffMode: "summary_only",
    memory: {
      session_id: sessionId,
      summary_version: 1,
      active_model: "",
      symbol: "NQ",
      timeframe: "1m",
      window_range: "最近7天",
      user_goal_summary: "",
      market_context_summary: "",
      key_zones_summary: [],
      active_plans_summary: [],
      invalidated_plans_summary: [],
      important_messages: [],
      current_user_intent: "",
      latest_question: "",
      latest_answer_summary: "",
      selected_annotations: [],
      last_updated_at: null,
    },
  };
}

export function createWorkbenchState() {
  const persistedLayout = readStorage("layout", {});
  const persistedWorkbench = readStorage("workbench", {});
  const persistedSessions = readStorage("sessions", null);
  const persistedFilters = readStorage("annotationFilters", null);
  /** 按 sessionId 去重，避免本地存储或异常合并产生重复条目 */
  const rawSessions = Array.isArray(persistedSessions) && persistedSessions.length
    ? persistedSessions
    : [createDefaultSession(0)];
  const dedupedRaw = [];
  const seenIds = new Set();
  for (let i = rawSessions.length - 1; i >= 0; i -= 1) {
    const s = rawSessions[i];
    const id = String(s?.id || s?.sessionId || "").trim();
    if (!id || seenIds.has(id)) {
      continue;
    }
    seenIds.add(id);
    dedupedRaw.unshift(s);
  }
  const sessionsSource = dedupedRaw.length ? dedupedRaw : [createDefaultSession(0)];
  const sessions = sessionsSource
      .map((session, index) => ({
        ...createDefaultSession(index),
        ...session,
        sessionId: session?.sessionId || session?.id || createDefaultSession(index).sessionId,
        symbol: session?.symbol || session?.memory?.symbol || "NQ",
        contractId: session?.contractId || session?.symbol || session?.memory?.symbol || "NQ",
        timeframe: session?.timeframe || session?.memory?.timeframe || "1m",
        windowRange: session?.windowRange || session?.memory?.window_range || "最近7天",
        draftText: session?.draftText ?? session?.draft ?? "",
        // draftAttachments 是待发送附件主字段；attachments 仅作兼容镜像。
        draftAttachments: Array.isArray(session?.draftAttachments) ? session.draftAttachments : (Array.isArray(session?.attachments) ? session.attachments : []),
        selectedPromptBlockIds: Array.isArray(session?.selectedPromptBlockIds) ? session.selectedPromptBlockIds : [],
        pinnedContextBlockIds: Array.isArray(session?.pinnedContextBlockIds) ? session.pinnedContextBlockIds : [],
        includeMemorySummary: !!session?.includeMemorySummary,
        includeRecentMessages: !!session?.includeRecentMessages,
        promptBlocks: Array.isArray(session?.promptBlocks) ? session.promptBlocks : [],
        mountedReplyIds: Array.isArray(session?.mountedReplyIds) ? session.mountedReplyIds : [],
        unreadCount: Number.isFinite(session?.unreadCount) ? session.unreadCount : 0,
        scrollOffset: Number.isFinite(session?.scrollOffset) ? session.scrollOffset : 0,
        activePlanId: session?.activePlanId || null,
        workspaceRole: session?.workspaceRole || "analyst",
        handoffMode: session?.handoffMode || "summary_only",
      }));

  const state = {
    buildResponse: null,
    snapshot: null,
    operatorEntries: [],
    manualRegions: [],
    aiReview: null,
    aiThreads: sessions,
    activeAiThreadId: persistedWorkbench.activeAiThreadId || sessions[0].id,
    currentReplayIngestionId: null,
    selectedCandleIndex: null,
    selectedFootprintBar: null,
    selectedAnnotationId: null,
    selectedChartEventClusterKey: null,
    // chartView 保存当前视口；lastChartUpdateType 用于区分 initial / tail_update / full_reset。
    chartView: null,
    lastChartUpdateType: null,
    chartMetrics: null,
    chartEventModel: null,
    buildInFlight: false,
    snapshotLoading: false,
    sidebarLoading: false,
    deferredRefreshScheduled: false,
    followLatest: true,
    integrity: null,
    pendingBackfill: null,
    lastLiveTailIntegrityHash: null,
    autoBootstrapped: false,
    pendingChartRerender: false,
    symbolOptions: ["NQ", "ES", "CL", "YM", "RTY"],
    timeframeOptions: ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
    quickRanges: [
      { value: "1d", label: "最近1天", days: 1 },
      { value: "3d", label: "最近3天", days: 3 },
      { value: "7d", label: "最近7天", days: 7 },
      { value: "15d", label: "最近15天", days: 15 },
      { value: "custom", label: "自定义", days: null },
    ],
    modelOptions: pickModelOptions(),
    chartInteraction: {
      regionMode: false,
      draftRegion: null,
      panStartX: null,
      panStartY: null,
      panStartView: null,
      panStartPriceRange: null,
    },
    layout: {
      chartWidth: persistedLayout.chartWidth || 980,
      chatWidth: persistedLayout.chatWidth || 620,
      chatHeight: persistedLayout.chatHeight || 360,
      dragKind: null,
      dragStartX: null,
      dragStartY: null,
      dragStartChartWidth: null,
      dragStartChatWidth: null,
      dragStartChatHeight: null,
    },
    drawerState: {
      context: persistedWorkbench.drawerState?.context ?? false,
      manual: persistedWorkbench.drawerState?.manual ?? false,
      focus: persistedWorkbench.drawerState?.focus ?? false,
      strategy: persistedWorkbench.drawerState?.strategy ?? false,
      entries: persistedWorkbench.drawerState?.entries ?? false,
      recap: persistedWorkbench.drawerState?.recap ?? false,
      gamma: persistedWorkbench.drawerState?.gamma ?? false,
    },
    layerState: {
      largeOrders: persistedWorkbench.layerState?.largeOrders ?? false,
      absorption: persistedWorkbench.layerState?.absorption ?? false,
      iceberg: persistedWorkbench.layerState?.iceberg ?? false,
      replenishment: persistedWorkbench.layerState?.replenishment ?? false,
      events: persistedWorkbench.layerState?.events ?? true,
      focusRegions: persistedWorkbench.layerState?.focusRegions ?? true,
      manualRegions: persistedWorkbench.layerState?.manualRegions ?? true,
      operatorEntries: persistedWorkbench.layerState?.operatorEntries ?? true,
      aiAnnotations: persistedWorkbench.layerState?.aiAnnotations ?? true,
    },
    annotationFilters: persistedFilters || {
      onlyCurrentSession: true,
      hideCompleted: true,
      sessionIds: [],
      messageIds: [],
      annotationIds: [],
      objectTypes: ["entry_line", "stop_loss", "take_profit", "support_zone", "resistance_zone", "no_trade_zone", "zone"],
      showPaths: false,
      showInvalidated: false,
      selectedOnly: false,
    },
    annotationPanelOpen: false,
    aiAnnotations: [],
    pinnedPlanId: persistedWorkbench.pinnedPlanId || null,
    annotationPopoverTargetId: null,
    symbolWorkspaceState: persistedWorkbench.symbolWorkspaceState || {},
    eventStreamItems: [],
    eventStreamHoverItem: null,
    eventStreamFilter: persistedWorkbench.eventStreamFilter || "all",
    replyExtractionState: {
      filter: persistedWorkbench.replyExtractionState?.filter || "all",
      showIgnored: !!persistedWorkbench.replyExtractionState?.showIgnored,
      intensity: persistedWorkbench.replyExtractionState?.intensity || "balanced",
      autoExtractEnabled: persistedWorkbench.replyExtractionState?.autoExtractEnabled !== false,
      collapsed: !!persistedWorkbench.replyExtractionState?.collapsed,
      bySymbol: persistedWorkbench.replyExtractionState?.bySymbol || {},
    },
    sessionComparisonEnabled: false,
    topBar: {
      symbol: persistedWorkbench.topBar?.symbol || "NQ",
      timeframe: persistedWorkbench.topBar?.timeframe || "1m",
      quickRange: persistedWorkbench.topBar?.quickRange || "7d",
      lastSyncedAt: persistedWorkbench.topBar?.lastSyncedAt || null,
    },
    aiSidebarOpen: readStorage("aiSidebarState", {}).open ?? false,
    aiSidebarPinned: readStorage("aiSidebarState", {}).pinned ?? false,
    optionsGamma: {
      loading: false,
      error: null,
      sourceCsvPath: "",
      discoveredAt: null,
      requestedSymbol: "SPX",
      requestedTradeDate: null,
      summary: null,
      textReport: "",
      artifacts: null,
      aiInterpretation: "",
      aiAnalysisError: null,
      lastLoadedAt: null,
    },
    perf: {
      loadStartedAt: null,
      buildResponseMs: null,
      coreSnapshotLoadMs: null,
      coreRenderMs: null,
      sidebarLoadMs: null,
      sidebarRenderMs: null,
      chartUpdateMs: null,
      deferredAnnotationMs: null,
      lastReason: null,
    },
    historyBackfillLoading: false,
    fullHistoryLoaded: false,
  };

  return state;
}
