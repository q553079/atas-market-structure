const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 18090;
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

function parseVisibleBars(text) {
  const match = String(text || "").match(/可见\s*(\d+)\s*根/);
  return match ? Number(match[1]) : null;
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
    const width = await page.locator("#buildProgressFill").evaluate((el) => el.style.width || "");
    progressSamples.push(width);
  }
  const numericProgress = progressSamples
    .map((value) => Number(String(value).replace("%", "")))
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

  const viewportText = await page.locator("#chartViewportMeta").innerText();
  const visibleBars = parseVisibleBars(viewportText);
  expect(visibleBars).not.toBeNull();
  expect(visibleBars).toBeGreaterThanOrEqual(160);
  expect(visibleBars).toBeLessThanOrEqual(190);

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
});
