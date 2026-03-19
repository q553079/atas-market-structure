export function createLayoutController({ els, state, scheduleChartRerender }) {
  function applyLayoutWidths() {
    els.shellLayout.style.setProperty("--left-panel-width", `${state.layout.leftWidth}px`);
    els.shellLayout.style.setProperty("--right-panel-width", `${state.layout.rightWidth}px`);
    els.shellLayout.style.setProperty("--chat-thread-height", `${state.layout.chatHeight}px`);
    scheduleChartRerender();
  }

  function setLeftPanelCollapsed(collapsed) {
    els.shellLayout.classList.toggle("left-collapsed", collapsed);
    els.toggleLeftPanelButton.textContent = collapsed ? "▶" : "◀";
    els.restoreLeftPanelButton.setAttribute("aria-hidden", collapsed ? "false" : "true");
    scheduleChartRerender();
  }

  function setRightPanelCollapsed(collapsed) {
    els.shellLayout.classList.toggle("right-collapsed", collapsed);
    els.toggleRightPanelButton.textContent = collapsed ? "◀" : "▶";
    els.restoreRightPanelButton.setAttribute("aria-hidden", collapsed ? "false" : "true");
    scheduleChartRerender();
  }

  function beginLayoutDrag(kind, event) {
    event.preventDefault();
    event.stopPropagation();
    state.layout.dragKind = kind;
    state.layout.dragStartX = event.clientX;
    state.layout.dragStartY = event.clientY;
    state.layout.dragStartLeftWidth = state.layout.leftWidth;
    state.layout.dragStartRightWidth = state.layout.rightWidth;
    state.layout.dragStartChatHeight = state.layout.chatHeight;
    if (kind === "left") {
      els.leftResizeHandle.classList.add("dragging");
    } else if (kind === "right") {
      els.rightResizeHandle.classList.add("dragging");
    } else if (kind === "chat") {
      els.aiChatResizeHandle.classList.add("dragging");
    }
    document.body.style.userSelect = "none";
    document.body.style.cursor = kind === "chat" ? "row-resize" : "col-resize";
  }

  function updateLayoutDrag(event) {
    if (!state.layout.dragKind) {
      return false;
    }
    if (state.layout.dragKind === "left") {
      const nextWidth = state.layout.dragStartLeftWidth + (event.clientX - state.layout.dragStartX);
      state.layout.leftWidth = Math.max(260, Math.min(520, nextWidth));
    } else if (state.layout.dragKind === "right") {
      const nextWidth = state.layout.dragStartRightWidth - (event.clientX - state.layout.dragStartX);
      state.layout.rightWidth = Math.max(280, Math.min(560, nextWidth));
    } else if (state.layout.dragKind === "chat") {
      const nextHeight = state.layout.dragStartChatHeight + (event.clientY - state.layout.dragStartY);
      state.layout.chatHeight = Math.max(220, Math.min(760, nextHeight));
    }
    applyLayoutWidths();
    return true;
  }

  function finishLayoutDrag() {
    if (!state.layout.dragKind) {
      return;
    }
    els.leftResizeHandle.classList.remove("dragging");
    els.rightResizeHandle.classList.remove("dragging");
    els.aiChatResizeHandle.classList.remove("dragging");
    state.layout.dragKind = null;
    state.layout.dragStartX = null;
    state.layout.dragStartY = null;
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
  }

  function initializePanelToggles() {
    applyLayoutWidths();
    setLeftPanelCollapsed(false);
    setRightPanelCollapsed(false);

    els.toggleLeftPanelButton.addEventListener("click", () => {
      setLeftPanelCollapsed(!els.leftPanel.classList.contains("collapsed"));
    });
    els.toggleRightPanelButton.addEventListener("click", () => {
      setRightPanelCollapsed(!els.rightPanel.classList.contains("collapsed"));
    });
    els.restoreLeftPanelButton.addEventListener("click", () => {
      setLeftPanelCollapsed(false);
    });
    els.restoreRightPanelButton.addEventListener("click", () => {
      setRightPanelCollapsed(false);
    });
    els.leftResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("left", event));
    els.rightResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("right", event));
    els.aiChatResizeHandle.addEventListener("mousedown", (event) => beginLayoutDrag("chat", event));
  }

  return {
    applyLayoutWidths,
    setLeftPanelCollapsed,
    setRightPanelCollapsed,
    beginLayoutDrag,
    updateLayoutDrag,
    finishLayoutDrag,
    initializePanelToggles,
  };
}
