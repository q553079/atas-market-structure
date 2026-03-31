const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 18092;
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
  const base = Date.UTC(2026, 2, 25, 1, 30, 0);
  let previousClose = startPrice;
  for (let index = 0; index < count; index += 1) {
    const startedAt = new Date(base + index * 60 * 1000);
    const endedAt = new Date(base + (index + 1) * 60 * 1000);
    const drift = index * 0.12;
    const wave = Math.sin(index / 7) * 2.1;
    const close = startPrice + drift + wave;
    const open = previousClose;
    const high = Math.max(open, close) + 1.1;
    const low = Math.min(open, close) - 1.05;
    candles.push({
      started_at: startedAt.toISOString(),
      ended_at: endedAt.toISOString(),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: 120 + ((index * 13) % 55),
    });
    previousClose = close;
  }
  return candles;
}

function buildSnapshot(symbol, count = 180, startPrice = 21500) {
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

async function installReplayRoutes(page, snapshot) {
  await page.route("**/api/v1/workbench/replay-builder/build", async (route) => {
    const payload = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        action: "built_from_local_history",
        reason: "mock build success",
        local_message_count: 0,
        cache_key: payload.cache_key || `${snapshot.instrument_symbol}_mock`,
        ingestion_id: `ing-${snapshot.instrument_symbol.toLowerCase()}`,
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
}

async function buildReplay(page, snapshot) {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#buildButton")).toBeVisible();
  await page.fill("#instrumentSymbol", snapshot.instrument_symbol);
  await page.selectOption("#displayTimeframe", "1m");
  await page.click("#buildButton");
  await page.waitForFunction((expectedCount) => {
    const text = document.querySelector("#chartViewportMeta")?.textContent || "";
    return text.includes(`总 ${expectedCount} 根`);
  }, snapshot.candles.length);
}

async function waitForSeededAssistantReply(page) {
  await expect(page.locator("#aiChatThread")).toContainText(
    "Session-only 回复：这是服务端预置回复，可用于事件来源联动。",
    { timeout: 15000 },
  );
}

async function ensureChartToolsOpen(page) {
  const manualKeyLevelButton = page.locator("#manualKeyLevelButton");
  if (await manualKeyLevelButton.isVisible().catch(() => false)) {
    return;
  }
  await page.locator("#chartToolbarSecondary > summary").click();
  await expect(manualKeyLevelButton).toBeVisible();
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

test("formal event candidates drive event cards, hover spotlight, overlay click, and AI chips", async ({ page }) => {
  const snapshot = buildSnapshot("NQ", 180, 21500);
  await installReplayRoutes(page, snapshot);
  await buildReplay(page, snapshot);
  await waitForSeededAssistantReply(page);
  await ensureChartToolsOpen(page);

  const createResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().endsWith("/api/v1/workbench/event-candidates");
  });
  await page.locator("#chartToolbarSecondary").evaluate((node) => { node.open = true; });
  await page.locator("#manualKeyLevelButton").click();
  await createResponse;

  const zoneCard = page.locator(".event-candidate-card", { hasText: "手工关键位" }).first();
  await expect(zoneCard).toBeVisible({ timeout: 15000 });
  await expect(page.locator("#eventStreamSummary")).toContainText("当前");
  await expect(page.locator("#eventStreamList")).toContainText("刚发生");

  const zoneChip = page.locator(".message-event-chip", { hasText: "手工关键位" }).first();
  await expect(zoneChip).toBeVisible({ timeout: 15000 });

  await expect.poll(async () => page.locator("#chartSvg .event-overlay-hit").count()).toBe(0);

  await zoneCard.hover();
  await expect.poll(async () => page.locator("#chartSvg .event-overlay-hit").count()).toBeGreaterThan(0);

  await zoneChip.click();
  await expect(zoneCard).toHaveClass(/is-selected/);

  await page.locator("#statusSymbolChip").hover();
  await expect.poll(async () => page.locator("#chartSvg .event-overlay-hit").count()).toBe(0);

  await zoneCard.click();
  await expect(zoneCard).toHaveClass(/is-selected/);
  await expect(zoneCard).not.toHaveClass(/is-mounted/);

  await zoneCard.locator('[data-event-action="mount"]').click();
  await expect(zoneCard).toHaveClass(/is-mounted/, { timeout: 10000 });

  await page.locator("#statusDataChip").hover();
  await expect.poll(async () => page.locator("#chartSvg .event-overlay-hit").count()).toBeGreaterThan(0);

  const eventId = await zoneCard.getAttribute("data-event-id");
  expect(eventId).toBeTruthy();
  const stableMountedCard = await page.evaluate((id) => {
    const selector = `.event-candidate-card[data-event-id="${id}"]`;
    const node = document.querySelector(selector);
    window.__mountedEventCardNode = node;
    return !!node;
  }, eventId);
  expect(stableMountedCard).toBeTruthy();

  const createAnotherResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().endsWith("/api/v1/workbench/event-candidates");
  });
  await page.locator("#chartToolbarSecondary").evaluate((node) => { node.open = true; });
  await page.locator("#manualKeyLevelButton").click();
  await createAnotherResponse;
  await expect(page.locator(".event-candidate-card", { hasText: "手工关键位" }).nth(1)).toBeVisible({ timeout: 10000 });
  const preservedMountedCard = await page.evaluate((id) => {
    const selector = `.event-candidate-card[data-event-id="${id}"]`;
    const node = document.querySelector(selector);
    return {
      sameNode: !!window.__mountedEventCardNode && node === window.__mountedEventCardNode,
      mounted: !!node?.classList.contains("is-mounted"),
    };
  }, eventId);
  expect(preservedMountedCard.sameNode).toBeTruthy();
  expect(preservedMountedCard.mounted).toBeTruthy();

  await page.locator(`#chartSvg .event-overlay-hit[data-event-id="${eventId}"]`).click({ force: true });
  await expect(zoneCard).toHaveClass(/is-selected/);
});

test("manual chart-created event candidates can mount and survive reload", async ({ page }) => {
  const snapshot = buildSnapshot("NQ", 160, 21480);
  await installReplayRoutes(page, snapshot);
  await buildReplay(page, snapshot);
  await waitForSeededAssistantReply(page);
  await ensureChartToolsOpen(page);

  const createResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().endsWith("/api/v1/workbench/event-candidates");
  });
  await page.locator("#chartToolbarSecondary").evaluate((node) => { node.open = true; });
  await page.locator("#manualKeyLevelButton").click();
  await createResponse;

  const manualCard = page.locator(".event-candidate-card", { hasText: "手工关键位" }).first();
  await expect(manualCard).toBeVisible({ timeout: 10000 });

  await manualCard.locator('[data-event-action="mount"]').click();
  await expect(manualCard).toHaveClass(/is-mounted/, { timeout: 10000 });

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".event-candidate-card", { hasText: "手工关键位" }).first()).toHaveClass(/is-mounted/, { timeout: 15000 });
});
