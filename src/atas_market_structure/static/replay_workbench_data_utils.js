export async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = rawText;
    }
  }
  if (!response.ok) {
    if (payload && typeof payload === "object") {
      throw new Error(payload.detail || payload.error || "request failed");
    }
    throw new Error(rawText || `request failed (${response.status})`);
  }
  return payload && typeof payload === "object" ? payload : {};
}

export function toUtcString(localValue) {
  if (!localValue) {
    return null;
  }
  return new Date(localValue).toISOString();
}

export function toLocalInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

export function createCacheKeyHelpers({ els }) {
  function buildCacheKey() {
    const symbol = (els.instrumentSymbol.value.trim() || "UNKNOWN").toUpperCase();
    const timeframe = els.displayTimeframe.value;
    const windowStart = toUtcString(els.windowStart.value) || "missing-start";
    const windowEnd = toUtcString(els.windowEnd.value) || "missing-end";
    return `${symbol}|${timeframe}|${windowStart}|${windowEnd}`;
  }

  function syncCacheKey() {
    els.cacheKey.value = buildCacheKey();
  }

  function applyWindowPreset(timeframe, lookbackDays) {
    // 限制最大加载天数为7天
    const maxDays = 7;
    const actualDays = Math.min(lookbackDays, maxDays);
    
    const now = new Date();
    const start = new Date(now.getTime() - (actualDays * 24 * 60 * 60 * 1000));
    els.displayTimeframe.value = timeframe;
    els.windowStart.value = toLocalInputValue(start);
    els.windowEnd.value = toLocalInputValue(now);
    syncCacheKey();
  }

  return {
    buildCacheKey,
    syncCacheKey,
    applyWindowPreset,
  };
}
