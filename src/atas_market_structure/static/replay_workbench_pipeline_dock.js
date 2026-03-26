const POLL_INTERVAL_MS = 1200;
const COLLAPSE_STORAGE_KEY = "atas-market-structure.replay.pipeline-dock-collapsed";

const FLOW_COLORS = {
  atas: {
    fill: "#d9b78c",
    accent: "#f1dcc0",
    glow: "rgba(217, 183, 140, 0.16)",
    pipe: "rgba(217, 183, 140, 0.18)",
  },
  sqlite_raw: {
    fill: "#caa072",
    surface: "#edd7ba",
    glow: "rgba(202, 160, 114, 0.14)",
    pipe: "rgba(202, 160, 114, 0.16)",
  },
  clickhouse_1m: {
    fill: "#74bcb5",
    surface: "#d9efed",
    glow: "rgba(116, 188, 181, 0.14)",
    pipe: "rgba(116, 188, 181, 0.16)",
  },
  clickhouse_5m: {
    fill: "#86add8",
    surface: "#dce8f8",
    glow: "rgba(134, 173, 216, 0.14)",
    pipe: "rgba(134, 173, 216, 0.16)",
  },
  clickhouse_15m: {
    fill: "#9fbd7f",
    surface: "#e7f0da",
    glow: "rgba(159, 189, 127, 0.14)",
    pipe: "rgba(159, 189, 127, 0.16)",
  },
};

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return response.json();
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatPercent(value) {
  return `${Math.max(0, Math.min(100, Math.round(Number(value || 0))))}%`;
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(date);
}

function formatRate(value, unit = "/s") {
  const normalized = Number(value || 0);
  return `${normalized.toFixed(normalized >= 10 ? 1 : 2)}${unit}`;
}

function formatCompactRate(value, { raw = false, prefix = true } = {}) {
  const normalized = Number(value || 0);
  const label = formatRate(normalized, raw ? " raw/s" : "/s");
  return `${prefix && normalized > 0 ? "+" : ""}${label}`;
}

function getChartBackend(snapshot) {
  const backend = snapshot?.chart_backend || {};
  const engine = String(backend.engine || "").trim() || "Chart Store";
  const engineShort = String(backend.engine_short || backend.label_prefix || "").trim() || "主图";
  const storageKey = String(backend.storage_key || "clickhouse_chart").trim() || "clickhouse_chart";
  return {
    engine,
    engineShort,
    storageKey,
    mode: String(backend.mode || "unknown"),
  };
}

function getChartDownstream(snapshot) {
  const instant = snapshot?.instant_flow || {};
  return instant?.sqlite_to_chart || instant?.sqlite_to_clickhouse || {};
}

function readChartMetric(container, timeframe) {
  if (timeframe === "1m") {
    return Number(container?.chart_1m ?? container?.clickhouse_1m ?? 0);
  }
  if (timeframe === "5m") {
    return Number(container?.chart_5m ?? container?.clickhouse_5m ?? 0);
  }
  return Number(container?.chart_15m ?? container?.clickhouse_15m ?? 0);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeReadStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    console.warn("读取本地存储失败:", error);
    return null;
  }
}

function safeWriteStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn("写入本地存储失败:", error);
  }
}

class SourceNode {
  constructor(label, colors) {
    this.label = label;
    this.colors = colors;
    this.rect = { x: 0, y: 0, w: 64, h: 34 };
    this.rate = 0;
    this.count = 0;
    this.windowSeconds = 8;
    this.phase = Math.random() * Math.PI * 2;
  }

  setRect(rect) {
    this.rect = { ...rect };
  }

  sync(leg) {
    this.rate = Number(leg?.per_second || 0);
    this.count = Number(leg?.count || 0);
    this.windowSeconds = Math.max(1, Number(leg?.window_seconds || leg?.windowSeconds || 8));
  }

  update(dt) {
    const speedFactor = clampNumber(this.rate, 0, 5);
    this.phase += dt * (0.28 + speedFactor * 0.14);
  }

  draw(ctx) {
    const { x, y, w, h } = this.rect;
    const radius = Math.min(16, h / 2);
    const active = this.rate > 0.001;

    ctx.save();
    if (active) {
      ctx.shadowColor = this.colors.glow;
      ctx.shadowBlur = 12;
    }

    this.#roundedRect(ctx, x, y, w, h, radius);
    const shell = ctx.createLinearGradient(x, y, x, y + h);
    shell.addColorStop(0, "rgba(23, 35, 50, 0.92)");
    shell.addColorStop(1, "rgba(11, 19, 31, 0.94)");
    ctx.fillStyle = shell;
    ctx.fill();

    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(214, 224, 236, 0.14)";
    ctx.stroke();

    const dotX = x + 12;
    const dotY = y + h / 2;
    ctx.beginPath();
    ctx.fillStyle = active ? this.colors.fill : "rgba(161, 173, 191, 0.45)";
    ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
    ctx.fill();

    if (active) {
      ctx.beginPath();
      ctx.strokeStyle = "rgba(243, 212, 177, 0.28)";
      ctx.lineWidth = 1.1;
      ctx.arc(dotX, dotY, 7 + Math.sin(this.phase) * 1.1, 0, Math.PI * 2);
      ctx.stroke();

      for (let index = 0; index < 3; index += 1) {
        const offset = ((this.phase * 18) + index * 12) % (w - 26);
        ctx.beginPath();
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = "rgba(243, 212, 177, 0.18)";
        ctx.moveTo(x + 18 + offset, y + h / 2);
        ctx.lineTo(x + 28 + offset, y + h / 2);
        ctx.stroke();
      }
    }

    ctx.fillStyle = "#edf4ff";
    ctx.font = '700 11px "Bahnschrift", "Trebuchet MS", sans-serif';
    ctx.fillText(this.label, x + 22, y + 13);
    ctx.font = '600 9px "Bahnschrift", "Trebuchet MS", sans-serif';
    ctx.fillStyle = active ? "#f3d4b1" : "rgba(188, 203, 219, 0.58)";
    ctx.fillText(formatRate(this.rate, " raw/s"), x + 22, y + 24);

    ctx.restore();
  }

  outlet() {
    return {
      x: this.rect.x + this.rect.w,
      y: this.rect.y + this.rect.h / 2,
    };
  }

  #roundedRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}

class TankNode {
  constructor(key, label, colors) {
    this.key = key;
    this.label = label;
    this.colors = colors;
    this.rect = { x: 0, y: 0, w: 72, h: 48 };
    this.fillPercent = 0;
    this.targetFillPercent = 0;
    this.activityRate = 0;
    this.phase = Math.random() * Math.PI * 2;
  }

  setRect(rect) {
    this.rect = { ...rect };
  }

  sync(pool, activityRate = 0) {
    if (pool?.label) {
      this.label = String(pool.label);
    }
    this.targetFillPercent = clampNumber(Number(pool?.fill_percent || 0), 0, 100);
    this.activityRate = Number(activityRate || 0);
  }

  update(dt) {
    const blend = Math.min(1, dt * 2.2);
    this.fillPercent += (this.targetFillPercent - this.fillPercent) * blend;
    this.phase += dt * (0.18 + clampNumber(this.activityRate, 0, 5) * 0.1);
  }

  draw(ctx) {
    const { x, y, w, h } = this.rect;
    const radius = 14;
    const fill = clampNumber(this.fillPercent / 100, 0, 1);
    const waterTop = y + h * (1 - fill);
    const waveAmplitude = 1.2 + clampNumber(this.activityRate, 0, 4) * 0.22;
    const terminalW = Math.max(6, Math.round(w * 0.08));
    const terminalH = Math.max(10, Math.round(h * 0.2));
    const bodyW = w - terminalW - 4;
    const bodyX = x;
    const bodyY = y;
    const bodyH = h;
    const terminalX = x + bodyW + 2;
    const terminalY = y + (h - terminalH) / 2;

    ctx.save();
    ctx.shadowColor = this.colors.glow;
    ctx.shadowBlur = 12;

    this.#roundedRect(ctx, bodyX, bodyY, bodyW, bodyH, radius);
    const shell = ctx.createLinearGradient(x, y, x, y + h);
    shell.addColorStop(0, "rgba(17, 28, 41, 0.9)");
    shell.addColorStop(1, "rgba(8, 15, 26, 0.96)");
    ctx.fillStyle = shell;
    ctx.fill();
    ctx.strokeStyle = "rgba(214, 224, 236, 0.14)";
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.beginPath();
    ctx.roundRect(terminalX, terminalY, terminalW, terminalH, 4);
    ctx.fillStyle = "rgba(214, 224, 236, 0.18)";
    ctx.fill();
    ctx.strokeStyle = "rgba(214, 224, 236, 0.12)";
    ctx.stroke();

    this.#roundedRect(ctx, bodyX, bodyY, bodyW, bodyH, radius);
    ctx.clip();

    const fillGradient = ctx.createLinearGradient(bodyX, waterTop, bodyX, bodyY + bodyH);
    fillGradient.addColorStop(0, this.colors.surface);
    fillGradient.addColorStop(0.26, `${this.colors.surface}cc`);
    fillGradient.addColorStop(1, this.colors.fill);
    ctx.fillStyle = fillGradient;
    ctx.beginPath();
    ctx.moveTo(bodyX, bodyY + bodyH);
    ctx.lineTo(bodyX, waterTop);
    for (let i = 0; i <= 16; i += 1) {
      const px = bodyX + (bodyW / 16) * i;
      const py = waterTop + Math.sin(this.phase + i * 0.45) * waveAmplitude;
      ctx.lineTo(px, py);
    }
    ctx.lineTo(bodyX + bodyW, bodyY + bodyH);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "rgba(255,255,255,0.05)";
    ctx.fillRect(bodyX, bodyY, bodyW, bodyH);

    if (this.activityRate > 0.01) {
      const chargeGlow = ctx.createLinearGradient(bodyX, bodyY, bodyX + bodyW, bodyY);
      chargeGlow.addColorStop(0, "rgba(255,255,255,0)");
      chargeGlow.addColorStop(0.5, `${this.colors.surface}66`);
      chargeGlow.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = chargeGlow;
      ctx.fillRect(bodyX + 4, waterTop - 2, Math.max(18, bodyW * 0.42), 4);
    }

    ctx.restore();

    ctx.save();
    ctx.shadowColor = "rgba(3, 7, 18, 0.46)";
    ctx.shadowBlur = 4;
    ctx.fillStyle = "#edf4ff";
    ctx.font = '700 9px "Bahnschrift", "Trebuchet MS", sans-serif';
    ctx.textAlign = "center";
    ctx.fillText(this.label, x + w / 2, y + h - 6);
    ctx.font = '600 8px "Bahnschrift", "Trebuchet MS", sans-serif';
    ctx.fillStyle = "rgba(203, 216, 233, 0.76)";
    ctx.fillText(formatPercent(this.fillPercent), x + w / 2, y - 4);
    ctx.textAlign = "start";
    ctx.restore();
  }

  inlet() {
    return {
      x: this.rect.x,
      y: this.rect.y + this.rect.h / 2,
    };
  }

  outlet() {
    return {
      x: this.rect.x + this.rect.w,
      y: this.rect.y + this.rect.h / 2,
    };
  }

  #roundedRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}

class FlowStage {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.nodes = {
      atas: new SourceNode("ATAS", FLOW_COLORS.atas),
      sqlite_raw: new TankNode("sqlite_raw", "SQLite", FLOW_COLORS.sqlite_raw),
      clickhouse_1m: new TankNode("clickhouse_1m", "CK 1m", FLOW_COLORS.clickhouse_1m),
      clickhouse_5m: new TankNode("clickhouse_5m", "CK 5m", FLOW_COLORS.clickhouse_5m),
      clickhouse_15m: new TankNode("clickhouse_15m", "CK 15m", FLOW_COLORS.clickhouse_15m),
    };
    this.links = {
      atas_to_sqlite: this.#createLink("atas_to_sqlite", FLOW_COLORS.atas),
      sqlite_to_clickhouse_1m: this.#createLink("sqlite_to_clickhouse_1m", FLOW_COLORS.clickhouse_1m),
      sqlite_to_clickhouse_5m: this.#createLink("sqlite_to_clickhouse_5m", FLOW_COLORS.clickhouse_5m),
      sqlite_to_clickhouse_15m: this.#createLink("sqlite_to_clickhouse_15m", FLOW_COLORS.clickhouse_15m),
    };
    this.droplets = [];
    this.collapsed = false;
    this.documentVisible = !document.hidden;
    this._destroyed = false;
    this._settleUntil = 0;
    this._animationFrame = null;
    this._lastFrame = performance.now();
    this._resizeHandler = () => this.resize();
    this._resizeObserver = typeof ResizeObserver === "function"
      ? new ResizeObserver(() => this.resize())
      : null;
    this.resize();
    if (this._resizeObserver) {
      this._resizeObserver.observe(this.canvas);
    } else {
      window.addEventListener("resize", this._resizeHandler);
    }
    this.draw();
  }

  updateSnapshot(snapshot) {
    const pools = new Map((Array.isArray(snapshot?.recent_pools) ? snapshot.recent_pools : []).map((item) => [item.key, item]));
    const instant = snapshot?.instant_flow || {};
    const rawLeg = {
      ...(instant?.atas_to_sqlite || {}),
      window_seconds: Number(instant?.window_seconds || 8),
    };
    const downstream = getChartDownstream(snapshot);

    const ck1Leg = { ...(downstream["1m"] || {}), window_seconds: Number(instant?.window_seconds || 8) };
    const ck5Leg = { ...(downstream["5m"] || {}), window_seconds: Number(instant?.window_seconds || 8) };
    const ck15Leg = { ...(downstream["15m"] || {}), window_seconds: Number(instant?.window_seconds || 8) };

    this.nodes.atas.sync(rawLeg);
    this.nodes.sqlite_raw.sync(pools.get("sqlite_raw"), rawLeg.per_second);
    this.nodes.clickhouse_1m.sync(pools.get("clickhouse_1m"), ck1Leg.per_second);
    this.nodes.clickhouse_5m.sync(pools.get("clickhouse_5m"), ck5Leg.per_second);
    this.nodes.clickhouse_15m.sync(pools.get("clickhouse_15m"), ck15Leg.per_second);

    this.#syncLink("atas_to_sqlite", rawLeg, this.nodes.atas.outlet(), this.nodes.sqlite_raw.inlet());
    this.#syncLink("sqlite_to_clickhouse_1m", ck1Leg, this.nodes.sqlite_raw.outlet(), this.nodes.clickhouse_1m.inlet());
    this.#syncLink("sqlite_to_clickhouse_5m", ck5Leg, this.nodes.sqlite_raw.outlet(), this.nodes.clickhouse_5m.inlet());
    this.#syncLink("sqlite_to_clickhouse_15m", ck15Leg, this.nodes.sqlite_raw.outlet(), this.nodes.clickhouse_15m.inlet());

    this._settleUntil = performance.now() + 900;
    this.resize();
    this.#syncAnimationState();
    if (!this.#shouldAnimate()) {
      this.draw();
    }
  }

  setCollapsed(collapsed) {
    this.collapsed = !!collapsed;
    this.#syncAnimationState();
    if (!this.collapsed) {
      window.requestAnimationFrame(() => {
        this.resize();
        this.draw();
      });
    }
  }

  setDocumentVisible(isVisible) {
    this.documentVisible = !!isVisible;
    this.#syncAnimationState();
    if (this.documentVisible && !this.collapsed) {
      this.resize();
      this.draw();
    }
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) {
      return;
    }
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.round(bounds.width * ratio));
    this.canvas.height = Math.max(1, Math.round(bounds.height * ratio));
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.#layout(bounds.width, bounds.height);
  }

  destroy() {
    this._destroyed = true;
    if (this._animationFrame) {
      cancelAnimationFrame(this._animationFrame);
      this._animationFrame = null;
    }
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
    } else {
      window.removeEventListener("resize", this._resizeHandler);
    }
  }

  #createLink(key, colors) {
    return {
      key,
      colors,
      from: { x: 0, y: 0 },
      to: { x: 0, y: 0 },
      rate: 0,
      count: 0,
      windowSeconds: 8,
      active: false,
      emissionCarry: 0,
    };
  }

  #syncLink(key, leg, from, to) {
    const link = this.links[key];
    if (!link) {
      return;
    }
    link.from = { ...from };
    link.to = { ...to };
    link.rate = Number(leg?.per_second || 0);
    link.count = Number(leg?.count || 0);
    link.windowSeconds = Math.max(1, Number(leg?.window_seconds || 8));
    link.active = link.count > 0;
  }

  #layout(width, height) {
    const insetX = 10;
    const sourceW = clampNumber(width * 0.14, 60, 74);
    const sourceH = clampNumber(height * 0.34, 28, 34);
    const sqliteW = clampNumber(width * 0.16, 74, 92);
    const sqliteH = clampNumber(height * 0.76, 60, 74);
    const targetW = clampNumber(width * 0.12, 48, 62);
    const targetH = clampNumber(height * 0.31, 24, 32);
    const gap = clampNumber(width * 0.015, 6, 10);
    const sourceX = insetX;
    const sourceY = (height - sourceH) / 2;
    const sqliteX = sourceX + sourceW + 18;
    const sqliteY = (height - sqliteH) / 2;
    const targetsX = width - insetX - targetW;
    const topY = 7;
    const centerY = (height - targetH) / 2;
    const bottomY = height - targetH - 7;

    this.nodes.atas.setRect({ x: sourceX, y: sourceY, w: sourceW, h: sourceH });
    this.nodes.sqlite_raw.setRect({ x: sqliteX, y: sqliteY, w: sqliteW, h: sqliteH });
    this.nodes.clickhouse_1m.setRect({ x: targetsX, y: topY, w: targetW, h: targetH });
    this.nodes.clickhouse_5m.setRect({ x: targetsX, y: centerY, w: targetW, h: targetH });
    this.nodes.clickhouse_15m.setRect({ x: targetsX, y: bottomY, w: targetW, h: targetH });
  }

  #shouldAnimate() {
    if (this._destroyed || this.collapsed || !this.documentVisible) {
      return false;
    }
    if (performance.now() < this._settleUntil) {
      return true;
    }
    return Object.values(this.links).some((link) => link.active);
  }

  #syncAnimationState() {
    if (this.#shouldAnimate()) {
      if (!this._animationFrame) {
        this._lastFrame = performance.now();
        this._animationFrame = requestAnimationFrame((timestamp) => this.#loop(timestamp));
      }
      return;
    }
    if (this._animationFrame) {
      cancelAnimationFrame(this._animationFrame);
      this._animationFrame = null;
    }
  }

  #loop(timestamp) {
    if (this._destroyed) {
      return;
    }
    const dt = Math.min(0.05, (timestamp - this._lastFrame) / 1000);
    this._lastFrame = timestamp;
    this.#update(dt);
    this.draw();
    if (this.#shouldAnimate()) {
      this._animationFrame = requestAnimationFrame((nextTimestamp) => this.#loop(nextTimestamp));
    } else {
      this._animationFrame = null;
      this.draw();
    }
  }

  #update(dt) {
    this.nodes.atas.update(dt);
    this.nodes.sqlite_raw.update(dt);
    this.nodes.clickhouse_1m.update(dt);
    this.nodes.clickhouse_5m.update(dt);
    this.nodes.clickhouse_15m.update(dt);

    for (const link of Object.values(this.links)) {
      if (!link.active) {
        link.emissionCarry = 0;
        continue;
      }
      const emissionRate = clampNumber(link.rate * 0.46, 0.08, link.key === "atas_to_sqlite" ? 1.35 : 0.92);
      link.emissionCarry += emissionRate * dt;
      while (link.emissionCarry >= 1) {
        link.emissionCarry -= 1;
        this.droplets.push({
          key: link.key,
          from: { ...link.from },
          to: { ...link.to },
          progress: Math.random() * 0.12,
          speed: 0.06 + Math.min(link.rate, 6) * 0.02 + Math.random() * 0.018,
          size: 1.8 + Math.random() * 1.4,
          color: link.colors.surface,
          alpha: 0.24 + Math.random() * 0.12,
        });
      }
    }

    this.droplets = this.droplets.filter((droplet) => droplet.progress < 1.04);
    for (const droplet of this.droplets) {
      droplet.progress += droplet.speed * dt;
    }
  }

  draw() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (!width || !height) {
      return;
    }
    const ctx = this.ctx;
    ctx.clearRect(0, 0, width, height);

    const background = ctx.createLinearGradient(0, 0, width, height);
    background.addColorStop(0, "rgba(9, 16, 26, 0.96)");
    background.addColorStop(0.58, "rgba(7, 15, 24, 0.98)");
    background.addColorStop(1, "rgba(5, 12, 20, 1)");
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, width, height);

    this.#drawBackdrop(width, height);
    this.#drawLink(this.links.atas_to_sqlite);
    this.#drawLink(this.links.sqlite_to_clickhouse_1m);
    this.#drawLink(this.links.sqlite_to_clickhouse_5m);
    this.#drawLink(this.links.sqlite_to_clickhouse_15m);
    for (const droplet of this.droplets) {
      this.#drawDroplet(droplet);
    }
    this.nodes.atas.draw(ctx);
    this.nodes.sqlite_raw.draw(ctx);
    this.nodes.clickhouse_1m.draw(ctx);
    this.nodes.clickhouse_5m.draw(ctx);
    this.nodes.clickhouse_15m.draw(ctx);
  }

  #drawBackdrop(width, height) {
    const ctx = this.ctx;
    ctx.save();
    const warmGlow = ctx.createRadialGradient(width * 0.18, height * 0.5, 4, width * 0.18, height * 0.5, height * 0.7);
    warmGlow.addColorStop(0, "rgba(243, 212, 177, 0.08)");
    warmGlow.addColorStop(1, "rgba(243, 212, 177, 0)");
    ctx.fillStyle = warmGlow;
    ctx.fillRect(0, 0, width, height);

    const coolGlow = ctx.createRadialGradient(width * 0.86, height * 0.18, 4, width * 0.86, height * 0.18, height * 0.72);
    coolGlow.addColorStop(0, "rgba(157, 200, 238, 0.06)");
    coolGlow.addColorStop(1, "rgba(157, 200, 238, 0)");
    ctx.fillStyle = coolGlow;
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  }

  #drawLink(link, { showRate = false, unit = "/s" } = {}) {
    const ctx = this.ctx;
    const { from, to } = link;
    const cp1x = from.x + (to.x - from.x) * (link.key === "atas_to_sqlite" ? 0.42 : 0.34);
    const cp1y = from.y;
    const cp2x = from.x + (to.x - from.x) * 0.72;
    const cp2y = to.y;
    const glowAlpha = link.active ? clampNumber(0.1 + link.rate * 0.05, 0.1, 0.24) : 0.04;

    ctx.save();
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(8, 15, 24, 0.96)";
    ctx.lineWidth = link.key === "atas_to_sqlite" ? 5 : 4.4;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, to.x, to.y);
    ctx.stroke();

    const gradient = ctx.createLinearGradient(from.x, from.y, to.x, to.y);
    gradient.addColorStop(0, link.colors.pipe);
    gradient.addColorStop(1, link.active ? `${link.colors.surface}82` : "rgba(196, 209, 223, 0.1)");
    ctx.strokeStyle = gradient;
    ctx.lineWidth = link.key === "atas_to_sqlite" ? 2 : 1.8;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, to.x, to.y);
    ctx.stroke();

    if (link.active) {
      ctx.strokeStyle = `${link.colors.surface}${Math.round(glowAlpha * 255).toString(16).padStart(2, "0")}`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, to.x, to.y);
      ctx.stroke();
    }

    if (showRate) {
      const labelX = from.x + (to.x - from.x) * 0.56;
      const labelY = Math.min(from.y, to.y) - 10;
      const text = formatRate(link.rate, unit);
      ctx.font = '700 9px "Bahnschrift", "Trebuchet MS", sans-serif';
      const metrics = ctx.measureText(text);
      const textWidth = metrics.width + 14;
      ctx.fillStyle = "rgba(12, 20, 31, 0.84)";
      ctx.strokeStyle = "rgba(243, 212, 177, 0.16)";
      this.#roundedRect(ctx, labelX - textWidth / 2, labelY - 9, textWidth, 18, 9);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = link.active ? "#f3d4b1" : "rgba(193, 206, 219, 0.72)";
      ctx.textAlign = "center";
      ctx.fillText(text, labelX, labelY + 3);
      ctx.textAlign = "start";
    }

    ctx.restore();
  }

  #drawDroplet(droplet) {
    const ctx = this.ctx;
    const cp1x = droplet.from.x + (droplet.to.x - droplet.from.x) * (droplet.key === "atas_to_sqlite" ? 0.42 : 0.34);
    const cp1y = droplet.from.y;
    const cp2x = droplet.from.x + (droplet.to.x - droplet.from.x) * 0.72;
    const cp2y = droplet.to.y;
    const t = droplet.progress;
    const mt = 1 - t;
    const x =
      mt ** 3 * droplet.from.x
      + 3 * mt ** 2 * t * cp1x
      + 3 * mt * t ** 2 * cp2x
      + t ** 3 * droplet.to.x;
    const y =
      mt ** 3 * droplet.from.y
      + 3 * mt ** 2 * t * cp1y
      + 3 * mt * t ** 2 * cp2y
      + t ** 3 * droplet.to.y;

    ctx.save();
    ctx.shadowColor = droplet.color;
    ctx.shadowBlur = 6;
    ctx.globalAlpha = droplet.alpha;
    ctx.fillStyle = droplet.color;
    ctx.beginPath();
    ctx.arc(x, y, droplet.size, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  #roundedRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
}

function createElements(doc = document) {
  return {
    dock: doc.getElementById("headerPipelineDock"),
    body: doc.getElementById("headerPipelineBody"),
    toggle: doc.getElementById("headerPipelineToggle"),
    note: doc.getElementById("headerPipelineNote"),
    pressure: doc.getElementById("headerPipelinePressure"),
    contract: doc.getElementById("headerPipelineContract"),
    root: doc.getElementById("headerPipelineRoot"),
    generatedAt: doc.getElementById("headerPipelineGeneratedAt"),
    poolReadout: doc.getElementById("headerPipelinePools"),
    todayValue: doc.getElementById("headerPipelineTodayValue"),
    todayMeta: doc.getElementById("headerPipelineTodayMeta"),
    totalValue: doc.getElementById("headerPipelineTotalValue"),
    totalMeta: doc.getElementById("headerPipelineTotalMeta"),
    canvas: doc.getElementById("headerPipelineCanvas"),
  };
}

function createEmptySnapshot(rootSymbol = "") {
  return {
    generated_at: null,
    flow_window_minutes: 15,
    chart_backend: {
      engine: "Chart Store",
      engine_short: "主图",
      storage_key: "clickhouse_chart",
    },
    selected_contract: {
      contract_symbol: "",
      root_symbol: rootSymbol || "",
      shared_chart_pool: false,
    },
    recent_pools: [
      { key: "sqlite_raw", label: "SQLite 暂存", count: 0, capacity: 1, fill_percent: 0, timeframe: "1m" },
      { key: "clickhouse_1m", label: "主图 1m", count: 0, capacity: 1, fill_percent: 0, timeframe: "1m" },
      { key: "clickhouse_5m", label: "主图 5m", count: 0, capacity: 1, fill_percent: 0, timeframe: "5m" },
      { key: "clickhouse_15m", label: "主图 15m", count: 0, capacity: 1, fill_percent: 0, timeframe: "15m" },
    ],
    instant_flow: {
      window_seconds: 8,
      atas_to_sqlite: {
        count: 0,
        per_second: 0,
        active: false,
      },
      sqlite_to_chart: {
        "1m": { count: 0, per_second: 0, active: false },
        "5m": { count: 0, per_second: 0, active: false },
        "15m": { count: 0, per_second: 0, active: false },
      },
      sqlite_to_clickhouse: {
        "1m": { count: 0, per_second: 0, active: false },
        "5m": { count: 0, per_second: 0, active: false },
        "15m": { count: 0, per_second: 0, active: false },
      },
      total_writes: 0,
    },
    write_pressure: {
      status: "quiet",
      raw_writes_per_minute: 0,
      note: "当前没有活动中的注水。",
    },
    today: {
      bar_date: "--",
      sqlite_raw_1m: 0,
      chart_1m: 0,
      chart_5m: 0,
      chart_15m: 0,
      clickhouse_1m: 0,
      clickhouse_5m: 0,
      clickhouse_15m: 0,
      write_gap_1m: 0,
    },
    totals: {
      chart_1m: 0,
      chart_5m: 0,
      chart_15m: 0,
      clickhouse_1m: 0,
      clickhouse_5m: 0,
      clickhouse_15m: 0,
    },
    message: "",
  };
}

function derivePressureStatus(snapshot) {
  const instant = snapshot?.instant_flow || {};
  const rawRate = Number(instant?.atas_to_sqlite?.per_second || 0);
  const downstream = getChartDownstream(snapshot);
  const downstreamRate =
    Number(downstream["1m"]?.per_second || 0)
    + Number(downstream["5m"]?.per_second || 0)
    + Number(downstream["15m"]?.per_second || 0);
  const totalRate = rawRate + downstreamRate;
  if (totalRate >= 4 || rawRate >= 3) {
    return "hot";
  }
  if (totalRate >= 0.25) {
    return "busy";
  }
  return "quiet";
}

function buildDockNote(snapshot, { contractSymbol, rootSymbol }) {
  if (snapshot?.message) {
    return snapshot.message;
  }
  const chartBackend = getChartBackend(snapshot);
  const instant = snapshot?.instant_flow || {};
  const rawRate = Number(instant?.atas_to_sqlite?.per_second || 0);
  const downstream = getChartDownstream(snapshot);
  const ck1Rate = Number(downstream["1m"]?.per_second || 0);
  const ck5Rate = Number(downstream["5m"]?.per_second || 0);
  const ck15Rate = Number(downstream["15m"]?.per_second || 0);
  const downstreamRate = ck1Rate + ck5Rate + ck15Rate;
  const flowWindow = Number(snapshot?.flow_window_minutes || 15);
  const writePressure = snapshot?.write_pressure || {};
  const rawWpm = Number(writePressure.raw_writes_per_minute || 0);
  const ck1Wpm = Number(writePressure.chart_1m_writes_per_minute || 0);
  const sharedNote = snapshot?.selected_contract?.shared_chart_pool
    ? `共享 Root ${rootSymbol || "--"}`
    : "";

  let flowState = "当前静止";
  if (rawRate > 0.001 && downstreamRate <= 0.001) {
    flowState = "只进暂存";
  } else if (rawRate <= 0.001 && downstreamRate > 0.001) {
    flowState = `暂存回写 ${chartBackend.engineShort}`;
  } else if (rawRate > 0.001 && downstreamRate > 0.001) {
    flowState = "前后段同步注水";
  }

  const pressureSummary =
    rawWpm > 0.01 || ck1Wpm > 0.01
      ? `近${flowWindow}m ${rawWpm.toFixed(1)} raw/min · ${chartBackend.engineShort} 1m ${ck1Wpm.toFixed(1)}/min`
      : (writePressure.note || `近${flowWindow}m 无新增`);

  return [flowState, pressureSummary, sharedNote].filter(Boolean).join(" · ");
}

export function mountReplayWorkbenchPipelineDock({ app, pollIntervalMs = POLL_INTERVAL_MS } = {}) {
  const els = createElements(document);
  if (!els.dock || !els.canvas) {
    return {
      start() {},
      refresh() {},
      requestRefresh() {},
      destroy() {},
    };
  }

  const stage = new FlowStage(els.canvas);
  const trackedListeners = [];
  let refreshTimer = null;
  let scheduledRefreshTimer = null;
  let requestInFlight = false;
  let refreshQueued = false;
  let collapsed = safeReadStorage(COLLAPSE_STORAGE_KEY) === "1";

  function addTrackedListener(target, type, handler, options) {
    if (!target || typeof target.addEventListener !== "function") {
      return;
    }
    target.addEventListener(type, handler, options);
    trackedListeners.push(() => target.removeEventListener(type, handler, options));
  }

  function setPressureState(status) {
    const normalized = String(status || "quiet").toLowerCase();
    els.dock.dataset.pressure = normalized;
    if (els.pressure) {
      els.pressure.dataset.pressure = normalized;
    }
  }

  function applyCollapsedState(nextCollapsed) {
    collapsed = !!nextCollapsed;
    els.dock.dataset.collapsed = collapsed ? "true" : "false";
    if (els.body) {
      els.body.hidden = collapsed;
    }
    if (els.toggle) {
      els.toggle.textContent = collapsed ? "展开" : "收起";
      els.toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    stage.setCollapsed(collapsed);
    safeWriteStorage(COLLAPSE_STORAGE_KEY, collapsed ? "1" : "0");
  }

  function resolveActiveSymbols() {
    const inputRoot = String(app?.els?.instrumentSymbol?.value || "").trim().toUpperCase();
    const snapshot = app?.state?.snapshot || null;
    const snapshotRoot = String(
      snapshot?.instrument?.root_symbol
      || snapshot?.instrument_symbol
      || snapshot?.instrument?.symbol
      || "",
    ).trim().toUpperCase();
    const snapshotContract = String(
      snapshot?.instrument?.contract_symbol
      || snapshot?.contract_symbol
      || "",
    ).trim().toUpperCase();
    const activeRoot = inputRoot || snapshotRoot;
    const useSnapshotContract = !!snapshotContract && !!snapshotRoot && snapshotRoot === activeRoot;
    return {
      rootSymbol: activeRoot,
      contractSymbol: useSnapshotContract ? snapshotContract : "",
    };
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const { rootSymbol, contractSymbol } = resolveActiveSymbols();
    if (contractSymbol) {
      params.set("contract_symbol", contractSymbol);
    }
    if (rootSymbol) {
      params.set("root_symbol", rootSymbol);
    }
    params.set("days", "10");
    params.set("flow_window_minutes", "15");
    return params.toString();
  }

  function renderHeader(snapshot) {
    const selected = snapshot?.selected_contract || {};
    const rootSymbol = selected.root_symbol || resolveActiveSymbols().rootSymbol || "--";
    const contractSymbol = selected.contract_symbol || "--";
    const instant = snapshot?.instant_flow || {};
    const rawRate = Number(instant?.atas_to_sqlite?.per_second || 0);
    const writePressure = snapshot?.write_pressure || {};
    const pressureStatus = writePressure.status || derivePressureStatus(snapshot);
    const noteText = buildDockNote(snapshot, { contractSymbol, rootSymbol });

    setPressureState(pressureStatus);
    if (els.pressure) {
      els.pressure.textContent = rawRate > 0.001 ? formatRate(rawRate, " raw/s") : "0.00 raw/s";
      els.pressure.title = `ATAS -> SQLite · ${formatRate(rawRate, " raw/s")} · ${(Number(writePressure.raw_writes_per_minute || 0)).toFixed(2)} raw/min`;
    }
    if (els.contract) {
      els.contract.textContent = `合约 ${contractSymbol}`;
    }
    if (els.root) {
      els.root.textContent = `Root ${rootSymbol || "--"}`;
    }
    if (els.generatedAt) {
      els.generatedAt.textContent = `更新 ${formatTime(snapshot?.generated_at)}`;
    }
    if (els.note) {
      els.note.textContent = noteText;
      els.note.title = noteText;
    }
  }

  function renderPools(snapshot) {
    if (!els.poolReadout) {
      return;
    }
    const pools = Array.isArray(snapshot?.recent_pools) ? snapshot.recent_pools : [];
    if (!pools.length) {
      els.poolReadout.innerHTML = "";
      return;
    }
    const poolMap = new Map(pools.map((pool) => [pool.key, pool]));
    const storageMap = new Map((Array.isArray(snapshot?.storage_locations) ? snapshot.storage_locations : []).map((item) => [item.key, item]));
    const chartBackend = getChartBackend(snapshot);
    const instant = snapshot?.instant_flow || {};
    const downstream = getChartDownstream(snapshot);
    const flowWindow = Number(snapshot?.flow_window_minutes || 15);
    const today = snapshot?.today || {};
    const items = [
      {
        key: "sqlite_raw",
        label: "暂存",
        pool: poolMap.get("sqlite_raw"),
        rate: Number(instant?.atas_to_sqlite?.per_second || 0),
        todayValue: today.sqlite_raw_1m,
        raw: true,
      },
      {
        key: "clickhouse_1m",
        label: poolMap.get("clickhouse_1m")?.label || `${chartBackend.engineShort} 1m`,
        pool: poolMap.get("clickhouse_1m"),
        rate: Number(downstream["1m"]?.per_second || 0),
        todayValue: readChartMetric(today, "1m"),
      },
      {
        key: "clickhouse_5m",
        label: poolMap.get("clickhouse_5m")?.label || `${chartBackend.engineShort} 5m`,
        pool: poolMap.get("clickhouse_5m"),
        rate: Number(downstream["5m"]?.per_second || 0),
        todayValue: readChartMetric(today, "5m"),
      },
      {
        key: "clickhouse_15m",
        label: poolMap.get("clickhouse_15m")?.label || `${chartBackend.engineShort} 15m`,
        pool: poolMap.get("clickhouse_15m"),
        rate: Number(downstream["15m"]?.per_second || 0),
        todayValue: readChartMetric(today, "15m"),
      },
    ];

    els.poolReadout.innerHTML = items
      .map((item) => {
        const pool = item.pool || { count: 0, fill_percent: 0, capacity: 0 };
        const rate = Number(item.rate || 0);
        const fillPercent = clampNumber(Number(pool.fill_percent || 0), 0, 100);
        const storage = storageMap.get(item.key) || storageMap.get(chartBackend.storageKey);
        const storageTitle = [storage?.engine, storage?.location, storage?.purpose].filter(Boolean).join(" · ");
        return `
          <article
            class="header-pipeline-pool-chip"
            data-pool-key="${escapeHtml(item.key)}"
            data-active="${rate > 0.001 || Number(pool.count || 0) > 0 ? "true" : "false"}"
            title="${escapeHtml(storageTitle)}"
          >
            <div class="header-pipeline-pool-head">
              <span class="header-pipeline-pool-name">${escapeHtml(item.label)}</span>
              <span class="header-pipeline-pool-rate">${escapeHtml(formatCompactRate(rate, { raw: !!item.raw }))}</span>
            </div>
            <div class="header-pipeline-pool-value-row">
              <strong>${formatNumber(pool.count)}</strong>
              <small>${formatPercent(fillPercent)}</small>
            </div>
            <div class="header-pipeline-pool-meta">近${flowWindow}m ${formatNumber(pool.count)} / ${formatNumber(pool.capacity || 0)} · 今 ${formatNumber(item.todayValue)}</div>
            <div class="header-pipeline-pool-track"><span style="width:${fillPercent}%"></span></div>
          </article>
        `;
      })
      .join("");
  }

  function renderSummaries(snapshot) {
    const today = snapshot?.today || {};
    const totals = snapshot?.totals || {};
    const chartBackend = getChartBackend(snapshot);
    const quota1m = Number(today.quota_1m || 1440);
    const todayChart1m = readChartMetric(today, "1m");
    const totalChart1m = readChartMetric(totals, "1m");
    const totalChart5m = readChartMetric(totals, "5m");
    const totalChart15m = readChartMetric(totals, "15m");

    if (els.todayValue) {
      els.todayValue.textContent = `${formatNumber(todayChart1m)} / ${formatNumber(quota1m)}`;
    }
    if (els.todayMeta) {
      els.todayMeta.textContent = `SQLite ${formatNumber(today.sqlite_raw_1m)} · ${chartBackend.engineShort} 差值 ${formatNumber(today.write_gap_1m)}`;
    }
    if (els.totalValue) {
      els.totalValue.textContent = formatNumber(totalChart1m);
    }
    if (els.totalMeta) {
      els.totalMeta.textContent = `1m ${formatNumber(totalChart1m)} · 5m ${formatNumber(totalChart5m)} · 15m ${formatNumber(totalChart15m)}`;
    }
  }

  function renderSnapshot(snapshot) {
    els.dock.dataset.state = "ready";
    renderHeader(snapshot);
    renderPools(snapshot);
    renderSummaries(snapshot);
    stage.updateSnapshot(snapshot || createEmptySnapshot(resolveActiveSymbols().rootSymbol));
  }

  function renderError(error) {
    const fallback = createEmptySnapshot(resolveActiveSymbols().rootSymbol);
    els.dock.dataset.state = "error";
    setPressureState("quiet");
    if (els.note) {
      const message = String(error?.message || error || "管线监控加载失败。");
      els.note.textContent = message;
      els.note.title = message;
    }
    if (els.pressure) {
      els.pressure.textContent = "0.00 raw/s";
    }
    if (els.contract) {
      els.contract.textContent = "合约 --";
    }
    if (els.root) {
      const activeRoot = resolveActiveSymbols().rootSymbol || "--";
      els.root.textContent = `Root ${activeRoot}`;
    }
    if (els.generatedAt) {
      els.generatedAt.textContent = "快照 --";
    }
    renderPools(fallback);
    renderSummaries(fallback);
    stage.updateSnapshot(fallback);
  }

  async function refresh() {
    if (requestInFlight) {
      refreshQueued = true;
      return;
    }
    requestInFlight = true;
    try {
      const snapshot = await fetchJson(`/api/v1/workbench/pipeline-monitor?${buildQuery()}`);
      renderSnapshot(snapshot);
    } catch (error) {
      console.error("回放页管线监控加载失败:", error);
      renderError(error);
    } finally {
      requestInFlight = false;
      if (refreshQueued) {
        refreshQueued = false;
        requestRefresh({ immediate: true });
      }
    }
  }

  function requestRefresh({ immediate = false } = {}) {
    if (scheduledRefreshTimer) {
      clearTimeout(scheduledRefreshTimer);
      scheduledRefreshTimer = null;
    }
    scheduledRefreshTimer = window.setTimeout(() => {
      scheduledRefreshTimer = null;
      void refresh();
    }, immediate ? 0 : 120);
  }

  function startPolling() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
    refreshTimer = window.setInterval(() => {
      requestRefresh({ immediate: true });
    }, pollIntervalMs);
  }

  function bindInteractions() {
    addTrackedListener(els.toggle, "click", () => {
      applyCollapsedState(!collapsed);
    });
    addTrackedListener(app?.els?.instrumentSymbol, "change", () => requestRefresh({ immediate: true }));
    addTrackedListener(app?.els?.instrumentSymbol, "blur", () => requestRefresh({ immediate: true }));
    addTrackedListener(app?.els?.buildButton, "click", () => requestRefresh({ immediate: false }));
    addTrackedListener(app?.els?.refreshAllButton, "click", () => requestRefresh({ immediate: true }));
    addTrackedListener(document, "visibilitychange", () => {
      stage.setDocumentVisible(!document.hidden);
      if (!document.hidden) {
        requestRefresh({ immediate: true });
      }
    });
  }

  function start() {
    bindInteractions();
    applyCollapsedState(collapsed);
    stage.setDocumentVisible(!document.hidden);
    requestRefresh({ immediate: true });
    startPolling();
  }

  function destroy() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    if (scheduledRefreshTimer) {
      clearTimeout(scheduledRefreshTimer);
      scheduledRefreshTimer = null;
    }
    while (trackedListeners.length) {
      const unbind = trackedListeners.pop();
      try {
        unbind?.();
      } catch (error) {
        console.warn("移除回放页管线监控监听失败:", error);
      }
    }
    stage.destroy();
  }

  return {
    start,
    refresh: () => requestRefresh({ immediate: true }),
    requestRefresh,
    destroy,
  };
}
