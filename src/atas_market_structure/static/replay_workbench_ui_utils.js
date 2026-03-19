export function timeframeLabel(value) {
  return {
    "1m": "1分",
    "5m": "5分",
    "15m": "15分",
    "30m": "30分",
    "1h": "1小时",
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
    unverified: "未核对",
    verified: "已核对",
    durable: "已固化",
    invalidated: "已作废",
  }[status] || status;
}

export function translateAcquisitionMode(mode) {
  return {
    cache_reuse: "缓存复用",
    local_history: "本地连续流",
    atas_fetch: "ATAS 历史",
  }[mode] || mode;
}

export function createThreadId() {
  return `thread-${Math.random().toString(16).slice(2, 10)}`;
}

export function getPresetThreadMeta(preset) {
  return {
    recent_20_bars: { id: "recent-20-bars", title: "最近20根K线" },
    recent_20_minutes: { id: "recent-20-minutes", title: "最近20分钟" },
    focus_regions: { id: "focus-regions", title: "重点区域" },
    trapped_large_orders: { id: "trapped-large-orders", title: "被套大单" },
    live_depth: { id: "live-depth", title: "实时挂单" },
    general: { id: "main", title: "主线程" },
  }[preset] || { id: createThreadId(), title: "新线程" };
}

export function renderList(items) {
  if (!items || !items.length) {
    return `<p></p>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}
