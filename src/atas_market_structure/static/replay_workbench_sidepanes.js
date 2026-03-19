export function createSidepaneRenderer({ state, els, escapeHtml, renderList, translateAction, translateVerificationStatus, translateAcquisitionMode }) {
  function renderBuildSummary() {
    const result = state.buildResponse;
    if (!result) {
      els.buildSummary.className = "empty-note";
      els.buildSummary.textContent = "还没有构建结果。";
      return;
    }

    const summaryParts = [
      `<div class="info-card"><h4>构建动作</h4><p class="mono">${escapeHtml(translateAction(result.action))}</p></div>`,
      `<div class="info-card"><h4>原因</h4><p>${escapeHtml(result.reason)}</p></div>`,
      `<div class="info-card"><h4>本地连续流消息</h4><p class="mono">${escapeHtml(String(result.local_message_count))}</p></div>`,
    ];

    if (result.summary) {
      summaryParts.push(
        `<div class="info-card"><h4>核对状态</h4><p class="mono">${escapeHtml(translateVerificationStatus(result.summary.verification_status))} / ${escapeHtml(String(result.summary.verification_count))}</p></div>`,
        `<div class="info-card"><h4>采集来源</h4><p class="mono">${escapeHtml(translateAcquisitionMode(result.summary.acquisition_mode))}</p></div>`,
        `<div class="info-card"><h4>K 线数量</h4><p class="mono">${escapeHtml(String(result.summary.candle_count))}</p></div>`,
      );
    }

    const digest = state.snapshot?.raw_features?.history_footprint_digest;
    if (digest) {
      summaryParts.push(
        `<div class="info-card"><h4>历史足迹摘要</h4><p class="mono">bars=${escapeHtml(String(digest.bar_count || 0))} price_levels=${escapeHtml(String(digest.price_level_count || 0))}</p></div>`,
      );
    }

    if (result.atas_fetch_request) {
      summaryParts.push(
        `<div class="info-card"><h4>需要向 ATAS 补抓</h4><p class="mono">${escapeHtml(JSON.stringify(result.atas_fetch_request, null, 2))}</p></div>`,
      );
    }

    els.buildSummary.className = "meta-grid";
    els.buildSummary.innerHTML = summaryParts.join("");
  }

  function renderFocusRegions() {
    const focusRegions = state.snapshot?.focus_regions || [];
    els.focusRegions.innerHTML = "";
    if (!focusRegions.length) {
      els.focusRegions.innerHTML = `<div class="empty-note">当前回放没有重点区域。</div>`;
      return;
    }
    focusRegions.forEach((region) => {
      const card = document.createElement("div");
      card.className = "info-card";
      card.innerHTML = `
        <h4>${escapeHtml(region.label)}</h4>
        <p class="mono">${escapeHtml(region.price_low.toFixed(2))} - ${escapeHtml(region.price_high.toFixed(2))}</p>
        <p>优先级=${escapeHtml(String(region.priority))}</p>
        ${renderList(region.reason_codes)}
        ${renderList(region.notes)}
      `;
      els.focusRegions.appendChild(card);
    });
  }

  function renderStrategyCandidates() {
    const candidates = state.snapshot?.strategy_candidates || [];
    els.strategyCandidates.innerHTML = "";
    if (!candidates.length) {
      els.strategyCandidates.innerHTML = `<div class="empty-note">当前 replay 没有匹配到策略卡片。</div>`;
      return;
    }
    candidates.forEach((candidate) => {
      const card = document.createElement("div");
      card.className = "info-card";
      card.innerHTML = `
        <h4>${escapeHtml(candidate.title)}</h4>
        <p class="mono">${escapeHtml(candidate.strategy_id)}</p>
        <p class="mono">${escapeHtml(candidate.source_path)}</p>
        ${renderList(candidate.why_relevant)}
      `;
      els.strategyCandidates.appendChild(card);
    });
  }

  function renderOperatorEntries() {
    const entries = state.operatorEntries || [];
    els.operatorEntries.innerHTML = "";
    if (!entries.length) {
      els.operatorEntries.innerHTML = `<div class="empty-note">当前 replay 还没有记录开仓。</div>`;
      return;
    }
    entries.forEach((entry) => {
      const card = document.createElement("div");
      card.className = "info-card";
      card.innerHTML = `
        <h4>${escapeHtml(entry.side === "buy" ? "多头" : "空头")} @ ${escapeHtml(entry.entry_price.toFixed(2))}</h4>
        <p class="mono">${escapeHtml(new Date(entry.executed_at).toLocaleString())}</p>
        <p class="mono">数量=${escapeHtml(String(entry.quantity ?? ""))} 止损=${escapeHtml(entry.stop_price != null ? entry.stop_price.toFixed(2) : "n/a")}</p>
        <p>${escapeHtml(entry.thesis || "")}</p>
        ${renderList(entry.context_notes)}
      `;
      els.operatorEntries.appendChild(card);
    });
  }

  function renderManualRegions() {
    const regions = state.manualRegions || [];
    els.manualRegions.innerHTML = "";
    if (!regions.length) {
      els.manualRegions.innerHTML = `<div class="empty-note">当前还没有手工区域。点击“开始框选区域”，在图上拖出一个时间-价格区域后保存。</div>`;
      return;
    }
    regions.forEach((region) => {
      const card = document.createElement("div");
      card.className = "info-card";
      card.innerHTML = `
        <h4>${escapeHtml(region.label)}</h4>
        <p class="mono">${escapeHtml(Number(region.price_low).toFixed(2))} - ${escapeHtml(Number(region.price_high).toFixed(2))}</p>
        <p class="mono">${escapeHtml(new Date(region.started_at).toLocaleString())} -> ${escapeHtml(new Date(region.ended_at).toLocaleString())}</p>
        <p>${escapeHtml(region.thesis)}</p>
        ${renderList(region.notes)}
        ${renderList(region.tags)}
      `;
      els.manualRegions.appendChild(card);
    });
  }

  function renderSelectedCandle() {
    const snapshot = state.snapshot;
    const candle = snapshot?.candles?.[state.selectedCandleIndex ?? -1];
    if (!candle) {
      els.selectedCandle.className = "empty-note";
      els.selectedCandle.textContent = "点击图上的 K 线，查看该 bar 的 OHLC、bid/ask、delta 和 footprint 细节。";
      return;
    }
    const detail = state.selectedFootprintBar;
    els.selectedCandle.className = "card-list";
    els.selectedCandle.innerHTML = `
      <div class="info-card">
        <h4>${escapeHtml(new Date(candle.started_at).toLocaleString())}</h4>
        <p class="mono">O ${escapeHtml(Number(candle.open).toFixed(2))} H ${escapeHtml(Number(candle.high).toFixed(2))} L ${escapeHtml(Number(candle.low).toFixed(2))} C ${escapeHtml(Number(candle.close).toFixed(2))}</p>
        <p class="mono">成交量=${escapeHtml(String(candle.volume ?? "n/a"))} Delta=${escapeHtml(String(candle.delta ?? "n/a"))} Bid=${escapeHtml(String(candle.bid_volume ?? "n/a"))} Ask=${escapeHtml(String(candle.ask_volume ?? "n/a"))}</p>
        ${detail?.price_levels ? `<p class="mono">足迹价位层数=${escapeHtml(String(detail.price_levels.length))}</p>` : ""}
        ${detail?.error ? `<p>${escapeHtml(detail.error)}</p>` : ""}
      </div>
    `;
  }

  function renderFootprintLadder() {
    const detail = state.selectedFootprintBar;
    if (!detail || detail.error) {
      els.footprintLadder.className = "empty-note";
      els.footprintLadder.textContent = detail?.error || "历史 footprint 细节会在选中 K 线后加载。";
      return;
    }
    const levels = detail.price_levels || [];
    if (!levels.length) {
      els.footprintLadder.className = "empty-note";
      els.footprintLadder.textContent = "当前 bar 没有历史 footprint 价位明细。";
      return;
    }
    const rows = levels.slice(0, 120).map((level) => `
      <div class="ladder-row">
        <span class="price">${escapeHtml(Number(level.price).toFixed(2))}</span>
        <span class="bid">${escapeHtml(String(level.bid_volume ?? 0))}</span>
        <span class="ask">${escapeHtml(String(level.ask_volume ?? 0))}</span>
        <span>${escapeHtml(String(level.delta ?? 0))}</span>
      </div>
    `).join("");
    els.footprintLadder.className = "ladder";
    els.footprintLadder.innerHTML = `
      <div class="ladder-header">
        <span>价位</span>
        <span>Bid</span>
        <span>Ask</span>
        <span>Delta</span>
      </div>
      ${rows}
    `;
  }

  function renderAiBriefing() {
    const briefing = state.snapshot?.ai_briefing;
    if (!briefing) {
      els.aiBriefing.className = "empty-note";
      els.aiBriefing.textContent = "当前回放还没有 AI 简报。";
      return;
    }
    els.aiBriefing.className = "card-list";
    els.aiBriefing.innerHTML = `
      <div class="info-card">
        <h4>任务目标</h4>
        <p>${escapeHtml(briefing.objective)}</p>
      </div>
      <div class="info-card">
        <h4>重点问题</h4>
        ${renderList(briefing.focus_questions)}
      </div>
      <div class="info-card">
        <h4>要求输出</h4>
        ${renderList(briefing.required_outputs)}
      </div>
      <div class="info-card">
        <h4>备注</h4>
        ${renderList(briefing.notes)}
      </div>
    `;
  }

  function renderEventTimeline() {
    const events = state.snapshot?.event_annotations || [];
    els.eventTimeline.innerHTML = "";
    if (!events.length) {
      els.eventTimeline.innerHTML = `<div class="empty-note">当前 replay 没有事件标注。</div>`;
      return;
    }
    events.forEach((event) => {
      const card = document.createElement("div");
      card.className = "info-card";
      const priceText = event.price != null
        ? event.price.toFixed(2)
        : `${Number(event.price_low ?? 0).toFixed(2)} - ${Number(event.price_high ?? 0).toFixed(2)}`;
      card.innerHTML = `
        <h4>${escapeHtml(event.event_kind)}</h4>
        <p class="mono">${escapeHtml(new Date(event.observed_at).toLocaleString())}</p>
        <p class="mono">${escapeHtml(priceText)}</p>
        ${renderList(event.notes)}
      `;
      els.eventTimeline.appendChild(card);
    });
  }

  return {
    renderBuildSummary,
    renderFocusRegions,
    renderStrategyCandidates,
    renderOperatorEntries,
    renderManualRegions,
    renderSelectedCandle,
    renderFootprintLadder,
    renderAiBriefing,
    renderEventTimeline,
  };
}
