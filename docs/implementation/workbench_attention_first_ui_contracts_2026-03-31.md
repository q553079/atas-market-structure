# Replay Workbench Attention-First UI Contracts

## Goal

冻结 replay workbench 注意力优先 UI 所依赖的最小充分契约，确保前后端、状态层、Prompt Trace、EventCandidate、答复卡、Nearby Context、Change Inspector 对同一对象的理解一致。

这份文档定义的是：

- 共享术语
- additive 字段
- 推荐字段放置位置
- 向后兼容与降级规则
- 最小示例 payload

它不是视觉设计文档，也不是完整 API 文档。

## Scope

本契约覆盖以下对象：

- assistant reply / chat message
- prompt block
- event candidate
- prompt trace
- client-only UI state

不在范围：

- recognition pipeline
- deterministic event semantics
- auto-trading or execution logic

## Compatibility Policy

- 所有字段必须 additive。
- 不重命名现有 public payload 字段。
- 优先放入已有 `meta` / `metadata` 容器，而不是扩散新的顶层字段。
- 老消息、老事件、老 prompt trace 在缺少新字段时仍然有效。
- UI 必须支持“新字段缺失时的兼容降级”。

## Time Encoding Policy

所有跨前后端的时间字段统一使用：

- `ISO8601 UTC`

展示层可以按市场时区渲染，但 wire contract 不使用相对时间词，也不使用本地时区歧义格式。

## Shared Semantic Sources

### `symbol`

- 当前工作对象的合约或根符号
- 与主图所展示的 instrument 一致

### `timeframe`

- 当前工作对象的显示周期
- 使用现有 workbench 周期字符串，如 `1m`, `5m`, `15m`, `1h`

### `session_date`

- 交易日日期
- `YYYY-MM-DD`
- 由市场交易日语义决定，不等于浏览器本地自然日

### `chart_visible_window`

定义：

- 当前主图真实可见的时间区间

来源：

- 只能来自图表组件当前 visible range

规则：

- 这是唯一合法的“当前窗口”来源
- 其他模块不得自己推测当前窗口

结构：

```json
{
  "window_start": "2026-03-31T01:31:00Z",
  "window_end": "2026-03-31T02:07:00Z"
}
```

### `reply_window`

定义：

- 某条 AI 回复实际分析所依据的绝对时间区间

规则：

- 发送请求时冻结
- 回复完成后不因用户继续拖图而回写

### `reply_window_anchor`

定义：

- 一个稳定的、可比较的 reply 锚点

推荐格式：

`{symbol}|{timeframe}|{window_start}|{window_end}|{session_date}`

作用：

- 作为答复卡、图上对象、Nearby Context、Change Inspector 的共同比较键

### `active_reply`

定义：

- 当前用户正在阅读、聚焦、或与图表联动的那条 assistant reply

规则：

- 同一 `symbol + timeframe` 工作区同时只允许一条 `active_reply`

### `nearby_event`

定义：

- 事件时间落在 `chart_visible_window` 内
- 或事件虽不在可见区间内，但满足 `influencing_event`

### `influencing_event`

定义：

- 事件时间早于 `chart_visible_window.window_start`
- 且仍满足以下至少一条：
  - 被 `active_reply` 引用
  - 绑定了当前仍可见对象
  - 是用户显式固定的锚点

### `fixed_anchor`

定义：

- 用户显式固定、允许跨窗口或跨日保留的关键位、区域、上下文块或计划卡

规则：

- 没有显式固定，就不能被判定为 `fixed_anchor`

### `ephemeral_context`

定义：

- 仅对本轮或当前会话临时有效的系统生成上下文

规则：

- 默认不过夜
- 默认不参与跨日比较

## Assistant Reply Contract

### Preferred placement

推荐将新的 workbench UI 字段放在：

- `ChatMessage.meta.workbench_ui`

旧消息若没有该对象，视为 legacy message。

### Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schema_version` | string | yes | UI contract version, additive only |
| `symbol` | string | yes | reply 绑定的 symbol |
| `timeframe` | string | yes | reply 绑定的 timeframe |
| `reply_window` | object | yes | 该回复分析的绝对时间区间 |
| `reply_window_anchor` | string | yes | reply 稳定比较键 |
| `reply_session_date` | string | yes | 交易日 |
| `assertion_level` | string enum | yes | `observational` / `conditional` / `high_uncertainty` / `insufficient_context` |
| `alignment_state` | string enum | yes | `aligned` / `ambiguous` / `out_of_bounds` / `pending_confirmation` |
| `stale_state` | string enum | yes | `current_window` / `stale_window` / `cross_day_anchor` / `refresh_needed` |
| `object_count` | integer | no | 当前 reply 绑定的图上对象数 |
| `source_event_ids` | string[] | no | 当前 reply 直接引用的 event ids |
| `source_object_ids` | string[] | no | 当前 reply 生成或绑定的对象 ids |
| `context_version` | string | no | 当前 reply 使用的上下文版本摘要 |
| `cross_day_anchor_count` | integer | no | 跨日固定锚点数量 |

### Assertion level enum

- `observational`
  - 只描述结构、对象、现象
- `conditional`
  - 可以给方向判断，但必须有失效条件
- `high_uncertainty`
  - 允许总结，但必须强调不确定来源
- `insufficient_context`
  - 禁止给方向性结论，只能说明缺什么

### Alignment state enum

- `aligned`
- `ambiguous`
- `out_of_bounds`
- `pending_confirmation`

### Stale state enum

- `current_window`
  - 同 `symbol / timeframe` 且与 `chart_visible_window` 重叠比例 `>= 0.5`
- `stale_window`
  - 同 `symbol / timeframe` 但重叠比例 `< 0.5`
- `cross_day_anchor`
  - 引用了上一交易日的 `fixed_anchor`
- `refresh_needed`
  - 当前 `symbol / timeframe` 已切换，或存在更新的同范围 reply

### Required rendering rules

- `conditional`
  - UI 必须展示失效条件
- `high_uncertainty`
  - UI 必须展示不确定性
- `insufficient_context`
  - UI 禁止渲染强结论标题
  - UI 禁止渲染计划卡

### Legacy fallback

若 `meta.workbench_ui` 缺失：

- 回复仍可显示
- 但只能走 legacy chat bubble / basic card 路径
- 不参与 Change Inspector
- 不参与高可信 nearby-context 绑定

## Prompt Block Contract

### Preferred placement

Prompt block 保持当前对象结构不变，新增字段优先放在 block 自身 additive 字段上，避免二次嵌套过深。

### Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `block_id` | string | yes | 稳定唯一标识 |
| `block_version` | integer | yes | 版本号 |
| `source_kind` | string enum | yes | block 来源分类 |
| `scope` | string enum | yes | 生效范围 |
| `editable` | boolean | yes | 用户是否可编辑 |
| `pinned` | boolean | yes | 当前是否固定 |
| `author` | string | no | block 作者或来源 |
| `updated_at` | string | no | 最近更新时间 |

### `source_kind` enum

- `system_policy`
- `analysis_template`
- `window_snapshot`
- `nearby_event_summary`
- `memory_summary`
- `recent_messages`
- `user_note`
- `pinned_context`

### `scope` enum

- `request`
- `session`
- `trading_day`
- `manual_global`

### Editing rules

- `system_policy`
  - 不可编辑
- `analysis_template`
  - 不直接编辑，只切换
- `window_snapshot`
  - 不可编辑
- `nearby_event_summary`
  - 不可编辑，但必须可追溯来源
- `memory_summary`
  - 只能开关
- `recent_messages`
  - 只能开关
- `user_note`
  - 可编辑
- `pinned_context`
  - 可编辑、可固定、可回滚

### Prompt Trace linkage

每次发送请求时，trace 或请求记录至少要保留：

- `block_id`
- `block_version`
- `pinned`

否则无法回答“这条回复到底看到了哪个版本”。

## Event Candidate Presentation Contract

### Preferred placement

推荐将 workbench-specific 展示语义放在：

- `EventCandidate.metadata.presentation`

### Fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `presentation_class` | string enum | no | `nearby` / `influencing` / `historical` / `fixed_anchor` |
| `source_prompt_trace_id` | string | no | 来源 Prompt Trace |
| `source_message_id` | string | no | 来源 assistant message |
| `anchor_time` | string | no | 主锚点时间 |
| `anchor_price` | number | no | 主锚点价格 |
| `is_fixed_anchor` | boolean | no | 是否显式固定 |
| `visible_reason` | string enum | no | 当前为什么在前台显示 |

### `visible_reason` enum

- `inside_visible_window`
- `referenced_by_active_reply`
- `bound_to_visible_object`
- `user_pinned`

### Frontend rule

如果 presentation 字段缺失，前端可以退回 legacy event-stream 渲染，但不能把它误判为 `nearby` 或 `fixed_anchor`。

## Prompt Trace Contract Additions

### Required capabilities

Prompt Trace 至少要能回答：

- 这条回复用了哪些 block
- 对应 block 是哪个 version
- 哪些 block 是 pinned
- 哪些 block 是系统自动生成

### Recommended additive snapshot fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `context_version` | string | no | 本轮上下文摘要版本 |
| `context_blocks[]` | array | no | 带版本信息的上下文块列表 |
| `reply_window` | object | no | 本轮分析窗口 |
| `reply_window_anchor` | string | no | 本轮比较锚点 |

## Client-only UI State Contract

以下状态是前端私有状态，不要求后端持久化，但命名和语义必须稳定：

| State key | Type | Meaning |
|---|---|---|
| `chartVisibleWindow` | object | 当前可见时间窗口 |
| `activeReplyId` | string | 当前激活 reply |
| `activeReplyWindowAnchor` | string | 当前激活 reply anchor |
| `activeSymbol` | string | 当前 symbol |
| `activeTimeframe` | string | 当前 timeframe |
| `changeInspectorMode` | string enum | `collapsed` / `peek` / `expanded` |
| `contextRecipeExpanded` | boolean | 上下文配方展开状态 |

## Change Inspector Eligibility Rules

`Change Inspector` 不需要单独持久化全文 diff。  
它只需要一套稳定的 eligibility 规则。

允许比较的最小条件：

- 两条 reply 都有 `meta.workbench_ui`
- `symbol` 相同
- `timeframe` 相同
- 交易上下文可比较
- 至少一条 reply 不是 `insufficient_context`

推荐比较键：

1. 优先同 `reply_window_anchor`
2. 若不相同，但两个 `reply_window` 有显著重叠，可做弱比较
3. 否则不进入 Change Inspector

禁止比较：

- 不同 symbol
- 不同 timeframe
- 相距很远的旧回复
- legacy message 与结构化 reply 混比

## Minimal Example Payloads

### Assistant reply fragment

```json
{
  "message_id": "msg_123",
  "role": "assistant",
  "content": "当前结构偏延续，但失守关键位后假设失效。",
  "meta": {
    "workbench_ui": {
      "schema_version": "workbench_ui_contract_v1",
      "symbol": "NQ",
      "timeframe": "1m",
      "reply_window": {
        "window_start": "2026-03-31T01:31:00Z",
        "window_end": "2026-03-31T02:07:00Z"
      },
      "reply_window_anchor": "NQ|1m|2026-03-31T01:31:00Z|2026-03-31T02:07:00Z|2026-03-31",
      "reply_session_date": "2026-03-31",
      "assertion_level": "conditional",
      "alignment_state": "aligned",
      "stale_state": "current_window",
      "object_count": 3,
      "source_event_ids": ["evt_1", "evt_2"],
      "context_version": "ctx_v17"
    }
  }
}
```

### Prompt block fragment

```json
{
  "block_id": "blk_9",
  "block_version": 3,
  "source_kind": "pinned_context",
  "scope": "trading_day",
  "editable": true,
  "pinned": true,
  "author": "user",
  "updated_at": "2026-03-31T01:20:00Z"
}
```

### Event candidate fragment

```json
{
  "event_id": "evt_1",
  "kind": "market_event",
  "metadata": {
    "presentation": {
      "presentation_class": "influencing",
      "source_prompt_trace_id": "trace_88",
      "source_message_id": "msg_123",
      "anchor_time": "2026-03-31T01:37:00Z",
      "is_fixed_anchor": false,
      "visible_reason": "referenced_by_active_reply"
    }
  }
}
```

## Validation Rules

- `reply_window.window_start < reply_window.window_end`
- `reply_window_anchor` must be reproducible from the component fields
- `assertion_level = conditional` requires an invalidation condition in the rendered card
- `assertion_level = insufficient_context` forbids plan-card rendering
- `block_version` must be monotonic per `block_id`
- `presentation_class = fixed_anchor` requires `is_fixed_anchor = true`

## Implementation Notes

- Prefer adding one focused serializer/helper per surface instead of growing legacy bootstrap shells.
- Keep old messages and old traces renderable.
- Avoid binding UI correctness to raw LLM prose; bind it to additive structured metadata.
