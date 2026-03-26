import { createWorkbenchState } from "./replay_workbench_state.js";
import { createWorkbenchElements } from "./replay_workbench_dom.js";
import { fetchJson, toLocalInputValue, createCacheKeyHelpers } from "./replay_workbench_data_utils.js";
import {
  timeframeLabel,
  getPresetThreadMeta,
  createThreadId,
  translateAction,
  translateVerificationStatus,
  translateAcquisitionMode,
  writeStorage,
  readStorage,
  summarizeText,
  escapeHtml,
  createPlanId,
  sanitizeReplayCandles,
} from "./replay_workbench_ui_utils.js";
import { createAiThreadController } from "./replay_workbench_ai_threads.js";
import { createAiChatController } from "./replay_workbench_ai_chat.js";
import { createReplayLoader } from "./replay_workbench_replay_loader.js";
import { createWorkbenchActions } from "./replay_workbench_actions.js";
import { createWorkbenchEventApi } from "./replay_workbench_event_api.js";
import { createWorkbenchEventPanelController } from "./replay_workbench_event_panel.js";
import { createWorkbenchEventManualTools } from "./replay_workbench_event_manual_tools.js";
import { createWorkbenchEventOutcomePanelController } from "./replay_workbench_event_outcome_panel.js";
import { createWorkbenchPromptTracePanelController } from "./replay_workbench_prompt_trace_panel.js";
import {
  createChartViewHelpers,
  clampChartView,
  buildChartViewportKey,
  snapshotChartViewForRegistry,
} from "./replay_workbench_chart_utils.js";
import { focusChartViewOnEventCandidate } from "./replay_workbench_event_overlay.js";
import { createPlanLifecycleEngine } from "./replay_workbench_plan_lifecycle.js";
import { createSessionMemoryEngine } from "./replay_workbench_session_memory.js";
import { createAnnotationPanelController } from "./replay_workbench_annotation_panel.js";
import { createAnnotationPopoverController } from "./replay_workbench_annotation_popover.js";
import { createModelSwitcherController } from "./replay_workbench_model_switcher.js";
import {
  createDefaultAnnotationFilters,
  isAnnotationDeleted,
  normalizeWorkbenchAnnotation,
  updateAnnotationPreference,
} from "./replay_workbench_annotation_utils.js";

function renderStatusStripFactory(els) {
  return function renderStatusStrip(chips = []) {
    if (!els.statusStrip) return;
    try {
      const safeChips = Array.isArray(chips) ? chips : [];
      els.statusStrip.innerHTML = safeChips.map((item) => {
        if (!item || typeof item !== "object") {
          const label = typeof item === "string" ? item : String(item || "");
          return `<span class="chip">${label}</span>`;
        }
        const variant = item.variant ? ` ${item.variant}` : "";
        const label = item.label || String(item || "");
        return `<span class="chip${variant}">${label}</span>`;
      }).join("");
    } catch (error) {
      console.error("renderStatusStrip 错误:", error, chips);
      els.statusStrip.innerHTML = `<span class="chip warn">状态显示错误</span>`;
    }
  };
}

function buildStatusChips(result) {
  if (!result) {
    return [];
  }
  const chips = [];
  if (result.action) {
    chips.push({ label: translateAction(result.action), variant: "good" });
  }
  if (result.summary?.verification_status) {
    chips.push({ label: translateVerificationStatus(result.summary.verification_status), variant: "emphasis" });
  }
  if (result.summary?.acquisition_mode) {
    chips.push({ label: translateAcquisitionMode(result.summary.acquisition_mode), variant: "" });
  }
  if (result.integrity?.status) {
    chips.push({ label: `完整性：${result.integrity.status}`, variant: result.integrity.status === "complete" ? "good" : "warn" });
  }
  if (result.atas_backfill_request?.status) {
    chips.push({ label: `补数：${result.atas_backfill_request.status}`, variant: "emphasis" });
  }
  return chips;
}

function renderGammaDrawer({ state, els }) {
  const gamma = state.optionsGamma || {};
  if (els.gammaCsvPath && document.activeElement !== els.gammaCsvPath) {
    els.gammaCsvPath.value = gamma.sourceCsvPath || "";
  }

  if (els.gammaSummaryContainer) {
    if (gamma.loading) {
      els.gammaSummaryContainer.innerHTML = `<div class="info-card"><h4>Gamma 分析</h4><p>加载中…</p></div>`;
    } else if (gamma.error) {
      els.gammaSummaryContainer.innerHTML = `<div class="info-card"><h4>Gamma 分析失败</h4><p>${escapeHtml(gamma.error)}</p></div>`;
    } else if (gamma.summary) {
      const summary = gamma.summary;
      const resistance = Array.isArray(summary.resistance_levels) ? summary.resistance_levels.slice(0, 3) : [];
      const support = Array.isArray(summary.support_levels) ? summary.support_levels.slice(0, 3) : [];
      els.gammaSummaryContainer.innerHTML = `
        <div class="drawer-card-grid">
          <div class="info-card">
            <h4>来源</h4>
            <p>${escapeHtml(gamma.sourceCsvPath || summary.source_file || "-")}</p>
            <p>${escapeHtml(summary.quote_time || gamma.lastLoadedAt || "-")}</p>
          </div>
          <div class="info-card">
            <h4>环境</h4>
            <p>Regime：${escapeHtml(summary.regime || "-")}</p>
            <p>Zero Gamma：${summary.zero_gamma_proxy ?? "-"}</p>
          </div>
          <div class="info-card">
            <h4>支撑 / 阻力</h4>
            <p>支撑：${escapeHtml(support.map((item) => item.es_equivalent ?? item.strike).join(" / ") || "-")}</p>
            <p>阻力：${escapeHtml(resistance.map((item) => item.es_equivalent ?? item.strike).join(" / ") || "-")}</p>
          </div>
        </div>
        ${gamma.textReport ? `<pre class="summary-preview">${escapeHtml(gamma.textReport)}</pre>` : ""}
      `;
    } else {
      els.gammaSummaryContainer.innerHTML = `<div class="empty-note">尚未加载 Gamma 分析。</div>`;
    }
  }

  if (els.gammaMapContainer) {
    if (gamma.artifacts?.svg_content) {
      els.gammaMapContainer.innerHTML = `
        <div class="info-card">
          <h4>Gamma Map</h4>
          <div class="gamma-map-shell">${gamma.artifacts.svg_content}</div>
          ${gamma.artifacts.svg_path ? `<p class="mono">SVG: ${escapeHtml(gamma.artifacts.svg_path)}</p>` : ""}
        </div>
      `;
    } else {
      els.gammaMapContainer.innerHTML = `<div class="empty-note">暂无 Gamma map。</div>`;
    }
  }

  if (els.gammaAiContainer) {
    if (gamma.aiInterpretation || gamma.aiAnalysisError) {
      els.gammaAiContainer.innerHTML = `
        <div class="info-card">
          <h4>AI 解读</h4>
          ${gamma.aiInterpretation ? `<pre class="summary-preview">${escapeHtml(gamma.aiInterpretation)}</pre>` : ""}
          ${gamma.aiAnalysisError ? `<p>AI 解读失败：${escapeHtml(gamma.aiAnalysisError)}</p>` : ""}
        </div>
      `;
    } else {
      els.gammaAiContainer.innerHTML = `<div class="empty-note">暂无 AI 解读。</div>`;
    }
  }

  if (els.gammaLoadButton) {
    els.gammaLoadButton.disabled = !!gamma.loading;
    els.gammaLoadButton.textContent = gamma.loading ? "加载中…" : "加载 / 刷新 Gamma";
  }
}

function formatCompactLocalDateTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${month}/${day} ${hour}:${minute}`;
}

function getActiveSession(state) {
  return (state.aiThreads || []).find((item) => item.id === state.activeAiThreadId || item.sessionId === state.activeAiThreadId)
    || state.aiThreads?.[0]
    || null;
}

function formatRecapSideLabel(side) {
  const normalized = String(side || "").trim().toLowerCase();
  if (normalized === "buy" || normalized === "long") {
    return "做多";
  }
  if (normalized === "sell" || normalized === "short") {
    return "做空";
  }
  return normalized || "--";
}

function formatRecapStatusLabel(status) {
  const normalized = String(status || "").trim().toLowerCase();
  const statusLabels = {
    active: "进行中",
    pending: "待观察",
    executed: "已执行",
    completed: "已完成",
    invalidated: "已失效",
    cancelled: "已取消",
  };
  return statusLabels[normalized] || (status || "--");
}

function getRecapStatusVariant(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "active" || normalized === "pending") {
    return "active";
  }
  if (normalized === "executed" || normalized === "completed") {
    return "good";
  }
  if (normalized === "invalidated" || normalized === "cancelled") {
    return "warn";
  }
  return "";
}

function renderRecapDrawerMarkup(state) {
  const activeSession = getActiveSession(state);
  const recapItems = Array.isArray(activeSession?.recapItems) ? activeSession.recapItems : [];
  const sections = [];

  if (state.aiReview) {
    sections.push(`
      <div class="info-card">
        <div class="recap-card-head">
          <div>
            <h4>${escapeHtml(state.aiReview.model || "AI复盘")}</h4>
            <p class="recap-card-meta">${escapeHtml(activeSession?.title || "当前会话")}</p>
          </div>
        </div>
        <p>${escapeHtml(summarizeText(state.aiReview.review || state.aiReview.reply_text || "", 600))}</p>
      </div>
    `);
  }

  if (recapItems.length) {
    sections.push(`
      <div class="info-card">
        <div class="recap-card-head">
          <div>
            <h4>计划卡复盘素材</h4>
            <p class="recap-card-meta">${escapeHtml(activeSession?.title || "当前会话")} · ${recapItems.length} 条</p>
          </div>
        </div>
        <div class="recap-item-list">
          ${recapItems.map((item) => {
            const targetLabels = Array.isArray(item.targetLabels) ? item.targetLabels.filter(Boolean) : [];
            const statusVariant = getRecapStatusVariant(item.status);
            const chipClass = `session-workspace-chip${statusVariant ? ` ${statusVariant}` : ""}`;
            const detailChips = [
              `方向 ${formatRecapSideLabel(item.side)}`,
              item.entryLabel ? `入场 ${item.entryLabel}` : "",
              item.stopLabel && item.stopLabel !== "--" ? `止损 ${item.stopLabel}` : "",
              targetLabels.length ? `止盈 ${targetLabels.join(" / ")}` : "",
            ].filter(Boolean);
            return `
              <article class="recap-item-card">
                <div class="recap-item-head">
                  <strong>${escapeHtml(item.title || "AI计划卡")}</strong>
                  <span class="${chipClass}">${escapeHtml(formatRecapStatusLabel(item.status))}</span>
                </div>
                ${detailChips.length ? `<div class="recap-item-chip-row">${detailChips.map((label) => `<span class="session-workspace-chip">${escapeHtml(label)}</span>`).join("")}</div>` : ""}
                ${item.summary ? `<p class="recap-item-note">${escapeHtml(summarizeText(item.summary, 180))}</p>` : ""}
                ${item.structuredSummary ? `<pre class="summary-preview recap-item-structured">${escapeHtml(item.structuredSummary)}</pre>` : ""}
                <p class="recap-card-meta">加入时间：${escapeHtml(formatCompactLocalDateTime(item.addedAt))}${item.sourceModel ? ` · ${escapeHtml(item.sourceModel)}` : ""}</p>
              </article>
            `;
          }).join("")}
        </div>
      </div>
    `);
  }

  if (!sections.length) {
    return `<div class="empty-note">无复盘简报。</div>`;
  }
  return `<div class="recap-panel-stack">${sections.join("")}</div>`;
}

function renderClusterItemsMarkup(cluster) {
  const items = Array.isArray(cluster?.items) ? cluster.items.slice(0, 5) : [];
  if (!items.length) {
    return `<p class="empty-note">无事件明细。</p>`;
  }
  return `
    <div class="context-event-list">
      ${items.map((item) => `
        <div class="context-event-item">
          <strong>${escapeHtml(item.shortLabel || item.title || item.eventKind || "事件")}</strong>
          <p>${escapeHtml(item.metaText || item.priceText || "无附加说明")}</p>
          ${item.notePreviewText ? `<p>${escapeHtml(item.notePreviewText)}</p>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderEventPreviewMarkup(clusters = []) {
  if (!clusters.length) {
    return `<p class="empty-note">当前视图无关键事件。</p>`;
  }
  return `
    <div class="context-event-list">
      ${clusters.slice(0, 4).map((cluster) => `
        <div class="context-event-item">
          <strong>${escapeHtml(cluster.timeLabel || "--")} · ${escapeHtml(cluster.summaryText || "事件")}</strong>
          <p>${escapeHtml(cluster.priceText || "价格未知")}</p>
          ${cluster.notePreviewText ? `<p>${escapeHtml(cluster.notePreviewText)}</p>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderProjectionBadgeRow(items = []) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!values.length) {
    return `<p class="empty-note">无</p>`;
  }
  return `<div class="recap-item-chip-row">${values.map((item) => `<span class="session-workspace-chip">${escapeHtml(String(item))}</span>`).join("")}</div>`;
}

function renderCurrentBeliefMarkup(projection) {
  const currentBelief = projection?.belief_timeline?.current_belief || null;
  if (!currentBelief) {
    return `<div class="info-card"><h4>Belief State</h4><p class="empty-note">当前窗口没有 belief state。</p></div>`;
  }
  const topRegimes = Array.isArray(currentBelief.regime_posteriors)
    ? currentBelief.regime_posteriors.slice(0, 3).map((item) => `${item.regime} ${Number(item.probability || 0).toFixed(2)}`)
    : [];
  const topHypotheses = Array.isArray(currentBelief.event_hypotheses)
    ? currentBelief.event_hypotheses.slice(0, 3).map((item) => {
      const label = item.mapped_event_kind || item.hypothesis_kind;
      return `${label} / ${item.phase} / ${Number(item.posterior_probability || 0).toFixed(2)}`;
    })
    : [];
  const activeAnchors = Array.isArray(currentBelief.active_anchors)
    ? currentBelief.active_anchors.slice(0, 4).map((item) => item.anchor_id || item.anchor_type)
    : [];
  return `
    <div class="info-card">
      <h4>Belief State</h4>
      <p class="mono">${escapeHtml(currentBelief.observed_at || "--")}</p>
      <p class="mono">mode=${escapeHtml(currentBelief.recognition_mode || "--")} · profile=${escapeHtml(currentBelief.profile_version || "--")} · engine=${escapeHtml(currentBelief.engine_version || "--")}</p>
      <p>Top Regimes</p>
      ${renderProjectionBadgeRow(topRegimes)}
      <p>Top Hypotheses</p>
      ${renderProjectionBadgeRow(topHypotheses)}
      <p>Active Anchors</p>
      ${renderProjectionBadgeRow(activeAnchors)}
      <p>Transition Watch</p>
      ${renderProjectionBadgeRow(currentBelief.transition_watch || [])}
      <p>Missing Confirmation</p>
      ${renderProjectionBadgeRow(currentBelief.missing_confirmation || [])}
    </div>
  `;
}

function renderProjectionHealthMarkup(projection) {
  const health = projection?.health_status?.health || null;
  const dataQuality = projection?.health_status?.data_quality || null;
  if (!health || !dataQuality) {
    return `<div class="info-card"><h4>Health</h4><p class="empty-note">未加载 health/degraded 状态。</p></div>`;
  }
  return `
    <div class="info-card">
      <h4>Health / Degraded</h4>
      <p class="mono">status=${escapeHtml(health.status || "--")} · freshness=${escapeHtml(health.freshness || "--")} · completeness=${escapeHtml(health.completeness || "--")}</p>
      <p class="mono">profile=${escapeHtml(health.profile_version || "--")} · engine=${escapeHtml(health.engine_version || "--")}</p>
      <p>Degraded Badges</p>
      ${renderProjectionBadgeRow(health.degraded_reasons || [])}
      <p>Source Status</p>
      ${renderProjectionBadgeRow((dataQuality.source_statuses || []).map((item) => `${item.source_kind}:${item.available ? "ok" : "missing"}`))}
    </div>
  `;
}

function renderProjectionEpisodesMarkup(projection) {
  const items = Array.isArray(projection?.episode_reviews?.items) ? projection.episode_reviews.items.slice(0, 6) : [];
  if (!items.length) {
    return `<div class="info-card"><h4>Closed Episodes</h4><p class="empty-note">当前窗口没有 closed episode。</p></div>`;
  }
  return `
    <div class="info-card">
      <h4>Closed Episodes</h4>
      <div class="recap-item-list">
        ${items.map((item) => `
          <article class="recap-item-card">
            <div class="recap-item-head">
              <strong>${escapeHtml(item.episode.event_kind || "episode")}</strong>
              <span class="session-workspace-chip">${escapeHtml(item.summary_status || "--")}</span>
            </div>
            <p class="recap-card-meta">${escapeHtml(formatCompactLocalDateTime(item.episode.started_at))} → ${escapeHtml(formatCompactLocalDateTime(item.episode.ended_at))}</p>
            ${item.episode.key_evidence_summary?.length ? `<p>${escapeHtml(item.episode.key_evidence_summary.slice(0, 3).join(" / "))}</p>` : ""}
            ${item.evaluation?.diagnosis?.supporting_reasons?.length ? `<p>${escapeHtml(item.evaluation.diagnosis.supporting_reasons.slice(0, 3).join(" / "))}</p>` : ""}
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderProjectionEvaluationsMarkup(projection) {
  const items = Array.isArray(projection?.episode_evaluations?.items) ? projection.episode_evaluations.items.slice(0, 6) : [];
  if (!items.length) {
    return `<div class="info-card"><h4>Episode Evaluation</h4><p class="empty-note">当前窗口没有 episode evaluation。</p></div>`;
  }
  return `
    <div class="info-card">
      <h4>Episode Evaluation</h4>
      <div class="recap-item-list">
        ${items.map((item) => `
          <article class="recap-item-card">
            <div class="recap-item-head">
              <strong>${escapeHtml(item.evaluation.evaluated_event_kind || "evaluation")}</strong>
              <span class="session-workspace-chip">${escapeHtml(item.primary_failure_mode || "--")}</span>
            </div>
            <p class="recap-card-meta">${escapeHtml(formatCompactLocalDateTime(item.evaluation.evaluated_at))}</p>
            <p>selection=${escapeHtml(String(item.evaluation.scores?.hypothesis_selection_score ?? "--"))}
              / confirm=${escapeHtml(String(item.evaluation.scores?.confirmation_timing_score ?? "--"))}
              / invalidate=${escapeHtml(String(item.evaluation.scores?.invalidation_timing_score ?? "--"))}</p>
            <p>transition=${escapeHtml(String(item.evaluation.scores?.transition_handling_score ?? "--"))}
              / calibration=${escapeHtml(String(item.evaluation.scores?.calibration_score ?? "--"))}</p>
            <p>Candidate Parameters</p>
            ${renderProjectionBadgeRow(item.candidate_parameters || [])}
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderProjectionTuningMarkup(projection) {
  const metadata = projection?.metadata || null;
  const items = Array.isArray(projection?.tuning_reviews?.items) ? projection.tuning_reviews.items.slice(0, 4) : [];
  const metadataCard = metadata ? `
    <div class="info-card">
      <h4>Profile / Engine</h4>
      <p class="mono">profile=${escapeHtml(metadata.active_profile?.profile_version || "--")} · ontology=${escapeHtml(metadata.active_profile?.ontology_version || "--")}</p>
      <p class="mono">engine=${escapeHtml(metadata.active_build?.engine_version || "--")} · status=${escapeHtml(metadata.active_build?.status || "--")}</p>
      ${metadata.latest_patch_candidate ? `<p class="mono">latest patch=${escapeHtml(metadata.latest_patch_candidate.candidate_id || "--")} / ${escapeHtml(metadata.latest_patch_candidate_status || "--")}</p>` : `<p class="empty-note">当前没有 patch candidate。</p>`}
    </div>
  ` : "";
  const recommendationCard = items.length ? `
    <div class="info-card">
      <h4>AI Recommendation / Patch Compare</h4>
      <div class="recap-item-list">
        ${items.map((item) => `
          <article class="recap-item-card">
            <div class="recap-item-head">
              <strong>${escapeHtml(item.recommendation.advisor_kind || "recommendation")}</strong>
              <span class="session-workspace-chip">${escapeHtml(item.recommendation.confidence || "--")}</span>
            </div>
            <p class="recap-card-meta">${escapeHtml(formatCompactLocalDateTime(item.recommendation.generated_at))}</p>
            <p>${escapeHtml(summarizeText(item.recommendation.expected_improvement || "", 180))}</p>
            ${item.recommendation.recommendations?.length ? `<p>${escapeHtml(item.recommendation.recommendations.slice(0, 3).map((entry) => `${entry.parameter}:${entry.direction}->${entry.proposed_value}`).join(" / "))}</p>` : ""}
            ${item.patch_candidate ? `<p class="mono">patch=${escapeHtml(item.patch_candidate.proposed_profile_version || "--")} / status=${escapeHtml(item.patch_candidate_status || "--")}</p>` : `<p class="empty-note">无 patch candidate。</p>`}
            ${item.latest_validation_result?.preview?.changed_fields?.length ? `<p>${escapeHtml(item.latest_validation_result.preview.changed_fields.slice(0, 3).map((entry) => `${entry.field_path}:${entry.previous_value}->${entry.next_value}`).join(" / "))}</p>` : ""}
            ${item.latest_validation_result ? `<p class="mono">validation=${escapeHtml(item.latest_validation_result.validation_status || "--")} / promotion_ready=${escapeHtml(String(item.latest_validation_result.promotion_ready))}</p>` : ""}
          </article>
        `).join("")}
      </div>
    </div>
  ` : `<div class="info-card"><h4>AI Recommendation / Patch Compare</h4><p class="empty-note">当前窗口没有 tuning recommendation。</p></div>`;
  return `${metadataCard}${recommendationCard}`;
}

function renderDrawers({ state, els }) {
  const snapshot = state.snapshot;
  const projection = state.reviewProjection || null;
  const eventModel = state.chartEventModel || null;
  const selectedCluster = eventModel?.selectedCluster || null;
  const topVisibleClusters = Array.isArray(eventModel?.topVisibleClusters) ? eventModel.topVisibleClusters : [];
  const symbol = snapshot?.instrument_symbol || state.topBar.symbol;
  const timeframe = timeframeLabel(snapshot?.display_timeframe || state.topBar.timeframe);
  const syncLabel = formatCompactLocalDateTime(state.topBar.lastSyncedAt);
  const marketMeta = syncLabel && syncLabel !== "--"
    ? `${symbol} / ${timeframe} · ${syncLabel}`
    : `${symbol} / ${timeframe}`;
  els.drawerContextPanel.innerHTML = snapshot
    ? `
      <div class="info-card">
        <h4>盘面</h4>
        <p>${escapeHtml(marketMeta)}</p>
        <p>${escapeHtml(eventModel?.viewportSummary || "视图未初始化")}</p>
      </div>
      <div class="drawer-card-grid">
        ${renderProjectionHealthMarkup(projection)}
        ${renderCurrentBeliefMarkup(projection)}
        <div class="info-card">
          <h4>${selectedCluster ? `事件详情 · ${escapeHtml(selectedCluster.timeLabel || "--")}` : "当前视图关键事件"}</h4>
          <p>${escapeHtml(selectedCluster?.summaryText || eventModel?.viewportSummary || "当前还没有关键事件摘要。")}</p>
          ${selectedCluster ? `<p>${escapeHtml(selectedCluster.priceText || "价格未知")}</p>` : ""}
          ${selectedCluster ? renderClusterItemsMarkup(selectedCluster) : renderEventPreviewMarkup(topVisibleClusters)}
        </div>
      </div>
    `
    : `<div class="empty-note">未加载图表。</div>`;

  if (els.manualRegionList) {
    els.manualRegionList.innerHTML = state.manualRegions.length
      ? state.manualRegions.map((item) => `<div class="info-card compact-card"><h4>${item.label}</h4><p>${item.started_at} → ${item.ended_at}</p><p>${item.price_low} - ${item.price_high}</p></div>`).join("")
      : `<div class="empty-note">无手工区域。</div>`;
  }

  els.drawerFocusPanel.innerHTML = snapshot?.focus_regions?.length
    ? snapshot.focus_regions.map((item) => `<div class="info-card"><h4>${item.label}</h4><p>${item.price_low} - ${item.price_high}</p></div>`).join("")
    : `<div class="empty-note">无焦点区域。</div>`;

  els.drawerStrategyPanel.innerHTML = snapshot?.strategy_candidates?.length
    ? snapshot.strategy_candidates.map((item) => `<div class="info-card"><h4>${item.title || item.strategy_id}</h4><p>${summarizeText(item.thesis || item.summary || "", 180)}</p></div>`).join("")
    : `<div class="empty-note">无策略匹配。</div>`;

  if (els.operatorEntryList) {
    els.operatorEntryList.innerHTML = state.operatorEntries.length
      ? state.operatorEntries.map((item) => `<div class="info-card compact-card"><h4>${item.side === "buy" ? "多头开仓" : "空头开仓"}</h4><p>${item.executed_at}</p><p>${item.entry_price}</p></div>`).join("")
      : `<div class="empty-note">无开仓记录。</div>`;
  }

  els.drawerRecapPanel.innerHTML = `
    <div class="recap-panel-stack">
      ${renderProjectionEpisodesMarkup(projection)}
      ${renderProjectionEvaluationsMarkup(projection)}
      ${renderProjectionTuningMarkup(projection)}
      ${renderRecapDrawerMarkup(state)}
    </div>
  `;

  renderGammaDrawer({ state, els });
}


export function bootReplayWorkbench({ renderChart, getRenderSnapshot, getBuildRequestPayload }) {
  const state = createWorkbenchState();
  const els = createWorkbenchElements(document);
  const { buildCacheKey, syncCacheKey, applyWindowPreset } = createCacheKeyHelpers({ els });
  const { ensureChartView, createDefaultChartView } = createChartViewHelpers({ state });
  const renderStatusStrip = renderStatusStripFactory(els);
  const planLifecycleEngine = createPlanLifecycleEngine({ state });
  const sessionMemoryEngine = createSessionMemoryEngine({ state, els, fetchJson });
  const MOBILE_AI_BREAKPOINT = 1000;
  const DESKTOP_SIDEBAR_MIN = 520;
  const DESKTOP_SIDEBAR_MAX = 820;
  let chartViewportPersistTimer = null;

  function collectLayerStateFromInputs() {
    return {
      largeOrders: !!els.layerLargeOrders?.checked,
      absorption: !!els.layerAbsorption?.checked,
      iceberg: !!els.layerIceberg?.checked,
      replenishment: !!els.layerReplenishment?.checked,
      events: !!els.layerEvents?.checked,
      focusRegions: !!els.layerFocusRegions?.checked,
      manualRegions: !!els.layerManualRegions?.checked,
      operatorEntries: !!els.layerOperatorEntries?.checked,
      aiAnnotations: !!els.layerAiAnnotations?.checked,
    };
  }

  function applyLayerStateToInputs() {
    const layerState = state.layerState || {};
    if (els.layerLargeOrders) els.layerLargeOrders.checked = !!layerState.largeOrders;
    if (els.layerAbsorption) els.layerAbsorption.checked = !!layerState.absorption;
    if (els.layerIceberg) els.layerIceberg.checked = !!layerState.iceberg;
    if (els.layerReplenishment) els.layerReplenishment.checked = !!layerState.replenishment;
    if (els.layerEvents) els.layerEvents.checked = layerState.events !== false;
    if (els.layerFocusRegions) els.layerFocusRegions.checked = layerState.focusRegions !== false;
    if (els.layerManualRegions) els.layerManualRegions.checked = layerState.manualRegions !== false;
    if (els.layerOperatorEntries) els.layerOperatorEntries.checked = layerState.operatorEntries !== false;
    if (els.layerAiAnnotations) els.layerAiAnnotations.checked = layerState.aiAnnotations !== false;
    state.layerState = collectLayerStateFromInputs();
  }

  function persistLayerState() {
    state.layerState = collectLayerStateFromInputs();
    persistWorkbenchState();
  }

  function persistWorkbenchState() {
    writeStorage("workbench", {
      activeAiThreadId: state.activeAiThreadId,
      drawerState: state.drawerState,
      topBar: state.topBar,
      pinnedPlanId: state.pinnedPlanId,
      annotationPreferences: state.annotationPreferences || {},
      layerState: state.layerState || collectLayerStateFromInputs(),
      symbolWorkspaceState: state.symbolWorkspaceState || {},
      eventStreamFilter: state.eventStreamFilter || "all",
      eventWorkbench: {
        schemaVersion: state.eventWorkbench?.schemaVersion || null,
        sessionId: state.eventWorkbench?.sessionId || null,
        symbol: state.eventWorkbench?.symbol || null,
        timeframe: state.eventWorkbench?.timeframe || null,
        sessionKey: state.eventWorkbench?.sessionKey || null,
        selectedEventId: state.eventWorkbench?.selectedEventId || null,
        pinnedEventIds: Array.isArray(state.eventWorkbench?.pinnedEventIds) ? state.eventWorkbench.pinnedEventIds : [],
      },
      eventOutcomeWorkbench: {
        sessionKey: state.eventOutcomeWorkbench?.sessionKey || null,
        focusedEventId: state.eventOutcomeWorkbench?.focusedEventId || null,
        lastLoadedAt: state.eventOutcomeWorkbench?.lastLoadedAt || null,
      },
      replyExtractionState: state.replyExtractionState || {
        filter: "all",
        showIgnored: false,
        pendingOnly: false,
        intensity: "balanced",
        autoExtractEnabled: true,
        collapsed: false,
        bySymbol: {},
      },
      chartViewportRegistry: state.chartViewportRegistry || {},
    });
  }

  function sameChartViewportRecord(left, right) {
    if (!left && !right) {
      return true;
    }
    if (!left || !right) {
      return false;
    }
    return left.startIndex === right.startIndex
      && left.endIndex === right.endIndex
      && left.totalCount === right.totalCount
      && left.rightPadding === right.rightPadding
      && left.followLatest === right.followLatest
      && left.yMin === right.yMin
      && left.yMax === right.yMax;
  }

  function schedulePersistChartViewportRegistry() {
    if (chartViewportPersistTimer) {
      window.clearTimeout(chartViewportPersistTimer);
    }
    chartViewportPersistTimer = window.setTimeout(() => {
      chartViewportPersistTimer = null;
      persistWorkbenchState();
    }, 140);
  }

  function rememberCurrentChartView(snapshot = state.snapshot, { persist = true } = {}) {
    if (!snapshot?.candles?.length || !state.chartView) {
      return null;
    }
    const chartViewportKey = buildChartViewportKey(snapshot);
    if (!chartViewportKey) {
      return null;
    }
    const lastVisibleBar = snapshot.candles[Math.min(snapshot.candles.length - 1, state.chartView.endIndex)] || null;
    const nextRecord = snapshotChartViewForRegistry(snapshot.candles.length, state.chartView, {
      lastVisibleEndedAt: lastVisibleBar?.ended_at || lastVisibleBar?.started_at || null,
    });
    if (!nextRecord) {
      return null;
    }
    state.followLatest = !!nextRecord.followLatest;
    const previousRecord = state.chartViewportRegistry?.[chartViewportKey] || null;
    if (!sameChartViewportRecord(previousRecord, nextRecord)) {
      state.chartViewportRegistry = {
        ...(state.chartViewportRegistry || {}),
        [chartViewportKey]: nextRecord,
      };
      if (persist) {
        schedulePersistChartViewportRegistry();
      }
    }
    state.lastChartViewportKey = chartViewportKey;
    return nextRecord;
  }

  function formatExactLocalDateTime(value) {
    if (!value) {
      return "--";
    }
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) {
      return "--";
    }
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function getSyncStatusState(value = state.topBar?.lastSyncedAt) {
    const exactLabel = formatExactLocalDateTime(value);
    if (exactLabel === "--") {
      return {
        label: "最近同步：未同步",
        variant: "warn",
        title: "尚未同步或缓存已重置。",
      };
    }
    const syncDate = new Date(value);
    const diffMs = Date.now() - syncDate.getTime();
    if (!Number.isFinite(diffMs)) {
      return {
        label: "最近同步：--",
        variant: "warn",
        title: "同步时间不可用。",
      };
    }
    const minuteMs = 60 * 1000;
    const hourMs = 60 * minuteMs;
    const dayMs = 24 * hourMs;
    if (diffMs < 2 * minuteMs) {
      return {
        label: "最近同步：刚刚",
        variant: "good",
        title: `最近同步：${exactLabel}`,
      };
    }
    if (diffMs < hourMs) {
      return {
        label: `最近同步：${Math.max(1, Math.round(diffMs / minuteMs))} 分钟前`,
        variant: "good",
        title: `最近同步：${exactLabel}`,
      };
    }
    if (diffMs < dayMs) {
      return {
        label: `最近同步：${Math.max(1, Math.round(diffMs / hourMs))} 小时前`,
        variant: "emphasis",
        title: `最近同步：${exactLabel}`,
      };
    }
    return {
      label: `最近同步：${Math.max(1, Math.round(diffMs / dayMs))} 天前`,
      variant: "warn",
      title: `最近同步：${exactLabel}`,
    };
  }

  function formatSyncLabel(value) {
    return getSyncStatusState(value).label;
  }

  function applyHeaderChipState(element, { label = "", variant = "", title = "" } = {}) {
    if (!element) {
      return;
    }
    element.className = variant ? `status-chip ${variant}` : "status-chip";
    element.textContent = label;
    element.title = title || label;
  }

  function getDataStatusState() {
    if (state.snapshotLoading || state.buildInFlight || state.enrichmentInFlight) {
      return {
        label: "数据状态：加载中",
        variant: "emphasis",
        title: "当前正在加载图表或刷新数据。",
      };
    }
    if (state.snapshot?.live_tail) {
      return {
        label: "数据状态：实时尾流",
        variant: "emphasis",
        title: "当前视图包含实时尾流更新。",
      };
    }
    if (state.snapshot) {
      return {
        label: "数据状态：历史快照",
        variant: "",
        title: "当前视图来自历史快照。",
      };
    }
    return {
      label: "数据状态：未加载",
      variant: "warn",
      title: "尚未加载图表数据。",
    };
  }

  function getIntegrityStatusState() {
    const integrity = state.integrity || state.snapshot?.integrity || state.buildResponse?.integrity || null;
    let label = "完整性：待评估";
    let variant = "";
    let title = "当前还没有完整性评估结果。";
    if (integrity?.status) {
      const gapCount = Number(integrity.gap_count || 0);
      const missingBarCount = Number(integrity.missing_bar_count || 0);
      label = gapCount || missingBarCount
        ? `完整性：${integrity.status} / 缺 ${missingBarCount} / gap ${gapCount}`
        : `完整性：${integrity.status}`;
      variant = integrity.status === "complete" && !gapCount && !missingBarCount
        ? "good"
        : (gapCount || missingBarCount ? "warn" : "emphasis");
      title = [
        `完整性状态：${integrity.status}`,
        `缺失K线：${missingBarCount}`,
        `缺口数：${gapCount}`,
      ].join("\n");
    }
    return { label, variant, title };
  }

  function getCacheStatusState() {
    const buildAction = state.buildResponse?.action || null;
    const acquisitionMode = state.snapshot?.acquisition_mode || state.buildResponse?.summary?.acquisition_mode || null;
    let label = "缓存：待构建";
    let variant = "";
    let title = "当前还没有可复用的快照状态。";
    if (buildAction === "cache_hit" || acquisitionMode === "cache_reuse") {
      label = "缓存：命中 / 复用";
      variant = "good";
      title = "本次视图直接复用了已有缓存。";
    } else if (buildAction === "built_from_local_history" || acquisitionMode === "local_history") {
      label = "来源：本地连续流";
      variant = "emphasis";
      title = "本次视图来自本地连续历史数据。";
    } else if (buildAction === "built_from_atas_history" || acquisitionMode === "atas_fetch") {
      label = "来源：ATAS 历史";
      variant = "emphasis";
      title = "本次视图通过 ATAS 历史数据构建。";
    } else if (buildAction === "atas_fetch_required") {
      label = "缓存：未命中";
      variant = "warn";
      title = "当前缓存不可复用，需要重新拉取历史数据。";
    }
    return { label, variant, title };
  }

  function getBackfillStatusState() {
    const integrity = state.integrity || state.snapshot?.integrity || state.buildResponse?.integrity || null;
    let label = "补数：无需";
    let variant = "good";
    let title = "当前不需要额外补齐历史数据。";
    if (state.transportProgress?.label) {
      const progressPercent = Number(state.transportProgress.progress_percent || 0);
      const progressStage = String(state.transportProgress.stage || "").toLowerCase();
      if (progressStage === "complete") {
        label = "补数：已完成";
        variant = "good";
      } else if (["failed", "expired"].includes(progressStage)) {
        label = "补数：未完成";
        variant = "warn";
      } else if (
        progressStage === "idle"
        && !state.transportProgress.active
        && !state.transportProgress.request
      ) {
        label = "补数：无活动任务";
        variant = (Number(integrity?.gap_count || 0) > 0 || Number(integrity?.missing_bar_count || 0) > 0)
          ? "warn"
          : "good";
      } else {
        label = `补数：${progressPercent}%`;
        variant = state.transportProgress.active ? "emphasis" : "warn";
      }
      title = [state.transportProgress.label, state.transportProgress.detail].filter(Boolean).join("\n");
      return { label, variant, title };
    }
    if (state.pendingBackfill?.status) {
      label = `补数：${state.pendingBackfill.status}`;
      variant = ["pending", "dispatched"].includes(String(state.pendingBackfill.status)) ? "emphasis" : "good";
      title = `最近补数任务状态：${state.pendingBackfill.status}`;
    } else if (state.historyBackfillLoading) {
      label = "补数：后台补齐中";
      variant = "emphasis";
      title = "后台正在补齐缺失历史数据。";
    } else if (integrity && (Number(integrity.gap_count || 0) > 0 || Number(integrity.missing_bar_count || 0) > 0)) {
      label = "补数：仍有缺口";
      variant = "warn";
      title = "当前仍存在缺口，建议继续补数。";
    } else if (state.fullHistoryLoaded) {
      label = "补数：历史已补齐";
      variant = "good";
      title = "历史数据已补齐完成。";
    }
    return { label, variant, title };
  }

  function updateHeaderMoreMenuState() {
    const isOpen = !!els.headerMoreMenu && !els.headerMoreMenu.hidden;
    const hasCacheKey = !!String(els.cacheKey?.value || "").trim();
    const cacheActionBusy = state.buildInFlight || state.snapshotLoading || state.enrichmentInFlight;
    const hasRepairWindow = !!String(els.windowStart?.value || "").trim() && !!String(els.windowEnd?.value || "").trim();
    const repairChartInstanceId = String(
      els.chartInstanceId?.value || state.snapshot?.source?.chart_instance_id || state.pendingBackfill?.chart_instance_id || "",
    ).trim();
    if (els.headerMoreButton) {
      els.headerMoreButton.classList.toggle("is-active", isOpen);
      els.headerMoreButton.textContent = isOpen ? "更多▲" : "更多▼";
      els.headerMoreButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
    if (els.headerMoreMenuStatus) {
      const dataState = getDataStatusState();
      const timeframe = timeframeLabel(state.topBar?.timeframe || els.displayTimeframe?.value || "1m");
      els.headerMoreMenuStatus.textContent = `${state.topBar?.symbol || "NQ"} / ${timeframe} · ${dataState.label.replace(/^数据状态：/, "")}`;
      els.headerMoreMenuStatus.title = dataState.title || dataState.label;
    }
    if (els.headerMoreMenuSync) {
      const syncState = getSyncStatusState();
      const integrityState = getIntegrityStatusState();
      els.headerMoreMenuSync.textContent = `${syncState.label} · ${integrityState.label.replace(/^完整性：/, "")}`;
      els.headerMoreMenuSync.title = [
        syncState.title || syncState.label,
        integrityState.title || integrityState.label,
        getCacheStatusState().title || getCacheStatusState().label,
        getBackfillStatusState().title || getBackfillStatusState().label,
      ].join("\n");
    }
    if (els.lookupCacheButton) {
      els.lookupCacheButton.disabled = cacheActionBusy || !hasCacheKey;
      els.lookupCacheButton.title = !hasCacheKey
        ? "当前参数还没有可查询的缓存键。"
        : (cacheActionBusy ? "当前正在刷新或加载数据，请稍后再试。" : "查询当前参数对应的缓存记录，并打开缓存信息。");
    }
    if (els.invalidateCacheButton) {
      els.invalidateCacheButton.disabled = cacheActionBusy || !hasCacheKey;
      els.invalidateCacheButton.title = !hasCacheKey
        ? "当前参数还没有可重置的缓存键。"
        : (cacheActionBusy ? "当前正在刷新或加载数据，请稍后再试。" : "作废当前参数对应的缓存记录。");
    }
    if (els.repairChartButton) {
      els.repairChartButton.disabled = cacheActionBusy || !hasCacheKey || !hasRepairWindow;
      if (!hasCacheKey) {
        els.repairChartButton.title = "当前参数还没有可修复的缓存键。";
      } else if (!hasRepairWindow) {
        els.repairChartButton.title = "修复当前图表前需要完整的开始和结束时间。";
      } else if (cacheActionBusy) {
        els.repairChartButton.title = "当前正在刷新或加载数据，请稍后再试。";
      } else if (repairChartInstanceId) {
        els.repairChartButton.title = `清空当前窗口并要求 ATAS 图表 ${repairChartInstanceId} 重新回传已加载 K 线。`;
      } else {
        els.repairChartButton.title = "清空当前窗口并重新发起修复，但当前未绑定 chart_instance_id，将由同品种匹配图表领取任务。";
      }
    }
    if (els.refreshCacheViewerButton) {
      els.refreshCacheViewerButton.disabled = cacheActionBusy || !hasCacheKey;
      els.refreshCacheViewerButton.title = !hasCacheKey
        ? "当前参数还没有可刷新的缓存键。"
        : (cacheActionBusy ? "当前正在刷新或加载数据，请稍后再试。" : "重新查询当前缓存状态。");
    }
  }

  function setHeaderMoreMenuOpen(nextOpen = false) {
    if (!els.headerMoreMenu) {
      return;
    }
    els.headerMoreMenu.hidden = !nextOpen;
    updateHeaderMoreMenuState();
  }

  function closeHeaderMoreMenu() {
    setHeaderMoreMenuOpen(false);
  }

  function toggleHeaderMoreMenu() {
    setHeaderMoreMenuOpen(!!els.headerMoreMenu?.hidden);
  }

  function isCacheViewerOpen() {
    return !!els.cacheViewerModal && !els.cacheViewerModal.classList.contains("is-hidden");
  }

  function closeCacheViewer() {
    if (!els.cacheViewerModal) {
      return;
    }
    els.cacheViewerModal.classList.add("is-hidden");
  }

  function updateCacheViewer() {
    if (!els.cacheViewerKey || !els.cacheViewerIngestionId || !els.cacheViewerSnapshotStatus || !els.cacheViewerDetailsJson) {
      return;
    }
    const dataState = getDataStatusState();
    const cacheState = getCacheStatusState();
    const integrityState = getIntegrityStatusState();
    const backfillState = getBackfillStatusState();
    const syncState = getSyncStatusState();
    applyHeaderChipState(els.cacheViewerDataChip, dataState);
    applyHeaderChipState(els.cacheViewerCacheChip, cacheState);
    applyHeaderChipState(els.cacheViewerIntegrityChip, integrityState);
    applyHeaderChipState(els.cacheViewerBackfillChip, backfillState);
    applyHeaderChipState(els.cacheViewerSyncChip, syncState);
    els.cacheViewerKey.textContent = els.cacheKey?.value || "-";
    els.cacheViewerIngestionId.textContent = state.currentReplayIngestionId || "-";
    if (state.snapshotLoading || state.buildInFlight || state.enrichmentInFlight) {
      els.cacheViewerSnapshotStatus.textContent = "加载中";
      els.cacheViewerSnapshotStatus.style.color = "var(--blue)";
    } else if (state.snapshot) {
      const candleCount = Array.isArray(state.snapshot.candles) ? state.snapshot.candles.length : 0;
      els.cacheViewerSnapshotStatus.textContent = `已加载 · ${candleCount} 根K线`;
      els.cacheViewerSnapshotStatus.style.color = "var(--green)";
    } else if (state.buildResponse?.atas_fetch_request?.manual_reimport_required) {
      els.cacheViewerSnapshotStatus.textContent = "已作废 · 需要重新构建";
      els.cacheViewerSnapshotStatus.style.color = "var(--orange)";
    } else {
      els.cacheViewerSnapshotStatus.textContent = "未加载";
      els.cacheViewerSnapshotStatus.style.color = "var(--text-soft)";
    }
    const details = {
      instrument_symbol: state.snapshot?.instrument_symbol || state.topBar?.symbol || "-",
      display_timeframe: state.snapshot?.display_timeframe || state.topBar?.timeframe || "-",
      quick_range: state.topBar?.quickRange || els.quickRangeSelect?.value || null,
      window_start: state.snapshot?.window_start || els.windowStart?.value || "-",
      window_end: state.snapshot?.window_end || els.windowEnd?.value || "-",
      candle_count: Array.isArray(state.snapshot?.candles) ? state.snapshot.candles.length : 0,
      event_annotation_count: Array.isArray(state.snapshot?.event_annotations) ? state.snapshot.event_annotations.length : 0,
      focus_region_count: Array.isArray(state.snapshot?.focus_regions) ? state.snapshot.focus_regions.length : 0,
      strategy_candidate_count: Array.isArray(state.snapshot?.strategy_candidates) ? state.snapshot.strategy_candidates.length : 0,
      live_tail: !!state.snapshot?.live_tail,
      follow_latest: !!state.followLatest,
      cache_key: els.cacheKey?.value || null,
      replay_ingestion_id: state.currentReplayIngestionId || null,
      replay_snapshot_id: state.buildResponse?.replay_snapshot_id || state.buildResponse?.cache_record?.replay_snapshot_id || null,
      build_action: state.buildResponse?.action || null,
      acquisition_mode: state.snapshot?.acquisition_mode || state.buildResponse?.summary?.acquisition_mode || null,
      verification_state: state.buildResponse?.cache_record?.verification_state || null,
      cache_policy: state.buildResponse?.cache_record?.cache_policy || null,
      integrity: state.integrity || state.snapshot?.integrity || state.buildResponse?.integrity || null,
      pending_backfill: state.pendingBackfill || null,
      transport_progress: state.transportProgress || null,
      last_synced_at: state.topBar?.lastSyncedAt || null,
      last_chart_update_type: state.lastChartUpdateType || null,
      cache_record: state.buildResponse?.cache_record || null,
    };
    if (els.cacheViewerDetails) {
      els.cacheViewerDetails.style.display = "block";
    }
    els.cacheViewerDetailsJson.textContent = JSON.stringify(details, null, 2);
  }

  function openCacheViewer() {
    if (!els.cacheViewerModal) {
      return;
    }
    updateCacheViewer();
    els.cacheViewerModal.classList.remove("is-hidden");
    closeHeaderMoreMenu();
  }

  function markWorkbenchSynced(timestamp = new Date().toISOString()) {
    state.topBar.lastSyncedAt = timestamp;
    updateHeaderStatus();
  }

  async function lookupCacheFromHeader({ button = els.lookupCacheButton, openViewerOnSuccess = true } = {}) {
    const result = await runButtonAction(button, async () => {
      const lookupResult = await actions.handleLookup();
      if (!lookupResult) {
        return null;
      }
      markWorkbenchSynced();
      return lookupResult;
    }, { silentError: true });
    if (!result) {
      return null;
    }
    if (openViewerOnSuccess) {
      openCacheViewer();
    } else if (isCacheViewerOpen()) {
      updateCacheViewer();
    }
    return result;
  }

  async function invalidateCacheFromHeader({ button = els.invalidateCacheButton } = {}) {
    const result = await runButtonAction(button, async () => {
      const invalidateResult = await actions.handleInvalidate();
      if (!invalidateResult) {
        return null;
      }
      markWorkbenchSynced();
      return invalidateResult;
    }, { silentError: true });
    if (!result) {
      return null;
    }
    if (isCacheViewerOpen()) {
      updateCacheViewer();
    }
    return result;
  }

  function exportCurrentSettings() {
    const payload = {
      exportedAt: new Date().toISOString(),
      workspaceContext: {
        instrumentSymbol: els.instrumentSymbol?.value?.trim() || state.topBar?.symbol || "NQ",
        displayTimeframe: els.displayTimeframe?.value || state.topBar?.timeframe || "1m",
        quickRange: els.quickRangeSelect?.value || state.topBar?.quickRange || "7d",
        windowStart: els.windowStart?.value || null,
        windowEnd: els.windowEnd?.value || null,
        cacheKey: els.cacheKey?.value || null,
        replayIngestionId: state.currentReplayIngestionId || null,
        followLatest: !!state.followLatest,
      },
      topBar: state.topBar,
      layout: state.layout,
      drawerState: state.drawerState,
      layerState: state.layerState,
      annotationFilters: state.annotationFilters,
      annotationPreferences: state.annotationPreferences || {},
      eventStreamFilter: state.eventStreamFilter || "all",
      replyExtractionState: state.replyExtractionState || null,
      activeAiThreadId: state.activeAiThreadId,
      pinnedPlanId: state.pinnedPlanId,
      symbolWorkspaceState: state.symbolWorkspaceState || {},
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const timestamp = new Date().toISOString().replace(/[:]/g, "-").replace(/\..+$/, "");
    link.href = url;
    link.download = `replay-workbench-settings-${timestamp}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 300);
  }


  function jumpToMessage(messageId) {
    if (!messageId) {
      return false;
    }
    scrollChatToBottom({ behavior: "auto", markRead: true, persist: false });
    const node = els.aiChatThread.querySelector(`[data-message-id="${messageId}"]`);
    if (!node) {
      return false;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    const session = getActiveThread();
    session.autoFollowChat = false;
    session.hasUnreadChatBelow = false;
    session.scrollOffset = els.aiChatThread?.scrollTop || 0;
    node.classList.add("source-flash");
    window.setTimeout(() => node.classList.remove("source-flash"), 2200);
    return true;
  }

  function jumpToMessageWhenReady(messageId, { retries = 12, delay = 80 } = {}) {
    if (!messageId) {
      return;
    }
    let attempts = 0;
    const tryJump = () => {
      if (jumpToMessage(messageId)) {
        return;
      }
      attempts += 1;
      if (attempts >= retries) {
        return;
      }
      window.setTimeout(tryJump, delay);
    };
    tryJump();
  }

  function jumpToSecondaryMessage(messageId) {
    if (!messageId || !els.eventScribeThread) {
      return false;
    }
    const node = els.eventScribeThread.querySelector(`[data-secondary-message-id="${messageId}"]`);
    if (!node) {
      return false;
    }
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("source-flash");
    window.setTimeout(() => node.classList.remove("source-flash"), 2200);
    return true;
  }

  function jumpToSecondaryMessageWhenReady(messageId, { retries = 12, delay = 80 } = {}) {
    if (!messageId) {
      return;
    }
    let attempts = 0;
    const tryJump = () => {
      if (jumpToSecondaryMessage(messageId)) {
        return;
      }
      attempts += 1;
      if (attempts >= retries) {
        return;
      }
      window.setTimeout(tryJump, delay);
    };
    tryJump();
  }

  function resolveAnnotationScope(annotationId, mode = "only") {
    const annotations = Array.isArray(state.aiAnnotations) ? state.aiAnnotations : [];
    const target = annotations.find((item) => item.id === annotationId);
    if (!target) {
      return null;
    }
    const scopedAnnotationIds = mode === "source" && target.plan_id
      ? annotations.filter((item) => item.plan_id === target.plan_id).map((item) => item.id)
      : mode === "reply" && target.message_id
        ? annotations
          .filter((item) => item.message_id === target.message_id && item.session_id === target.session_id)
          .map((item) => item.id)
        : [annotationId];
    return {
      target,
      filters: {
        onlyCurrentSession: false,
        sessionIds: target.session_id ? [target.session_id] : [],
        messageIds: target.message_id ? [target.message_id] : [],
        annotationIds: scopedAnnotationIds,
        selectedOnly: false,
      },
    };
  }

  function applyAnnotationScope(annotationId, {
    mode = "only",
    activateSession = false,
    jumpToSource = false,
    render = true,
  } = {}) {
    const scope = resolveAnnotationScope(annotationId, mode);
    if (!scope) {
      return null;
    }
    const { target, filters } = scope;
    state.selectedAnnotationId = annotationId;
    state.annotationFilters.onlyCurrentSession = filters.onlyCurrentSession;
    state.annotationFilters.sessionIds = filters.sessionIds;
    state.annotationFilters.messageIds = filters.messageIds;
    state.annotationFilters.annotationIds = filters.annotationIds;
    state.annotationFilters.selectedOnly = filters.selectedOnly;
    writeStorage("annotationFilters", state.annotationFilters);
    if (activateSession && target.session_id) {
      const session = state.aiThreads.find((item) => item.id === target.session_id);
      setActiveThread(target.session_id, session?.title || "会话", buildThreadActivationOverrides(session));
    }
    if (render) {
      renderSnapshot();
    }
    if (jumpToSource && target.message_id) {
      const targetSession = target.session_id
        ? state.aiThreads.find((item) => item.id === target.session_id)
        : null;
      if (targetSession && getWorkspaceRole(targetSession) === "scribe") {
        rememberSymbolWorkspaceSession(targetSession);
        renderEventScribePanel();
        jumpToSecondaryMessageWhenReady(target.message_id);
      } else {
        jumpToMessageWhenReady(target.message_id);
      }
    }
    return scope;
  }

  let annotationPopoverController = null;

  function getAnnotationById(annotationId) {
    return (state.aiAnnotations || []).find((item) => item.id === annotationId) || null;
  }

  function writeAnnotationFilters() {
    writeStorage("annotationFilters", state.annotationFilters);
  }

  function updateAnnotationPreferenceState(target, patch = {}) {
    if (!target) {
      return;
    }
    state.annotationPreferences = updateAnnotationPreference(state.annotationPreferences || {}, target, patch);
    if (Object.prototype.hasOwnProperty.call(patch, "visible")) {
      target.visible = patch.visible !== false;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "pinned")) {
      target.pinned = !!patch.pinned;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "deleted")) {
      target.deleted = !!patch.deleted;
    }
  }

  function pruneAnnotationFilterIds(annotationId) {
    if (!Array.isArray(state.annotationFilters.annotationIds)) {
      state.annotationFilters.annotationIds = [];
      return;
    }
    state.annotationFilters.annotationIds = state.annotationFilters.annotationIds.filter((item) => item !== annotationId);
    if (state.annotationFilters.selectedOnly && !state.annotationFilters.annotationIds.length) {
      state.annotationFilters.selectedOnly = false;
    }
  }

  function refreshAnnotationPopover(annotationId) {
    if (state.annotationPopoverTargetId !== annotationId) {
      return;
    }
    const target = getAnnotationById(annotationId);
    if (!target || isAnnotationDeleted(target)) {
      annotationPopoverController?.hideAnnotationPopover();
      return;
    }
    annotationPopoverController?.showAnnotationPopover(annotationId);
  }

  function ensureAnnotationVisible(target) {
    if (!target || target.visible !== false) {
      return;
    }
    updateAnnotationPreferenceState(target, { visible: true });
  }

  function buildThreadActivationOverrides(session = null) {
    if (!session) {
      return {};
    }
    return {
      symbol: session.symbol || session.contractId || session.memory?.symbol || state.topBar.symbol,
      contractId: session.contractId || session.symbol || session.memory?.symbol || state.topBar.symbol,
      timeframe: session.timeframe || session.memory?.timeframe || state.topBar.timeframe,
      windowRange: session.windowRange || session.memory?.window_range || state.topBar.quickRange,
    };
  }

  function toFocusTimestamp(value) {
    if (!value) {
      return null;
    }
    const timestamp = new Date(value).getTime();
    return Number.isFinite(timestamp) ? timestamp : null;
  }

  function toFocusNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function findCandleIndexForTime(candles, targetTime, { mode = "nearest" } = {}) {
    if (!Array.isArray(candles) || !candles.length || !Number.isFinite(targetTime)) {
      return 0;
    }
    let nearestIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < candles.length; index += 1) {
      const candle = candles[index];
      const startedAt = toFocusTimestamp(candle?.started_at);
      const endedAt = toFocusTimestamp(candle?.ended_at || candle?.started_at);
      const anchorTime = startedAt ?? endedAt;
      if (anchorTime == null) {
        continue;
      }
      const distance = Math.abs(anchorTime - targetTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
      if (mode === "start" && endedAt != null && endedAt >= targetTime) {
        return index;
      }
      if (mode === "end" && startedAt != null && startedAt > targetTime) {
        return Math.max(0, index - 1);
      }
    }
    return nearestIndex;
  }

  function buildVisiblePriceEnvelope(visibleCandles = [], focusPrices = []) {
    const candleValues = visibleCandles.flatMap((candle) => [
      toFocusNumber(candle?.low),
      toFocusNumber(candle?.high),
    ]).filter((item) => item != null);
    let annotationValues = focusPrices.map((item) => toFocusNumber(item)).filter((item) => item != null);
    if (candleValues.length && annotationValues.length) {
      const candleMin = Math.min(...candleValues);
      const candleMax = Math.max(...candleValues);
      const candleSpan = Math.max(candleMax - candleMin, Math.max(Math.abs(candleMax) * 0.002, 2));
      const maxDistance = Math.max(candleSpan * 4, Math.max(Math.abs(candleMax) * 0.002, 8));
      const boundedAnnotationValues = annotationValues.filter((price) => (
        price >= candleMin - maxDistance && price <= candleMax + maxDistance
      ));
      if (boundedAnnotationValues.length !== annotationValues.length) {
        console.warn(
          `buildVisiblePriceEnvelope: dropped ${annotationValues.length - boundedAnnotationValues.length} outlier annotation prices outside visible candle range`,
        );
      }
      annotationValues = boundedAnnotationValues;
    }
    const values = [
      ...annotationValues,
      ...candleValues,
    ];
    if (!values.length) {
      return { min: null, max: null };
    }
    const minPrice = Math.min(...values);
    const maxPrice = Math.max(...values);
    const span = maxPrice - minPrice;
    const padding = Math.max(span * 0.1, span === 0 ? Math.max(Math.abs(maxPrice) * 0.002, 1) : 1);
    return {
      min: minPrice - padding,
      max: maxPrice + padding,
    };
  }

  function collectAnnotationFocusMetrics(annotations = []) {
    const times = [];
    const prices = [];
    annotations.forEach((item) => {
      if (!item) {
        return;
      }
      [
        item.start_time,
        item.end_time,
        item.expires_at,
        item.created_at,
        item.updated_at,
      ].forEach((value) => {
        const timestamp = toFocusTimestamp(value);
        if (timestamp != null) {
          times.push(timestamp);
        }
      });
      [
        item.entry_price,
        item.stop_price,
        item.target_price,
        item.price_low,
        item.price_high,
      ].forEach((value) => {
        const numeric = toFocusNumber(value);
        if (numeric != null) {
          prices.push(numeric);
        }
      });
      if (Array.isArray(item.path_points)) {
        item.path_points.forEach((point) => {
          const pointTimestamp = toFocusTimestamp(point?.time || point?.started_at || point?.ended_at);
          if (pointTimestamp != null) {
            times.push(pointTimestamp);
          }
          const pointPrice = toFocusNumber(point?.price);
          if (pointPrice != null) {
            prices.push(pointPrice);
          }
        });
      }
    });
    return {
      startTime: times.length ? Math.min(...times) : null,
      endTime: times.length ? Math.max(...times) : null,
      prices,
    };
  }

  function syncLiveChartLogicalRange(view, reason = "同步图表视窗") {
    if (!view) {
      return;
    }
    const timeScale = window._lwChartState?.chartInstance?.timeScale?.();
    if (!timeScale?.setVisibleLogicalRange) {
      return;
    }
    try {
      timeScale.setVisibleLogicalRange({
        from: view.startIndex,
        to: view.endIndex,
      });
    } catch (error) {
      console.warn(`${reason}失败:`, error);
    }
  }

  function focusAnnotationsOnChart(annotations = [], { minimumSpan = 36, maximumSpan = 140 } = {}) {
    const candles = state.snapshot?.candles || [];
    if (!annotations.length || !candles.length) {
      return false;
    }
    const metrics = collectAnnotationFocusMetrics(annotations);
    const defaultStartTime = toFocusTimestamp(state.snapshot?.window_start) ?? toFocusTimestamp(candles[0]?.started_at);
    const defaultEndTime = toFocusTimestamp(state.snapshot?.window_end)
      ?? toFocusTimestamp(candles[candles.length - 1]?.ended_at || candles[candles.length - 1]?.started_at);
    const startTime = metrics.startTime ?? defaultStartTime;
    const endTime = metrics.endTime ?? metrics.startTime ?? defaultEndTime ?? startTime;
    const focusStartIndex = findCandleIndexForTime(candles, startTime, { mode: "start" });
    const focusEndIndex = Math.max(focusStartIndex, findCandleIndexForTime(candles, endTime, { mode: "end" }));
    const focusSpan = Math.max(1, focusEndIndex - focusStartIndex + 1);
    const currentSpan = state.chartView
      ? Math.max(1, state.chartView.endIndex - state.chartView.startIndex + 1)
      : 0;
    const maxSpan = Math.max(minimumSpan, Math.min(maximumSpan, candles.length));
    const baselineSpan = currentSpan ? Math.min(currentSpan, maxSpan) : minimumSpan;
    const paddingBars = Math.max(6, Math.ceil(focusSpan * 0.75));
    const targetSpan = Math.max(
      minimumSpan,
      Math.min(maxSpan, Math.max(focusSpan + (paddingBars * 2), baselineSpan)),
    );
    const centerIndex = Math.round((focusStartIndex + focusEndIndex) / 2);
    let startIndex = centerIndex - Math.floor(targetSpan / 2);
    let endIndex = startIndex + targetSpan - 1;
    if (startIndex < 0) {
      startIndex = 0;
      endIndex = targetSpan - 1;
    }
    if (endIndex >= candles.length) {
      endIndex = candles.length - 1;
      startIndex = Math.max(0, endIndex - targetSpan + 1);
    }
    const visibleCandles = candles.slice(startIndex, endIndex + 1);
    const envelope = buildVisiblePriceEnvelope(visibleCandles, metrics.prices);
    const shouldResetPriceRange = envelope.min != null && (
      metrics.prices.length > 0
      || state.chartView?.yMin == null
      || state.chartView?.yMax == null
      || state.chartView.yMin > envelope.min
      || state.chartView.yMax < envelope.max
    );
    const nextView = clampChartView(candles.length, startIndex, endIndex, {
      ...state.chartView,
      yMin: shouldResetPriceRange ? envelope.min : state.chartView?.yMin ?? null,
      yMax: shouldResetPriceRange ? envelope.max : state.chartView?.yMax ?? null,
    });
    state.chartView = nextView;
    syncLiveChartLogicalRange(nextView, "标记定位时同步图表视窗");
    return true;
  }

  function handleAnnotationObjectAction(action, annotationId) {
    const target = getAnnotationById(annotationId);
    if (!target || isAnnotationDeleted(target)) {
      if (action === "detail") {
        annotationPopoverController?.hideAnnotationPopover();
      }
      return;
    }
    if (action === "detail") {
      state.selectedAnnotationId = annotationId;
      annotationPopoverController?.showAnnotationPopover(annotationId);
      renderSnapshot();
      return;
    }
    if (action === "locate") {
      ensureAnnotationVisible(target);
      annotationPopoverController?.hideAnnotationPopover();
      persistWorkbenchState();
      applyAnnotationScope(annotationId, {
        mode: "only",
        activateSession: true,
        jumpToSource: false,
        render: false,
      });
      focusAnnotationsOnChart([target], { minimumSpan: 32, maximumSpan: 120 });
      renderSnapshot();
      return;
    }
    if (action === "only") {
      ensureAnnotationVisible(target);
      annotationPopoverController?.hideAnnotationPopover();
      persistWorkbenchState();
      applyAnnotationScope(annotationId, {
        mode: "only",
        activateSession: false,
        jumpToSource: false,
        render: true,
      });
      return;
    }
    if (action === "source") {
      annotationPopoverController?.hideAnnotationPopover();
      applyAnnotationScope(annotationId, {
        mode: "reply",
        activateSession: true,
        jumpToSource: true,
        render: true,
      });
      return;
    }
    if (action === "pin") {
      updateAnnotationPreferenceState(target, { pinned: !target.pinned });
      persistWorkbenchState();
      refreshAnnotationPopover(annotationId);
      renderSnapshot();
      return;
    }
    if (action === "toggle") {
      updateAnnotationPreferenceState(target, { visible: target.visible === false });
      persistWorkbenchState();
      refreshAnnotationPopover(annotationId);
      renderSnapshot();
      return;
    }
    if (action === "delete") {
      updateAnnotationPreferenceState(target, {
        deleted: true,
        pinned: false,
        visible: false,
      });
      pruneAnnotationFilterIds(annotationId);
      if (state.selectedAnnotationId === annotationId) {
        state.selectedAnnotationId = null;
      }
      annotationPopoverController?.hideAnnotationPopover();
      writeAnnotationFilters();
      persistWorkbenchState();
      renderSnapshot();
    }
  }

  function getReplyAnnotations({ messageId, sessionId = null, planId = null } = {}) {
    return (state.aiAnnotations || []).filter((item) => {
      if (isAnnotationDeleted(item)) return false;
      if (sessionId && item.session_id !== sessionId) return false;
      if (messageId && item.message_id === messageId) return true;
      if (planId && item.plan_id === planId) return true;
      return false;
    });
  }

  function syncMountedRepliesToServer(session, { messageId = null, mountedToChart = null, mountMode = "append", mountedObjectIds = [] } = {}) {
    if (!fetchJson || !session?.id) {
      return Promise.resolve();
    }
    return (async () => {
      try {
        await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mounted_reply_ids: Array.isArray(session.mountedReplyIds) ? session.mountedReplyIds : [],
          }),
        });
      } catch (error) {
        console.warn("同步 mounted replies 失败:", error);
      }
      if (!messageId || mountedToChart == null) {
        return;
      }
      try {
        await fetchJson(`/api/v1/workbench/chat/messages/${encodeURIComponent(messageId)}/mount`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mounted_to_chart: !!mountedToChart,
            mount_mode: mountMode,
            mounted_object_ids: Array.isArray(mountedObjectIds) ? mountedObjectIds : [],
          }),
        });
      } catch (error) {
        console.warn("同步回复挂载状态失败:", error);
      }
    })();
  }

  function syncPromptBlocksToServer(session, { selectedPromptBlockIds = null, pinnedContextBlockIds = null, includeMemorySummary = null, includeRecentMessages = null } = {}) {
    if (!fetchJson || !session?.id) {
      return Promise.resolve();
    }
    return fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_prompt_block_ids: Array.isArray(selectedPromptBlockIds) ? selectedPromptBlockIds : (Array.isArray(session.selectedPromptBlockIds) ? session.selectedPromptBlockIds : []),
        pinned_context_block_ids: Array.isArray(pinnedContextBlockIds) ? pinnedContextBlockIds : (Array.isArray(session.pinnedContextBlockIds) ? session.pinnedContextBlockIds : []),
        include_memory_summary: includeMemorySummary ?? !!session.includeMemorySummary,
        include_recent_messages: includeRecentMessages ?? !!session.includeRecentMessages,
      }),
    }).catch((error) => {
      console.warn("同步 prompt blocks 失败:", error);
    });
  }

  function mountReplyObjects(messageId, mode = "show", { sessionId = null, planId = null } = {}) {
    if (!messageId) {
      return [];
    }
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (!targetSession) {
      return [];
    }
    const related = getReplyAnnotations({ messageId, sessionId: targetSession.id, planId });
    const mountedObjectIds = related.map((item) => item.id);
    const mountedReplyIds = Array.isArray(targetSession.mountedReplyIds) ? targetSession.mountedReplyIds : [];
    if (mode === "replace") {
      targetSession.mountedReplyIds = [messageId];
    } else if (mode === "show") {
      targetSession.mountedReplyIds = mountedReplyIds.includes(messageId)
        ? mountedReplyIds
        : [...mountedReplyIds, messageId];
    }
    targetSession.messages = (targetSession.messages || []).map((message) => {
      if (message.message_id === messageId) {
        return {
          ...message,
          mountedToChart: true,
          mountedObjectIds,
        };
      }
      if (mode === "replace") {
        return { ...message, mountedToChart: false, mountedObjectIds: [] };
      }
      return message;
    });
    const mountMode = mode === "replace" ? "replace" : mode === "focus" ? "focus_only" : "append";
    void syncMountedRepliesToServer(targetSession, {
      messageId,
      mountedToChart: true,
      mountMode,
      mountedObjectIds,
    });
    queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    persistSessions();
    return mountedObjectIds;
  }

  function unmountReplyObjects(messageId, { sessionId = null } = {}) {
    if (!messageId) {
      return;
    }
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (!targetSession) {
      return;
    }
    targetSession.mountedReplyIds = (targetSession.mountedReplyIds || []).filter((id) => id !== messageId);
    targetSession.messages = (targetSession.messages || []).map((message) => message.message_id === messageId
      ? { ...message, mountedToChart: false, mountedObjectIds: [] }
      : message);
    void syncMountedRepliesToServer(targetSession, {
      messageId,
      mountedToChart: false,
      mountMode: "append",
      mountedObjectIds: [],
    });
    queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    persistSessions();
  }

  function focusReplyObjects(messageId, { sessionId = null, planId = null, mode = "focus" } = {}) {
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    const related = getReplyAnnotations({ messageId, sessionId: targetSession?.id, planId });
    if (!related.length) {
      return [];
    }
    state.selectedAnnotationId = related[0].id;
    state.annotationFilters.onlyCurrentSession = false;
    state.annotationFilters.sessionIds = targetSession ? [targetSession.id] : [];
    state.annotationFilters.messageIds = messageId ? [messageId] : [];
    state.annotationFilters.annotationIds = mode === "focus" ? related.map((item) => item.id) : [];
    writeStorage("annotationFilters", state.annotationFilters);
    if (targetSession) {
      void syncMountedRepliesToServer(targetSession, {
        messageId,
        mountedToChart: true,
        mountMode: mode === "focus" ? "focus_only" : "append",
        mountedObjectIds: related.map((item) => item.id),
      });
      queueSessionMemoryRefresh([targetSession.id], { forceServer: true, delay: 120 });
    }
    return related;
  }

  function focusPlanOnChart({ action, planId, messageId, sessionId }) {
    const targetSession = state.aiThreads.find((item) => item.id === (sessionId || state.activeAiThreadId));
    if (targetSession) {
      setActiveThread(targetSession.id, targetSession.title, buildThreadActivationOverrides(targetSession));
    }
    const related = getReplyAnnotations({ messageId, sessionId: targetSession?.id || sessionId, planId });
    if (action === "unmount") {
      unmountReplyObjects(messageId, { sessionId: targetSession?.id || sessionId });
      if (messageId) {
        state.annotationFilters.annotationIds = (state.annotationFilters.annotationIds || []).filter((id) => {
          const annotation = state.aiAnnotations.find((item) => item.id === id);
          return annotation?.message_id !== messageId;
        });
      }
      writeStorage("annotationFilters", state.annotationFilters);
      renderStatusStrip([{ label: "已从图表取消挂载回复对象。", variant: "good" }]);
      renderSnapshot();
      return;
    }
    if (!related.length) {
      if (action === "jump" && messageId) {
        jumpToMessageWhenReady(messageId);
      }
      renderStatusStrip([{ label: "当前回复还没有可上图对象，已保留在会话里。", variant: "warn" }]);
      renderSnapshot();
      return;
    }
    state.selectedAnnotationId = related[0].id;
    const session = state.aiThreads.find((item) => item.id === (targetSession?.id || state.activeAiThreadId));
    if (action === "focus") {
      if (session && messageId) {
        mountReplyObjects(messageId, "focus", { sessionId: session.id, planId });
      }
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "focus" });
    } else if (action === "show") {
      if (session && messageId) {
        mountReplyObjects(messageId, "show", { sessionId: session.id, planId });
      }
      focusReplyObjects(messageId, { sessionId: session?.id, planId, mode: "show" });
    } else if (session && messageId) {
      mountReplyObjects(messageId, "replace", { sessionId: session.id, planId });
    }
    writeStorage("annotationFilters", state.annotationFilters);
    if (action === "jump") {
      jumpToMessageWhenReady(messageId);
    }
    focusAnnotationsOnChart(related, { minimumSpan: 36, maximumSpan: 140 });
    persistSessions();
    renderSnapshot();
  }

  function getWorkspaceRole(session, fallback = "analyst") {
    return String(session?.workspaceRole || fallback || "analyst").trim().toLowerCase() || "analyst";
  }

  function getSymbolWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    if (!state.symbolWorkspaceState || typeof state.symbolWorkspaceState !== "object") {
      state.symbolWorkspaceState = {};
    }
    if (!state.symbolWorkspaceState[normalizedSymbol]) {
      state.symbolWorkspaceState[normalizedSymbol] = {
        analystSessionId: null,
        scribeSessionId: null,
        lastActiveAt: null,
      };
    }
    return state.symbolWorkspaceState[normalizedSymbol];
  }

  function rememberSymbolWorkspaceSession(session) {
    if (!session) {
      return;
    }
    const symbol = String(session.symbol || session.contractId || session.memory?.symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const workspace = getSymbolWorkspace(symbol);
    const role = getWorkspaceRole(session);
    if (role === "scribe") {
      workspace.scribeSessionId = session.id;
    } else {
      workspace.analystSessionId = session.id;
    }
    workspace.lastActiveAt = new Date().toISOString();
    persistWorkbenchState();
  }

  function getSessionByRole(symbol, role = "analyst") {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const normalizedRole = getWorkspaceRole({ workspaceRole: role });
    const workspace = getSymbolWorkspace(normalizedSymbol);
    const sessionId = normalizedRole === "scribe" ? workspace.scribeSessionId : workspace.analystSessionId;
    const remembered = sessionId
      ? state.aiThreads.find((item) => item.id === sessionId && getWorkspaceRole(item) === normalizedRole)
      : null;
    if (remembered) {
      return remembered;
    }
    return null;
  }

  function getReplyExtractionState() {
    if (!state.replyExtractionState || typeof state.replyExtractionState !== "object") {
      state.replyExtractionState = {
        filter: "all",
        showIgnored: false,
        pendingOnly: false,
        intensity: "balanced",
        autoExtractEnabled: true,
        collapsed: false,
        bySymbol: {},
      };
    }
    if (!state.replyExtractionState.bySymbol || typeof state.replyExtractionState.bySymbol !== "object") {
      state.replyExtractionState.bySymbol = {};
    }
    if (!state.replyExtractionState.filter) {
      state.replyExtractionState.filter = "all";
    }
    if (!["strict", "balanced", "aggressive"].includes(state.replyExtractionState.intensity)) {
      state.replyExtractionState.intensity = "balanced";
    }
    state.replyExtractionState.showIgnored = !!state.replyExtractionState.showIgnored;
    state.replyExtractionState.pendingOnly = !!state.replyExtractionState.pendingOnly;
    state.replyExtractionState.autoExtractEnabled = state.replyExtractionState.autoExtractEnabled !== false;
    state.replyExtractionState.collapsed = !!state.replyExtractionState.collapsed;
    return state.replyExtractionState;
  }

  function getReplyExtractionWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const extractionState = getReplyExtractionState();
    if (!extractionState.bySymbol[normalizedSymbol]) {
      extractionState.bySymbol[normalizedSymbol] = {
        candidateMeta: {},
        lastTouchedAt: null,
      };
    }
    const workspace = extractionState.bySymbol[normalizedSymbol];
    if (!workspace.candidateMeta || typeof workspace.candidateMeta !== "object") {
      workspace.candidateMeta = {};
    }
    return workspace;
  }

  function getReplyCandidateKey(item = {}) {
    return String(item?.stableKey || item?.candidateKey || item?.id || "").trim() || null;
  }

  function updateReplyCandidateMeta(symbol, itemOrKey, patch = {}) {
    const candidateKey = typeof itemOrKey === "string" ? itemOrKey : getReplyCandidateKey(itemOrKey);
    if (!candidateKey) {
      return null;
    }
    const workspace = getReplyExtractionWorkspace(symbol);
    workspace.candidateMeta[candidateKey] = {
      ...(workspace.candidateMeta[candidateKey] || {}),
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    workspace.lastTouchedAt = workspace.candidateMeta[candidateKey].updatedAt;
    persistWorkbenchState();
    return workspace.candidateMeta[candidateKey];
  }

  function hydrateReplyCandidateState(symbol, item = {}) {
    const candidateKey = getReplyCandidateKey(item);
    const workspace = getReplyExtractionWorkspace(symbol);
    const meta = candidateKey ? (workspace.candidateMeta[candidateKey] || {}) : {};
    return {
      ...item,
      candidateKey,
      status: meta.status || item.status || "candidate",
      pinned: !!meta.pinned,
      ignored: (meta.status || item.status) === "ignored",
      linkedClusterKey: meta.linkedClusterKey || item.linkedClusterKey || null,
    };
  }

  async function activateSymbolWorkspace(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    let analystSession = getSessionByRole(normalizedSymbol, "analyst");
    if (!analystSession) {
      analystSession = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
        workspaceRole: "analyst",
        activate: false,
      });
    }
    let scribeSession = getSessionByRole(normalizedSymbol, "scribe");
    if (!scribeSession) {
      scribeSession = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
        workspaceRole: "scribe",
        activate: false,
      });
    }
    if (scribeSession) {
      rememberSymbolWorkspaceSession(scribeSession);
    }
    if (analystSession) {
      rememberSymbolWorkspaceSession(analystSession);
      setActiveThread(analystSession.id, analystSession.title, {
        symbol: normalizedSymbol,
        contractId: analystSession.contractId || normalizedSymbol,
        timeframe: analystSession.timeframe || state.topBar?.timeframe || "1m",
        windowRange: analystSession.windowRange || state.topBar?.quickRange || "最近7天",
        workspaceRole: "analyst",
      });
    }
    return { analystSession, scribeSession };
  }

  let eventPanelController = null;
  let eventOutcomeController = null;
  const promptTracePanelController = createWorkbenchPromptTracePanelController({
    state,
    els,
    fetchJson,
    renderStatusStrip,
    jumpToMessage: (messageId) => jumpToMessageWhenReady(messageId),
    onEventSelected: (eventId) => eventPanelController?.selectEvent(eventId, { centerChart: true, scrollCard: true }),
  });
  const threadController = createAiThreadController({
    state,
    els,
    onPlanAction: focusPlanOnChart,
    onPlanMetaAction: ({ type, ok, plan, summary, error }) => {
      if (type === "copy") {
        renderStatusStrip([{
          label: ok
            ? `已复制计划摘要：${plan?.title || "AI计划卡"}`
            : `复制失败：${error?.message || "无法写入剪贴板"}`,
          variant: ok ? "good" : "warn",
        }]);
        return;
      }
      if (type === "recap") {
        if (!ok) {
          renderStatusStrip([{ label: error?.message || "加入复盘失败", variant: "warn" }]);
          return;
        }
        setDrawerOpen("recap", true);
        renderSidebarSnapshot();
        renderStatusStrip([{ label: `已加入复盘：${plan?.title || summary || "AI计划卡"}`, variant: "good" }]);
      }
    },
    onMountedRepliesChanged: (session, nextIds) => {
      void syncMountedRepliesToServer(session);
      queueSessionMemoryRefresh([session.id], { forceServer: true, delay: 120 });
      if (Array.isArray(nextIds) && session.id === state.activeAiThreadId) {
        renderSnapshot();
      }
    },
    onPromptBlocksChanged: (session, { selectedPromptBlockIds, pinnedContextBlockIds, includeMemorySummary, includeRecentMessages } = {}) => {
      void syncPromptBlocksToServer(session, { selectedPromptBlockIds, pinnedContextBlockIds, includeMemorySummary, includeRecentMessages });
      if (session.id === state.activeAiThreadId) {
        renderAiChat();
      }
    },
    fetchJson,
    renderStatusStrip,
    onSessionActivated: (session) => {
      if (getWorkspaceRole(session) === "analyst") {
        rememberSymbolWorkspaceSession(session);
      }
      eventPanelController?.markDirty();
      void eventPanelController?.syncActiveSessionEventStream({ force: true, reason: "session-activated" });
      eventOutcomeController?.markDirty();
      void eventOutcomeController?.syncActiveSessionOutcomes({ force: true });
      renderSnapshot();
    },
  });
  const {
    ensureThread,
    getActiveThread,
    setActiveThread,
    hydrateSessionFromServer,
    syncSessionsFromServer,
    createBackendSession,
    getOrCreateBlankSessionForSymbol,
    createNewAnalystSession,
    getPreferredSessionForSymbol,
    renderAiThreadTabs,
    appendAiChatMessage,
    renderAiChat,
    upsertPlanCardToSession,
    cloneActiveThreadBranch,
    renameActiveThread,
    togglePinActiveThread,
    deleteActiveThread,
    addAttachments,
    clearAttachments,
    addPromptBlock,
    setMountedReplyIds,
    bindChatScrollBehavior,
    scrollChatToBottom,
    updateChatFollowState,
    scheduleDraftStateSync,
    persistSessions,
  } = threadController;

  const eventApi = createWorkbenchEventApi({ fetchJson });

  async function ensureActiveSessionPersisted() {
    let session = typeof getActiveThread === "function" ? getActiveThread() : null;
    if (session && !/^session-\d+$/i.test(String(session.id || ""))) {
      return session;
    }
    const symbol = session?.symbol || state.topBar?.symbol || "NQ";
    const contractId = session?.contractId || symbol;
    if (typeof getOrCreateBlankSessionForSymbol === "function") {
      session = await getOrCreateBlankSessionForSymbol(symbol, contractId, {
        workspaceRole: session?.workspaceRole || "analyst",
        activate: true,
      });
    }
    return session;
  }

  function jumpToEventSource(candidate) {
    if (!candidate?.source_message_id) {
      return false;
    }
    const targetSession = state.aiThreads.find((item) => item.id === candidate.session_id) || getActiveThread();
    if (targetSession) {
      setActiveThread(targetSession.id, targetSession.title, targetSession);
      renderAiSurface();
    }
    jumpToMessageWhenReady(candidate.source_message_id);
    return true;
  }

  function focusEventCandidateOnChart(candidate, { centerChart = true, announce = false } = {}) {
    if (!centerChart || !candidate) {
      window.dispatchEvent(new CustomEvent("replay-workbench:hover-item-changed"));
      return false;
    }
    const candles = state.snapshot?.candles || [];
    if (!candles.length) {
      return false;
    }
    const nextView = focusChartViewOnEventCandidate({
      candidate,
      candles,
      currentView: state.chartView,
      clampChartView,
    });
    if (!nextView) {
      window.dispatchEvent(new CustomEvent("replay-workbench:hover-item-changed"));
      return false;
    }
    state.chartView = nextView;
    syncLiveChartLogicalRange(nextView, "聚焦事件候选时同步图表视窗");
    renderCoreSnapshot();
    renderViewportDerivedSurfaces();
    if (announce) {
      renderStatusStrip([{ label: `已定位到事件：${candidate.title || "事件"}`, variant: "emphasis" }]);
    }
    return true;
  }

  function createProgressController({
    container,
    fill,
    percentNode,
    labelNode,
    detailNode = null,
    defaultLabel = "进度",
    defaultDetail = "",
    completeHoldMs = 1200,
    fillDimension = "width",
  }) {
    if (!container || !fill || !percentNode || !labelNode) {
      return {
        setProgress() {},
        reset() {},
      };
    }
    let animationFrame = null;
    let visualPercent = 0;
    let hideTimer = null;

    function stopAnimation() {
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = null;
      }
    }

    function writePercent(nextPercent) {
      fill.style[fillDimension] = `${nextPercent.toFixed(1)}%`;
      percentNode.textContent = `${Math.round(nextPercent)}%`;
      container.style.setProperty("--progress-percent", nextPercent.toFixed(1));
    }

    function resetVisuals() {
      stopAnimation();
      visualPercent = 0;
      writePercent(0);
      labelNode.textContent = defaultLabel;
      if (detailNode) {
        detailNode.textContent = defaultDetail;
      }
      container.classList.remove("active");
      container.classList.remove("visible");
      container.classList.remove("build-progress-complete");
    }

    function animateTo(targetPercent = 0) {
      const target = Math.max(0, Math.min(100, Number(targetPercent) || 0));
      stopAnimation();
      const step = () => {
        const delta = target - visualPercent;
        if (Math.abs(delta) < 0.35) {
          visualPercent = target;
        } else {
          visualPercent += delta * 0.2;
        }
        writePercent(visualPercent);
        if (Math.abs(target - visualPercent) >= 0.35) {
          animationFrame = requestAnimationFrame(step);
        } else {
          animationFrame = null;
        }
      };
      animationFrame = requestAnimationFrame(step);
    }

    function setProgress(active, percent = 0, label = "", detail = "", options = {}) {
      const isActive = !!active;
      const target = Math.max(0, Math.min(100, Number(percent) || 0));
      const holdMs = Number.isFinite(Number(options?.holdMs)) ? Number(options.holdMs) : (target >= 100 ? completeHoldMs : 0);
      if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
      }
      labelNode.textContent = label || defaultLabel;
      if (detailNode) {
        detailNode.textContent = detail || defaultDetail;
      }
      if (!isActive && target <= 0) {
        resetVisuals();
        return;
      }
      container.classList.add("visible");
      container.classList.toggle("active", isActive);
      container.classList.toggle("build-progress-complete", !isActive && target >= 100);
      animateTo(target);
      if (!isActive) {
        hideTimer = window.setTimeout(() => {
          resetVisuals();
        }, holdMs);
      }
    }

    return {
      setProgress,
      reset: resetVisuals,
    };
  }

  const buildProgressController = createProgressController({
    container: els.buildProgress,
    fill: els.buildProgressFill,
    percentNode: els.buildProgressPercent,
    labelNode: els.buildProgressLabel,
    defaultLabel: "界面加载进度",
    fillDimension: "height",
  });

  const transferProgressController = createProgressController({
    container: els.transferProgress,
    fill: els.transferProgressFill,
    percentNode: els.transferProgressPercent,
    labelNode: els.transferProgressLabel,
    detailNode: els.transferProgressDetail,
    defaultLabel: "ATAS 传输进度",
    defaultDetail: "当前没有活动中的 ATAS 传输任务。",
    completeHoldMs: 2200,
  });

  const replayLoader = createReplayLoader({
    state,
    els,
    fetchJson,
    ensureThread,
    renderCoreSnapshot: () => renderCoreSnapshot(),
    renderSidebarSnapshot: () => renderSidebarSnapshot(),
    renderDeferredSurfaces: () => renderDeferredSurfaces(),
  });

  const actions = createWorkbenchActions({
    state,
    els,
    fetchJson,
    toUtcString: (value) => value ? new Date(value).toISOString() : null,
    syncCacheKey,
    renderStatusStrip,
    renderSnapshot: (...args) => getRenderSnapshot()(...args),
    renderCoreSnapshot: () => renderCoreSnapshot(),
    renderError: (error) => renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]),
    renderAiError: (error) => renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]),
    setBuildProgress: (active, percent, label) => {
      if (state.silentBuildProgress) {
        if (!active) {
          buildProgressController.reset();
        }
        return;
      }
      buildProgressController.setProgress(active, percent, label || "界面加载进度");
    },
    buildRequestPayload: (...args) => getBuildRequestPayload()(...args),
    buildStatusChips,
    translateVerificationStatus,
    loadSnapshotByIngestionId: replayLoader.loadSnapshotByIngestionId,
    applySnapshotToState: replayLoader.applySnapshotToState,
    loadSidebarDataInBackground: replayLoader.loadSidebarDataInBackground,
    loadHistoryDepthInBackground: replayLoader.loadHistoryDepthInBackground,
    loadDeferredEnhancements: replayLoader.loadDeferredEnhancements,
  });

  const aiChat = createAiChatController({
    state,
    els,
    fetchJson,
    renderStatusStrip,
    getActiveThread,
    setActiveThread,
    appendAiChatMessage,
    getPresetThreadMeta,
    createThreadId,
    upsertPlanCardToSession,
    persistSessions,
    sessionMemoryEngine,
    addPromptBlock,
    getOrCreateBlankSessionForSymbol,
    createNewAnalystSession,
    renderAiChat,
    scheduleDraftStateSync,
    setMountedReplyIds,
    onReplyCommitted: ({ session, messageId }) => {
      eventPanelController?.markDirty({ sourceMessageId: messageId });
      void eventPanelController?.syncActiveSessionEventStream({
        force: true,
        reason: "reply-committed",
        sourceMessageId: messageId,
      });
      eventOutcomeController?.markDirty();
      void eventOutcomeController?.syncActiveSessionOutcomes({ force: true });
      if (session?.id) {
        queueSessionMemoryRefresh([session.id], { forceServer: true, delay: 120 });
      }
    },
  });
  aiChat.bindStreamingControls?.();

  eventPanelController = createWorkbenchEventPanelController({
    state,
    els,
    eventApi,
    renderStatusStrip,
    persistWorkbenchState,
    getActiveThread,
    ensureActiveSessionPersisted,
    focusEventCandidateOnChart,
    jumpToEventSource,
    onPromptTraceRequested: (candidate) => {
      void promptTracePanelController.openPromptTraceForCandidate(candidate);
      return true;
    },
    onOutcomeRequested: (candidate) => eventOutcomeController?.focusOutcomeForCandidate(candidate) || false,
    afterMutation: async (mutation) => {
      if (mutation?.candidate?.session_id) {
        await hydrateSessionFromServer(mutation.candidate.session_id, {
          activate: mutation.candidate.session_id === state.activeAiThreadId,
        });
      }
      eventOutcomeController?.markDirty();
      await eventOutcomeController?.syncActiveSessionOutcomes({ force: true });
      renderSnapshot();
    },
  });

  eventOutcomeController = createWorkbenchEventOutcomePanelController({
    state,
    els,
    eventApi,
    renderStatusStrip,
    persistWorkbenchState,
    getActiveThread,
    jumpToMessage: (messageId) => jumpToMessageWhenReady(messageId),
    onPromptTraceRequested: (candidate) => promptTracePanelController.openPromptTraceForCandidate(candidate),
    onEventSelected: (eventId) => eventPanelController?.selectEvent(eventId, { centerChart: true, scrollCard: true }),
  });

  const manualEventTools = createWorkbenchEventManualTools({
    state,
    els,
    renderStatusStrip,
    ensureActiveSessionPersisted,
    createManualEventCandidate: (payload) => eventPanelController?.createManualEventCandidate(payload),
    renderSnapshot: () => renderSnapshot(),
  });
  const annotationPanelController = createAnnotationPanelController({
    state,
    els,
    renderSnapshot: () => renderSnapshot(),
    onAnnotationAction: handleAnnotationObjectAction,
  });
  annotationPopoverController = createAnnotationPopoverController({
    state,
    els,
    onAnnotationAction: handleAnnotationObjectAction,
  });
  const modelSwitcherController = createModelSwitcherController({
    state,
    els,
    getActiveThread,
    appendAiChatMessage,
    persistSessions,
    sessionMemoryEngine,
    renderSnapshot: () => renderSnapshot(),
  });
  const buttonFeedbackTimers = new WeakMap();
  const defaultAttachmentAccept = els.attachmentInput?.getAttribute("accept") || "";
  const voiceCaptureState = {
    recognition: null,
    listening: false,
    stopRequested: false,
    errorMessage: "",
    transcriptCaptured: false,
    baseText: "",
  };

  function isDockedAiLayout() {
    return window.innerWidth > MOBILE_AI_BREAKPOINT;
  }

  function syncAiSidebarViewportState({ persist = true } = {}) {
    if (!els.aiSidebar) {
      return;
    }
    const docked = isDockedAiLayout();
    const shouldOpen = docked ? true : !!state.aiSidebarOpen;
    els.aiSidebar.classList.toggle("open", shouldOpen);
    els.workbenchMain?.classList.toggle("ai-sidebar-open", shouldOpen);
    if (els.aiSidebarTrigger) {
      els.aiSidebarTrigger.classList.toggle("hidden", shouldOpen);
    }
    if (docked) {
      state.aiSidebarOpen = true;
    }
    if (persist) {
      writeStorage("aiSidebarState", {
        open: state.aiSidebarOpen,
        pinned: state.aiSidebarPinned,
      });
    }
  }

  function syncBottomDrawerVisibility() {
    if (!els.bottomContextDrawer) {
      return;
    }
    const hasOpenDrawer = Object.values(state.drawerState || {}).some(Boolean);
    els.bottomContextDrawer.hidden = !hasOpenDrawer;
  }

  function getDrawerPanel(key) {
    return {
      context: els.drawerContextPanel,
      manual: els.drawerManualPanel,
      focus: els.drawerFocusPanel,
      strategy: els.drawerStrategyPanel,
      entries: els.drawerEntriesPanel,
      recap: els.drawerRecapPanel,
      gamma: els.drawerGammaPanel,
    }[key] || null;
  }

  function getDrawerButton(key) {
    return {
      context: els.drawerContextButton,
      manual: els.drawerManualButton,
      focus: els.drawerFocusButton,
      strategy: els.drawerStrategyButton,
      entries: els.drawerEntriesButton,
      recap: els.drawerRecapButton,
      gamma: els.drawerGammaButton,
    }[key] || null;
  }

  function syncDrawerTabState() {
    ["context", "manual", "focus", "strategy", "entries", "recap", "gamma"].forEach((key) => {
      const button = getDrawerButton(key);
      if (!button) {
        return;
      }
      const isActive = !!state.drawerState[key];
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function setDrawerOpen(key, open) {
    const panel = getDrawerPanel(key);
    state.drawerState[key] = !!open;
    if (panel) {
      panel.style.display = open ? "block" : "none";
    }
    syncDrawerTabState();
    syncBottomDrawerVisibility();
    persistWorkbenchState();
  }

  function focusChartOnEventCluster(cluster) {
    const candles = state.snapshot?.candles || [];
    if (!cluster || !candles.length) {
      return;
    }
    const targetTime = Number(cluster.time || 0) * 1000;
    let targetIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    candles.forEach((bar, index) => {
      const barTime = new Date(bar.started_at).getTime();
      const distance = Math.abs(barTime - targetTime);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        targetIndex = index;
      }
    });
    const span = state.chartView
      ? Math.max(24, state.chartView.endIndex - state.chartView.startIndex + 1)
      : Math.min(120, candles.length);
    const startIndex = Math.max(0, targetIndex - Math.floor(span / 2));
    const endIndex = Math.min(candles.length - 1, startIndex + span - 1);
    const nextView = clampChartView(candles.length, startIndex, endIndex, state.chartView);
    state.chartView = nextView;
    syncLiveChartLogicalRange(nextView, "聚焦事件簇时同步图表视窗");
  }

  function selectChartEventCluster(clusterKey, { centerChart = false, openContext = true, announce = false } = {}) {
    const cluster = state.chartEventModel?.clusterIndex?.[clusterKey];
    if (!cluster) {
      return false;
    }
    state.selectedChartEventClusterKey = clusterKey;
    if (centerChart) {
      focusChartOnEventCluster(cluster);
    }
    if (openContext) {
      setDrawerOpen("context", true);
    }
    if (announce) {
      renderStatusStrip([{ label: `事件详情：${cluster.timeLabel || "--"} · ${cluster.summaryText || "事件"}`, variant: "emphasis" }]);
    }
    renderSnapshot();
    return true;
  }

  function applyLayoutWidths() {
    const nextSidebarWidth = Math.max(
      DESKTOP_SIDEBAR_MIN,
      Math.min(DESKTOP_SIDEBAR_MAX, Number(state.layout.chatWidth) || 440),
    );
    state.layout.chatWidth = nextSidebarWidth;
    els.shellLayout?.style.setProperty("--sidebar-width", `${nextSidebarWidth}px`);
    els.chartWorkspace.style.minWidth = "0";
    els.chartWorkspace.style.width = "";
    els.rightPanel.style.width = "";
    els.aiSidebar.style.width = "";
    els.aiChatThread.style.height = "";
    syncAiSidebarViewportState({ persist: false });
    writeStorage("layout", state.layout);
    window.requestAnimationFrame(() => updateChatFollowState({ persist: false }));
  }

  const uiActionLocks = new Set();

  function setButtonBusy(button, busy) {
    if (!button) {
      return;
    }
    button.dataset.busy = busy ? "true" : "false";
    button.setAttribute("aria-busy", busy ? "true" : "false");
    if ("disabled" in button) {
      if (busy) {
        button.dataset.wasDisabled = button.disabled ? "true" : "false";
        button.disabled = true;
      } else {
        button.disabled = button.dataset.wasDisabled === "true";
        delete button.dataset.wasDisabled;
      }
    }
  }

  function pulseButton(button) {
    if (!button) {
      return;
    }
    button.dataset.pressed = "true";
    const previousTimer = buttonFeedbackTimers.get(button);
    if (previousTimer) {
      window.clearTimeout(previousTimer);
    }
    const timer = window.setTimeout(() => {
      delete button.dataset.pressed;
      buttonFeedbackTimers.delete(button);
    }, 150);
    buttonFeedbackTimers.set(button, timer);
  }

  function installButtonFeedback() {
    document.addEventListener("pointerdown", (event) => {
      const button = event.target?.closest("button");
      if (!button || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const button = document.activeElement;
      if (!(button instanceof HTMLElement) || !button.matches("button") || button.disabled) {
        return;
      }
      pulseButton(button);
    }, true);
  }

  function focusComposerInput() {
    if (!els.aiChatInput) {
      return;
    }
    els.aiChatInput.focus();
    const end = els.aiChatInput.value.length;
    if (typeof els.aiChatInput.setSelectionRange === "function") {
      els.aiChatInput.setSelectionRange(end, end);
    }
  }

  function updateComposerDraft(value) {
    if (!els.aiChatInput) {
      return;
    }
    els.aiChatInput.value = value;
    aiChat.handleComposerInput(value);
  }

  function syncAiSidebarPinButtonState() {
    if (!els.aiSidebarPinButton) {
      return;
    }
    els.aiSidebarPinButton.classList.toggle("is-active", !!state.aiSidebarPinned);
    els.aiSidebarPinButton.setAttribute("aria-pressed", state.aiSidebarPinned ? "true" : "false");
    els.aiSidebarPinButton.title = state.aiSidebarPinned ? "取消固定侧栏偏好" : "固定侧栏偏好";
  }

  function syncQuickActionButtonState() {
    const skillPanelOpen = !!els.aiSkillPanel && !els.aiSkillPanel.hidden;
    if (els.aiMoreButton) {
      els.aiMoreButton.classList.toggle("is-active", skillPanelOpen);
      els.aiMoreButton.setAttribute("aria-expanded", skillPanelOpen ? "true" : "false");
    }
    [els.aiVoiceButton, els.aiVoiceInputButton].forEach((button) => {
      if (!button) {
        return;
      }
      button.classList.toggle("is-active", !!voiceCaptureState.listening);
      button.setAttribute("aria-pressed", voiceCaptureState.listening ? "true" : "false");
      setButtonBusy(button, false);
    });
  }

  function setSkillPanelVisible(visible, { announce = false } = {}) {
    if (!els.aiSkillPanel) {
      return;
    }
    const nextVisible = !!visible;
    const previousVisible = !els.aiSkillPanel.hidden;
    els.aiSkillPanel.hidden = !nextVisible;
    syncQuickActionButtonState();
    if (!announce || previousVisible === nextVisible) {
      return;
    }
    renderStatusStrip([{ label: nextVisible ? "已打开快捷技能面板" : "已收起快捷技能面板", variant: "emphasis" }]);
    if (nextVisible) {
      els.aiSkillSearch?.focus();
    } else {
      focusComposerInput();
    }
  }

  function openAttachmentPicker({ accept = defaultAttachmentAccept, statusLabel = "选择要附加的文件" } = {}) {
    if (!els.attachmentInput) {
      renderStatusStrip([{ label: "当前页面还没有可用的附件入口。", variant: "warn" }]);
      return;
    }
    els.attachmentInput.setAttribute("accept", accept || defaultAttachmentAccept);
    renderStatusStrip([{ label: statusLabel, variant: "emphasis" }]);
    els.attachmentInput.click();
  }

  function addQuickAttachment(item, statusLabel) {
    addAttachments([item]);
    renderStatusStrip([{ label: statusLabel, variant: "good" }]);
    renderSnapshot();
    focusComposerInput();
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error(`读取文件失败: ${file?.name || "unknown"}`));
      reader.readAsDataURL(file);
    });
  }

  async function mapFileToAttachment(file) {
    const mediaType = file?.type || "application/octet-stream";
    const dataUrl = await readFileAsDataUrl(file);
    return {
      name: file?.name || `attachment-${Date.now()}`,
      kind: mediaType,
      media_type: mediaType,
      size: Number(file?.size || 0),
      data_url: dataUrl,
      preview_url: mediaType.startsWith("image/") ? dataUrl : "",
    };
  }

  function loadImageFromUrl(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("加载图片失败"));
      image.src = url;
    });
  }

  async function captureChartFrameDataUrl() {
    if (!els.chartFrame || !state.snapshot?.candles?.length) {
      throw new Error("请先加载图表，再生成图表截图。");
    }
    const frameRect = els.chartFrame.getBoundingClientRect();
    const width = Math.max(1, Math.round(frameRect.width));
    const height = Math.max(1, Math.round(frameRect.height));
    if (width < 4 || height < 4) {
      throw new Error("图表还未完成渲染。");
    }

    const output = document.createElement("canvas");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    output.width = Math.round(width * dpr);
    output.height = Math.round(height * dpr);
    const ctx = output.getContext("2d");
    if (!ctx) {
      throw new Error("当前浏览器无法生成截图。");
    }
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#101827";
    ctx.fillRect(0, 0, width, height);

    let hasLayer = false;
    const visibleCanvases = Array.from(els.chartFrame.querySelectorAll("canvas")).filter((node) => {
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    });
    visibleCanvases.forEach((canvasNode) => {
      const rect = canvasNode.getBoundingClientRect();
      ctx.drawImage(canvasNode, rect.left - frameRect.left, rect.top - frameRect.top, rect.width, rect.height);
      hasLayer = true;
    });

    if (els.chartSvg && els.chartSvg.style.display !== "none" && els.chartSvg.innerHTML.trim()) {
      const serialized = new XMLSerializer().serializeToString(els.chartSvg);
      const svgMarkup = serialized.includes("xmlns=")
        ? serialized
        : serialized.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
      const blobUrl = URL.createObjectURL(new Blob([svgMarkup], { type: "image/svg+xml;charset=utf-8" }));
      try {
        const image = await loadImageFromUrl(blobUrl);
        const rect = els.chartSvg.getBoundingClientRect();
        ctx.drawImage(image, rect.left - frameRect.left, rect.top - frameRect.top, rect.width, rect.height);
        hasLayer = true;
      } finally {
        URL.revokeObjectURL(blobUrl);
      }
    }

    if (!hasLayer) {
      throw new Error("当前图表没有可截图的可视内容。");
    }
    return output.toDataURL("image/png");
  }

  async function addChartScreenshotAttachment(statusLabel = "已把图表截图加入当前会话附件。") {
    const dataUrl = await captureChartFrameDataUrl();
    addQuickAttachment({
      name: `chart-${Date.now()}.png`,
      kind: "chart-screenshot",
      media_type: "image/png",
      data_url: dataUrl,
      preview_url: dataUrl,
    }, statusLabel);
  }

  function normalizeVoiceError(errorCode) {
    const mapping = {
      "aborted": "已中断",
      "audio-capture": "没有检测到可用麦克风",
      "network": "网络异常",
      "not-allowed": "没有获得麦克风权限",
      "service-not-allowed": "浏览器禁止使用语音服务",
      "no-speech": "没有识别到语音",
    };
    return mapping[errorCode] || errorCode || "未知错误";
  }

  function applyVoiceDraft(transcript) {
    const normalized = String(transcript || "").trim();
    const nextDraft = normalized
      ? `${voiceCaptureState.baseText}${voiceCaptureState.baseText ? "\n" : ""}${normalized}`.trim()
      : voiceCaptureState.baseText;
    updateComposerDraft(nextDraft);
  }

  function stopVoiceCapture({ announce = true } = {}) {
    if (!voiceCaptureState.listening || !voiceCaptureState.recognition) {
      return false;
    }
    voiceCaptureState.stopRequested = true;
    if (announce) {
      renderStatusStrip([{ label: "正在停止语音输入…", variant: "emphasis" }]);
    }
    try {
      voiceCaptureState.recognition.stop();
      return true;
    } catch (error) {
      console.warn("停止语音输入失败:", error);
      return false;
    }
  }

  function startVoiceCapture() {
    if (voiceCaptureState.listening) {
      stopVoiceCapture();
      return;
    }
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      renderStatusStrip([{ label: "当前浏览器不支持语音输入，已聚焦消息输入框。", variant: "warn" }]);
      focusComposerInput();
      return;
    }
    voiceCaptureState.baseText = (els.aiChatInput?.value || "").trimEnd();
    voiceCaptureState.stopRequested = false;
    voiceCaptureState.errorMessage = "";
    voiceCaptureState.transcriptCaptured = false;
    const recognition = new SpeechRecognitionCtor();
    voiceCaptureState.recognition = recognition;
    recognition.lang = "zh-CN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      voiceCaptureState.listening = true;
      syncQuickActionButtonState();
      renderStatusStrip([{ label: "正在语音输入，再点一次可停止。", variant: "emphasis" }]);
      focusComposerInput();
    };
    recognition.onresult = (event) => {
      let mergedTranscript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        const segment = event.results[index]?.[0]?.transcript || "";
        mergedTranscript += segment;
        if (event.results[index]?.isFinal && segment.trim()) {
          voiceCaptureState.transcriptCaptured = true;
        }
      }
      if (mergedTranscript.trim()) {
        applyVoiceDraft(mergedTranscript);
      }
    };
    recognition.onerror = (event) => {
      voiceCaptureState.errorMessage = normalizeVoiceError(event.error);
    };
    recognition.onend = () => {
      const hadTranscript = voiceCaptureState.transcriptCaptured;
      const errorMessage = voiceCaptureState.errorMessage;
      const stopRequested = voiceCaptureState.stopRequested;
      voiceCaptureState.recognition = null;
      voiceCaptureState.listening = false;
      voiceCaptureState.stopRequested = false;
      voiceCaptureState.errorMessage = "";
      voiceCaptureState.transcriptCaptured = false;
      syncQuickActionButtonState();
      if (errorMessage) {
        renderStatusStrip([{ label: `语音输入失败：${errorMessage}`, variant: "warn" }]);
      } else if (hadTranscript) {
        renderStatusStrip([{ label: "语音内容已写入输入框。", variant: "good" }]);
        focusComposerInput();
      } else if (stopRequested) {
        renderStatusStrip([{ label: "语音输入已停止。", variant: "emphasis" }]);
        focusComposerInput();
      } else {
        renderStatusStrip([{ label: "没有识别到语音内容。", variant: "warn" }]);
        focusComposerInput();
      }
    };
    try {
      renderStatusStrip([{ label: "正在请求语音权限…", variant: "emphasis" }]);
      recognition.start();
    } catch (error) {
      voiceCaptureState.recognition = null;
      voiceCaptureState.listening = false;
      syncQuickActionButtonState();
      renderStatusStrip([{ label: `语音输入无法启动：${error.message || String(error)}`, variant: "warn" }]);
      focusComposerInput();
    }
  }

  async function runButtonAction(button, action, {
    silentError = false,
    lockKey = "",
    extraBusyTargets = [],
    blockedLabel = "",
  } = {}) {
    const busyTargets = Array.from(new Set([button, ...extraBusyTargets].filter(Boolean)));
    if (busyTargets.some((target) => target?.dataset.busy === "true")) {
      if (blockedLabel) {
        renderStatusStrip([{ label: blockedLabel, variant: "warn" }]);
      }
      return null;
    }
    const normalizedLockKey = String(lockKey || "").trim();
    if (normalizedLockKey && uiActionLocks.has(normalizedLockKey)) {
      if (blockedLabel) {
        renderStatusStrip([{ label: blockedLabel, variant: "warn" }]);
      }
      return null;
    }
    if (normalizedLockKey) {
      uiActionLocks.add(normalizedLockKey);
    }
    busyTargets.forEach((target) => setButtonBusy(target, true));
    try {
      return await action();
    } catch (error) {
      console.error("按钮动作失败:", error);
      if (!silentError) {
        renderStatusStrip([{ label: error.message || String(error), variant: "warn" }]);
      }
      return null;
    } finally {
      busyTargets.forEach((target) => setButtonBusy(target, false));
      if (normalizedLockKey) {
        uiActionLocks.delete(normalizedLockKey);
      }
    }
  }

  async function dispatchAiComposerSend({ button = els.aiChatSendButton, extraBusyTargets = [], beforeSend = null } = {}) {
    return runButtonAction(button, async () => {
      if (typeof beforeSend === "function") {
        const proceed = await beforeSend();
        if (proceed === false) {
          return null;
        }
      }
      await aiChat.handleAiChatSend();
      renderSnapshot();
      return true;
    }, {
      lockKey: "ai-composer-send",
      extraBusyTargets,
      blockedLabel: "AI 正在处理上一条请求，请等待完成或先停止生成。",
    });
  }

  function updateHeaderStatus() {
    state.topBar.symbol = els.instrumentSymbol.value.trim() || "NQ";
    state.topBar.timeframe = els.displayTimeframe.value;
    state.topBar.quickRange = els.quickRangeSelect.value;
    applyHeaderChipState(els.statusSymbolChip, { label: state.topBar.symbol });
    applyHeaderChipState(els.statusTimeframeChip, { label: timeframeLabel(state.topBar.timeframe) });
    const perfParts = [];
    if (Number.isFinite(state.perf.buildResponseMs)) perfParts.push(`build ${state.perf.buildResponseMs}ms`);
    if (Number.isFinite(state.perf.coreSnapshotLoadMs)) perfParts.push(`core-load ${state.perf.coreSnapshotLoadMs}ms`);
    if (Number.isFinite(state.perf.coreRenderMs)) perfParts.push(`core-render ${state.perf.coreRenderMs}ms`);
    if (Number.isFinite(state.perf.sidebarLoadMs)) perfParts.push(`sidebar-load ${state.perf.sidebarLoadMs}ms`);
    if (Number.isFinite(state.perf.sidebarRenderMs)) perfParts.push(`sidebar-render ${state.perf.sidebarRenderMs}ms`);
    if (state.historyBackfillLoading) perfParts.push("history loading");
    else if (state.fullHistoryLoaded) perfParts.push("history ready");
    const quickRangeLabel = els.quickRangeSelect.options[els.quickRangeSelect.selectedIndex]?.text || "自定义";
    applyHeaderChipState(els.statusWindowChip, {
      label: perfParts.length ? `${quickRangeLabel} · ${perfParts.join(" / ")}` : quickRangeLabel,
      title: perfParts.length ? `${quickRangeLabel}\n${perfParts.join(" / ")}` : quickRangeLabel,
    });

    applyHeaderChipState(els.statusDataChip, getDataStatusState());
    applyHeaderChipState(els.statusIntegrityChip, getIntegrityStatusState());
    applyHeaderChipState(els.statusCacheChip, getCacheStatusState());
    applyHeaderChipState(els.statusBackfillChip, getBackfillStatusState());

    const viewportSummary = state.chartEventModel?.viewportSummary
      || (state.snapshot?.candles?.length ? (els.chartViewportMeta?.textContent || "视图已初始化") : "视图：未初始化");
    applyHeaderChipState(els.statusViewportChip, {
      label: `视图：${viewportSummary.replace(/^视图：/, "")}`,
      variant: state.chartEventModel?.shownClusterCount ? "emphasis" : "",
      title: els.chartViewportMeta?.textContent || viewportSummary,
    });

    applyHeaderChipState(els.statusSyncChip, getSyncStatusState());
    updateHeaderMoreMenuState();
    if (isCacheViewerOpen()) {
      updateCacheViewer();
    }
    syncBackfillProgressPolling();
    persistWorkbenchState();
  }


  function updateAnnotationLifecycle() {
    return planLifecycleEngine.updateAnnotationLifecycle();
  }

  let pendingMemoryRefreshTimer = null;
  let pendingAnnotationLifecycleTimer = null;
  const memoryRefreshQueue = new Set();

  function queueSessionMemoryRefresh(sessionIds = [], { forceServer = true, delay = 220 } = {}) {
    if (state.snapshotLoading) {
      return;
    }
    if (!sessionMemoryEngine?.refreshSessionMemory) {
      return;
    }
    (Array.isArray(sessionIds) ? sessionIds : [sessionIds]).filter(Boolean).forEach((id) => memoryRefreshQueue.add(id));
    if (!memoryRefreshQueue.size) {
      return;
    }
    if (pendingMemoryRefreshTimer) {
      clearTimeout(pendingMemoryRefreshTimer);
    }
    pendingMemoryRefreshTimer = window.setTimeout(async () => {
      const targetIds = Array.from(memoryRefreshQueue);
      memoryRefreshQueue.clear();
      pendingMemoryRefreshTimer = null;
      await Promise.all(targetIds.map(async (sessionId) => {
        const session = state.aiThreads.find((item) => item.id === sessionId || item.sessionId === sessionId);
        if (!session) {
          return;
        }
        try {
          await sessionMemoryEngine.refreshSessionMemory(session, { forceServer });
        } catch (error) {
          console.warn("刷新会话记忆失败:", error);
        }
      }));
      persistSessions();
      if (targetIds.includes(state.activeAiThreadId)) {
        renderAiThreadTabs();
        renderAiChat();
        if (els.aiModelSwitcherModal && !els.aiModelSwitcherModal.classList.contains("is-hidden")) {
          try {
            await modelSwitcherController.refreshHandoffPreview({ forceServer: false });
          } catch (error) {
            console.warn("刷新交接预览失败:", error);
          }
        }
      }
    }, delay);
  }

  function queueAnnotationLifecycleRefresh({ delay = 1200, refreshMemory = true, forceServer = true } = {}) {
    if (state.snapshotLoading) {
      return;
    }
    if (pendingAnnotationLifecycleTimer) {
      clearTimeout(pendingAnnotationLifecycleTimer);
    }
    pendingAnnotationLifecycleTimer = window.setTimeout(() => {
      const startedAt = performance.now();
      pendingAnnotationLifecycleTimer = null;
      const changedSessionIds = updateAnnotationLifecycle();
      if (refreshMemory && changedSessionIds?.length) {
        queueSessionMemoryRefresh(changedSessionIds, { forceServer, delay: 260 });
      }
      annotationPanelController.renderAnnotationPanel();
      state.perf.deferredAnnotationMs = Math.round(performance.now() - startedAt);
    }, delay);
  }

  function updateDynamicAnalysisVisibility() {
    const hasManualRegions = !!state.manualRegions.length;
    const hasSelectedBar = state.selectedCandleIndex != null || state.selectedFootprintBar != null;
    const hasEntries = !!state.operatorEntries.length;
    const hasLiveDepth = !!state.snapshot?.live_tail;
    Array.from(els.analysisTypeSelect.options).forEach((option) => {
      const hidden = (option.value === "manual_region" && !hasManualRegions)
        || (option.value === "selected_bar" && !hasSelectedBar)
        || (option.value === "entry_review" && !hasEntries)
        || (option.value === "live_depth" && !hasLiveDepth);
      option.hidden = hidden;
    });
    Array.from(els.analysisRangeSelect.options).forEach((option) => {
      const hidden = (option.value === "selected_region" && !hasManualRegions)
        || (option.value === "selected_bar" && !hasSelectedBar)
        || (option.value === "latest_entry" && !hasEntries);
      option.hidden = hidden;
    });
    [els.analysisTypeSelect, els.analysisRangeSelect].forEach((select) => {
      const currentOption = select?.selectedOptions?.[0];
      if (currentOption && currentOption.hidden) {
        const fallback = Array.from(select.options).find((option) => !option.hidden);
        if (fallback) {
          select.value = fallback.value;
        }
      }
    });
    [
      [els.manualRegionButton, hasManualRegions],
      [els.selectedBarButton, hasSelectedBar],
      [els.liveDepthButton, hasLiveDepth],
    ].forEach(([button, visible]) => {
      if (!button) {
        return;
      }
      button.hidden = !visible;
      button.disabled = !visible;
    });
  }

  let liveRefreshInterval = null;
  let liveRefreshRequestInFlight = false;

  function getTimeframeMinutes(timeframe) {
    const minutesByTimeframe = {
      "1m": 1,
      "5m": 5,
      "15m": 15,
      "30m": 30,
      "1h": 60,
      "1d": 1440,
    };
    return minutesByTimeframe[timeframe] || 1;
  }

  function buildCandleSignature(candle) {
    if (!candle) {
      return "";
    }
    return [
      candle.started_at || "",
      candle.open ?? "",
      candle.high ?? "",
      candle.low ?? "",
      candle.close ?? "",
      candle.volume ?? "",
    ].join(":");
  }

  function hasSameStartedAtPrefix(previousCandles = [], nextCandles = [], length = previousCandles.length) {
    if (!Array.isArray(previousCandles) || !Array.isArray(nextCandles) || length <= 0) {
      return false;
    }
    for (let index = 0; index < length; index += 1) {
      if (previousCandles[index]?.started_at !== nextCandles[index]?.started_at) {
        return false;
      }
    }
    return true;
  }

  function canUseTailUpdate(previousCandles = [], nextCandles = []) {
    if (!previousCandles.length || !nextCandles.length || nextCandles.length < previousCandles.length) {
      return false;
    }
    if (nextCandles.length - previousCandles.length > 1) {
      return false;
    }
    const previousLastStartedAt = previousCandles[previousCandles.length - 1]?.started_at;
    const nextLastStartedAt = nextCandles[nextCandles.length - 1]?.started_at;
    if (!previousLastStartedAt || !nextLastStartedAt) {
      return false;
    }
    if (nextCandles.length === previousCandles.length) {
      return previousLastStartedAt === nextLastStartedAt;
    }
    return hasSameStartedAtPrefix(previousCandles.slice(0, -1), nextCandles, previousCandles.length - 1)
      && nextCandles[nextCandles.length - 2]?.started_at === previousLastStartedAt;
  }

  function canUseAppendTail(previousCandles = [], nextCandles = []) {
    if (!previousCandles.length || !nextCandles.length || nextCandles.length <= previousCandles.length) {
      return false;
    }
    return hasSameStartedAtPrefix(previousCandles, nextCandles, previousCandles.length);
  }

  function applyLiveResponseMeta(response) {
    const integrityHash = response?.integrity ? JSON.stringify(response.integrity) : null;
    const integrityChanged = integrityHash !== state.lastLiveTailIntegrityHash;
    state.integrity = response?.integrity || state.integrity;
    state.pendingBackfill = response?.latest_backfill_request || state.pendingBackfill;
    state.lastLiveTailIntegrityHash = integrityHash;
    return { integrityChanged };
  }

  let backfillProgressInterval = null;
  let backfillProgressRequestInFlight = false;

  function buildBackfillProgressQuery() {
    const pending = state.pendingBackfill || state.transportProgress?.request || state.buildResponse?.atas_backfill_request || null;
    const instrumentSymbol = String(
      pending?.instrument_symbol
        || state.snapshot?.instrument_symbol
        || state.snapshot?.instrument?.symbol
        || state.topBar?.symbol
        || els.instrumentSymbol?.value
        || "",
    ).trim().toUpperCase();
    const displayTimeframe = String(
      pending?.display_timeframe
        || state.snapshot?.display_timeframe
        || state.topBar?.timeframe
        || els.displayTimeframe?.value
        || "",
    ).trim();
    if (!instrumentSymbol || !displayTimeframe) {
      return null;
    }
    const params = new URLSearchParams({
      instrument_symbol: instrumentSymbol,
      display_timeframe: displayTimeframe,
    });
    const cacheKey = String(pending?.cache_key || els.cacheKey?.value || "").trim();
    const chartInstanceId = String(
      pending?.chart_instance_id || els.chartInstanceId?.value || state.snapshot?.source?.chart_instance_id || "",
    ).trim();
    const contractSymbol = String(
      pending?.target_contract_symbol || pending?.contract_symbol || state.snapshot?.instrument?.contract_symbol || "",
    ).trim().toUpperCase();
    const rootSymbol = String(
      pending?.target_root_symbol || pending?.root_symbol || state.snapshot?.instrument?.root_symbol || "",
    ).trim().toUpperCase();
    const windowStart = String(
      pending?.window_start || state.snapshot?.window_start || (els.windowStart?.value ? new Date(els.windowStart.value).toISOString() : ""),
    ).trim();
    const windowEnd = String(
      pending?.window_end || state.snapshot?.window_end || (els.windowEnd?.value ? new Date(els.windowEnd.value).toISOString() : ""),
    ).trim();
    if (cacheKey) params.set("cache_key", cacheKey);
    if (chartInstanceId) params.set("chart_instance_id", chartInstanceId);
    if (contractSymbol) params.set("contract_symbol", contractSymbol);
    if (rootSymbol) params.set("root_symbol", rootSymbol);
    if (windowStart) params.set("window_start", windowStart);
    if (windowEnd) params.set("window_end", windowEnd);
    return params;
  }

  function renderTransferProgress() {
    const progress = state.transportProgress;
    if (!progress) {
      const pendingStatus = String(state.pendingBackfill?.status || "").toLowerCase();
      if (["pending", "dispatched", "acknowledged"].includes(pendingStatus)) {
        const pendingLabelMap = {
          pending: "回补任务已排队，等待 ATAS 领取",
          dispatched: "ATAS 已领取任务，等待历史K线回传",
          acknowledged: "ATAS 已回执，后端正在核对",
        };
        transferProgressController.setProgress(
          true,
          0,
          pendingLabelMap[pendingStatus] || "ATAS 传输进度",
          state.pendingBackfill?.request_id ? `request_id=${state.pendingBackfill.request_id}` : "正在等待首批进度数据。",
        );
        return;
      }
      transferProgressController.reset();
      return;
    }
    const progressStage = String(progress.stage || "").toLowerCase();
    if (
      progressStage === "idle"
      && !progress.active
      && !progress.request
      && Number(progress.progress_percent || 0) <= 0
    ) {
      transferProgressController.reset();
      return;
    }
    transferProgressController.setProgress(
      !!progress.active,
      Number(progress.progress_percent) || 0,
      progress.label || "ATAS 传输进度",
      progress.detail || "等待 ATAS 历史数据。",
      { holdMs: progress.active ? 0 : 2200 },
    );
  }

  function shouldPollBackfillProgress() {
    const pendingStatus = String(state.pendingBackfill?.status || state.transportProgress?.status || "").toLowerCase();
    return ["pending", "dispatched", "acknowledged"].includes(pendingStatus);
  }

  function stopBackfillProgressPolling({ resetVisual = false } = {}) {
    if (backfillProgressInterval) {
      clearInterval(backfillProgressInterval);
      backfillProgressInterval = null;
    }
    backfillProgressRequestInFlight = false;
    if (resetVisual && !state.transportProgress) {
      transferProgressController.reset();
    }
  }

  async function pollBackfillProgress({ force = false } = {}) {
    if (backfillProgressRequestInFlight) {
      return;
    }
    const query = buildBackfillProgressQuery();
    if (!query) {
      if (!force) {
        state.transportProgress = null;
        renderTransferProgress();
      }
      stopBackfillProgressPolling({ resetVisual: true });
      return;
    }
    if (!force && !shouldPollBackfillProgress()) {
      renderTransferProgress();
      stopBackfillProgressPolling();
      return;
    }
    backfillProgressRequestInFlight = true;
    try {
      const response = await fetchJson(`/api/v1/workbench/backfill-progress?${query.toString()}`);
      state.transportProgress = response || null;
      if (response?.request) {
        state.pendingBackfill = response.request;
      } else if (!response?.active) {
        state.pendingBackfill = null;
      }
      renderTransferProgress();
      if (response?.active) {
        return;
      }
      stopBackfillProgressPolling();
    } catch (error) {
      console.warn("轮询 backfill progress 失败:", error);
    } finally {
      backfillProgressRequestInFlight = false;
    }
  }

  function syncBackfillProgressPolling({ force = false } = {}) {
    renderTransferProgress();
    if (force) {
      void pollBackfillProgress({ force: true });
    }
    if (!shouldPollBackfillProgress()) {
      stopBackfillProgressPolling();
      return;
    }
    if (!backfillProgressInterval) {
      backfillProgressInterval = window.setInterval(() => {
        void pollBackfillProgress();
      }, 1800);
    }
  }

  function shouldReloadSnapshotForLiveResponse(response, merged) {
    if (!response) {
      return false;
    }
    if (response.snapshot_refresh_required || response.reload_snapshot) {
      return true;
    }
    if (response.integrity_changed && !merged) {
      return true;
    }
    return false;
  }

  function shouldApplyLiveTailToSnapshot(response, timeframe) {
    if (state.followLatest) {
      return true;
    }
    const snapshotCandles = Array.isArray(state.snapshot?.candles) ? state.snapshot.candles : [];
    if (!snapshotCandles.length) {
      return true;
    }
    const latestObservedAtMs = Date.parse(response?.latest_observed_at || "");
    const snapshotLast = snapshotCandles[snapshotCandles.length - 1];
    const snapshotEdgeMs = Date.parse(
      snapshotLast?.ended_at
        || snapshotLast?.started_at
        || state.snapshot?.window_end
        || "",
    );
    if (!Number.isFinite(latestObservedAtMs) || !Number.isFinite(snapshotEdgeMs)) {
      return true;
    }
    const maxAllowedDriftMs = getTimeframeMinutes(timeframe) * 3 * 60 * 1000;
    return latestObservedAtMs - snapshotEdgeMs <= maxAllowedDriftMs;
  }

  function mergeLiveTailIntoSnapshot(response, timeframe) {
    if (!state.snapshot?.candles?.length || !response?.candles?.length) {
      return { merged: false, requiresReload: false, updateType: "full_reset" };
    }
    const preservedEventAnnotations = (Array.isArray(state.snapshot.event_annotations) ? state.snapshot.event_annotations : [])
      .filter((item) => item?.source_kind !== "collector");
    const liveEventAnnotations = Array.isArray(response.event_annotations) ? response.event_annotations : [];
    const preservedFocusRegions = (Array.isArray(state.snapshot.focus_regions) ? state.snapshot.focus_regions : [])
      .filter((item) => !(typeof item?.region_id === "string" && item.region_id.startsWith("focus-")));
    const liveFocusRegions = Array.isArray(response.focus_regions) ? response.focus_regions : [];
    const previousLiveTail = state.snapshot?.live_tail && typeof state.snapshot.live_tail === "object"
      ? state.snapshot.live_tail
      : {};
    const nextLiveTail = {
      ...previousLiveTail,
      instrument_symbol: response.instrument_symbol ?? previousLiveTail.instrument_symbol ?? state.snapshot.instrument_symbol ?? null,
      display_timeframe: response.display_timeframe ?? previousLiveTail.display_timeframe ?? state.snapshot.display_timeframe ?? null,
      latest_observed_at: response.latest_observed_at ?? previousLiveTail.latest_observed_at ?? null,
      latest_price: response.latest_price ?? previousLiveTail.latest_price ?? null,
      best_bid: response.best_bid ?? previousLiveTail.best_bid ?? null,
      best_ask: response.best_ask ?? previousLiveTail.best_ask ?? null,
      latest_price_source: response.latest_price_source ?? previousLiveTail.latest_price_source ?? null,
      best_bid_source: response.best_bid_source ?? previousLiveTail.best_bid_source ?? null,
      best_ask_source: response.best_ask_source ?? previousLiveTail.best_ask_source ?? null,
      source_message_count: response.source_message_count ?? previousLiveTail.source_message_count ?? 0,
      trade_summary: response.trade_summary ?? previousLiveTail.trade_summary ?? null,
      significant_liquidity: Array.isArray(response.significant_liquidity)
        ? response.significant_liquidity
        : (Array.isArray(previousLiveTail.significant_liquidity) ? previousLiveTail.significant_liquidity : []),
      same_price_replenishment: Array.isArray(response.same_price_replenishment)
        ? response.same_price_replenishment
        : (Array.isArray(previousLiveTail.same_price_replenishment) ? previousLiveTail.same_price_replenishment : []),
      active_initiative_drive: response.active_initiative_drive ?? previousLiveTail.active_initiative_drive ?? null,
      active_post_harvest_response: response.active_post_harvest_response ?? previousLiveTail.active_post_harvest_response ?? null,
      integrity: response.integrity ?? previousLiveTail.integrity ?? null,
    };
    const existingCandles = Array.isArray(state.snapshot.candles) ? [...state.snapshot.candles] : [];
    const incomingCandles = response.candles.filter((item) => item?.started_at);
    if (!existingCandles.length || !incomingCandles.length) {
      return { merged: false, requiresReload: false, updateType: "full_reset" };
    }
    const maxTemporalDriftMs = getTimeframeMinutes(timeframe) * 10 * 60 * 1000;
    const incomingLast = incomingCandles[incomingCandles.length - 1];
    const incomingLastEndedAtMs = new Date(incomingLast?.ended_at || incomingLast?.started_at || 0).getTime();
    const latestObservedAtMs = new Date(response.latest_observed_at || 0).getTime();
    if (
      Number.isFinite(incomingLastEndedAtMs)
      && Number.isFinite(latestObservedAtMs)
      && latestObservedAtMs - incomingLastEndedAtMs > maxTemporalDriftMs
    ) {
      console.warn("Ignoring stale live-tail candles that lag latest_observed_at", {
        timeframe,
        latest_observed_at: response.latest_observed_at,
        incoming_last_started_at: incomingLast?.started_at || null,
        incoming_last_ended_at: incomingLast?.ended_at || null,
      });
      state.snapshot = {
        ...state.snapshot,
        live_tail: nextLiveTail,
      };
      return { merged: true, requiresReload: false, updateType: "quote_only" };
    }
    const alignedIndex = existingCandles.findIndex((bar) => bar.started_at === incomingCandles[0].started_at);
    if (alignedIndex < 0) {
      const lastExisting = existingCandles[existingCandles.length - 1];
      if (!lastExisting || new Date(incomingCandles[0].started_at) <= new Date(lastExisting.started_at)) {
        const reverseDriftMs = lastExisting
          ? new Date(lastExisting.started_at).getTime() - new Date(incomingCandles[0].started_at).getTime()
          : NaN;
        if (Number.isFinite(reverseDriftMs) && reverseDriftMs > maxTemporalDriftMs) {
          console.warn("Ignoring stale live-tail candles that would rewind the current snapshot", {
            timeframe,
            snapshot_last_started_at: lastExisting?.started_at || null,
            incoming_first_started_at: incomingCandles[0]?.started_at || null,
          });
          state.snapshot = {
            ...state.snapshot,
            live_tail: nextLiveTail,
          };
          return { merged: true, requiresReload: false, updateType: "quote_only" };
        }
        return { merged: false, requiresReload: true, updateType: "full_reset" };
      }
      const seamGapMs = new Date(incomingCandles[0].started_at).getTime() - new Date(lastExisting.ended_at || lastExisting.started_at).getTime();
      const maxSeamGapMs = getTimeframeMinutes(timeframe) * 2 * 60 * 1000;
      if (Number.isFinite(seamGapMs) && seamGapMs > maxSeamGapMs) {
        return { merged: false, requiresReload: true, updateType: "full_reset" };
      }
      existingCandles.push(...incomingCandles);
    } else {
      existingCandles.splice(alignedIndex, existingCandles.length - alignedIndex, ...incomingCandles);
    }
    const deduped = [];
    const seen = new Set();
    existingCandles.forEach((bar) => {
      if (!bar?.started_at || seen.has(bar.started_at)) {
        return;
      }
      seen.add(bar.started_at);
      deduped.push(bar);
    });
    deduped.sort((left, right) => new Date(left.started_at) - new Date(right.started_at));
    const previousCandles = state.snapshot.candles;
    const previousLength = previousCandles.length;
    const previousLastSignature = buildCandleSignature(previousCandles[previousCandles.length - 1]);
    const nextCandles = sanitizeReplayCandles(
      deduped,
      { context: "live-tail-merge" },
    );
    state.snapshot = {
      ...state.snapshot,
      live_tail: nextLiveTail,
      candles: nextCandles,
      event_annotations: [...preservedEventAnnotations, ...liveEventAnnotations],
      focus_regions: [...preservedFocusRegions, ...liveFocusRegions],
      window_end: response.latest_observed_at ?? state.snapshot.window_end,
    };
    const nextLastSignature = buildCandleSignature(nextCandles[nextCandles.length - 1]);
    let updateType = "full_reset";
    if (canUseTailUpdate(previousCandles, nextCandles) && previousLastSignature !== nextLastSignature) {
      updateType = "tail_update";
    } else if (canUseAppendTail(previousCandles, nextCandles)) {
      updateType = "append_tail";
    }
    if (updateType === "append_tail" && state.chartView && state.followLatest) {
      const growth = Math.max(0, nextCandles.length - previousLength);
      if (growth > 0) {
        state.chartView = clampChartView(
          nextCandles.length,
          state.chartView.startIndex + growth,
          state.chartView.endIndex + growth,
          state.chartView,
        );
        state.chartViewportResetPending = true;
      }
    }
    return { merged: true, requiresReload: false, updateType };
  }

  function syncRelativeWindowToNow() {
    const preset = state.quickRanges.find((item) => item.value === els.quickRangeSelect?.value);
    if (preset?.days) {
      applyWindowPreset(els.displayTimeframe.value, preset.days);
      return true;
    }
    syncCacheKey();
    return false;
  }

  function startLiveRefresh() {
    if (liveRefreshInterval) {
      clearInterval(liveRefreshInterval);
    }
    liveRefreshRequestInFlight = false;
    liveRefreshInterval = setInterval(async () => {
      if (
        !state.snapshot?.candles?.length
        || state.snapshotLoading
        || state.buildInFlight
        || liveRefreshRequestInFlight
      ) {
        return;
      }
      liveRefreshRequestInFlight = true;
      try {
        const symbol = els.instrumentSymbol?.value?.trim();
        const timeframe = els.displayTimeframe?.value;
        const chartInstanceId = String(
          els.chartInstanceId?.value || state.snapshot?.source?.chart_instance_id || state.pendingBackfill?.chart_instance_id || "",
        ).trim();
        if (!symbol || !timeframe) return;

        const liveTailQuery = new URLSearchParams({
          instrument_symbol: symbol,
          display_timeframe: timeframe,
          lookback_bars: "4",
        });
        if (chartInstanceId) {
          liveTailQuery.set("chart_instance_id", chartInstanceId);
        }

        const response = await fetchJson(`/api/v1/workbench/live-tail?${liveTailQuery.toString()}`);
        const { integrityChanged } = applyLiveResponseMeta(response);
        if (!shouldApplyLiveTailToSnapshot(response, timeframe)) {
          state.topBar.lastSyncedAt = response.latest_observed_at || state.topBar.lastSyncedAt;
          updateHeaderStatus();
          return;
        }
        const mergeResult = mergeLiveTailIntoSnapshot(response, timeframe);
        const needsReload = shouldReloadSnapshotForLiveResponse(response, mergeResult.merged) || mergeResult.requiresReload;

        if (needsReload || (integrityChanged && !mergeResult.merged)) {
          const refreshed = await actions.handleFastChartRefresh({
            latestObservedAt: response.latest_observed_at || null,
            silent: true,
          });
          if (!refreshed) {
            await handleBuildWithForceRefresh({ syncRelativeWindow: !!state.followLatest, silentProgress: true });
          }
          return;
        }
        if (mergeResult.merged) {
          state.lastChartUpdateType = mergeResult.updateType;
          state.topBar.lastSyncedAt = response.latest_observed_at || new Date().toISOString();
          renderChart();
          renderSidebarSnapshot();
        }
      } catch (error) {
        console.warn("实时刷新失败:", error);
      } finally {
        liveRefreshRequestInFlight = false;
      }
    }, 5000);
  }

  function renderCoreSnapshot() {
    const startedAt = performance.now();
    renderChart();
    updateDynamicAnalysisVisibility();
    updateHeaderStatus();
    state.perf.coreRenderMs = Math.round(performance.now() - startedAt);
    if (state.snapshot?.candles?.length) {
      startLiveRefresh();
    }
  }

  function renderViewportDerivedSurfaces() {
    renderDrawers({ state, els });
    updateHeaderStatus();
  }

  function renderSidebarSnapshot() {
    const startedAt = performance.now();
    renderViewportDerivedSurfaces();
    updateDynamicAnalysisVisibility();
    state.perf.sidebarRenderMs = Math.round(performance.now() - startedAt);
  }

  function renderAiSurface() {
    renderAiThreadTabs();
    renderAiChat();
    eventPanelController?.decorateChatMessages();
    eventPanelController?.renderEventPanel();
    eventOutcomeController?.renderOutcomeSurfaces();
    renderEventScribePanel();
    renderReplyExtractionPanel();
    renderContractNav();
  }

  function renderAnnotationSurface({ skipLifecycle = false } = {}) {
    if (!skipLifecycle) {
      queueAnnotationLifecycleRefresh({ delay: 1200, refreshMemory: true, forceServer: true });
      return;
    }
    annotationPanelController.renderAnnotationPanel();
  }

  function renderDeferredSurfaces() {
    renderAiSurface();
    renderAnnotationSurface({ skipLifecycle: false });
  }

  function renderSnapshot() {
    renderCoreSnapshot();
    renderSidebarSnapshot();
    renderDeferredSurfaces();
    manualEventTools?.updateToolbarUi?.();
  }

  async function runBuildFlow({ forceRefresh = false, syncRelativeWindow = false, silentProgress = false } = {}) {
    const previous = !!els.forceRebuild?.checked;
    const previousSilentBuildProgress = !!state.silentBuildProgress;
    state.silentBuildProgress = !!silentProgress;
    if (state.silentBuildProgress) {
      buildProgressController.reset();
    }
    rememberCurrentChartView(state.snapshot, { persist: false });
    if (syncRelativeWindow) {
      syncRelativeWindowToNow();
    }
    if (els.forceRebuild) {
      els.forceRebuild.checked = !!forceRefresh;
    }
    try {
      await actions.handleBuild();
      state.topBar.lastSyncedAt = new Date().toISOString();
      syncBackfillProgressPolling({ force: true });
      persistWorkbenchState();
      renderAiSurface();
    } finally {
      state.silentBuildProgress = previousSilentBuildProgress;
      if (els.forceRebuild) {
        els.forceRebuild.checked = previous;
      }
    }
  }

  async function handleBuildWithForceRefresh({ syncRelativeWindow = true, silentProgress = false } = {}) {
    await runBuildFlow({ forceRefresh: true, syncRelativeWindow, silentProgress });
  }

  async function loadGammaAnalysis({ autoDiscoverLatest = false } = {}) {
    const gamma = state.optionsGamma;
    gamma.loading = true;
    gamma.error = null;
    if (els.gammaCsvPath && els.gammaCsvPath.value.trim()) {
      gamma.sourceCsvPath = els.gammaCsvPath.value.trim();
    }
    renderSnapshot();
    try {
      if (autoDiscoverLatest) {
        const latest = await fetchJson(`/api/v1/options/latest-csv?symbol=${encodeURIComponent(gamma.requestedSymbol || "SPX")}`);
        gamma.sourceCsvPath = latest.csv_path || "";
        gamma.discoveredAt = new Date().toISOString();
        if (els.gammaCsvPath) {
          els.gammaCsvPath.value = gamma.sourceCsvPath;
        }
      }
      const response = await fetchJson("/api/v1/options/gamma-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: gamma.requestedSymbol || "SPX",
          trade_date: gamma.requestedTradeDate,
          csv_path: gamma.sourceCsvPath || null,
          auto_discover_latest: !gamma.sourceCsvPath,
          include_ai_analysis: true,
          persist_artifacts: false,
        }),
      });
      gamma.summary = response.summary || null;
      gamma.textReport = response.text_report || "";
      gamma.artifacts = response.artifacts || null;
      gamma.aiInterpretation = response.ai_interpretation || "";
      gamma.aiAnalysisError = response.ai_analysis_error || null;
      gamma.sourceCsvPath = response.source?.csv_path || gamma.sourceCsvPath || "";
      gamma.lastLoadedAt = response.generated_at || new Date().toISOString();
      renderStatusStrip([{ label: "Gamma 已加载", variant: "good" }]);
    } catch (error) {
      gamma.error = error.message || String(error);
      renderStatusStrip([{ label: gamma.error, variant: "warn" }]);
    } finally {
      gamma.loading = false;
      renderSnapshot();
    }
  }

  function buildGammaPromptText() {
    const gamma = state.optionsGamma;
    if (!gamma?.summary) {
      throw new Error("还没有可发送的 Gamma 分析。");
    }
    const parts = [
      `以下是当前期权 Gamma 分析背景，请结合它回答后续问题。`,
      `来源 CSV: ${gamma.sourceCsvPath || gamma.summary.source_file || "-"}`,
      gamma.summary.quote_time ? `报价时间: ${gamma.summary.quote_time}` : "",
      gamma.summary.regime ? `Gamma 环境: ${gamma.summary.regime}` : "",
      gamma.summary.zero_gamma_proxy_es != null ? `Zero Gamma ES: ${gamma.summary.zero_gamma_proxy_es}` : "",
      gamma.textReport ? `\nSummary:\n${gamma.textReport}` : "",
      gamma.aiInterpretation ? `\nAI 解读:\n${gamma.aiInterpretation}` : "",
    ].filter(Boolean);
    return parts.join("\n");
  }

  async function sendGammaToChat(createNew = false) {
    const prompt = buildGammaPromptText();
    if (createNew) {
      await aiChat.handlePresetAnalysis("general", prompt, true);
      return;
    }
    els.aiChatInput.value = prompt;
    await aiChat.handleAiChatSend();
  }

  function resetAnnotationFilters() {
    state.annotationFilters = createDefaultAnnotationFilters();
    writeStorage("annotationFilters", state.annotationFilters);
    renderSnapshot();
  }


  function toggleAiSidebar() {
    if (isDockedAiLayout()) {
      openAiSidebar();
      return;
    }
    const isOpen = els.aiSidebar?.classList.contains("open");
    if (isOpen) {
      closeAiSidebar();
    } else {
      openAiSidebar();
    }
  }

  function openAiSidebar() {
    if (!els.aiSidebar) return;
    state.aiSidebarOpen = true;
    syncAiSidebarViewportState();
  }

  function closeAiSidebar() {
    if (!els.aiSidebar) return;
    if (isDockedAiLayout()) {
      openAiSidebar();
      return;
    }
    state.aiSidebarOpen = false;
    syncAiSidebarViewportState();
  }

  function getLatestAssistantMessage(session) {
    return [...(session?.messages || [])].reverse().find((item) => item.role === "assistant" && String(item.content || "").trim()) || null;
  }

  function getStructuredReplyMessageIds(session) {
    const sessionId = session?.id || null;
    const ids = new Set();
    (session?.messages || []).forEach((message) => {
      if (message?.role !== "assistant") {
        return;
      }
      const structuredCount = [
        ...(Array.isArray(message.annotations) ? message.annotations : []),
        ...(Array.isArray(message.planCards) ? message.planCards : []),
        ...(Array.isArray(message.meta?.annotations) ? message.meta.annotations : []),
        ...(Array.isArray(message.meta?.planCards) ? message.meta.planCards : []),
      ].length;
      if (structuredCount > 0 && message.message_id) {
        ids.add(message.message_id);
      }
    });
    (state.aiAnnotations || []).forEach((annotation) => {
      if (sessionId && annotation.session_id !== sessionId) {
        return;
      }
      if (annotation.message_id) {
        ids.add(annotation.message_id);
      }
      if (annotation.source_message_id) {
        ids.add(annotation.source_message_id);
      }
    });
    return ids;
  }

  function hasStructuredReplyContent(session) {
    return getStructuredReplyMessageIds(session).size > 0;
  }

  function getLatestUserMessage(session) {
    return [...(session?.messages || [])].reverse().find((item) => item.role === "user" && String(item.content || "").trim()) || null;
  }

  function buildSecondaryMessageMarkup(message) {
    const role = message?.role === "assistant" ? "assistant" : "user";
    const title = role === "assistant"
      ? (message?.replyTitle || message?.meta?.replyTitle || "事件判断")
      : "你";
    return `
      <article class="secondary-chat-message ${role}" data-secondary-message-id="${escapeHtml(message?.message_id || "")}">
        <div class="secondary-chat-head">
          <strong>${escapeHtml(title)}</strong>
          <span class="meta">${escapeHtml(role === "assistant" ? "Event Scribe AI" : "用户")}</span>
        </div>
        <div class="secondary-chat-body">${escapeHtml(String(message?.content || "").trim() || (role === "assistant" ? "事件整理中…" : ""))}</div>
      </article>
    `;
  }

  function isCandidateTemporalOrMetricNumber(content, startIndex, rawValue) {
    const before = content.slice(Math.max(0, startIndex - 8), startIndex);
    const after = content.slice(startIndex + rawValue.length, Math.min(content.length, startIndex + rawValue.length + 10));
    const around = `${before}${rawValue}${after}`;
    const numeric = Number(rawValue);
    if (/[:：]\d{1,2}\s*$/.test(before) || /^\s*[:：/]\d/.test(after)) {
      return true;
    }
    if (/[年月日号周点时分秒]\s*$/.test(before) || /^\s*[年月日号周点时分秒]/.test(after)) {
      return true;
    }
    if (/^\s*(?:条|根|笔|分钟|小时|天|周|月|年|倍|手|次|tick|ticks|%|％)/i.test(after)) {
      return true;
    }
    if (numeric >= 1900 && numeric <= 2100 && /[年月日]|UTC|GMT/.test(around)) {
      return true;
    }
    return false;
  }

  function formatReplyCandidateNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(2) : "";
  }

  function getReplyCandidateTone(item = {}) {
    const text = `${item.label || ""} ${item.excerpt || ""}`;
    if (/支撑|需求|回踩|接多|做多|多头/.test(text)) {
      return "bull";
    }
    if (/阻力|压力|供给|反抽|做空|空头/.test(text)) {
      return "bear";
    }
    if (/风险|失效|止损|不能追|不要追|谨慎|放弃/.test(text)) {
      return "risk";
    }
    return "neutral";
  }

  function getReplyCandidateDedupKey(item = {}) {
    const tone = getReplyCandidateTone(item);
    if (item.type === "zone" && Number.isFinite(item.priceLow) && Number.isFinite(item.priceHigh)) {
      return `zone:${formatReplyCandidateNumber(item.priceLow)}:${formatReplyCandidateNumber(item.priceHigh)}:${tone}`;
    }
    if (Number.isFinite(item.price)) {
      return `${item.type}:${formatReplyCandidateNumber(item.price)}:${tone}`;
    }
    const labelKey = String(item.label || "").trim().toLowerCase();
    return `${item.type}:${tone}:${labelKey}`;
  }

  function getReplyCandidateSourcePriority(item = {}) {
    const stableKey = String(item.stableKey || "");
    if (stableKey.startsWith("annotation:")) {
      return 0;
    }
    if (item.sourceRole === "scribe") {
      return 1;
    }
    if (item.sourceRole === "analyst") {
      return 2;
    }
    return 3;
  }

  function shouldReplaceReplyCandidate(existing, incoming) {
    if (!existing) {
      return true;
    }
    const existingPriority = getReplyCandidateSourcePriority(existing);
    const incomingPriority = getReplyCandidateSourcePriority(incoming);
    if (incomingPriority !== existingPriority) {
      return incomingPriority < existingPriority;
    }
    const existingTime = Date.parse(existing.observedAt || "") || 0;
    const incomingTime = Date.parse(incoming.observedAt || "") || 0;
    if (incomingTime !== existingTime) {
      return incomingTime > existingTime;
    }
    return String(incoming.excerpt || "").length > String(existing.excerpt || "").length;
  }

  function sortReplyCandidates(items = []) {
    const typeOrder = { plan: 0, zone: 1, risk: 2, price: 3 };
    return [...items].sort((left, right) => {
      if (left.ignored !== right.ignored) {
        return left.ignored ? 1 : -1;
      }
      if ((left.pinned || false) !== (right.pinned || false)) {
        return left.pinned ? -1 : 1;
      }
      const leftTypeOrder = typeOrder[left.type] ?? 9;
      const rightTypeOrder = typeOrder[right.type] ?? 9;
      if (leftTypeOrder !== rightTypeOrder) {
        return leftTypeOrder - rightTypeOrder;
      }
      const leftSourcePriority = getReplyCandidateSourcePriority(left);
      const rightSourcePriority = getReplyCandidateSourcePriority(right);
      if (leftSourcePriority !== rightSourcePriority) {
        return leftSourcePriority - rightSourcePriority;
      }
      const rightTime = Date.parse(right.observedAt || "") || 0;
      const leftTime = Date.parse(left.observedAt || "") || 0;
      if (rightTime !== leftTime) {
        return rightTime - leftTime;
      }
      const rightPrice = Number.isFinite(right.price) ? right.price : (Number.isFinite(right.priceHigh) ? right.priceHigh : -Infinity);
      const leftPrice = Number.isFinite(left.price) ? left.price : (Number.isFinite(left.priceHigh) ? left.priceHigh : -Infinity);
      return rightPrice - leftPrice;
    });
  }

  function getReplyCandidatePriceMetrics(item = {}) {
    const directPrice = Number(item.price);
    const low = Number(item.priceLow);
    const high = Number(item.priceHigh);
    if (Number.isFinite(low) && Number.isFinite(high)) {
      const min = Math.min(low, high);
      const max = Math.max(low, high);
      return { min, max, midpoint: (min + max) / 2 };
    }
    if (Number.isFinite(directPrice)) {
      return { min: directPrice, max: directPrice, midpoint: directPrice };
    }
    return { min: null, max: null, midpoint: null };
  }

  function getChartEventClusterPriceMetrics(cluster = {}) {
    const values = (Array.isArray(cluster?.items) ? cluster.items : [])
      .flatMap((item) => [item.price, item.priceLow, item.priceHigh])
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value));
    if (!values.length) {
      return { min: null, max: null, midpoint: null };
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { min, max, midpoint: (min + max) / 2 };
  }

  function getPriceRangeDistance(minA, maxA, minB, maxB) {
    if (![minA, maxA, minB, maxB].every((value) => Number.isFinite(value))) {
      return null;
    }
    if (maxA >= minB && maxB >= minA) {
      return 0;
    }
    if (maxA < minB) {
      return minB - maxA;
    }
    return minA - maxB;
  }

  function buildReplyCandidateHoverItemFromCluster(cluster = null) {
    if (!cluster?.items?.length) {
      return null;
    }
    const prices = cluster.items
      .flatMap((item) => [item.price, item.priceLow, item.priceHigh])
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value));
    const primaryItem = cluster.items[0] || {};
    const detailText = [
      cluster.notePreviewText,
      primaryItem.metaText,
      cluster.priceText,
    ].filter(Boolean).join(" · ");
    return {
      id: cluster.key,
      category: cluster.dominantCategory || primaryItem.category || "events",
      title: cluster.summaryText || primaryItem.shortLabel || "事件",
      observedAt: primaryItem.observedAt || (cluster.time ? cluster.time * 1000 : null),
      price: prices.length ? prices[0] : null,
      priceLow: prices.length ? Math.min(...prices) : null,
      priceHigh: prices.length ? Math.max(...prices) : null,
      timeLabel: cluster.timeLabel || "--",
      priceText: cluster.priceText || "价格未知",
      detailText: detailText || "关键盘口事件",
    };
  }

  function buildReplyCandidateClusterLink(item = {}, chartEventModel = state.chartEventModel) {
    const clusterIndex = chartEventModel?.clusterIndex || {};
    const manualCluster = item?.linkedClusterKey ? clusterIndex[item.linkedClusterKey] : null;
    if (manualCluster) {
      return {
        cluster: manualCluster,
        score: 999,
        priceMatched: true,
        timeMatched: true,
        reason: "manual",
      };
    }
    const clusters = Array.isArray(chartEventModel?.clusters) ? chartEventModel.clusters : [];
    if (!clusters.length) {
      return null;
    }

    const candidatePrice = getReplyCandidatePriceMetrics(item);
    const observedAtMs = Date.parse(item?.observedAt || "");
    let best = null;

    clusters.forEach((cluster) => {
      let score = 0;
      let priceMatched = false;
      let timeMatched = false;
      const clusterPrice = getChartEventClusterPriceMetrics(cluster);
      const rangeDistance = getPriceRangeDistance(
        candidatePrice.min,
        candidatePrice.max,
        clusterPrice.min,
        clusterPrice.max,
      );
      if (rangeDistance === 0) {
        score += item.type === "zone" ? 120 : 104;
        priceMatched = true;
      } else if (Number.isFinite(rangeDistance)) {
        const referencePrice = Math.abs(candidatePrice.midpoint || clusterPrice.midpoint || 0);
        const tolerance = Math.max(4, referencePrice * 0.0006);
        const normalizedDistance = rangeDistance / tolerance;
        if (normalizedDistance <= 2.5) {
          score += Math.max(0, 92 - normalizedDistance * 28);
          priceMatched = true;
        }
      }

      if (Number.isFinite(observedAtMs)) {
        const diffSeconds = Math.abs(Math.round(observedAtMs / 1000) - Number(cluster.time || 0));
        if (diffSeconds <= 15 * 60) {
          score += 36;
          timeMatched = true;
        } else if (diffSeconds <= 60 * 60) {
          score += 24;
          timeMatched = true;
        } else if (diffSeconds <= 6 * 60 * 60) {
          score += 12;
          timeMatched = true;
        } else if (diffSeconds <= 24 * 60 * 60) {
          score += 6;
        }
      }

      if (item.type === "risk" && cluster.dominantCategory === "trapped") {
        score += 18;
      } else if (item.type === "zone" && ["events", "absorption", "largeOrders", "replenishment", "trapped"].includes(cluster.dominantCategory)) {
        score += 10;
      } else if (item.type === "plan" && ["events", "absorption", "largeOrders", "replenishment"].includes(cluster.dominantCategory)) {
        score += 8;
      } else if (item.type === "price") {
        score += 4;
      }

      if (!priceMatched && !timeMatched) {
        return;
      }
      if (!best || score > best.score) {
        best = {
          cluster,
          score,
          priceMatched,
          timeMatched,
          reason: priceMatched ? "price" : "time",
        };
      }
    });

    if (!best || best.score < 28) {
      return null;
    }
    return best;
  }

  function attachReplyCandidateEventLinks(items = [], chartEventModel = state.chartEventModel) {
    return (Array.isArray(items) ? items : []).map((item) => {
      const link = buildReplyCandidateClusterLink(item, chartEventModel);
      if (!link?.cluster) {
        return {
          ...item,
          linkedClusterKey: null,
          linkedClusterTimeLabel: "",
          linkedClusterSummary: "",
          linkedClusterPriceText: "",
          linkedClusterScore: 0,
          linkedClusterReason: "",
        };
      }
      return {
        ...item,
        linkedClusterKey: link.cluster.key,
        linkedClusterTimeLabel: link.cluster.timeLabel || "--",
        linkedClusterSummary: link.cluster.summaryText || "事件",
        linkedClusterPriceText: link.cluster.priceText || "价格未知",
        linkedClusterScore: link.score,
        linkedClusterReason: link.reason || "",
      };
    });
  }

  function applyReplyExtractionRuntimeFilters(items = [], extractionState = getReplyExtractionState()) {
    const intensity = extractionState?.intensity || "balanced";
    const autoExtractEnabled = extractionState?.autoExtractEnabled !== false;
    let filtered = Array.isArray(items) ? [...items] : [];
    if (!autoExtractEnabled) {
      filtered = filtered.filter((item) => String(item?.stableKey || "").startsWith("annotation:"));
    }
    if (intensity === "strict") {
      filtered = filtered.filter((item) => item?.type !== "price");
    }
    if (intensity === "aggressive") {
      filtered = sortReplyCandidates(filtered);
      return filtered.slice(0, 60);
    }
    return filtered;
  }

  function isPendingReplyExtractionItem(item = {}) {
    return ["candidate", "confirmed"].includes(item?.status || "candidate");
  }

  function getFilteredReplyExtractionItems(allItems = [], extractionState = getReplyExtractionState()) {
    const filter = extractionState.filter || "all";
    const showIgnored = !!extractionState.showIgnored;
    const pendingOnly = !!extractionState.pendingOnly;
    return allItems.filter((item) => {
      if (!showIgnored && item.ignored) {
        return false;
      }
      if (pendingOnly && !isPendingReplyExtractionItem(item)) {
        return false;
      }
      return filter === "all" ? true : item.type === filter;
    });
  }

  function buildReplyExtractionClusterSummaryMap(items = []) {
    const summaryByCluster = {};
    (Array.isArray(items) ? items : [])
      .filter((item) => item?.linkedClusterKey && !item?.ignored)
      .forEach((item) => {
        const key = item.linkedClusterKey;
        if (!summaryByCluster[key]) {
          summaryByCluster[key] = {
            total: 0,
            plan: 0,
            zone: 0,
            risk: 0,
            price: 0,
            pending: 0,
            labels: [],
          };
        }
        const bucket = summaryByCluster[key];
        bucket.total += 1;
        bucket[item.type] = (bucket[item.type] || 0) + 1;
        if (isPendingReplyExtractionItem(item)) {
          bucket.pending += 1;
        }
        if (item.label && !bucket.labels.includes(item.label) && bucket.labels.length < 2) {
          bucket.labels.push(item.label);
        }
      });
    return summaryByCluster;
  }

  function getReplyExtractionClusterSummaryMap() {
    const extractionState = getReplyExtractionState();
    const items = applyReplyExtractionRuntimeFilters(buildReplyExtractionItems(), extractionState);
    return buildReplyExtractionClusterSummaryMap(items);
  }

  function getVisibleReplyExtractionItems() {
    const extractionState = getReplyExtractionState();
    const allItems = applyReplyExtractionRuntimeFilters(buildReplyExtractionItems(), extractionState);
    return getFilteredReplyExtractionItems(allItems, extractionState);
  }

  function buildReplyExtractionExportText(items = [], {
    extractionState = getReplyExtractionState(),
    totalCount = items.length,
    symbol = null,
  } = {}) {
    const resolvedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const filterLabelMap = {
      all: "全部",
      plan: "行动",
      zone: "区域",
      risk: "风险",
      price: "价位",
    };
    const intensityLabelMap = {
      strict: "严格",
      balanced: "平衡",
      aggressive: "激进",
    };
    const typeLabelMap = {
      plan: "行动计划",
      zone: "关键区域",
      risk: "风险提醒",
      price: "补充价位",
    };
    const statusLabelMap = {
      candidate: "候选",
      confirmed: "已确认",
      mounted: "已上图",
      promoted_annotation: "已上图",
      promoted_plan: "已转计划",
      ignored: "已忽略",
    };
    const lines = [
      `# ${resolvedSymbol} 事件整理摘要`,
      "",
      `- 导出时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
      `- 记录强度：${intensityLabelMap[extractionState.intensity] || extractionState.intensity || "平衡"}`,
      `- 类型筛选：${filterLabelMap[extractionState.filter] || "全部"}`,
      `- 视图模式：${extractionState.pendingOnly ? "仅看未处理" : extractionState.showIgnored ? "查看全部历史" : "当前候选"}`,
      `- 可见条目：${items.length} / ${totalCount}`,
      "",
    ];
    if (!items.length) {
      lines.push("当前筛选下暂无可导出的事件。");
      return lines.join("\n");
    }
    ["plan", "zone", "risk", "price"].forEach((type) => {
      const groupItems = items.filter((item) => item.type === type);
      if (!groupItems.length) {
        return;
      }
      lines.push(`## ${typeLabelMap[type] || "候选"}（${groupItems.length}）`);
      lines.push("");
      groupItems.forEach((item, index) => {
        const priceText = type === "zone"
          ? `${item.priceLow?.toFixed?.(2) ?? item.priceLow} - ${item.priceHigh?.toFixed?.(2) ?? item.priceHigh}`
          : (item.price != null ? `${item.price?.toFixed?.(2) ?? item.price}` : "未定位价格");
        const sourceText = [item.sourceActor || "AI", formatCompactLocalDateTime(item.observedAt)].filter(Boolean).join(" · ");
        lines.push(`${index + 1}. ${item.label || "候选事件"} | ${priceText} | ${statusLabelMap[item.status] || "候选"}`);
        if (item.excerpt) {
          lines.push(`   ${item.excerpt}`);
        }
        if (sourceText) {
          lines.push(`   来源：${sourceText}`);
        }
        if (item.sourceTitle) {
          lines.push(`   话题：${item.sourceTitle}`);
        }
      });
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  function exportReplyExtractionSummary() {
    const extractionState = getReplyExtractionState();
    const allItems = applyReplyExtractionRuntimeFilters(buildReplyExtractionItems(), extractionState);
    const visibleItems = getFilteredReplyExtractionItems(allItems, extractionState);
    if (!visibleItems.length) {
      renderStatusStrip([{ label: "当前筛选下没有可导出的事件摘要。", variant: "warn" }]);
      return;
    }
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const content = buildReplyExtractionExportText(visibleItems, {
      extractionState,
      totalCount: allItems.length,
      symbol,
    });
    const timestamp = new Date().toISOString().replace(/[:]/g, "-").replace(/\..+$/, "");
    const filename = `${symbol.toLowerCase()}-reply-events-${timestamp}.md`;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(content)
        .then(() => {
          renderStatusStrip([{ label: `已导出并复制事件摘要：${filename}`, variant: "good" }]);
        })
        .catch(() => {
          renderStatusStrip([{ label: `已导出事件摘要：${filename}`, variant: "good" }]);
        });
      return;
    }
    renderStatusStrip([{ label: `已导出事件摘要：${filename}`, variant: "good" }]);
  }

  function inferCandidateSide(item = {}) {
    const text = `${item.label || ""} ${item.excerpt || ""}`;
    if (/阻力|压力|供给|做空|空头|反抽/.test(text)) {
      return "sell";
    }
    if (/支撑|需求|做多|多头|回踩/.test(text)) {
      return "buy";
    }
    return "buy";
  }

  function resolveCandidateSession(item = {}) {
    const symbol = String(state.topBar?.symbol || item.symbol || "NQ").trim().toUpperCase() || "NQ";
    const analystSession = getSessionByRole(symbol, "analyst");
    if (analystSession) {
      return analystSession;
    }
    if (item.sessionId) {
      const sourceSession = state.aiThreads.find((entry) => entry.id === item.sessionId);
      if (sourceSession) {
        return sourceSession;
      }
    }
    return getActiveThread();
  }

  function findPromotedAnnotationByCandidate(candidate = {}, sessionId = null) {
    const candidateKey = getReplyCandidateKey(candidate);
    if (!candidateKey) {
      return null;
    }
    const annotations = Array.isArray(state.aiAnnotations) ? state.aiAnnotations : [];
    const byKey = annotations.find((annotation) => annotation.source_event_key === candidateKey && (!sessionId || annotation.session_id === sessionId));
    if (byKey) {
      return byKey;
    }
    const stableKey = String(candidate.stableKey || "");
    if (stableKey.startsWith("annotation:")) {
      const annotationId = stableKey.slice("annotation:".length);
      return annotations.find((annotation) => annotation.id === annotationId) || null;
    }
    return null;
  }

  function buildAnnotationFromCandidate(candidate = {}, session = null) {
    const targetSession = session || resolveCandidateSession(candidate);
    const symbol = String(targetSession?.symbol || targetSession?.contractId || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const timeframe = targetSession?.timeframe || state.topBar?.timeframe || "1m";
    const startTime = state.snapshot?.window_start || new Date().toISOString();
    const endTime = state.snapshot?.window_end || new Date().toISOString();
    const latestClose = state.snapshot?.candles?.[state.snapshot.candles.length - 1]?.close ?? null;
    const basePrice = Number.isFinite(candidate.price) ? candidate.price : (Number.isFinite(latestClose) ? latestClose : null);
    const side = inferCandidateSide(candidate);
    const reason = String(candidate.excerpt || candidate.label || "来自事件整理候选").trim();
    const candidateKey = getReplyCandidateKey(candidate);
    let type = "entry_line";
    let entryPrice = null;
    let stopPrice = null;
    let targetPrice = null;
    let priceLow = null;
    let priceHigh = null;
    let tpLevel = null;
    if (candidate.type === "zone") {
      const hasRange = Number.isFinite(candidate.priceLow) && Number.isFinite(candidate.priceHigh);
      const halfRange = 6;
      priceLow = hasRange ? Math.min(candidate.priceLow, candidate.priceHigh) : (Number.isFinite(basePrice) ? basePrice - halfRange : null);
      priceHigh = hasRange ? Math.max(candidate.priceLow, candidate.priceHigh) : (Number.isFinite(basePrice) ? basePrice + halfRange : null);
      if (/no[-_ ]?trade|风险|失效|谨慎/i.test(`${candidate.label || ""} ${candidate.excerpt || ""}`)) {
        type = "no_trade_zone";
      } else if (/阻力|压力|供给|空头/.test(`${candidate.label || ""} ${candidate.excerpt || ""}`)) {
        type = "resistance_zone";
      } else {
        type = "support_zone";
      }
    } else if (candidate.type === "risk") {
      type = "no_trade_zone";
      if (Number.isFinite(basePrice)) {
        priceLow = basePrice - 6;
        priceHigh = basePrice + 6;
      }
    } else if (/止损|风险|失效/.test(candidate.label || "")) {
      type = "stop_loss";
      stopPrice = basePrice;
    } else if (/止盈|目标|TP/i.test(candidate.label || "")) {
      type = "take_profit";
      targetPrice = basePrice;
      tpLevel = 1;
    } else {
      type = "entry_line";
      entryPrice = basePrice;
    }
    if (["entry_line", "stop_loss", "take_profit"].includes(type) && !Number.isFinite(entryPrice) && !Number.isFinite(stopPrice) && !Number.isFinite(targetPrice)) {
      return null;
    }
    if (["support_zone", "resistance_zone", "no_trade_zone"].includes(type) && (!Number.isFinite(priceLow) || !Number.isFinite(priceHigh))) {
      return null;
    }
    return normalizeWorkbenchAnnotation({
      id: `ann-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      annotation_id: null,
      object_id: null,
      session_id: targetSession.id,
      message_id: candidate.messageId || targetSession.messages?.[targetSession.messages.length - 1]?.message_id || null,
      source_message_id: candidate.messageId || null,
      plan_id: null,
      symbol,
      timeframe,
      type,
      subtype: null,
      label: candidate.label || (type === "entry_line" ? "候选入场" : "候选标记"),
      reason,
      start_time: startTime,
      end_time: endTime,
      expires_at: candidate.expiresAt || candidate.expires_at || null,
      status: "active",
      priority: candidate.priority ?? null,
      confidence: candidate.confidence ?? null,
      visible: true,
      pinned: false,
      source_kind: "event_candidate",
      source_event_key: candidateKey,
      event_kind: candidate.type || null,
      source_reply_title: candidate.replyTitle || candidate.sourceReplyTitle || null,
      side,
      entry_price: Number.isFinite(entryPrice) ? entryPrice : null,
      stop_price: Number.isFinite(stopPrice) ? stopPrice : null,
      target_price: Number.isFinite(targetPrice) ? targetPrice : null,
      tp_level: Number.isFinite(tpLevel) ? tpLevel : null,
      price_low: Number.isFinite(priceLow) ? priceLow : null,
      price_high: Number.isFinite(priceHigh) ? priceHigh : null,
      path_points: [],
    }, {
      session: targetSession,
      messageId: candidate.messageId || targetSession.messages?.[targetSession.messages.length - 1]?.message_id || null,
      state,
      defaultSourceKind: "event_candidate",
      sourceReplyTitle: candidate.replyTitle || candidate.sourceReplyTitle || null,
    });
  }

  function promoteCandidateToAnnotation(candidate = {}) {
    const targetSession = resolveCandidateSession(candidate);
    const existing = findPromotedAnnotationByCandidate(candidate, targetSession?.id);
    if (existing) {
      existing.visible = true;
      existing.updated_at = new Date().toISOString();
      return { annotation: existing, created: false, session: targetSession };
    }
    const annotation = buildAnnotationFromCandidate(candidate, targetSession);
    if (!annotation) {
      return { annotation: null, created: false, session: targetSession };
    }
    state.aiAnnotations = [...(state.aiAnnotations || []), annotation];
    return { annotation, created: true, session: targetSession };
  }

  function buildPlanCardFromCandidate(candidate = {}) {
    const targetSession = resolveCandidateSession(candidate);
    const side = inferCandidateSide(candidate);
    const latestClose = state.snapshot?.candles?.[state.snapshot.candles.length - 1]?.close ?? null;
    const midpoint = Number.isFinite(candidate.priceLow) && Number.isFinite(candidate.priceHigh)
      ? (candidate.priceLow + candidate.priceHigh) / 2
      : null;
    const entryPrice = Number.isFinite(candidate.price) ? candidate.price : (Number.isFinite(midpoint) ? midpoint : latestClose);
    if (!Number.isFinite(entryPrice)) {
      return { planCard: null, message: null, session: targetSession };
    }
    const stopOffset = 8;
    const tpOffset = 14;
    const stopPrice = side === "sell" ? entryPrice + stopOffset : entryPrice - stopOffset;
    const tp1 = side === "sell" ? entryPrice - tpOffset : entryPrice + tpOffset;
    const tp2 = side === "sell" ? entryPrice - tpOffset * 2 : entryPrice + tpOffset * 2;
    const planRaw = {
      id: createPlanId(),
      title: candidate.type === "plan"
        ? (candidate.label || `候选计划 ${entryPrice.toFixed(2)}`)
        : `${side === "sell" ? "空头" : "多头"}候选计划 ${entryPrice.toFixed(2)}`,
      status: "active",
      side,
      entryPrice,
      entryPriceLow: Number.isFinite(candidate.priceLow) ? Math.min(candidate.priceLow, candidate.priceHigh ?? candidate.priceLow) : null,
      entryPriceHigh: Number.isFinite(candidate.priceHigh) ? Math.max(candidate.priceLow ?? candidate.priceHigh, candidate.priceHigh) : null,
      stopPrice,
      targetPrice: tp1,
      targetPrice2: tp2,
      take_profits: [
        { id: "1", tp_level: 1, target_price: tp1 },
        { id: "2", tp_level: 2, target_price: tp2 },
      ],
      message_id: candidate.messageId || null,
      session_id: targetSession.id,
      source_kind: "event_candidate",
      confidence: candidate.confidence ?? null,
      priority: candidate.priority ?? null,
      summary: summarizeText(candidate.excerpt || candidate.label || "来自事件整理候选", 120),
      notes: candidate.excerpt || candidate.label || "来自事件整理候选",
    };
    const planCard = upsertPlanCardToSession(planRaw, targetSession.id, null);
    const message = appendAiChatMessage(
      "assistant",
      `已将候选事件转为计划卡：${planCard.title}`,
      {
        status: "completed",
        replyTitle: "候选事件处理",
        session_only: true,
        planCards: [planCard],
        source_message_id: candidate.messageId || null,
        event_candidate_key: getReplyCandidateKey(candidate),
      },
      targetSession.id,
      targetSession.title,
    );
    const planInMessage = message?.meta?.planCards?.[0] || null;
    if (planInMessage) {
      planInMessage.message_id = message.message_id;
      planInMessage.session_id = targetSession.id;
      message.planCards = [planInMessage];
      message.meta.planCards = [planInMessage];
    }
    targetSession.activePlanId = planCard.id || planCard.plan_id || null;
    persistSessions();
    return { planCard: planInMessage || planCard, message, session: targetSession };
  }

  function extractReplyCandidatesFromText(text, meta = {}) {
    const content = String(text || "").trim();
    if (!content) {
      return [];
    }
    const items = [];
    const seen = new Set();
    const priceValues = [];
    const pushItem = (item) => {
      if (!item) {
        return;
      }
      const key = item.stableKey || `${item.type}:${item.price ?? ""}:${item.priceLow ?? ""}:${item.priceHigh ?? ""}:${item.sessionId ?? ""}:${item.messageId ?? ""}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      items.push(item);
    };
    const messageScopeId = meta.messageId || meta.sessionId || "msg";
    const sourceRole = meta.sourceRole || "analyst";
    const sourceActor = meta.sourceActor || (sourceRole === "scribe" ? "事件判断 AI" : "行情分析 AI");
    const sourceTitle = meta.sourceTitle || "AI 提取";
    const observedAt = meta.observedAt || null;
    const sourceKind = meta.sourceKind || "text_fallback";
    const summary = summarizeText(content, 120);
    const rangeRegex = /(\d{3,6}(?:\.\d+)?)[\s]*(?:-|~|到|至)[\s]*(\d{3,6}(?:\.\d+)?)/g;
    const rangeSpans = [];
    let rangeMatch;
    while ((rangeMatch = rangeRegex.exec(content)) !== null) {
      const low = Number(rangeMatch[1]);
      const high = Number(rangeMatch[2]);
      if (!Number.isFinite(low) || !Number.isFinite(high)) {
        continue;
      }
      rangeSpans.push([rangeMatch.index, rangeRegex.lastIndex]);
      const priceLow = Math.min(low, high);
      const priceHigh = Math.max(low, high);
      pushItem({
        id: `${meta.messageId || meta.sessionId || "msg"}-zone-${rangeMatch.index}-${priceLow}-${priceHigh}`,
        stableKey: `${messageScopeId}:zone:${priceLow}:${priceHigh}`,
        type: "zone",
        label: /支撑|需求|回踩/.test(content) ? "支撑区域" : /阻力|压力|供给/.test(content) ? "阻力区域" : "候选区域",
        priceLow,
        priceHigh,
        category: /风险|失效|放弃|谨慎/.test(content) ? "trapped" : "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        sourceKind,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summary,
      });
    }
    const priceRegex = /\d{3,6}(?:\.\d+)?/g;
    let priceMatch;
    while ((priceMatch = priceRegex.exec(content)) !== null) {
      const inRangeSpan = rangeSpans.some(([start, end]) => priceMatch.index >= start && priceMatch.index < end);
      if (inRangeSpan || isCandidateTemporalOrMetricNumber(content, priceMatch.index, priceMatch[0])) {
        continue;
      }
      const price = Number(priceMatch[0]);
      if (!Number.isFinite(price)) {
        continue;
      }
      priceValues.push(price);
      pushItem({
        id: `${messageScopeId}-price-${priceMatch.index}-${price}`,
        stableKey: `${messageScopeId}:price:${price}`,
        type: /止损|失效|风险/.test(content) ? "risk" : "price",
        label: /止损/.test(content)
          ? "止损位"
          : /止盈|目标/.test(content)
            ? "目标位"
            : /入场|回踩/.test(content)
              ? "入场位"
              : /失效|跌破|站不上|风险/.test(content)
                ? "风险位"
                : "关键价位",
        price,
        category: /止损|失效|跌破|站不上|风险/.test(content) ? "trapped" : "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        sourceKind,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summary,
      });
    }
    const riskHint = content.match(/(?:风险|失效|谨慎|放弃|跌破|站不上|不能追|不要追)[^。；\n]*/);
    if (riskHint) {
      pushItem({
        id: `${messageScopeId}-risk-${riskHint.index || 0}`,
        stableKey: `${messageScopeId}:risk:${riskHint[0]}`,
        type: "risk",
        label: "风险提示",
        price: priceValues[0] ?? null,
        category: "trapped",
        sourceRole,
        sourceActor,
        sourceTitle,
        sourceKind,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summarizeText(riskHint[0], 96),
      });
    }
    const planHint = content.match(/(?:做多|做空|观望|等待确认|突破跟随|回踩接多|反抽做空|计划|脚本)[^。；\n]*/);
    if (planHint) {
      pushItem({
        id: `${messageScopeId}-plan-${planHint.index || 0}`,
        stableKey: `${messageScopeId}:plan:${planHint[0]}`,
        type: "plan",
        label: /观望|等待/.test(planHint[0]) ? "观望计划" : /做空|反抽/.test(planHint[0]) ? "空头计划" : "多头计划",
        price: priceValues[0] ?? null,
        category: "events",
        sourceRole,
        sourceActor,
        sourceTitle,
        sourceKind,
        messageId: meta.messageId || null,
        sessionId: meta.sessionId || null,
        observedAt,
        excerpt: summarizeText(planHint[0], 96),
      });
    }
    return items;
  }

  function buildReplyExtractionItems() {
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const extractionState = getReplyExtractionState();
    const aggressiveMode = extractionState.intensity === "aggressive";
    const analystSession = getSessionByRole(symbol, "analyst");
    const scribeSession = getSessionByRole(symbol, "scribe");
    const sessions = [scribeSession, analystSession].filter(Boolean);
    const structuredMessageIdsBySession = new Map(
      sessions.map((session) => [session.id, getStructuredReplyMessageIds(session)]),
    );
    const hasStructuredCandidates = sessions.some((session) => {
      const structuredIds = structuredMessageIdsBySession.get(session.id);
      return structuredIds && structuredIds.size > 0;
    });
    const scribeHasStructuredReply = hasStructuredReplyContent(scribeSession);
    const candidateMap = new Map();
    const pushCandidate = (item) => {
      const dedupKey = getReplyCandidateDedupKey(item);
      if (!dedupKey) {
        return;
      }
      const existing = candidateMap.get(dedupKey);
      if (!existing || shouldReplaceReplyCandidate(existing, item)) {
        candidateMap.set(dedupKey, item);
      }
    };

    sessions.forEach((session) => {
      const sessionRole = getWorkspaceRole(session);
      (state.aiAnnotations || [])
        .filter((annotation) => annotation.session_id === session.id)
        .forEach((annotation) => {
          const annotationType = String(annotation.type || "").toLowerCase();
          const normalizedType = ["plan", "zone", "risk", "price"].includes(annotation.event_kind)
            ? annotation.event_kind
            : annotation.price_low != null || annotation.price_high != null
              ? (/no_trade|risk|invalid/.test(annotationType) ? "risk" : "zone")
              : (/stop|risk|invalid/.test(annotationType) ? "risk" : /plan|entry|profit|target/.test(annotationType) ? "plan" : "price");
          pushCandidate({
            id: `annotation-${annotation.id}`,
            stableKey: `annotation:${annotation.id}`,
            type: normalizedType,
            label: annotation.label || annotation.type || "AI 标记",
            price: annotation.entry_price ?? annotation.target_price ?? annotation.stop_price ?? null,
            priceLow: annotation.price_low ?? null,
            priceHigh: annotation.price_high ?? null,
            category: normalizedType === "risk" ? "trapped" : "events",
            excerpt: summarizeText(annotation.reason || annotation.label || "", 100),
            sourceRole: sessionRole,
            sourceActor: sessionRole === "scribe" ? "事件判断 AI" : "行情分析 AI",
            sourceTitle: session.title || (sessionRole === "scribe" ? "事件整理 AI" : "行情分析 AI"),
            messageId: annotation.message_id || null,
            sessionId: session.id,
            observedAt: annotation.started_at || annotation.created_at || annotation.updated_at || null,
          });
        });
      const structuredMessageIds = structuredMessageIdsBySession.get(session.id) || new Set();
      const allowMessageExtraction = aggressiveMode
        || !hasStructuredCandidates
        || (sessionRole === "analyst" && !scribeHasStructuredReply);
      if (!allowMessageExtraction) {
        return;
      }
      [...(session.messages || [])]
        .filter((message) => message.role === "assistant")
        .slice(sessionRole === "scribe" ? -8 : -4)
        .forEach((message) => {
          if (structuredMessageIds.has(message.message_id)) {
            return;
          }
          extractReplyCandidatesFromText(message.content, {
            sessionId: session.id,
            messageId: message.message_id,
            sourceRole: sessionRole,
            sourceActor: sessionRole === "scribe" ? "事件判断 AI" : "行情分析 AI",
            sourceTitle: message.replyTitle || session.title || (sessionRole === "scribe" ? "事件整理 AI" : "行情分析 AI"),
            observedAt: message.created_at || message.updated_at || null,
            sourceKind: "text_fallback",
          }).forEach(pushCandidate);
        });
    });
    return attachReplyCandidateEventLinks(sortReplyCandidates(
      Array.from(candidateMap.values())
        .map((item) => hydrateReplyCandidateState(symbol, item)),
    )).slice(0, 36);
  }

  function setHoverOverlayItem(item = null) {
    state.eventStreamHoverItem = item || null;
    window.dispatchEvent(new CustomEvent("replay-workbench:hover-item-changed"));
  }

  async function ensureScribeSessionForSymbol(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const existing = getSessionByRole(normalizedSymbol, "scribe");
    if (existing) {
      rememberSymbolWorkspaceSession(existing);
      return existing;
    }
    const created = await getOrCreateBlankSessionForSymbol(normalizedSymbol, normalizedSymbol, {
      workspaceRole: "scribe",
      activate: false,
    });
    rememberSymbolWorkspaceSession(created);
    return created;
  }

  async function createFreshScribeSession(symbol = null) {
    const normalizedSymbol = String(symbol || state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const count = state.aiThreads.filter((item) => {
      const itemSymbol = String(item.symbol || item.contractId || item.memory?.symbol || "").trim().toUpperCase();
      return itemSymbol === normalizedSymbol && getWorkspaceRole(item) === "scribe";
    }).length + 1;
    const title = `${normalizedSymbol}-事件-${String(count).padStart(2, "0")}`;
    const session = await createBackendSession({
      title,
      symbol: normalizedSymbol,
      contractId: normalizedSymbol,
      timeframe: state.topBar?.timeframe || "1m",
      windowRange: state.topBar?.quickRange || "最近7天",
      activate: false,
      workspaceRole: "scribe",
    });
    rememberSymbolWorkspaceSession(session);
    return session;
  }

  async function sendEventScribeMessage({ button = els.eventScribeSendButton } = {}) {
    return runButtonAction(button, async () => {
      const message = String(els.eventScribeInput?.value || "").trim();
      if (!message) {
        renderStatusStrip([{ label: "请先输入事件整理问题。", variant: "warn" }]);
        els.eventScribeInput?.focus();
        return null;
      }
      const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
      session.draftText = "";
      session.draft = "";
      session.loadingFromServer = true;
      renderEventScribePanel();
      try {
        const analystSession = getSessionByRole(state.topBar?.symbol, "analyst");
        const latestAnalystReply = getLatestAssistantMessage(analystSession);
        const latestAnalystQuestion = getLatestUserMessage(analystSession);
        await fetchJson(`/api/v1/workbench/chat/sessions/${encodeURIComponent(session.id)}/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            replay_ingestion_id: state.currentReplayIngestionId || null,
            preset: "general",
            user_input: message,
            selected_block_ids: [],
            pinned_block_ids: [],
            include_memory_summary: true,
            include_recent_messages: true,
            analysis_type: "event_timeline",
            analysis_range: "current_window",
            analysis_style: "standard",
            model: session.activeModel || null,
            attachments: [],
            extra_context: {
              analyst_latest_question: latestAnalystQuestion?.content || "",
              analyst_latest_reply: latestAnalystReply?.content || "",
            },
          }),
        });
        const hydrated = await hydrateSessionFromServer(session.id, { activate: false });
        if (hydrated) {
          hydrated.loadingFromServer = false;
          rememberSymbolWorkspaceSession(hydrated);
        }
        renderStatusStrip([{ label: "事件整理 AI 已更新。", variant: "good" }]);
      } catch (error) {
        session.loadingFromServer = false;
        session.draftText = message;
        session.draft = message;
        renderStatusStrip([{ label: error.message || "事件整理 AI 发送失败。", variant: "warn" }]);
      }
      renderSnapshot();
      return true;
    }, {
      lockKey: "event-scribe-send",
      blockedLabel: "事件整理正在处理中，请等待当前请求完成。",
      silentError: true,
    });
  }

  function renderEventScribePanel() {
    if (!els.eventScribePanel) {
      return;
    }
    const session = getSessionByRole(state.topBar?.symbol, "scribe");
    const latestAnalystReply = getLatestAssistantMessage(getSessionByRole(state.topBar?.symbol, "analyst"));
    if (els.eventScribeSessionLabel) {
      els.eventScribeSessionLabel.textContent = session?.title || "未建立会话";
    }
    if (els.eventScribeInput && document.activeElement !== els.eventScribeInput) {
      els.eventScribeInput.value = session?.draftText || session?.draft || "";
    }
    if (els.eventScribeSendButton) {
      els.eventScribeSendButton.disabled = !session || !!session.loadingFromServer;
      els.eventScribeSendButton.textContent = session?.loadingFromServer ? "整理中…" : "发送";
    }
    if (els.eventScribeMirrorButton) {
      els.eventScribeMirrorButton.disabled = !latestAnalystReply;
    }
    if (!session) {
      els.eventScribeThread.innerHTML = `<div class="secondary-chat-empty">当前品种无事件会话。</div>`;
      return;
    }
    if (session.loadingFromServer) {
      els.eventScribeThread.innerHTML = `
        ${(session.messages || []).slice(-4).map((message) => buildSecondaryMessageMarkup(message)).join("")}
        <div class="secondary-chat-empty">事件判断 AI 正在整理…</div>
      `;
      return;
    }
    const messages = (session.messages || []).slice(-8);
    els.eventScribeThread.innerHTML = messages.length
      ? messages.map((message) => buildSecondaryMessageMarkup(message)).join("")
      : `<div class="secondary-chat-empty">可发送价位、区域、风险、时间线。</div>`;
  }

  function renderReplyExtractionPanel() {
    if (!els.replyExtractionPanel || !els.replyExtractionList || !els.replyExtractionSummary) {
      return;
    }
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const extractionState = getReplyExtractionState();
    const filter = extractionState.filter || "all";
    const showIgnored = !!extractionState.showIgnored;
    const pendingOnly = !!extractionState.pendingOnly;
    const collapsed = !!extractionState.collapsed;
    const allItems = applyReplyExtractionRuntimeFilters(buildReplyExtractionItems(), extractionState);
    const counts = {
      price: allItems.filter((item) => item.type === "price").length,
      zone: allItems.filter((item) => item.type === "zone").length,
      risk: allItems.filter((item) => item.type === "risk").length,
      plan: allItems.filter((item) => item.type === "plan").length,
      ignored: allItems.filter((item) => item.ignored).length,
      pending: allItems.filter((item) => isPendingReplyExtractionItem(item)).length,
      confirmed: allItems.filter((item) => item.status === "confirmed").length,
      mounted: allItems.filter((item) => item.status === "mounted" || item.status === "promoted_annotation").length,
      promoted: allItems.filter((item) => item.status === "promoted_plan").length,
    };
    const items = getFilteredReplyExtractionItems(allItems, extractionState);
    els.replyExtractionFilterBar?.querySelectorAll("[data-reply-extraction-filter]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.replyExtractionFilter === filter);
    });
    if (els.replyExtractionShowIgnoredButton) {
      els.replyExtractionShowIgnoredButton.classList.toggle("is-active", showIgnored && !pendingOnly);
      els.replyExtractionShowIgnoredButton.disabled = pendingOnly;
      els.replyExtractionShowIgnoredButton.textContent = pendingOnly ? "仅待处理中" : (showIgnored ? "隐藏已忽略" : "显示已忽略");
    }
    if (els.replyExtractionPendingOnlyButton) {
      els.replyExtractionPendingOnlyButton.classList.toggle("is-active", pendingOnly);
      els.replyExtractionPendingOnlyButton.disabled = !counts.pending;
    }
    if (els.replyExtractionShowHistoryButton) {
      els.replyExtractionShowHistoryButton.classList.toggle("is-active", !pendingOnly && showIgnored);
      els.replyExtractionShowHistoryButton.disabled = !allItems.length;
    }
    if (els.replyExtractionExportButton) {
      els.replyExtractionExportButton.disabled = !items.length;
    }
    if (els.replyExtractionFooterMeta) {
      els.replyExtractionFooterMeta.textContent = allItems.length
        ? `当前显示 ${items.length} 条${pendingOnly ? "待处理事件" : "筛选结果"}，待处理 ${counts.pending} 条${showIgnored && !pendingOnly ? "，含已忽略/已上图历史" : ""}。`
        : "当前还没有可导出的事件摘要。";
    }
    if (els.replyExtractionCollapseButton) {
      els.replyExtractionCollapseButton.classList.toggle("is-active", collapsed);
      els.replyExtractionCollapseButton.textContent = collapsed ? "展开" : "收起";
    }
    if (els.replyExtractionPanel) {
      els.replyExtractionPanel.classList.toggle("is-collapsed", collapsed);
    }
    if (els.replyExtractionControls) {
      els.replyExtractionControls.hidden = collapsed;
    }
    if (els.replyExtractionFilterBar) {
      els.replyExtractionFilterBar.hidden = collapsed;
    }
    if (els.replyExtractionList) {
      els.replyExtractionList.hidden = collapsed;
    }
    if (els.replyExtractionFooter) {
      els.replyExtractionFooter.hidden = collapsed;
    }
    els.replyExtractionSummary.textContent = allItems.length
      ? `${symbol} 事件整理 ${allItems.length} 条。行动 ${counts.plan} / 区域 ${counts.zone} / 风险 ${counts.risk}${counts.price ? ` / 补充价位 ${counts.price}` : ""}${counts.pending ? ` / 待处理 ${counts.pending}` : ""}${counts.confirmed ? ` / 已确认 ${counts.confirmed}` : ""}${counts.mounted ? ` / 已上图 ${counts.mounted}` : ""}${counts.promoted ? ` / 转计划 ${counts.promoted}` : ""}${counts.ignored ? ` / 已忽略 ${counts.ignored}` : ""}。`
      : "等待事件整理。";
    if (collapsed) {
      return;
    }
    if (!items.length) {
      els.replyExtractionList.innerHTML = `<div class="reply-extraction-empty">${allItems.length ? "当前筛选下无结果。" : "暂无事件整理结果。"}</div>`;
      return;
    }
    const groupConfig = [
      { key: "plan", title: "行动计划", hint: "优先看可执行结论", limit: 4, countVariant: "good" },
      { key: "zone", title: "关键区域", hint: "先盯支撑与阻力带", limit: 6, countVariant: "emphasis" },
      { key: "risk", title: "风险提醒", hint: "先排除不能做的地方", limit: 6, countVariant: "warn" },
      { key: "price", title: "补充价位", hint: "辅助参考，不单独构成事件", limit: 4, countVariant: "" },
    ];
    const typeLabelMap = {
      price: "价位",
      zone: "区域",
      risk: "风险",
      plan: "行动",
    };
    const statusLabelMap = {
      candidate: "候选",
      confirmed: "已确认",
      mounted: "已上图",
      promoted_annotation: "已上图",
      promoted_plan: "已转计划",
      ignored: "已忽略",
    };
    const getCandidateSourceBadge = (item) => {
      const stableKey = String(item.stableKey || "");
      if (stableKey.startsWith("annotation:")) {
        return "图上标记";
      }
      if (item.sourceRole === "scribe") {
        return "事件整理";
      }
      if (item.sourceRole === "analyst") {
        return "主分析";
      }
      return item.sourceActor || "来源";
    };
    const focusLinkedCluster = (item, { announce = false } = {}) => {
      if (!item?.linkedClusterKey) {
        return false;
      }
      const focused = selectChartEventCluster(item.linkedClusterKey, {
        centerChart: false,
        openContext: true,
        announce,
      });
      if (focused) {
        setHoverOverlayItem(buildReplyCandidateHoverItemFromCluster(state.chartEventModel?.clusterIndex?.[item.linkedClusterKey]) || item);
      }
      return focused;
    };
    const buildItemMarkup = (item) => {
      const priceLabel = item.type === "zone"
        ? `${item.priceLow?.toFixed?.(2) ?? item.priceLow} - ${item.priceHigh?.toFixed?.(2) ?? item.priceHigh}`
        : (item.price != null ? `${item.price?.toFixed?.(2) ?? item.price}` : "未定位价格");
      const sourceRoleLabel = getCandidateSourceBadge(item);
      const ignoredClass = item.ignored ? " is-ignored" : "";
      const observedAtLabel = formatCompactLocalDateTime(item.observedAt);
      const statusLabel = statusLabelMap[item.status] || statusLabelMap.candidate;
      const statusClass = item.status === "ignored"
        ? "warn"
        : item.status === "mounted" || item.status === "promoted_annotation" || item.status === "promoted_plan"
          ? "good"
          : item.status === "confirmed"
            ? "emphasis"
            : "";
      return `
        <article class="reply-extraction-item type-${escapeHtml(item.type || "price")}${ignoredClass}" data-extraction-id="${escapeHtml(item.id)}" data-candidate-key="${escapeHtml(item.candidateKey || item.id)}">
          <div class="reply-extraction-head">
            <div class="reply-extraction-title-wrap">
              <strong>${escapeHtml(item.label || (item.type === "zone" ? "候选区域" : "关键价位"))}</strong>
              <div class="reply-extraction-meta">${escapeHtml(item.sourceTitle || "AI 提取")}</div>
            </div>
            <div class="reply-extraction-chip-row">
              <span class="chip">${escapeHtml(typeLabelMap[item.type] || "候选")}</span>
              <span class="chip">${escapeHtml(sourceRoleLabel)}</span>
              <span class="chip ${escapeHtml(statusClass)}">${escapeHtml(statusLabel)}</span>
            </div>
          </div>
          <div class="reply-extraction-price">${escapeHtml(priceLabel)}</div>
          <p>${escapeHtml(item.excerpt || "等待确认")}</p>
          ${item.linkedClusterKey ? `
            <div class="reply-extraction-link-line">
              <span class="reply-extraction-link-chip">事件 ${escapeHtml(item.linkedClusterTimeLabel || "--")}</span>
              <span>${escapeHtml(item.linkedClusterSummary || "已关联事件簇")}</span>
            </div>
          ` : ""}
          <div class="reply-extraction-source-line">
            <span>${escapeHtml(item.sourceActor || "AI")}</span>
            <span>${escapeHtml(observedAtLabel)}</span>
          </div>
          <div class="reply-extraction-actions">
            <button type="button" class="secondary tiny" data-extraction-action="mount" data-extraction-id="${escapeHtml(item.id)}">${item.status === "mounted" || item.status === "promoted_annotation" ? "再上图" : "上图"}</button>
            <button type="button" class="secondary tiny" data-extraction-action="confirm" data-extraction-id="${escapeHtml(item.id)}">${item.status === "confirmed" ? "已确认" : "确认"}</button>
            <button type="button" class="secondary tiny" data-extraction-action="promote-plan" data-extraction-id="${escapeHtml(item.id)}">${item.status === "promoted_plan" ? "再转计划" : "转计划卡"}</button>
            ${item.linkedClusterKey ? `<button type="button" class="secondary tiny" data-extraction-action="event" data-extraction-id="${escapeHtml(item.id)}">事件</button>` : ""}
            <button type="button" class="secondary tiny" data-extraction-action="source" data-extraction-id="${escapeHtml(item.id)}">来源</button>
            <button type="button" class="secondary tiny" data-extraction-action="ignore" data-extraction-id="${escapeHtml(item.id)}">${item.ignored ? "恢复" : "忽略"}</button>
          </div>
        </article>
      `;
    };
    const activeGroups = filter === "all"
      ? groupConfig
      : groupConfig.filter((group) => group.key === filter);
    els.replyExtractionList.innerHTML = activeGroups
      .filter((group) => items.some((item) => item.type === group.key))
      .map((group) => {
        const groupItems = items.filter((item) => item.type === group.key);
        const visibleItems = filter === "all" ? groupItems.slice(0, group.limit) : groupItems;
        const hiddenCount = Math.max(0, groupItems.length - visibleItems.length);
        return `
          <section class="reply-extraction-group">
            <div class="reply-extraction-group-head">
              <div>
                <strong>${escapeHtml(group.title)}</strong>
                <div class="meta">${escapeHtml(group.hint)}</div>
              </div>
              <span class="chip reply-extraction-group-count ${escapeHtml(group.countVariant)}">${groupItems.length}</span>
            </div>
            <div class="reply-extraction-group-list">
              ${visibleItems.map((item) => buildItemMarkup(item)).join("")}
            </div>
            ${hiddenCount ? `<div class="reply-extraction-more-note">当前还有 ${hiddenCount} 条${escapeHtml(group.title)}未展开，可切换顶部筛选单独查看。</div>` : ""}
          </section>
        `;
      }).join("");
    const openExtractionSource = (item) => {
      if (!item?.messageId) {
        return;
      }
      const targetSession = item.sessionId
        ? state.aiThreads.find((entry) => entry.id === item.sessionId)
        : null;
      if (!targetSession) {
        return;
      }
      if (getWorkspaceRole(targetSession) === "analyst") {
        setActiveThread(targetSession.id, targetSession.title, targetSession);
        jumpToMessageWhenReady(item.messageId);
        return;
      }
      rememberSymbolWorkspaceSession(targetSession);
      renderEventScribePanel();
      jumpToSecondaryMessageWhenReady(item.messageId);
    };
    els.replyExtractionList.querySelectorAll(".reply-extraction-item[data-extraction-id]").forEach((node) => {
      const item = items.find((entry) => entry.id === node.dataset.extractionId);
      node.addEventListener("mouseenter", () => {
        const hoverItem = item?.linkedClusterKey
          ? buildReplyCandidateHoverItemFromCluster(state.chartEventModel?.clusterIndex?.[item.linkedClusterKey])
          : item;
        setHoverOverlayItem(hoverItem || item);
      });
      node.addEventListener("mouseleave", () => setHoverOverlayItem(null));
      node.addEventListener("click", (event) => {
        const actionButton = event.target?.closest("[data-extraction-action]");
        if (actionButton) {
          if (!item) {
            return;
          }
          const action = actionButton.dataset.extractionAction;
          if (action === "source") {
            openExtractionSource(item);
            return;
          }
          if (action === "event") {
            if (focusLinkedCluster(item, { announce: false })) {
              renderStatusStrip([{ label: `已定位到事件簇：${item.linkedClusterTimeLabel || "--"} · ${item.linkedClusterSummary || "事件"}`, variant: "emphasis" }]);
            } else {
              renderStatusStrip([{ label: "当前候选还没有可定位的事件簇。", variant: "warn" }]);
            }
            return;
          }
          if (action === "ignore") {
            updateReplyCandidateMeta(symbol, item.candidateKey || item.id, {
              status: item.ignored ? "candidate" : "ignored",
            });
            renderReplyExtractionPanel();
            renderStatusStrip([{
              label: item.ignored ? "候选事件已恢复。" : "候选事件已忽略。",
              variant: item.ignored ? "good" : "warn",
            }]);
            return;
          }
          if (action === "confirm") {
            const nextStatus = item.status === "confirmed" ? "candidate" : "confirmed";
            updateReplyCandidateMeta(symbol, item.candidateKey || item.id, { status: nextStatus });
            renderReplyExtractionPanel();
            renderStatusStrip([{
              label: nextStatus === "confirmed" ? "候选事件已确认，可继续上图或转计划。" : "已取消确认，回到候选状态。",
              variant: nextStatus === "confirmed" ? "good" : "emphasis",
            }]);
            return;
          }
          if (action === "mount") {
            const promoted = promoteCandidateToAnnotation(item);
            if (!promoted.annotation) {
              renderStatusStrip([{ label: "该候选缺少可用价格，暂时无法上图。", variant: "warn" }]);
              return;
            }
            updateReplyCandidateMeta(symbol, item.candidateKey || item.id, {
              status: promoted.created ? "promoted_annotation" : "mounted",
            });
            applyAnnotationScope?.(promoted.annotation.id, {
              mode: "only",
              activateSession: true,
              jumpToSource: false,
              render: true,
            });
            queueSessionMemoryRefresh([promoted.annotation.session_id], { forceServer: true, delay: 140 });
            renderReplyExtractionPanel();
            renderStatusStrip([{
              label: promoted.created ? "候选事件已上图。可在标记管理器继续精修。" : "候选事件对应标记已定位到图表。",
              variant: "good",
            }]);
            return;
          }
          if (action === "promote-plan") {
            const promoted = buildPlanCardFromCandidate(item);
            if (!promoted.planCard || !promoted.message || !promoted.session) {
              renderStatusStrip([{ label: "该候选缺少可执行价格，暂时无法转为计划卡。", variant: "warn" }]);
              return;
            }
            updateReplyCandidateMeta(symbol, item.candidateKey || item.id, { status: "promoted_plan" });
            setActiveThread(promoted.session.id, promoted.session.title, promoted.session);
            jumpToMessageWhenReady(promoted.message.message_id);
            queueSessionMemoryRefresh([promoted.session.id], { forceServer: true, delay: 140 });
            renderReplyExtractionPanel();
            renderStatusStrip([{ label: `已生成计划卡：${promoted.planCard.title || "候选计划"}`, variant: "good" }]);
          }
          return;
        }
        if (focusLinkedCluster(item, { announce: false })) {
          renderStatusStrip([{ label: `已聚焦关联事件：${item.linkedClusterTimeLabel || "--"} · ${item.linkedClusterSummary || "事件"}`, variant: "emphasis" }]);
          return;
        }
        openExtractionSource(item);
      });
    });
    const canBatch = items.length > 0;
    if (els.replyExtractionBatchConfirmButton) {
      els.replyExtractionBatchConfirmButton.disabled = !canBatch;
    }
    if (els.replyExtractionBatchMountButton) {
      els.replyExtractionBatchMountButton.disabled = !canBatch;
    }
    if (els.replyExtractionBatchPromoteButton) {
      els.replyExtractionBatchPromoteButton.disabled = !canBatch;
    }
    if (els.replyExtractionBatchIgnoreButton) {
      els.replyExtractionBatchIgnoreButton.disabled = !canBatch;
    }
    if (els.replyExtractionAutoButton) {
      const autoEnabled = extractionState.autoExtractEnabled !== false;
      els.replyExtractionAutoButton.classList.toggle("is-active", autoEnabled);
      els.replyExtractionAutoButton.textContent = autoEnabled ? "自动记录：开" : "自动记录：关";
    }
    if (els.replyExtractionIntensitySelect && document.activeElement !== els.replyExtractionIntensitySelect) {
      els.replyExtractionIntensitySelect.value = extractionState.intensity || "balanced";
    }
  }

  function applyReplyExtractionBatchAction(action = "confirm") {
    const symbol = String(state.topBar?.symbol || "NQ").trim().toUpperCase() || "NQ";
    const items = getVisibleReplyExtractionItems();
    if (!items.length) {
      renderStatusStrip([{ label: "当前筛选下没有可批量处理的候选。", variant: "warn" }]);
      return;
    }
    let updated = 0;
    let skipped = 0;
    const touchedSessionIds = new Set();
    if (action === "confirm") {
      items.forEach((item) => {
        if (item.ignored) {
          skipped += 1;
          return;
        }
        updateReplyCandidateMeta(symbol, item.candidateKey || item.id, { status: "confirmed" });
        updated += 1;
      });
      renderReplyExtractionPanel();
      renderStatusStrip([{ label: `已批量确认 ${updated} 条候选${skipped ? `，跳过 ${skipped} 条` : ""}。`, variant: "good" }]);
      return;
    }
    if (action === "ignore") {
      items.forEach((item) => {
        updateReplyCandidateMeta(symbol, item.candidateKey || item.id, { status: "ignored" });
        updated += 1;
      });
      renderReplyExtractionPanel();
      renderStatusStrip([{ label: `已批量忽略 ${updated} 条候选。`, variant: "warn" }]);
      return;
    }
    if (action === "mount") {
      let firstAnnotationId = null;
      items.forEach((item) => {
        const promoted = promoteCandidateToAnnotation(item);
        if (!promoted.annotation) {
          skipped += 1;
          return;
        }
        if (!firstAnnotationId) {
          firstAnnotationId = promoted.annotation.id;
        }
        touchedSessionIds.add(promoted.annotation.session_id);
        updateReplyCandidateMeta(symbol, item.candidateKey || item.id, {
          status: promoted.created ? "promoted_annotation" : "mounted",
        });
        updated += 1;
      });
      if (firstAnnotationId) {
        applyAnnotationScope?.(firstAnnotationId, {
          mode: "reply",
          activateSession: true,
          jumpToSource: false,
          render: false,
        });
      }
      if (touchedSessionIds.size) {
        queueSessionMemoryRefresh(Array.from(touchedSessionIds), { forceServer: true, delay: 140 });
      }
      renderReplyExtractionPanel();
      renderSnapshot();
      renderStatusStrip([{
        label: updated
          ? `已批量上图 ${updated} 条候选${skipped ? `，跳过 ${skipped} 条` : ""}。`
          : "当前候选缺少可用价格，未执行上图。",
        variant: updated ? "good" : "warn",
      }]);
      return;
    }
    if (action === "promote-plan") {
      let firstPromoted = null;
      items.forEach((item) => {
        if (item.ignored) {
          skipped += 1;
          return;
        }
        const promoted = buildPlanCardFromCandidate(item);
        if (!promoted.planCard || !promoted.message || !promoted.session) {
          skipped += 1;
          return;
        }
        if (!firstPromoted) {
          firstPromoted = promoted;
        }
        touchedSessionIds.add(promoted.session.id);
        updateReplyCandidateMeta(symbol, item.candidateKey || item.id, { status: "promoted_plan" });
        updated += 1;
      });
      if (firstPromoted?.session?.id) {
        setActiveThread(firstPromoted.session.id, firstPromoted.session.title, firstPromoted.session);
      }
      if (firstPromoted?.message?.message_id) {
        jumpToMessageWhenReady(firstPromoted.message.message_id);
      }
      if (touchedSessionIds.size) {
        queueSessionMemoryRefresh(Array.from(touchedSessionIds), { forceServer: true, delay: 140 });
      }
      renderReplyExtractionPanel();
      renderSnapshot();
      renderStatusStrip([{
        label: updated
          ? `已批量转计划卡 ${updated} 条候选${skipped ? `，跳过 ${skipped} 条` : ""}。`
          : "当前候选缺少可执行价格，未生成计划卡。",
        variant: updated ? "good" : "warn",
      }]);
      return;
    }
  }

  function renderContractNav() {
    if (!els.aiContractNav) return;
    const getThreadTimestamp = (thread) => {
      const candidates = [
        thread?.updatedAt,
        thread?.memory?.last_updated_at,
        thread?.messages?.[thread.messages.length - 1]?.updated_at,
        thread?.messages?.[thread.messages.length - 1]?.created_at,
        thread?.createdAt,
      ];
      for (const candidate of candidates) {
        if (!candidate) {
          continue;
        }
        const timestamp = Date.parse(candidate);
        if (Number.isFinite(timestamp)) {
          return timestamp;
        }
      }
      return 0;
    };
    const hasThreadDraft = (thread) => {
      const textDraft = String(thread?.draftText || thread?.draft || "").trim();
      const attachmentDraft = Array.isArray(thread?.draftAttachments)
        ? thread.draftAttachments.length
        : (Array.isArray(thread?.attachments) ? thread.attachments.length : 0);
      return !!textDraft || attachmentDraft > 0;
    };
    const isBlankThread = (thread) => {
      const attachmentCount = Array.isArray(thread?.draftAttachments)
        ? thread.draftAttachments.length
        : (Array.isArray(thread?.attachments) ? thread.attachments.length : 0);
      return !(thread?.messages?.length)
        && !String(thread?.draftText || thread?.draft || "").trim()
        && attachmentCount === 0
        && !(thread?.selectedPromptBlockIds?.length)
        && !(thread?.mountedReplyIds?.length);
    };
    const shouldSurfaceAnalystThread = (thread) => {
      if (!thread) {
        return false;
      }
      if (!isBlankThread(thread)) {
        return true;
      }
      return thread.id === state.activeAiThreadId;
    };
    const sortThreads = (a, b, symbol = null) => {
      const aActive = a.id === state.activeAiThreadId;
      const bActive = b.id === state.activeAiThreadId;
      if (aActive !== bActive) {
        return aActive ? -1 : 1;
      }
      if (symbol) {
        const aMatches = (a.symbol || a.contractId || a.memory?.symbol || "") === symbol;
        const bMatches = (b.symbol || b.contractId || b.memory?.symbol || "") === symbol;
        if (aMatches !== bMatches) {
          return aMatches ? -1 : 1;
        }
      }
      if (!!a.pinned !== !!b.pinned) {
        return a.pinned ? -1 : 1;
      }
      if (!!a.activePlanId !== !!b.activePlanId) {
        return a.activePlanId ? -1 : 1;
      }
      if (hasThreadDraft(a) !== hasThreadDraft(b)) {
        return hasThreadDraft(a) ? -1 : 1;
      }
      if ((a.unreadCount || 0) !== (b.unreadCount || 0)) {
        return (b.unreadCount || 0) - (a.unreadCount || 0);
      }
      return getThreadTimestamp(b) - getThreadTimestamp(a);
    };
    const contracts = new Map();
    state.aiThreads
      .filter((thread) => getWorkspaceRole(thread) === "analyst")
      .filter((thread) => shouldSurfaceAnalystThread(thread))
      .forEach((thread) => {
      const symbol = thread.symbol || thread.contractId || thread.memory?.symbol || state.topBar.symbol || "NQ";
      if (!contracts.has(symbol)) {
        contracts.set(symbol, {
          symbol,
          threads: [],
          active: false,
        });
      }
      contracts.get(symbol).threads.push(thread);
      if (thread.id === state.activeAiThreadId) {
        contracts.get(symbol).active = true;
      }
      });
    const contractArray = Array.from(contracts.values()).sort((a, b) => {
      if (a.active) return -1;
      if (b.active) return 1;
      return a.symbol.localeCompare(b.symbol);
    });
    contractArray.forEach((contract) => {
      contract.threads.sort((a, b) => sortThreads(a, b, contract.symbol));
    });
    els.aiContractNav.innerHTML = contractArray.map((contract) => {
      const unreadCount = contract.threads.reduce((sum, t) => sum + (t.unreadCount || 0), 0);
      const threadCount = contract.threads.length;
      return `
        <div class="ai-contract-card ${contract.active ? "active" : ""}" 
             data-contract-symbol="${contract.symbol}" 
             title="${contract.symbol} (${threadCount}个会话)">
          <div class="ai-contract-symbol">${contract.symbol}</div>
          ${unreadCount > 0 ? `<div class="ai-contract-badge">${unreadCount > 9 ? "9+" : unreadCount}</div>` : ""}
        </div>
      `;
    }).join("");
    els.aiContractNav.querySelectorAll(".ai-contract-card").forEach((card) => {
      card.addEventListener("click", () => {
        const symbol = card.dataset.contractSymbol;
        const contract = contractArray.find((c) => c.symbol === symbol);
        if (contract && contract.threads.length > 0) {
          const preferredThread = [...contract.threads].sort((a, b) => sortThreads(a, b, symbol))[0];
          if (preferredThread) {
            rememberSymbolWorkspaceSession(preferredThread);
          }
          els.instrumentSymbol.value = symbol;
          state.topBar.symbol = symbol;
          void activateSymbolWorkspace(symbol).then(() => renderSnapshot());
        }
      });
    });
  }

  function initializeSkillPanel() {
    if (!els.aiSkillPanel || !els.aiSkillGrid) return;
    const skills = [
      { id: "kline_analysis", name: "K线分析", icon: "📊", prompt: "请分析当前K线图表并给出交易建议" },
      { id: "recent_bars", name: "最近20根K线", icon: "📈", prompt: "请分析最近20根K线并给出交易计划" },
      { id: "focus_regions", name: "重点区域", icon: "🎯", prompt: "请围绕当前重点区域给出计划" },
      { id: "live_depth", name: "实时挂单", icon: "📋", prompt: "请结合当前盘口结构给出建议" },
      { id: "manual_region", name: "手工区域", icon: "✏️", prompt: "请围绕手工区域做标准分析" },
      { id: "selected_bar", name: "选中K线", icon: "🔍", prompt: "请分析当前选中K线" },
    ];
    els.aiSkillGrid.innerHTML = skills.map((skill) => `
      <div class="ai-skill-card" data-skill-id="${skill.id}">
        <div class="ai-skill-icon">${skill.icon}</div>
        <div class="ai-skill-name">${skill.name}</div>
      </div>
    `).join("");
    const skillCards = Array.from(els.aiSkillGrid.querySelectorAll(".ai-skill-card"));
    skillCards.forEach((card) => {
      card.addEventListener("click", async () => {
        const skillId = card.dataset.skillId;
        const skill = skills.find((s) => s.id === skillId);
        if (skill) {
          await dispatchAiComposerSend({
            button: card,
            extraBusyTargets: skillCards,
            beforeSend: () => {
              updateComposerDraft(skill.prompt);
              setSkillPanelVisible(false);
              return true;
            },
          });
        }
      });
    });
    if (els.aiSkillSearch) {
      els.aiSkillSearch.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();
        els.aiSkillGrid.querySelectorAll(".ai-skill-card").forEach((card) => {
          const name = card.querySelector(".ai-skill-name").textContent.toLowerCase();
          card.style.display = name.includes(query) ? "flex" : "none";
        });
      });
    }
  }

  function attachBindings() {
    applyLayoutWidths();
    bindChatScrollBehavior();
    installButtonFeedback();
    syncQuickActionButtonState();
    const screenshotAttachmentButtons = [
      els.aiScreenshotButton,
      els.chartScreenshotButton,
      els.chartToolbarScreenshotButton,
    ].filter(Boolean);

    // AI 侧边栏控制
    els.aiSidebarTrigger?.addEventListener("click", toggleAiSidebar);
    els.aiSidebarCloseButton?.addEventListener("click", closeAiSidebar);
    els.aiSidebarPinButton?.addEventListener("click", () => {
      state.aiSidebarPinned = !state.aiSidebarPinned;
      writeStorage("aiSidebarState", { open: state.aiSidebarOpen, pinned: state.aiSidebarPinned });
      syncAiSidebarPinButtonState();
      renderStatusStrip([{ label: state.aiSidebarPinned ? "AI 侧栏固定偏好已开启" : "AI 侧栏固定偏好已关闭", variant: "emphasis" }]);
    });

    // 技能面板控制
    els.aiChatInput?.addEventListener("input", (e) => {
      const value = e.target.value;
      if (value.startsWith("@") || value.startsWith("/")) {
        setSkillPanelVisible(true);
      } else if (els.aiSkillPanel && !els.aiSkillPanel.hidden) {
        setSkillPanelVisible(false);
      }
    });

    // 快速操作按钮
    els.aiKlineAnalysisButton?.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.aiKlineAnalysisButton, async () => {
        await aiChat.handlePresetAnalysis("recent_20_bars", "请分析当前K线图表并给出交易建议。", false);
        renderSnapshot();
      });
    });
    els.aiMoreButton?.addEventListener("click", () => {
      setSkillPanelVisible(els.aiSkillPanel?.hidden ?? true, { announce: true });
    });
    els.aiAttachmentButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择文件后会附加到当前会话。", accept: defaultAttachmentAccept });
    });
    els.aiScreenshotButton?.addEventListener("click", async () => {
      await runButtonAction(els.aiScreenshotButton, async () => {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      }, {
        lockKey: "chart-screenshot-attachment",
        extraBusyTargets: screenshotAttachmentButtons,
      });
    });
    els.aiVoiceButton?.addEventListener("click", startVoiceCapture);
    els.aiVoiceInputButton?.addEventListener("click", startVoiceCapture);

    // 初始化技能面板
    initializeSkillPanel();

    // 恢复侧边栏状态
    const sidebarState = readStorage("aiSidebarState", { open: false, pinned: false });
    state.aiSidebarOpen = !!sidebarState.open;
    state.aiSidebarPinned = !!sidebarState.pinned;
    syncAiSidebarViewportState({ persist: false });
    syncAiSidebarPinButtonState();
    syncQuickActionButtonState();
    let resizeTimer = null;
    window.addEventListener("resize", () => {
      if (resizeTimer) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(() => {
        applyLayoutWidths();
        renderSnapshot();
      }, 120);
    });
    els.timeframeTabs.forEach((button) => {
      button.addEventListener("click", () => {
        els.displayTimeframe.value = button.dataset.timeframe;
        els.timeframeTabs.forEach((item) => item.classList.toggle("active", item === button));
        syncCacheKey();
        updateHeaderStatus();
      });
    });
    els.displayTimeframe.addEventListener("change", () => {
      els.timeframeTabs.forEach((item) => item.classList.toggle("active", item.dataset.timeframe === els.displayTimeframe.value));
      syncCacheKey();
      updateHeaderStatus();
    });
    els.quickRangeSelect.addEventListener("change", () => {
      const preset = state.quickRanges.find((item) => item.value === els.quickRangeSelect.value);
      if (preset?.days) {
        applyWindowPreset(els.displayTimeframe.value, preset.days);
      }
      updateHeaderStatus();
    });
    els.instrumentSymbol.addEventListener("change", async () => {
      const nextSymbol = (els.instrumentSymbol.value || "").trim().toUpperCase() || "NQ";
      els.instrumentSymbol.value = nextSymbol;
      state.topBar.symbol = nextSymbol;
      persistWorkbenchState();
      syncCacheKey();
      updateHeaderStatus();
      try {
        await syncSessionsFromServer({ symbol: nextSymbol, activateFirst: false });
        await activateSymbolWorkspace(nextSymbol);
      } catch (error) {
        console.warn("切换品种同步会话失败:", error);
        await activateSymbolWorkspace(nextSymbol);
      }
      // 切换品种时重新加载图表
      void handleBuildWithForceRefresh({ syncRelativeWindow: true });
    });
    
    // 启动时获取合约列表
    async function loadInstrumentsList() {
      try {
        const response = await fetchJson("/api/v1/workbench/instruments");
        if (response?.instruments?.length) {
          // 更新 datalist 选项
          let datalist = document.getElementById("symbolOptions");
          if (!datalist) {
            datalist = document.createElement("datalist");
            datalist.id = "symbolOptions";
            els.instrumentSymbol.setAttribute("list", "symbolOptions");
            els.instrumentSymbol.parentNode.appendChild(datalist);
          }
          datalist.innerHTML = response.instruments.map(s => `<option value="${s}">`).join("");
          
          // 如果当前品种不在列表中，添加到开头
          const currentSymbol = els.instrumentSymbol.value.trim().toUpperCase();
          if (currentSymbol && !response.instruments.includes(currentSymbol)) {
            const option = document.createElement("option");
            option.value = currentSymbol;
            datalist.prepend(option);
          }
        }
      } catch (error) {
        console.warn("获取合约列表失败:", error);
      }
    }
    loadInstrumentsList();
    els.windowStart.addEventListener("change", syncCacheKey);
    els.windowEnd.addEventListener("change", syncCacheKey);

    function zoomTimeAxis(factor) {
      const chart = window._lwChartState?.chartInstance;
      if (chart) {
        const range = chart.timeScale().getVisibleLogicalRange?.();
        if (!range) {
          chart.timeScale().fitContent();
          return;
        }
        const center = (range.from + range.to) / 2;
        const span = Math.max(10, (range.to - range.from) * factor);
        chart.timeScale().setVisibleLogicalRange({
          from: center - span / 2,
          to: center + span / 2,
        });
        return;
      }
      if (!state.snapshot?.candles?.length || !state.chartView) {
        return;
      }
      const total = state.snapshot.candles.length;
      const currentSpan = Math.max(20, state.chartView.endIndex - state.chartView.startIndex + 1);
      const targetSpan = Math.max(20, Math.min(total, Math.round(currentSpan * factor)));
      const center = Math.round((state.chartView.startIndex + state.chartView.endIndex) / 2);
      let startIndex = center - Math.floor(targetSpan / 2);
      let endIndex = startIndex + targetSpan - 1;
      if (startIndex < 0) {
        startIndex = 0;
        endIndex = targetSpan - 1;
      }
      if (endIndex >= total) {
        endIndex = total - 1;
        startIndex = Math.max(0, endIndex - targetSpan + 1);
      }
      state.chartView = clampChartView(total, startIndex, endIndex, state.chartView);
      renderChart();
      renderViewportDerivedSurfaces();
    }

    function zoomPriceAxis(factor) {
      if (!state.snapshot?.candles?.length || !state.chartView || state.chartView.yMin == null || state.chartView.yMax == null) {
        return;
      }
      const currentSpan = state.chartView.yMax - state.chartView.yMin;
      const targetSpan = Math.max(0.5, currentSpan * factor);
      const center = (state.chartView.yMin + state.chartView.yMax) / 2;
      state.chartView.yMin = center - targetSpan / 2;
      state.chartView.yMax = center + targetSpan / 2;
      renderChart();
      renderViewportDerivedSurfaces();
    }

    function resetChartView() {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      state.chartView = createDefaultChartView(state.snapshot.candles.length);
      const chart = window._lwChartState?.chartInstance;
      if (chart) {
        chart.timeScale().setVisibleLogicalRange({
          from: state.chartView.startIndex,
          to: state.chartView.endIndex,
        });
      }
      renderChart();
      renderViewportDerivedSurfaces();
    }

    els.zoomInButton?.addEventListener("click", () => zoomTimeAxis(0.6));
    els.zoomOutButton?.addEventListener("click", () => zoomTimeAxis(1.6));
    els.zoomPriceInButton?.addEventListener("click", () => zoomPriceAxis(0.84));
    els.zoomPriceOutButton?.addEventListener("click", () => zoomPriceAxis(1.2));
    els.resetViewButton?.addEventListener("click", () => resetChartView());
    els.chartContainer?.addEventListener("wheel", (event) => {
      if (!state.snapshot?.candles?.length) {
        return;
      }
      event.preventDefault();
      if (event.shiftKey) {
        zoomPriceAxis(event.deltaY < 0 ? 0.84 : 1.2);
        return;
      }
      zoomTimeAxis(event.deltaY < 0 ? 0.8 : 1.25);
    }, { passive: false });

    els.headerMoreButton?.addEventListener("click", () => {
      toggleHeaderMoreMenu();
    });
    els.lookupCacheButton?.addEventListener("click", async () => {
      closeHeaderMoreMenu();
      await lookupCacheFromHeader({ button: els.lookupCacheButton, openViewerOnSuccess: true });
    });
    els.closeCacheViewerButton?.addEventListener("click", () => {
      closeCacheViewer();
    });
    els.refreshCacheViewerButton?.addEventListener("click", async () => {
      if (!String(els.cacheKey?.value || "").trim()) {
        updateCacheViewer();
        renderStatusStrip([{ label: "当前参数还没有缓存键。", variant: "warn" }]);
        return;
      }
      await lookupCacheFromHeader({ button: els.refreshCacheViewerButton, openViewerOnSuccess: false });
    });
    els.invalidateCacheButton?.addEventListener("click", async () => {
      closeHeaderMoreMenu();
      await invalidateCacheFromHeader({ button: els.invalidateCacheButton });
    });
    els.repairChartButton?.addEventListener("click", async () => {
      closeHeaderMoreMenu();
      await runButtonAction(els.repairChartButton, async () => {
        const result = await actions.handleRepairCurrentWindow();
        if (result) {
          markWorkbenchSynced();
          syncBackfillProgressPolling({ force: true });
        }
      }, { silentError: true });
    });
    els.exportSettingsButton?.addEventListener("click", () => {
      exportCurrentSettings();
      renderStatusStrip([{ label: "当前工作台设置已导出。", variant: "good" }]);
      closeHeaderMoreMenu();
    });
    document.addEventListener("click", (event) => {
      const target = event.target;
      if (els.headerMoreMenu && !els.headerMoreMenu.hidden) {
        if (!target?.closest?.("#headerMoreMenu") && !target?.closest?.("#headerMoreButton")) {
          closeHeaderMoreMenu();
        }
      }
      if (target === els.cacheViewerModal) {
        closeCacheViewer();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      closeHeaderMoreMenu();
      closeCacheViewer();
    });

    els.buildButton.addEventListener("click", async () => {
      await runButtonAction(els.buildButton, async () => {
        await runBuildFlow({ forceRefresh: false, syncRelativeWindow: false });
      }, { silentError: true });
    });
    els.refreshAllButton.addEventListener("click", async () => {
      await runButtonAction(els.refreshAllButton, async () => {
        await runBuildFlow({ forceRefresh: true, syncRelativeWindow: true });
      }, { silentError: true });
    });
    els.restoreLayoutButton.addEventListener("click", () => {
      const persistedLayout = readStorage("layout", null);
      if (persistedLayout) {
        state.layout = { ...state.layout, ...persistedLayout };
        renderStatusStrip([{ label: "已恢复上次布局。", variant: "good" }]);
      } else {
        renderStatusStrip([{ label: "还没有可恢复的历史布局。", variant: "warn" }]);
      }
      applyLayoutWidths();
      renderSnapshot();
    });

    els.aiNewThreadButton.addEventListener("click", async () => {
      await runButtonAction(els.aiNewThreadButton, async () => {
        await aiChat.createNewThread();
        renderSnapshot();
      }, {
        lockKey: "ai-new-thread",
        blockedLabel: "正在创建新会话，请稍候。",
      });
    });
    els.aiChatSendButton.addEventListener("click", async () => {
      await dispatchAiComposerSend();
    });
    els.aiChatInput.addEventListener("input", (event) => aiChat.handleComposerInput(event.target.value));
    els.aiChatInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await dispatchAiComposerSend();
      }
    });
    els.eventScribeSendButton?.addEventListener("click", async () => {
      await sendEventScribeMessage({ button: els.eventScribeSendButton });
    });
    els.eventScribeInput?.addEventListener("input", async (event) => {
      const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
      session.draftText = event.target.value;
      session.draft = event.target.value;
      rememberSymbolWorkspaceSession(session);
      renderEventScribePanel();
    });
    els.eventScribeInput?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        await sendEventScribeMessage({ button: els.eventScribeSendButton });
      }
    });
    els.eventScribeMirrorButton?.addEventListener("click", async () => {
      await runButtonAction(els.eventScribeMirrorButton, async () => {
        const analystSession = getSessionByRole(state.topBar?.symbol, "analyst");
        const latestAssistantReply = getLatestAssistantMessage(analystSession);
        const session = await ensureScribeSessionForSymbol(state.topBar?.symbol);
        if (!latestAssistantReply) {
          renderStatusStrip([{ label: "当前还没有可整理的行情分析回复。", variant: "warn" }]);
          return null;
        }
        const nextDraft = `请提取下面这条回复中的关键价位、区域、风险、事件顺序，并整理成可审阅候选项：\n\n${latestAssistantReply.content}`;
        session.draftText = nextDraft;
        session.draft = nextDraft;
        rememberSymbolWorkspaceSession(session);
        if (els.eventScribeInput) {
          els.eventScribeInput.value = nextDraft;
          els.eventScribeInput.focus();
        }
        renderEventScribePanel();
        return true;
      }, {
        lockKey: "event-scribe-mirror",
        blockedLabel: "正在准备事件整理草稿，请稍候。",
      });
    });
    els.eventScribeNewSessionButton?.addEventListener("click", async () => {
      await runButtonAction(els.eventScribeNewSessionButton, async () => {
        await createFreshScribeSession(state.topBar?.symbol);
        renderSnapshot();
      }, {
        lockKey: "event-scribe-new-session",
        blockedLabel: "正在创建事件整理会话，请稍候。",
      });
    });
    if (!eventPanelController) {
      els.eventStreamFilterBar?.querySelectorAll("[data-event-stream-filter]").forEach((button) => {
        button.addEventListener("click", () => {
          state.eventStreamFilter = button.dataset.eventStreamFilter || "all";
          persistWorkbenchState();
          renderChart();
        });
      });
    }
    els.replyExtractionFilterBar?.querySelectorAll("[data-reply-extraction-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        getReplyExtractionState().filter = button.dataset.replyExtractionFilter || "all";
        persistWorkbenchState();
        renderReplyExtractionPanel();
      });
    });
    els.replyExtractionShowIgnoredButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      if (extractionState.pendingOnly) {
        extractionState.pendingOnly = false;
      }
      extractionState.showIgnored = !extractionState.showIgnored;
      persistWorkbenchState();
      renderReplyExtractionPanel();
    });
    els.replyExtractionPendingOnlyButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      extractionState.pendingOnly = true;
      extractionState.showIgnored = false;
      persistWorkbenchState();
      renderReplyExtractionPanel();
      renderStatusStrip([{ label: "事件整理已切换为仅看未处理。", variant: "emphasis" }]);
    });
    els.replyExtractionShowHistoryButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      extractionState.pendingOnly = false;
      extractionState.showIgnored = true;
      persistWorkbenchState();
      renderReplyExtractionPanel();
      renderStatusStrip([{ label: "事件整理已切换为完整历史视图。", variant: "emphasis" }]);
    });
    els.replyExtractionExportButton?.addEventListener("click", () => {
      exportReplyExtractionSummary();
    });
    els.replyExtractionAutoButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      extractionState.autoExtractEnabled = extractionState.autoExtractEnabled === false;
      persistWorkbenchState();
      renderReplyExtractionPanel();
      renderStatusStrip([{
        label: extractionState.autoExtractEnabled ? "事件整理自动记录已开启。" : "事件整理自动记录已关闭（仅保留图上对象）。",
        variant: "emphasis",
      }]);
    });
    els.replyExtractionIntensitySelect?.addEventListener("change", () => {
      const extractionState = getReplyExtractionState();
      extractionState.intensity = els.replyExtractionIntensitySelect.value || "balanced";
      persistWorkbenchState();
      renderReplyExtractionPanel();
      renderStatusStrip([{ label: `事件整理强度已切换为：${extractionState.intensity}`, variant: "emphasis" }]);
    });
    els.replyExtractionBatchConfirmButton?.addEventListener("click", () => {
      applyReplyExtractionBatchAction("confirm");
    });
    els.replyExtractionBatchMountButton?.addEventListener("click", () => {
      applyReplyExtractionBatchAction("mount");
    });
    els.replyExtractionBatchPromoteButton?.addEventListener("click", () => {
      applyReplyExtractionBatchAction("promote-plan");
    });
    els.replyExtractionBatchIgnoreButton?.addEventListener("click", () => {
      applyReplyExtractionBatchAction("ignore");
    });
    els.replyExtractionCollapseButton?.addEventListener("click", () => {
      const extractionState = getReplyExtractionState();
      extractionState.collapsed = !extractionState.collapsed;
      persistWorkbenchState();
      renderReplyExtractionPanel();
      renderStatusStrip([{
        label: extractionState.collapsed ? "事件整理面板已收起。" : "事件整理面板已展开。",
        variant: "emphasis",
      }]);
    });
    els.saveRegionButton?.addEventListener("click", async () => {
      await runButtonAction(els.saveRegionButton, async () => {
        await actions.handleSaveRegion();
        renderSnapshot();
      }, { silentError: true });
    });
    els.saveRegionQuickButton?.addEventListener("click", async () => {
      await runButtonAction(els.saveRegionQuickButton, async () => {
        await actions.handleSaveRegion();
        renderSnapshot();
      }, { silentError: true });
    });
    els.recordEntryButton?.addEventListener("click", async () => {
      await runButtonAction(els.recordEntryButton, async () => {
        await actions.handleRecordEntry();
        renderSnapshot();
      }, { silentError: true });
    });

    els.aiChatThread?.addEventListener("click", async (event) => {
      const button = event.target?.closest("button[data-message-action]");
      if (!button) {
        return;
      }
      const action = button.dataset.messageAction;
      const messageId = button.dataset.messageId;
      if (!messageId || !action) {
        return;
      }
      if (action === "regenerate") {
        await aiChat.regenerateMessage(messageId);
        renderSnapshot();
        return;
      }
      if (action === "prompt-trace") {
        const session = getActiveThread();
        const message = (session?.messages || []).find((item) => item.message_id === messageId) || null;
        void promptTracePanelController.openPromptTraceForMessage({
          promptTraceId: message?.promptTraceId || message?.meta?.promptTraceId || button.dataset.promptTraceId || null,
          messageId,
        });
        return;
      }
      if (["show", "focus", "jump", "unmount"].includes(action)) {
        focusPlanOnChart({
          action,
          messageId,
          sessionId: getActiveThread()?.id || state.activeAiThreadId,
          planId: null,
        });
        return;
      }
      renderSnapshot();
    });

    els.analysisSendCurrentButton.addEventListener("click", async () => {
      await runButtonAction(els.analysisSendCurrentButton, async () => {
        const session = getActiveThread();
        session.analysisTemplate = {
          type: els.analysisTypeSelect.value,
          range: els.analysisRangeSelect.value,
          style: els.analysisStyleSelect.value,
          sendMode: "current",
        };
        persistSessions();
        await aiChat.handlePresetAnalysis(els.analysisTypeSelect.value, `请基于当前${els.analysisRangeSelect.value}做${els.analysisStyleSelect.value}风格分析。`, false);
        renderSnapshot();
      });
    });
    els.analysisSendNewButton.addEventListener("click", async () => {
      await runButtonAction(els.analysisSendNewButton, async () => {
        await aiChat.handlePresetAnalysis(els.analysisTypeSelect.value, `请基于当前${els.analysisRangeSelect.value}做${els.analysisStyleSelect.value}风格分析。`, true);
        renderSnapshot();
      });
    });
    els.gammaAutoDiscoverButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaAutoDiscoverButton, async () => {
        await loadGammaAnalysis({ autoDiscoverLatest: true });
      }, { silentError: true });
    });
    els.gammaLoadButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaLoadButton, async () => {
        await loadGammaAnalysis({ autoDiscoverLatest: false });
      }, { silentError: true });
    });
    els.gammaSendCurrentButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaSendCurrentButton, async () => {
        await sendGammaToChat(false);
        renderSnapshot();
      });
    });
    els.gammaSendNewButton?.addEventListener("click", async () => {
      await runButtonAction(els.gammaSendNewButton, async () => {
        await sendGammaToChat(true);
        renderSnapshot();
      });
    });

    const aiPresetButtons = [
      els.aiKlineAnalysisButton,
      els.recent20BarsButton,
      els.recent20MinutesButton,
      els.focusRegionsButton,
      els.liveDepthButton,
      els.manualRegionButton,
      els.selectedBarButton,
    ].filter(Boolean);

    function setAiPresetButtonsBusy(activeButton, busy) {
      aiPresetButtons.forEach((button) => {
        if (!button) {
          return;
        }
        const isTarget = button === activeButton;
        button.disabled = !!busy;
        button.dataset.busy = busy && isTarget ? "true" : "false";
        button.classList.toggle("is-active", !!busy && isTarget);
      });
    }

    async function runAiPresetButtonAction(button, action) {
      if (button?.dataset.busy === "true") {
        return null;
      }
      setAiPresetButtonsBusy(button, true);
      try {
        return await action();
      } catch (error) {
        console.error("AI 快捷动作失败:", error);
        renderStatusStrip([{ label: error?.message || String(error), variant: "warn" }]);
        return null;
      } finally {
        setAiPresetButtonsBusy(button, false);
      }
    }

    els.recent20BarsButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.recent20BarsButton, async () => {
        await aiChat.handlePresetAnalysis("recent_20_bars", "请分析最近20根K线并给出交易计划。", false);
        renderSnapshot();
      });
    });
    els.recent20MinutesButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.recent20MinutesButton, async () => {
        await aiChat.handlePresetAnalysis("recent_20_minutes", "请分析最近20分钟并给出交易计划。", false);
        renderSnapshot();
      });
    });
    els.focusRegionsButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.focusRegionsButton, async () => {
        await aiChat.handlePresetAnalysis("focus_regions", "请围绕当前重点区域给出计划。", false);
        renderSnapshot();
      });
    });
    els.liveDepthButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.liveDepthButton, async () => {
        await aiChat.handlePresetAnalysis("live_depth", "请结合当前盘口结构给出建议。", false);
        renderSnapshot();
      });
    });
    els.manualRegionButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.manualRegionButton, async () => {
        await aiChat.handlePresetAnalysis("manual_region", aiChat.buildManualRegionAnalysisPrompt(), false);
        renderSnapshot();
      });
    });
    els.selectedBarButton.addEventListener("click", async () => {
      await runAiPresetButtonAction(els.selectedBarButton, async () => {
        await aiChat.handlePresetAnalysis("selected_bar", aiChat.buildSelectedBarAnalysisPrompt(), false);
        renderSnapshot();
      });
    });

    els.annotationManagerButton.addEventListener("click", () => {
      state.annotationPanelOpen = true;
      renderSnapshot();
    });
    els.toggleAnnotationPanelButton.addEventListener("click", () => {
      state.annotationPanelOpen = !state.annotationPanelOpen;
      renderSnapshot();
    });
    els.closeAnnotationPanelButton.addEventListener("click", () => {
      state.annotationPanelOpen = false;
      renderSnapshot();
    });
    els.filterOnlyCurrentSession.addEventListener("change", () => {
      state.annotationFilters.onlyCurrentSession = els.filterOnlyCurrentSession.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterHideCompleted.addEventListener("change", () => {
      state.annotationFilters.hideCompleted = els.filterHideCompleted.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterShowPaths?.addEventListener("change", () => {
      state.annotationFilters.showPaths = els.filterShowPaths.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.filterShowInvalidated?.addEventListener("change", () => {
      state.annotationFilters.showInvalidated = els.filterShowInvalidated.checked;
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationShowSelectedOnlyButton?.addEventListener("click", () => {
      state.annotationFilters.selectedOnly = true;
      state.annotationFilters.annotationIds = state.selectedAnnotationId ? [state.selectedAnnotationId] : ["__none__"];
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationHideAllButton?.addEventListener("click", () => {
      state.annotationFilters.onlyCurrentSession = false;
      state.annotationFilters.sessionIds = [];
      state.annotationFilters.messageIds = [];
      state.annotationFilters.annotationIds = ["__none__"];
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationShowPinnedButton?.addEventListener("click", () => {
      state.annotationFilters.onlyCurrentSession = false;
      state.annotationFilters.sessionIds = [];
      state.annotationFilters.messageIds = [];
      const pinnedIds = state.aiAnnotations
        .filter((item) => item.pinned && !isAnnotationDeleted(item))
        .map((item) => item.id);
      state.annotationFilters.annotationIds = pinnedIds.length ? pinnedIds : ["__none__"];
      writeStorage("annotationFilters", state.annotationFilters);
      renderSnapshot();
    });
    els.annotationFilterResetButton.addEventListener("click", resetAnnotationFilters);

    els.sessionRenameButton?.addEventListener("click", () => {
      const nextTitle = window.prompt("输入会话名称", getActiveThread().title);
      if (nextTitle && nextTitle.trim()) {
        renameActiveThread(nextTitle.trim());
        renderSnapshot();
      }
    });
    els.sessionPinButton?.addEventListener("click", () => {
      togglePinActiveThread();
      renderSnapshot();
    });
    els.sessionDeleteButton?.addEventListener("click", () => {
      if (window.confirm("确认归档当前会话？")) {
        deleteActiveThread();
        renderSnapshot();
      }
    });
    els.sessionMoreButton?.addEventListener("click", async () => {
      await runButtonAction(els.sessionMoreButton, async () => {
        if (!els.sessionMoreMenu) {
          return null;
        }
        const willOpen = els.sessionMoreMenu.hidden;
        if (!willOpen) {
          els.sessionMoreMenu.hidden = true;
          return true;
        }
        els.sessionMoreMenu.hidden = false;
        renderSnapshot();
        if (syncSessionsFromServer) {
          try {
            await syncSessionsFromServer({ activateFirst: false });
            renderSnapshot();
            els.sessionMoreMenu.hidden = false;
          } catch (error) {
            console.warn("刷新会话工作区失败:", error);
          }
        }
        els.sessionMoreMenu.querySelector("[data-session-search-input]")?.focus();
        return true;
      }, {
        lockKey: "session-more-menu",
        blockedLabel: "会话列表正在刷新，请稍候。",
      });
    });
    els.clearPinnedPlanButton?.addEventListener("click", () => {
      state.pinnedPlanId = null;
      const session = getActiveThread();
      session.activePlanId = null;
      persistSessions();
      renderSnapshot();
    });

    els.addAttachmentButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择要附加到当前会话的文件。", accept: defaultAttachmentAccept });
    });
    els.attachmentInput?.addEventListener("change", async () => {
      const files = Array.from(els.attachmentInput.files || []);
      try {
        const mapped = await Promise.all(files.map((file) => mapFileToAttachment(file)));
        addAttachments(mapped);
        renderStatusStrip([{ label: mapped.length ? `已添加 ${mapped.length} 个附件。` : "未选择附件。", variant: mapped.length ? "good" : "warn" }]);
        renderSnapshot();
        focusComposerInput();
      } catch (error) {
        renderStatusStrip([{ label: error.message || "读取附件失败。", variant: "warn" }]);
      } finally {
        els.attachmentInput.value = "";
        els.attachmentInput.setAttribute("accept", defaultAttachmentAccept);
      }
    });
    els.chartScreenshotButton?.addEventListener("click", async () => {
      await runButtonAction(els.chartScreenshotButton, async () => {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      }, {
        lockKey: "chart-screenshot-attachment",
        extraBusyTargets: screenshotAttachmentButtons,
      });
    });
    els.chartToolbarScreenshotButton?.addEventListener("click", async () => {
      await runButtonAction(els.chartToolbarScreenshotButton, async () => {
        await addChartScreenshotAttachment("已把图表截图加入当前会话附件。");
      }, {
        lockKey: "chart-screenshot-attachment",
        extraBusyTargets: screenshotAttachmentButtons,
      });
    });
    els.externalScreenshotButton?.addEventListener("click", () => {
      openAttachmentPicker({ statusLabel: "选择一张外部截图图片。", accept: "image/*" });
    });
    els.clearAttachmentsButton?.addEventListener("click", () => {
      clearAttachments();
      renderStatusStrip([{ label: "当前会话附件已清空。", variant: "emphasis" }]);
      renderSnapshot();
    });

    modelSwitcherController.bindModelSwitcherActions();
    annotationPopoverController.bindAnnotationPopoverActions();

    els.rightResizeHandle.addEventListener("mousedown", (event) => {
      if (!isDockedAiLayout()) {
        return;
      }
      const startX = event.clientX;
      const startWidth = state.layout.chatWidth;
      const onMove = (moveEvent) => {
        state.layout.chatWidth = Math.max(
          DESKTOP_SIDEBAR_MIN,
          Math.min(DESKTOP_SIDEBAR_MAX, startWidth - (moveEvent.clientX - startX)),
        );
        applyLayoutWidths();
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
    const drawerButtons = [
      [els.drawerContextButton, els.drawerContextPanel, "context"],
      [els.drawerManualButton, els.drawerManualPanel, "manual"],
      [els.drawerFocusButton, els.drawerFocusPanel, "focus"],
      [els.drawerStrategyButton, els.drawerStrategyPanel, "strategy"],
      [els.drawerEntriesButton, els.drawerEntriesPanel, "entries"],
      [els.drawerRecapButton, els.drawerRecapPanel, "recap"],
      [els.drawerGammaButton, els.drawerGammaPanel, "gamma"],
    ];
    drawerButtons.forEach(([button, panel, key]) => {
      button?.addEventListener("click", () => {
        setDrawerOpen(key, !state.drawerState[key]);
      });
      if (panel) {
        panel.style.display = state.drawerState[key] ? "block" : "none";
      }
    });
    syncDrawerTabState();
    syncBottomDrawerVisibility();

    els.chartEventRail?.addEventListener("click", (event) => {
      const button = event.target?.closest("[data-event-cluster-key]");
      if (!button) {
        return;
      }
      const clusterKey = button.dataset.eventClusterKey;
      if (!clusterKey) {
        return;
      }
      selectChartEventCluster(clusterKey, {
        centerChart: true,
        openContext: true,
        announce: true,
      });
    });

    [
      els.layerLargeOrders,
      els.layerAbsorption,
      els.layerIceberg,
      els.layerReplenishment,
      els.layerEvents,
      els.layerFocusRegions,
      els.layerManualRegions,
      els.layerOperatorEntries,
      els.layerAiAnnotations,
    ].forEach((input) => {
      input?.addEventListener("change", () => {
        persistLayerState();
        renderSnapshot();
      });
    });

    // 按钮绑定已在 replay_workbench_bindings.js 中处理，这里只处理 sendViewportButton
    if (els.sendViewportButton) {
      els.sendViewportButton.addEventListener("click", async () => {
        await runButtonAction(els.sendViewportButton, async () => {
          const summary = els.chartViewportMeta?.textContent || "当前可视区域";
          const session = getActiveThread();
          await aiChat.handleAiChat("general", `请基于当前图表可视区域继续分析：${summary}`, {
            id: session.id,
            title: session.title,
            symbol: session.symbol,
            contractId: session.contractId,
            timeframe: session.timeframe,
            windowRange: session.windowRange,
          });
          renderSnapshot();
        });
      });
    }

    els.chartSvg.addEventListener("click", (event) => {
      const target = event.target.closest("[data-annotation-id]");
      if (!target) {
        annotationPopoverController.hideAnnotationPopover();
        return;
      }
      handleAnnotationObjectAction("detail", target.dataset.annotationId);
    });
  }

  async function bootstrap() {
    const now = new Date();
    const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    if (!els.windowStart.value) {
      els.windowStart.value = toLocalInputValue(start);
    }
    if (!els.windowEnd.value) {
      els.windowEnd.value = toLocalInputValue(now);
    }
    els.instrumentSymbol.value = state.topBar.symbol;
    els.displayTimeframe.value = state.topBar.timeframe;
    els.quickRangeSelect.value = state.topBar.quickRange;
    applyLayerStateToInputs();
    syncCacheKey();
    try {
      await syncSessionsFromServer({ activateFirst: false, symbol: state.topBar.symbol });
    } catch (error) {
      console.warn("从后端同步会话失败:", error);
    }
    const restoredActiveSession = state.aiThreads.find((item) => item.id === state.activeAiThreadId);
    if (restoredActiveSession && getWorkspaceRole(restoredActiveSession) === "analyst") {
      rememberSymbolWorkspaceSession(restoredActiveSession);
    }
    try {
      await activateSymbolWorkspace(state.topBar.symbol);
    } catch (error) {
      console.warn("初始化按品种工作区失败:", error);
      const fallbackSession = getPreferredSessionForSymbol(state.topBar.symbol, { workspaceRole: "analyst" }) || state.aiThreads[0];
      if (fallbackSession) {
        setActiveThread(fallbackSession.id, fallbackSession.title, fallbackSession);
      }
    }
    await eventPanelController?.syncActiveSessionEventStream({ force: true, reason: "bootstrap" });
    await eventOutcomeController?.syncActiveSessionOutcomes({ force: true });
    renderSnapshot();
  }

  return {
    state,
    els,
    ensureChartView,
    rememberCurrentChartView,
    buildCacheKey,
    syncCacheKey,
    renderSnapshot,
    updateHeaderStatus,
    renderViewportDerivedSurfaces,
    getReplyExtractionClusterSummaryMap,
    selectChartEventCluster,
    renderEventPanel: () => eventPanelController?.renderEventPanel(),
    syncActiveSessionEventStream: (options = {}) => eventPanelController?.syncActiveSessionEventStream(options),
    handleEventOverlayClick: (eventId) => eventPanelController?.handleOverlayEventClick(eventId),
    handleEventOverlayEnter: (eventId) => eventPanelController?.handleOverlayEventEnter(eventId),
    handleEventOverlayLeave: () => eventPanelController?.handleOverlayEventLeave(),
    handleManualToolPointer: (pointer) => manualEventTools?.setLastPointer(pointer),
    attachBindings,
    bootstrap,
    handleBuild: actions.handleBuild,
  };
}
