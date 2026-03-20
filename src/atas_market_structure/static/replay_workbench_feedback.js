export function createWorkbenchFeedback({
  state,
  els,
  renderSnapshot,
  translateAction,
  translateVerificationStatus,
}) {
  function renderStatusStrip(items) {
    els.statusStrip.innerHTML = "";
    items.forEach((item) => {
      const chip = document.createElement("div");
      chip.className = `chip ${item.variant || ""}`.trim();
      chip.textContent = item.label;
      els.statusStrip.appendChild(chip);
    });
  }

  function buildStatusChips(result) {
    const chips = [
      { label: translateAction(result.action), variant: result.action === "atas_fetch_required" ? "warn" : "good" },
    ];
    if (result.summary) {
      chips.push({ label: `核对：${translateVerificationStatus(result.summary.verification_status)}`, variant: result.summary.verification_status === "durable" ? "good" : "emphasis" });
      chips.push({ label: `${result.summary.verification_count}/${result.summary.verification_passes_to_lock} 次核对`, variant: "emphasis" });
    }
    if (result.integrity) {
      chips.push({ label: `完整性：${result.integrity.status}`, variant: result.integrity.status === "complete" ? "good" : "warn" });
      if (result.integrity.missing_bar_count) {
        chips.push({ label: `缺失 ${result.integrity.missing_bar_count} 根`, variant: "warn" });
      }
    }
    if (result.atas_backfill_request?.request_id) {
      chips.push({ label: `补数 ${result.atas_backfill_request.status}`, variant: "emphasis" });
    }
    if (result.local_message_count) {
      chips.push({ label: `${result.local_message_count} 条本地消息`, variant: "" });
    }
    return chips;
  }

  function renderError(error, options = {}) {
    const preserveSnapshot = Boolean(options.preserveSnapshot);
    state.aiReview = null;
    if (!preserveSnapshot) {
      state.snapshot = null;
      state.currentReplayIngestionId = null;
      state.manualRegions = [];
      state.selectedCandleIndex = null;
      state.selectedFootprintBar = null;
      state.chartView = null;
    }
    state.buildResponse = {
      action: "atas_fetch_required",
      cache_key: els.cacheKey.value.trim(),
      reason: error.message || String(error),
      local_message_count: 0,
      replay_snapshot_id: null,
      ingestion_id: null,
      summary: null,
      cache_record: null,
      atas_fetch_request: null,
    };
    renderStatusStrip([{ label: "请求失败", variant: "warn" }]);
    renderSnapshot();
  }

  function renderAiError(error) {
    state.aiReview = null;
    renderStatusStrip([{ label: "AI 复盘失败", variant: "warn" }]);
    els.aiReview.className = "empty-note";
    els.aiReview.textContent = error.message || String(error);
  }

  return {
    renderStatusStrip,
    buildStatusChips,
    renderError,
    renderAiError,
  };
}
