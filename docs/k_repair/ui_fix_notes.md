# ATAS replay workbench UI 修复建议

这份补丁主要解决 4 个问题：

1. **切换品种 / 周期后，沿用上一次图表视口，导致 K 线刚出来时过度压缩**
2. **不同品种的图表不能自动回到合理可视范围，需要手动拖拽 / 缩放**
3. **首屏加载体感偏慢**（主要是图表先被旧视口污染，用户会误以为“加载慢”）
4. **进度条跳变太硬**

## 根因

- `applySnapshotToState()` 在切换 symbol/timeframe 时会把 `state.chartView` 置空，但 Lightweight Charts 的可视逻辑区间仍然保留在旧图上。
- `renderChart()` 又会优先把当前 chart 的 `logicalRange` 反写回 `state.chartView`，所以新数据刚加载时，还是拿到了旧图的缩放状态。
- 进度条是离散百分比直接写 `width`，没有缓动，也没有等待态的视觉反馈。

## 本次补丁做了什么

### 1) 在快照切换时显式打标记
文件：`replay_workbench_replay_loader.js`

- 新增：
  - `state.chartViewportResetPending`
  - `state.chartAutoScalePending`

用途：只要不是“同品种同周期保留视图”的情况，就要求图表在下一次渲染时重新同步视口和价格轴。

### 2) 阻止旧视口污染新数据
文件：`replay_workbench.html`

- 在 `renderChart()` 里：
  - 只有当 `chartViewportResetPending === false` 时，才允许从 Lightweight Charts 当前 `logicalRange` 反写回 `state.chartView`
- 新增 `syncLightweightChartViewportToState()`：
  - 用 `state.chartView.startIndex/endIndex` 强制回写到图表
  - 同时触发右侧价格轴 autoscale
  - 再做一次 `requestAnimationFrame` 后的二次同步，避免初次布局尚未稳定时失效

### 3) 让进度条有缓动，不再“生硬跳点”
文件：`replay_workbench_bootstrap.js` + `replay_workbench.css`

- JS：
  - 增加 `animateBuildProgress()`
  - 用 `requestAnimationFrame` 把目标百分比平滑逼近
- CSS：
  - 给 `.build-progress-fill` 增加 `transition`
  - 添加 shimmer 扫光动画
  - 完成态停止扫光

## 推荐再做的下一步（可选）

### A. 进一步提升“首图出来”的速度感
当前 `renderChart()` 会先构建 `eventModel`，再更新图表。建议改成两段式：

1. 第一帧先 `updateChartData(..., markers: [])`
2. 下一帧再 `buildChartEventModel()`、补 marker 和右侧事件流

这样用户会更快看到 K 线主体。

### B. 默认可视 bar 数按周期动态设置
当前 `createDefaultChartView()` 固定大致 180 根。可以改成：

- 1m: 120~180
- 5m: 100~140
- 15m: 80~120
- 1h: 60~100
- 4h / 1d: 40~80

这样切换到高周期时，默认观感会更自然。

## 文件

- 可直接交给 Codex 的 patch：`ui_fix.patch`
