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
  let actionsBound = false;

  function getResolvedTargetModel(session) {
    return els.activeModelSelect?.value || session?.activeModel || null;
  }

  function getHandoffModeLabel(mode) {
    if (mode === "summary_plus_recent_3") {
      return "会话主信息 + 最近3轮问答";
    }
    if (mode === "question_only") {
      return "仅当前问题";
    }
    return "会话主信息";
  }

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
    const preview = await sessionMemoryEngine.buildHandoffPacket(session, {
      forceServer,
      targetModel: getResolvedTargetModel(session),
      commit: false,
    });
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
    const previousModel = session.activeModel || "";
    const nextModel = els.activeModelSelect.value;
    session.activeModel = nextModel;
    session.handoffMode = sessionMemoryEngine.normalizeHandoffMode(els.handoffModeSelect.value);
    const handoffSummary = await sessionMemoryEngine.buildHandoffPacket(session, {
      forceServer: true,
      targetModel: nextModel,
      commit: true,
    });
    const activePlans = Array.isArray(session.lastHandoffPacket?.active_plans) ? session.lastHandoffPacket.active_plans.length : 0;
    const activeAnnotations = Array.isArray(session.lastHandoffPacket?.active_annotations) ? session.lastHandoffPacket.active_annotations.length : 0;
    const modeLabel = getHandoffModeLabel(session.handoffMode);
    const lead = previousModel && previousModel !== nextModel
      ? `已从 ${previousModel} 切换到 ${nextModel || "服务端默认"}`
      : `已刷新 ${nextModel || "服务端默认"} 的交接摘要`;
    const detailParts = [
      `模式：${modeLabel}`,
      activePlans ? `活动计划 ${activePlans} 项` : "",
      activeAnnotations ? `关键对象 ${activeAnnotations} 项` : "",
    ].filter(Boolean);
    session.handoffSummary = handoffSummary || session.lastHandoffSummary || "";
    appendAiChatMessage("assistant", `${lead}，交接内容包含${detailParts.join("，")}。`, {
      preset: "system",
      provider: "system",
      model: session.activeModel || "default",
      handoff_mode: session.handoffMode,
      handoff_summary: session.lastHandoffSummary || handoffSummary || "",
    }, session.id, session.title);
    els.aiModelSwitcherModal.classList.add("is-hidden");
    persistSessions();
    renderSnapshot();
  }

  function bindModelSwitcherActions() {
    if (actionsBound) {
      return;
    }
    actionsBound = true;
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
    els.activeModelSelect?.addEventListener("change", () => {
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
