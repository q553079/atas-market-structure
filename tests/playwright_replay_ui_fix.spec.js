const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 18090;
const STORAGE_PREFIX = "replay-workbench/v2";
let serverProcess;

function waitForHealth(timeoutMs = 30000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const tryRequest = () => {
      const req = http.get(`http://127.0.0.1:${PORT}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
          return;
        }
        if (Date.now() - startedAt > timeoutMs) {
          reject(new Error(`health check failed with status ${res.statusCode}`));
          return;
        }
        setTimeout(tryRequest, 250);
      });
      req.on("error", () => {
        if (Date.now() - startedAt > timeoutMs) {
          reject(new Error("timed out waiting for fake workbench server"));
          return;
        }
        setTimeout(tryRequest, 250);
      });
    };
    tryRequest();
  });
}

function buildCandles({ count, startPrice }) {
  const candles = [];
  const base = Date.UTC(2026, 2, 1, 0, 0, 0);
  let px = startPrice;
  for (let i = 0; i < count; i += 1) {
    const startedAt = new Date(base + i * 60 * 1000);
    const endedAt = new Date(base + (i + 1) * 60 * 1000);
    const drift = i * 0.18;
    const wave = Math.sin(i / 8) * 2.5;
    const close = startPrice + drift + wave;
    const open = px;
    const high = Math.max(open, close) + 1.2;
    const low = Math.min(open, close) - 1.2;
    candles.push({
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: 100 + ((i * 17) % 60),
    });
    px = close;
  }
  return candles;
}

function buildSnapshot(symbol, count, startPrice) {
  const candles = buildCandles({ count, startPrice });
  return {
    instrument_symbol: symbol,
    display_timeframe: "1m",
    window_start: candles[0].started_at,
    window_end: candles[candles.length - 1].ended_at,
    candles,
    event_annotations: [],
    focus_regions: [],
    strategy_candidates: [],
    raw_features: {
      deferred_history_available: false,
      total_candle_count: candles.length,
    },
    live_tail: {
      instrument_symbol: symbol,
      display_timeframe: "1m",
      latest_price: candles[candles.length - 1].close,
      best_bid: candles[candles.length - 1].close - 0.25,
      best_ask: candles[candles.length - 1].close + 0.25,
      latest_price_source: "continuous_state",
      best_bid_source: "ticks_raw",
      best_ask_source: "ticks_raw",
    },
  };
}

function buildEventEnvelope({ candidates = [], sessionId = "fake-session", symbol = "NQ", timeframe = "1m" } = {}) {
  return {
    schema_version: "event_stream.v1",
    query: {
      session_id: sessionId,
      symbol,
      timeframe,
    },
    candidates,
    items: [],
    memory_entries: [],
  };
}

function parseVisibleBars(text) {
  const match = String(text || "").match(/可见\s*(\d+)\s*根/);
  return match ? Number(match[1]) : null;
}

async function collectVisibleFirstScreenAttentionControls(page) {
  return page.evaluate(() => {
    const isVisible = (node) => {
      if (!(node instanceof HTMLElement) || node.hidden) {
        return false;
      }
      const closedDetails = node.closest("details:not([open])");
      if (closedDetails instanceof HTMLDetailsElement) {
        const summary = closedDetails.querySelector(":scope > summary");
        if (!(summary instanceof HTMLElement) || (node !== summary && !summary.contains(node))) {
          return false;
        }
      }
      const style = window.getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
        return false;
      }
      return node.getClientRects().length > 0;
    };
    const readLabel = (node) => {
      const text = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (text) {
        return text;
      }
      const title = String(node.getAttribute("title") || "").trim();
      if (title) {
        return title;
      }
      const ariaLabel = String(node.getAttribute("aria-label") || "").trim();
      if (ariaLabel) {
        return ariaLabel;
      }
      return node.id || node.tagName.toLowerCase();
    };
    const seen = new Set();
    const controls = [];
    const nodes = [
      document.querySelector("#buildButton"),
      document.querySelector("#chartToolbarSecondary > summary") || document.querySelector("#chartToolbarSecondary summary"),
      ...Array.from(document.querySelectorAll("#aiPrimaryActions > button, #aiPrimaryActions > summary")),
      document.querySelector("#chatComposerToolsMenu > summary"),
      document.querySelector("#aiChatSendButton"),
    ];
    nodes.forEach((node) => {
      if (!(node instanceof HTMLElement) || !isVisible(node) || node.id === "aiChatStopButton") {
        return;
      }
      const key = node.id || `${node.tagName}:${readLabel(node)}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      controls.push({
        id: node.id || "",
        label: readLabel(node),
      });
    });
    return controls;
  });
}

async function collectVisibleAnnotationManagerEntries(page) {
  return page.evaluate(() => {
    const isVisible = (node) => {
      if (!(node instanceof HTMLElement) || node.hidden) {
        return false;
      }
      const closedDetails = node.closest("details:not([open])");
      if (closedDetails instanceof HTMLDetailsElement) {
        const summary = closedDetails.querySelector(":scope > summary");
        if (!(summary instanceof HTMLElement) || (node !== summary && !summary.contains(node))) {
          return false;
        }
      }
      const style = window.getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
        return false;
      }
      return node.getClientRects().length > 0;
    };
    return Array.from(document.querySelectorAll("button, summary"))
      .filter((node) => {
        const text = (node.textContent || "").replace(/\s+/g, " ").trim();
        return (
          node.id === "annotationManagerButton"
          || node.id === "toggleAnnotationPanelButton"
          || text === "标记管理"
        );
      })
      .filter(isVisible)
      .map((node) => ({
        id: node.id || "",
        label: (node.textContent || "").replace(/\s+/g, " ").trim(),
      }));
  });
}

function buildAttentionReply(messageId, {
  title,
  content,
  startedAt,
  endedAt,
  anchor,
  contextVersion,
  sessionDate,
  objectCount,
  sourceEventIds = [],
  sourceObjectIds = [],
  contextBlocks = [],
  includeMemorySummary = true,
  includeRecentMessages = true,
  modelName = "fake-ui-chat",
  promptTraceId = null,
  alignmentState = "aligned",
  assertionLevel = "grounded",
}) {
  return {
    message_id: messageId,
    promptTraceId,
    prompt_trace_id: promptTraceId,
    role: "assistant",
    content,
    status: "completed",
    model: modelName,
    replyTitle: title,
    reply_title: title,
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: endedAt,
    updated_at: endedAt,
    meta: {
      replyTitle: title,
      promptTraceId,
      prompt_trace_id: promptTraceId,
      workbench_ui: {
        schema_version: "workbench_ui.v1",
        symbol: "NQ",
        timeframe: "1m",
        reply_window: {
          window_start: startedAt,
          window_end: endedAt,
        },
        reply_window_anchor: anchor,
        reply_session_date: sessionDate,
        context_version: contextVersion,
        context_blocks: contextBlocks,
        selected_block_count: contextBlocks.length,
        pinned_block_count: contextBlocks.filter((item) => item?.pinned).length,
        include_memory_summary: includeMemorySummary,
        include_recent_messages: includeRecentMessages,
        model_name: modelName,
        object_count: objectCount,
        source_event_ids: sourceEventIds,
        source_object_ids: sourceObjectIds,
        alignment_state: alignmentState,
        assertion_level: assertionLevel,
        cross_day_anchor_count: 0,
      },
    },
  };
}

function buildAttentionFirstSession() {
  const userMessage = {
    message_id: "msg-user-1",
    role: "user",
    content: "先看当前窗口附近的结构，再决定是否展开旧事件。",
    status: "sent",
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: "2026-03-25T09:50:00.000Z",
    updated_at: "2026-03-25T09:50:00.000Z",
    meta: {},
  };
  const olderReply = buildAttentionReply("msg-assistant-1", {
    title: "第一版开盘结构",
    content: "第一版回复：09:30 到 09:48 的回踩结构偏完整，但事件对齐仍然偏粗，需要继续核对。",
    startedAt: "2026-03-25T09:30:00.000Z",
    endedAt: "2026-03-25T09:48:00.000Z",
    promptTraceId: "trace-msg-assistant-1",
    anchor: "anchor-old",
    contextVersion: "ctx-v1",
    sessionDate: "2026-03-25",
    objectCount: 2,
    contextBlocks: [
      {
        block_id: "pb-window",
        block_version: 1,
        source_kind: "window_snapshot",
        scope: "request",
        editable: false,
        selected: true,
        pinned: false,
      },
      {
        block_id: "pb-memory",
        block_version: 1,
        source_kind: "memory_summary",
        scope: "session",
        editable: false,
        selected: true,
        pinned: true,
      },
    ],
    sourceEventIds: ["ev-open-1", "ev-open-2"],
    sourceObjectIds: ["obj-zone-1"],
    alignmentState: "partial",
    assertionLevel: "review",
  });
  const newerReply = buildAttentionReply("msg-assistant-2", {
    title: "第二版窗口校准",
    content: "第二版回复：把当前窗口收敛到 09:34 到 09:55，并且只保留附近事件，整体比第一版更贴近当前盘面。",
    startedAt: "2026-03-25T09:34:00.000Z",
    endedAt: "2026-03-25T09:55:00.000Z",
    promptTraceId: "trace-msg-assistant-2",
    anchor: "anchor-new",
    contextVersion: "ctx-v2",
    sessionDate: "2026-03-25",
    objectCount: 4,
    contextBlocks: [
      {
        block_id: "pb-window",
        block_version: 1,
        source_kind: "window_snapshot",
        scope: "request",
        editable: false,
        selected: true,
        pinned: false,
      },
      {
        block_id: "pb-memory",
        block_version: 2,
        source_kind: "memory_summary",
        scope: "session",
        editable: false,
        selected: true,
        pinned: true,
      },
    ],
    sourceEventIds: ["ev-open-2", "ev-open-3", "ev-open-4"],
    sourceObjectIds: ["obj-zone-1", "obj-plan-2"],
    alignmentState: "aligned",
    assertionLevel: "grounded",
  });
  return {
    id: "sess-ui-attention-1",
    sessionId: "sess-ui-attention-1",
    workspaceRole: "analyst",
    title: "NQ 01",
    pinned: true,
    preset: "general",
    symbol: "NQ",
    contractId: "NQ",
    timeframe: "1m",
    windowRange: "最近7天",
    unreadCount: 0,
    selectedPromptBlockIds: ["pb-window", "pb-memory"],
    pinnedContextBlockIds: ["pb-memory"],
    includeMemorySummary: true,
    includeRecentMessages: true,
    promptBlocks: [
      {
        blockId: "pb-window",
        id: "pb-window",
        title: "当前可视窗口",
        previewText: "只取最近 20 分钟窗口，不跨日。",
        preview_text: "只取最近 20 分钟窗口，不跨日。",
        sourceLabel: "窗口快照",
        source_label: "窗口快照",
        sourceKind: "window_snapshot",
        source_kind: "window_snapshot",
        block_version: 1,
        scope: "request",
        editable: false,
        ephemeral: true,
        pinned: false,
      },
      {
        blockId: "pb-memory",
        id: "pb-memory",
        title: "会话记忆摘要",
        previewText: "保留当前用户目标与关键价位，忽略过久历史。",
        preview_text: "保留当前用户目标与关键价位，忽略过久历史。",
        sourceLabel: "记忆摘要",
        source_label: "记忆摘要",
        sourceKind: "memory_summary",
        source_kind: "memory_summary",
        block_version: 2,
        scope: "session",
        editable: false,
        ephemeral: false,
        pinned: true,
      },
    ],
    mountedReplyIds: [],
    activeReplyId: "msg-assistant-2",
    activeReplyWindowAnchor: "anchor-new",
    contextRecipeExpanded: false,
    answerCardDensity: "compact",
    lastContextVersion: "ctx-v2",
    activePlanId: null,
    recapItems: [],
    scrollOffset: 0,
    messages: [userMessage, olderReply, newerReply],
    turns: [userMessage, olderReply, newerReply].map((message) => ({
      role: message.role,
      content: message.content,
      meta: message.meta || {},
    })),
    draft: "",
    draftText: "",
    attachments: [],
    draftAttachments: [],
    attachmentPreviewCollapsed: false,
    expandedLongTextMessageIds: [],
    analysisTemplate: {
      type: "recent_20_bars",
      range: "current_window",
      style: "standard",
      sendMode: "current",
    },
    activeModel: "fake-ui-chat",
    handoffMode: "summary_only",
    backendLoaded: true,
    loadingFromServer: false,
    memory: {
      session_id: "sess-ui-attention-1",
      summary_version: 1,
      active_model: "fake-ui-chat",
      symbol: "NQ",
      timeframe: "1m",
      window_range: "最近7天",
      user_goal_summary: "优先判断当前窗口，不把远古事件掺进来。",
      market_context_summary: "只保留当前窗口附近事件与对象。",
      key_zones_summary: ["21520-21528 回踩带", "21548 高点"],
      active_plans_summary: [],
      invalidated_plans_summary: [],
      important_messages: ["第一版回复更粗，第二版更贴窗。"],
      current_user_intent: "先看当前盘面，再决定要不要展开上下文。",
      latest_question: userMessage.content,
      latest_answer_summary: "第二版回复强化了当前窗口和事件对齐。",
      selected_annotations: [],
      last_updated_at: newerReply.updated_at,
    },
  };
}

function buildPromptTraceEnvelopeForMessage(session, messageId) {
  const message = (session.messages || []).find((item) => item.message_id === messageId);
  if (!message) {
    return null;
  }
  const workbenchUi = message.meta?.workbench_ui || {};
  const blockIndex = new Map((session.promptBlocks || []).map((block) => [block.blockId || block.id, block]));
  const contextBlocks = Array.isArray(workbenchUi.context_blocks) ? workbenchUi.context_blocks : [];
  return {
    trace: {
      schema_version: "prompt_trace.v1",
      prompt_trace_id: message.prompt_trace_id || message.promptTraceId || `trace-${messageId}`,
      session_id: session.id,
      message_id: messageId,
      symbol: session.symbol,
      timeframe: session.timeframe,
      analysis_type: "attention_first",
      analysis_range: "current_window",
      analysis_style: "standard",
      selected_block_ids: contextBlocks.map((item) => item.block_id),
      pinned_block_ids: contextBlocks.filter((item) => item?.pinned).map((item) => item.block_id),
      attached_event_ids: Array.isArray(workbenchUi.source_event_ids) ? workbenchUi.source_event_ids : [],
      prompt_block_summaries: contextBlocks.map((item) => {
        const block = blockIndex.get(item.block_id) || {};
        return {
          block_id: item.block_id,
          kind: block.kind || item.source_kind || "context",
          title: block.title || item.block_id,
          preview_text: block.preview_text || block.previewText || "",
          payload_summary: {},
          block_version: item.block_version || 1,
          source_kind: item.source_kind || "system_policy",
          scope: item.scope || "request",
          editable: !!item.editable,
          selected: item.selected !== false,
          pinned: !!item.pinned,
        };
      }),
      bar_window_summary: {},
      manual_selection_summary: {},
      memory_summary: {
        include_memory_summary: !!workbenchUi.include_memory_summary,
        include_recent_messages: !!workbenchUi.include_recent_messages,
      },
      final_system_prompt: "system prompt preview",
      final_user_prompt: message.content,
      model_name: workbenchUi.model_name || message.model || session.activeModel,
      model_input_hash: `${messageId}-hash`,
      context_version: workbenchUi.context_version,
      context_blocks: contextBlocks,
      reply_window: workbenchUi.reply_window,
      reply_window_anchor: workbenchUi.reply_window_anchor,
      block_version_refs: contextBlocks,
      snapshot: {
        context_version: workbenchUi.context_version,
        context_blocks: contextBlocks,
        reply_window: workbenchUi.reply_window,
        reply_window_anchor: workbenchUi.reply_window_anchor,
        request_snapshot: {
          transport_mode: "ui-test",
        },
      },
      metadata: {
        context_version: workbenchUi.context_version,
        block_version_refs: contextBlocks,
        reply_window: workbenchUi.reply_window,
        reply_window_anchor: workbenchUi.reply_window_anchor,
        include_memory_summary: !!workbenchUi.include_memory_summary,
        include_recent_messages: !!workbenchUi.include_recent_messages,
        truncation: {},
      },
      created_at: message.created_at,
      updated_at: message.updated_at,
    },
  };
}

function buildTraceOnlyPromptTraceEnvelope({
  session,
  messageId,
  promptTraceId,
  startedAt,
  endedAt,
  contextVersion = "ctx-trace-only",
  sessionDate = "2026-03-25",
} = {}) {
  return {
    trace: {
      schema_version: "prompt_trace.v1",
      prompt_trace_id: promptTraceId,
      session_id: session.id,
      message_id: messageId,
      symbol: session.symbol,
      timeframe: session.timeframe,
      analysis_type: "attention_first",
      analysis_range: "current_window",
      analysis_style: "standard",
      selected_block_ids: [],
      pinned_block_ids: [],
      attached_event_ids: [],
      prompt_block_summaries: [],
      bar_window_summary: {},
      manual_selection_summary: {},
      memory_summary: {},
      final_system_prompt: "system prompt preview",
      final_user_prompt: "trace only",
      model_name: session.activeModel || "fake-ui-chat",
      model_input_hash: `${messageId}-trace-only`,
      context_version: contextVersion,
      context_blocks: [],
      reply_window: {
        window_start: startedAt,
        window_end: endedAt,
      },
      reply_window_anchor: "trace-only-anchor",
      snapshot: {
        context_version: contextVersion,
        reply_session_date: sessionDate,
        reply_window: {
          window_start: startedAt,
          window_end: endedAt,
        },
        request_snapshot: {
          transport_mode: "ui-test",
        },
      },
      metadata: {
        context_version: contextVersion,
        reply_session_date: sessionDate,
        reply_window: {
          window_start: startedAt,
          window_end: endedAt,
        },
        reply_window_anchor: "trace-only-anchor",
        include_memory_summary: false,
        include_recent_messages: true,
        block_version_refs: [],
        truncation: {},
      },
      created_at: endedAt,
      updated_at: endedAt,
    },
  };
}

function buildServerSessionSummary(session) {
  return {
    session_id: session.id,
    title: session.title,
    symbol: session.symbol,
    contract_id: session.contractId,
    timeframe: session.timeframe,
    window_range: { label: session.windowRange },
    status: "active",
    unread_count: session.unreadCount,
    selected_prompt_block_ids: session.selectedPromptBlockIds,
    pinned_context_block_ids: session.pinnedContextBlockIds,
    include_memory_summary: session.includeMemorySummary,
    include_recent_messages: session.includeRecentMessages,
    mounted_reply_ids: session.mountedReplyIds,
    active_plan_id: null,
    scroll_offset: session.scrollOffset,
    draft_text: session.draftText,
    draft_attachments: [],
    active_model: session.activeModel,
    pinned: session.pinned,
    created_at: session.messages[0].created_at,
    updated_at: session.memory.last_updated_at,
  };
}

test.beforeAll(async () => {
  const serverScript = path.join(__dirname, "playwright_support", "fake_workbench_ui_server.py");
  serverProcess = spawn("python", [serverScript], {
    cwd: path.resolve(__dirname, ".."),
    env: {
      ...process.env,
      UI_TEST_PORT: String(PORT),
      PYTHONPATH: path.resolve(__dirname, "..", "src"),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProcess.stdout.on("data", (chunk) => process.stdout.write(String(chunk)));
  serverProcess.stderr.on("data", (chunk) => process.stderr.write(String(chunk)));
  await waitForHealth();
});

test.afterAll(async () => {
  if (!serverProcess) {
    return;
  }
  serverProcess.kill("SIGTERM");
});

test("build progress is eased and symbol switch keeps a sane viewport", async ({ page }) => {
  const nqSnapshot = buildSnapshot("NQ", 500, 21000);
  const esSnapshot = buildSnapshot("ES", 200, 5300);

  await page.route("**/api/v1/workbench/replay-builder/build", async (route) => {
    const payload = JSON.parse(route.request().postData() || "{}");
    const symbol = String(payload.instrument_symbol || "NQ").trim().toUpperCase();
    const snapshot = symbol === "ES" ? esSnapshot : nqSnapshot;
    const ingestionId = symbol === "ES" ? "ing-es" : "ing-nq";
    await new Promise((resolve) => setTimeout(resolve, 900));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        action: "built_from_local_history",
        reason: "mock build success",
        local_message_count: 0,
        cache_key: payload.cache_key || `${symbol}_mock`,
        ingestion_id: ingestionId,
        summary: {
          instrument_symbol: symbol,
          display_timeframe: "1m",
          acquisition_mode: "local_history",
          candle_count: snapshot.candles.length,
        },
        core_snapshot: snapshot,
      }),
    });
  });

  await page.route("**/api/v1/workbench/operator-entries?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ entries: [] }),
    });
  });
  await page.route("**/api/v1/workbench/manual-regions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ regions: [] }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();

  await page.fill("#instrumentSymbol", "NQ");
  await page.selectOption("#displayTimeframe", "1m");
  await page.click("#buildButton");

  const progressSamples = [];
  for (let i = 0; i < 12; i += 1) {
    await page.waitForTimeout(90);
    const percent = await page.locator("#buildProgress").evaluate((el) => {
      const cssValue = getComputedStyle(el).getPropertyValue("--progress-percent");
      return cssValue || "";
    });
    progressSamples.push(percent);
  }
  const numericProgress = progressSamples
    .map((value) => Number(String(value).replace("%", "").trim()))
    .filter((n) => Number.isFinite(n));
  const distinctProgress = [...new Set(numericProgress.map((n) => Number(n.toFixed(1))))];
  const hasFractionalStep = distinctProgress.some((n) => Math.abs(n - Math.round(n)) > 0.001);
  expect(distinctProgress.length).toBeGreaterThanOrEqual(4);
  expect(hasFractionalStep).toBeTruthy();

  await page.waitForFunction(() => {
    const text = document.querySelector("#chartViewportMeta")?.textContent || "";
    return text.includes("总 500 根");
  });

  await page.fill("#instrumentSymbol", "ES");
  await page.click("#buildButton");

  await page.waitForFunction(() => {
    const text = document.querySelector("#chartViewportMeta")?.textContent || "";
    return text.includes("总 200 根");
  });
  await page.waitForTimeout(450);

  const logicalRange = await page.evaluate(() => {
    const range = window._lwChartState?.chartInstance?.timeScale?.().getVisibleLogicalRange?.();
    if (!range) {
      return null;
    }
    return { from: Number(range.from), to: Number(range.to) };
  });
  expect(logicalRange).not.toBeNull();
  expect(logicalRange.to).toBeGreaterThanOrEqual(198);
  expect(logicalRange.to - logicalRange.from).toBeGreaterThanOrEqual(70);
  expect(logicalRange.to - logicalRange.from).toBeLessThanOrEqual(190);
});

test("plain wheel no longer silently zooms the chart viewport", async ({ page }) => {
  const snapshot = buildSnapshot("NQ", 180, 21000);

  await page.route("**/api/v1/workbench/replay-builder/build", async (route) => {
    const payload = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        action: "built_from_local_history",
        reason: "mock build success",
        local_message_count: 0,
        cache_key: payload.cache_key || "NQ_mock",
        ingestion_id: "ing-nq",
        summary: {
          instrument_symbol: snapshot.instrument_symbol,
          display_timeframe: "1m",
          acquisition_mode: "local_history",
          candle_count: snapshot.candles.length,
        },
        core_snapshot: snapshot,
      }),
    });
  });

  await page.route("**/api/v1/workbench/operator-entries?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ entries: [] }),
    });
  });
  await page.route("**/api/v1/workbench/manual-regions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ regions: [] }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();

  await page.fill("#instrumentSymbol", "NQ");
  await page.selectOption("#displayTimeframe", "1m");
  await page.click("#buildButton");
  await page.waitForFunction(() => {
    const text = document.querySelector("#chartViewportMeta")?.textContent || "";
    return text.includes("总 180 根");
  });
  await page.waitForTimeout(450);

  const initialRange = await page.evaluate(() => {
    const range = window._lwChartState?.chartInstance?.timeScale?.().getVisibleLogicalRange?.();
    return range ? { from: Number(range.from), to: Number(range.to) } : null;
  });
  expect(initialRange).not.toBeNull();

  for (let index = 0; index < 8; index += 1) {
    await page.locator("#chartContainer").dispatchEvent("wheel", {
      deltaX: 0,
      deltaY: -240,
    });
    await page.waitForTimeout(50);
  }

  const plainWheelRange = await page.evaluate(() => {
    const range = window._lwChartState?.chartInstance?.timeScale?.().getVisibleLogicalRange?.();
    return range ? { from: Number(range.from), to: Number(range.to) } : null;
  });
  expect(plainWheelRange).not.toBeNull();
  expect(Math.abs(plainWheelRange.from - initialRange.from)).toBeLessThan(0.75);
  expect(Math.abs(plainWheelRange.to - initialRange.to)).toBeLessThan(0.75);
});

test("event panel keeps backend history but only shows candidates near the current chart window", async ({ page }) => {
  const snapshot = buildSnapshot("NQ", 3000, 21000);
  const oldCandidate = {
    event_id: "evt-old",
    session_id: "fake-session",
    candidate_kind: "market_event",
    lifecycle_state: "candidate",
    source_type: "manual",
    title: "远古事件",
    summary: "这个事件只应该在拉回早期窗口时出现。",
    price_ref: snapshot.candles[60].close,
    anchor_start_ts: snapshot.candles[60].started_at,
    anchor_end_ts: snapshot.candles[61].ended_at,
    created_at: snapshot.candles[61].ended_at,
    updated_at: snapshot.candles[61].ended_at,
  };
  const recentCandidate = {
    event_id: "evt-recent",
    session_id: "fake-session",
    candidate_kind: "market_event",
    lifecycle_state: "candidate",
    source_type: "manual",
    title: "近端事件",
    summary: "这个事件应该跟着最新窗口显示。",
    price_ref: snapshot.candles[2940].close,
    anchor_start_ts: snapshot.candles[2940].started_at,
    anchor_end_ts: snapshot.candles[2941].ended_at,
    created_at: snapshot.candles[2941].ended_at,
    updated_at: snapshot.candles[2941].ended_at,
  };
  const envelope = buildEventEnvelope({
    candidates: [oldCandidate, recentCandidate],
    symbol: snapshot.instrument_symbol,
    timeframe: snapshot.display_timeframe,
  });

  await page.route("**/api/v1/workbench/replay-builder/build", async (route) => {
    const payload = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        action: "built_from_local_history",
        reason: "mock build success",
        local_message_count: 0,
        cache_key: payload.cache_key || "NQ_window_mock",
        ingestion_id: "ing-nq-window",
        summary: {
          instrument_symbol: snapshot.instrument_symbol,
          display_timeframe: snapshot.display_timeframe,
          acquisition_mode: "local_history",
          candle_count: snapshot.candles.length,
        },
        core_snapshot: snapshot,
      }),
    });
  });
  await page.route("**/api/v1/workbench/event-stream?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(envelope),
    });
  });
  await page.route("**/api/v1/workbench/operator-entries?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ entries: [] }),
    });
  });
  await page.route("**/api/v1/workbench/manual-regions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ regions: [] }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();

  await page.fill("#instrumentSymbol", "NQ");
  await page.selectOption("#displayTimeframe", "1m");
  await page.click("#buildButton");

  await page.waitForFunction(() => {
    const text = document.querySelector("#chartViewportMeta")?.textContent || "";
    return text.includes("总 3000 根");
  });
  await page.waitForFunction(() => {
    const summary = document.querySelector("#eventStreamSummary")?.textContent || "";
    return summary.includes("后台 2 条");
  });

  await expect(page.locator("#eventStreamList .event-candidate-card:visible")).toHaveCount(1);
  await expect(page.locator('#eventStreamList .event-candidate-card:visible', { hasText: "近端事件" })).toHaveCount(1);
  await expect(page.locator('#eventStreamList .event-candidate-card:visible', { hasText: "远古事件" })).toHaveCount(0);
  const historyShell = page.locator('#eventStreamList .nearby-context-history-shell[data-nearby-group="history"]');
  const historySummary = page.locator("#eventStreamList .nearby-context-history-summary");
  await expect(historyShell).toHaveJSProperty("open", false);
  await historySummary.click();
  await expect(historyShell).toHaveJSProperty("open", true);
  await historySummary.click();
  await expect(historyShell).toHaveJSProperty("open", false);
  await page.getByRole("button", { name: "事件" }).click();
  await expect(historyShell).toHaveJSProperty("open", false);
  await expect(page.locator('#eventStreamList .event-candidate-card:visible', { hasText: "远古事件" })).toHaveCount(0);

  await page.waitForTimeout(900);
  await page.evaluate(() => {
    const chart = window._lwChartState?.chartInstance;
    const timeScale = chart?.timeScale?.();
    if (!timeScale?.setVisibleLogicalRange) {
      throw new Error("lightweight chart not ready");
    }
    timeScale.setVisibleLogicalRange({
      from: 120,
      to: 300,
    });
  });
  await page.waitForFunction(() => {
    const range = window._lwChartState?.chartInstance?.timeScale?.().getVisibleLogicalRange?.();
    return range && Number(range.to) < 400;
  });

  await expect(page.locator("#eventStreamList .event-candidate-card:visible")).toHaveCount(0);
  await expect(page.locator("#eventStreamList")).toContainText("历史");
  await expect(page.locator('#eventStreamList .event-candidate-card:visible', { hasText: "近端事件" })).toHaveCount(0);
});

test("attention-first first screen keeps primary modules bounded and secondary noise collapsed", async ({ page }) => {
  const session = buildAttentionFirstSession();
  const serverSession = buildServerSessionSummary(session);

  await page.addInitScript(({ seededSession, storagePrefix }) => {
    window.localStorage.clear();
    window.localStorage.setItem(`${storagePrefix}:sessions`, JSON.stringify([seededSession]));
    window.localStorage.setItem(`${storagePrefix}:workbench`, JSON.stringify({
      activeAiThreadId: seededSession.id,
      topBar: {
        symbol: seededSession.symbol,
        timeframe: seededSession.timeframe,
        quickRange: "7d",
      },
      changeInspector: {
        open: false,
        mode: "semantic",
        baselineReplyId: null,
        compareReplyId: null,
        pinned: false,
      },
    }));
  }, {
    seededSession: session,
    storagePrefix: STORAGE_PREFIX,
  });

  await page.route("**/api/v1/workbench/chat/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [serverSession] }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#contextRecipePanel")).toBeVisible();
  await expect(page.locator("#nearbyContextDock")).toBeVisible();

  await expect(page.locator("#chartWorkspace")).toBeVisible();
  await expect(page.locator("#aiWorkspaceSurface")).toBeVisible();
  await expect(page.locator('[data-attention-primary-module="input-composer"]')).toBeVisible();
  await expect(page.locator("#nearbyContextDock")).toBeVisible();
  await expect(page.locator("#nearbyContextDock #eventStreamPanel")).toBeVisible();
  await expect(page.locator("#workbenchMain > #eventStreamPanel")).toHaveCount(0);
  await expect(page.locator("#aiSecondaryControls")).toHaveJSProperty("open", false);
  await expect(page.locator("#eventScribePanel")).toBeHidden();
  await expect(page.locator("#replyExtractionPanel")).toBeHidden();
  await expect(page.locator("#changeInspectorPanel")).toBeHidden();
  const nearbyDockBox = await page.locator("#nearbyContextDock").boundingBox();
  const contextRecipeBox = await page.locator("#contextRecipePanel").boundingBox();
  if (!nearbyDockBox || !contextRecipeBox) {
    throw new Error("Nearby Context dock or Context Recipe panel is missing a visible layout box.");
  }
  expect(nearbyDockBox.y).toBeLessThan(contextRecipeBox.y);

  const visiblePrimaryModuleCount = await page.evaluate(() => {
    const selectors = [
      "#chartWorkspace",
      '[data-attention-primary-module="input-composer"]',
      "#aiWorkspaceSurface",
      "#nearbyContextDock",
    ];
    return selectors.filter((selector) => {
      const node = document.querySelector(selector);
      if (!(node instanceof HTMLElement) || node.hidden) {
        return false;
      }
      const style = window.getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden";
    }).length;
  });
  const visibleAttentionControls = await collectVisibleFirstScreenAttentionControls(page);
  const visibleAnnotationManagerEntries = await collectVisibleAnnotationManagerEntries(page);
  expect(visiblePrimaryModuleCount).toBeLessThanOrEqual(4);
  expect(visiblePrimaryModuleCount).toBe(4);
  expect(visibleAttentionControls.length).toBeLessThanOrEqual(6);
  expect(visibleAttentionControls.map((item) => item.label)).toEqual([
    "加载图表",
    "图表工具",
    "分析当前窗口",
    "更多工具",
    "附加",
    "发送",
  ]);
  expect(visibleAnnotationManagerEntries).toEqual([]);
});

test("nearby context dock stays inside the AI workspace instead of overlapping lower sections", async ({ page }) => {
  await page.setViewportSize({ width: 920, height: 780 });
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();

  const layout = await page.evaluate(() => {
    document.querySelector("#aiSidebar")?.classList.add("open");

    const setVisible = (selector) => {
      const node = document.querySelector(selector);
      if (node instanceof HTMLElement) {
        node.hidden = false;
        node.removeAttribute("hidden");
        node.setAttribute("aria-hidden", "false");
      }
      return node;
    };

    setVisible("#aiAnswerWorkspace");
    setVisible("#activeReplyWorkspaceCard");
    setVisible("#nearbyContextDock");

    const activeReply = document.querySelector("#activeReplyWorkspaceCard");
    if (activeReply instanceof HTMLElement) {
      activeReply.innerHTML = `
        <div class="answer-workspace-hero">
          <strong>当前答复</strong>
          <p>模拟一条较长的当前答复，用来验证附近事件区在内容膨胀时仍然会被约束在自己的工作区内。</p>
        </div>
      `;
    }

    const summary = document.querySelector("#eventStreamSummary");
    if (summary instanceof HTMLElement) {
      summary.textContent = "模拟高内容量事件流，验证事件区不会压住聊天区和下面的更多工具区域。";
    }

    const eventStreamList = document.querySelector("#eventStreamList");
    if (eventStreamList instanceof HTMLElement) {
      eventStreamList.innerHTML = Array.from({ length: 10 }, (_, index) => `
        <article class="event-candidate-card kind-market-event context-nearby" data-event-id="layout-${index}">
          <div class="event-candidate-card-head">
            <div class="event-candidate-title-wrap">
              <strong>模拟事件 ${index + 1}</strong>
              <div class="event-candidate-kicker">market_event</div>
            </div>
            <div class="event-candidate-badge-row">
              <span class="event-candidate-badge lifecycle">PENDING</span>
              <span class="event-candidate-badge confidence">0%</span>
            </div>
          </div>
          <p class="event-candidate-summary">这里放一段更长的摘要，用来模拟真实事件流里的多行内容和较高卡片密度。</p>
          <div class="event-candidate-context-row">
            <span class="event-candidate-badge context reply">当前回答</span>
            <span class="event-candidate-badge context object">图上对象</span>
            <span class="event-candidate-badge context reason">当前窗口 + 图上对象</span>
          </div>
          <div class="event-candidate-meta-grid">
            <span>21520-21528</span>
            <span>03/22 23:11</span>
            <span>手工</span>
          </div>
        </article>
      `).join("");
    }

    const rect = (selector) => {
      const node = document.querySelector(selector);
      if (!(node instanceof HTMLElement) || node.hidden) {
        return null;
      }
      const box = node.getBoundingClientRect();
      return {
        top: box.top,
        bottom: box.bottom,
        height: box.height,
        clientHeight: node.clientHeight,
        scrollHeight: node.scrollHeight,
      };
    };

    return {
      aiAnswerWorkspace: rect("#aiAnswerWorkspace"),
      nearbyContextDock: rect("#nearbyContextDock"),
      eventStreamList: rect("#eventStreamList"),
      chatThreadShell: rect(".chat-thread-shell"),
      aiSecondaryControls: rect("#aiSecondaryControls"),
    };
  });

  expect(layout.aiAnswerWorkspace).not.toBeNull();
  expect(layout.nearbyContextDock).not.toBeNull();
  expect(layout.eventStreamList).not.toBeNull();
  expect(layout.chatThreadShell).not.toBeNull();
  expect(layout.aiSecondaryControls).not.toBeNull();

  expect(layout.nearbyContextDock.bottom).toBeLessThanOrEqual(layout.aiAnswerWorkspace.bottom + 0.5);
  expect(layout.nearbyContextDock.bottom).toBeLessThanOrEqual(layout.chatThreadShell.top + 0.5);
  expect(layout.chatThreadShell.bottom).toBeLessThanOrEqual(layout.aiSecondaryControls.top + 0.5);
  expect(layout.eventStreamList.scrollHeight).toBeGreaterThan(layout.eventStreamList.clientHeight);
});

test("more tools expands inside its own card instead of spilling over adjacent areas", async ({ page }) => {
  await page.setViewportSize({ width: 920, height: 780 });
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();

  await page.evaluate(() => document.querySelector("#aiSidebar")?.classList.add("open"));
  await page.click("#aiMoreButton");
  await expect(page.locator("#aiSecondaryControls")).toHaveJSProperty("open", true);

  const layout = await page.evaluate(() => {
    const rect = (selector) => {
      const node = document.querySelector(selector);
      if (!(node instanceof HTMLElement) || node.hidden) {
        return null;
      }
      const box = node.getBoundingClientRect();
      return {
        top: box.top,
        bottom: box.bottom,
        height: box.height,
        clientHeight: node.clientHeight,
        scrollHeight: node.scrollHeight,
      };
    };

    return {
      aiWorkspaceSurface: rect("#aiWorkspaceSurface"),
      aiSecondaryControls: rect("#aiSecondaryControls"),
      aiSecondaryControlsBody: rect("#aiSecondaryControls .ai-secondary-controls-body"),
      spillsBelowVisibleCard: (() => {
        const details = document.querySelector("#aiSecondaryControls");
        if (!(details instanceof HTMLElement)) {
          return null;
        }
        const detailsRect = details.getBoundingClientRect();
        const sampleX = Math.min(detailsRect.left + 24, window.innerWidth - 4);
        const sampleY = Math.min(detailsRect.bottom + 4, window.innerHeight - 4);
        const hit = document.elementFromPoint(sampleX, sampleY);
        return !!hit?.closest?.("#aiSecondaryControls .ai-secondary-controls-body");
      })(),
    };
  });

  expect(layout.aiWorkspaceSurface).not.toBeNull();
  expect(layout.aiSecondaryControls).not.toBeNull();
  expect(layout.aiSecondaryControlsBody).not.toBeNull();
  expect(layout.spillsBelowVisibleCard).not.toBeNull();

  expect(layout.aiSecondaryControls.top).toBeGreaterThanOrEqual(layout.aiWorkspaceSurface.bottom - 0.5);
  expect(layout.aiSecondaryControlsBody.scrollHeight).toBeGreaterThan(layout.aiSecondaryControlsBody.clientHeight);
  expect(layout.spillsBelowVisibleCard).toBe(false);
});

test("older thread replies stay skim until hover or click reveals detail without breaking reply focus", async ({ page }) => {
  const session = buildAttentionFirstSession();
  const serverSession = buildServerSessionSummary(session);

  await page.addInitScript(({ seededSession, storagePrefix }) => {
    window.localStorage.clear();
    window.localStorage.setItem(`${storagePrefix}:sessions`, JSON.stringify([seededSession]));
    window.localStorage.setItem(`${storagePrefix}:workbench`, JSON.stringify({
      activeAiThreadId: seededSession.id,
      topBar: {
        symbol: seededSession.symbol,
        timeframe: seededSession.timeframe,
        quickRange: "7d",
      },
      changeInspector: {
        open: false,
        mode: "semantic",
        baselineReplyId: null,
        compareReplyId: null,
        pinned: false,
      },
    }));
  }, {
    seededSession: session,
    storagePrefix: STORAGE_PREFIX,
  });

  await page.route("**/api/v1/workbench/chat/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [serverSession] }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });

  const olderReply = page.locator('#aiChatThread .chat-message[data-message-id="msg-assistant-1"]');
  const activeReply = page.locator('#aiChatThread .chat-message[data-message-id="msg-assistant-2"]');
  const olderPeek = olderReply.locator(".answer-card-skim-peek");
  const olderToggle = olderReply.getByRole("button", { name: "细节" });

  await expect(olderReply).toHaveAttribute("data-message-density", "skim");
  await expect(olderReply).toHaveAttribute("data-skim-expanded", "false");
  await expect(olderReply.locator('[data-card-density="skim"]')).toHaveCount(1);
  await expect(activeReply).toHaveAttribute("data-message-density", "compact");
  await expect(olderToggle).toBeVisible();

  const beforeHover = await olderPeek.evaluate((node) => {
    const style = window.getComputedStyle(node);
    return {
      opacity: Number(style.opacity),
      maxHeight: style.maxHeight,
      visibility: style.visibility,
    };
  });
  expect(beforeHover.opacity).toBeLessThan(0.1);
  expect(beforeHover.maxHeight).toBe("0px");
  expect(beforeHover.visibility).toBe("hidden");

  await olderReply.hover();
  await page.waitForTimeout(220);

  const afterHover = await olderPeek.evaluate((node) => {
    const style = window.getComputedStyle(node);
    return {
      opacity: Number(style.opacity),
      maxHeight: style.maxHeight,
      visibility: style.visibility,
    };
  });
  expect(afterHover.opacity).toBeGreaterThan(0.9);
  expect(afterHover.maxHeight).not.toBe("0px");
  expect(afterHover.visibility).toBe("visible");

  await page.mouse.move(0, 0);
  await page.waitForTimeout(220);

  await olderToggle.click();
  await expect(olderReply).toHaveAttribute("data-skim-expanded", "true");
  await expect(olderReply.getByRole("button", { name: "收起" })).toBeVisible();
  await expect(activeReply).toHaveAttribute("data-message-density", "compact");

  const persistedAfterToggle = await page.evaluate(({ storagePrefix }) => {
    const sessions = JSON.parse(window.localStorage.getItem(`${storagePrefix}:sessions`) || "[]");
    return {
      activeReplyId: sessions[0]?.activeReplyId || null,
      expandedSkimMessageIds: Array.isArray(sessions[0]?.expandedSkimMessageIds) ? sessions[0].expandedSkimMessageIds : [],
    };
  }, {
    storagePrefix: STORAGE_PREFIX,
  });
  expect(persistedAfterToggle.activeReplyId).toBe("msg-assistant-2");
  expect(persistedAfterToggle.expandedSkimMessageIds).toEqual(["msg-assistant-1"]);

  await page.locator("#aiChatInput").click();
  await expect(olderReply).toHaveAttribute("data-skim-expanded", "false");

  const persistedAfterOutsideCollapse = await page.evaluate(({ storagePrefix }) => {
    const sessions = JSON.parse(window.localStorage.getItem(`${storagePrefix}:sessions`) || "[]");
    return {
      activeReplyId: sessions[0]?.activeReplyId || null,
      expandedSkimMessageIds: Array.isArray(sessions[0]?.expandedSkimMessageIds) ? sessions[0].expandedSkimMessageIds : [],
    };
  }, {
    storagePrefix: STORAGE_PREFIX,
  });
  expect(persistedAfterOutsideCollapse.activeReplyId).toBe("msg-assistant-2");
  expect(persistedAfterOutsideCollapse.expandedSkimMessageIds).toEqual([]);

  await olderReply.getByRole("button", { name: "细节" }).click();
  await expect(olderReply).toHaveAttribute("data-skim-expanded", "true");

  await olderReply.locator(".answer-card-skim-title").click();
  await expect(olderReply).toHaveClass(/is-reply-focus/);
  await expect(olderReply).toHaveAttribute("data-message-density", "compact");

  const persistedAfterFocus = await page.evaluate(({ storagePrefix }) => {
    const sessions = JSON.parse(window.localStorage.getItem(`${storagePrefix}:sessions`) || "[]");
    return {
      activeReplyId: sessions[0]?.activeReplyId || null,
      expandedSkimMessageIds: Array.isArray(sessions[0]?.expandedSkimMessageIds) ? sessions[0].expandedSkimMessageIds : [],
    };
  }, {
    storagePrefix: STORAGE_PREFIX,
  });
  expect(persistedAfterFocus.activeReplyId).toBe("msg-assistant-1");
  expect(persistedAfterFocus.expandedSkimMessageIds).toEqual([]);
});

test("answer workspace and change inspector follow assistant reply focus", async ({ page }) => {
  const session = buildAttentionFirstSession();
  const serverSession = buildServerSessionSummary(session);
  const promptTraceByMessageId = new Map(
    ["msg-assistant-1", "msg-assistant-2"].map((messageId) => [messageId, buildPromptTraceEnvelopeForMessage(session, messageId)]),
  );
  const promptTraceById = new Map(
    Array.from(promptTraceByMessageId.values())
      .filter(Boolean)
      .map((envelope) => [envelope.trace.prompt_trace_id, envelope]),
  );
  const attentionEventEnvelope = buildEventEnvelope({
    sessionId: session.id,
    symbol: session.symbol,
    timeframe: session.timeframe,
    candidates: [
      {
        event_id: "evt-reply-new",
        session_id: session.id,
        candidate_kind: "market_event",
        lifecycle_state: "candidate",
        source_type: "ai_reply_structured",
        title: "第二版关联事件",
        summary: "应该跟当前 active reply 一起被收敛到 nearby dock。",
        source_message_id: "msg-assistant-2",
        anchor_start_ts: "2026-03-25T09:42:00.000Z",
        anchor_end_ts: "2026-03-25T09:47:00.000Z",
        created_at: "2026-03-25T09:47:00.000Z",
        updated_at: "2026-03-25T09:47:00.000Z",
        metadata: {
          presentation: {
            source_message_id: "msg-assistant-2",
            reply_window_anchor: "anchor-new",
          },
        },
      },
      {
        event_id: "evt-reply-old",
        session_id: session.id,
        candidate_kind: "market_event",
        lifecycle_state: "candidate",
        source_type: "ai_reply_structured",
        title: "第一版关联事件",
        summary: "切回上一条回答后，这个条目应成为当前回答关联项。",
        source_message_id: "msg-assistant-1",
        anchor_start_ts: "2026-03-25T09:36:00.000Z",
        anchor_end_ts: "2026-03-25T09:40:00.000Z",
        created_at: "2026-03-25T09:40:00.000Z",
        updated_at: "2026-03-25T09:40:00.000Z",
        metadata: {
          presentation: {
            source_message_id: "msg-assistant-1",
            reply_window_anchor: "anchor-old",
          },
        },
      },
      {
        event_id: "evt-fixed-anchor",
        session_id: session.id,
        candidate_kind: "key_level",
        lifecycle_state: "candidate",
        source_type: "manual",
        title: "固定参考锚点",
        summary: "固定锚点应作为独立组保留。",
        price_ref: 21520,
        anchor_start_ts: "2026-03-24T15:30:00.000Z",
        anchor_end_ts: "2026-03-24T15:30:00.000Z",
        created_at: "2026-03-24T15:30:00.000Z",
        updated_at: "2026-03-24T15:30:00.000Z",
        metadata: {
          presentation: {
            anchor_time: "2026-03-24T15:30:00.000Z",
            is_fixed_anchor: true,
          },
        },
      },
    ],
  });

  await page.addInitScript(({ seededSession, storagePrefix }) => {
    window.localStorage.clear();
    window.localStorage.setItem(`${storagePrefix}:sessions`, JSON.stringify([seededSession]));
    window.localStorage.setItem(`${storagePrefix}:workbench`, JSON.stringify({
      activeAiThreadId: seededSession.id,
      topBar: {
        symbol: "NQ",
        timeframe: "1m",
        quickRange: "7d",
      },
      changeInspector: {
        open: false,
        mode: "semantic",
        baselineReplyId: null,
        compareReplyId: null,
        pinned: false,
      },
    }));
  }, {
    seededSession: session,
    storagePrefix: STORAGE_PREFIX,
  });

  await page.route("**/api/v1/workbench/chat/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [serverSession] }),
    });
  });
  await page.route("**/api/v1/workbench/event-stream?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(attentionEventEnvelope),
    });
  });
  await page.route("**/api/v1/workbench/messages/*/prompt-trace", async (route) => {
    const match = route.request().url().match(/\/messages\/([^/]+)\/prompt-trace$/);
    const messageId = match ? decodeURIComponent(match[1]) : "";
    const payload = promptTraceByMessageId.get(messageId);
    await route.fulfill({
      status: payload ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(payload || { error: "not found" }),
    });
  });
  await page.route("**/api/v1/workbench/prompt-traces/*", async (route) => {
    const match = route.request().url().match(/\/prompt-traces\/([^/?]+)/);
    const promptTraceId = match ? decodeURIComponent(match[1]) : "";
    const payload = promptTraceById.get(promptTraceId);
    await route.fulfill({
      status: payload ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(payload || { error: "not found" }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#contextRecipePanel")).toBeVisible();
  await expect(page.locator("#contextRecipePanel")).toContainText("当前回答上下文");
  await expect(page.locator("#contextRecipePanel")).toContainText("ctx-v2");
  await expect(page.locator("#contextRecipePanel")).toContainText("已选 Blocks");
  await expect(page.locator("#nearbyContextDock")).toBeVisible();
  await expect(page.locator("#changeInspectorToggle")).toBeVisible();
  await expect(page.locator("#changeInspectorPanel")).toBeHidden();
  await expect(page.locator("#eventStreamList")).toContainText("仍在影响当前窗口");
  await expect(page.locator('.event-candidate-card', { hasText: "第二版关联事件" })).toContainText("当前回答");
  await expect(page.locator("#eventStreamList")).toContainText("固定锚点");
  const initialStableMessageNode = await page.evaluate(() => {
    const node = document.querySelector('.chat-message[data-message-id="msg-user-1"]');
    window.__stableUserMessageNode = node;
    return !!node;
  });
  expect(initialStableMessageNode).toBeTruthy();

  await page.locator("#changeInspectorToggle").click({ force: true });
  await expect(page.locator("#changeInspectorPanel")).toBeVisible();
  await expect(page.locator("#changeInspectorPanel")).toHaveAttribute("data-mode", "peek");
  await expect(page.locator("#changeInspectorPanel")).toContainText("只做结构化比较");
  await expect(page.locator('[data-change-inspector-mode="text"]')).toHaveCount(0);
  await page.locator('[data-change-inspector-mode="expanded"]').dispatchEvent("click");
  await expect(page.locator("#changeInspectorPanel")).toHaveAttribute("data-mode", "expanded");
  await expect(page.locator("#changeInspectorPanel")).toContainText("回复变化");
  await expect(page.locator("#changeInspectorPanel")).toContainText("上下文变化");

  await page.selectOption('[data-change-inspector-select="compare"]', "msg-assistant-1");
  await expect(page.locator('.chat-message[data-message-id="msg-assistant-1"]')).toHaveClass(/is-reply-focus/);
  await expect(page.locator('.chat-message[data-message-id="msg-assistant-1"]')).toHaveCount(1);
  await expect(page.locator('.chat-message[data-message-id="msg-assistant-2"]')).toHaveCount(1);
  await expect(page.locator("#changeInspectorPanel")).toBeVisible();
  await expect(page.locator("#contextRecipePanel")).toContainText("ctx-v1");
  await expect(page.locator("#nearbyContextDock")).toContainText("anchor-old");
  await expect(page.locator('.event-candidate-card', { hasText: "第一版关联事件" })).toContainText("当前回答");
  await expect(page.locator('.event-candidate-card', { hasText: "第二版关联事件" })).not.toContainText("当前回答");
  await page.locator('#contextRecipePanel [data-context-recipe-toggle="true"]').click({ force: true });
  await expect(page.locator("#contextRecipePanel")).toContainText("pb-memory");
  await expect(page.locator("#contextRecipePanel")).toContainText("当前最新 v2");
  await page.locator('#contextRecipePanel [data-context-recipe-open-trace="true"]').click({ force: true });
  await expect(page.locator("#promptTraceModal")).toBeVisible();
  await expect(page.locator("#promptTraceSummary")).toContainText("Context Recipe 对齐");
  await expect(page.locator("#promptTraceSummary")).toContainText("reply_window_anchor");
  await expect(page.locator("#promptTraceSummary")).toContainText("ctx-v1");
  await expect(page.locator("#promptTraceBlocks")).toContainText("v1");
  await page.locator("#closePromptTraceButton").click({ force: true });
  await expect(page.locator("#promptTraceModal")).toBeHidden();
  const preservedThreadNode = await page.evaluate(() => {
    const node = document.querySelector('.chat-message[data-message-id="msg-user-1"]');
    return {
      sameNode: !!window.__stableUserMessageNode && node === window.__stableUserMessageNode,
      isConnected: !!window.__stableUserMessageNode?.isConnected,
    };
  });
  expect(preservedThreadNode.sameNode).toBeTruthy();
  expect(preservedThreadNode.isConnected).toBeTruthy();

  await page.click('#eventStreamFilterBar [data-event-stream-filter="price_zone"]');

  const persistedState = await page.evaluate(({ storagePrefix }) => {
    const sessions = JSON.parse(window.localStorage.getItem(`${storagePrefix}:sessions`) || "[]");
    const workbench = JSON.parse(window.localStorage.getItem(`${storagePrefix}:workbench`) || "{}");
    return {
      activeReplyId: sessions[0]?.activeReplyId || null,
      inspectorOpen: !!workbench.changeInspector?.open,
      inspectorMode: workbench.changeInspector?.mode || null,
      compareReplyId: workbench.changeInspector?.compareReplyId || null,
    };
  }, {
    storagePrefix: STORAGE_PREFIX,
  });
  expect(persistedState.activeReplyId).toBe("msg-assistant-1");
  expect(persistedState.inspectorOpen).toBeTruthy();
  expect(persistedState.inspectorMode).toBe("expanded");
  expect(persistedState.compareReplyId).toBe("msg-assistant-1");

  await page.locator('[data-change-inspector-close="true"]').dispatchEvent("click");
  await expect(page.locator("#changeInspectorPanel")).toBeHidden();
});

test("context recipe keeps reply window for trace-only and legacy replies", async ({ page }) => {
  const traceOnlyReply = {
    message_id: "msg-assistant-trace-only",
    promptTraceId: "trace-only-1",
    prompt_trace_id: "trace-only-1",
    role: "assistant",
    content: "这条回复只有 Prompt Trace，没有 workbench_ui 元数据。",
    status: "completed",
    model: "fake-ui-chat",
    replyTitle: "仅 Trace 回复",
    reply_title: "仅 Trace 回复",
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: "2026-03-25T10:02:00.000Z",
    updated_at: "2026-03-25T10:02:00.000Z",
    meta: {
      promptTraceId: "trace-only-1",
      prompt_trace_id: "trace-only-1",
    },
  };
  const legacyReply = {
    message_id: "msg-assistant-legacy",
    role: "assistant",
    content: "这条旧消息既没有 workbench_ui，也没有 Prompt Trace。",
    status: "completed",
    model: "fake-ui-chat",
    replyTitle: "Legacy 回复",
    reply_title: "Legacy 回复",
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: "2026-03-24T14:20:00.000Z",
    updated_at: "2026-03-24T14:20:00.000Z",
    meta: {},
  };
  const session = {
    ...buildAttentionFirstSession(),
    id: "sess-ui-trace-fallback",
    sessionId: "sess-ui-trace-fallback",
    title: "NQ Trace Fallback",
    windowRange: "最近3天",
    activeReplyId: "msg-assistant-trace-only",
    activeReplyWindowAnchor: null,
    lastContextVersion: null,
    selectedPromptBlockIds: [],
    pinnedContextBlockIds: [],
    promptBlocks: [],
    includeMemorySummary: false,
    includeRecentMessages: true,
    messages: [
      {
        message_id: "msg-user-fallback",
        role: "user",
        content: "先看 trace-only，再看 legacy 回退。",
        status: "sent",
        annotations: [],
        planCards: [],
        mountedToChart: false,
        mountedObjectIds: [],
        created_at: "2026-03-25T09:59:00.000Z",
        updated_at: "2026-03-25T09:59:00.000Z",
        meta: {},
      },
      traceOnlyReply,
      legacyReply,
    ],
    turns: [
      {
        role: "user",
        content: "先看 trace-only，再看 legacy 回退。",
        meta: {},
      },
      {
        role: "assistant",
        content: traceOnlyReply.content,
        meta: traceOnlyReply.meta,
      },
      {
        role: "assistant",
        content: legacyReply.content,
        meta: legacyReply.meta,
      },
    ],
    memory: {
      ...buildAttentionFirstSession().memory,
      session_id: "sess-ui-trace-fallback",
      window_range: "最近3天",
      latest_answer_summary: traceOnlyReply.content,
      last_updated_at: traceOnlyReply.updated_at,
    },
  };
  const serverSession = buildServerSessionSummary(session);
  const traceOnlyEnvelope = buildTraceOnlyPromptTraceEnvelope({
    session,
    messageId: "msg-assistant-trace-only",
    promptTraceId: "trace-only-1",
    startedAt: "2026-03-25T09:40:00.000Z",
    endedAt: "2026-03-25T09:58:00.000Z",
  });

  await page.addInitScript(({ seededSession, storagePrefix }) => {
    window.localStorage.clear();
    window.localStorage.setItem(`${storagePrefix}:sessions`, JSON.stringify([seededSession]));
    window.localStorage.setItem(`${storagePrefix}:workbench`, JSON.stringify({
      activeAiThreadId: seededSession.id,
      topBar: {
        symbol: "NQ",
        timeframe: "1m",
        quickRange: "7d",
      },
      changeInspector: {
        open: false,
        mode: "semantic",
        baselineReplyId: null,
        compareReplyId: null,
        pinned: false,
      },
    }));
  }, {
    seededSession: session,
    storagePrefix: STORAGE_PREFIX,
  });

  await page.route("**/api/v1/workbench/chat/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [serverSession] }),
    });
  });
  await page.route("**/api/v1/workbench/event-stream?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildEventEnvelope({
        sessionId: session.id,
        symbol: session.symbol,
        timeframe: session.timeframe,
        candidates: [],
      })),
    });
  });
  await page.route("**/api/v1/workbench/messages/*/prompt-trace", async (route) => {
    const match = route.request().url().match(/\/messages\/([^/]+)\/prompt-trace$/);
    const messageId = match ? decodeURIComponent(match[1]) : "";
    const payload = messageId === "msg-assistant-trace-only" ? traceOnlyEnvelope : null;
    await route.fulfill({
      status: payload ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(payload || { error: "not found" }),
    });
  });
  await page.route("**/api/v1/workbench/prompt-traces/*", async (route) => {
    const match = route.request().url().match(/\/prompt-traces\/([^/?]+)/);
    const promptTraceId = match ? decodeURIComponent(match[1]) : "";
    const payload = promptTraceId === "trace-only-1" ? traceOnlyEnvelope : null;
    await route.fulfill({
      status: payload ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(payload || { error: "not found" }),
    });
  });

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  const windowRangeStat = page.locator('#contextRecipePanel .answer-workspace-stat', { hasText: "当前窗口范围" }).locator("strong");
  await expect(windowRangeStat).toContainText("->");
  await expect(windowRangeStat).not.toHaveText("未记录");
  await expect(page.locator("#contextRecipePanel")).toContainText("ctx-trace-only");

  await page.click('.chat-message[data-message-id="msg-assistant-legacy"]');
  await expect(page.locator('.chat-message[data-message-id="msg-assistant-legacy"]')).toHaveClass(/is-reply-focus/);
  await expect(windowRangeStat).toHaveText("最近3天");
});

test("render stability fallback restores previous keyed markup without duplicate nodes", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });

  const result = await page.evaluate(async () => {
    const mod = await import("/static/replay_workbench_render_stability.js");
    const host = document.createElement("div");
    host.id = "render-stability-fallback-host";
    document.body.appendChild(host);
    host.innerHTML = `
      <article class="chat-message" data-message-id="stable-1" data-render-signature="sig-stable">
        <div class="chat-bubble"><span data-probe="value">stable</span></div>
      </article>
    `;
    const rendered = mod.reconcileKeyedChildren(host, [{
      key: "stable-1",
      signature: "sig-broken",
      markup: `
        <article class="chat-message" data-message-id="stable-1">
          <div class="chat-bubble"><span data-probe="value">broken</span></div>
        </article>
        <article class="chat-message" data-message-id="stable-1-dup"></article>
      `,
    }], {
      keyAttribute: "data-message-id",
      itemSelector: ".chat-message[data-message-id]",
    });
    return {
      rendered,
      fallback: host.dataset.renderFallback || "",
      stableCount: host.querySelectorAll('.chat-message[data-message-id="stable-1"]').length,
      duplicateCount: host.querySelectorAll('.chat-message[data-message-id="stable-1-dup"]').length,
      text: host.querySelector('[data-probe="value"]')?.textContent || "",
    };
  });

  expect(result.rendered).toBeFalsy();
  expect(result.fallback).toBe("restore-previous-list");
  expect(result.stableCount).toBe(1);
  expect(result.duplicateCount).toBe(0);
  expect(result.text).toBe("stable");
});
