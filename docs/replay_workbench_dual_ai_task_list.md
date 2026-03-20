# Replay Workbench 双 AI 协作开发任务清单

基于以下文档与需求整理：
- `docs/replay_workbench_ui_ai_design.md`
- `docs/replay_workbench_ai_chat_backend_api_design.md`
- `docs/replay_workbench_ai_chat_frontend_implementation_plan.md`
- 用户新增需求：
  - 一个 AI 专门处理行情交流
  - 一个 AI 专门记录关键点位、事件信息
  - 形成可审阅的信息流
  - 支持选择性标记到左侧 K 线图

---

## 总体目标

把当前右侧 AI 工作区从“单 AI 聊天 + 零散上图”升级为：

1. **主 AI（行情分析 AI）**
   - 负责与你直接交流行情
   - 负责分析、推演、计划、风险说明

2. **辅 AI（事件记录 AI）**
   - 负责监听你与主 AI 的对话
   - 提取关键点位、关键区域、关键事件、计划意图、风险提示
   - 形成候选事件流
   - 供你选择性确认、忽略、上图或转计划卡

3. **候选事件流 → 正式图表对象**
   - 不允许聊天内容直接无脑上图
   - 必须先进入候选层，再由用户选择投影到图表

---

## P0（优先立即补齐）

### P0-1 建立双 AI 概念层与状态模型
**目标**
- 在现有单 AI 会话系统中正式引入“主 AI + 辅 AI”概念。

**涉及文档 / 文件**
- `docs/replay_workbench_ui_ai_design.md`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 在 session 级状态中加入：
  - `activeAnalystModel`
  - `eventScribeEnabled`
  - `eventScribeMode`
  - `eventStreamBySessionId`
- 明确主 AI 回复与辅 AI 事件提取的调用顺序
- 保证切会话时双 AI 相关状态可恢复

---

### P0-2 建立候选事件对象模型（EventCandidate）
**目标**
- 给“事件流”定义统一结构，避免后续前后端各自发挥。

**涉及文档 / 文件**
- `docs/replay_workbench_ui_ai_design.md`
- `docs/replay_workbench_ai_chat_backend_api_design.md`
- `src/atas_market_structure/static/replay_workbench_state.js`

**改造点**
- 定义统一字段：
  - `event_id`
  - `session_id`
  - `source_message_id`
  - `symbol`
  - `timeframe`
  - `kind`
  - `subtype`
  - `label`
  - `summary`
  - `price / price_low / price_high`
  - `observed_at / expires_at`
  - `confidence / importance`
  - `status`
  - `promote_to_chart_allowed`
  - `promote_to_plan_allowed`
- 统一状态枚举：
  - `candidate`
  - `confirmed`
  - `mounted`
  - `ignored`
  - `expired`
  - `archived`

---

### P0-3 事件类型分类落表
**目标**
- 把辅 AI 可产出的信息类型先规范好，后续提示词和 UI 才能稳定。

**涉及文档 / 文件**
- `docs/replay_workbench_ui_ai_design.md`
- 新增 schema 草案文档（如有必要）

**改造点**
- 固化 6 类候选事件：
  1. `key_level`
  2. `price_zone`
  3. `market_event`
  4. `thesis_fragment`
  5. `plan_intent`
  6. `risk_note`
- 为每类补字段说明与是否允许上图 / 转计划卡

---

### P0-4 主 AI 回复完成后触发辅 AI 事件提取
**目标**
- 建立最稳定的双 AI 协作链路。

**涉及文件**
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/ai_review_services.py`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 保持主 AI 继续走现有流式回复链路
- 在主 AI `message_end` 后触发一次辅 AI 提取
- 辅 AI 输入至少包括：
  - 最新用户消息
  - 最新 analyst reply
  - 当前 session memory
  - 当前 active plans
  - 当前已挂载标记（可选）
- 提取结果回写为当前 session 的 candidate event stream

---

### P0-5 新增右侧候选事件流面板（EventScribePanel）
**目标**
- 在 UI 中给“事件记录 AI”的结果一个独立承载区。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 在右栏新增可折叠 `EventScribePanel`
- 区分主消息流和候选事件流
- 面板头部提供：
  - 开关
  - 记录强度
  - 类型过滤
  - 批量操作入口
- 候选项支持卡片式展示，不做成第二聊天窗

---

### P0-6 单条候选事件操作闭环
**目标**
- 每个候选事件必须可被处理，而不是只展示文本。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_chart_overlays.js`
- `src/atas_market_structure/static/replay_workbench_annotation_panel.js`
- `src/atas_market_structure/static/replay_workbench_annotation_popover.js`

**改造点**
- 每条候选事件支持：
  - `[上图]`
  - `[确认]`
  - `[忽略]`
  - `[转为计划卡]`
  - `[查看来源消息]`
- “上图”行为应走正式 annotation / plan card 流程
- “查看来源消息”可回跳到对应 analyst reply / user message

---

### P0-7 候选事件提升为正式图表对象
**目标**
- 打通 candidate → annotation / plan card → chart overlay 的最小闭环。

**涉及文件**
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/static/replay_workbench_chart_overlays.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`

**改造点**
- 支持把 `key_level / price_zone / market_event` 提升为 annotation
- 支持把 `plan_intent` 提升为 plan card
- 提升后同步 mounted 状态与图层状态
- 图上对象保留来源 event_id / source_message_id

---

### P0-8 双轨 Session Memory 基础版
**目标**
- 避免辅 AI 每轮重复抽取相同内容，也保证模型切换时不丢主信息。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_session_memory.js`
- `src/atas_market_structure/static/replay_workbench_model_switcher.js`
- `src/atas_market_structure/workbench_services.py`

**改造点**
- 在现有 memory 基础上区分：
  - `AnalystMemory`
  - `EventMemory`
- `AnalystMemory` 维护：目标、结论、剧本、关键区域、活动计划
- `EventMemory` 维护：已提取候选、已确认、已挂载、已忽略

---

### P0-9 最小 API / SSE 清单落地
**目标**
- 先把双 AI 所需接口边界明确，避免实现阶段反复返工。

**涉及文档 / 文件**
- `docs/replay_workbench_ai_chat_backend_api_design.md`
- 可新增后端任务草案文档

**改造点**
- 至少补齐以下接口设计：
  - `GET /api/v1/workbench/chat/sessions/{session_id}/event-stream`
  - `POST /api/v1/workbench/chat/sessions/{session_id}/event-stream/extract`
  - `PATCH /api/v1/workbench/chat/event-candidates/{event_id}`
  - `POST /api/v1/workbench/chat/event-candidates/{event_id}/promote`
  - `POST /api/v1/workbench/chat/sessions/{session_id}/event-stream/bulk`
- 至少补齐以下 SSE 事件：
  - `event_stream_start`
  - `event_candidate_patch`
  - `event_stream_end`

---

## P1（第二阶段）

### P1-1 批量处理候选事件
**目标**
- 提高高频使用场景下的处理效率。

**改造点**
- 支持批量：
  - 确认
  - 忽略
  - 上图
  - 转计划卡
- 支持“仅处理高优先级 / 仅处理当前过滤结果”

---

### P1-2 候选事件过滤与排序增强
**目标**
- 在事件流变多之后仍保持可读性。

**改造点**
- 支持按以下维度过滤：
  - 类型
  - 状态
  - 置信度
  - 重要度
  - 来源消息
- 支持排序：
  - 最新优先
  - 高优先级优先
  - 未处理优先

---

### P1-3 去重与合并规则引擎
**目标**
- 避免同一阻力位、同一风险提示被辅 AI 每轮重复生成。

**涉及文件**
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/repository.py`

**改造点**
- 基于以下维度去重：
  - 同 session
  - 同 kind
  - 同 price / zone
  - 相似 label / summary
- 合并时允许：
  - 提升 confidence
  - 增加引用计数
  - 更新最后出现时间

---

### P1-4 来源链路可追溯
**目标**
- 候选事件、正式 annotation、plan card 三者之间关系可追踪。

**改造点**
- 图上对象可查看来源 event candidate
- event candidate 可查看来源消息
- 消息中可看到“本轮提取出哪些候选事件”

---

### P1-5 手动增强提取模式
**目标**
- 允许用户在关键时刻主动让辅 AI 做更重的整理。

**改造点**
- 新增按钮：
  - `提取本轮关键事件`
  - `整理为时间线`
  - `提取关键点位`
- 允许指定范围：
  - 仅当前一轮
  - 最近 3 轮
  - 当前会话摘要

---

### P1-6 候选事件 → 时间线视图
**目标**
- 除了上图，还能在右侧形成复盘友好的事件时间线。

**改造点**
- 支持把部分 market events / thesis fragments 汇总成 timeline notes
- 与底部复盘抽屉联动

---

## P2（增强体验）

### P2-1 流式增量事件提取
- 主 AI 流式输出时，辅 AI 同步做增量抽取
- 需要更严格的去重与 UI 防抖策略

### P2-2 记录强度模式细化
- `轻量`：只提取高价值点位 / 风险
- `标准`：提取点位、区域、事件、计划意图
- `激进`：附带 thesis fragments 与更多候选项

### P2-3 自动推荐上图
- 基于置信度、重要度、是否重复、是否已有 mounted 对象给出“推荐上图”标签

### P2-4 双 AI 模型策略可配置
- analyst / event-scribe 分别选择模型
- 支持成本优先 / 准确优先 / 极速优先预设

### P2-5 事件摘要导出
- 导出当前会话的事件流摘要
- 导出复盘材料
- 导出上图对象来源说明

### P2-6 事件流与策略库联动
- 将高价值 pattern / event 序列沉淀到策略库候选条目

---

## 建议的落地顺序

1. **先做结构，不先做花活**
   - P0-1 / P0-2 / P0-3
   - 先把双 AI 状态、候选事件模型、事件类型定义清楚

2. **再打通最小链路**
   - P0-4 / P0-5 / P0-6 / P0-7
   - 实现“主 AI 回复 → 辅 AI 提取 → 事件面板展示 → 单条上图/忽略/确认”

3. **再补持久化与记忆**
   - P0-8 / P0-9
   - 把 memory、API、SSE 边界固定下来

4. **第二阶段解决规模化可用性**
   - P1-1 / P1-2 / P1-3 / P1-4
   - 重点解决批量处理、过滤排序、去重合并、来源追溯

5. **最后再追求体验增强**
   - P1-5 / P1-6 / 全部 P2

---

## 实施原则

### 原则 1：主 AI 只负责聊天与分析
- 不要让主 AI 同时承担完整事件归档职责
- 保持主消息流流畅、自然、稳定

### 原则 2：辅 AI 只输出候选层
- 不要让辅 AI 直接污染图表
- 必须经过候选 → 确认/提升 → 正式对象 的路径

### 原则 3：图表永远以“用户可控”为第一原则
- 选择性上图
- 支持忽略
- 支持回溯来源
- 支持批量处理

### 原则 4：先保证结构清晰，再追求实时炫技
- P0 先做“回复后触发提取”
- 流式增量提取放到 P2

---

## 一句话总结

这份任务清单的核心，不是“再加一个 AI”，而是把系统明确拆成三层：

1. **行情交流层**：主 AI 负责分析与对话
2. **事件候选层**：辅 AI 负责记录、提炼、生成候选信息流
3. **图表投影层**：只有被选择的候选事件才进入正式标记与 K 线渲染

这样才能既保留高质量行情交流，又把关键点位与事件沉淀成真正可用的交易工作流。