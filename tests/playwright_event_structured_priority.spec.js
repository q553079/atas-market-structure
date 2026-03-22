const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const PORT = 18080;
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

test("event scribe prefers structured annotations over text fallback noise", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "networkidle" });

  const eventInput = page.locator("#eventScribeInput");
  await expect(eventInput).toBeVisible();
  await eventInput.fill("请整理当前窗口的关键计划、区域和风险。");

  const replyResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().includes("/api/v1/workbench/chat/sessions/")
      && response.url().endsWith("/reply")
      && response.request().postData()?.includes("\"analysis_type\":\"event_timeline\"");
  });
  await page.locator("#eventScribeSendButton").click();
  await replyResponse;

  await expect(page.locator("#statusStrip")).toContainText("事件整理 AI 已更新");
  await expect(page.locator("#replyExtractionSummary")).toContainText("行动 1 / 区域 1 / 风险 1");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化计划");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化支撑区");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化风险位");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22000");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22123");
  await expect(page.locator("#replyExtractionList")).not.toContainText("候选区域");
});

test("streaming chat prefers structured annotations over text fallback noise", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/workbench/replay`, { waitUntil: "networkidle" });

  const createSessionResponse = page.waitForResponse((response) => {
    return response.request().method() === "POST"
      && response.url().endsWith("/api/v1/workbench/chat/sessions");
  });
  await page.locator("#aiNewThreadButton").click();
  await createSessionResponse;
  await expect(page.locator("#currentSessionTitle")).toContainText("NQ 02");
  await expect(page.locator("#aiChatThread")).toContainText("还没有消息");

  const analysisTypeSelect = page.locator("#analysisTypeSelect");
  await expect(analysisTypeSelect).toBeVisible();
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
  await expect(page.locator("#replyExtractionSummary")).toContainText("行动 1 / 区域 1 / 风险 1");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化计划");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化支撑区");
  await expect(page.locator("#replyExtractionList")).toContainText("结构化风险位");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22000");
  await expect(page.locator("#replyExtractionList")).not.toContainText("22123");
  await expect(page.locator("#replyExtractionList")).not.toContainText("候选区域");
});
