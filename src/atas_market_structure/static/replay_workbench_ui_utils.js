const STORAGE_PREFIX = "replay-workbench/v2";

export function timeframeLabel(value) {
  return {
    "1m": "1分",
    "5m": "5分",
    "15m": "15分",
    "30m": "30分",
    "1h": "1小时",
    "4h": "4小时",
    "1d": "日线",
  }[value] || value;
}

export function translateAction(action) {
  return {
    cache_hit: "命中缓存",
    built_from_local_history: "已从本地连续流重建",
    built_from_atas_history: "已从 ATAS 历史重建",
    atas_fetch_required: "需要补抓 ATAS 历史",
  }[action] || action;
}

export function translateVerificationStatus(status) {
  return {
    draft: "草稿",
    unverified: "未核对",
    verified: "已核对",
    durable: "已固化",
    invalidated: "已作废",
    active: "活动中",
    triggered: "已触发",
    tp_hit: "止盈命中",
    sl_hit: "止损命中",
    expired: "已过期",
    hidden: "已隐藏",
    archived: "已归档",
    completed: "已完成",
  }[status] || status;
}

export function translateAcquisitionMode(mode) {
  return {
    cache_reuse: "缓存复用",
    local_history: "本地连续流",
    atas_fetch: "ATAS 历史",
  }[mode] || mode;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

export function renderList(items) {
  if (!items || !items.length) {
    return `<p></p>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}

export function createThreadId(prefix = "session") {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

export function createMessageId() {
  return `msg-${Math.random().toString(16).slice(2, 10)}`;
}

export function createPlanId() {
  return `plan-${Math.random().toString(16).slice(2, 10)}`;
}

export function getPresetThreadMeta(preset) {
  return {
    recent_20_bars: { id: "recent-20-bars", title: "最近20根K线" },
    recent_20_minutes: { id: "recent-20-minutes", title: "最近20分钟" },
    focus_regions: { id: "focus-regions", title: "重点区域" },
    trapped_large_orders: { id: "trapped-large-orders", title: "挂单结构" },
    live_depth: { id: "live-depth", title: "实时挂单" },
    general: { id: "session-01", title: "01" },
  }[preset] || { id: createThreadId(), title: "新会话" };
}

export function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

export function readStorage(key, fallback = null) {
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}:${key}`);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    return fallback;
  }
}

export function writeStorage(key, value) {
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}:${key}`, JSON.stringify(value));
  } catch (error) {
    // ignore persistence errors
  }
}

export function removeStorage(key) {
  try {
    window.localStorage.removeItem(`${STORAGE_PREFIX}:${key}`);
  } catch (error) {
    // ignore persistence errors
  }
}

export function pickModelOptions() {
  return [
    { value: "", label: "服务端默认" },
    { value: "gpt-4.1", label: "GPT-4.1" },
    { value: "gpt-4o", label: "GPT-4o" },
    { value: "claude-sonnet", label: "Claude Sonnet" },
    { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  ];
}

export function formatPrice(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : "待定";
}

export function summarizeText(text, maxLength = 180) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}…`;
}

export function sanitizeReplayCandles(candles = [], options = {}) {
  const {
    context = "replay",
    log = true,
  } = options || {};
  if (!Array.isArray(candles) || !candles.length) {
    return [];
  }
  const deduped = new Map();
  let droppedCount = 0;
  let duplicateCount = 0;
  let correctedCount = 0;
  let unsortedCount = 0;
  let previousTimeMs = null;

  candles.forEach((raw) => {
    if (!raw || typeof raw !== "object" || !raw.started_at) {
      droppedCount += 1;
      return;
    }
    const startedAtMs = Date.parse(raw.started_at);
    if (!Number.isFinite(startedAtMs)) {
      droppedCount += 1;
      return;
    }
    const open = Number(raw.open);
    const high = Number(raw.high);
    const low = Number(raw.low);
    const close = Number(raw.close);
    if (![open, high, low, close].every((value) => Number.isFinite(value))) {
      droppedCount += 1;
      return;
    }
    if (previousTimeMs != null && startedAtMs < previousTimeMs) {
      unsortedCount += 1;
    }
    previousTimeMs = startedAtMs;
    const normalizedHigh = Math.max(open, high, low, close);
    const normalizedLow = Math.min(open, high, low, close);
    if (normalizedHigh !== high || normalizedLow !== low) {
      correctedCount += 1;
    }
    const endedAtMs = Date.parse(raw.ended_at || raw.started_at);
    const safeStartedAt = new Date(startedAtMs).toISOString();
    const safeEndedAtMs = Number.isFinite(endedAtMs) && endedAtMs >= startedAtMs
      ? endedAtMs
      : startedAtMs;
    const safeEndedAt = new Date(safeEndedAtMs).toISOString();
    const dedupeKey = String(startedAtMs);
    if (deduped.has(dedupeKey)) {
      duplicateCount += 1;
    }
    deduped.set(dedupeKey, {
      ...raw,
      started_at: safeStartedAt,
      ended_at: safeEndedAt,
      open,
      high: normalizedHigh,
      low: normalizedLow,
      close,
      volume: raw.volume == null ? raw.volume : Number(raw.volume),
      delta: raw.delta == null ? raw.delta : Number(raw.delta),
      bid_volume: raw.bid_volume == null ? raw.bid_volume : Number(raw.bid_volume),
      ask_volume: raw.ask_volume == null ? raw.ask_volume : Number(raw.ask_volume),
    });
  });

  const normalized = Array.from(deduped.values()).sort((left, right) => (
    Date.parse(left.started_at) - Date.parse(right.started_at)
  ));
  if (log && (droppedCount > 0 || duplicateCount > 0 || correctedCount > 0 || unsortedCount > 0)) {
    console.warn(
      `sanitizeReplayCandles[${context}]: input=${candles.length} output=${normalized.length} dropped=${droppedCount} deduped=${duplicateCount} corrected=${correctedCount} unsorted=${unsortedCount}`,
    );
  }
  return normalized;
}

export function normalizeReplaySnapshot(snapshot, options = {}) {
  if (!snapshot || typeof snapshot !== "object") {
    return snapshot;
  }
  return {
    ...snapshot,
    candles: sanitizeReplayCandles(snapshot.candles, options),
  };
}

export function normalizeParagraphs(text) {
  return String(text || "")
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function deriveSessionOrdinal(index) {
  return String(index + 1).padStart(2, "0");
}
