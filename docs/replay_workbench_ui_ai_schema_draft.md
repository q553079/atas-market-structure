# Replay Workbench UI / AI 数据结构草案

> 目标：把 `replay_workbench_ui_ai_design.md` 中的产品设计，进一步收敛为前后端都能直接实现的数据结构草案。
>
> 说明：
> - 本文档不是最终 JSON Schema 标准文件
> - 但字段命名、对象层级、状态枚举应尽量稳定
> - 后续可直接据此生成 `schemas/` 下的正式 schema 文件

---

## 1. 设计原则

1. 所有 AI 输出必须结构化
2. 图表标记对象与聊天消息要能互相引用
3. 会话与 AI 模型切换要可追溯
4. 生命周期状态要可机读
5. 前端筛选状态要能持久化
6. 数据结构要支持多会话、多模型、多对象、多计划

---

## 2. 顶层对象关系

```text
ReplayWorkbenchState
├── workbench_context
├── sessions[]
│   ├── messages[]
│   ├── drafts
│   ├── session_memory
│   ├── plans[]
│   └── annotations[]
├── ui_state
├── filters
└── model_registry
```

---

## 3. ReplayWorkbenchState

```json
{
  "workbench_context": {},
  "sessions": [],
  "ui_state": {},
  "filters": {},
  "model_registry": {}
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| workbench_context | object | 当前工作台全局上下文 |
| sessions | array | 所有会话 |
| ui_state | object | UI 状态与布局状态 |
| filters | object | 全局过滤器状态 |
| model_registry | object | 可用 AI 模型清单 |

---

## 4. WorkbenchContext

```json
{
  "symbol": "NQ",
  "symbol_label": "纳指",
  "timeframe": "1m",
  "window_range": {
    "preset": "7d",
    "start_time": "2026-03-12T09:30:00Z",
    "end_time": "2026-03-19T09:30:00Z"
  },
  "data_status": "live",
  "last_sync_at": "2026-03-19T03:00:00Z",
  "active_session_id": "session_03",
  "active_model": "gpt-4.1",
  "chart_cursor": {
    "time": "2026-03-19T02:31:00Z",
    "price": 24852.25
  }
}
```

### 枚举建议
- `data_status`: `live | delayed | historical | disconnected`
- `timeframe`: `1m | 5m | 15m | 30m | 1h | 4h | 1d`

---

## 5. Session

```json
{
  "session_id": "session_03",
  "title": "重点区域",
  "kind": "analysis",
  "created_at": "2026-03-19T01:00:00Z",
  "updated_at": "2026-03-19T03:00:00Z",
  "pinned": true,
  "archived": false,
  "active_model": "gpt-4.1",
  "preferred_model": "gpt-4.1",
  "messages": [],
  "draft": {},
  "session_memory": {},
  "plans": [],
  "annotations": []
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| session_id | string | 会话唯一 ID |
| title | string | 会话标题 |
| kind | string | 会话类型 |
| pinned | boolean | 是否固定 |
| archived | boolean | 是否归档 |
| active_model | string | 当前该会话使用的模型 |
| preferred_model | string | 默认模型偏好 |
| messages | array | 消息列表 |
| draft | object | 当前草稿状态 |
| session_memory | object | 会话主信息摘要 |
| plans | array | 计划卡列表 |
| annotations | array | 标记对象列表 |

### kind 枚举建议
- `analysis`
- `review`
- `focus_region`
- `position_review`
- `free_chat`

---

## 6. Message

```json
{
  "message_id": "msg_0012",
  "session_id": "session_03",
  "role": "assistant",
  "model": "gpt-4.1",
  "created_at": "2026-03-19T02:31:00Z",
  "content": {
    "summary": "不追多，等待回踩 24852 附近确认。",
    "body": "当前价格接近上方阻力，直接追多风险较大，建议等待回踩确认。",
    "format": "markdown"
  },
  "attachments": [],
  "plan_refs": ["plan_a"],
  "annotation_refs": ["ann_entry_1", "ann_sl_1", "ann_tp1_1"],
  "tags": ["entry", "risk"],
  "visible_on_chart": true,
  "collapsed": false
}
```

### role 枚举
- `user`
- `assistant`
- `system`
- `tool`

---

## 7. Draft

```json
{
  "text": "如果接下来直接突破 24866，没有回踩，还能不能追？",
  "attachments": ["file_001"],
  "selected_template": {
    "analysis_type": "重点价格区域",
    "analysis_scope": "当前窗口",
    "output_style": "标准分析"
  },
  "updated_at": "2026-03-19T03:01:00Z"
}
```

---

## 8. SessionMemory

```json
{
  "summary_version": 4,
  "active_model": "gpt-4.1",
  "symbol": "NQ",
  "timeframe": "1m",
  "window_range": "最近7天",
  "user_goal_summary": "寻找高胜率回踩做多机会",
  "market_context_summary": "价格自 24800 防守区反弹，正接近上方阻力区。",
  "key_zones_summary": [
    "支撑区 24840-24848 仍有效",
    "阻力区 24866-24872 首次测试",
    "24856-24858 为无交易区"
  ],
  "active_plans_summary": [
    "回踩 24852 做多，止损 24844，TP1 24866，TP2 24878，未触发"
  ],
  "invalidated_plans_summary": [],
  "important_messages": ["msg_0010", "msg_0012"],
  "current_user_intent": "判断是否继续等待回踩，还是接受突破追单",
  "latest_question": "如果接下来直接突破 24866，没有回踩，还能不能追？",
  "latest_answer_summary": "当前不建议直接追多，优先等待回踩确认。",
  "selected_annotations": ["ann_support_1", "ann_entry_1"],
  "last_updated_at": "2026-03-19T03:02:00Z"
}
```

---

## 9. PlanCard

```json
{
  "plan_id": "plan_a",
  "session_id": "session_03",
  "message_id": "msg_0012",
  "title": "回踩做多计划",
  "side": "buy",
  "entry_type": "point",
  "entry_price": 24852.25,
  "entry_price_low": null,
  "entry_price_high": null,
  "stop_price": 24844.0,
  "take_profits": [
    {
      "level": 1,
      "price": 24866.0,
      "status": "active"
    },
    {
      "level": 2,
      "price": 24878.0,
      "status": "active"
    }
  ],
  "supporting_zones": ["ann_support_1"],
  "invalidations": [
    {
      "type": "close_below",
      "price": 24840.0,
      "reason": "支撑区失守"
    }
  ],
  "time_validity": {
    "mode": "duration",
    "minutes": 30,
    "expires_at": "2026-03-19T03:30:00Z"
  },
  "risk_reward": 1.8,
  "confidence": 0.72,
  "priority": "high",
  "status": "active",
  "source_kind": "replay_analysis",
  "notes": "不追多，等待回踩确认。",
  "annotation_refs": ["ann_entry_1", "ann_sl_1", "ann_tp1_1", "ann_tp2_1"]
}
```

### status 枚举建议
- `draft`
- `active`
- `triggered`
- `tp_hit`
- `sl_hit`
- `expired`
- `invalidated`
- `completed`
- `archived`

---

## 10. Annotation

```json
{
  "id": "ann_entry_1",
  "session_id": "session_03",
  "message_id": "msg_0012",
  "plan_id": "plan_a",
  "symbol": "NQ",
  "timeframe": "1m",
  "type": "line",
  "subtype": "entry",
  "label": "AI开多 24852.25",
  "reason": "等待回踩确认后入场",
  "start_time": "2026-03-19T02:31:00Z",
  "end_time": null,
  "expires_at": "2026-03-19T03:30:00Z",
  "price": 24852.25,
  "price_low": null,
  "price_high": null,
  "trigger_mode": "touch",
  "status": "active",
  "priority": "high",
  "confidence": 0.72,
  "visible": true,
  "pinned": false,
  "source_kind": "replay_analysis",
  "created_at": "2026-03-19T02:31:00Z",
  "updated_at": "2026-03-19T02:31:00Z",
  "style": {
    "color": "#00b894",
    "line_style": "solid",
    "line_width": 2,
    "opacity": 1
  },
  "lifecycle": {
    "terminate_on_touch": true,
    "terminate_on_time": true,
    "terminate_on_invalidation": true
  }
}
```

### type 枚举建议
- `line`
- `zone`
- `path`
- `marker`
- `plan_link`

### subtype 枚举建议
- `entry`
- `stop_loss`
- `take_profit`
- `support`
- `resistance`
- `no_trade`
- `path_arrow`
- `observation`

---

## 11. AnnotationStyle

```json
{
  "color": "#00b894",
  "line_style": "solid",
  "line_width": 2,
  "fill_color": "#00b89433",
  "opacity": 1,
  "show_label": true,
  "show_reason": false
}
```

---

## 12. AnnotationLifecycle

```json
{
  "trigger_mode": "touch",
  "activation_condition": "entry_triggered",
  "terminate_on_touch": true,
  "terminate_on_close": false,
  "terminate_on_time": true,
  "terminate_on_invalidation": true,
  "termination_reason": null
}
```

---

## 13. ModelHandoffPacket

```json
{
  "from_model": "gpt-4.1",
  "to_model": "claude-sonnet",
  "handoff_mode": "summary_plus_recent_turns",
  "session_id": "session_03",
  "workbench_context": {
    "symbol": "NQ",
    "timeframe": "1m",
    "window_range": "最近7天"
  },
  "session_memory": {},
  "recent_messages": ["msg_0011", "msg_0012", "msg_0013"],
  "active_plan_refs": ["plan_a"],
  "active_annotation_refs": ["ann_entry_1", "ann_support_1"],
  "latest_user_question": "如果接下来直接突破 24866，没有回踩，还能不能追？",
  "created_at": "2026-03-19T03:05:00Z"
}
```

### handoff_mode 枚举
- `summary_only`
- `summary_plus_recent_turns`
- `latest_question_only`

---

## 14. UIState

```json
{
  "layout": {
    "left_panel_width": 68,
    "right_panel_width": 32,
    "bottom_drawer_height": 240,
    "bottom_drawer_open": true
  },
  "chat": {
    "active_session_id": "session_03",
    "message_scroll_top": 1024,
    "input_focused": true,
    "toolbar_expanded": true,
    "attachment_bar_expanded": false
  },
  "chart": {
    "zoom_level": 1.2,
    "show_volume": true,
    "selected_bar_time": "2026-03-19T02:31:00Z",
    "selected_region": null
  },
  "ai": {
    "model_switcher_open": false,
    "annotation_panel_open": false
  }
}
```

---

## 15. FilterState

```json
{
  "session_visibility": {
    "session_01": false,
    "session_02": false,
    "session_03": true
  },
  "message_visibility": {
    "msg_0012": true,
    "msg_0013": false
  },
  "object_type_visibility": {
    "entry": true,
    "stop_loss": true,
    "take_profit": true,
    "support": true,
    "resistance": true,
    "no_trade": true,
    "path_arrow": false,
    "completed": false,
    "invalidated": false
  },
  "only_current_session": true,
  "hide_completed": true,
  "hide_invalidated": true
}
```

---

## 16. ModelRegistry

```json
{
  "available_models": [
    {
      "id": "gpt-4.1",
      "label": "GPT-4.1",
      "vendor": "openai",
      "supports_vision": true,
      "supports_long_context": true,
      "recommended_for": ["general_analysis", "plan_generation"]
    },
    {
      "id": "claude-sonnet",
      "label": "Claude Sonnet",
      "vendor": "anthropic",
      "supports_vision": true,
      "supports_long_context": true,
      "recommended_for": ["long_review", "context_handoff"]
    }
  ],
  "default_model": "gpt-4.1"
}
```

---

## 17. 关键前后端接口建议

### 17.1 获取工作台快照
`GET /api/replay-workbench/snapshot`

返回：
- `ReplayWorkbenchState`

### 17.2 发送聊天消息
`POST /api/replay-workbench/chat/send`

请求体建议：

```json
{
  "session_id": "session_03",
  "model": "gpt-4.1",
  "handoff_mode": "summary_only",
  "message": {
    "text": "这里还能追多吗？",
    "attachments": []
  },
  "analysis_template": {
    "analysis_type": "重点价格区域",
    "analysis_scope": "当前窗口",
    "output_style": "标准分析"
  }
}
```

### 17.3 切换 AI 模型
`POST /api/replay-workbench/chat/switch-model`

```json
{
  "session_id": "session_03",
  "from_model": "gpt-4.1",
  "to_model": "claude-sonnet",
  "handoff_mode": "summary_plus_recent_turns"
}
```

响应建议返回：
- 新的 `session_memory`
- 系统提示消息
- 生成的 `handoff_packet_id`

### 17.4 更新对象可见性
`POST /api/replay-workbench/annotations/filter`

### 17.5 确认/隐藏某个标记
`POST /api/replay-workbench/annotations/update`

### 17.6 生命周期推进
`POST /api/replay-workbench/plans/evaluate`

---

## 18. 落地优先级建议

### P0
- `Session`
- `Message`
- `Draft`
- `PlanCard`
- `Annotation`
- `FilterState`
- `SessionMemory`
- `ModelHandoffPacket`

### P1
- `UIState`
- `ModelRegistry`
- `AnnotationStyle`
- `AnnotationLifecycle`

### P2
- 正式 JSON Schema 文件
- 后端对象校验
- 前端 TypeScript 类型自动生成

---

## 19. 给实现者的最终建议

如果只能先做最小可用版，优先保证下面 4 件事：

1. 一条 AI 回复能产出：`Message + PlanCard + Annotation[]`
2. 图表能根据 `Annotation.status` 正确渲染和终止
3. 会话切换与 AI 切换不丢 `Draft + SessionMemory`
4. 标记管理器能根据 `FilterState` 稳定筛选对象

只要这 4 件事先站住，这个系统后续就能持续扩展。