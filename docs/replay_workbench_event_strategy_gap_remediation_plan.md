# Replay Workbench 事件策略补齐方案

## 1. 目标

本文档用于补齐当前 Replay Workbench 中“事件策略 / 事件流”能力，解决以下问题：

1. 当前右侧事件整理更多是前端临时抽取，不是正式后端对象层。
2. 候选事件缺少稳定持久化、统一状态机与来源链路。
3. 主 AI 回复后没有自动进入事件提取闭环。
4. 候选事件与 annotation / plan card / chart overlay 的提升流程主要在前端拼装，缺少服务端统一规则。
5. 底部 strategy candidates 与右侧 event stream 是两套割裂体系。

目标不是继续“补按钮”，而是把系统补成三层：

- **行情交流层**：主 AI（Analyst）负责对话与分析。
- **事件候选层**：Event Scribe / Extraction 负责生成结构化候选事件流。
- **图表投影层**：用户选择后才生成 annotation / plan card，并进入图表。

---

## 2. 当前问题总结

结合 `docs/replay_workbench_ui_ai_design.md`、`docs/replay_workbench_dual_ai_task_list.md` 与当前代码实现，主要缺口如下：

### 2.1 缺少正式 EventCandidate 模型

当前没有独立的后端候选事件实体，前端主要通过：

- `state.aiAnnotations` 反推候选项
- `extractReplyCandidatesFromText()` 从文本正则抽价位/区域/风险

导致问题：

- 候选事件不稳定
- 不能统一持久化
- 刷新/多端后不一致
- 无法系统级去重/合并/审计

### 2.2 缺少 event-stream API / SSE

设计文档里需要的：

- `GET /api/v1/workbench/chat/sessions/{session_id}/event-stream`
- `POST /api/v1/workbench/chat/sessions/{session_id}/event-stream/extract`
- `PATCH /api/v1/workbench/chat/event-candidates/{event_id}`
- `POST /api/v1/workbench/chat/event-candidates/{event_id}/promote`
- `POST /api/v1/workbench/chat/sessions/{session_id}/event-stream/bulk`

当前尚未形成这套边界。

### 2.3 缺少“主 AI 回复完成 -> 自动提取候选事件”闭环

目前的 scribe 更像一个“第二聊天框”，还不是自动事件提取管线。

### 2.4 候选状态机仍在前端本地

当前 `replyExtractionState.bySymbol.candidateMeta` 只是浏览器状态，不是后端事实状态。

### 2.5 候选类型过粗

当前前端主要分为：

- `plan`
- `zone`
- `risk`
- `price`

但设计文档要求 6 类更细语义：

- `key_level`
- `price_zone`
- `market_event`
- `thesis_fragment`
- `plan_intent`
- `risk_note`

### 2.6 promotion 在前端完成，缺少服务端规则

当前前端直接构造 annotation / plan card，导致：

- 规则分散
- 状态难追踪
- 去重无统一入口
- 来源链路脆弱

---

## 3. 补齐后的目标架构

## 3.1 三层模型

### A. Analyst Conversation Layer

负责：

- 主 AI 对话
- 行情分析
- 结论输出

主要对象：

- `ChatSession`
- `ChatMessage`

### B. Event Candidate Layer

负责：

- 从 Analyst 回复中提取结构化候选事件
- 统一状态、去重、来源追溯、批处理

主要对象：

- `EventCandidate`
- `EventStream`
- `EventMemory`

### C. Projection Layer

负责：

- 候选事件提升为 annotation / plan card
- 与图表 overlays 联动

主要对象：

- `ChatAnnotation`
- `ChatPlanCard`
- `ChartOverlay`

---

## 4. 数据模型补齐方案

## 4.1 新增 EventCandidate

建议新增统一候选事件结构：

```json
{
  "event_id": "evt-...",
  "session_id": "sess-...",
  "source_message_id": "msg-...",
  "source_reply_role": "analyst",
  "source_agent": "event_scribe",
  "symbol": "NQ",
  "timeframe": "1m",
  "kind": "price_zone",
  "subtype": "resistance",
  "label": "上方阻力带",
  "summary": "18540-18548 为反抽压力区",
  "price": null,
  "price_low": 18540,
  "price_high": 18548,
  "observed_at": "...",
  "expires_at": null,
  "confidence": 0.78,
  "importance": 0.81,
  "status": "candidate",
  "promote_to_chart_allowed": true,
  "promote_to_plan_allowed": false,
  "promoted_object_type": null,
  "promoted_object_id": null,
  "source_excerpt": "...",
  "dedup_key": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

## 4.2 状态机

统一状态枚举：

- `candidate`
- `confirmed`
- `mounted`
- `ignored`
- `promoted_plan`
- `expired`
- `archived`

推荐状态流：

`candidate -> confirmed -> mounted / promoted_plan`

或：

`candidate -> ignored`

## 4.3 类型体系

统一六类：

1. `key_level`
2. `price_zone`
3. `market_event`
4. `thesis_fragment`
5. `plan_intent`
6. `risk_note`

建议允许动作矩阵：

| kind | 上图 | 转计划卡 | 进入时间线 |
|---|---|---:|---:|
| key_level | 是 | 否 | 可选 |
| price_zone | 是 | 否 | 可选 |
| market_event | 可选 | 否 | 是 |
| thesis_fragment | 否 | 否 | 是 |
| plan_intent | 可选 | 是 | 是 |
| risk_note | 可选 | 否 | 是 |

---

## 5. 后端补齐方案

## 5.1 Repository 层

建议在 `repository.py` 中新增：

- `StoredEventCandidate`
- `save_event_candidate(...)`
- `update_event_candidate(...)`
- `get_event_candidate(event_id)`
- `list_event_candidates(session_id, status, kind, limit)`
- `bulk_update_event_candidates(...)`

若当前数据库沿用 SQLite / ClickHouse 混合方式，可先把 event candidates 放入现有 chat/session 同类持久化结构，优先落到主应用可读写存储层。

## 5.2 Service 层

建议在 `workbench_services.py` 中新增 `ReplayWorkbenchEventStreamService`，负责：

1. `extract_candidates_for_session(session_id, source_message_id)`
2. `list_event_stream(session_id, filters)`
3. `patch_event_candidate(event_id, status/pinned/importance)`
4. `promote_event_candidate(event_id, target="annotation"|"plan_card")`
5. `bulk_apply(session_id, action, filters)`

## 5.3 提取器层

新增独立提取器，例如：

- `SharedReplyExtractionAgent`
- 或 `EventCandidateExtractionService`

输入：

- 最新 user message
- 最新 analyst reply
- session memory
- active plans
- visible annotations

输出：

- `EventCandidate[]`

### 实施建议

第一阶段允许双轨：

- **主轨**：模型结构化抽取
- **兜底**：保留当前正则抽取逻辑，但迁移到后端，且仅作为 fallback

即不要再让前端负责主提取逻辑。

## 5.4 自动触发链路

在 Analyst reply 流结束后：

1. `message_end`
2. 后端调用事件提取器
3. 保存 EventCandidate
4. 推送 event-stream SSE

建议 SSE 事件：

- `event_stream_start`
- `event_candidate_patch`
- `event_stream_end`

## 5.5 promotion 改为服务端完成

当前前端的：

- `promoteCandidateToAnnotation()`
- `buildPlanCardFromCandidate()`

应逐步改成只发请求，不再本地生成正式对象。

服务端 promotion 规则：

- `key_level / price_zone / risk_note` -> `ChatAnnotation`
- `plan_intent` -> `ChatPlanCard`
- `market_event / thesis_fragment` 默认不直接转 plan，可进入 timeline note

输出时必须写回：

- `promoted_object_type`
- `promoted_object_id`
- `status`

---

## 6. 前端补齐方案

## 6.1 保留面板，但重构数据来源

受影响文件：

- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench.css`

核心原则：

- **保留现有右侧候选面板 UI 骨架**
- **将数据源从本地推断切换为后端 event-stream**

## 6.2 state 改造

新增：

- `eventStreamBySessionId`
- `eventStreamLoadingBySessionId`
- `eventStreamFilter`
- `eventScribeEnabled`
- `eventScribeMode`

弱化 / 废弃：

- `replyExtractionState.bySymbol.candidateMeta` 作为主状态来源

它最多只保留 UI 偏好：

- collapsed
- filter
- showIgnored
- intensity

不能再承载候选事件事实状态。

## 6.3 面板交互调整

右侧面板建议拆成两个层次：

### 默认模式

只展示：

- 自动记录开关
- 强度切换
- 类型过滤
- 批量处理
- 候选卡片流

### 高级模式

再展示：

- 手动触发提取
- Scribe 对话输入框

这样避免“第二聊天窗”干扰主工作流。

## 6.4 候选卡片排序策略

建议默认顺序：

1. `plan_intent`
2. `risk_note`
3. `price_zone`
4. `key_level`
5. `market_event`
6. `thesis_fragment`

即先看：

- 能否执行
- 哪些不能做
- 关键区域在哪里

而不是先堆一串数字。

## 6.5 卡片动作

每条候选保留：

- `[上图]`
- `[确认]`
- `[忽略]`
- `[转计划卡]`
- `[来源]`

但动作走服务端接口。

前端只负责：

- optimistic UI（可选）
- 刷新 event stream
- 聚焦对应 source message / annotation

---

## 7. 与策略系统统一方案

## 7.1 问题

当前存在两套“候选”：

1. 底部 drawer 的 `strategy_candidates`
2. 右侧 reply extraction candidates

用户感知会割裂。

## 7.2 建议统一策略

定义统一信息层：

### 市场事实层

- replay/live 结构事件
- liquidity
- gap
- footprint

### AI 解释层

- event candidates
- thesis fragments
- risk notes
- plan intents

### 执行层

- annotations
- plan cards
- overlays

### UI 分工

- **底部 drawer**：长期背景 / 策略库匹配 / replay 结构上下文
- **右侧事件流**：当前会话可操作候选项

这样两者分工不同，但底层对象体系可以统一。

---

## 8. 分阶段落地计划

## Phase 1：补对象层与最小链路

目标：先从“前端伪事件流”升级到“正式后端候选流”。

### 任务

1. 新增 `EventCandidate` 数据模型与 repository
2. 新增 event-stream API
3. 新增自动提取服务
4. Analyst `message_end` 后自动触发提取
5. 前端面板改为读取后端 event stream

### 完成标准

- 页面刷新后候选事件仍在
- 候选状态跨端一致
- 不再依赖前端正则作为主来源

## Phase 2：补 promotion 与来源链路

### 任务

1. 服务端实现 candidate -> annotation
2. 服务端实现 candidate -> plan card
3. 前端来源跳转统一
4. 建立 `source_message_id / event_id / promoted_object_id` 链路

### 完成标准

- 任一 annotation 可追溯来源 candidate
- 任一 candidate 可追溯来源 message
- plan card 可追溯来源 candidate

## Phase 3：补规模化可用性

### 任务

1. 去重 / 合并规则
2. 批量处理
3. 过滤排序增强
4. EventMemory / AnalystMemory 双轨

### 完成标准

- 高频使用时不会被重复候选淹没
- 批量确认/忽略/上图/转计划稳定可用

## Phase 4：补体验增强

### 任务

1. 流式增量提取
2. 自动推荐上图
3. timeline notes
4. 导出事件摘要

---

## 9. 建议的文件级改造清单

## 后端

### 必改

- `src/atas_market_structure/workbench_services.py`
  - 新增 EventStream service / extract / patch / promote / bulk
- `src/atas_market_structure/repository.py`
  - 新增 event candidate 持久化
- `src/atas_market_structure/models.py`
  - 新增 EventCandidate / EventStreamResponse / PromoteRequest 等模型
- `src/atas_market_structure/app_routes/` 下对应路由文件
  - 新增 event-stream 相关 API

### 可选新增文件

- `src/atas_market_structure/event_stream_services.py`
- `src/atas_market_structure/event_extraction_services.py`

## 前端

### 必改

- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench.css`

### 建议新增/拆分

- `src/atas_market_structure/static/replay_workbench_event_stream.js`
  - event-stream 获取、patch、promote、bulk
- `src/atas_market_structure/static/replay_workbench_event_stream_panel.js`
  - 渲染右侧候选事件面板

---

## 10. 风险与注意事项

## 10.0 事件提取准确率提升方案

这是补齐中的第一优先级之一，因为如果提取不准，后面的 event stream / promote / 上图都会放大噪音。

### 10.0.1 当前准确率差的根因

当前提取容易不准，通常来自 5 类问题：

1. **输入上下文不完整**
   - 只看单条 analyst 回复，不看用户问题、当前 symbol、timeframe、已存在 plan、图表可视区。
2. **抽取目标不清晰**
   - 没有严格区分“事实 / 推断 / 计划 / 风险 / 价格区间”。
3. **只靠前端正则**
   - 能抓到数字，但抓不到语义边界、条件句、否定句、优先级。
4. **没有 schema 约束**
   - 模型输出不稳定，字段缺失或类型漂移。
5. **没有回评估闭环**
   - 没有 gold set、没有 precision/recall、没有误报漏报样本池。

### 10.0.2 可落地的提升方法

建议按“多层提取 + 置信评分 + 校验回路”来做，而不是指望一次 prompt 就彻底解决。

#### A. 改成两阶段提取

不要让模型一步直接吐最终 EventCandidate，建议分两步：

**阶段 1：语义切片（Span Detection）**

从 analyst reply 中先找：

- 哪一句是关键价位
- 哪一句是区间
- 哪一句是风险提示
- 哪一句是计划意图
- 哪一句是市场事件

输出 `candidate_spans[]`：

```json
[
  {
    "span_text": "18540-18548 是反抽压力区",
    "span_type": "price_zone",
    "start_char": 18,
    "end_char": 36,
    "confidence": 0.84
  }
]
```

**阶段 2：结构化归一化（Normalization）**

再把 span 转成正式 EventCandidate：

- price_low / price_high
- kind / subtype
- summary
- confidence
- importance
- source_excerpt

这样比一步到位更稳，因为先找“语义片段”，再做“结构映射”。

#### B. 建立严格 schema 输出

要求模型严格输出 JSON，并做服务端 schema 校验。若失败：

1. 先重试一次修复格式
2. 再 fallback 到规则抽取
3. 标记 `extraction_mode = fallback_rule`

这能避免“看起来提取成功，其实字段错位”。

#### C. 引入规则校验器（Validator）

模型抽出来后，不要直接入库，先过校验器：

- `price_low <= price_high`
- `confidence` 在 0~1
- `kind=price_zone` 时必须有价格边界
- `plan_intent` 不能只有纯数字、必须有动作语义（如等待、回踩、确认、做多、做空、止损）
- `risk_note` 里出现否定 / 规避语义（如不要追、避免、失效、无优势）时优先归入风险类

规则校验器不是替代模型，而是压掉低级错误。

#### D. 做“类型专用 prompt”而不是单 prompt 通吃

与其让一个 prompt 同时抽 6 类，不如拆成：

- `extract_key_levels`
- `extract_price_zones`
- `extract_plan_intents`
- `extract_risk_notes`
- `extract_market_events`

最后再 merge + dedup。

这样好处是：

- 类型边界更清晰
- prompt 更短
- 每类规则更容易迭代

#### E. 引入上下文增强

提取时必须拼入这些上下文：

- 当前 symbol / timeframe
- 用户最后一问
- analyst 最后一答
- 最近 3~5 条对话摘要
- 当前 chart visible range
- 当前已存在 annotation / active plan

很多误报并不是模型笨，而是缺乏上下文导致把“举例”“复述”“否定”当成正式事件。

#### F. 置信度改为组合评分

不要只信模型给的一个 confidence。建议总分来自：

- `model_confidence`
- `schema_valid_score`
- `rule_consistency_score`
- `context_alignment_score`
- `dedup_penalty`

例如：

```text
final_confidence =
  0.45 * model_confidence +
  0.20 * schema_valid_score +
  0.15 * rule_consistency_score +
  0.15 * context_alignment_score -
  0.05 * dedup_penalty
```

只有超过阈值的候选才进入默认面板；低分项进入“低置信候选”折叠区。

#### G. 让 analyst 输出更适合提取

这是最容易被忽略、但收益很高的一步：

如果 analyst 回复本身结构混乱，后面很难抽准。建议把 analyst 输出模板约束为：

1. 当前判断
2. 关键价位 / 关键区间
3. 触发条件
4. 风险 / 失效条件
5. 应对计划

即先把“生产文本的人”规范化，再去做抽取，准确率会明显上升。

#### H. 建立 gold set + 离线评估

必须抽 100~300 条真实 analyst 回复，人工标注：

- 哪些是 `key_level`
- 哪些是 `price_zone`
- 哪些是 `plan_intent`
- 哪些是 `risk_note`
- 哪些不该被抽

然后离线评估：

- precision
- recall
- F1
- 按类型分桶表现
- top false positive / top false negative

没有这一步，就只能靠感觉调 prompt。

### 10.0.3 我建议的准确率路线

按投入产出比，建议优先级如下：

#### 第一梯队（最值得先做）

1. 两阶段提取：span -> normalized event
2. schema 校验 + rule validator
3. 上下文增强
4. analyst 回复模板化

#### 第二梯队

5. 类型专用 prompt
6. 组合置信评分
7. 低置信候选折叠展示

#### 第三梯队

8. gold set + 自动评估回归
9. 针对误报类型做 hard negative prompt / few-shot
10. 引入轻量 reranker 或二次审校模型

### 10.0.4 可接受的准确率目标

建议不要追求“一开始全自动 100% 准”，而是先定义业务可用阈值：

- `price_zone / key_level` precision ≥ 0.85
- `risk_note / plan_intent` precision ≥ 0.80
- 整体高置信候选 precision ≥ 0.85
- 默认面板 false positive rate 明显低于当前版本

也就是说，**先保证默认看到的候选“少而准”**，再逐步补 recall。

### 10.0.5 一句话建议

如果你问我“最有效的提升办法是什么”，不是继续堆正则，而是：

**把事件提取做成：结构化 analyst 输出 + 两阶段抽取 + schema/规则校验 + 离线评估闭环。**

## 10.1 不要继续把前端正则抽取当主系统

它可以作为 fallback，但不能再作为事实数据源。

## 10.2 不要让 Scribe 直接污染图表

必须坚持：

`候选事件 -> 用户确认/提升 -> 正式 annotation / plan card`

## 10.3 不要让主 AI 同时承担聊天与完整归档责任

主 AI 负责交流，事件提取层负责结构化整理。

## 10.4 先补结构，再优化体验

推荐顺序：

1. 对象模型
2. API
3. 自动提取
4. promotion
5. 去重批量
6. 流式体验

---

## 11. 一句话结论

当前“事件策略不可用”的根因，不是少几个 UI 控件，而是**系统缺少正式的候选事件层**。补齐方案的核心也不是继续前端修修补补，而是尽快落地：

**Analyst Reply -> Event Extraction -> EventCandidate Store -> Event Stream API -> Promote to Annotation/Plan**

只有这条链路成立，右侧事件策略面板才会从“前端临时整理器”升级成真正可用的交易工作流。