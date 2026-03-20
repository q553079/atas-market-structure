# ATAS 开平仓 / 账户成交追踪设计方案

## 状态

- `status`: `proposed_design`
- `scope`: ATAS 账户/订单/成交/持仓 → 本地服务 → 数据库存储 → 前端聚合展示 → AI 在线追踪 → 周复盘
- `priority`: `high`

---

## 1. 背景与目标

当前系统已经能从 ATAS 侧采集：

- 行情价差与逐笔成交
- DOM / 大单流动性
- second-level 特征
- history bars / history footprint
- 回放工作台的结构化事件

但**还没有真正采集“交易执行层”数据**，也就是：

- 哪个账户开仓
- 哪个账户平仓
- 进场时间
- 进场价格
- 离场时间
- 离场价格
- 开仓数量 / 平仓数量
- 持仓方向与剩余仓位
- 订单状态变化（新单 / 部分成交 / 全成 / 撤单 / 拒单）

这部分数据对后续目标非常关键：

1. 前端聚合展示真实开平仓行为
2. 支持按账户分开展示 / 合并展示
3. AI 在线追踪当前仓位生命周期
4. 形成每周复盘与交易统计
5. 为后续“计划 → 执行 → 管理 → 结果”闭环打基础

---

## 2. 这件事现在是否已经支持？

### 2.1 当前代码库现状：**不支持**

当前仓库里的 C# ATAS 采集器只覆盖了：

- `OnCumulativeTrade`
- `OnUpdateCumulativeTrade`
- `OnBestBidAskChanged`
- `MarketDepthChanged`
- `OnMarketByOrdersChanged`
- history bars / history footprint / backfill 控制平面

当前 payload contract 只定义了：

- `continuous_state`
- `trigger_burst`
- `history_bars`
- `history_footprint`
- backfill command/ack

**没有账户、持仓、订单、成交回报相关消息。**

也就是说：

> 当前系统还没有把“开平仓执行数据”接入进来。

---

## 3. 联网确认结论

### 3.1 已确认的部分

通过联网至少确认：

- `help.atas.net` 站点可访问（返回 302 到帮助中心首页）
- 当前公开网页抓取在本环境里不稳定，搜索页 TLS/抓取存在限制

### 3.2 未能通过公开网页直接确认的部分

由于当前网络环境限制与公开文档抓取不稳定，**本次没有拿到足够的官方页面证据，能够 100% 证明 ATAS 指标 API 一定能直接暴露以下对象**：

- account / portfolio
- position changed callback
- order changed callback
- own trade / execution callback

因此这里必须给出一个**保守结论**：

> **公开网页层面，本次未能完成“官方文档实锤确认”。**

### 3.3 结合现有 ATAS 指标生态，给出的工程判断

虽然本次没有抓到足够的官方网页文档，但从现有 ATAS 指标 / 数据回调模型、以及常见交易平台 API 结构判断：

- **拿到市场数据（trade/depth/MBO）是已验证的**
- **拿到账户/订单/持仓/成交回报“有较大概率可行”**，但不能在没有探针验证前直接当成既定事实

所以正确做法不是直接宣布“肯定能拿到”，而是：

> 先做 **ATAS Execution Probe** 验证，再决定最终接入路径。

这是生产上更稳妥的方案。

---

## 4. 总体设计原则

1. **执行数据优先保证正确性，不追求先炫 UI**
2. **账户级别、订单级别、成交级别分层存储**
3. **成交回报（fill / execution）是事实源头**
4. **仓位生命周期由成交流推导，不靠前端猜测**
5. **必须支持多账户并行**
6. **前端既能聚合，也能按账户拆分**
7. **所有时间统一 UTC 存储**
8. **价格、数量、方向、手续费、归因都要可追溯**
9. **AI 只消费结构化执行事实，不直接消费 UI 状态**
10. **若 ATAS 指标 API 拿不到完整执行数据，则必须改走本地交易回报桥接方案**

---

## 5. 分阶段结论

### 结论 A：如果 ATAS 能直接提供账户/订单/成交/持仓事件
那么最优方案是：

- 在 C# 采集器新增 execution/account 通道
- 发到 Python 后端
- 后端标准化并持久化
- 前端实时展示
- AI 读取执行事实流

### 结论 B：如果 ATAS 只能部分提供（例如只有持仓，没有订单明细）
那么采用降级方案：

- 优先采集 `position snapshot + own trade executions`
- 用成交流重建开仓/平仓事件
- 订单细节作为可选增强

### 结论 C：如果 ATAS 指标 API 完全拿不到执行层事件
那么采用替代方案：

- 保留现有行情采集器不动
- 新增独立的本地桥接程序（或 C# companion）
- 从 ATAS 可用的交易侧接口、导出、日志、插件能力中单独获取执行数据
- 和市场数据在后端按时间轴统一汇总

---

## 6. 必须先做的验证任务（P0）

这是最重要的一步。

### 6.1 新建 `ATAS Execution Probe`

目标：验证以下能力是否真实可用。

#### Probe 需要验证的对象

- 账户列表是否可枚举
- 账户唯一标识是否可获取
- 当前净持仓是否可获取
- 持仓变更事件是否可订阅
- 活动订单是否可枚举
- 订单状态变化是否可订阅
- 自有成交 / 成交回报是否可订阅
- 成交中是否带：
  - account id
  - symbol
  - side
  - qty
  - price
  - exec time
  - order id
  - execution id

### 6.2 Probe 输出要求

Probe 不接业务系统，只打印和落本地日志：

```text
[ATAS-EXEC-PROBE] account=SIM-01 position=+2 avg=21541.25
[ATAS-EXEC-PROBE] order status changed order=abc123 status=working
[ATAS-EXEC-PROBE] execution fill exec=fill-889 account=SIM-01 side=buy qty=1 price=21542.00 time=...
```

### 6.3 Probe 验收标准

只有满足以下条件，才进入正式开发：

1. 能稳定拿到账户标识
2. 能稳定拿到成交回报
3. 成交回报的时间、价格、数量与 ATAS 界面一致
4. 持仓变化与成交累计结果一致
5. 多账户情况下不会串号

---

## 7. 推荐的数据模型

执行层建议拆成四层：

1. `account`
2. `order`
3. `execution_fill`
4. `position_lifecycle`

其中：

- `execution_fill` 是最底层事实
- `position_lifecycle` 是聚合视图
- `weekly_review` 是更高层复盘产物

---

## 8. 建议新增消息契约

建议在现有 adapter contract 基础上新增 4 类消息。

### 8.1 `account_snapshot`

作用：周期性上报账户静态/半静态状态。

```json
{
  "schema_version": "1.0.0",
  "message_type": "account_snapshot",
  "emitted_at": "2026-03-21T01:00:00Z",
  "source": { "system": "ATAS", "instance_id": "DESKTOP-ATAS-01", "chart_instance_id": "exec-bridge", "adapter_version": "0.11.0" },
  "accounts": [
    {
      "account_id": "SIM-01",
      "account_label": "Main Sim",
      "broker": "SIM",
      "currency": "USD",
      "equity": 100000.0,
      "balance": 100000.0,
      "margin_used": 0.0,
      "updated_at": "2026-03-21T01:00:00Z"
    }
  ]
}
```

### 8.2 `position_snapshot`

作用：周期性上报账户 × 合约维度净持仓。

```json
{
  "schema_version": "1.0.0",
  "message_type": "position_snapshot",
  "emitted_at": "2026-03-21T01:00:00Z",
  "positions": [
    {
      "account_id": "SIM-01",
      "symbol": "NQM6",
      "side": "long",
      "net_quantity": 2,
      "avg_price": 21541.25,
      "unrealized_pnl": 125.0,
      "realized_pnl": 420.0,
      "updated_at": "2026-03-21T01:00:00Z"
    }
  ]
}
```

### 8.3 `order_update`

作用：订单状态变化流。

```json
{
  "schema_version": "1.0.0",
  "message_type": "order_update",
  "emitted_at": "2026-03-21T01:00:01Z",
  "order": {
    "order_id": "ord-001",
    "client_order_id": "local-001",
    "account_id": "SIM-01",
    "symbol": "NQM6",
    "side": "buy",
    "order_type": "limit",
    "time_in_force": "day",
    "price": 21541.25,
    "stop_price": null,
    "quantity": 2,
    "filled_quantity": 1,
    "remaining_quantity": 1,
    "status": "partially_filled",
    "submitted_at": "2026-03-21T01:00:00.200Z",
    "last_updated_at": "2026-03-21T01:00:01.050Z"
  }
}
```

### 8.4 `execution_fill`

作用：成交事实流，最关键。

```json
{
  "schema_version": "1.0.0",
  "message_type": "execution_fill",
  "emitted_at": "2026-03-21T01:00:01.080Z",
  "execution": {
    "execution_id": "fill-0001",
    "order_id": "ord-001",
    "account_id": "SIM-01",
    "symbol": "NQM6",
    "side": "buy",
    "fill_quantity": 1,
    "fill_price": 21541.25,
    "fill_time": "2026-03-21T01:00:01.050Z",
    "commission": 1.8,
    "fees": 0.0,
    "liquidity_flag": null,
    "exchange_trade_id": null
  }
}
```

---

## 9. 后端数据库设计

建议新增以下表。

### 9.1 `trading_accounts`

字段：

- `account_id` PK
- `account_label`
- `broker`
- `currency`
- `first_seen_at`
- `last_seen_at`
- `is_active`
- `metadata_json`

### 9.2 `trade_orders`

字段：

- `order_id` PK
- `client_order_id`
- `account_id`
- `symbol`
- `side`
- `order_type`
- `time_in_force`
- `price`
- `stop_price`
- `quantity`
- `filled_quantity`
- `remaining_quantity`
- `status`
- `submitted_at`
- `last_updated_at`
- `raw_payload_json`

索引：

- `(account_id, symbol, submitted_at desc)`
- `(status, last_updated_at desc)`

### 9.3 `trade_executions`

字段：

- `execution_id` PK
- `order_id`
- `account_id`
- `symbol`
- `side`
- `fill_quantity`
- `fill_price`
- `fill_time`
- `commission`
- `fees`
- `exchange_trade_id`
- `raw_payload_json`
- `ingested_at`

索引：

- `(account_id, symbol, fill_time desc)`
- `(order_id, fill_time asc)`
- `(fill_time desc)`

### 9.4 `position_snapshots`

字段：

- `snapshot_id` PK
- `account_id`
- `symbol`
- `side`
- `net_quantity`
- `avg_price`
- `unrealized_pnl`
- `realized_pnl`
- `updated_at`
- `raw_payload_json`

索引：

- `(account_id, symbol, updated_at desc)`

### 9.5 `position_lifecycles`

这是 AI 和前端最常用的聚合对象。

字段：

- `lifecycle_id` PK
- `account_id`
- `symbol`
- `direction`
- `opened_at`
- `closed_at`
- `open_quantity`
- `close_quantity`
- `entry_avg_price`
- `exit_avg_price`
- `gross_pnl`
- `net_pnl`
- `max_open_quantity`
- `status` (`open` / `closed` / `partial_exit`)
- `first_execution_id`
- `last_execution_id`
- `execution_count`
- `holding_seconds`
- `session_code`
- `trading_date`
- `tags_json`

索引：

- `(account_id, opened_at desc)`
- `(symbol, opened_at desc)`
- `(status, opened_at desc)`
- `(trading_date, account_id)`

---

## 10. 核心聚合逻辑

### 10.1 以成交回报为准

必须遵守：

- **订单不是事实终态**
- **成交才是事实终态**
- **仓位生命周期由成交累加/对冲推导**

### 10.2 生命周期重建规则

以 `account_id + symbol` 为分组键，按 `fill_time, execution_id` 排序。

#### Long 例子

- buy 1 @ 100 → 开多开始
- buy 1 @ 101 → 加仓
- sell 1 @ 103 → 部分止盈
- sell 1 @ 104 → 平仓结束

则重建为一个 `position_lifecycle`：

- `opened_at = 第一笔 buy 时间`
- `closed_at = 最后一笔使净仓位回到 0 的 sell 时间`
- `entry_avg_price = 加权平均`
- `exit_avg_price = 平仓部分加权平均`

### 10.3 反手场景

例如：

- 当前净多 1
- 再来 sell 2

则要拆成：

1. 先平掉原多单 1
2. 剩余 1 手形成新的空头 lifecycle

这部分必须在后端明确实现，不能让前端自己猜。

---

## 11. 与市场数据对齐

用户特别强调：

- 数据要对
- 要实时记录
- 进场离场的时间和价格必须准确
- 方便 AI 在线追踪

因此必须把执行数据和行情时间轴统一。

### 11.1 统一时间规则

所有执行层时间统一存：

- `exchange/event original time`（若有）
- `adapter observed time`
- `server ingested_at`

其中前端默认展示：

- `event original time`
- 无原始时间时退化为 `adapter observed time`

### 11.2 与 K 线绑定

后端增加一个映射字段：

- `bar_bucket_started_at`
- `display_timeframe`

这样前端可以在：

- 1m 图上画执行点
- 5m / 15m 图上按桶聚合

### 11.3 执行点图层

图表叠加层要支持：

- 开仓点（箭头）
- 加仓点
- 减仓点
- 平仓点
- 悬浮显示账户 / 数量 / 价格 / 时间 / pnl

---

## 12. API 设计建议

### 12.1 实时流

新增：

- `POST /api/v1/adapter/account-snapshot`
- `POST /api/v1/adapter/position-snapshot`
- `POST /api/v1/adapter/order-update`
- `POST /api/v1/adapter/execution-fill`

### 12.2 前端查询 API

#### 查询执行流水

- `GET /api/v1/trading/executions?symbol=NQ&account_id=SIM-01&start=...&end=...`

#### 查询订单状态

- `GET /api/v1/trading/orders?...`

#### 查询生命周期

- `GET /api/v1/trading/position-lifecycles?...`

#### 聚合概览

- `GET /api/v1/trading/summary?group_by=account|symbol|day|week`

#### 当前开仓概览

- `GET /api/v1/trading/open-positions`

#### 周复盘

- `GET /api/v1/review/weekly?week=2026-W12&account_id=SIM-01`

---

## 13. 前端展示设计

### 13.1 展示模式

前端至少支持 3 种模式：

1. **聚合模式**
   - 所有账户合并看
2. **按账户拆分**
   - 每个账户单独筛选
3. **账户 + 合约交叉筛选**
   - 例如只看 `SIM-01 + NQ`

### 13.2 工作台新增模块

建议新增：

- `执行记录`
- `当前持仓`
- `账户汇总`
- `周复盘`

### 13.3 图表上的执行标记

- `B` 开多
- `S` 开空
- `TP` 止盈
- `SL` 止损
- `X` 手动平仓
- `REV` 反手

### 13.4 右侧 AI 面板

AI 在线追踪区新增：

- 当前持仓方向
- 当前均价
- 当前未实现盈亏
- 最近一次加仓 / 减仓
- 入场后 adverse excursion / favorable excursion
- 当前交易是否偏离原计划

---

## 14. AI 在线追踪设计

### 14.1 AI 消费的不是 UI，而是执行事实流

新增 AI 输入对象：

- `current_open_positions`
- `recent_execution_fills`
- `active_position_lifecycles`
- `execution_vs_plan_assessment`

### 14.2 AI 可做的事情

#### 在线追踪

- 当前仓位是否仍符合原脚本
- 入场后是否出现异常加仓
- 是否过早止盈
- 是否在 no-trade 区域开单
- 是否在计划外位置追单

#### 事后复盘

- 该笔交易的 entry quality
- exit quality
- management quality
- execution slippage
- 是否与 AI/人工计划一致

### 14.3 每周复盘输入

按周聚合：

- 总交易数
- 胜率
- 平均盈亏比
- 平均持仓时长
- 最大连续亏损
- 各账户表现
- 各品种表现
- 各时段表现
- AI 计划一致率
- 计划外交易占比

---

## 15. 数据正确性要求

### 15.1 去重

成交流必须防重：

优先键：

- `execution_id`

若无稳定 execution id，则退化键：

- `account_id + symbol + fill_time + fill_price + fill_quantity + side + order_id`

### 15.2 顺序一致性

同一 `account_id + symbol` 下：

- 按 `fill_time`
- 若同秒冲突，再按 `execution_id/local_sequence`

### 15.3 可审计

数据库必须保留：

- 原始 payload
- 标准化记录
- 生命周期聚合结果

这样以后发现某笔交易显示不对，可以回溯。

---

## 16. 性能与实时性要求

### 16.1 实时目标

- 执行回报进入后端延迟：目标 `< 300ms`
- 前端可见延迟：目标 `< 1s`
- AI 跟踪状态刷新：目标 `1s ~ 3s`

### 16.2 容错

如果瞬时网络抖动：

- C# 端本地队列缓存最近 N 条执行消息
- 后端入库幂等
- 前端用增量拉取 + 当前 open position snapshot 修正

---

## 17. 风险与未知点

### 风险 1：ATAS 指标 API 未必直接暴露完整交易账户对象

这是当前最大不确定性。

应对：

- 先做 probe
- 若 probe 失败，改走 companion bridge

### 风险 2：不同券商 / 连接类型返回字段不一致

应对：

- payload 增加 `broker` / `connection_type`
- 原始 payload 全量落库
- 标准化层做字段映射

### 风险 3：同一账户多终端下单导致状态不全

应对：

- 优先采 execution fill，不依赖本地 order cache
- position snapshot 定时校验 lifecycle 重建结果

### 风险 4：部分成交 / 反手 / 锁仓逻辑复杂

应对：

- 后端专门实现 lifecycle engine
- 加单元测试覆盖

---

## 18. 推荐实施顺序

### P0：能力验证

1. 新建 `ATAS Execution Probe`
2. 验证 account / order / fill / position 能否获取
3. 做 5~10 笔人工测试订单
4. 校验时间、价格、数量完全一致

### P1：后端事实接入

1. 新增 execution/account payload schema
2. 新增 Python 接口
3. 新增数据库表
4. 实现 execution 幂等入库
5. 实现 lifecycle engine v1

### P2：前端展示

1. 图表执行点图层
2. 账户筛选
3. 聚合 / 分账户切换
4. 当前持仓面板
5. 执行记录表格

### P3：AI 在线追踪

1. 当前持仓事实流接入 AI
2. 计划一致性比对
3. 进场后管理质量判断
4. 复盘摘要生成

### P4：每周复盘

1. 周维度统计聚合
2. 周报页面
3. AI 周复盘总结
4. 典型错误模式归因

---

## 19. 与现有系统的关系

### 19.1 不建议直接改坏当前市场数据采集器

当前 collector 已经承担：

- continuous state
- trigger burst
- history bars
- history footprint
- backfill poll/ack

执行层建议：

- **优先独立加一条 execution 通道**
- 避免把市场数据 collector 变成一个过度复杂的大一统采集器

### 19.2 推荐架构

```text
ATAS Market Collector  ---> 市场结构/回放/AI 上下文
ATAS Execution Probe   ---> 账户/订单/成交/持仓
                           ↓
                     Python normalize + DB
                           ↓
               前端聚合展示 + AI 在线追踪 + 周复盘
```

---

## 20. 最终结论

### 结论 1
当前系统**还没有**把 ATAS 的开平仓、账户、订单、成交、持仓数据接入进来。

### 结论 2
本次联网只确认了 ATAS help 站点可访问，但**没有拿到足够官方网页证据**去 100% 证明指标 API 一定直接提供账户/执行对象，所以现在不能草率下结论说“已经确认 ATAS 一定能拿到”。

### 结论 3
工程上最稳妥的方案是：

- 先做 `ATAS Execution Probe`
- 若 probe 验证通过，直接走 execution 数据正式接入
- 若 probe 验证不通过，改走 companion bridge / 替代桥接方案

### 结论 4
无论最终数据从哪条 ATAS 能力链路拿到，**系统都应该以 execution fill 为事实源**，并在后端构建：

- 账户表
- 订单表
- 成交表
- 持仓生命周期表
- 周复盘聚合表

这样才能真正支持：

- 前端聚合/分开展示
- AI 在线追踪
- 每周复盘
- 计划—执行—结果闭环

---

## 21. 下一步最具体建议

下一步不要先改 UI，先做下面两件事：

1. **新增一个 C# Probe**，验证 ATAS 是否能拿到：
   - account
   - position
   - order update
   - execution fill

2. **若 Probe 成功，再实现最小闭环**：
   - `execution_fill` 入库
   - `position_lifecycle` 聚合
   - 前端图上显示开/平仓点

这是风险最低、价值最高的顺序。
