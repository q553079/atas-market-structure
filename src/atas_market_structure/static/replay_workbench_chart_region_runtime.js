function isInteractiveTarget(target) {
  return target instanceof Element
    && !!target.closest("button,input,select,textarea,a,label,[role='button']");
}

export function bindChartRegionRuntime({
  state,
  els,
  bindClickAction,
  beginRegionDraft,
  updateRegionDraft,
  updateRegionQuickActionState,
  renderStatusStrip,
  getActiveChartRegionSurfaceRect,
  regionDraftTargets = [],
  renderRegionModeChanged = null,
}) {
  let activeRegionPointerId = null;
  let regionPointerMoved = false;

  function renderRegionModeSurface() {
    if (typeof renderRegionModeChanged === "function") {
      renderRegionModeChanged();
    }
  }

  function syncQuickActions() {
    updateRegionQuickActionState?.();
  }

  function resetPointerState({ clearMoved = false } = {}) {
    activeRegionPointerId = null;
    if (clearMoved) {
      regionPointerMoved = false;
    }
    state.chartInteraction.regionDragActive = false;
    syncQuickActions();
  }

  function isRegionSelectionSurfaceEvent(event) {
    if (!state.chartInteraction.regionMode) {
      return false;
    }
    const surfaceRect = getActiveChartRegionSurfaceRect?.();
    if (!surfaceRect) {
      return false;
    }
    const x = Number(event?.clientX);
    const y = Number(event?.clientY);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return false;
    }
    if (x < surfaceRect.left || x > surfaceRect.right || y < surfaceRect.top || y > surfaceRect.bottom) {
      return false;
    }
    if (isInteractiveTarget(event?.target)) {
      return false;
    }
    return true;
  }

  function handleRegionDragStart(event) {
    if (!state.chartInteraction.regionMode || state.chartInteraction.regionAnchorActive || event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    state.chartInteraction.regionDragActive = !!beginRegionDraft(event);
    state.chartInteraction.regionAnchorActive = false;
    if (state.chartInteraction.regionDragActive) {
      syncQuickActions();
    }
  }

  function handleRegionAnchorClick(event) {
    if (!state.chartInteraction.regionMode || event.button !== 0) {
      return;
    }
    if (regionPointerMoved) {
      regionPointerMoved = false;
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (!state.chartInteraction.draftRegion) {
      if (!beginRegionDraft(event)) {
        return;
      }
      state.chartInteraction.regionAnchorActive = true;
      renderStatusStrip?.([{ label: "已记录起点，移动鼠标预览后再次左击确认终点。", variant: "emphasis" }]);
      syncQuickActions();
      return;
    }
    if (!state.chartInteraction.regionAnchorActive) {
      state.chartInteraction.regionAnchorActive = true;
      renderStatusStrip?.([{ label: "已记录起点，移动鼠标预览后再次左击确认终点。", variant: "emphasis" }]);
      syncQuickActions();
      return;
    }
    updateRegionDraft(event);
    state.chartInteraction.regionAnchorActive = false;
    state.chartInteraction.regionDragActive = false;
    renderStatusStrip?.([{
      label: state.currentReplayIngestionId
        ? "框选完成，可发送到聊天区、保存区域或删除并回补。"
        : "框选完成，可发送到聊天区或删除并回补。保存区域需等待完整回放加载完成。",
      variant: "good",
    }]);
    syncQuickActions();
  }

  function finishPointerDrag(event) {
    if (activeRegionPointerId !== event.pointerId) {
      return;
    }
    if (state.chartInteraction.regionMode && state.chartInteraction.regionDragActive && state.chartInteraction.draftRegion) {
      event.preventDefault();
      updateRegionDraft(event);
    }
    resetPointerState();
  }

  bindClickAction(els.armRegionButton, () => {
    if (!state.snapshot?.candles?.length) {
      renderStatusStrip?.([{ label: "请先加载一段 K 线数据，再进行框选。", variant: "warn" }]);
      return;
    }
    state.chartInteraction.regionMode = !state.chartInteraction.regionMode;
    state.chartInteraction.regionDragActive = false;
    state.chartInteraction.regionAnchorActive = false;
    regionPointerMoved = false;
    activeRegionPointerId = null;
    if (!state.chartInteraction.regionMode) {
      state.chartInteraction.draftRegion = null;
    }
    renderStatusStrip?.([{
      label: state.chartInteraction.regionMode
        ? "已进入框选模式。可左键点起点再点终点，或直接拖出要删除并回补的时间窗。"
        : "已退出框选模式。",
      variant: "emphasis",
    }]);
    syncQuickActions();
    renderRegionModeSurface();
  });

  document.addEventListener("pointerdown", (event) => {
    if (!isRegionSelectionSurfaceEvent(event) || state.chartInteraction.regionAnchorActive || event.button !== 0) {
      return;
    }
    handleRegionDragStart(event);
    if (!state.chartInteraction.regionDragActive) {
      return;
    }
    regionPointerMoved = false;
    activeRegionPointerId = event.pointerId;
    els.chartRegionCaptureLayer?.setPointerCapture?.(event.pointerId);
  }, true);

  document.addEventListener("click", (event) => {
    if (!isRegionSelectionSurfaceEvent(event) || event.button !== 0) {
      return;
    }
    handleRegionAnchorClick(event);
  }, true);

  window.addEventListener("pointermove", (event) => {
    if (state.chartInteraction.regionAnchorActive && state.chartInteraction.draftRegion) {
      if (!isRegionSelectionSurfaceEvent(event)) {
        return;
      }
      updateRegionDraft(event);
      return;
    }
    if (!state.chartInteraction.regionMode || !state.chartInteraction.regionDragActive || activeRegionPointerId !== event.pointerId) {
      return;
    }
    event.preventDefault();
    regionPointerMoved = true;
    updateRegionDraft(event);
  }, true);

  window.addEventListener("pointerup", (event) => {
    finishPointerDrag(event);
  }, true);

  if (els.chartRegionCaptureLayer) {
    els.chartRegionCaptureLayer.addEventListener("pointerdown", (event) => {
      if (!state.chartInteraction.regionMode || event.button !== 0) {
        return;
      }
      handleRegionDragStart(event);
      if (!state.chartInteraction.regionDragActive) {
        return;
      }
      regionPointerMoved = false;
      activeRegionPointerId = event.pointerId;
      els.chartRegionCaptureLayer.setPointerCapture?.(event.pointerId);
    });

    els.chartRegionCaptureLayer.addEventListener("pointermove", (event) => {
      if (state.chartInteraction.regionAnchorActive && state.chartInteraction.draftRegion) {
        updateRegionDraft(event);
        return;
      }
      if (!state.chartInteraction.regionMode || !state.chartInteraction.regionDragActive || activeRegionPointerId !== event.pointerId) {
        return;
      }
      event.preventDefault();
      regionPointerMoved = true;
      updateRegionDraft(event);
    });

    els.chartRegionCaptureLayer.addEventListener("pointerup", finishPointerDrag);
    els.chartRegionCaptureLayer.addEventListener("pointercancel", finishPointerDrag);
    els.chartRegionCaptureLayer.addEventListener("click", (event) => {
      handleRegionAnchorClick(event);
    });
    els.chartRegionCaptureLayer.addEventListener("lostpointercapture", () => {
      resetPointerState();
    });
  }

  regionDraftTargets
    .filter((target) => target && target !== els.chartRegionCaptureLayer)
    .forEach((target) => {
      target.addEventListener("mousedown", (event) => {
        handleRegionDragStart(event);
      }, true);
    });

  window.addEventListener("mousemove", (event) => {
    if (state.chartInteraction.regionAnchorActive && state.chartInteraction.draftRegion) {
      updateRegionDraft(event);
      return;
    }
    if (activeRegionPointerId != null || !state.chartInteraction.regionMode || !state.chartInteraction.regionDragActive || !state.chartInteraction.draftRegion) {
      return;
    }
    updateRegionDraft(event);
  });

  window.addEventListener("mouseup", (event) => {
    if (activeRegionPointerId != null || !state.chartInteraction.regionMode || !state.chartInteraction.regionDragActive || !state.chartInteraction.draftRegion) {
      return;
    }
    updateRegionDraft(event);
    state.chartInteraction.regionDragActive = false;
    syncQuickActions();
  });

  window.addEventListener("blur", () => {
    resetPointerState({ clearMoved: true });
  });
}
