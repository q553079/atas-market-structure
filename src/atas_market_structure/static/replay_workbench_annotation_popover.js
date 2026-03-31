import {
  escapeHtml,
  formatPrice,
  summarizeText,
  translateVerificationStatus,
} from "./replay_workbench_ui_utils.js";
import { getAnnotationTypeLabel, isAnnotationDeleted } from "./replay_workbench_annotation_utils.js";

function formatLocalDateTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function buildDetailRows(items = []) {
  return items
    .filter(([, value]) => value !== "" && value != null)
    .map(([label, value]) => `
      <div class="annotation-detail-item">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(String(value))}</strong>
      </div>
    `)
    .join("");
}

function buildTargetMetrics(target, siblings = []) {
  const entry = siblings.find((item) => item.type === "entry_line") || target;
  const stop = siblings.find((item) => item.type === "stop_loss") || (target.type === "stop_loss" ? target : null);
  const tps = siblings.filter((item) => item.type === "take_profit").sort((a, b) => (a.tp_level || 0) - (b.tp_level || 0));
  const zones = siblings.filter((item) => ["support_zone", "resistance_zone", "no_trade_zone", "zone"].includes(item.type));
  const priceLines = [
    entry?.entry_price != null ? ["入场", formatPrice(entry.entry_price)] : null,
    stop?.stop_price != null ? ["止损", `${formatPrice(stop.stop_price)} · ${translateVerificationStatus(stop.status || "active")}`] : null,
    ...tps.map((tp) => [`TP${tp.tp_level || "?"}`, `${formatPrice(tp.target_price)} · ${translateVerificationStatus(tp.status || "active")}`]),
    target.target_price != null && !tps.length ? ["目标", formatPrice(target.target_price)] : null,
    target.price_low != null && target.price_high != null ? ["对象区间", `${formatPrice(target.price_low)} - ${formatPrice(target.price_high)}`] : null,
    zones.length ? ["关联区域", zones.map((item) => item.label || getAnnotationTypeLabel(item.type)).join(" / ")] : null,
  ].filter(Boolean);
  return buildDetailRows(priceLines) || `<div class="annotation-detail-note">当前对象暂无可展示的价格结构信息。</div>`;
}

export function createAnnotationPopoverController({
  state,
  els,
  onAnnotationAction,
}) {
  let actionsBound = false;

  function showAnnotationPopover(annotationId) {
    const target = (state.aiAnnotations || []).find((item) => item.id === annotationId);
    if (!target || isAnnotationDeleted(target) || !els.annotationPopover) {
      hideAnnotationPopover();
      return;
    }
    state.annotationPopoverTargetId = annotationId;
    const session = state.aiThreads.find((item) => item.id === target.session_id);
    const siblings = (state.aiAnnotations || []).filter((item) => item.plan_id && item.plan_id === target.plan_id && !isAnnotationDeleted(item));
    const sourceMessage = session?.messages?.find((item) => item.message_id === target.message_id) || null;
    const replyTitle = sourceMessage?.replyTitle || sourceMessage?.meta?.replyTitle || sourceMessage?.meta?.reply_title || null;
    const sourceSessionLabel = session?.title || "会话";
    const sourceReplyLabel = replyTitle || summarizeText(sourceMessage?.content || "", 32) || "未命名回复";
    const confidenceValue = Number(target.confidence);
    const tags = [
      `<span class="annotation-object-chip">${escapeHtml(getAnnotationTypeLabel(target.type))}</span>`,
      `<span class="annotation-object-chip">${escapeHtml(translateVerificationStatus(target.status || "active"))}</span>`,
      target.visible === false ? `<span class="annotation-object-chip warn">已隐藏</span>` : `<span class="annotation-object-chip good">显示中</span>`,
      target.pinned ? `<span class="annotation-object-chip good">已固定</span>` : "",
    ].filter(Boolean).join("");

    els.annotationPopover.classList.remove("is-hidden");
    els.annotationPopoverTitle.textContent = target.label || getAnnotationTypeLabel(target.type) || "AI 标记";
    els.annotationPopoverMeta.textContent = `来源会话：${sourceSessionLabel} / 来源回复：${sourceReplyLabel} / 消息：${target.message_id || "无消息"}`;
    els.annotationPopoverBody.innerHTML = `
      <div class="annotation-detail-grid">
        <div class="annotation-detail-card">
          <div class="annotation-object-chip-row">${tags}</div>
          <div class="annotation-detail-list">
            ${buildDetailRows([
              ["对象类型", getAnnotationTypeLabel(target.type)],
              ["对象状态", translateVerificationStatus(target.status || "active")],
              ["来源会话", sourceSessionLabel],
              ["来源消息", target.message_id || "无消息"],
              ["固定状态", target.pinned ? "已固定" : "未固定"],
              ["显示状态", target.visible === false ? "已隐藏" : "显示中"],
              ["计划 ID", target.plan_id || "--"],
              ["更新时间", formatLocalDateTime(target.updated_at || target.end_time || target.created_at)],
            ])}
          </div>
        </div>
        <div class="annotation-detail-card">
          <h4>价格与结构</h4>
          <div class="annotation-detail-list">
            ${buildTargetMetrics(target, siblings)}
          </div>
        </div>
        <div class="annotation-detail-card">
          <h4>分析备注</h4>
          <div class="annotation-detail-note">${escapeHtml(target.reason || sourceMessage?.meta?.summary || "当前对象暂无补充说明。")}</div>
          <div class="annotation-detail-list">
            ${buildDetailRows([
              ["优先级", target.priority ?? "--"],
              ["置信度", Number.isFinite(confidenceValue) ? `${Math.round(confidenceValue * 100)}%` : "--"],
              ["开始时间", formatLocalDateTime(target.start_time || target.created_at)],
              ["结束时间", formatLocalDateTime(target.end_time || target.expires_at)],
            ])}
          </div>
        </div>
      </div>
    `;
    if (els.annotationPopoverLocateButton) {
      els.annotationPopoverLocateButton.textContent = "定位图表";
    }
    if (els.annotationPopoverOnlyButton) {
      els.annotationPopoverOnlyButton.textContent = "仅显示此对象";
    }
    if (els.annotationPopoverToggleButton) {
      els.annotationPopoverToggleButton.textContent = target.visible === false ? "显示对象" : "隐藏对象";
    }
    if (els.annotationPopoverPinButton) {
      els.annotationPopoverPinButton.textContent = target.pinned ? "取消固定" : "固定对象";
    }
  }

  function hideAnnotationPopover() {
    if (els.annotationPopover) {
      els.annotationPopover.classList.add("is-hidden");
    }
    state.annotationPopoverTargetId = null;
  }

  function bindAnnotationPopoverActions() {
    if (actionsBound) {
      return;
    }
    actionsBound = true;
    els.closeAnnotationPopoverButton?.addEventListener("click", hideAnnotationPopover);
    els.annotationPopover?.addEventListener("click", (event) => {
      if (event.target === els.annotationPopover) {
        hideAnnotationPopover();
      }
    });
    [
      [els.annotationPopoverLocateButton, "locate"],
      [els.annotationPopoverSourceButton, "source"],
      [els.annotationPopoverOnlyButton, "only"],
      [els.annotationPopoverToggleButton, "toggle"],
      [els.annotationPopoverPinButton, "pin"],
      [els.annotationPopoverDeleteButton, "delete"],
    ].forEach(([button, action]) => {
      button?.addEventListener("click", () => {
        const id = state.annotationPopoverTargetId;
        if (!id) {
          return;
        }
        onAnnotationAction?.(action, id);
      });
    });
  }

  return {
    showAnnotationPopover,
    hideAnnotationPopover,
    bindAnnotationPopoverActions,
  };
}
