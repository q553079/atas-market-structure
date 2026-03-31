# Replay Workbench Attention-First UI Phase 0 Codex Prompt Pack

状态：执行提示包  
日期：2026-03-31  
用途：把 Phase 0 从设计/映射文档转成可直接交给实现型 Codex 的任务切片

依赖：

- `docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md`

---

## 1. 使用方式

这份文档不是再讨论方向，而是给出可执行切片。  
每个切片都遵守同一组仓库约束：

- 不改 recognition pipeline
- 不让 AI 进入 deterministic recognition 主路径
- 不扩展 ontology
- 不新增生产依赖
- 所有字段 additive
- 不静默改 public route contract / enum / degraded mode
- 视口行为不能退化，非换合约/换周期/显式 reset 不得重置

推荐执行顺序：

1. Prompt A：后端 additive metadata 打通
2. Prompt B：前端接收层与状态保真
3. Prompt C：Phase 0 DOM 锚点和隐藏骨架

不要跳步。  
Prompt B 依赖 Prompt A。  
Prompt C 依赖 Prompt B 至少把状态字段接住。

---

## 2. Prompt A

## 2.1 目标

把 Phase 0 需要的 additive metadata 先在后端打通，但不改首屏布局。

重点结果：

- `ChatMessage.meta.workbench_ui` 可返回
- `PromptTraceBlockSummary` 可返回 block 版本/治理信息
- `PromptBlock` 可返回 block 版本/治理信息
- `PromptTrace.snapshot / metadata` 可持久化 `context_version`
- assistant message `response_payload.workbench_ui` 成为 reply metadata 真相来源

## 2.2 Files To Change

- `src/atas_market_structure/models/_chat.py`
- `src/atas_market_structure/models/_workbench_prompt_traces.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/workbench_chat_service.py`
- `src/atas_market_structure/workbench_prompt_trace_service.py`
- `tests/test_contract_schema_versions.py`
- `tests/test_workbench_prompt_trace_service.py`
- `tests/test_chat_backend_e2e.py`
- `tests/test_app_chat_routes.py`

## 2.3 Files Not To Change

- recognition pipeline 相关模块
- `src/atas_market_structure/workbench_event_service.py`
- `src/atas_market_structure/app_routes/_workbench_routes.py`
- 前端静态文件
- repository schema / SQLite 表结构

## 2.4 实现要求

1. 给 `ChatMessage` 增加 additive `meta: dict[str, Any] = Field(default_factory=dict, ...)`。
2. 给 `PromptBlock` 增加 additive 字段：
   - `block_version`
   - `source_kind`
   - `scope`
   - `editable`
   - `author`
   - `updated_at`
3. 给 `PromptTraceBlockSummary` 增加 additive 字段：
   - `block_version`
   - `source_kind`
   - `scope`
   - `editable`
   - `selected`
   - `pinned`
4. 不新增 SQLite 列。Prompt block 治理字段先落：
   - `StoredPromptBlock.full_payload["block_meta"]`
5. reply metadata 真相落：
   - `StoredChatMessage.response_payload["workbench_ui"]`
6. 在 `_message_model()` 中把以下内容投影到 `ChatMessage.meta`：
   - attachments
   - parent message id
   - prompt trace id
   - `response_payload.workbench_ui`
7. 在 prompt trace 中补：
   - `context_version`
   - block version refs
   - 允许后续前端/后端从 `snapshot` 或 `metadata` 查到 exact block version
8. 不要把 `stale_state` 当长期真相硬编码存储；如果要返回，只能是初始值或缺省值，不能替代前端实时派生。
9. 不要把 `nearby / influencing / historical` 写回数据库。

## 2.5 建议实现策略

- 在 `workbench_chat_service.py` 内部新增轻量 helper：
  - `_derive_prompt_block_meta(...)`
  - `_build_context_version(...)`
  - `_build_reply_workbench_ui_meta(...)`
- 在 `workbench_prompt_trace_service.py` 中：
  - 从 `StoredPromptBlock.full_payload.block_meta` 读取治理字段
  - 缺失时按 mapping doc 的兼容默认填充
- `context_version` 可先用稳定 JSON + hash 的保守实现
- 老消息缺少 `response_payload["workbench_ui"]` 时，`ChatMessage.meta.workbench_ui` 应为缺失而不是伪造复杂对象

## 2.6 验收标准

- chat reply route 返回的 `assistant_message` 带有 `meta.workbench_ui`
- prompt trace route 返回的 `prompt_block_summaries` 带版本/治理字段
- prompt block build route 返回的 block 带版本/治理字段
- 旧测试仍然通过，新增字段不破坏老 payload
- 不需要前端参与，后端单测与 route 测试即可验证

## 2.7 Tests To Run

- `python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_prompt_trace_service.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py -q`

## 2.8 可直接复制的 Prompt

```text
你在 D:\docker\atas-market-structure 工作。

任务：实现 Replay Workbench attention-first UI 的 Phase 0 后端 additive metadata，不改布局，不改 recognition pipeline，不新增生产依赖。

必须先遵守 AGENTS.md 的输出格式，先给出：
1. files to change
2. files not to change
3. plan
4. risks
5. tests to run

只允许修改这些文件：
- src/atas_market_structure/models/_chat.py
- src/atas_market_structure/models/_workbench_prompt_traces.py
- src/atas_market_structure/models/__init__.py
- src/atas_market_structure/workbench_chat_service.py
- src/atas_market_structure/workbench_prompt_trace_service.py
- tests/test_contract_schema_versions.py
- tests/test_workbench_prompt_trace_service.py
- tests/test_chat_backend_e2e.py
- tests/test_app_chat_routes.py

不要修改这些文件：
- 任何 recognition pipeline 模块
- src/atas_market_structure/workbench_event_service.py
- src/atas_market_structure/app_routes/_workbench_routes.py
- 任何前端静态文件
- 任何 repository schema / SQLite 表结构

实施要求：
- 给 ChatMessage 增加 additive meta 字段。
- 给 PromptBlock 增加 additive 字段：block_version/source_kind/scope/editable/author/updated_at。
- 给 PromptTraceBlockSummary 增加 additive 字段：block_version/source_kind/scope/editable/selected/pinned。
- 不新增 SQLite 列。Prompt block 治理字段先放进 StoredPromptBlock.full_payload["block_meta"]。
- assistant reply metadata 真相放进 StoredChatMessage.response_payload["workbench_ui"]。
- 在 _message_model() 中把 attachments / parent_message_id / prompt_trace_id / response_payload.workbench_ui 投影到 ChatMessage.meta。
- 在 prompt trace snapshot 或 metadata 中记录 context_version 和 exact block version refs。
- 不要把 stale_state 当长期真相硬编码存储。
- 不要把 nearby / influencing / historical 写回数据库。
- 所有字段必须 additive，不得重命名现有 public 字段。

参考文档：
- docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md
- docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md
- docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md

完成后必须运行：
- python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_prompt_trace_service.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py -q

最后输出：
- 改了什么
- 哪些 contract 发生 additive 扩展
- 测试结果
- 剩余风险
```

---

## 3. Prompt B

## 3.1 目标

让前端真正接住 Phase 0 后端 metadata，并在不改首屏布局的前提下，建立 reply 聚焦和 inspector 基础状态。

重点结果：

- 服务端 `message.meta.workbench_ui` 不再被前端覆盖掉
- session 级新增 `activeReplyId` / `activeReplyWindowAnchor`
- root state 新增 `changeInspector`
- reply 请求能附带 `extra_context.ui_context.chart_visible_window`
- prompt block 的治理字段能在前端被显式读取

## 3.2 Files To Change

- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `tests/playwright_replay_ui_fix.spec.js`

## 3.3 Files Not To Change

- 后端 Python 模块
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
- 图表绘制和 K 线生成链路

## 3.4 实现要求

1. 在 `createDefaultSession()` 和 session normalize 流程里新增：
   - `activeReplyId`
   - `activeReplyWindowAnchor`
   - `contextRecipeExpanded`
   - `answerCardDensity`
   - `lastContextVersion`
2. 在 root state 新增：
   - `changeInspector.open`
   - `changeInspector.mode`
   - `changeInspector.baselineReplyId`
   - `changeInspector.compareReplyId`
   - `changeInspector.pinned`
3. 修复 `mapServerMessage()`：
   - 保留服务端原始 `message.meta`
   - 再 merge 本地兼容字段
   - 不能反向覆盖 `meta.workbench_ui`
4. 修复 `replacePendingAssistantMessage()`：
   - 能完整 merge `meta.workbench_ui`
   - 不要因为一次 streaming patch 清掉 reply 聚焦状态
5. 更新 `normalizePromptBlock()`：
   - 显式投影 `blockVersion/sourceKind/scope/editable`
   - 兼容 `full_payload.block_meta`
6. 发送 reply 时，把当前图表窗口注入：
   - `extra_context.ui_context.chart_visible_window`
7. 不改主布局，不改 event panel 结构，不新增新可见面板。

## 3.5 建议实现策略

- `mapServerMessage()` 应先拿 `serverMeta = message.meta || {}`
- 本地兼容字段只做 additive merge
- 新 session 字段必须有 local storage 兼容默认，防止老缓存崩溃
- `chart_visible_window` 只能从 `state.chartView` 或既有图表窗口辅助函数取
- 不要从 `session.windowRange` 反推精确窗口

## 3.6 验收标准

- 后端已返回 `assistant_message.meta.workbench_ui` 时，前端 session message 中仍然存在
- 刷新/同步后，新增状态字段不会导致 thread 状态或视口莫名清空
- prompt block 前端对象上可以直接读到治理字段
- 发送消息时 request payload 带 `extra_context.ui_context.chart_visible_window`
- 不改变当前首屏布局与主要交互

## 3.7 Tests To Run

- `node --check src\\atas_market_structure\\static\\replay_workbench_state.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`

## 3.8 可直接复制的 Prompt

```text
你在 D:\docker\atas-market-structure 工作。

任务：实现 Replay Workbench attention-first UI 的 Phase 0 前端接收层与状态保真，不改主布局，不改 K 线和图表业务逻辑。

必须先遵守 AGENTS.md 的输出格式，先给出：
1. files to change
2. files not to change
3. plan
4. risks
5. tests to run

只允许修改这些文件：
- src/atas_market_structure/static/replay_workbench_state.js
- src/atas_market_structure/static/replay_workbench_ai_threads.js
- src/atas_market_structure/static/replay_workbench_ai_chat.js
- tests/playwright_replay_ui_fix.spec.js

不要修改这些文件：
- 任何后端 Python 文件
- src/atas_market_structure/static/replay_workbench.html
- src/atas_market_structure/static/replay_workbench_dom.js
- src/atas_market_structure/static/replay_workbench_event_panel.js
- 图表绘制和 K 线生成链路

实施要求：
- 在 session state 中新增 activeReplyId / activeReplyWindowAnchor / contextRecipeExpanded / answerCardDensity / lastContextVersion。
- 在 root state 中新增 changeInspector.open/mode/baselineReplyId/compareReplyId/pinned。
- 修复 replay_workbench_ai_threads.js 的 mapServerMessage()，必须保留服务端原始 message.meta，再 merge 本地兼容字段，不能覆盖 meta.workbench_ui。
- 修复 replacePendingAssistantMessage()，完整 merge meta.workbench_ui，不要清掉 reply 聚焦状态。
- 更新 normalizePromptBlock()，显式投影 blockVersion/sourceKind/scope/editable，并兼容 full_payload.block_meta。
- 发送 reply 时，把当前图表窗口放进 extra_context.ui_context.chart_visible_window。
- 不改主布局，不新增新可见面板。

参考文档：
- docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md
- docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md

完成后必须运行：
- node --check src\\atas_market_structure\\static\\replay_workbench_state.js
- node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js
- node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js

最后输出：
- 改了什么
- 哪些状态字段和 message/block 结构发生 additive 扩展
- 校验结果
- 剩余风险
```

---

## 4. Prompt C

## 4.1 目标

在不切换主界面的前提下，把 Phase 1 需要的 DOM 锚点和折叠面板骨架预埋进去。

重点结果：

- 为 `AI Answer Workspace`
- `Nearby Context Dock`
- `Context Recipe`
- `Change Inspector`

建立最小挂载点和 DOM refs，但默认不替换现有主路径。

## 4.2 Files To Change

- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench.css`

## 4.3 Files Not To Change

- 所有后端 Python 文件
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

## 4.4 实现要求

1. 只加最小骨架元素和 class，不切换当前默认功能入口。
2. 在 HTML 中增加以下锚点：
   - `aiAnswerWorkspace`
   - `nearbyContextDock`
   - `contextRecipePanel`
   - `changeInspectorPanel`
   - `changeInspectorToggle`
   - `changeInspectorCloseButton`
3. 在 DOM 工厂中注册这些元素。
4. CSS 只增加隐藏骨架、默认折叠与兼容样式。
5. 默认行为：
   - 不影响当前 event panel
   - 不影响当前 chat thread
   - 不改变首屏布局宽度分配
6. `changeInspectorPanel` 默认折叠。

## 4.5 验收标准

- 页面仍可正常加载
- 当前 UI 视觉和主要布局不被强行切换
- 新 DOM refs 可供下一阶段模块挂载
- CSS 不引入大面积空白或布局抖动

## 4.6 Tests To Run

- `node --check src\\atas_market_structure\\static\\replay_workbench_dom.js`

## 4.7 可直接复制的 Prompt

```text
你在 D:\docker\atas-market-structure 工作。

任务：为 Replay Workbench attention-first UI Phase 1 预埋 DOM 锚点和折叠骨架，但不切换当前主布局和主功能路径。

必须先遵守 AGENTS.md 的输出格式，先给出：
1. files to change
2. files not to change
3. plan
4. risks
5. tests to run

只允许修改这些文件：
- src/atas_market_structure/static/replay_workbench.html
- src/atas_market_structure/static/replay_workbench_dom.js
- src/atas_market_structure/static/replay_workbench.css

不要修改这些文件：
- 所有后端 Python 文件
- src/atas_market_structure/static/replay_workbench_ai_threads.js
- src/atas_market_structure/static/replay_workbench_event_panel.js
- src/atas_market_structure/static/replay_workbench_bootstrap.js

实施要求：
- 只加最小骨架和 DOM refs，不切换当前默认 UI 流程。
- 在 HTML 中增加 aiAnswerWorkspace / nearbyContextDock / contextRecipePanel / changeInspectorPanel / changeInspectorToggle / changeInspectorCloseButton。
- 在 replay_workbench_dom.js 中注册这些 refs。
- CSS 只增加隐藏骨架、默认折叠和兼容样式。
- changeInspectorPanel 默认折叠。
- 不允许改出新的大面积空白，不允许破坏当前布局宽度分配。

参考文档：
- docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md
- docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md

完成后必须运行：
- node --check src\\atas_market_structure\\static\\replay_workbench_dom.js

最后输出：
- 增加了哪些 DOM 锚点
- 兼容策略
- 校验结果
- 剩余风险
```

---

## 5. 我现在的判断

到这一步，已经可以让实现型 Codex 开始干活了。  
原因不是“文档很多”，而是最关键的三件事已经收敛：

1. 字段落点已经冻结
2. 执行顺序已经冻结
3. 每个切片的可改文件、禁改文件、测试和验收已经冻结

也就是说，接下来再卡住，问题大概率不会是“方向不清楚”，而会是具体实现细节。

---

## 6. 推荐实际开工顺序

先跑 Prompt A。  
只有 A 完成，前端才有真实 metadata 可接。  
然后跑 Prompt B。  
最后跑 Prompt C。

不要直接跳到 answer card 或 change inspector 的可见 UI。  
否则还是会回到老问题：表面上有了新壳子，底层 reply / context / event 语义仍然是散的。
