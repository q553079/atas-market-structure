export function createAiReviewRenderer({ state, els, escapeHtml, renderList }) {
  function renderAiReview() {
    const reviewResult = state.aiReview;
    if (!reviewResult) {
      els.aiReview.className = "empty-note";
      els.aiReview.textContent = state.currentReplayIngestionId
        ? "当前 replay 还没有 AI 复盘。点击“AI 分析”生成或复用。"
        : "当前还没有可分析的 replay。先构建回放。";
      return;
    }

    const review = reviewResult.review;
    const keyZonesHtml = review.key_zones?.length
      ? review.key_zones.map((zone) => `
          <div class="info-card">
            <h4>${escapeHtml(zone.label)}</h4>
            <p class="mono">${escapeHtml(zone.zone_low.toFixed(2))} - ${escapeHtml(zone.zone_high.toFixed(2))}</p>
            <p>角色=${escapeHtml(zone.role)} 强度=${escapeHtml(zone.strength_score.toFixed(2))}</p>
            ${renderList(zone.evidence)}
          </div>
        `).join("")
      : `<div class="empty-note">AI 没有返回重点区域。</div>`;
    const invalidationsHtml = review.invalidations?.length
      ? review.invalidations.map((item) => `
          <div class="info-card">
            <h4>${escapeHtml(item.label)}</h4>
            <p class="mono">${escapeHtml(item.price.toFixed(2))}</p>
            <p>${escapeHtml(item.reason)}</p>
          </div>
        `).join("")
      : `<div class="empty-note">AI 没有返回失效位。</div>`;
    const entryReviewsHtml = review.entry_reviews?.length
      ? review.entry_reviews.map((entryReview) => `
          <div class="info-card">
            <h4>${escapeHtml(entryReview.entry_id)} / ${escapeHtml(entryReview.verdict)}</h4>
            <p class="mono">上下文匹配=${escapeHtml(entryReview.context_alignment_score.toFixed(2))}</p>
            <h4>理由</h4>
            ${renderList(entryReview.rationale)}
            <h4>问题</h4>
            ${renderList(entryReview.mistakes)}
            <h4>更好条件</h4>
            ${renderList(entryReview.better_conditions)}
          </div>
        `).join("")
      : `<div class="empty-note">当前 AI 复盘还没有逐条开仓评价。</div>`;

    els.aiReview.className = "card-list";
    els.aiReview.innerHTML = `
      <div class="info-card">
        <h4>总结</h4>
        <p>${escapeHtml(review.narrative_summary)}</p>
      </div>
      <div class="info-card">
        <h4>优先剧本</h4>
        <p class="mono">${escapeHtml(review.script_review.preferred_script)}</p>
        <h4>偏好理由</h4>
        ${renderList(review.script_review.preferred_rationale)}
        <h4>延续条件</h4>
        ${renderList(review.script_review.continuation_case)}
        <h4>反转条件</h4>
        ${renderList(review.script_review.reversal_case)}
      </div>
      <div class="info-card">
        <h4>模型来源</h4>
        <p class="mono">${escapeHtml(reviewResult.provider)} / ${escapeHtml(reviewResult.model)}</p>
        <p class="mono">保存时间=${escapeHtml(new Date(reviewResult.stored_at).toLocaleString())}</p>
      </div>
      ${entryReviewsHtml}
      ${keyZonesHtml}
      ${invalidationsHtml}
      <div class="info-card">
        <h4>禁止开仓提示</h4>
        ${renderList(review.no_trade_guidance)}
      </div>
      <div class="info-card">
        <h4>操作员关注点</h4>
        ${renderList(review.operator_focus)}
      </div>
      <div class="info-card">
        <h4>未解决冲突</h4>
        ${renderList(review.unresolved_conflicts)}
      </div>
    `;
  }

  return {
    renderAiReview,
  };
}
