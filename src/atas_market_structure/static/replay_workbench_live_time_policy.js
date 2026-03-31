const TIMEFRAME_MINUTES = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "30m": 30,
  "1h": 60,
  "4h": 240,
  "1d": 1440,
};

export function getTimeframeMinutes(timeframe) {
  const normalized = String(timeframe || "").trim().toLowerCase();
  if (TIMEFRAME_MINUTES[normalized]) {
    return TIMEFRAME_MINUTES[normalized];
  }
  const parsed = Number.parseInt(normalized, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export function buildBarBucketBoundsMs(bar, timeframe) {
  const startedAtMs = Date.parse(bar?.started_at || "");
  if (!Number.isFinite(startedAtMs)) {
    return null;
  }
  const timeframeMinutes = getTimeframeMinutes(timeframe);
  return {
    startMs: startedAtMs,
    endMs: startedAtMs + (timeframeMinutes * 60 * 1000),
  };
}

export function isTimestampWithinBarBucket(timestamp, bar, timeframe) {
  const bounds = buildBarBucketBoundsMs(bar, timeframe);
  const observedAtMs = Date.parse(timestamp || "");
  if (!bounds || !Number.isFinite(observedAtMs)) {
    return false;
  }
  return observedAtMs >= bounds.startMs && observedAtMs < bounds.endMs;
}

export function isTimestampBeyondBarBucket(timestamp, bar, timeframe) {
  const bounds = buildBarBucketBoundsMs(bar, timeframe);
  const observedAtMs = Date.parse(timestamp || "");
  if (!bounds || !Number.isFinite(observedAtMs)) {
    return false;
  }
  return observedAtMs >= bounds.endMs;
}
