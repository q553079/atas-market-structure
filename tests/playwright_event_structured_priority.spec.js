const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 18080;
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

function buildStructuredReply(messageId, {
  title,
  content,
  startedAt,
  endedAt,
  anchor,
  sessionDate,
  assertionLevel = "observational",
  alignmentState = "aligned",
  objectCount = 0,
  sourceEventIds = [],
  sourceObjectIds = [],
  planCards = [],
}) {
  return {
    message_id: messageId,
    role: "assistant",
    content,
    status: "completed",
    replyTitle: title,
    reply_title: title,
    annotations: [],
    planCards,
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: endedAt,
    updated_at: endedAt,
    meta: {
      replyTitle: title,
      planCards,
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
        context_version: `ctx-${messageId}`,
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

function buildStructuredPrioritySession() {
  const userMessage = {
    message_id: "msg-user-card-1",
    role: "user",
    content: "只保留可比较的 reply，别把 legacy 噪音混成主视图。",
    status: "sent",
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: "2026-03-25T09:48:00.000Z",
    updated_at: "2026-03-25T09:48:00.000Z",
    meta: {},
  };
  const legacyReply = {
    message_id: "msg-legacy",
    role: "assistant",
    content: "这是一条 legacy assistant 气泡，没有 workbench_ui，也必须继续可用。",
    status: "completed",
    annotations: [],
    planCards: [],
    mountedToChart: false,
    mountedObjectIds: [],
    created_at: "2026-03-25T09:49:00.000Z",
    updated_at: "2026-03-25T09:49:00.000Z",
    meta: {
      replyTitle: "Legacy 回复",
    },
  };
  const conditionalReply = buildStructuredReply("msg-conditional", {
    title: "条件性回踩脚本",
    content: "结论：当前回踩仍可继续观察。 失效条件：若跌破 21518，则这轮回踩脚本失效。 风险：21518 下方承接不足时会快速回吐。",
    startedAt: "2026-03-25T09:30:00.000Z",
    endedAt: "2026-03-25T09:42:00.000Z",
    anchor: "anchor-conditional",
    sessionDate: "2026-03-25",
    assertionLevel: "conditional",
    objectCount: 2,
    sourceEventIds: ["evt-1"],
    sourceObjectIds: ["obj-1"],
  });
  const uncertaintyReply = buildStructuredReply("msg-high", {
    title: "高不确定窗口",
    content: "结论：当前只能做观察性跟踪。 不确定性：量能与事件锚点都不足，当前窗口不适合放大成稳定方向判断。 风险：继续追价容易把噪音当成延续。",
    startedAt: "2026-03-25T09:36:00.000Z",
    endedAt: "2026-03-25T09:50:00.000Z",
    anchor: "anchor-high",
    sessionDate: "2026-03-25",
    assertionLevel: "high_uncertainty",
    alignmentState: "pending_confirmation",
    objectCount: 1,
  });
  const insufficientReply = buildStructuredReply("msg-insufficient", {
    title: "等待更多上下文",
    content: "当前缺少稳定 reply_window 对应对象，暂不形成方向性结论，只记录缺口与待补上下文。",
    startedAt: "2026-03-25T09:45:00.000Z",
    endedAt: "2026-03-25T09:55:00.000Z",
    anchor: "anchor-insufficient",
    sessionDate: "2026-03-25",
    assertionLevel: "insufficient_context",
    alignmentState: "ambiguous",
    objectCount: 0,
    planCards: [{
      id: "plan-should-hide",
      title: "不应显示的计划卡",
      status: "active",
      side: "buy",
      entryPrice: 21524,
      stopPrice: 21518,
      take_profits: [],
      summary: "上下文不足时不应该冒充稳定交易计划。",
    }],
  });
  return {
    id: "sess-structured-cards-1",
    sessionId: "sess-structured-cards-1",
    workspaceRole: "analyst",
    title: "NQ 卡片",
    pinned: true,
    preset: "general",
    symbol: "NQ",
    contractId: "NQ",
    timeframe: "1m",
    windowRange: "最近7天",
    unreadCount: 0,
    selectedPromptBlockIds: [],
    pinnedContextBlockIds: [],
    includeMemorySummary: false,
    includeRecentMessages: false,
    promptBlocks: [],
    mountedReplyIds: [],
    activeReplyId: "msg-insufficient",
    activeReplyWindowAnchor: "anchor-insufficient",
    contextRecipeExpanded: false,
    answerCardDensity: "compact",
    lastContextVersion: "ctx-msg-insufficient",
    activePlanId: null,
    recapItems: [],
    scrollOffset: 0,
    messages: [userMessage, legacyReply, conditionalReply, uncertaintyReply, insufficientReply],
    turns: [userMessage, legacyReply, conditionalReply, uncertaintyReply, insufficientReply].map((message) => ({
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
      type: "general",
      range: "current_window",
      style: "standard",
      sendMode: "current",
    },
    activeModel: "fake-ui-chat",
    handoffMode: "summary_only",
    backendLoaded: true,
    loadingFromServer: false,
    memory: {
      session_id: "sess-structured-cards-1",
      summary_version: 1,
      active_model: "fake-ui-chat",
      symbol: "NQ",
      timeframe: "1m",
      window_range: "最近7天",
      user_goal_summary: "优先展示结构化答复卡。",
      market_context_summary: "高不确定和上下文不足必须降级展示。",
      key_zones_summary: [],
      active_plans_summary: [],
      invalidated_plans_summary: [],
      important_messages: ["legacy 与结构化卡需要并存。"],
      current_user_intent: "验证卡片优先级与谨慎输出。",
      latest_question: userMessage.content,
      latest_answer_summary: insufficientReply.content,
      selected_annotations: [],
      last_updated_at: insufficientReply.updated_at,
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
    active_plan_id: session.activePlanId,
    scroll_offset: session.scrollOffset,
    draft_text: session.draftText,
    draft_attachments: [],
    active_model: session.activeModel,
    pinned: session.pinned,
    created_at: session.messages[0].created_at,
    updated_at: session.memory.last_updated_at,
  };
}

async function ensureAiWorkspaceReady(page) {
  const moreButton = page.locator("#aiMoreButton");
  if (await moreButton.isVisible().catch(() => false)) {
    return;
  }
  const sidebarTrigger = page.locator("#aiSidebarTrigger");
  if (await sidebarTrigger.isVisible().catch(() => false)) {
    await sidebarTrigger.click({ force: true });
  }
  await moreButton.scrollIntoViewIfNeeded();
  await expect(moreButton).toBeVisible();
}

test("event scribe prefers structured annotations over text fallback noise", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "networkidle" });

  await page.locator("#aiMoreButton").click();
  const eventInput = page.locator("#eventScribeInput");
  await expect(eventInput).toBeVisible();
  await expect(page.locator("#replyExtractionCollapseButton")).toHaveText("展开");
  await eventInput.fill("请整理当前窗口的关键计划、区域和风险。");

  await page.locator("#eventScribeSendButton").click();
  await expect(page.locator("#statusStrip")).toContainText("事件整理 AI 已更新", { timeout: 15000 });
  await page.locator("#replyExtractionCollapseButton").dispatchEvent("click");
  await expect(page.locator("#replyExtractionCollapseButton")).toHaveText("收起");
  await expect(page.locator("#replyExtractionSummary")).toContainText("行动");
  await expect(page.locator("#replyExtractionSummary")).toContainText("区域 1 / 风险 1");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化计划");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化支撑区");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化风险位");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22000");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22123");
  await expect(page.locator("#replyExtractionList")).not.toContainText("候选区域");
});

test("streaming chat prefers structured annotations over text fallback noise", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "networkidle" });

  await expect(page.locator("#aiPrimaryActions button:visible")).toHaveCount(2);
  await expect(page.locator("#aiSecondaryControls")).toHaveJSProperty("open", false);
  expect(await page.locator("[data-attention-primary-action]:visible").count()).toBeLessThanOrEqual(6);
  await ensureAiWorkspaceReady(page);

  const createSessionResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().endsWith("/api/v1/workbench/chat/sessions");
  });
  const secondaryControls = page.locator("#aiSecondaryControls");
  if (!(await secondaryControls.evaluate((node) => node.open))) {
    await page.locator("#aiMoreButton").click();
  }
  await expect(secondaryControls).toHaveJSProperty("open", true);
  await page.locator("#aiNewThreadButton").click();
  await createSessionResponse;
  await expect(page.locator("#currentSessionTitle")).toContainText("NQ 02");
  await expect(page.locator("#aiChatThread")).toContainText("还没有消息");

  if (!(await secondaryControls.evaluate((node) => node.open))) {
    await page.locator("#aiMoreButton").click();
  }
  const analysisTypeSelect = page.locator("#analysisTypeSelect");
  await expect(analysisTypeSelect).toBeVisible();
  await expect(page.locator("#analysisSendCurrentButton")).toBeVisible();
  await expect(page.locator("#recent20BarsButton")).toHaveCount(0);
  await expect(page.locator("#recent20MinutesButton")).toHaveCount(0);
  await analysisTypeSelect.selectOption("event_timeline");

  const streamResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().includes("/api/v1/workbench/chat/sessions/")
      && response.url().endsWith("/stream")
      && response.request().postData()?.includes("\"analysis_type\":\"event_timeline\"");
  });
  await page.locator("#analysisSendCurrentButton").click();
  await streamResponse;

  await expect(page.locator("#statusStrip")).toContainText("AI 流式输出完成", { timeout: 15000 });
  await expect(page.locator("#replyExtractionCollapseButton")).toHaveText("展开");
  await page.locator("#replyExtractionCollapseButton").dispatchEvent("click");
  await expect(page.locator("#replyExtractionCollapseButton")).toHaveText("收起");
  await expect(page.locator("#replyExtractionSummary")).toContainText("行动");
  await expect(page.locator("#replyExtractionSummary")).toContainText("区域 1 / 风险 1");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化计划");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化支撑区");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化风险位");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22000");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22123");
  await expect(page.locator("#replyExtractionList")).not.toContainText("候选区域");
});

test("structured answer cards take priority over legacy bubbles and expose cautious output", async ({ page }) => {
  const session = buildStructuredPrioritySession();
  const serverSession = buildServerSessionSummary(session);

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

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });

  const activeCard = page.locator('.chat-message[data-message-id="msg-insufficient"] [data-structured-answer-card="true"]');
  await expect(activeCard).toBeVisible();
  await expect(activeCard).toHaveAttribute("data-card-density", /^(full|compact)$/);
  await expect(activeCard).toHaveAttribute("data-assertion-level", "insufficient_context");
  await expect(activeCard).toContainText("上下文不足");
  await expect(page.locator('.chat-message[data-message-id="msg-insufficient"] .chat-plan-card')).toHaveCount(0);

  const uncertaintyCard = page.locator('.chat-message[data-message-id="msg-high"] [data-structured-answer-card="true"]');
  await expect(uncertaintyCard).toHaveAttribute("data-card-density", "compact");
  await expect(page.locator('.chat-message[data-message-id="msg-high"]')).toContainText("不确定");

  const conditionalCard = page.locator('.chat-message[data-message-id="msg-conditional"] [data-structured-answer-card="true"]');
  await expect(conditionalCard).toHaveAttribute("data-card-density", "skim");
  await expect(page.locator('.chat-message[data-message-id="msg-conditional"]')).toContainText("需失效条件");

  await expect(page.locator('.chat-message[data-message-id="msg-legacy"] [data-structured-answer-card="true"]')).toHaveCount(0);
  await expect(page.locator('.chat-message[data-message-id="msg-legacy"] .chat-bubble-body')).toContainText("legacy assistant 气泡");

  await page.click('.chat-message[data-message-id="msg-high"]');
  await expect(page.locator('.chat-message[data-message-id="msg-high"]')).toHaveClass(/is-reply-focus/);
  await expect(page.locator('.chat-message[data-message-id="msg-high"] [data-structured-answer-card="true"]')).toHaveAttribute("data-card-density", "compact");
  await expect(page.locator('#activeReplyWorkspaceCard [data-structured-answer-card="true"]')).toHaveAttribute("data-card-density", "full");
  await expect(page.locator("#activeReplyWorkspaceCard")).toContainText("高不确定");
  await expect(page.locator('#activeReplyWorkspaceCard [data-answer-section="uncertainty"]')).toBeVisible();
  await expect(page.locator('.chat-message[data-message-id="msg-insufficient"] [data-structured-answer-card="true"]')).toHaveAttribute("data-card-density", "compact");

  const persistedActiveReplyId = await page.evaluate(({ storagePrefix }) => {
    const sessions = JSON.parse(window.localStorage.getItem(`${storagePrefix}:sessions`) || "[]");
    return sessions[0]?.activeReplyId || null;
  }, {
    storagePrefix: STORAGE_PREFIX,
  });
  expect(persistedActiveReplyId).toBe("msg-high");
});

test("change inspector only compares eligible structured replies and never falls back to raw text diff", async ({ page }) => {
  const session = buildStructuredPrioritySession();
  const serverSession = buildServerSessionSummary(session);

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

  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });

  await expect(page.locator("#changeInspectorToggle")).toBeVisible();
  await expect(page.locator("#changeInspectorPanel")).toBeHidden();
  await page.locator("#changeInspectorToggle").click({ force: true });
  await expect(page.locator("#changeInspectorPanel")).toBeVisible();
  await expect(page.locator("#changeInspectorPanel")).toHaveAttribute("data-mode", "peek");
  await expect(page.locator("#changeInspectorPanel")).toContainText("只做结构化比较");
  await expect(page.locator('[data-change-inspector-mode="text"]')).toHaveCount(0);

  await page.locator('[data-change-inspector-mode="expanded"]').dispatchEvent("click");
  await expect(page.locator("#changeInspectorPanel")).toHaveAttribute("data-mode", "expanded");
  await expect(page.locator("#changeInspectorPanel")).toContainText("回复变化");
  await expect(page.locator("#changeInspectorPanel")).not.toContainText("Baseline");
  await expect(page.locator("#changeInspectorPanel")).not.toContainText("Current");

  await page.click('.chat-message[data-message-id="msg-legacy"]');
  await expect(page.locator('.chat-message[data-message-id="msg-legacy"]')).toHaveClass(/is-reply-focus/);
  await expect(page.locator("#changeInspectorToggle")).toBeHidden();
  await expect(page.locator("#changeInspectorPanel")).toBeHidden();

  await page.click('.chat-message[data-message-id="msg-conditional"]');
  await expect(page.locator('.chat-message[data-message-id="msg-conditional"]')).toHaveClass(/is-reply-focus/);
  await expect(page.locator("#changeInspectorToggle")).toBeVisible();
});
