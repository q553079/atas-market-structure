import { pickModelOptions } from "./replay_workbench_ui_utils.js";

export function createModelSwitcherController({
  state,
  els,
  getActiveThread,
  appendAiChatMessage,
  persistSessions,
  sessionMemoryEngine,
  renderSnapshot,
}) {
  async function refreshHandoffPreview({ forceServer = false } = {}) {
    const session = getActiveThread();
    if (!session) {
      return "";
    }
    session.handoffMode = sessionMemoryEngine.normalizeHandoffMode(session.handoffMode || els.handoffModeSelect?.value);
    if (els.handoffModeSelect) {
      els.handoffModeSelect.value = session.handoffMode;
    }
    if (els.handoffSummaryPreview) {
      els.handoffSummaryPreview.textContent = "正在生成交接摘要…";
    }
    const preview = await sessionMemoryEngine.buildHandoffPacket(session, { forceServer });
    if (els.handoffSummaryPreview) {
      els.handoffSummaryPreview.textContent = preview || "暂无交接摘要";
    }
    return preview;
  }

  async function openModelSwitcher() {
    const session = getActiveThread();
    els.aiModelSwitcherModal.classList.remove("is-hidden");
    const modelOptions = state.modelOptions && state.modelOptions.length > 0 ? state.modelOptions : pickModelOptions();
    els.activeModelSelect.innerHTML = modelOptions.map((item) => `<option value="${item.value}" ${item.value === session.activeModel ? "selected" : ""}>${item.label}</option>`).join("");
    session.handoffMode = sessionMemoryEngine.normalizeHandoffMode(session.handoffMode || "summary_only");
    els.handoffModeSelect.value = session.handoffMode;
    await refreshHandoffPreview();
    const handleEsc = (e) => {
      if (e.key === "Escape") {
        els.aiModelSwitcherModal.classList.add("is-hidden");
        document.removeEventListener("keydown", handleEsc);
      }
    };
    document.addEventListener("keydown", handleEsc);
    const handleBackgroundClick = (e) => {
      if (e.target === els.aiModelSwitcherModal) {
        els.aiModelSwitcherModal.classList.add("is-hidden");
        els.aiModelSwitcherModal.removeEventListener("click", handleBackgroundClick);
        document.removeEventListener("keydown", handleEsc);
      }
    };
    els.aiModelSwitcherModal.addEventListener("click", handleBackgroundClick);
  }

  async function confirmModelSwitch() {
    const session = getActiveThread();
    session.activeModel = els.activeModelSelect.value;
    session.handoffMode = sessionMemoryEngine.normalizeHandoffMode(els.handoffModeSelect.value);
    session.handoffSummary = await sessionMemoryEngine.buildHandoffPacket(session, { forceServer: true });
    appendAiChatMessage("assistant", `已切换到 ${session.activeModel || "服务端默认"}，交接信息已按 ${session.handoffMode} 模式刷新。`, {
      preset: "system",
      provider: "system",
      model: session.activeModel || "default",
      handoff_mode: session.handoffMode,
    }, session.id, session.title);
    els.aiModelSwitcherModal.classList.add("is-hidden");
    persistSessions();
    renderSnapshot();
  }

  function bindModelSwitcherActions() {
    els.aiModelSwitcherButton?.addEventListener("click", () => {
      openModelSwitcher();
    });
    els.closeModelSwitcherButton?.addEventListener("click", () => {
      els.aiModelSwitcherModal.classList.add("is-hidden");
    });
    els.showHandoffSummaryButton?.addEventListener("click", () => {
      refreshHandoffPreview({ forceServer: true });
    });
    els.handoffModeSelect?.addEventListener("change", () => {
      const session = getActiveThread();
      if (!session) {
        return;
      }
      session.handoffMode = sessionMemoryEngine.normalizeHandoffMode(els.handoffModeSelect.value);
      refreshHandoffPreview();
    });
    els.confirmModelSwitchButton?.addEventListener("click", () => {
      confirmModelSwitch();
    });
  }

  return {
    openModelSwitcher,
    confirmModelSwitch,
    bindModelSwitcherActions,
    refreshHandoffPreview,
  };
}
