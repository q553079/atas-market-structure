const POLL_INTERVAL_MS = 5000;
const POOL_COLORS = {
  sqlite_raw: { fill: "#d07b31", foam: "#f0c27c", glow: "rgba(208,123,49,0.28)" },
  clickhouse_1m: { fill: "#2d8f85", foam: "#9dd8d2", glow: "rgba(45,143,133,0.28)" },
  clickhouse_5m: { fill: "#2375a6", foam: "#8ac2ef", glow: "rgba(35,117,166,0.26)" },
  clickhouse_15m: { fill: "#5a8f3d", foam: "#b4d88c", glow: "rgba(90,143,61,0.24)" },
};

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
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

class PoolTank {
  constructor(key, label, colors) {
    this.key = key;
    this.label = label;
    this.colors = colors;
    this.fillPercent = 0;
    this.targetFillPercent = 0;
    this.count = 0;
    this.capacity = 1;
    this.rect = { x: 0, y: 0, w: 100, h: 100 };
    this.particles = [];
    this.phase = Math.random() * Math.PI * 2;
  }

  setRect(rect) {
    this.rect = { ...rect };
    this.#reseedParticles(true);
  }

  sync(data) {
    this.targetFillPercent = Number(data?.fill_percent || 0);
    this.count = Number(data?.count || 0);
    this.capacity = Math.max(1, Number(data?.capacity || 1));
    this.label = data?.label || this.label;
  }

  update(dt) {
    const blend = Math.min(1, dt * 2.2);
    this.fillPercent += (this.targetFillPercent - this.fillPercent) * blend;
    this.phase += dt * 1.4;
    this.#reseedParticles(false);
    const waterTop = this.rect.y + this.rect.h * (1 - this.fillPercent / 100);
    const left = this.rect.x + 12;
    const right = this.rect.x + this.rect.w - 12;
    const bottom = this.rect.y + this.rect.h - 12;
    const top = waterTop + 8;

    for (const particle of this.particles) {
      particle.vy += 14 * dt;
      particle.vx += (Math.random() - 0.5) * 6 * dt;
      particle.x += particle.vx * dt;
      particle.y += particle.vy * dt;

      if (particle.x < left + particle.r) {
        particle.x = left + particle.r;
        particle.vx *= -0.75;
      } else if (particle.x > right - particle.r) {
        particle.x = right - particle.r;
        particle.vx *= -0.75;
      }

      if (particle.y > bottom - particle.r) {
        particle.y = bottom - particle.r;
        particle.vy *= -0.72;
      } else if (particle.y < top + particle.r) {
        particle.y = top + particle.r;
        particle.vy *= -0.4;
      }
    }

    for (let i = 0; i < this.particles.length; i += 1) {
      for (let j = i + 1; j < this.particles.length; j += 1) {
        const a = this.particles[i];
        const b = this.particles[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const distance = Math.hypot(dx, dy) || 0.001;
        const minDistance = a.r + b.r + 1;
        if (distance >= minDistance) continue;
        const overlap = (minDistance - distance) * 0.5;
        const nx = dx / distance;
        const ny = dy / distance;
        a.x -= nx * overlap;
        a.y -= ny * overlap;
        b.x += nx * overlap;
        b.y += ny * overlap;
        a.vx -= nx * overlap * 1.2;
        a.vy -= ny * overlap * 1.2;
        b.vx += nx * overlap * 1.2;
        b.vy += ny * overlap * 1.2;
      }
    }
  }

  draw(ctx) {
    const { x, y, w, h } = this.rect;
    const radius = 26;
    const waterTop = y + h * (1 - this.fillPercent / 100);
    const waveAmplitude = 6 + (this.fillPercent / 100) * 4;

    ctx.save();
    ctx.shadowColor = this.colors.glow;
    ctx.shadowBlur = 22;
    this.#roundedRect(ctx, x, y, w, h, radius);
    ctx.strokeStyle = "rgba(21, 35, 33, 0.18)";
    ctx.lineWidth = 2;
    ctx.stroke();

    this.#roundedRect(ctx, x, y, w, h, radius);
    ctx.clip();

    const fillGradient = ctx.createLinearGradient(x, y, x, y + h);
    fillGradient.addColorStop(0, this.colors.foam);
    fillGradient.addColorStop(0.24, `${this.colors.foam}cc`);
    fillGradient.addColorStop(1, this.colors.fill);
    ctx.fillStyle = fillGradient;
    ctx.beginPath();
    ctx.moveTo(x, y + h);
    ctx.lineTo(x, waterTop);
    for (let i = 0; i <= 20; i += 1) {
      const px = x + (w / 20) * i;
      const py = waterTop + Math.sin(this.phase + i * 0.45) * waveAmplitude;
      ctx.lineTo(px, py);
    }
    ctx.lineTo(x + w, y + h);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "rgba(255,255,255,0.14)";
    ctx.fillRect(x, y, w, h);

    for (const particle of this.particles) {
      const bubble = ctx.createRadialGradient(
        particle.x - particle.r * 0.4,
        particle.y - particle.r * 0.6,
        0,
        particle.x,
        particle.y,
        particle.r * 1.6,
      );
      bubble.addColorStop(0, "rgba(255,255,255,0.85)");
      bubble.addColorStop(0.28, this.colors.foam);
      bubble.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = bubble;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.r * 1.2, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();

    ctx.fillStyle = "#152321";
    ctx.font = "700 18px Bahnschrift, Trebuchet MS, sans-serif";
    ctx.fillText(this.label, x, y - 20);
    ctx.font = "600 13px Bahnschrift, Trebuchet MS, sans-serif";
    ctx.fillStyle = "rgba(21,35,33,0.72)";
    ctx.fillText(`${formatNumber(this.count)} / ${formatNumber(this.capacity)}`, x, y - 2);
  }

  outlet() {
    return {
      x: this.rect.x + this.rect.w,
      y: this.rect.y + this.rect.h * 0.48,
    };
  }

  inlet() {
    return {
      x: this.rect.x,
      y: this.rect.y + this.rect.h * 0.48,
    };
  }

  #reseedParticles(force) {
    const targetCount = Math.max(4, Math.round((this.fillPercent / 100) * 30));
    if (!force && this.particles.length === targetCount) {
      return;
    }
    while (this.particles.length > targetCount) {
      this.particles.pop();
    }
    while (this.particles.length < targetCount) {
      this.particles.push(this.#spawnParticle());
    }
  }

  #spawnParticle() {
    const waterTop = this.rect.y + this.rect.h * (1 - Math.max(this.fillPercent, 8) / 100);
    return {
      x: this.rect.x + 20 + Math.random() * Math.max(20, this.rect.w - 40),
      y: waterTop + 12 + Math.random() * Math.max(20, this.rect.h - (waterTop - this.rect.y) - 24),
      vx: (Math.random() - 0.5) * 10,
      vy: (Math.random() - 0.5) * 10,
      r: 3 + Math.random() * 5,
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
    this.pools = {
      sqlite_raw: new PoolTank("sqlite_raw", "SQLite 暂存池", POOL_COLORS.sqlite_raw),
      clickhouse_1m: new PoolTank("clickhouse_1m", "CK 1m", POOL_COLORS.clickhouse_1m),
      clickhouse_5m: new PoolTank("clickhouse_5m", "CK 5m", POOL_COLORS.clickhouse_5m),
      clickhouse_15m: new PoolTank("clickhouse_15m", "CK 15m", POOL_COLORS.clickhouse_15m),
    };
    this.droplets = [];
    this.lastFrame = performance.now();
    this.activity = "quiet";
    this._emissionCarry = 0;
    this.resize();
    window.addEventListener("resize", () => this.resize());
    requestAnimationFrame((ts) => this.loop(ts));
  }

  updateSnapshot(snapshot) {
    const pools = Array.isArray(snapshot?.recent_pools) ? snapshot.recent_pools : [];
    for (const item of pools) {
      const pool = this.pools[item.key];
      if (pool) {
        pool.sync(item);
      }
    }
    this.activity = snapshot?.write_pressure?.status || "quiet";
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.round(bounds.width * ratio));
    this.canvas.height = Math.max(1, Math.round(bounds.height * ratio));
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.layout(bounds.width, bounds.height);
  }

  layout(width, height) {
    const leftWidth = Math.max(180, width * 0.24);
    const sourceHeight = Math.max(220, height * 0.58);
    this.pools.sqlite_raw.setRect({
      x: 48,
      y: (height - sourceHeight) * 0.5,
      w: leftWidth,
      h: sourceHeight,
    });

    const rightX = width * 0.42;
    const targetWidth = Math.max(150, width * 0.18);
    const gap = 18;
    const targetHeight = Math.max(120, (height - 70 - gap * 2) / 3);
    this.pools.clickhouse_1m.setRect({ x: rightX, y: 52, w: targetWidth, h: targetHeight });
    this.pools.clickhouse_5m.setRect({ x: rightX + targetWidth + 48, y: 98, w: targetWidth, h: targetHeight });
    this.pools.clickhouse_15m.setRect({ x: rightX + targetWidth * 0.52, y: 52 + targetHeight + gap * 2, w: targetWidth, h: targetHeight });
  }

  loop(timestamp) {
    const dt = Math.min(0.035, (timestamp - this.lastFrame) / 1000);
    this.lastFrame = timestamp;
    this.update(dt);
    this.draw();
    requestAnimationFrame((ts) => this.loop(ts));
  }

  update(dt) {
    for (const pool of Object.values(this.pools)) {
      pool.update(dt);
    }
    this.#spawnDroplets(dt);
    this.droplets = this.droplets.filter((droplet) => droplet.progress < 1);
    for (const droplet of this.droplets) {
      droplet.progress += droplet.speed * dt;
      droplet.size *= 0.999;
    }
  }

  draw() {
    const ctx = this.ctx;
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);

    const bg = ctx.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, "rgba(255,255,255,0.72)");
    bg.addColorStop(1, "rgba(219,213,201,0.38)");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    this.#drawGrid(width, height);
    this.#drawPipes(ctx);
    for (const droplet of this.droplets) {
      this.#drawDroplet(ctx, droplet);
    }
    for (const pool of Object.values(this.pools)) {
      pool.draw(ctx);
    }
  }

  #drawGrid(width, height) {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = "rgba(21,35,33,0.05)";
    ctx.lineWidth = 1;
    for (let x = 24; x < width; x += 36) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 24; y < height; y += 36) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  #drawPipes(ctx) {
    const source = this.pools.sqlite_raw;
    const targets = [this.pools.clickhouse_1m, this.pools.clickhouse_5m, this.pools.clickhouse_15m];
    for (const target of targets) {
      const from = source.outlet();
      const to = target.inlet();
      const cp1x = from.x + (to.x - from.x) * 0.35;
      const cp1y = from.y;
      const cp2x = from.x + (to.x - from.x) * 0.72;
      const cp2y = to.y;

      ctx.save();
      ctx.strokeStyle = "rgba(21,35,33,0.14)";
      ctx.lineWidth = 12;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, to.x, to.y);
      ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,0.48)";
      ctx.lineWidth = 4;
      ctx.stroke();
      ctx.restore();
    }
  }

  #spawnDroplets(dt) {
    const source = this.pools.sqlite_raw;
    const targets = [this.pools.clickhouse_1m, this.pools.clickhouse_5m, this.pools.clickhouse_15m];
    const intensity = {
      quiet: 0.35,
      busy: 0.9,
      hot: 1.7,
    }[this.activity] || 0.4;
    const sourceFill = source.fillPercent / 100;
    if (sourceFill <= 0.04) {
      return;
    }

    const emissionRate = intensity * sourceFill * 10;
    this._emissionCarry += emissionRate * dt;
    while (this._emissionCarry >= 1) {
      this._emissionCarry -= 1;
      const target = targets[Math.floor(Math.random() * targets.length)];
      const from = source.outlet();
      const to = target.inlet();
      this.droplets.push({
        from,
        to,
        progress: 0,
        speed: 0.35 + Math.random() * 0.35,
        size: 5 + Math.random() * 5,
        color: target.colors.foam,
      });
    }
  }

  #drawDroplet(ctx, droplet) {
    const cp1x = droplet.from.x + (droplet.to.x - droplet.from.x) * 0.35;
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
    ctx.shadowBlur = 16;
    ctx.fillStyle = droplet.color;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(1.6, droplet.size), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

const els = {
  contractSelect: document.getElementById("contractSelect"),
  daysSelect: document.getElementById("daysSelect"),
  flowWindowSelect: document.getElementById("flowWindowSelect"),
  refreshButton: document.getElementById("refreshButton"),
  liveBadge: document.getElementById("liveBadge"),
  generatedAt: document.getElementById("generatedAt"),
  pressurePill: document.getElementById("pressurePill"),
  contractPill: document.getElementById("contractPill"),
  rootPill: document.getElementById("rootPill"),
  stageNote: document.getElementById("stageNote"),
  poolReadout: document.getElementById("poolReadout"),
  totalsCard: document.getElementById("totalsCard"),
  todayCard: document.getElementById("todayCard"),
  storageGrid: document.getElementById("storageGrid"),
  dailyList: document.getElementById("dailyList"),
};

const stage = new FlowStage(document.getElementById("flowCanvas"));

let currentContract = "";
let refreshTimer = null;
let requestInFlight = false;

function buildQuery() {
  const params = new URLSearchParams();
  const contract = String(els.contractSelect.value || "").trim();
  if (contract) {
    params.set("contract_symbol", contract);
  }
  params.set("days", String(els.daysSelect.value || "10"));
  params.set("flow_window_minutes", String(els.flowWindowSelect.value || "15"));
  return params.toString();
}

async function refreshSnapshot({ keepSelection = true } = {}) {
  if (requestInFlight) return;
  requestInFlight = true;
  els.refreshButton.disabled = true;
  try {
    const snapshot = await fetchJson(`/api/v1/workbench/pipeline-monitor?${buildQuery()}`);
    if (!keepSelection || !currentContract) {
      currentContract = snapshot?.selected_contract?.contract_symbol || "";
    }
    renderSnapshot(snapshot);
  } catch (error) {
    console.error("刷新 pipeline monitor 失败:", error);
    els.liveBadge.textContent = "加载失败";
    els.stageNote.textContent = String(error.message || error);
  } finally {
    requestInFlight = false;
    els.refreshButton.disabled = false;
  }
}

function renderSnapshot(snapshot) {
  populateContracts(snapshot.contracts || [], snapshot.selected_contract?.contract_symbol || currentContract);
  currentContract = snapshot?.selected_contract?.contract_symbol || "";
  stage.updateSnapshot(snapshot);
  renderHeader(snapshot);
  renderPools(snapshot.recent_pools || []);
  renderTotals(snapshot);
  renderStorage(snapshot.storage_locations || []);
  renderDaily(snapshot.daily_rows || []);
}

function populateContracts(contracts, selected) {
  const existing = Array.from(els.contractSelect.options).map((item) => item.value);
  const nextValues = contracts.map((item) => item.contract_symbol);
  const changed = existing.join("|") !== nextValues.join("|");
  if (changed) {
    els.contractSelect.innerHTML = contracts
      .map((item) => {
        const latest = item.latest_raw_updated_at ? ` · ${formatTime(item.latest_raw_updated_at)}` : "";
        return `<option value="${escapeHtml(item.contract_symbol)}">${escapeHtml(item.contract_symbol)} / ${escapeHtml(item.root_symbol)}${latest}</option>`;
      })
      .join("");
  }
  if (selected) {
    els.contractSelect.value = selected;
  }
}

function renderHeader(snapshot) {
  els.generatedAt.textContent = formatTime(snapshot.generated_at);
  const pressure = snapshot.write_pressure || {};
  const selected = snapshot.selected_contract || {};
  els.liveBadge.textContent = {
    quiet: "流量安静",
    busy: "持续注水",
    hot: "高压写入",
  }[pressure.status] || "等待数据";
  els.pressurePill.textContent = `写入强度：${pressure.status || "--"} / ${pressure.raw_writes_per_minute ?? "--"} raw/min`;
  els.contractPill.textContent = `合约：${selected.contract_symbol || "--"}`;
  els.rootPill.textContent = `Root：${selected.root_symbol || "--"}`;
  els.stageNote.textContent = selected.shared_chart_pool
    ? `当前合约 ${selected.contract_symbol || "--"} 的原始 bars 会流入 root ${selected.root_symbol || "--"} 的共享 CK K 线池。`
    : "当前选择的数据池按同一符号闭环流转。";
}

function renderPools(pools) {
  if (!pools.length) {
    els.poolReadout.innerHTML = `<div class="empty-state">当前还没有可展示的流量池。</div>`;
    return;
  }
  els.poolReadout.innerHTML = pools
    .map((pool) => `
      <article class="pool-chip">
        <div class="pool-chip-head">
          <span>${escapeHtml(pool.label)}</span>
          <strong>${formatPercent(pool.fill_percent)}</strong>
        </div>
        <small>${formatNumber(pool.count)} / ${formatNumber(pool.capacity)}（最近 ${escapeHtml(pool.timeframe)} 写入）</small>
        <div class="pool-bar"><span style="width:${Math.max(0, Math.min(100, Number(pool.fill_percent || 0)))}%"></span></div>
      </article>
    `)
    .join("");
}

function renderTotals(snapshot) {
  const totals = snapshot.totals || {};
  const pressure = snapshot.write_pressure || {};
  els.totalsCard.innerHTML = `
    <div class="metric-title">从开始到现在</div>
    <h2>累计库存</h2>
    <p class="metric-copy">看总量，确认哪些数据已经真正落到 SQLite 和 ClickHouse。</p>
    <div class="metric-grid">
      <div class="metric-item"><strong>${formatNumber(totals.sqlite_raw_1m)}</strong><span>SQLite 原始 1m</span></div>
      <div class="metric-item"><strong>${formatNumber(totals.clickhouse_1m)}</strong><span>CK 1m</span></div>
      <div class="metric-item"><strong>${formatNumber(totals.clickhouse_5m)}</strong><span>CK 5m</span></div>
      <div class="metric-item"><strong>${formatNumber(totals.clickhouse_15m)}</strong><span>CK 15m</span></div>
    </div>
    <div class="fill-meter"><span style="width:${pressure.status === "hot" ? 100 : pressure.status === "busy" ? 66 : 32}%"></span></div>
  `;

  const today = snapshot.today || {};
  els.todayCard.innerHTML = `
    <div class="metric-title">今天 / 选中窗口</div>
    <h2>${escapeHtml(today.bar_date || "--")}</h2>
    <p class="metric-copy">以 1m 一天 1440 根为总量基准，直接看当天入库和聚合完成度。</p>
    <div class="metric-grid">
      <div class="metric-item"><strong>${formatNumber(today.sqlite_raw_1m)}</strong><span>SQLite 原始 1m</span></div>
      <div class="metric-item"><strong>${formatNumber(today.clickhouse_1m)}</strong><span>CK 1m</span></div>
      <div class="metric-item"><strong>${formatNumber(today.clickhouse_5m)}</strong><span>CK 5m</span></div>
      <div class="metric-item"><strong>${formatNumber(today.clickhouse_15m)}</strong><span>CK 15m</span></div>
    </div>
    <div class="fill-meter"><span style="width:${Math.max(0, Math.min(100, Number(today.raw_fill_percent || 0)))}%"></span></div>
  `;
}

function renderStorage(items) {
  if (!items.length) {
    els.storageGrid.innerHTML = `<div class="empty-state">暂时没有可展示的存储位置。</div>`;
    return;
  }
  els.storageGrid.innerHTML = items
    .map((item) => `
      <article class="storage-item">
        <div class="storage-engine">${escapeHtml(item.engine)}</div>
        <h3>${escapeHtml(item.label)}</h3>
        <p class="storage-meta">${escapeHtml(item.purpose)}</p>
        <div class="storage-location">${escapeHtml(item.location)}</div>
      </article>
    `)
    .join("");
}

function renderDaily(rows) {
  if (!rows.length) {
    els.dailyList.innerHTML = `<div class="empty-state">当前没有按日期可展示的 1m 入库记录。</div>`;
    return;
  }
  els.dailyList.innerHTML = rows
    .map((row) => {
      const chart1Fill = row.chart_fill_percent?.["1m"] ?? 0;
      const gap = Number(row.write_gap_1m || 0);
      return `
        <article class="daily-row">
          <div class="daily-top">
            <div>
              <h3>${escapeHtml(row.bar_date)}</h3>
              <div class="daily-meta">最近更新时间：${escapeHtml(formatTime(row.latest_updated_at))}</div>
            </div>
            <div class="daily-meta">1m 差值：${formatNumber(gap)} 根</div>
          </div>
          <div class="daily-metrics">
            <div class="daily-metric">
              <strong>${formatNumber(row.sqlite_raw_1m)}</strong>
              <span>SQLite 原始 1m / ${formatPercent(row.raw_fill_percent)}</span>
            </div>
            <div class="daily-metric">
              <strong>${formatNumber(row.clickhouse_1m)}</strong>
              <span>CK 1m / ${formatPercent(chart1Fill)}</span>
            </div>
            <div class="daily-metric">
              <strong>${formatNumber(row.clickhouse_5m)}</strong>
              <span>CK 5m / ${formatPercent(row.chart_fill_percent?.["5m"] ?? 0)}</span>
            </div>
            <div class="daily-metric">
              <strong>${formatNumber(row.clickhouse_15m)}</strong>
              <span>CK 15m / ${formatPercent(row.chart_fill_percent?.["15m"] ?? 0)}</span>
            </div>
          </div>
          <div class="daily-fill-track"><span style="width:${Math.max(0, Math.min(100, Number(row.raw_fill_percent || 0)))}%"></span></div>
        </article>
      `;
    })
    .join("");
}

function schedulePolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
  }
  refreshTimer = window.setInterval(() => {
    void refreshSnapshot({ keepSelection: true });
  }, POLL_INTERVAL_MS);
}

els.refreshButton.addEventListener("click", () => {
  void refreshSnapshot({ keepSelection: true });
});

els.contractSelect.addEventListener("change", () => {
  currentContract = String(els.contractSelect.value || "");
  void refreshSnapshot({ keepSelection: true });
});

els.daysSelect.addEventListener("change", () => {
  void refreshSnapshot({ keepSelection: true });
});

els.flowWindowSelect.addEventListener("change", () => {
  void refreshSnapshot({ keepSelection: true });
});

void refreshSnapshot({ keepSelection: false });
schedulePolling();
