import { formatPrice, writeStorage } from "./replay_workbench_ui_utils.js";

export function createAnnotationPopoverController({
  state,
  els,
  setActiveThread,
  renderSnapshot,
  jumpToMessage,
}) {
  function showAnnotationPopover(annotationId) {
    const target = (state.aiAnnotations || []).find((item) => item.id === annotationId);
    if (!target || !els.annotationPopover) {
      return;
    }
    state.annotationPopoverTargetId = annotationId;
    const session = state.aiThreads.find((item) => item.id === target.session_id);
    const siblings = (state.aiAnnotations || []).filter((item) => item.plan_id && item.plan_id === target.plan_id);
    const stop = siblings.find((item) => item.type === "stop_loss");
    const tps = siblings.filter((item) => item.type === "take_profit").sort((a, b) => (a.tp_level || 0) - (b.tp_level || 0));
    const sourceMessage = session?.messages?.find((item) => item.message_id === target.message_id) || null;
    const replyTitle = sourceMessage?.replyTitle || sourceMessage?.meta?.replyTitle || sourceMessage?.meta?.reply_title || null;
    const sourceSessionLabel = session?.title || "会话";
    const sourceReplyLabel = replyTitle || sourceMessage?.content?.slice(0, 24) || "未命名回复";
    els.annotationPopover.classList.remove("is-hidden");
    els.annotationPopoverTitle.textContent = target.label || target.type || "AI 标记";
    els.annotationPopoverMeta.textContent = `来源会话：${sourceSessionLabel} / 来源回复：${sourceReplyLabel} / 消息：${target.message_id || "无消息"}`;
    const bodyLines = [
      `状态：${target.status || "active"}`,
      target.entry_price != null ? `入场：${formatPrice(target.entry_price)}` : "",
      stop?.stop_price != null ? `止损：${formatPrice(stop.stop_price)}（${stop.status || "active"}）` : (target.stop_price != null ? `止损：${formatPrice(target.stop_price)}` : ""),
      ...tps.map((tp) => `TP${tp.tp_level || "?"}：${formatPrice(tp.target_price)}（${tp.status || "active"}）`),
      target.target_price != null ? `目标：${formatPrice(target.target_price)}` : "",
      target.price_low != null && target.price_high != null ? `区域：${formatPrice(target.price_low)} - ${formatPrice(target.price_high)}` : "",
      target.reason ? `原因：${target.reason}` : "",
    ].filter(Boolean);
    els.annotationPopoverBody.textContent = bodyLines.join("\n");
  }

  function hideAnnotationPopover() {
    if (els.annotationPopover) {
      els.annotationPopover.classList.add("is-hidden");
    }
    state.annotationPopoverTargetId = null;
  }

  function openAnnotationSource(annotationId) {
    const target = (state.aiAnnotations || []).find((item) => item.id === annotationId);
    if (!target) {
      return;
    }
    state.selectedAnnotationId = annotationId;
    state.annotationFilters.selectedOnly = false;
    state.annotationFilters.onlyCurrentSession = false;
    state.annotationFilters.sessionIds = target.session_id ? [target.session_id] : [];
    state.annotationFilters.messageIds = target.message_id ? [target.message_id] : [];
    state.annotationFilters.annotationIds = target.plan_id
      ? state.aiAnnotations.filter((item) => item.plan_id === target.plan_id).map((item) => item.id)
      : [annotationId];
    writeStorage("annotationFilters", state.annotationFilters);
    setActiveThread(target.session_id, state.aiThreads.find((s) => s.id === target.session_id)?.title || "会话");
    renderSnapshot();
    window.setTimeout(() => jumpToMessage(target.message_id), 60);
  }

  function bindAnnotationPopoverActions() {
    els.closeAnnotationPopoverButton?.addEventListener("click", hideAnnotationPopover);
    els.annotationPopoverSourceButton?.addEventListener("click", () => {
      const id = state.annotationPopoverTargetId;
      hideAnnotationPopover();
      if (id) {
        openAnnotationSource(id);
      }
    });
    els.annotationPopoverOnlyButton?.addEventListener("click", () => {
      const id = state.annotationPopoverTargetId;
      if (!id) return;
      const base = state.aiAnnotations.find((row) => row.id === id);
      state.selectedAnnotationId = id;
      state.annotationFilters.onlyCurrentSession = false;
      state.annotationFilters.sessionIds = base?.session_id ? [base.session_id] : [];
      state.annotationFilters.messageIds = base?.message_id ? [base.message_id] : [];
      state.annotationFilters.annotationIds = base?.plan_id
        ? state.aiAnnotations.filter((item) => item.plan_id === base.plan_id).map((item) => item.id)
        : [id];
      writeStorage("annotationFilters", state.annotationFilters);
      hideAnnotationPopover();
      renderSnapshot();
    });
    els.annotationPopoverHideButton?.addEventListener("click", () => {
      const target = state.aiAnnotations.find((item) => item.id === state.annotationPopoverTargetId);
      if (!target) return;
      target.visible = false;
      hideAnnotationPopover();
      renderSnapshot();
    });
  }

  return {
    showAnnotationPopover,
    hideAnnotationPopover,
    openAnnotationSource,
    bindAnnotationPopoverActions,
  };
}
