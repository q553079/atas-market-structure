# Replay Workbench K线实时联动与7天补数完整性设计方案

## 1. 文档目的

本文档用于明确 Replay Workbench 当前 K 线数据链路的问题、目标状态、总体架构、实时传输方案、补数方案、前端无感更新方案，以及后续具体落地步骤。

目标不是做“能看”的版本，而是做一套 **强联动、强补偿、强一致、前端无感更新** 的 K 线数据链路。

---

## 2. 设计目标

### 2.1 核心目标

必须满足以下硬性要求：

1. **最近至少 7 天的当前周期 K 线不能漏数据**。
2. **缺多少补多少**，不能只补尾巴，不能只补当前可视区域。
3. **ATAS C# 采集脚本与 Python 后端保持强联动**，不能依赖人工刷新修复数据缺口。
4. **实时数据必须持续流入**，不能频繁出现“短一截”“卡一段”“不刷新”的现象。
5. **补回的数据必须先进入后端统一数据面，再无感更新到前端图表**。
6. **K线图必须保留上次打开时的样子**，不能因为关闭页面、重开页面、或新开一个界面就丢失图表状态。
7. **图表状态与数据都要实时缓存**，至少要能恢复：
   - 当前品种
   - 当前周期
   - 当前 candles 数据快照
   - 当前 viewport / 缩放 / 可视范围
   - 当前叠加层、标注、用户操作状态
8. **前端更新必须无感**：
   - 不整页刷新
   - 不强制回到最新位置
   - 不重置缩放
   - 不破坏用户当前查看区域
9. **K线首屏加载必须优先保证速度**，后端首次返回不要给过多 K 线，应按周期只返回一个较小的首屏窗口，先让图表秒开，再后台继续补齐更多历史数据。
10. **历史完整性、缓存状态与实时性都要可观测**，系统要知道自己是否缺数、补数是否成功、实时是否掉线、缓存是否新鲜。

### 2.2 业务表达

用一句话定义目标状态：

> 对于当前选中品种 + 周期，系统必须尽最大努力保证最近 7 天数据完整；如果发现任何时间段缺失，后台立即发起补数；补回后前端按时间轴无感并入，不要求人工刷新；同时图表在关闭后再次打开或新开页面时，应尽量恢复到上一次使用时的状态；并且首屏加载必须优先快开，例如 1 分钟周期先只给最近 3 小时，再后台继续补齐更长历史。

---

## 3. 当前现状总结

### 3.1 已有能力

当前系统已经具备以下基础能力：

#### 后端侧
- 支持 ingest `adapter_continuous_state`
- 支持 ingest `adapter_history_bars`
- 支持 ingest `adapter_history_footprint`
- 支持 replay snapshot build
- 支持 `live-tail` 查询
- 支持 gap 检测与 synthetic filler bar 补平时间轴
- 支持 backfill request / poll / ack 控制面接口

#### C# / ATAS 侧
- 支持 continuous-state 向后端上报
- 支持 backfill command poll
- 支持 backfill ack
- 已有 chart_instance_id 概念，可用于图表实例定向联动

#### 前端侧
- 能加载历史快照并渲染 K 线
- 能定时拉 `live-tail`
- 能对尾部最后一根 K 线做替换或追加新 bar
- 有基础 chart state / chartView / renderChart 流程

### 3.2 当前主要问题

虽然主链路已打通，但距离“生产级强联动方案”还有明显差距。

#### 问题 1：实时方案本质上还是轮询，不是强实时流
当前前端主要依赖：
- 每 5 秒轮询 `/api/v1/workbench/live-tail`

问题：
- 延迟不可控
- 容易在边界时间点漏掉细粒度变化
- 一旦某个轮询周期失败，恢复不够强
- 不能体现真正“持续实时传输”

#### 问题 2：ATAS ↔ 后端联动还不够硬
当前虽然存在：
- `/api/v1/adapter/backfill-command`
- `/api/v1/adapter/backfill-ack`
- `/api/v1/workbench/atas-backfill-requests`

但还没有完全体现为：
- 缺口一出现立即自动发起 backfill request
- C# 稳定 poll 并立即执行
- ack 后自动刷新 snapshot/live cache
- 前端自动收到合并结果

#### 问题 3：7 天完整性没有被定义成硬约束
当前代码里虽然有：
- gap 检测
- 局部 patch
- synthetic filler

但还没有一套明确机制去保证：
- 当前周期最近 7 天理论应有多少 bar
- 实际少多少
- 缺口在哪些段
- 哪些段已经补
- 哪些段仍待补

#### 问题 4：前端“无感更新”还不够完整
当前前端更偏：
- 修改 `state.snapshot.candles`
- 调 `renderChart()`
- lightweight chart 多数场景走全量 `setData()` 思路

这对于：
- 尾部 bar 更新

还勉强可用，但对于：
- 中间缺失段补回
- synthetic filler 被真实 bar 替换
- 保持 viewport 稳定

还不够精细。

#### 问题 5：图表状态持久化与缓存恢复没有被纳入主设计
目前还没有把以下能力做成明确目标：
- 页面关闭后恢复到上次图表状态
- 新开页面先秒开最近快照
- 实时数据与补数结果持续写缓存
- 本地缓存与后端缓存协同恢复

#### 问题 6：首屏K线加载过重，影响打开速度
当前如果一次返回过大的 candles 数据量，会导致：
- 后端构建慢
- 网络传输慢
- 前端 `setData()` 慢
- 页面打开和切换周期时明显卡顿

这不符合“先开出来再补齐”的体验要求。

---

## 4. 目标架构

目标架构应改造成如下闭环：

```text
ATAS 图表 / ATAS 指标
    ↓
C# Collector（continuous-state / history-bars / history-footprint）
    ↓
Python API + ReplayWorkbenchService
    ↓
首屏窗口裁剪（按周期快速返回最小可用窗口）
    ↓
数据完整性扫描（7天窗口）
    ↓
缺口检测（gap segments）
    ↓
自动发起 ATAS backfill request
    ↓
C# poll command → 执行回补 → ack
    ↓
后端重建/更新 snapshot + live tail cache + workspace cache
    ↓
前端按 started_at 无感 merge
    ↓
图表最小代价刷新 + 本地缓存同步更新 + 后台扩窗
```

这条链必须满足：
- 自动
- 可追踪
- 可重试
- 可恢复
- 不依赖人工刷新

---

## 5. 数据一致性原则

### 5.1 时间轴优先
图表数据必须以 `started_at` 作为主排序与合并键。

原则：
1. 同一 `started_at` 只允许最终存在一根 bar。
2. 如果同一 `started_at` 同时存在：
   - synthetic filler
   - live tail bar
   - history bar
   最终优先级必须明确。

建议优先级：

```text
真实 history bar > 真实 live bar > synthetic filler
```

### 5.2 后端是真实数据统一源
前端不能自己“发明真实数据”，只能：
- 临时展示 synthetic filler 防止时间压缩
- 等待后端真实 bars 回补并替换

也就是说：
- **真实数据唯一来源是后端统一数据面**
- 前端只做显示层 merge，不做事实层推断

### 5.3 实时与历史必须能融合
历史 bars 与 continuous-state 聚合出来的 live bars 最终都要落在同一个按时间排序的 bar 序列中。

### 5.4 缓存不是事实源
缓存只承担：
- 秒开恢复
- 页面重开恢复
- 新页面快速显示
- 减少冷启动等待

但缓存不能覆盖真实数据源地位：
- 后端统一数据面仍是唯一事实源
- 本地缓存永远服从后端更高版本数据

### 5.5 首屏窗口不等于完整性窗口
必须明确区分两个概念：
- **首屏展示窗口**：为了快开，故意先小
- **后台完整性窗口**：为了正确性，仍需继续覆盖最近 7 天

也就是说：
- 首屏少返回是性能策略
- 后台继续补齐是正确性策略

---

## 6. 7天完整性方案

### 6.1 为什么必须把“7天完整”做成硬约束
如果没有完整性硬约束，系统就会退化成：
- 能显示多少算多少
- 缺了先凑合
- 等用户自己发现问题再手动刷新

这不符合交易/复盘场景要求。

所以必须定义：

> 当前选中周期下，最近 7 天窗口内，系统必须持续评估数据完整性。

### 6.2 各周期理论 bar 数
最近 7 天理论 bar 数应按周期计算，而不是统一写死 `7 * 24 * 60`。

例如：

| 周期 | 7天理论bar数 |
|---|---:|
| 1m | 10080 |
| 5m | 2016 |
| 15m | 672 |
| 30m | 336 |
| 1h | 168 |
| 1d | 7 |

公式：

```text
expectedBars = ceil(7天总分钟数 / timeframe分钟数)
```

### 6.3 完整性扫描输出
每次 build / live refresh / ack 后都要生成完整性扫描结果：

```json
{
  "window_days": 7,
  "timeframe": "1m",
  "expected_bar_count": 10080,
  "actual_bar_count": 10012,
  "missing_bar_count": 68,
  "gap_segments": [
    {
      "start": "2026-03-18T10:21:00Z",
      "end": "2026-03-18T10:27:59Z",
      "missing_bar_count": 7
    }
  ],
  "status": "needs_backfill"
}
```

### 6.4 缺口定义
gap segment 应按连续缺失区间聚合，而不是一个 bar 一个 request。

好处：
- 减少 backfill command 数量
- 更方便 C# 批量补数
- 更方便追踪状态

---

## 7. ATAS 强联动方案

### 7.1 目标
ATAS C# 采集器必须承担两类责任：

1. **实时上报 continuous-state**
2. **执行后端派发的历史回补命令**

### 7.2 当前问题
当前 C# 侧更像：
- 有一个 continuous-state 上报线程
- 有一个 backfill poll 逻辑
- 有时会短、更、卡、不稳定

说明它还不是一个强约束的可靠采集器。

### 7.3 强联动要求
C# 侧必须做到：

#### 1）continuous-state 稳定发送
- 固定节奏发送
- 单次失败自动重试
- 连续失败进入 degraded 状态
- 恢复后立即恢复发送

#### 2）带稳定标识
每条消息必须带：
- `instrument_symbol`
- `chart_instance_id`
- `observed_window_start`
- `observed_window_end`
- `emitted_at`
- 建议新增 `sequence_id` 或 `stream_seq`

这样后端才能识别：
- 掉包
- 乱序
- 长时间停更

#### 3）稳定 poll backfill command
只要图表实例还活着：
- 持续 poll `/api/v1/adapter/backfill-command`
- poll 频率要比当前更积极
- 不能依赖人工操作触发

#### 4）执行 backfill 后可靠 ack
ack 只能在以下条件都成立后发送：
- history bars 已成功拉到
- history bars 已成功发到 Python 后端
- 如要求 footprint，同样已成功完成

不能“先 ack，后慢慢补”。

---

## 8. 后端自动补数方案

### 8.1 总体原则
后端必须成为“缺口发现者 + 补数调度者 + 合并协调者”。

后端不应该只是“被动接收数据”，而应该主动负责：
- 检查是否缺数据
- 生成补数计划
- 跟踪补数进度
- 收到 ack 后重算完整性

### 8.2 自动触发时机
以下场景都应触发完整性扫描：

1. `build_replay_snapshot()` 完成后
2. `get_live_tail()` 返回前
3. 收到 `adapter_history_bars` 后
4. 收到 `adapter_history_footprint` 后
5. 收到 `backfill_ack` 后
6. 定时后台巡检任务

### 8.3 自动 backfill 触发规则
如果完整性扫描结果：
- `missing_bar_count > 0`
- 且 gap 落在最近 7 天窗口内

则立即：
- 生成 `ReplayWorkbenchAtasBackfillRequest`
- 写入 `missing_segments`
- 标记原因，例如：
  - `seven_day_integrity_gap`
  - `live_tail_gap`
  - `history_snapshot_gap`

### 8.4 回补粒度
建议按 gap segment 回补，不按单根 bar 回补。

一个 segment 至少包含：
- `prev_ended_at`
- `next_started_at`
- `missing_bar_count`
- `timeframe`

### 8.5 回补后的处理
收到 ack 后后端必须：

1. 重新拉取对应 symbol/timeframe 的最新 history bars
2. 重算 7 天完整性
3. 如果仍缺失，继续发下一轮 backfill
4. 如果已完整，更新状态为 `complete`
5. 更新前端可拉取的数据版本号
6. 同步刷新工作台缓存版本

---

## 9. 实时方案设计

本节是你特别要求补充的“实时方案”。

### 9.1 实时方案目标

实时方案目标不是“看上去差不多”，而是：

1. 新价格持续进入系统
2. 最新 bar 能低延迟更新
3. 出现网络抖动或短断后自动恢复
4. 不因为实时刷新破坏 7 天完整性
5. 实时与补数机制统一协同
6. 实时更新过程中持续同步缓存

### 9.2 实时方案分层
建议分为两层：

#### 第一层：采集实时层
由 C# 持续发送 `continuous-state`。

作用：
- 提供最新 price / bid / ask / trade summary
- 聚合出最新进行中的 bar
- 用于 live-tail 显示

#### 第二层：历史修正层
由 backfill + history-bars 负责修正：
- continuous-state 聚合误差
- 网络抖动造成的遗漏
- 长时间缺段

也就是说：

> continuous-state 负责“快”，history bars 负责“准”。

### 9.3 推荐实时传输方案
#### 方案 A：短期可落地方案
继续保留现有 HTTP 架构，但升级为：

- C# 高频 POST `continuous-state`
- 前端较快频率轮询 `live-tail`
- 后端自动扫描 gap 并调度 backfill
- live-tail 返回版本号 / 数据签名
- 前端按增量方式 merge
- merge 后立即更新本地缓存与工作台缓存

适合短期快速落地。

#### 方案 B：中期推荐方案
增加 **SSE（Server-Sent Events）**。

后端提供：
- `/api/v1/workbench/live-stream?instrument_symbol=...&timeframe=...`

推送事件类型：
- `tail_bar_update`
- `tail_bar_append`
- `history_backfill_merged`
- `integrity_status_changed`
- `stream_state_changed`
- `workspace_cache_refreshed`

优点：
- 比轮询更实时
- 前端更新延迟更低
- 后端能主动通知“补回的数据已可合并”
- 后端能主动通知缓存版本已更新

#### 方案 C：长期方案
使用 WebSocket 双向通道。

适合场景：
- 更复杂实时状态同步
- 客户端主动订阅/取消订阅
- 多图表实例统一管理

### 9.4 实时状态模型
系统中应统一维护：

```json
{
  "stream_state": "live",
  "latest_adapter_sync_at": "2026-03-20T15:30:12Z",
  "latest_live_tail_at": "2026-03-20T15:30:13Z",
  "latest_history_sync_at": "2026-03-20T15:29:58Z",
  "seven_day_integrity_status": "backfilling",
  "pending_backfill_segments": 2,
  "workspace_cache_status": "fresh"
}
```

前端状态展示应区分：
- `live`
- `delayed`
- `stale`
- `offline`
- `backfilling`
- `cache_restored`

---

## 10. 首屏快速加载方案

### 10.1 目标
K线加载必须遵循“先快开、再补齐”的原则。

目标如下：

1. 页面或图表首次打开时，优先在最短时间内把图渲染出来。
2. 后端首次返回不要给过多 K 线，避免构建、传输、渲染同时过重。
3. 首屏只返回一个适合当前周期的最小可用窗口，先满足观察与操作。
4. 更长历史、7天完整性、补数结果应在后台逐步补齐。
5. 首屏快速加载不能破坏后续实时更新、补数合并和缓存恢复。

### 10.2 首屏窗口建议
建议后端针对不同周期设置默认首屏窗口，而不是首次直接返回 7 天全量。

推荐初始窗口如下：

| 周期 | 首屏建议窗口 |
|---|---|
| 1m | 3小时 |
| 5m | 12小时 |
| 15m | 1天 |
| 30m | 2天 |
| 1h | 3天 |
| 4h | 7天 |
| 1d | 30天 |

其中必须明确落地：

- **1分钟K线首屏先只渲染3个小时**。
- 其他周期按同样思路，优先返回足够看、但不重的首屏窗口。

### 10.3 加载策略
建议将 K 线加载拆成三层：

#### 第一层：首屏快速窗口
- 只返回当前周期的首屏窗口
- 目标是秒开图表
- 例如 1m 先给最近 3 小时

#### 第二层：后台扩窗
- 首屏渲染成功后，再后台补拉更长窗口
- 可逐步扩展到最近 1 天、3 天、7 天
- 扩窗过程不应阻塞首屏展示

#### 第三层：完整性与补数
- 扩窗过程中继续执行 7 天完整性扫描
- 有缺口则继续 backfill
- 前端无感合并新增历史与补回 bars

### 10.4 与缓存策略的关系
如果本地缓存或工作台缓存中已有最近一次图表状态：
- 优先使用缓存秒开
- 然后再向后端请求首屏窗口与最新 live 数据
- 再继续后台扩窗和补数

也就是说：

> 最佳路径应是“缓存秒开 > 首屏窗口校准 > 后台扩窗 > 补数补齐”。

### 10.5 与实时/补数链路的关系
首屏少返回，不代表后端可以少管完整性。

必须区分两个概念：
- **首屏展示窗口**：为了速度，故意先小
- **后台完整性窗口**：为了正确性，仍要继续做到最近7天完整

也就是说：
- 前端首次只看见较小窗口是正常的
- 但后端后台仍应继续推进最近7天补齐与缓存更新

### 10.6 设计要求总结
首屏快速加载方案必须满足：

1. 首次打开图表优先快。
2. 1m 周期默认先给 3 小时。
3. 其他周期按比例给较小首屏窗口。
4. 首屏渲染后再后台扩窗。
5. 扩窗与补数都必须无感并入。
6. 不因为追求完整性而牺牲首屏速度。

---

## 11. 图表状态持久化与实时缓存方案

### 11.1 目标
除了实时更新与补数完整性，还必须保证：

1. 用户关闭页面后再次打开，K线图尽量恢复到上次状态。
2. 用户新开一个界面时，能够快速拿到最近一次缓存的图表数据与视口状态。
3. 实时流入的数据与补回的数据要持续写入缓存，而不是只存在于内存中。
4. 缓存恢复不能破坏后续实时更新与补数合并。

### 11.2 需要缓存的内容
建议至少缓存以下对象：

#### 1）图表数据缓存
- instrument_symbol
- timeframe
- candles
- last_real_bar_started_at
- snapshot_version
- tail_version
- integrity_status
- pending_backfill_segments
- latest_adapter_sync_at
- latest_history_sync_at

#### 2）图表视图缓存
- 当前 visible logical range
- 当前 visible time range
- 当前 price scale 范围（如可恢复）
- 是否处于“跟随最新”模式
- 当前缩放级别

#### 3）图表交互缓存
- 当前选中品种
- 当前选中周期
- overlays 显隐状态
- 标注/手工区域状态
- 当前 workspace / session 上下文

### 11.3 缓存分层
建议做两层缓存：

#### 第一层：前端本地缓存
用于页面关闭后再次打开时快速恢复。

推荐：
- `localStorage` 存轻量状态
- `IndexedDB` 存较大的 candles 数据与图表快照

#### 第二层：后端工作台缓存
用于：
- 新开页面时快速恢复
- 多页面之间共享最近状态
- 前端本地缓存失效时兜底恢复

也就是说：

> 前端缓存负责“秒开恢复”，后端缓存负责“跨页面/跨会话兜底恢复”。

### 11.4 缓存写入时机
以下场景都应触发缓存更新：

1. 历史 snapshot build 成功后
2. live-tail 收到尾部增量后
3. backfill 合并成功后
4. synthetic filler 被真实 bars 替换后
5. 用户切换品种 / 周期后
6. 用户移动 viewport / 缩放后
7. 用户新增标注 / overlay 操作后
8. 页面关闭前 `beforeunload` 阶段

### 11.5 恢复策略
页面重新打开时，推荐恢复顺序：

1. 先恢复前端本地缓存中的最近图表状态
2. 立即渲染缓存 candles + 视口状态，保证用户看到“上次打开的样子”
3. 并行请求后端最新 snapshot / live-tail / integrity 状态
4. 将后端最新数据与本地缓存按 `started_at` merge
5. 若缓存已过旧，则以后端数据为准，但尽量保留视口与交互状态

### 11.6 新开一个页面的行为要求
如果用户新开一个界面：
- 不能从空白图开始
- 应优先读取后端工作台缓存或最近本地缓存
- 先展示最近一次可用快照
- 再无感追平到最新 live + backfill 状态

也就是说：

> “新开页面” 应该是“先秒开最近状态，再静默追最新”，而不是“重新从零构建”。

### 11.7 缓存一致性原则
缓存不是事实源，只是恢复与提速层。

必须遵守：
- 后端统一数据面仍是真实源
- 本地缓存仅用于快速恢复
- 一旦后端返回更高版本 `snapshot_version` / `tail_version`，前端缓存必须被覆盖更新
- 真实 history bars 到达后，必须替换缓存中的 filler 或旧 live 聚合 bar

### 11.8 设计要求总结
图表缓存方案最终必须满足：

1. 关闭再打开，尽量恢复上次图表样子。
2. 新开一个界面，也能快速拿到最近状态。
3. 实时更新过程中持续写缓存。
4. 补数完成后缓存同步更新。
5. 缓存恢复后继续无缝接上实时流与补数流。

---

## 12. 前端无感更新方案

### 12.1 前端目标
前端必须做到两类无感更新：

1. **尾部实时无感更新**
2. **中间缺段补回无感插补**

### 12.2 合并规则
前端每次收到新的实时尾部或补数结果时，应按 `started_at` merge：

#### 同 started_at 时
优先级：

```text
真实 history > 真实 live > synthetic filler
```

#### 新 started_at 时
直接插入正确时间位置。

#### synthetic filler 替换规则
如果某位置已有 synthetic filler，而后端返回真实 bar：
- 用真实 bar 替换 filler
- 不改变整段时间轴长度
- 不闪烁提示

### 12.3 视口策略
前端必须区分两种模式：

#### 模式 A：跟随最新
用户当前在最右端附近时：
- append 新 bar 后自动轻微右移
- 保持“盯盘”体验

#### 模式 B：查看历史
用户主动拖离最右端时：
- 补回数据只 merge，不强行跳转到最新
- 缩放与位置保持不变

### 12.4 渲染策略
#### 尾部更新
- 用增量 update
- 避免全量 `setData()`

#### 中段插补
- 允许局部重算后 `setData()`
- 但要保留 chart view
- 不重置 fitContent

### 12.5 前端不应做的事
前端不应该：
- 每次 live-tail 返回都全量刷新整个工作台
- 每次补数后整页重载
- 每次数据变化都 reset chart viewport

---

## 13. synthetic filler 的角色定位

### 13.1 filler 的作用
synthetic filler 只应承担：
- 让时间轴连续
- 防止 UI 把缺失时间压缩掉
- 明示“这里目前还没真实数据”

### 13.2 filler 不是最终数据
必须明确：
- filler 只是临时显示对象
- 不是事实数据
- 最终必须被真实 history bar 替换

### 13.3 filler 的生命周期
1. 检测到 gap
2. 立即插入 filler 保持图表连续
3. 立即后台请求真实 backfill
4. 回补成功后，用真实 bar 替换 filler
5. 更新完整性状态

---

## 14. 推荐的数据流闭环

### 14.1 历史加载阶段
```text
前端 build snapshot
→ 后端 build_replay_snapshot
→ 先返回首屏窗口数据
→ 扫描最近7天完整性
→ 如缺失则返回 snapshot + gap metadata
→ 同时自动创建 backfill request
→ 前端先显示当前可得数据 + filler
→ 同步写入本地缓存/工作台缓存
→ 后台扩窗继续拉更长历史
→ C# 执行补数
→ ack
→ 后端重建/合并
→ 后端刷新工作台缓存
→ 前端无感替换 filler 并更新本地缓存
```

### 14.2 实时阶段
```text
C# continuous-state 持续发送
→ 后端更新 live tail
→ 前端接收尾部更新
→ 若 live tail 检出时间缺口
→ 后端自动 backfill request
→ C# 拉 history bars / footprint
→ ack
→ 后端将真实bars并入
→ 后端刷新缓存版本
→ 前端无感插补缺段并同步缓存
```

---

## 15. 需要新增或强化的状态字段

建议在后端和前端都引入统一的数据状态对象：

```json
{
  "instrument_symbol": "NQ",
  "timeframe": "1m",
  "integrity_window_days": 7,
  "expected_bar_count": 10080,
  "actual_bar_count": 10012,
  "missing_bar_count": 68,
  "gap_segment_count": 3,
  "integrity_status": "backfilling",
  "stream_state": "live",
  "latest_adapter_sync_at": "2026-03-20T15:30:12Z",
  "last_backfill_requested_at": "2026-03-20T15:30:18Z",
  "last_backfill_ack_at": null,
  "snapshot_version": 42,
  "tail_version": 1088,
  "chart_cache_key": "NQ:1m:default-workspace",
  "cached_at": "2026-03-20T15:30:19Z",
  "view_state_version": 12,
  "follow_latest": true,
  "workspace_cache_status": "fresh",
  "initial_window_policy": "3h_for_1m"
}
```

这样前端才能知道：
- 当前是否还缺数据
- 是否正在补数
- 有没有新版本可 merge
- 当前缓存是否可直接恢复
- 当前是否仍处于首屏窗口模式

---

## 16. 改造优先级

### P0：必须先完成

#### P0-1 后端 7 天完整性扫描
- 对当前 timeframe 计算 7 天理论 bar 数
- 生成 gap segments
- 统一输出 integrity 状态

#### P0-2 自动 backfill request
- gap 一出现就自动创建 request
- 不依赖用户点击刷新

#### P0-3 C# 稳定 poll + 执行 + ack
- 保证 ATAS 侧持续执行补数命令
- ack 仅在数据真正入后端后发送

#### P0-4 首屏快速加载
- 首次打开优先返回小窗口数据
- 1m 默认先给最近 3 小时
- 渲染成功后再后台扩窗

#### P0-5 前端无感 merge
- synthetic filler 可被真实 bar 替换
- 中段缺失 bars 可自动插入
- viewport 不跳

### P1：强实时体验增强

#### P1-1 live-tail 增量更新
- 尾部只更新最新 bar
- 减少全量 setData

#### P1-2 图表状态持久化与实时缓存
- 本地缓存最近图表状态
- 后端缓存最近工作台状态
- 页面关闭后可恢复
- 新开页面可秒开最近状态

#### P1-3 数据状态 UI
- 展示 live/delayed/stale/backfilling
- 展示缺口数量与最近补数时间
- 展示缓存恢复状态与缓存新鲜度
- 展示当前是否处于首屏窗口/后台扩窗阶段

#### P1-4 自动跟随 / 历史查看双模式
- 跟随最新
- 保持历史视口

### P2：长期优化

#### P2-1 SSE 实时推送
- 补数完成后主动推送前端
- 减少轮询延迟
- 推送缓存版本更新事件

#### P2-2 WebSocket 双向控制
- 多图表订阅
- 更细粒度更新事件

---

## 17. 文件级改造建议

### 17.1 Python 后端
重点文件：
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/app.py`

建议新增/强化：
1. 首屏窗口裁剪与按周期默认窗口策略
2. 7天完整性扫描函数
3. 自动 `atas-backfill-request` 触发逻辑
4. ack 后自动 rebuild / merge 逻辑
5. snapshot/tail version 机制
6. integrity status 输出
7. 图表工作台缓存读写接口
8. live stream / SSE 接口（中期）

### 17.2 C# / ATAS
重点文件：
- `src-csharp/AtasMarketStructure.Adapter/Collector/AtasMarketStructureCollectorShell.cs`
- `src-csharp/AtasMarketStructure.Adapter/Collector/CollectorInfrastructure.cs`
- `src-csharp/AtasMarketStructure.Adapter/Contracts/AdapterPayloads.cs`

建议新增/强化：
1. continuous-state 失败重试
2. backfill poll 固定节奏
3. backfill 执行成功判定更严格
4. ack 前确认历史已真正送达后端
5. sequence / stream id
6. 断连恢复逻辑

### 17.3 前端
重点文件：
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/init_lightweight_chart.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_chart_utils.js`

建议新增/强化：
1. 数据 merge 层
2. synthetic filler 替换机制
3. 中段缺失插补 merge
4. 尾部 update 模式
5. viewport 锁定策略
6. 本地缓存与恢复机制
7. 首屏窗口模式与后台扩窗衔接逻辑
8. integrity / backfill / cache 状态提示

---

## 18. 验收标准

完成后必须通过以下验收：

### 场景 1：ATAS 正常实时运行
- 最新 bar 持续更新
- 数据状态显示 `live`
- 不出现明显停顿

### 场景 2：短时网络抖动
- live tail 可短暂延迟
- 后端检测 gap
- 自动创建 backfill request
- ATAS 自动回补
- 前端无感补回缺段

### 场景 3：中间缺了几分钟
- 图表时间轴不被压缩
- 前端可临时显示 filler
- 补数回来后被真实 bars 替换
- 用户不需要手动刷新

### 场景 4：最近7天窗口完整性
- 任意时刻都能输出 expected / actual / missing
- 只要 missing > 0，系统处于 `backfilling` 或 `degraded`
- 缺口补完后回到 `complete`

### 场景 5：用户正在查看历史区域
- 补数回来时不跳到最新
- 缩放级别不变
- 当前视口尽量不变

### 场景 6：页面关闭后再次打开
- 图表优先恢复到上一次关闭前的状态
- 当前品种、周期、视口、缩放尽量保留
- 然后静默追平最新 live/backfill 数据

### 场景 7：新开一个页面
- 不从空白图开始
- 优先读取最近缓存快照
- 图表先秒开，再无感追最新

### 场景 8：首屏快速加载
- 1m 周期首次默认只加载最近 3 小时
- 其他周期按默认首屏窗口策略返回
- 首屏先开出来，再后台扩窗与补数
- 扩窗过程不影响当前操作与视口

---

## 19. AI交互与策略事件可视化设计

### 19.1 设计目标

在 Replay Workbench 中，AI 交互与 K 线图的关系不能设计成“把所有信息都直接画到图上”。

如果把：
- 策略库命中结果
- 事件 annotations
- AI 分析结论
- 入场/止损/止盈建议
- 手工区域
- 焦点区域

全部同时堆到 K 线图上，最终结果一定是：
- 主图拥挤
- 信息互相遮挡
- 用户第一眼看不出重点
- 真正重要的结构反而被淹没

所以这里的目标不是“显示更多”，而是：

> 让用户第一眼看出“行情在什么地方发生了什么关键事件”，并且能在需要时逐层展开更多上下文，而不是让主图承担全部解释责任。

### 19.2 总体原则：三层表达

建议将 AI + K 线 + 策略库事件拆成三层表达，而不是单层堆叠：

#### 第一层：K线主图层
主图只承载最关键、最少量、最值得盯的对象：

1. **K 线本体**
2. **高优先级价格区域**
   - focus regions
   - support / resistance
   - no-trade zone
   - defendable zone
3. **高价值事件锚点**
   - gap
   - replenishment
   - initiative drive
   - harvest / post-harvest
   - strategy hit
4. **当前 AI 计划对象**
   - entry line
   - stop loss
   - take profit
   - invalidation zone

主图上不应直接展示长段解释文本，只展示：
- 价格本体
- 区域
- 小型 marker
- 必要的计划线

#### 第二层：事件时间轴 / 事件列表层
这一层负责回答：

> 这里具体发生了什么？

建议放在：
- 图下方轻量时间轴
- 或右侧事件列表 / 事件抽屉

每个事件卡片至少展示：
- 时间
- 事件类型
- 方向
- 强度/置信度
- 关联策略
- 简短说明

K 线图上的 marker 只负责“提示这里有事发生”，真正解释放到事件列表里。

#### 第三层：AI语义聚合层
AI 不应该简单重复原子事件，而应该负责把原子事件组织成：

1. **结构摘要**
   - 例如：09:42–09:47 出现买方吸收 + 同价补单，构成 defendable support
2. **阶段判断**
   - 例如：上方流动性 harvest 完成后，进入 lower relocation 风险段
3. **操作对象**
   - 例如：入场、止损、目标、失效条件

也就是说：

> 策略库负责提供“事实与事件”，AI 负责把这些事实组织成“结构化结论”，然后再把结论投影回图表对象。

### 19.3 主图不臃肿的关键原则

为了避免 K 线主图臃肿，建议强制遵守以下规则：

#### 原则 1：默认只显示 Top-N 高价值事件
主图默认不展示所有事件，而只展示：
- 高优先级事件
- 最新关键事件
- 与当前 AI 计划直接相关的事件

例如：
- 默认只显示最近窗口内 top 5~10 个高价值 marker
- 普通低优先级事件进入事件列表，不直接压到主图上

#### 原则 2：按事件族折叠
不要让每个原子事件都独立占一个图形对象。

建议先按事件族折叠，例如：
- liquidity family
- replenishment family
- drive family
- gap family
- strategy-hit family

默认只显示事件族摘要，用户展开后再看单条事件。

#### 原则 3：按时间段聚合 cluster
同一小时间窗内多个事件，不要在图上画多个重叠 marker。

建议聚合成 cluster marker，例如：
- `3` 表示该时间附近有 3 个事件
- `吸收×2 + gap×1`
- `策略命中×2`

点击 cluster 后，再在侧边栏或 popover 中展开详情。

#### 原则 4：主图短标签，详情侧栏展开
主图上的任何文本必须控制为短标签，例如：
- `买方吸收`
- `Gap回补`
- `驱动`
- `策略命中`

不要把长 explanation 直接写在图上。

长解释统一进入：
- annotation popover
- 右侧详情抽屉
- AI 会话面板

### 19.4 策略库事件到图表对象的统一映射

策略库内部可能有很多复杂的 reason code、pattern、doctrine 和 machine-readable signals。

但投影到图表时，不建议每种策略各画一套 UI，而应统一收敛成 4 类图表对象：

#### 1）Point Marker（点事件）
用于单点触发类事件，例如：
- gap open / gap fill
- replenishment
- initiative start
- liquidity take
- strategy hit

展示方式：
- 放在 bar 上方或下方
- 小图标 + 短标签
- hover 显示简述

#### 2）Price Zone（价格区）
用于区间类对象，例如：
- support zone
- resistance zone
- no-trade zone
- defendable region
- manual region
- harvested area

展示方式：
- 半透明价格带
- 尽量弱化视觉重量
- 可按优先级调透明度和边框强度

#### 3）Time Span（持续过程）
用于某个行为持续发生了一段时间，例如：
- initiative drive 持续段
- absorption 持续段
- harvest response 持续段

展示方式：
- 细时间带
- 背景弱高亮
- 或顶部小状态条

#### 4）Plan Overlay（AI/策略计划对象）
用于 AI 或策略最终产出的可执行对象，例如：
- entry line
- stop loss
- take profit
- invalidation line / zone

展示方式：
- 线对象
- 区域对象
- 可显式挂载 / 卸载

这样做的好处是：
- 策略库可以持续扩展
- 图表表达形式保持稳定
- 用户只需理解 4 类对象，而不必理解底层全部 reason code

### 19.5 建议的视觉编码规范

建议为不同对象建立统一视觉语义：

#### 事件族 → marker 形状
- 圆点：流动性 / 吸收 / replenishment
- 三角：initiative / directional drive
- 方块：gap / gap fill / balance shift
- 旗标：策略命中 / AI 结构结论
- 菱形：人工标注 / 手工确认事件

#### 方向 → 颜色
- 绿色：偏多
- 红色：偏空
- 黄色 / 橙色：中性警示 / 过渡状态
- 蓝色：信息型 / 人工型 / 辅助型
- 紫色：AI 聚合结论 / 策略命中对象

#### 强度 → 视觉权重
- 高置信：更高不透明度 / 更粗边框
- 低置信：更淡、更轻
- 已失效对象：置灰或虚线

#### 生命周期 → 样式
- active：实线 / 正常亮度
- pending：弱亮度 / 半透明
- invalidated：灰色 / 虚线 / 删除线标签
- historical-only：低存在感，只在展开时显示

### 19.6 AI交互应如何嵌入图表

AI 与图表的关系不应是“AI 面板独立存在，图表独立存在”，而应形成可跳转、可挂载、可回溯的关系。

建议将 AI 交互拆成以下几类操作：

#### 1）从图到AI
用户在图表上：
- 点击某根 K 线
- 框选某段区域
- 点击某个 marker
- 点击某个 focus region

然后发起：
- `分析这根K线`
- `分析这个区域`
- `解释这个事件`
- `围绕这个结构生成计划`

#### 2）从AI回图
AI 回复后，不能只停留在文字区，而应能把结论回挂到图上：
- entry / SL / TP 线
- invalidation 区域
- support / resistance 区域
- 关键事件引用

#### 3）从事件到AI
用户点击某个策略事件时，应能直接触发：
- `为什么这是高优先级事件？`
- `这个事件对应策略库里的哪个 pattern？`
- `它和前后结构有什么关系？`

#### 4）从AI到事件列表
AI 在生成总结时，应同时输出关联事件引用：
- linked_event_ids
- linked_region_ids
- linked_plan_ids

这样用户看 AI 的一句结论时，可以反查：
- 它依据了哪些事件
- 它依据了哪几个区域
- 它对应图上的哪个对象

### 19.7 最推荐的交互流

建议最终把用户体验设计成以下流程：

#### 第一步：打开图表
用户第一眼只看到：
- K 线
- 少量 focus region
- 少量高价值 marker
- 当前挂载的 AI 计划对象

此时主图干净、可读。

#### 第二步：鼠标扫过 / hover
hover marker 时只显示一行短提示，例如：
- `09:43 买方吸收（高置信）`
- `09:57 Gap 回补完成`
- `10:12 策略命中：Upper liquidity harvest`

#### 第三步：点击看详情
点击 marker / region 后，在右侧详情或 popover 中显示：
- 事件说明
- 关联 bars
- 关联策略
- AI 摘要
- 是否可生成计划

#### 第四步：需要时再展开AI分析
用户再点击：
- `解释原因`
- `生成计划`
- `继续分析后续演化`

AI 才进一步展开结构推理。

#### 第五步：计划挂载到图表
如果 AI 生成了有效的交易计划，则用户可以：
- 挂载到图表
- 高亮 entry / SL / TP
- 后续继续跟踪计划生命周期

也就是说：

> 图表负责定位“哪里有事”，事件面板负责解释“发生了什么”，AI 负责总结“这意味着什么、可以怎么做”。

### 19.8 与当前代码结构的落地方向

结合当前 Replay Workbench 已有代码结构，建议后续按以下方向落地：

#### 前端侧
重点文件：
- `src/atas_market_structure/static/replay_workbench_chart_overlays.js`
- `src/atas_market_structure/static/replay_workbench_annotation_panel.js`
- `src/atas_market_structure/static/replay_workbench_annotation_popover.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_plan_lifecycle.js`

建议新增/强化：
1. 事件族分层显示与折叠控制
2. Top-N 关键 marker 渲染策略
3. cluster marker 机制
4. marker → 事件详情 → AI 会话联动
5. AI 回复 → 图上 plan overlay 挂载
6. 事件时间轴 / 事件抽屉视图

#### 后端侧
重点文件：
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/app.py`

建议新增/强化：
1. 事件优先级排序字段
2. 事件分组字段（event family / cluster key）
3. linked_event_ids / linked_region_ids / linked_plan_ids 输出
4. 策略命中对象与事件对象的统一投影结构
5. AI 结果与图表 annotation 的统一挂载协议

### 19.9 本节结论

AI + K线图 + 策略库事件的最佳设计，不是把所有信息都压到主图上，而是：

- **主图只放最关键的价格、区域、少量事件和计划对象**
- **事件列表负责说明发生了什么**
- **AI 负责把事件组织成结构结论和操作对象**
- **用户通过点击/hover/挂载，在图、事件、AI 三者之间自由跳转**

最终目标不是让图表更“热闹”，而是让它更“可读、可解释、可操作”。

---

## 20. 图表库与展示方案选型优化建议

### 20.1 为什么需要单独讨论图表库选型

前文已经明确了：
- K线历史加载要快开
- 实时更新要无感
- 缺口补数要自动并入
- AI 与策略事件要能投影到图表
- 图表不能因为信息太多而臃肿

这意味着问题已经不只是“能不能画 K 线”，而是：

> 当前图表引擎是否适合承载实时尾部更新、事件叠加、AI 对象挂载、回放、以及低拥挤可视化这些需求。

因此有必要把“图表库/展示方案选型”作为独立设计项纳入整体方案，而不是把它当成纯实现细节。

### 20.2 选型原则

对于 Replay Workbench 这类工作台，图表库不应该只按“谁更像 TradingView”来选，而应该按以下标准综合评估：

1. **K线主图性能是否稳定**
2. **实时尾部 update 是否顺手**
3. **是否适合中段插补 / backfill merge**
4. **是否方便做自定义 overlay 与对象分层**
5. **是否容易与 AI 面板、事件面板联动**
6. **是否适合 replay / bar-by-bar 演进展示**
7. **是否适合当前已有前端代码结构渐进演进**
8. **迁移成本是否可控**

结论上，这个项目的关键并不是“找到一个包办一切的图表库”，而是找到：

> 一个稳定的 K 线主图引擎 + 一套适合事件、AI、计划对象的自定义叠加层与联动架构。

### 20.3 可借鉴的库/产品类型

#### 20.3.1 TradingView Lightweight Charts
优点：
- K 线主图性能好
- 实时尾部更新模型清晰
- 轻量、集成成本低
- 适合自己构建 overlay 与工作台层

缺点：
- 内建 annotation / drawing object 能力有限
- 复杂图表对象体系需要自己补
- AI / 事件 / 计划对象联动要靠自研

适配判断：
- **很适合作为当前项目的主图底座继续使用**
- 不适合期待它原生解决“策略事件工作台”的全部需求

#### 20.3.2 TradingView Charting Library
优点：
- 功能最完整
- 绘图、对象、指标、交互成熟
- 用户认知成本低，接近专业终端体验

缺点：
- 接入复杂度更高
- 授权与可用性要求更高
- 与当前已有代码耦合改造成本较大
- 容易把项目重心带向“适配库”，而不是“完成工作台逻辑”

适配判断：
- 适合未来如果要做更完整、更通用的图表终端时再评估
- **不建议作为当前阶段的优先迁移方向**

#### 20.3.3 Highcharts Stock
优点：
- stock 场景能力成熟
- 时间轴、缩放、navigator、annotation 等相对完整
- 适合企业级工作台整合

缺点：
- 金融交易图手感不如 TradingView 系列自然
- 若主要目标是“交易图 + 自定义结构叠加”，优势不一定显著

适配判断：
- 可作为“需要比 Lightweight 更强 annotation，但又不想引入完整 TV Library”的备选
- **属于可选折中方案，但不是当前最优**

#### 20.3.4 Apache ECharts
优点：
- 自定义能力极强
- 不只是 K 线，还适合做事件轨、热力视图、结构副图、统计面板
- 多图联动、组合式分析工作台能力强

缺点：
- K 线主图交互手感通常不如专业金融图表库
- 若用它承载全部主图交易体验，细节工作量会比较大

适配判断：
- **非常适合做事件轨、副图、结构面板、热力层等辅助可视化模块**
- 不一定适合作为当前项目唯一的主 K 线引擎替代 Lightweight

#### 20.3.5 D3 / Plotly / Vega-Lite 等通用可视化库
优点：
- 可塑性高
- 适合做实验性或研究型可视化

缺点：
- 如果拿来当主 K 线引擎，工程成本高
- replay、实时尾部 update、对象系统往往都要自己补齐

适配判断：
- 适合局部特殊图层，不适合当前项目作为主图基础设施

#### 20.3.6 Bookmap / ATAS / Sierra / GoCharting 等产品形态借鉴
这类更多是“产品交互形态”的参考，不是直接替换库。

可重点借鉴：
- Bookmap：热力与事件发生位置感知
- ATAS：orderflow / footprint 与价格行为并列展示
- Sierra / NinjaTrader：专业对象层与图层开关
- GoCharting：DOM / footprint / orderflow 的组合视图

适配判断：
- **适合借鉴交互思路，不适合直接当作前端集成库方案**

### 20.4 对当前项目最有性价比的方案

综合当前项目现状，最合理的路线不是全面换库，而是：

#### 推荐路线：主图引擎保持 Lightweight Charts，增强自定义叠加层

建议的目标架构为：

```text
Lightweight Charts（K线主图）
    +
自定义 Overlay 层（marker / zone / span / plan）
    +
事件时间轴 / 副图层
    +
右侧事件详情 / AI 会话面板
    +
后端统一事件投影协议
```

这样做的优点：
1. 保留现有项目中已经可用的 K 线主图能力
2. 避免大规模迁移带来的不确定性
3. 更容易围绕 replay/backfill/live-tail 做针对性优化
4. 更适合逐步演进，而不是一次性推翻重来
5. 更符合当前项目的核心难点：
   - 不是 K 线画不出来
   - 而是事件、AI、策略对象如何低拥挤地组织起来

### 20.5 具体可优化的展示架构

#### 20.5.1 主图只负责价格与关键对象
继续让主图只承载：
- candles
- focus regions
- Top-N 高价值事件 marker
- AI plan overlays

不要把所有策略事件都压进主图。

#### 20.5.2 增加独立事件轨
建议增加一条与主图共享时间轴的轻量事件轨，专门展示：
- event cluster
- strategy hit
- AI 摘要节点
- 回放阶段切换点

这一层更适合借鉴 ECharts / TradingView pane 思路，而不是继续把所有对象堆在主图上。

#### 20.5.3 增加图层管理器
建议增加类似专业终端的 layer manager：
- 事件层
- 区域层
- 计划层
- AI 标注层
- 手工标注层

每层都支持：
- 显示/隐藏
- Top-N
- 仅当前会话
- 仅当前选中对象
- 仅高优先级对象

#### 20.5.4 增加 cluster marker 机制
对于同一时间窗口内密集事件，不应逐条画 marker，而应先聚合成 cluster。

cluster 点开后，再在 popover 或右侧事件抽屉中展示明细。

#### 20.5.5 增加 replay 友好的“渐进显露”机制
当前项目是 replay workbench，因此事件展示应支持：
- 只显示截至当前 replay 游标时刻已知的事件
- 随 replay 前进逐步显露后续事件
- AI 总结也受当前 replay 时间边界约束

这类机制比单纯换图表库更重要。

### 20.6 建议借鉴而不是照搬的设计点

应重点借鉴以下能力：

#### 从 TradingView 借鉴
- 小型 marker 体系
- drawing object 的对象化思维
- hover tooltip + 点击展开详情
- pane / 副图共享时间轴
- replay 的逐步显露体验

#### 从 Highcharts Stock 借鉴
- stock 场景下的 annotation 组织方式
- navigator / overview 视图
- 企业工作台式的完整交互组织

#### 从 ECharts 借鉴
- 事件轨
- 多图联动
- 复杂辅助可视化
- 时间轴驱动的组合视图

#### 从 Bookmap / ATAS 类产品借鉴
- 事件与价格位置关系的表达方式
- “哪里发生了什么”的空间感知
- orderflow / footprint 与价格行为并列而不互相遮挡的布局

### 20.7 工程实现上的优化建议

结合当前项目代码结构，建议优化不是“先换库”，而是按下面顺序推进：

#### 第一阶段：继续沿用 Lightweight Charts，补足对象层
重点做：
1. event family / cluster 数据结构
2. marker / zone / span / plan 四类对象层
3. 主图 Top-N 限流显示
4. annotation popover 与事件详情联动
5. AI plan 挂载/卸载协议

#### 第二阶段：补事件轨与图层管理
重点做：
1. 事件轨副图
2. layer manager
3. replay 时间边界过滤
4. hover / click / jump 联动

#### 第三阶段：评估是否需要引入新库辅助副图
如果后续发现：
- 事件轨
- 热力/footprint 辅助图
- 复杂结构面板

在当前方案下实现成本过高，再考虑：
- 主图仍保持 Lightweight Charts
- 辅助图层引入 ECharts 或其他通用图表库

也就是说：

> 推荐优先采用“主图不换，副图与辅助层渐进增强”的方案，而不是直接整体迁移。

### 20.8 本节结论

从当前项目目标来看，最优解不是单纯寻找一个“比 TradingView 更好”的库，而是：

- 主图继续使用轻量、稳定、适合实时尾部更新的 K 线引擎
- 事件、AI、计划对象通过自定义 overlay 分层表达
- 复杂说明和上下文转移到事件轨、详情面板与 AI 面板
- 借鉴 TradingView / Highcharts / ECharts / Bookmap 的长处，但不把项目架构绑死在某一个库上

对于当前 Replay Workbench，最推荐的工程路线仍然是：

> **继续以 Lightweight Charts 作为 K 线主图底座，在其上补事件层、计划层、事件轨与 AI 联动层，而不是现在就大规模替换主图引擎。**

---

## 20.9 前端交互收敛补充（2026-03）

上文主要解决的是 **K 线数据链路、补数、缓存恢复、实时一致性**。

但如果前端主图交互本身不收敛，用户仍然会感觉“图表能看，但不好用”，这会直接削弱设计目标。

因此，针对当前 Replay Workbench 前端，还需要补充以下设计约束：

### 20.9.1 ChartToolbar 必须回到图表主战场

图表区左侧工具栏必须直接提供这些操作：

- 放大 / 缩小 / 重置
- 框选区域
- 保存区域
- 图表截图
- 发送当前可视区域到聊天

这几类动作属于 **主图即时动作**，不能只藏在右侧聊天区或底部抽屉里。

原则是：

> 用户看着 K 线做决策时，最短路径必须在 K 线旁边完成，而不是跨区域找按钮。

### 20.9.2 按钮不能出现“死点击”

所有图表与聊天相关按钮都必须满足：

1. 点击后 `120ms` 内出现可见反馈
2. 异步动作必须有忙碌态
3. 不支持的动作必须明确提示原因
4. 不能出现点击后页面无变化、状态条无变化、按钮也无变化的情况

具体要求：

- 点击态：有按压 / 回弹反馈
- 忙碌态：有 loading / pulse / busy 状态
- 成功态：至少更新状态条、附件条或对应面板
- 失败态：明确给出错误文案

### 20.9.3 AI 快捷入口必须映射到真实动作

AI 输入区周围的快捷按钮不能只是装饰。

至少应做到：

- `语音` / `语音输入`：启动浏览器语音输入，或明确提示当前浏览器不支持
- `附件`：直接打开附件选择
- `截图`：直接把当前图表截图放入当前会话附件
- `更多`：打开技能 / 快捷动作面板

也就是说，AI 区的小按钮必须和主图上下文真正打通，而不是“后续再实现”的占位按钮。

### 20.9.4 K线状态要从“只显示数据状态”升级为“显示工作台状态”

顶部状态条与图表状态条不能只显示 `历史 / 实时`。

建议至少分层展示：

- 数据状态：`live / delayed / historical`
- 完整性状态：`complete / needs_backfill / degraded`
- 缓存恢复状态：`restored / cold_start / stale_cache`
- 最近同步时间
- 当前 viewport 上下文摘要

这样用户才能知道：

- 图有没有追到最新
- 最近 7 天数据是否完整
- 当前页面是不是从缓存恢复出来的
- 现在看到的是不是“上次打开的样子”

### 20.9.5 当前页面的 P0 收敛项

为了让现有页面尽快接近设计态，优先级应按下列顺序推进：

#### P0

- 图表主工具栏补齐 `保存区域` 与 `图表截图`
- 所有静态按钮补齐真实动作或明确反馈
- 输入发送、停止生成、附件、截图、语音等操作补齐即时反馈
- 右栏与左栏之间的图表上下文动作打通
- 空面板、空抽屉、空状态条不占空间

#### P1

- 图层管理器补齐大单 / 吸收 / 冰山 / 补单等层
- 顶部状态区补完整性 / 缓存恢复 / backfill 状态
- 图表截图从占位附件升级为真实图像快照
- 选中 K 线 / 手工区域 / 可视区域统一进入 Prompt block 装配链

### 20.9.6 这一补充的定位

这一节不是替代上文的数据链路设计，而是补齐一个事实：

> **K 线设计不仅是“数据对不对”，也是“主图区交互是不是足够直接、可感知、无死点击”。**

前端如果不满足这些交互约束，数据链路做得再强，用户体验也仍然偏离设计态。

---

## 21. 最终结论

当前系统已经具备：
- 历史加载能力
- 实时尾部更新能力
- gap 检测能力
- backfill 控制面雏形

但它还没有达到你要求的最终状态。

你要求的正确目标应该明确定义为：

> 最近至少 7 天、当前所选周期范围内，缺多少补多少；ATAS 与后端保持强联动；后台一旦补回真实数据，前端必须按时间轴无感并入图表，不要求人工刷新；同时图表关闭后再次打开或新开页面时，也必须尽量恢复到上一次使用时的状态；并且首屏加载必须优先快开，例如 1 分钟周期先只给最近 3 小时，再后台继续补齐更长历史。

换句话说：

**现状是“功能已具备雏形”，目标是“做成强联动、强补偿、强一致、前端无感、支持状态持久化与实时缓存恢复、并具备首屏快速加载策略的完整方案”。**

这份文档即为后续实现的完整设计依据。
