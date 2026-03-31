# Replay Workbench Attention-First UI Phase 0 Mapping

状态：Phase 0 映射草案  
日期：2026-03-31  
依赖：
- `docs/workbench/replay_workbench_attention_first_ui_v1.md`
- `docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md`

---

## 1. 这份文档解决什么

前面的设计文档和 contracts 文档已经定义了“应该有什么语义”，但还没有把这些语义落到当前代码库的真实锚点上。

这份文档专门回答五个问题：

1. 合同字段到底落在哪个现有对象里。
2. 哪些字段应该持久化，哪些只能在读路径或前端临时计算。
3. 哪些地方可以复用当前容器，避免立刻做 SQLite / schema 扩容。
4. 前端哪些函数当前会丢字段、重置状态、或者覆盖新增 metadata。
5. Phase 0 真正开始写代码时，第一批应改哪些文件，顺序是什么。

---

## 2. Phase 0 的硬原则

### 2.1 尽量复用已有 JSON 容器

当前 workbench 已经有几类非常关键的可复用容器：

- `StoredChatMessage.request_payload`
- `StoredChatMessage.response_payload`
- `StoredPromptTrace.snapshot`
- `StoredPromptTrace.metadata`
- `StoredPromptBlock.full_payload`
- `EventCandidate.metadata`

Phase 0 优先把新增语义放进这些容器，再投影到 API / 前端展示层。  
除非确实需要强校验或高频查询，否则先不要为了“字段看起来更干净”就新增数据库列。

### 2.2 只持久化稳定事实，不持久化窗口型派生状态

以下信息是稳定事实，适合持久化：

- reply 实际分析的时间区间
- reply 使用的 context version
- prompt block 的版本和治理属性
- event 的 source trace / 固定锚点标记

以下信息是窗口型派生状态，不应作为长期真相持久化：

- `nearby_event`
- `influencing_event`
- `historical`
- `stale_state`

这些都依赖“当前窗口”“当前激活回复”“当前是否 pinned”，应该在读路径或前端按当前状态计算。

### 2.3 不让 Phase 0 变成大规模 schema 改造

Phase 0 的目标是冻结语义和着陆点，不是一次性重写 chat/event/prompt trace 存储层。  
因此：

- `ChatMessage` 可以加 additive `meta`
- `PromptBlock` 可以加 additive 顶层投影字段
- 但底层持久化优先继续复用 `request_payload / response_payload / full_payload / metadata`

### 2.4 默认保留 legacy 路径

旧消息、旧 prompt block、旧 event candidate 在缺少新字段时必须继续工作：

- 可以继续显示
- 可以继续查询
- 不能因为缺少 attention-first metadata 就崩掉
- 只是降级到 legacy bubble / legacy event list / basic prompt chip

---

## 3. 现有代码锚点结论

### 3.1 Chat / Reply

当前最关键的现状：

- `src/atas_market_structure/repository_records.py`
  - `StoredChatMessage` 已经持有 `request_payload` 和 `response_payload`
- `src/atas_market_structure/workbench_chat_service.py`
  - `_prepare_reply_turn()` 已经把 UI 选择写入 user message `request_payload`
  - `_finalize_reply_turn()` 已经把模型输出写入 assistant message `response_payload`
  - `_message_model()` 当前没有把 `response_payload` 投影为公开 `meta`
- `src/atas_market_structure/models/_chat.py`
  - `ChatMessage` 目前没有 `meta`

结论：

- reply 相关 additive metadata 最合适的持久化落点是 `StoredChatMessage.response_payload["workbench_ui"]`
- API 层再把它投影为 `ChatMessage.meta.workbench_ui`
- 不需要为 `reply_window`、`assertion_level` 之类单独加一串顶层列

### 3.2 Prompt Trace

当前最关键的现状：

- `src/atas_market_structure/models/_workbench_prompt_traces.py`
  - `PromptTrace` 已经有 `snapshot` 和 `metadata`
  - `PromptTraceBlockSummary` 目前只有最小摘要字段
- `src/atas_market_structure/workbench_prompt_trace_service.py`
  - `create_prompt_trace()` 在模型调用前就会持久化快照
  - `_build_snapshot()` 已经汇总 prompt blocks、bar window、manual selection、memory summary

结论：

- `PromptTrace` 已经是最合适的“本次回答到底看了什么”的审计锚点
- `block_version`、`context_version`、`reply_window_anchor` 这些 Phase 0 语义，应该优先补进 `snapshot` / `metadata`
- 不需要新建另一套 trace 对象

### 3.3 Prompt Block

当前最关键的现状：

- `StoredPromptBlock` 目前只有：
  - `kind`
  - `preview_text`
  - `full_payload`
  - `selected_by_default`
  - `pinned`
  - `ephemeral`
- `workbench_chat_service._build_prompt_block()` 已经集中负责生成 block
- 前端 `normalizePromptBlock()` 会保留 `...raw`，但没有显式治理字段

结论：

- Phase 0 不急着给 `StoredPromptBlock` 扩数据库列
- 最稳妥做法是把治理字段先写进 `StoredPromptBlock.full_payload["block_meta"]`
- 再由 API 层把这些字段平铺投影给 `PromptBlock`

### 3.4 Event / Nearby Context

当前最关键的现状：

- `src/atas_market_structure/models/_workbench_events.py`
  - `EventCandidate` 已经有 `metadata`
  - 已经有 `source_prompt_trace_id`
- `src/atas_market_structure/workbench_event_service.py`
  - reply-time candidate 提取已经把 `source_prompt_trace_id` 串起来
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
  - 已经有按当前图表窗口过滤上下文的粗版逻辑

结论：

- “事件绑定 reply / trace / 当前窗口”这一层基础已经存在
- Phase 0 不需要把 `nearby / influencing / historical` 写回数据库
- 应该只补稳定锚点，例如 `metadata.fixed_anchor`
- `presentation_class` 在 Phase 3 更适合做读时计算

### 3.5 Frontend State

当前最关键的现状：

- `state.chartView` 已经是当前视口事实来源
- `chartViewportRegistry` / `pendingChartViewRestore` 已经承担视口保位
- session 对象已持有：
  - `selectedPromptBlockIds`
  - `pinnedContextBlockIds`
  - `promptBlocks`
  - `messages`
  - `mountedReplyIds`
- 但还没有：
  - `activeReplyId`
  - `activeReplyWindowAnchor`
  - `contextRecipeExpanded`
  - `changeInspector`

结论：

- `chartView` 继续做唯一合法的 `chart_visible_window` 来源
- reply 聚焦状态应该放到 session 级，而不是全局 root，避免切 thread 时丢上下文

### 3.6 Frontend 当前会丢失新 metadata 的位置

最大已知阻塞点：

- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
  - `mapServerMessage()` 当前会重建一个本地 `meta`
  - 这会丢掉未来后端发来的 `message.meta.workbench_ui`

结论：

- 只要这个函数不改，后端即使发出新的 workbench metadata，前端也接不住
- 这必须列入 Phase 0 第一批真实修补点

---

## 4. 合同字段到代码锚点的映射

## 4.1 `chart_visible_window`

| 项 | 推荐落点 |
|---|---|
| 真正来源 | 前端 `state.chartView` |
| 发送到后端 | `ChatReplyRequest.extra_context.ui_context.chart_visible_window` |
| 持久化 | 不单独持久化为消息长期字段 |
| 审计快照 | `PromptTrace.snapshot.request_snapshot.ui_context.chart_visible_window` |
| 前端使用 | reply stale / nearby context / change inspector 对齐 |

说明：

- 这是唯一合法的“当前窗口”事实来源。
- 不要从 `session.windowRange`、`quickRange`、`analysisRangeSelect` 反推。
- `session.windowRange` 当前同时承载本地字符串和后端结构体，不适合拿来做精确窗口。

## 4.2 Assistant Reply Metadata

### 推荐持久化路径

- `StoredChatMessage.response_payload["workbench_ui"]`

### 推荐 API 投影路径

- `ChatMessage.meta["workbench_ui"]`

### 推荐字段映射

| 合同字段 | 写入时机 | 持久化位置 | API / 前端读取位置 | 说明 |
|---|---|---|---|---|
| `reply_window` | reply finalize | `response_payload.workbench_ui.reply_window` | `message.meta.workbench_ui.reply_window` | 稳定事实，应持久化 |
| `reply_window_anchor` | reply finalize | `response_payload.workbench_ui.reply_window_anchor` | 同上 | 结构化答复、事件、Inspector 的共同比较键 |
| `reply_session_date` | reply finalize | `response_payload.workbench_ui.reply_session_date` | 同上 | 来自 replay snapshot / market session |
| `assertion_level` | reply finalize | `response_payload.workbench_ui.assertion_level` | 同上 | 稳定输出分类，应持久化 |
| `alignment_state` | reply finalize | `response_payload.workbench_ui.alignment_state` | 同上 | 初始值由后端给出，前端可再派生当前显示态 |
| `source_event_ids` | reply finalize | `response_payload.workbench_ui.source_event_ids` | 同上 | 可直接复用 `event_candidate_ids` |
| `source_object_ids` | reply finalize | `response_payload.workbench_ui.source_object_ids` | 同上 | annotation / plan / mounted object ids |
| `context_version` | trace finalize / reply finalize | `response_payload.workbench_ui.context_version` | 同上 | 与 trace 保持一致 |
| `cross_day_anchor_count` | reply finalize | `response_payload.workbench_ui.cross_day_anchor_count` | 同上 | 初期可为 `0` |
| `stale_state` | 不做稳定持久化真相 | 可选 initial value | 前端按当前窗口实时派生 | 依赖当前窗口，不应当作长期真相 |

### 推荐实现方式

Phase 0 不建议给 `ChatMessage` 增加大量顶层字段。  
建议只做两件事：

1. 在 `src/atas_market_structure/models/_chat.py` 里给 `ChatMessage` 加 additive `meta: dict[str, Any] = {}`
2. 在 `src/atas_market_structure/workbench_chat_service.py` 的 `_message_model()` 中，把：
   - attachments
   - prompt trace id
   - parent message id
   - `response_payload.workbench_ui`
   投影到 `meta`

### 为什么不直接顶层加字段

因为当前 reply 的真实持久化源已经是 `StoredChatMessage.response_payload`。  
如果再单独把这些字段抄成 `ChatMessage` 顶层，Phase 0 会立刻变成“双写 + 双来源”，后面更难收敛。

## 4.3 `context_version`

### 推荐真相来源

- `PromptTrace`

### 推荐双落点

- `PromptTrace.metadata["context_version"]`
- `StoredChatMessage.response_payload["workbench_ui"]["context_version"]`

### 推荐生成方式

`context_version` 建议由以下信息 hash 或拼接而成：

- `selected_block_ids`
- `pinned_block_ids`
- 每个 block 的 `block_id + block_version`
- `include_memory_summary`
- `include_recent_messages`
- `preset`

这样 `Change Inspector` 后续就可以比较：

- 同窗口不同上下文
- 同上下文不同窗口
- 不同交易日的固定锚点混入情况

## 4.4 Prompt Block Metadata

### 推荐持久化路径

- `StoredPromptBlock.full_payload["block_meta"]`

### 推荐 API 投影路径

- `PromptBlock.block_version`
- `PromptBlock.source_kind`
- `PromptBlock.scope`
- `PromptBlock.editable`
- `PromptBlock.author`
- `PromptBlock.updated_at`

### 推荐字段映射

| 合同字段 | 持久化位置 | API 投影 | 备注 |
|---|---|---|---|
| `block_version` | `full_payload.block_meta.block_version` | `PromptBlock.block_version` | 初始默认 `1` |
| `source_kind` | `full_payload.block_meta.source_kind` | `PromptBlock.source_kind` | 由 `kind` 归类，不替代 `kind` |
| `scope` | `full_payload.block_meta.scope` | `PromptBlock.scope` | 不要从 `pinned=true` 直接推成 `manual_global` |
| `editable` | `full_payload.block_meta.editable` | `PromptBlock.editable` | 决定 UI 是否可编辑 |
| `author` | `full_payload.block_meta.author` | `PromptBlock.author` | 可选 |
| `updated_at` | `full_payload.block_meta.updated_at` | `PromptBlock.updated_at` | 可选 |

### 当前 kind 到 `source_kind` 的建议映射

| 当前 `kind` | 推荐 `source_kind` |
|---|---|
| `candles_20` | `window_snapshot` |
| `selected_bar` | `window_snapshot` |
| `event_summary` | `nearby_event_summary` |
| `manual_region` | `window_snapshot` |
| `recent_messages` | `recent_messages` |
| `session_summary` | `memory_summary` |

说明：

- `kind` 继续保留当前工程用途。
- `source_kind` 是治理和 UI 分类，不是替换现有 `kind`。

### `scope` 的保守默认

| 条件 | 推荐 scope |
|---|---|
| `ephemeral=true` 且未显式长期保留 | `request` |
| `ephemeral=false` | `session` |
| `pinned=true` 但只是当前会话固定 | `session` |
| 用户明确标记“仅本交易日保留” | `trading_day` |
| 用户明确标记“跨日长期保留” | `manual_global` |

关键规则：

- `pinned=true` 不等于 `manual_global`
- `manual_global` 必须有明确 UI 行为，不允许靠推断

## 4.5 Prompt Trace Block Summary

### 推荐扩展位置

- `src/atas_market_structure/models/_workbench_prompt_traces.py`
  - `PromptTraceBlockSummary`

### 需要补的字段

- `block_version`
- `source_kind`
- `scope`
- `editable`
- `selected`
- `pinned`

### 原因

`PromptTrace` 必须回答：

- 这次回答用了哪些 block
- 每个 block 是哪个版本
- 哪些是 pinned
- 哪些是只读系统块

如果这些信息只存在 PromptBlock 当前快照里，而不写进 trace，那么后续 block 被编辑后，历史回复就失去可审计性。

## 4.6 Event / Nearby Context

### 稳定事实的持久化建议

| 语义 | 推荐位置 | 是否持久化 |
|---|---|---|
| `source_prompt_trace_id` | 现有顶层字段 | 是 |
| `fixed_anchor` | `EventCandidate.metadata.fixed_anchor` | 是 |
| `reply_window_anchor` 引用 | `EventCandidate.metadata.reply_window_anchor` | 可选，是 |
| `presentation_class` | 不作为长期真相落库 | 否 |
| `nearby / influencing / historical` | 前端或读路径计算 | 否 |

### 计算责任建议

| 结果 | 计算位置 | 原因 |
|---|---|---|
| `nearby_event` | 前端 Nearby Context 模块 | 依赖当前可见窗口 |
| `influencing_event` | 前端 Nearby Context 模块 | 依赖 `activeReplyId` / visible objects |
| `historical` | 前端 Nearby Context 模块 | 同上 |
| `fixed_anchor` | 后端持久化 + 前端读取 | 是稳定用户动作 |

### Phase 0 不应该做的事

- 不要把 `nearby` 直接写入数据库
- 不要让 event service 持久化一个很快就过期的展示类别
- 不要把“当前窗口附近”当成 event 的永久属性

## 4.7 Frontend Session State

### 推荐新增到每个 session 的字段

| 字段 | 推荐默认值 | 原因 |
|---|---|---|
| `activeReplyId` | `null` | 当前聚焦答复 |
| `activeReplyWindowAnchor` | `null` | 与图表、事件、Inspector 的联动键 |
| `contextRecipeExpanded` | `false` | 二层上下文摘要展开状态 |
| `answerCardDensity` | `"compact"` | `full / compact / skim` |
| `lastContextVersion` | `null` | 供 Change Inspector 和 stale 提示使用 |

### 推荐新增到 root `state` 的字段

| 字段 | 推荐默认值 | 原因 |
|---|---|---|
| `changeInspector.open` | `false` | 右侧 Inspector 默认折叠 |
| `changeInspector.mode` | `"semantic"` | 只支持语义 diff，不做原始文本 diff |
| `changeInspector.baselineReplyId` | `null` | 对比基线 |
| `changeInspector.compareReplyId` | `null` | 当前对比目标 |
| `changeInspector.pinned` | `false` | 是否钉住 |

### 为什么 `activeReplyId` 放 session，不放 root

因为当前 workbench 支持多 session / 多 thread。  
如果 `activeReplyId` 放 root：

- 切 thread 时会丢当前阅读焦点
- 容易把 A 会话的 active reply 错挂到 B 会话事件或图上对象

session 级更安全，也更符合“每个会话各自保留阅读位置”的预期。

## 4.8 Frontend DOM / Module Mapping

### 建议新增的 DOM 锚点

在 `replay_workbench.html` 中新增最小锚点，并在 `replay_workbench_dom.js` 注册：

- `aiAnswerWorkspace`
- `nearbyContextDock`
- `contextRecipePanel`
- `changeInspectorPanel`
- `changeInspectorToggle`
- `changeInspectorCloseButton`

### 模块归属建议

| 模块 | 责任 |
|---|---|
| `replay_workbench_ai_threads.js` | session orchestration、消息加载、轻量调度 |
| `replay_workbench_answer_cards.js` | structured answer card 渲染与交互 |
| `replay_workbench_nearby_context.js` | nearby / influencing / fixed anchor 分组 |
| `replay_workbench_context_recipe.js` | context recipe 摘要与展开 |
| `replay_workbench_change_inspector.js` | 默认折叠的语义对比面板 |
| `replay_workbench_event_panel.js` | Phase 0-1 作为 legacy facade，逐步退场 |

### Phase 0 必改前端函数

#### `mapServerMessage()`

当前问题：

- 会重新组装 `meta`
- 后端新增的 `message.meta.workbench_ui` 会被覆盖

Phase 0 目标：

- 先保留服务端原始 `message.meta`
- 再把本地兼容字段 merge 进去
- 绝不能反过来把服务端新字段覆盖掉

#### `replacePendingAssistantMessage()`

当前问题：

- 流式替换时只 merge 局部 meta

Phase 0 目标：

- 支持完整透传 `meta.workbench_ui`
- 不因一次流式 patch 就把 `activeReplyId` / `activeReplyWindowAnchor` 清掉

#### `normalizePromptBlock()`

当前问题：

- 虽然保留了 `...raw`，但治理字段没有显式投影

Phase 0 目标：

- 显式暴露：
  - `blockVersion`
  - `sourceKind`
  - `scope`
  - `editable`

这样前端 UI 不需要到处从 `full_payload.block_meta` 自己扒字段。

---

## 5. 推荐的 Phase 0 改动顺序

## 5.1 Step A: 先打通后端 additive metadata，不改可见 UI

优先文件：

- `src/atas_market_structure/models/_chat.py`
- `src/atas_market_structure/models/_workbench_prompt_traces.py`
- `src/atas_market_structure/workbench_chat_service.py`
- `src/atas_market_structure/workbench_prompt_trace_service.py`

目标：

- `ChatMessage.meta` 可以承载 `workbench_ui`
- assistant reply 能输出 `response_payload.workbench_ui`
- prompt trace 能记录 `context_version` 和 block version refs

## 5.2 Step B: 再修前端接收层，不做布局替换

优先文件：

- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_state.js`

目标：

- 前端不再丢服务端 metadata
- session 新增 `activeReplyId` 等状态
- 保持当前窗口与 thread 状态不重置

## 5.3 Step C: 最后再加隐藏 DOM 锚点

优先文件：

- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench_dom.js`

目标：

- 只加挂载点和 toggle，不立刻大改布局
- 为 Phase 1 的 answer cards / nearby context / inspector 做铺垫

---

## 6. 兼容与降级规则

## 6.1 Legacy message

如果 assistant message 没有 `meta.workbench_ui`：

- 继续显示
- 走 legacy bubble / basic card
- 不参与 Change Inspector
- nearby context 只做弱绑定

## 6.2 Legacy prompt block

如果 block 没有 `full_payload.block_meta`：

- `block_version = 1`
- `editable = false`
- `scope = "request"` 当 `ephemeral=true`
- `scope = "session"` 当 `ephemeral=false`
- `source_kind` 从 `kind` 做保守映射

## 6.3 Legacy event candidate

如果 event 没有 `metadata.fixed_anchor`：

- 默认 `false`
- 仍可基于时间窗口显示
- 不应自动升级为跨日锚点

## 6.4 Local storage

如果老 session 没有新状态字段：

- `activeReplyId = null`
- `activeReplyWindowAnchor = null`
- `contextRecipeExpanded = false`
- `answerCardDensity = "compact"`

禁止因为字段缺失而触发：

- 视口重置
- thread 重建
- mounted reply 清空

---

## 7. Phase 0 需要覆盖的测试

当前最相关的已有测试：

- `tests/test_workbench_prompt_trace_service.py`
- `tests/test_app_chat_routes.py`
- `tests/test_chat_backend_e2e.py`
- `tests/test_contract_schema_versions.py`

Phase 0 真实实现时建议补的断言：

1. `assistant_message.meta.workbench_ui` 能从 reply route 返回。
2. `PromptTraceBlockSummary` 能返回 `block_version`、`selected`、`pinned`。
3. `context_version` 在 trace 与 assistant message 上一致。
4. legacy message 缺少 `meta` 时不会破坏现有路由。
5. 前端映射函数不会覆盖服务端 `meta.workbench_ui`。

---

## 8. 这一阶段明确不做什么

- 不把 `nearby / influencing` 写进数据库。
- 不把 Change Inspector 提前做成可见主功能。
- 不在 Phase 0 里重写整个 `replay_workbench.html` 布局。
- 不把 Prompt Block 元数据直接提升为 SQLite 新列。
- 不让 AI 进入识别主路径。

---

## 9. 建议的 Phase 0 代码触点清单

### 后端

- `src/atas_market_structure/models/_chat.py`
  - `ChatMessage` 增加 additive `meta`
  - `PromptBlock` 增加 additive 顶层治理字段
- `src/atas_market_structure/models/_workbench_prompt_traces.py`
  - `PromptTraceBlockSummary` 增加版本/治理字段
- `src/atas_market_structure/workbench_chat_service.py`
  - 在 reply finalize 时写 `response_payload.workbench_ui`
  - `_message_model()` 投影 `meta`
- `src/atas_market_structure/workbench_prompt_trace_service.py`
  - 记录 `context_version`
  - 记录 `request_snapshot.ui_context.chart_visible_window`
  - 记录 block version refs

### 前端

- `src/atas_market_structure/static/replay_workbench_state.js`
  - session state 增加 active reply / context recipe / density
  - root state 增加 `changeInspector`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
  - 保留 server meta
  - 增加 active reply 选择与保位
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
  - prompt block 显式投影治理字段
  - reply 请求附带 `extra_context.ui_context.chart_visible_window`
- `src/atas_market_structure/static/replay_workbench_dom.js`
  - 注册新挂载点

---

## 10. 最后的判断

Phase 0 最重要的不是“先画一个新 UI”，而是先把三条线接成同一套语义：

1. `assistant reply`
2. `prompt trace / context recipe`
3. `event candidate / nearby context`

当前仓库基础其实已经够用了：

- chat 有 payload 容器
- prompt trace 有 snapshot / metadata
- event candidate 有 metadata 和 trace link
- state 有 chartView 和 viewport preserve

真正缺的是：

- 不丢字段的投影层
- session 级 active reply 状态
- prompt block version / governance 的统一落点
- 对“哪些该持久化、哪些只能现算”的边界约束

把这几件事先冻结，再进入 Phase 1 的布局和结构化答复改造，风险会明显更低。
