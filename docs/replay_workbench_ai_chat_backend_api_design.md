# Replay Workbench AI 聊天工作区后端 API / SSE / Session 数据结构设计文档

> 目标：为 Replay Workbench 的右侧 AI 聊天工作区提供一套可直接落地的后端设计方案，支持：
> - 多会话聊天
> - 多品种隔离
> - Prompt 可见化装配
> - AI 流式输出
> - 回复与图表标记联动
> - 会话记忆与模型切换交接
>
> 本文档面向：
> - Python 后端开发
> - 前端对接工程师
> - 负责 AI 网关 / 模型编排的实现者

---

# 1. 设计目标

后端必须支撑以下前端体验：

1. **多聊天会话并存**
   - 每个聊天窗口独立保存消息、草稿、上下文块、挂载回复、模型偏好

2. **不同品种硬隔离**
   - NQ 会话与 ES 会话绝不自动混用上下文
   - 切换品种时前端会打开一个新的空白会话，后端需天然支持这一隔离模型

3. **Prompt 可见化装配**
   - 前端展示摘要版 Prompt block
   - 后端发送完整版 block payload 给模型

4. **AI 流式输出**
   - 文本 token 实时流回前端
   - 结束后再落结构化对象和计划卡

5. **回复级图表对象挂载**
   - 每条 AI 回复都可派生 annotations / plan cards
   - 前端可控制某条回复是否挂到图表

6. **会话级记忆与模型切换交接**
   - 支持 session memory summary
   - 支持 handoff packet 给新模型

---

# 2. 架构总览

推荐拆成以下后端子模块：

```text
ReplayWorkbenchAiBackend
├── SessionStore
├── MessageStore
├── PromptBlockBuilder
├── ChatRequestAssembler
├── AiGatewayClient
├── StreamingResponseService
├── AnnotationExtractionService
├── PlanCardExtractionService
├── SessionMemoryEngine
├── ModelHandoffService
└── AnnotationMountStore
```

## 2.1 模块职责

### `SessionStore`
管理会话元信息：
- 会话创建
- 会话查询
- 会话归档
- 当前模型
- 当前草稿
- 当前品种 / 合约 / 周期

### `MessageStore`
管理消息：
- 用户消息
- AI 消息
- 流式中的临时 buffer
- 消息状态
- 回复附带的 annotations / plan cards

### `PromptBlockBuilder`
负责构造 prompt blocks：
- candles_20
- market_3h
- event_summary
- screenshot
- selected_bar
- manual_region
- current_plan
- session_summary

### `ChatRequestAssembler`
把前端选中的 block ids 装配成最终模型请求。

### `AiGatewayClient`
对接模型服务：
- 标准请求
- 流式请求
- 模型切换

### `StreamingResponseService`
把模型 token 流转换成 SSE 事件流。

### `AnnotationExtractionService`
从 AI 回复中提取结构化标记对象。

### `PlanCardExtractionService`
从 AI 回复中提取结构化计划卡。

### `SessionMemoryEngine`
生成 / 更新会话摘要。

### `ModelHandoffService`
生成模型切换交接包。

### `AnnotationMountStore`
记录哪条回复当前被挂载到图表。

---

# 3. 核心数据模型

---

## 3.1 ChatSession

每个聊天窗口一个 `ChatSession`。

```json
{
  "session_id": "sess_nq_20260320_001",
  "workspace_id": "replay_main",
  "title": "回踩做多",
  "symbol": "NQ",
  "contract_id": "NQM2026",
  "timeframe": "1m",
  "window_range": {
    "start": "2026-03-20T09:30:00Z",
    "end": "2026-03-20T16:00:00Z"
  },
  "active_model": "deepseek-chat",
  "status": "active",
  "draft_text": "",
  "draft_attachments": [],
  "selected_prompt_block_ids": [],
  "pinned_context_block_ids": [],
  "mounted_reply_ids": [],
  "active_plan_id": null,
  "memory_summary_id": "mem_001",
  "unread_count": 0,
  "scroll_offset": 0,
  "pinned": false,
  "created_at": "2026-03-20T10:01:02Z",
  "updated_at": "2026-03-20T10:03:20Z"
}
```

### 关键规则
- `symbol` 与 `contract_id` 是硬隔离字段
- 一个 session 只能属于一个品种 / 合约
- 所有 prompt block、message、annotation 必须可追溯到 session

---

## 3.2 ChatMessage

```json
{
  "message_id": "msg_001",
  "session_id": "sess_nq_20260320_001",
  "role": "assistant",
  "content": "这里不追多，优先等 24852-24848 回踩确认。",
  "status": "completed",
  "reply_title": "回踩做多逻辑",
  "stream_buffer": "",
  "model": "deepseek-chat",
  "annotations": ["ann_101", "ann_102"],
  "plan_cards": ["plan_001"],
  "mounted_to_chart": true,
  "mounted_object_ids": ["ann_101", "plan_001"],
  "is_key_conclusion": true,
  "created_at": "2026-03-20T10:05:00Z",
  "updated_at": "2026-03-20T10:05:30Z"
}
```

### `status` 枚举建议
#### 用户消息
- `draft`
- `queued`
- `sending`
- `sent`
- `failed`

#### AI 消息
- `pending`
- `streaming`
- `completed`
- `interrupted`
- `failed`
- `regenerated`

---

## 3.3 PromptBlock

用于实现“前端可见、后端完整版”的上下文块。

```json
{
  "block_id": "pb_20k_001",
  "session_id": "sess_nq_20260320_001",
  "symbol": "NQ",
  "contract_id": "NQM2026",
  "kind": "candles_20",
  "title": "最近20根K线",
  "preview_text": "09:30-09:49，高24866，低24841，当前24858，反弹后进入阻力前震荡。",
  "full_payload": {
    "bars": []
  },
  "selected_by_default": false,
  "pinned": false,
  "ephemeral": true,
  "created_at": "2026-03-20T10:04:00Z"
}
```

### `kind` 建议枚举
- `user_input`
- `candles_20`
- `market_3h`
- `current_window`
- `selected_bar`
- `manual_region`
- `screenshot`
- `event_summary`
- `current_plan`
- `session_summary`
- `recent_messages`
- `attachment`

### 关键规则
- 前端只展示 `preview_text`
- 后端装配请求时使用 `full_payload`
- `symbol` / `contract_id` 不一致的 block 默认不可被跨会话注入

---

## 3.4 SessionMemory

```json
{
  "memory_summary_id": "mem_001",
  "session_id": "sess_nq_20260320_001",
  "summary_version": 3,
  "active_model": "deepseek-chat",
  "symbol": "NQ",
  "contract_id": "NQM2026",
  "timeframe": "1m",
  "window_range": {
    "start": "2026-03-20T09:30:00Z",
    "end": "2026-03-20T16:00:00Z"
  },
  "user_goal_summary": "寻找高胜率回踩做多机会。",
  "market_context_summary": "价格自24800防御区反弹，当前接近24866阻力。",
  "key_zones_summary": [
    "支撑区 24840-24848 仍有效",
    "阻力区 24866-24872 首次测试"
  ],
  "active_plans_summary": [
    "计划A：回踩24852做多，止损24844，TP1 24866"
  ],
  "invalidated_plans_summary": [],
  "important_messages": ["msg_001"],
  "current_user_intent": "判断直接突破后是否能追单。",
  "latest_question": "如果接下来直接突破24866，没有回踩，还能不能追？",
  "latest_answer_summary": "不建议直接追，优先等待突破确认或二次回踩。",
  "selected_annotations": ["ann_101"],
  "last_updated_at": "2026-03-20T10:06:00Z"
}
```

---

## 3.5 Annotation

可复用你已有文档中的统一对象设计，这里强调后端落库存储字段。

```json
{
  "id": "ann_101",
  "session_id": "sess_nq_20260320_001",
  "message_id": "msg_001",
  "symbol": "NQ",
  "contract_id": "NQM2026",
  "timeframe": "1m",
  "type": "zone",
  "subtype": "support",
  "label": "支撑区 24840-24848",
  "reason": "回踩防守区",
  "start_time": "2026-03-20T10:05:00Z",
  "end_time": null,
  "expires_at": "2026-03-20T12:00:00Z",
  "status": "active",
  "priority": 80,
  "confidence": 0.78,
  "visible": true,
  "pinned": false,
  "source_kind": "replay_analysis",
  "created_at": "2026-03-20T10:05:00Z",
  "updated_at": "2026-03-20T10:05:00Z"
}
```

---

## 3.6 PlanCard

```json
{
  "plan_id": "plan_001",
  "session_id": "sess_nq_20260320_001",
  "message_id": "msg_001",
  "title": "回踩做多计划A",
  "side": "buy",
  "entry_type": "point",
  "entry_price": 24852.0,
  "stop_price": 24844.0,
  "take_profits": [24866.0, 24878.0],
  "invalidations": ["跌破24844"],
  "time_validity": "2h",
  "risk_reward": 2.1,
  "confidence": 0.78,
  "priority": 90,
  "status": "active",
  "source_kind": "replay_analysis",
  "notes": "优先等待回踩确认，不追高。"
}
```

---

# 4. API 设计

下面 API 路径仅为建议，可与你现有 `/api/replay-workbench/*` 路由风格对齐。

---

## 4.1 会话管理 API

### 4.1.1 新建会话
`POST /api/replay-workbench/chat/sessions`

#### 请求示例
```json
{
  "symbol": "NQ",
  "contract_id": "NQM2026",
  "timeframe": "1m",
  "window_range": {
    "start": "2026-03-20T09:30:00Z",
    "end": "2026-03-20T16:00:00Z"
  },
  "title": "回踩做多",
  "active_model": "deepseek-chat",
  "start_blank": true
}
```

#### 响应示例
```json
{
  "ok": true,
  "session": {}
}
```

### 关键规则
- `start_blank=true` 时，不注入任何历史消息 / 当前行情 / memory
- 切换品种时，前端应调用本接口创建新空白会话

---

### 4.1.2 获取会话列表
`GET /api/replay-workbench/chat/sessions`

支持查询参数：
- `symbol=NQ`
- `include_archived=false`
- `group_by_symbol=true`

#### 响应示例
```json
{
  "ok": true,
  "sessions": []
}
```

---

### 4.1.3 获取单会话详情
`GET /api/replay-workbench/chat/sessions/{session_id}`

返回：
- session 元信息
- draft
- selected blocks
- mounted replies
- active plan
- memory summary（可选）

---

### 4.1.4 更新会话元信息
`PATCH /api/replay-workbench/chat/sessions/{session_id}`

可更新：
- `title`
- `active_model`
- `pinned`
- `mounted_reply_ids`
- `selected_prompt_block_ids`
- `draft_text`

---

### 4.1.5 删除 / 归档会话
`POST /api/replay-workbench/chat/sessions/{session_id}/archive`

`DELETE /api/replay-workbench/chat/sessions/{session_id}`

---

## 4.2 消息 API

### 4.2.1 获取会话消息
`GET /api/replay-workbench/chat/sessions/{session_id}/messages`

支持分页：
- `before_message_id`
- `limit=50`

---

### 4.2.2 发送用户消息（非流式入口）
`POST /api/replay-workbench/chat/sessions/{session_id}/messages`

适用于：
- 仅保存用户消息
- 不立即请求模型

#### 请求示例
```json
{
  "role": "user",
  "content": "如果这里直接突破，还能不能追？",
  "attachments": [],
  "selected_block_ids": ["pb_20k_001", "pb_evt_001"]
}
```

---

## 4.3 Prompt Block API

### 4.3.1 生成候选 Prompt blocks
`POST /api/replay-workbench/chat/sessions/{session_id}/prompt-blocks/build`

#### 请求示例
```json
{
  "candidates": [
    "candles_20",
    "market_3h",
    "event_summary",
    "selected_bar",
    "manual_region",
    "current_plan"
  ]
}
```

#### 响应示例
```json
{
  "ok": true,
  "blocks": []
}
```

### 关键规则
- 这里只是生成候选，不代表本次发送一定会使用
- 前端可据此渲染可见 Prompt 装配器

---

### 4.3.2 获取某个 Prompt block 的原始内容
`GET /api/replay-workbench/chat/prompt-blocks/{block_id}`

用于“查看原始发送内容”高级预览。

---

## 4.4 流式聊天 API

### 4.4.1 发起流式 AI 回复
`POST /api/replay-workbench/chat/sessions/{session_id}/stream`

推荐返回 `text/event-stream`。

#### 请求示例
```json
{
  "user_input": "如果这里直接突破，还能不能追？",
  "selected_block_ids": ["pb_20k_001", "pb_evt_001"],
  "pinned_block_ids": [],
  "include_memory_summary": false,
  "include_recent_messages": false,
  "model": "deepseek-chat"
}
```

### 后端处理流程
1. 校验 session 是否存在
2. 校验 `selected_block_ids` 全部属于当前 session 或至少 symbol/contract 匹配
3. 保存用户消息
4. 创建 AI 占位消息，状态 `pending`
5. 装配最终模型请求
6. 调用模型流式接口
7. 边接 token 边输出 SSE
8. 完成后抽取 annotations / plan cards
9. 更新 AI 消息状态为 `completed`
10. 更新 session memory

---

### 4.4.2 停止流式生成
`POST /api/replay-workbench/chat/sessions/{session_id}/messages/{message_id}/stop`

用于停止当前 streaming。

---

### 4.4.3 重新生成某条 AI 回复
`POST /api/replay-workbench/chat/sessions/{session_id}/messages/{message_id}/regenerate`

请求中可附：
- 是否沿用原 block ids
- 是否沿用 memory summary
- 目标模型

---

## 4.5 Annotation / Plan Card API

### 4.5.1 获取会话 annotations
`GET /api/replay-workbench/chat/sessions/{session_id}/annotations`

支持筛选：
- `message_id`
- `status=active`
- `visible_only=true`

---

### 4.5.2 获取某条消息派生对象
`GET /api/replay-workbench/chat/messages/{message_id}/objects`

返回：
- annotations
- plan cards
- mounted state

---

### 4.5.3 更新回复挂载状态
`PATCH /api/replay-workbench/chat/messages/{message_id}/mount`

#### 请求示例
```json
{
  "mounted_to_chart": true,
  "mount_mode": "replace",
  "mounted_object_ids": ["ann_101", "plan_001"]
}
```

### `mount_mode` 枚举
- `append`
- `replace`
- `focus_only`

---

### 4.5.4 更新 annotation 可见状态
`PATCH /api/replay-workbench/chat/annotations/{annotation_id}`

可更新：
- `visible`
- `pinned`
- `status`

---

## 4.6 Session Memory / Handoff API

### 4.6.1 获取 session memory
`GET /api/replay-workbench/chat/sessions/{session_id}/memory`

---

### 4.6.2 强制刷新 session memory
`POST /api/replay-workbench/chat/sessions/{session_id}/memory/refresh`

触发时机：
- AI 回复后
- 计划卡生成后
- 标记状态变化后
- 用户手动要求刷新摘要

---

### 4.6.3 生成模型切换交接包
`POST /api/replay-workbench/chat/sessions/{session_id}/handoff`

#### 请求示例
```json
{
  "target_model": "gpt-4.1",
  "mode": "summary_plus_recent_3"
}
```

#### 响应示例
```json
{
  "ok": true,
  "handoff_packet": {
    "session_meta": {},
    "memory_summary": {},
    "recent_messages": [],
    "active_annotations": [],
    "active_plans": []
  }
}
```

### `mode` 枚举
- `question_only`
- `summary_only`
- `summary_plus_recent_3`

---

# 5. SSE 流式事件协议

推荐使用 SSE，而不是一开始就上 WebSocket。

---

## 5.1 事件类型一览

### `message_start`
AI 消息已创建，开始流式响应。

```text
event: message_start
data: {"session_id":"sess_001","message_id":"msg_ai_001","model":"deepseek-chat"}
```

### `message_status`
消息状态变化。

```text
event: message_status
data: {"message_id":"msg_ai_001","status":"streaming"}
```

### `token`
文本增量输出。

```text
event: token
data: {"message_id":"msg_ai_001","delta":"如果接下来直接突破24866，"}
```

### `annotation_patch`
消息结束后下发标记对象。

```text
event: annotation_patch
data: {"message_id":"msg_ai_001","annotations":[...]}
```

### `plan_card`
消息结束后下发计划卡。

```text
event: plan_card
data: {"message_id":"msg_ai_001","plan_cards":[...]}
```

### `memory_updated`
会话摘要已更新。

```text
event: memory_updated
data: {"session_id":"sess_001","memory_summary_id":"mem_002"}
```

### `message_end`
流式完成。

```text
event: message_end
data: {"message_id":"msg_ai_001","status":"completed","usage":{"input_tokens":1000,"output_tokens":260}}
```

### `error`
流式异常。

```text
event: error
data: {"message_id":"msg_ai_001","code":"MODEL_TIMEOUT","message":"model stream timeout"}
```

---

## 5.2 前端处理建议

前端收到：
- `message_start`：插入占位 AI 消息
- `token`：追加内容到当前 AI 消息
- `annotation_patch`：补充对象列表和上图能力
- `plan_card`：插入/更新计划卡 UI
- `memory_updated`：更新上下文摘要条
- `message_end`：把消息状态改为 completed

---

# 6. Prompt 装配规则

这是本方案最重要的安全边界之一。

## 6.1 默认不自动带历史
除非前端显式传：
- `include_memory_summary=true`
- `include_recent_messages=true`

否则：
- 不自动带会话摘要
- 不自动带最近轮次消息
- 不自动带当前行情

---

## 6.2 Prompt 装配顺序建议

建议后端最终 prompt 结构：

```text
[System Instructions]
[Workspace Meta]
[Session Meta]
[Selected Prompt Blocks - full payload]
[Optional Memory Summary]
[Optional Recent Messages]
[Current User Input]
```

### 说明
- 当前用户输入永远放最后
- Prompt block 顺序可保持前端选中顺序
- `memory summary` 与 `recent messages` 必须是可选注入

---

## 6.3 Block 校验规则

后端在装配前必须校验：
1. `block.session_id == current_session_id` 或至少 `symbol / contract_id` 完全一致
2. block 未过期
3. block 内容完整
4. screenshot / attachment 文件存在

若不通过，应返回可解释错误，例如：

```json
{
  "ok": false,
  "error": {
    "code": "PROMPT_BLOCK_SCOPE_MISMATCH",
    "message": "selected block belongs to another symbol/session"
  }
}
```

---

# 7. 会话隔离与品种隔离规则

## 7.1 会话隔离

后端必须保证：
- 一个 message 只能属于一个 session
- 一个 annotation 只能来源于一个 message / session
- 一个 plan card 只能来源于一个 message / session
- 一个 prompt block 默认只在所属 session 内有效

---

## 7.2 品种隔离

后端必须保证：
- `session.symbol` / `session.contract_id` 是核心隔离字段
- 所有 block / annotation / plan card / memory 记录都带上 symbol / contract_id
- 若跨品种注入，默认拒绝

---

## 7.3 切换品种时的后端预期

前端切换品种时，不应调用“沿用旧会话”的接口，而应：
1. 请求创建一个新 session
2. 指定新的 symbol / contract_id
3. `start_blank=true`

后端只需自然支持这一流程，不应自动尝试迁移旧 session 内容

---

# 8. Session Memory 更新时机

建议以下时机自动刷新 `SessionMemory`：

1. 用户发送新问题后
2. AI 回复完成后
3. 计划卡生成后
4. annotation 状态变化后
5. 用户切换模型前
6. 用户手动点击“刷新摘要”时

---

# 9. Annotation / Plan 生命周期后端职责

后端可提供基础状态更新能力，前端做可视化展示。

## 9.1 后端输入
- candles
- live tail
- existing plans
- existing zones
- trigger rules

## 9.2 后端输出
- 对象状态变化
- end_time
- hit event
- invalidation event

## 9.3 建议接口
`POST /api/replay-workbench/chat/sessions/{session_id}/lifecycle/evaluate`

#### 请求示例
```json
{
  "bars": [],
  "live_tail": {},
  "object_ids": ["ann_101", "plan_001"]
}
```

#### 响应示例
```json
{
  "ok": true,
  "transitions": [
    {
      "object_id": "plan_001",
      "from_status": "active",
      "to_status": "triggered",
      "event": "touch_entry"
    }
  ]
}
```

---

# 10. 错误处理建议

## 10.1 常见错误码
- `SESSION_NOT_FOUND`
- `MESSAGE_NOT_FOUND`
- `PROMPT_BLOCK_NOT_FOUND`
- `PROMPT_BLOCK_SCOPE_MISMATCH`
- `MODEL_NOT_AVAILABLE`
- `MODEL_STREAM_TIMEOUT`
- `STREAM_ALREADY_RUNNING`
- `ANNOTATION_NOT_FOUND`
- `PLAN_CARD_NOT_FOUND`
- `INVALID_SESSION_SYMBOL`

---

## 10.2 流式错误处理原则
- 已收到的 token 不丢
- 消息状态改为 `failed` 或 `interrupted`
- 前端保留半成品内容
- 用户可点击“继续生成”或“重新生成”

---

# 11. 持久化建议

建议以下内容持久化：

## 11.1 必须持久化
- sessions
- messages
- prompt blocks
- session memory
- annotations
- plan cards
- mounted reply state
- draft text
- draft attachments

## 11.2 可选持久化
- token 级流式 buffer
- raw model response
- prompt assembly trace
- usage metrics

---

# 12. 与现有系统的集成建议

结合你当前项目结构，建议优先放在以下方向：

- `workbench_services.py`：新增 chat session / stream orchestration
- `ai_review_services.py`：复用或扩展 AI 请求逻辑
- `repository.py`：补 session/message/prompt block 持久化
- `schemas/`：新增 chat session / stream event / prompt block schema
- `static/` 前端文件对接 SSE 与新 API

---

# 13. 开发优先级建议

## P0
1. ChatSession / ChatMessage / PromptBlock / SessionMemory 数据结构
2. 新建会话 / 查询会话 / 查询消息 API
3. Prompt block build API
4. 流式聊天 SSE API
5. 回复完成后 annotations / plan cards 落库
6. mounted reply 状态更新 API

## P1
7. session memory refresh API
8. model handoff API
9. lifecycle evaluate API
10. regenerate / stop generation API

## P2
11. usage metrics
12. raw response trace
13. SSE 断流恢复
14. 并行多模型响应

---

# 14. 给实现者的最终说明

这个后端设计的重点，不是“再加一个聊天接口”，而是要把 AI 聊天当成一个真正的会话系统来实现。

必须守住四条底线：

1. **Session 是一等对象**
   - 不是全局唯一聊天框
   - 每个 session 独立保存消息、草稿、上下文、模型、挂载回复

2. **Prompt 必须可控**
   - 前端看摘要版
   - 后端发完整版
   - 不自动偷偷塞过多上下文

3. **品种与会话必须隔离**
   - NQ、ES、CL 不串
   - 不同聊天窗不串
   - 不同请求不默认继承

4. **流式文本与结构化对象分阶段落地**
   - 先流文字
   - 再补 annotations / plan cards / memory update
   - 保证前端体验稳定

如果严格按这份文档实现，后端将能稳定支撑一个：

**多会话、多品种隔离、Prompt 可见化、回复可上图、支持 SSE 流式输出的专业交易 AI 工作台。**
