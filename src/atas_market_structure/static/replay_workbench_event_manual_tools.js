function isEditableTarget(target) {
  if (!target) {
    return false;
  }
  const tag = String(target.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

function coerceNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function toIsoString(value) {
  if (value == null) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

export function createWorkbenchEventManualTools({
  state,
  els,
  renderStatusStrip,
  ensureActiveSessionPersisted,
  createManualEventCandidate,
  renderSnapshot,
}) {
  function getManualToolState() {
    state.eventWorkbench = state.eventWorkbench || {};
    state.eventWorkbench.manualTool = state.eventWorkbench.manualTool || {
      mode: null,
      lastPointer: null,
      pending: false,
    };
    return state.eventWorkbench.manualTool;
  }

  function updateToolbarUi() {
    const manualTool = getManualToolState();
    const mode = String(manualTool.mode || "").trim();
    const hasDraft = !!state.chartInteraction?.draftRegion;
    els.manualKeyLevelButton?.classList.toggle("is-active", mode === "key_level");
    els.manualEventZoneButton?.classList.toggle("is-active", mode === "price_zone");
    els.manualRiskNoteButton?.classList.toggle("is-active", mode === "risk_note");
    if (els.saveEventCandidateButton) {
      els.saveEventCandidateButton.hidden = mode !== "price_zone";
      els.saveEventCandidateButton.disabled = !hasDraft || !!manualTool.pending;
    }
    if (els.cancelEventCandidateToolButton) {
      els.cancelEventCandidateToolButton.hidden = !mode;
    }
    if (els.eventToolMeta) {
      if (mode === "price_zone") {
        els.eventToolMeta.textContent = hasDraft
          ? "已框选区域，点击“保存事件”落库为 EventCandidate。"
          : "区域工具已激活，直接在图上拖拽框选价格区域。";
      } else if (mode === "key_level") {
        els.eventToolMeta.textContent = "关键位工具：点击按钮或按 L，按当前光标/选中 K 线创建。";
      } else if (mode === "risk_note") {
        els.eventToolMeta.textContent = "风险工具：点击按钮或按 R，按当前光标/选中 K 线创建。";
      } else {
        els.eventToolMeta.textContent = "L 建关键位，Z 建区域，R 建风险。";
      }
    }
  }

  function setLastPointer(pointer = null) {
    const manualTool = getManualToolState();
    manualTool.lastPointer = pointer || null;
    updateToolbarUi();
  }

  function resolvePointerFallback() {
    const manualTool = getManualToolState();
    if (manualTool.lastPointer?.price != null) {
      return manualTool.lastPointer;
    }
    const candles = state.snapshot?.candles || [];
    const selected = candles[state.selectedCandleIndex ?? -1] || candles[state.chartView?.endIndex ?? -1] || candles[candles.length - 1];
    if (!selected) {
      return null;
    }
    return {
      timestamp: new Date(selected.started_at).getTime(),
      price: coerceNumber(selected.close) ?? coerceNumber(selected.open),
    };
  }

  async function createInstantCandidate(mode) {
    const session = await ensureActiveSessionPersisted?.();
    if (!session?.id) {
      renderStatusStrip?.([{ label: "当前没有可写入的事件会话。", variant: "warn" }]);
      return null;
    }
    const pointer = resolvePointerFallback();
    if (!pointer || pointer.price == null) {
      renderStatusStrip?.([{ label: "当前没有可用的图表价格锚点。", variant: "warn" }]);
      return null;
    }
    const timestampIso = toIsoString(pointer.timestamp);
    if (mode === "key_level") {
      return createManualEventCandidate?.({
        candidate_kind: "key_level",
        title: `手工关键位 ${pointer.price.toFixed(2)}`,
        summary: "交易员在图表上手工创建的关键价位。",
        price_ref: pointer.price,
        anchor_start_ts: timestampIso,
        anchor_end_ts: timestampIso,
        metadata: { tool: "manual_key_level" },
      });
    }
    if (mode === "risk_note") {
      return createManualEventCandidate?.({
        candidate_kind: "risk_note",
        title: `手工风险位 ${pointer.price.toFixed(2)}`,
        summary: "交易员在图表上手工创建的风险提醒。",
        price_ref: pointer.price,
        anchor_start_ts: timestampIso,
        anchor_end_ts: timestampIso,
        metadata: { tool: "manual_risk_note" },
      });
    }
    return null;
  }

  async function runInstantTool(mode) {
    const manualTool = getManualToolState();
    manualTool.mode = mode;
    updateToolbarUi();
    const mutation = await createInstantCandidate(mode);
    manualTool.mode = null;
    updateToolbarUi();
    renderSnapshot?.();
    return mutation;
  }

  function clearDraftToolState({ render = true } = {}) {
    const manualTool = getManualToolState();
    manualTool.mode = null;
    manualTool.pending = false;
    if (state.chartInteraction) {
      state.chartInteraction.regionMode = false;
      state.chartInteraction.draftRegion = null;
    }
    updateToolbarUi();
    if (render) {
      renderSnapshot?.();
    }
  }

  function armZoneTool() {
    const manualTool = getManualToolState();
    manualTool.mode = "price_zone";
    if (state.chartInteraction) {
      state.chartInteraction.regionMode = true;
      state.chartInteraction.draftRegion = null;
    }
    updateToolbarUi();
    renderStatusStrip?.([{ label: "区域事件工具已激活，请在图表上拖拽框选。", variant: "emphasis" }]);
    renderSnapshot?.();
  }

  async function saveZoneCandidateFromDraft() {
    const manualTool = getManualToolState();
    const draft = state.chartInteraction?.draftRegion;
    const session = await ensureActiveSessionPersisted?.();
    if (!session?.id) {
      renderStatusStrip?.([{ label: "当前没有可写入的事件会话。", variant: "warn" }]);
      return null;
    }
    if (!draft) {
      renderStatusStrip?.([{ label: "当前还没有框选区域。", variant: "warn" }]);
      return null;
    }
    manualTool.pending = true;
    updateToolbarUi();
    try {
      const mutation = await createManualEventCandidate?.({
        candidate_kind: "price_zone",
        title: `手工区域 ${(coerceNumber(draft.price_low) ?? 0).toFixed(2)} - ${(coerceNumber(draft.price_high) ?? 0).toFixed(2)}`,
        summary: "交易员在图表上框选的价格区域。",
        anchor_start_ts: toIsoString(draft.started_at),
        anchor_end_ts: toIsoString(draft.ended_at),
        price_lower: coerceNumber(draft.price_low),
        price_upper: coerceNumber(draft.price_high),
        metadata: { tool: "manual_price_zone" },
      });
      clearDraftToolState({ render: true });
      return mutation;
    } finally {
      manualTool.pending = false;
      updateToolbarUi();
    }
  }

  function installBindings() {
    els.manualKeyLevelButton?.addEventListener("click", async () => {
      await runInstantTool("key_level");
    });
    els.manualEventZoneButton?.addEventListener("click", () => {
      armZoneTool();
    });
    els.manualRiskNoteButton?.addEventListener("click", async () => {
      await runInstantTool("risk_note");
    });
    els.saveEventCandidateButton?.addEventListener("click", async () => {
      await saveZoneCandidateFromDraft();
    });
    els.cancelEventCandidateToolButton?.addEventListener("click", () => {
      clearDraftToolState({ render: true });
      renderStatusStrip?.([{ label: "已取消手工事件工具。", variant: "emphasis" }]);
    });
    window.addEventListener("keydown", async (event) => {
      if (isEditableTarget(event.target)) {
        return;
      }
      if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        await runInstantTool("key_level");
        return;
      }
      if (event.key === "z" || event.key === "Z") {
        event.preventDefault();
        armZoneTool();
        return;
      }
      if (event.key === "r" || event.key === "R") {
        event.preventDefault();
        await runInstantTool("risk_note");
        return;
      }
      if (event.key === "Escape") {
        clearDraftToolState({ render: true });
        return;
      }
      if (event.key === "Enter" && getManualToolState().mode === "price_zone" && state.chartInteraction?.draftRegion) {
        event.preventDefault();
        await saveZoneCandidateFromDraft();
      }
    });
  }

  installBindings();
  updateToolbarUi();

  return {
    setLastPointer,
    updateToolbarUi,
    clearDraftToolState,
    saveZoneCandidateFromDraft,
  };
}
