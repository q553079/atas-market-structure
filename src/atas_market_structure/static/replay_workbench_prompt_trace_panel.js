import { escapeHtml, summarizeText } from "./replay_workbench_ui_utils.js";

function isDevelopmentMode() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("debug") === "1" || params.get("dev") === "1") {
      return true;
    }
  } catch {}
  const host = String(window.location.hostname || "").trim().toLowerCase();
  return host === "localhost" || host === "127.0.0.1";
}

function formatValue(value, { fallback = "--", maxChars = 240 } = {}) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return fallback;
    }
    return value.map((item) => formatValue(item, { fallback: "" })).filter(Boolean).join(", ");
  }
  if (typeof value === "object") {
    try {
      const rendered = JSON.stringify(value, null, 2);
      return rendered.length > maxChars ? `${rendered.slice(0, maxChars)}...` : rendered;
    } catch {
      return fallback;
    }
  }
  const text = String(value);
  return text.length > maxChars ? `${text.slice(0, maxChars)}...` : text;
}

function formatDateTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function jsonPreview(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function buildChip(label, {
  clickable = false,
  dataEventId = "",
} = {}) {
  return `<button type="button" class="prompt-trace-chip${clickable ? " is-clickable secondary tiny" : ""}" ${clickable ? `data-trace-event-id="${escapeHtml(dataEventId)}"` : "disabled"}>${escapeHtml(label)}</button>`;
}

function buildChipRow(items = [], formatter = (item) => formatValue(item)) {
  const values = Array.isArray(items) ? items : [];
  if (!values.length) {
    return `<p class="prompt-trace-meta-line">暂无。</p>`;
  }
  return `<div class="prompt-trace-chip-row">${values.map((item) => `<span class="prompt-trace-chip">${escapeHtml(formatter(item))}</span>`).join("")}</div>`;
}

function buildEventChipRow(trace, onEventSelected) {
  const eventIds = Array.isArray(trace?.attached_event_ids) ? trace.attached_event_ids : [];
  if (!eventIds.length) {
    return `<p class="prompt-trace-meta-line">本轮尚未绑定正式事件对象。</p>`;
  }
  return `
    <div class="prompt-trace-chip-row">
      ${eventIds.map((eventId) => {
        if (typeof onEventSelected === "function") {
          return buildChip(eventId, { clickable: true, dataEventId: eventId });
        }
        return `<span class="prompt-trace-chip">${escapeHtml(eventId)}</span>`;
      }).join("")}
    </div>
  `;
}

function buildKeyValueMarkup(summary = {}, {
  emptyLabel = "暂无摘要。",
  keys = null,
} = {}) {
  if (!summary || typeof summary !== "object") {
    return `<p class="prompt-trace-meta-line">${escapeHtml(emptyLabel)}</p>`;
  }
  const entries = Object.entries(summary)
    .filter(([key, value]) => value !== null && value !== undefined && value !== "" && (!Array.isArray(value) || value.length))
    .filter(([key]) => !Array.isArray(keys) || keys.includes(key));
  if (!entries.length) {
    return `<p class="prompt-trace-meta-line">${escapeHtml(emptyLabel)}</p>`;
  }
  return `
    <div class="prompt-trace-kv-list">
      ${entries.map(([key, value]) => `
        <div class="prompt-trace-kv-row">
          <span>${escapeHtml(key)}</span>
          <strong>${escapeHtml(formatValue(value, { maxChars: 360 }))}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function buildPromptPreviewCard(title, text = "") {
  const normalizedText = String(text || "").trim();
  if (!normalizedText) {
    return `
      <section class="prompt-trace-section">
        <h4>${escapeHtml(title)}</h4>
        <p class="prompt-trace-meta-line">无内容。</p>
      </section>
    `;
  }
  return `
    <section class="prompt-trace-section">
      <h4>${escapeHtml(title)}</h4>
      <p class="prompt-trace-meta-line">${escapeHtml(`${normalizedText.length} chars`)}</p>
      <pre class="prompt-trace-prompt-preview">${escapeHtml(summarizeText(normalizedText, 900))}</pre>
    </section>
  `;
}

function buildPromptBlockCards(blocks = []) {
  const items = Array.isArray(blocks) ? blocks : [];
  if (!items.length) {
    return `<div class="prompt-trace-empty">当前没有 prompt block 摘要。</div>`;
  }
  return items.map((block) => `
    <article class="prompt-trace-block-card">
      <div class="prompt-trace-block-head">
        <div>
          <h5>${escapeHtml(block.title || block.kind || "Prompt Block")}</h5>
          <p class="prompt-trace-meta-line">${escapeHtml(block.preview_text || block.previewText || "无预览")}</p>
        </div>
        <span class="prompt-trace-block-kind">${escapeHtml(block.kind || "unknown")}</span>
      </div>
      ${buildKeyValueMarkup(block.payload_summary || {}, { emptyLabel: "此 block 没有额外 payload 摘要。" })}
    </article>
  `).join("");
}

function buildSnapshotMarkup(trace, expandedSnapshot, developmentMode) {
  if (!trace) {
    return "";
  }
  const truncation = trace.metadata?.truncation || {};
  const requestSnapshot = trace.snapshot?.request_snapshot || {};
  return `
    <section class="prompt-trace-section">
      <h4>输入快照</h4>
      <p class="prompt-trace-meta-line">默认展示摘要；需要时再展开完整 snapshot。${developmentMode ? " 开发模式下会显示更多调试摘要。" : ""}</p>
      ${buildKeyValueMarkup({
        transport_mode: requestSnapshot.transport_mode,
        selected_block_count: Array.isArray(trace.selected_block_ids) ? trace.selected_block_ids.length : 0,
        pinned_block_count: Array.isArray(trace.pinned_block_ids) ? trace.pinned_block_ids.length : 0,
        attached_event_count: Array.isArray(trace.attached_event_ids) ? trace.attached_event_ids.length : 0,
        truncation_keys: Object.keys(truncation || {}),
      }, { emptyLabel: "当前没有额外 snapshot 摘要。" })}
      ${expandedSnapshot ? `<pre class="prompt-trace-json-preview">${escapeHtml(jsonPreview({
        snapshot: trace.snapshot || {},
        metadata: developmentMode ? (trace.metadata || {}) : { truncation: trace.metadata?.truncation || {} },
      }))}</pre>` : ""}
    </section>
  `;
}

export function createWorkbenchPromptTracePanelController({
  state,
  els,
  fetchJson,
  renderStatusStrip,
  jumpToMessage = null,
  onEventSelected = null,
}) {
  const developmentMode = isDevelopmentMode();
  let actionsBound = false;

  function getPanelState() {
    if (!state.promptTracePanel || typeof state.promptTracePanel !== "object") {
      state.promptTracePanel = {
        open: false,
        loading: false,
        promptTraceId: null,
        messageId: null,
        trace: null,
        error: null,
        expandedSnapshot: false,
      };
    }
    return state.promptTracePanel;
  }

  function closePromptTrace() {
    const panelState = getPanelState();
    panelState.open = false;
    renderPromptTracePanel();
  }

  function renderPromptTracePanel() {
    const panelState = getPanelState();
    const trace = panelState.trace;
    if (els.promptTraceModal) {
      els.promptTraceModal.classList.toggle("is-hidden", !panelState.open);
    }
    if (els.promptTraceJumpMessageButton) {
      els.promptTraceJumpMessageButton.disabled = !panelState.messageId;
    }
    if (els.promptTraceToggleSnapshotButton) {
      els.promptTraceToggleSnapshotButton.disabled = !trace;
      els.promptTraceToggleSnapshotButton.textContent = panelState.expandedSnapshot ? "收起快照" : "展开快照";
    }
    if (!els.promptTraceSummary || !els.promptTraceBlocks || !els.promptTraceSnapshot) {
      return;
    }
    if (panelState.loading) {
      if (els.promptTraceTitle) {
        els.promptTraceTitle.textContent = "Prompt Trace";
      }
      if (els.promptTraceMeta) {
        els.promptTraceMeta.textContent = "正在加载本轮 Prompt Trace…";
      }
      els.promptTraceSummary.innerHTML = `<div class="prompt-trace-empty">正在读取 prompt、bars、blocks、memory 和事件引用…</div>`;
      els.promptTraceBlocks.innerHTML = "";
      els.promptTraceSnapshot.innerHTML = "";
      return;
    }
    if (panelState.error) {
      if (els.promptTraceTitle) {
        els.promptTraceTitle.textContent = "Prompt Trace";
      }
      if (els.promptTraceMeta) {
        els.promptTraceMeta.textContent = "Prompt Trace 不可用。";
      }
      els.promptTraceSummary.innerHTML = `<div class="prompt-trace-error">${escapeHtml(panelState.error)}</div>`;
      els.promptTraceBlocks.innerHTML = "";
      els.promptTraceSnapshot.innerHTML = "";
      return;
    }
    if (!trace) {
      if (els.promptTraceTitle) {
        els.promptTraceTitle.textContent = "Prompt Trace";
      }
      if (els.promptTraceMeta) {
        els.promptTraceMeta.textContent = "当前没有可展示的 Prompt Trace。";
      }
      els.promptTraceSummary.innerHTML = `<div class="prompt-trace-empty">当前消息还没有 Prompt Trace，或该消息产生于旧版本流程。</div>`;
      els.promptTraceBlocks.innerHTML = "";
      els.promptTraceSnapshot.innerHTML = "";
      return;
    }

    if (els.promptTraceTitle) {
      els.promptTraceTitle.textContent = `Prompt Trace · ${trace.analysis_type || "general"}`;
    }
    if (els.promptTraceMeta) {
      const metaParts = [
        `${trace.symbol || "--"} / ${trace.timeframe || "--"}`,
        `message=${trace.message_id || "--"}`,
        `trace=${trace.prompt_trace_id || "--"}`,
        `created=${formatDateTime(trace.created_at)}`,
      ];
      els.promptTraceMeta.textContent = metaParts.join(" · ");
    }

    els.promptTraceSummary.innerHTML = `
      <section class="prompt-trace-section">
        <h4>分析摘要</h4>
        ${buildKeyValueMarkup({
          schema_version: trace.schema_version,
          analysis_type: trace.analysis_type,
          analysis_range: trace.analysis_range,
          analysis_style: trace.analysis_style,
          model_name: trace.model_name,
          prompt_trace_id: developmentMode ? trace.prompt_trace_id : null,
          model_input_hash: developmentMode ? trace.model_input_hash : `${String(trace.model_input_hash || "").slice(0, 16)}...`,
          created_at: formatDateTime(trace.created_at),
          updated_at: formatDateTime(trace.updated_at),
        }, { emptyLabel: "当前没有基础分析摘要。" })}
      </section>
      <section class="prompt-trace-section">
        <h4>事件与 Blocks</h4>
        <p class="prompt-trace-meta-line">Selected Blocks</p>
        ${buildChipRow(trace.selected_block_ids)}
        <p class="prompt-trace-meta-line">Pinned Blocks</p>
        ${buildChipRow(trace.pinned_block_ids)}
        <p class="prompt-trace-meta-line">Attached Events</p>
        ${buildEventChipRow(trace, onEventSelected)}
      </section>
      <section class="prompt-trace-section">
        <h4>Bars / 选区</h4>
        ${buildKeyValueMarkup(trace.bar_window_summary || {}, { emptyLabel: "没有 bars window 摘要。" })}
        ${buildKeyValueMarkup(trace.manual_selection_summary || {}, { emptyLabel: "没有手工选区摘要。" })}
      </section>
      <section class="prompt-trace-section">
        <h4>Memory / Context</h4>
        ${buildKeyValueMarkup(trace.memory_summary || {}, { emptyLabel: "没有 memory/context 摘要。" })}
      </section>
      ${buildPromptPreviewCard("System Prompt 摘要", trace.final_system_prompt)}
      ${buildPromptPreviewCard("User Prompt 摘要", trace.final_user_prompt)}
    `;
    els.promptTraceBlocks.innerHTML = buildPromptBlockCards(trace.prompt_block_summaries || []);
    els.promptTraceSnapshot.innerHTML = buildSnapshotMarkup(trace, panelState.expandedSnapshot, developmentMode);
  }

  async function fetchPromptTrace({ promptTraceId = null, messageId = null } = {}) {
    if (!fetchJson) {
      throw new Error("当前环境没有可用的 Prompt Trace API 客户端。");
    }
    if (promptTraceId) {
      return fetchJson(`/api/v1/workbench/prompt-traces/${encodeURIComponent(promptTraceId)}`);
    }
    if (messageId) {
      return fetchJson(`/api/v1/workbench/messages/${encodeURIComponent(messageId)}/prompt-trace`);
    }
    throw new Error("Prompt Trace 缺少 prompt_trace_id 或 message_id。");
  }

  async function openPromptTrace({ promptTraceId = null, messageId = null } = {}) {
    const panelState = getPanelState();
    panelState.open = true;
    panelState.loading = true;
    panelState.error = null;
    panelState.trace = null;
    panelState.promptTraceId = promptTraceId || null;
    panelState.messageId = messageId || null;
    panelState.expandedSnapshot = false;
    renderPromptTracePanel();
    try {
      const response = await fetchPromptTrace({ promptTraceId, messageId });
      const trace = response?.trace || response?.prompt_trace || null;
      if (!trace) {
        throw new Error("Prompt Trace 响应缺少 trace 对象。");
      }
      panelState.trace = trace;
      panelState.promptTraceId = trace.prompt_trace_id || panelState.promptTraceId || null;
      panelState.messageId = trace.message_id || panelState.messageId || null;
      panelState.loading = false;
      panelState.error = null;
      renderPromptTracePanel();
      return trace;
    } catch (error) {
      panelState.loading = false;
      panelState.error = error?.message || String(error);
      renderPromptTracePanel();
      renderStatusStrip?.([{ label: `Prompt Trace 读取失败：${panelState.error}`, variant: "warn" }]);
      return null;
    }
  }

  async function openPromptTraceForMessage({ promptTraceId = null, messageId = null } = {}) {
    if (!promptTraceId && !messageId) {
      renderStatusStrip?.([{ label: "当前消息没有可查询的 Prompt Trace。", variant: "warn" }]);
      return null;
    }
    return openPromptTrace({ promptTraceId, messageId });
  }

  async function openPromptTraceForCandidate(candidate = null) {
    if (!candidate) {
      return null;
    }
    return openPromptTrace({
      promptTraceId: candidate.source_prompt_trace_id || null,
      messageId: candidate.source_message_id || null,
    });
  }

  function bindActions() {
    if (actionsBound) {
      return;
    }
    actionsBound = true;
    els.closePromptTraceButton?.addEventListener("click", () => {
      closePromptTrace();
    });
    els.promptTraceToggleSnapshotButton?.addEventListener("click", () => {
      const panelState = getPanelState();
      if (!panelState.trace) {
        return;
      }
      panelState.expandedSnapshot = !panelState.expandedSnapshot;
      renderPromptTracePanel();
    });
    els.promptTraceJumpMessageButton?.addEventListener("click", () => {
      const panelState = getPanelState();
      if (!panelState.messageId) {
        return;
      }
      jumpToMessage?.(panelState.messageId);
      closePromptTrace();
    });
    els.promptTraceModal?.addEventListener("click", (event) => {
      if (event.target === els.promptTraceModal) {
        closePromptTrace();
      }
    });
    els.promptTraceSummary?.addEventListener("click", (event) => {
      const button = event.target?.closest?.("[data-trace-event-id]");
      if (!button) {
        return;
      }
      const eventId = String(button.dataset.traceEventId || "").trim();
      if (!eventId) {
        return;
      }
      onEventSelected?.(eventId);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && getPanelState().open) {
        closePromptTrace();
      }
    });
  }

  bindActions();
  renderPromptTracePanel();

  return {
    openPromptTrace,
    openPromptTraceForMessage,
    openPromptTraceForCandidate,
    closePromptTrace,
    renderPromptTracePanel,
  };
}
