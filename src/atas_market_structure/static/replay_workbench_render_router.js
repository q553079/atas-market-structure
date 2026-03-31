function buildThreadRenderToken(thread = {}) {
  const messages = Array.isArray(thread?.messages) ? thread.messages : [];
  const lastMessage = messages[messages.length - 1] || null;
  return [
    thread?.id || "",
    thread?.title || "",
    thread?.symbol || thread?.contractId || thread?.memory?.symbol || "",
    thread?.pinned ? "1" : "0",
    Number(thread?.unreadCount || 0),
    thread?.updatedAt || thread?.memory?.last_updated_at || "",
    thread?.loadingFromServer ? "1" : "0",
    messages.length,
    lastMessage?.message_id || "",
    lastMessage?.updated_at || lastMessage?.created_at || "",
    lastMessage?.status || "",
    String(lastMessage?.content || "").length,
    String(thread?.draftText || thread?.draft || "").length,
    Array.isArray(thread?.draftAttachments) ? thread.draftAttachments.length : 0,
  ].join("~");
}

export function createWorkbenchRenderRouter({
  state,
  els,
  getActiveThread,
  getSessionByRole,
  getReplyExtractionState,
  renderChart,
  renderDrawers,
  updateRegionQuickActionState,
  updateDynamicAnalysisVisibility,
  updateHeaderStatus,
  renderEventPanel,
  renderAiThreadTabs,
  renderContractNav,
  renderAiChat,
  decorateChatMessages,
  renderOutcomeSurfaces,
  renderEventScribePanel,
  renderReplyExtractionPanel,
  queueAnnotationLifecycleRefresh,
  renderAnnotationPanel,
  manualEventToolbarUpdate,
  startLiveRefresh = null,
}) {
  let lastAiThreadTabsRenderSignature = null;
  let lastAiChatRenderSignature = null;
  let lastSecondaryAiSurfaceSignature = null;

  function buildAiThreadTabsRenderSignature() {
    return [
      state.activeAiThreadId || "",
      state.topBar?.symbol || "",
      (Array.isArray(state.aiThreads) ? state.aiThreads : []).map((thread) => buildThreadRenderToken(thread)).join("|"),
    ].join("||");
  }

  function buildAiChatRenderSignature() {
    const session = getActiveThread?.();
    const sessionId = session?.id || null;
    const messages = Array.isArray(session?.messages) ? session.messages : [];
    const lastMessage = messages[messages.length - 1] || null;
    let annotationCount = 0;
    let lastAnnotationToken = "";
    (Array.isArray(state.aiAnnotations) ? state.aiAnnotations : []).forEach((item) => {
      if (sessionId && item?.session_id !== sessionId) {
        return;
      }
      annotationCount += 1;
      lastAnnotationToken = `${item?.object_id || ""}:${item?.message_id || ""}:${item?.updated_at || item?.created_at || ""}`;
    });
    return [
      sessionId || "",
      session?.loadingFromServer ? "1" : "0",
      session?.title || "",
      session?.activeModel || session?.memory?.active_model || "",
      session?.activePlanId || "",
      session?.activeReplyId || "",
      session?.lastContextVersion || "",
      session?.answerCardDensity || "",
      session?.contextRecipeExpanded ? "1" : "0",
      Array.isArray(session?.mountedReplyIds) ? session.mountedReplyIds.join(",") : "",
      Array.isArray(session?.selectedPromptBlockIds) ? session.selectedPromptBlockIds.join(",") : "",
      String(session?.draftText || session?.draft || "").length,
      Array.isArray(session?.draftAttachments) ? session.draftAttachments.length : 0,
      messages.length,
      lastMessage?.message_id || "",
      lastMessage?.status || "",
      lastMessage?.updated_at || lastMessage?.created_at || "",
      String(lastMessage?.content || "").length,
      Array.isArray(lastMessage?.annotations) ? lastMessage.annotations.length : 0,
      Array.isArray(lastMessage?.planCards) ? lastMessage.planCards.length : 0,
      lastMessage?.mountedToChart ? "1" : "0",
      annotationCount,
      lastAnnotationToken,
    ].join("||");
  }

  function buildSecondaryAiSurfaceSignature() {
    if (!els.aiSecondaryControls?.open) {
      return "closed";
    }
    const symbol = String(state.topBar?.symbol || "").trim();
    const scribeSession = getSessionByRole?.(symbol, "scribe");
    const extractionState = getReplyExtractionState?.();
    const scribeMessages = Array.isArray(scribeSession?.messages) ? scribeSession.messages : [];
    const scribeLastMessage = scribeMessages[scribeMessages.length - 1] || null;
    return [
      symbol,
      scribeSession?.id || "",
      scribeSession?.loadingFromServer ? "1" : "0",
      scribeMessages.length,
      scribeLastMessage?.message_id || "",
      scribeLastMessage?.updated_at || scribeLastMessage?.created_at || "",
      String(scribeLastMessage?.content || "").length,
      String(scribeSession?.draftText || scribeSession?.draft || "").length,
      extractionState?.filter || "all",
      extractionState?.collapsed ? "1" : "0",
      extractionState?.showIgnored ? "1" : "0",
      extractionState?.pendingOnly ? "1" : "0",
      Array.isArray(extractionState?.items) ? extractionState.items.length : 0,
    ].join("||");
  }

  function renderCoreSnapshot() {
    const startedAt = performance.now();
    renderChart?.();
    updateRegionQuickActionState?.();
    updateDynamicAnalysisVisibility?.();
    updateHeaderStatus?.();
    state.perf.coreRenderMs = Math.round(performance.now() - startedAt);
    if (state.snapshot?.candles?.length) {
      startLiveRefresh?.();
    }
  }

  function renderViewportDerivedSurfaces() {
    renderDrawers?.();
    renderEventPanel?.();
    updateHeaderStatus?.();
  }

  function renderSidebarSnapshot() {
    const startedAt = performance.now();
    renderViewportDerivedSurfaces();
    updateDynamicAnalysisVisibility?.();
    state.perf.sidebarRenderMs = Math.round(performance.now() - startedAt);
  }

  function renderViewportSnapshot() {
    renderCoreSnapshot();
    renderSidebarSnapshot();
  }

  function renderSecondaryAiPanels({ force = false } = {}) {
    const nextSignature = buildSecondaryAiSurfaceSignature();
    if (!els.aiSecondaryControls?.open) {
      lastSecondaryAiSurfaceSignature = nextSignature;
      return;
    }
    if (!force && nextSignature === lastSecondaryAiSurfaceSignature) {
      return;
    }
    renderEventScribePanel?.();
    renderReplyExtractionPanel?.();
    lastSecondaryAiSurfaceSignature = nextSignature;
  }

  function markSecondaryAiPanelsClosed() {
    lastSecondaryAiSurfaceSignature = "closed";
  }

  function renderAiSurface({ force = false } = {}) {
    const nextThreadTabsSignature = buildAiThreadTabsRenderSignature();
    if (force || nextThreadTabsSignature !== lastAiThreadTabsRenderSignature) {
      renderAiThreadTabs?.();
      renderContractNav?.();
      lastAiThreadTabsRenderSignature = nextThreadTabsSignature;
    }

    const nextAiChatSignature = buildAiChatRenderSignature();
    if (force || nextAiChatSignature !== lastAiChatRenderSignature) {
      renderAiChat?.();
      decorateChatMessages?.();
      lastAiChatRenderSignature = nextAiChatSignature;
    }

    renderOutcomeSurfaces?.();
    renderSecondaryAiPanels({ force });
  }

  function renderAnnotationSurface({ skipLifecycle = false } = {}) {
    if (!skipLifecycle) {
      queueAnnotationLifecycleRefresh?.({ delay: 1200, refreshMemory: true, forceServer: true });
      return;
    }
    renderAnnotationPanel?.();
  }

  function renderDeferredSurfaces() {
    renderAiSurface();
    renderAnnotationSurface({ skipLifecycle: false });
  }

  function renderSnapshot() {
    renderViewportSnapshot();
    renderDeferredSurfaces();
    manualEventToolbarUpdate?.();
  }

  return {
    renderCoreSnapshot,
    renderViewportDerivedSurfaces,
    renderSidebarSnapshot,
    renderViewportSnapshot,
    renderSecondaryAiPanels,
    markSecondaryAiPanelsClosed,
    renderAiSurface,
    renderAnnotationSurface,
    renderDeferredSurfaces,
    renderSnapshot,
  };
}
