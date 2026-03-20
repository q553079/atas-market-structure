# Replay Workbench AI 聊天工作区前端实现拆解文档

> 目标：基于当前项目已有前端结构，给出一份可直接指导开发的实现拆解方案。
>
> 本文档聚焦：
> - 对应当前 `static/*.js / html / css` 文件的改造方向
> - 右侧 AI 聊天工作区的组件拆分与状态拆分
> - 多会话、多品种隔离、Prompt 装配、流式输出、回复上图能力的前端落地步骤
> - P0 / P1 / P2 分阶段任务清单

---

# 1. 文档适用范围

本拆解文档基于当前项目中已出现的前端文件命名与职责，重点参考以下文件：

- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_session_memory.js`
- `src/atas_market_structure/static/replay_workbench_model_switcher.js`
- `src/atas_market_structure/static/replay_workbench_chart_overlays.js`
- `src/atas_market_structure/static/replay_workbench_annotation_panel.js`
- `src/atas_market_structure/static/replay_workbench_annotation_popover.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_ui_utils.js`

说明：
- 本文档不强制你切换框架，默认继续采用当前原生 JS 模块式拆分方式
- 本文档强调“逐步重构”，而不是要求一次性推翻现有结构

---

# 2. 当前前端改造目标

前端需要把右侧 AI 区从“普通聊天框”升级成以下能力集合：

1. **消息流主区最大化**
2. **多会话切换，像微信一样自然**
3. **不同品种会话隔离**
4. **新会话默认空白，不自动带上下文**
5. **Prompt 装配器可见、可勾选、可预览**
6. **AI 回复支持流式输出**
7. **AI 回复支持回复级上图 / 仅本条 / 叠加 / 替换**
8. **图表对象能回跳原消息**
9. **每会话独立草稿、模型、已挂载回复、滚动位置**

---

# 3. 推荐前端模块职责映射

基于你当前文件结构，建议这样分工。

---

## 3.1 `replay_workbench.html`

职责：
- 调整右侧 AI 工作区 DOM 结构
- 为消息流优先布局提供更清晰的容器层级

建议新增 / 重构区域：

```text
.ai-chat-workspace
├── .ai-chat-header
├── .ai-session-sidebar         （若本阶段实现双栏）
├── .ai-chat-main
│   ├── .ai-context-strip
│   ├── .ai-thread-view
│   ├── .ai-mounted-reply-strip
│   ├── .ai-prompt-selection-bar
│   ├── .ai-prompt-assembler-panel
│   └── .ai-chat-composer
```

### 最低要求
即使暂时不做左侧 sidebar，也至少要把现有右栏拆成：
- 头部
- 上下文压缩条
- 消息流主区
- Prompt 条
- 输入区

---

## 3.2 `replay_workbench.css`

职责：
- 实现“消息流优先”的整体布局
- 压缩顶部区域，放大消息区
- 支持消息流独立滚动
- 支持流式消息样式、回复卡样式、mounted reply strip 样式、prompt block 样式

### 重点改造方向

#### 1. 右栏主容器采用 flex column
```css
.ai-chat-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
```

#### 2. 消息流主区必须 `flex: 1`
```css
.ai-thread-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
```

#### 3. 输入区固定在底部
```css
.ai-chat-composer {
  flex: 0 0 auto;
}
```

#### 4. Prompt 装配器默认压缩成一行
#### 5. AI 回复卡宽度比普通 IM 更宽
#### 6. 顶部摘要条单行压缩显示

---

## 3.3 `replay_workbench_state.js`

职责：
- 承载所有新的前端状态结构
- 定义 session、message、prompt blocks、mounted replies、streaming 状态

建议新增主状态结构：

```js
state.aiChat = {
  sessionsById: {},
  sessionOrder: [],
  activeSessionId: null,
  activeSymbolScopedSessionIds: {},
  messagesBySessionId: {},
  promptBlocksBySessionId: {},
  mountedReplyIdsBySessionId: {},
  scrollStateBySessionId: {},
  composerStateBySessionId: {},
  streamStateBySessionId: {},
};
```

---

## 3.4 `replay_workbench_dom.js`

职责：
- DOM 查询与缓存
- 新增 UI 节点挂载点

建议补充 DOM refs：
- chat header
- context strip
- thread view
- mounted reply strip
- prompt selection bar
- prompt assembler panel
- composer
- session sidebar（如实现）

---

## 3.5 `replay_workbench_ai_threads.js`

职责：
- 多会话管理核心模块
- 会话切换、会话新建、会话分组、会话排序、会话隔离逻辑

建议放入：
- `createChatSession()`
- `activateChatSession()`
- `createBlankSessionForSymbol()`
- `getOrCreateBlankSessionForSymbol()`
- `archiveSession()`
- `renameSession()`
- `pinSession()`
- `cloneSessionBranch()`

### 关键规则
#### 切换品种时
必须调用：
- `getOrCreateBlankSessionForSymbol(symbol, contractId)`

而不是沿用旧会话。

---

## 3.6 `replay_workbench_ai_chat.js`

职责：
- 消息发送
- 消息渲染
- 流式输出
- AI 回复卡交互
- Prompt 装配器交互

建议放入：
- `renderChatThread(sessionId)`
- `renderAiReplyCard(message)`
- `renderUserMessageCard(message)`
- `sendChatMessage(sessionId)`
- `startStreamingReply(sessionId, requestPayload)`
- `appendStreamingToken(messageId, delta)`
- `finalizeStreamingMessage(messageId, payload)`
- `stopStreamingMessage(messageId)`
- `regenerateMessage(messageId)`

### 这里是最核心的文件之一
它负责把“聊天体验”真正做顺滑。

---

## 3.7 `replay_workbench_session_memory.js`

职责：
- 会话摘要展示
- Session Memory 拉取与刷新
- 模型切换前 handoff 预览

建议放入：
- `refreshSessionMemory(sessionId)`
- `renderContextStrip(sessionId)`
- `renderSessionMemoryPreview(memory)`
- `buildVisibleHandoffPreview(sessionId, mode)`

---

## 3.8 `replay_workbench_model_switcher.js`

职责：
- 模型切换 UI
- handoff 模式控制

建议补充：
- `question_only`
- `summary_only`
- `summary_plus_recent_3`

并把切换后系统提示插入消息流。

---

## 3.9 `replay_workbench_chart_overlays.js`

职责：
- 响应“某条回复上图”的操作
- 控制对象显示 / 隐藏 / 聚焦

建议补充：
- `mountReplyObjects(messageId, mode)`
- `unmountReplyObjects(messageId)`
- `focusReplyObjects(messageId)`
- `replaceMountedReplyObjects(messageId)`
- `syncMountedReplyStrip(sessionId)`

---

## 3.10 `replay_workbench_annotation_panel.js`

职责：
- 标记管理器升级
- 支持按回复筛选
- 支持按会话筛选

建议增加一层：
- 会话
- 回复
- 对象类型
- 对象明细

---

## 3.11 `replay_workbench_annotation_popover.js`

职责：
- 图上对象点击后弹出来源卡片
- 支持回跳原消息

建议补充：
- `jumpToSourceMessage(messageId)`
- `highlightSourceMessage(messageId)`
- `showReplySourcePopover(annotation)`

---

## 3.12 `replay_workbench_bootstrap.js`

职责：
- 初始化顺序编排
- SSE 事件监听初始化
- 页面首次恢复状态

建议保证启动顺序：
1. 初始化 state
2. 初始化 DOM refs
3. 恢复 sessions
4. 恢复 active session
5. 渲染 thread
6. 绑定 composer / toolbar / prompt assembler
7. 绑定 chart annotation backlink
8. 初始化流式事件控制器

---

# 4. 前端状态拆分建议

---

## 4.1 Session 级状态

每个 session 建议保留：

```js
{
  sessionId,
  title,
  symbol,
  contractId,
  timeframe,
  windowRange,
  activeModel,
  pinned,
  unreadCount,
  draftText,
  draftAttachments,
  selectedPromptBlockIds,
  pinnedContextBlockIds,
  mountedReplyIds,
  activePlanId,
  scrollOffset,
  memorySummary,
}
```

---

## 4.2 Message 级状态

```js
{
  messageId,
  sessionId,
  role,
  content,
  status,
  replyTitle,
  model,
  annotations,
  planCards,
  mountedToChart,
  mountedObjectIds,
  isKeyConclusion,
}
```

---

## 4.3 Prompt Block 级状态

```js
{
  blockId,
  sessionId,
  symbol,
  contractId,
  kind,
  title,
  previewText,
  fullPayloadLoaded,
  selected,
  pinned,
  ephemeral,
}
```

说明：
- 前端一般不必一直持有完整 payload，可按需加载“原始发送内容”

---

## 4.4 Streaming 级状态

```js
{
  sessionId,
  activeMessageId,
  controller,
  status, // idle / streaming / interrupted / failed
  autoScrollEnabled,
}
```

---

# 5. HTML 结构改造建议

## 5.1 右栏最小改造版

如果你不想一次性重做侧栏，可先做“单栏强化版”：

```text
.ai-chat-panel
├── .ai-chat-header
├── .ai-context-strip
├── .ai-thread-view
├── .ai-mounted-reply-strip
├── .ai-prompt-selection-bar
├── .ai-prompt-assembler-panel (collapsed by default)
└── .ai-chat-composer
```

这是 P0 最现实的改造路径。

---

## 5.2 右栏完整升级版

后续可升级为：

```text
.ai-chat-workspace
├── .ai-session-sidebar
└── .ai-chat-main
    ├── .ai-chat-header
    ├── .ai-context-strip
    ├── .ai-thread-view
    ├── .ai-mounted-reply-strip
    ├── .ai-prompt-selection-bar
    ├── .ai-prompt-assembler-panel
    └── .ai-chat-composer
```

---

# 6. CSS 实现重点

## 6.1 消息流优先
必须满足：
- thread view 独立滚动
- 顶部/底部固定区尽量压缩
- 右侧 AI 区第一视觉焦点是消息流

## 6.2 AI 回复卡样式
建议：
- 更宽
- 分段
- 支持“流式中”状态样式
- 支持对象 checklist
- 支持 hover 操作按钮

## 6.3 Mounted reply strip
建议轻量显示：
- tag 形式
- 支持关闭某条 mounted reply
- 支持“清空”

## 6.4 Prompt 装配器
建议两态：
- 收起：一行摘要
- 展开：块级 checklist

---

# 7. 消息流实现建议

## 7.1 渲染模型
建议按 session 渲染 message list：

```js
renderChatThread(sessionId) {
  const messages = state.aiChat.messagesBySessionId[sessionId] || [];
  // 清空 thread
  // 按顺序渲染 user / assistant cards
}
```

---

## 7.2 AI 回复卡能力
每条 AI 回复至少要有：
- 消息标题
- 流式状态
- 正文
- 对象列表
- 操作按钮

### 操作按钮最低要求
- `[上图]`
- `[仅本条]`
- `[查看图表]`

### 第二阶段再补
- `[叠加]`
- `[替换]`
- `[提取计划卡]`
- `[重新生成]`

---

## 7.3 自动吸底逻辑
建议规则：
- 用户在底部附近时，streaming 自动滚动到底部
- 用户手动上滑时，暂停自动吸底
- 给出“新回复更新中 [回到底部]”提示

---

# 8. 流式输出前端实现建议

## 8.1 推荐实现方式
用 `fetch + ReadableStream` 或 EventSource（取决于后端返回方式）处理 SSE。

## 8.2 前端流式处理流程

1. 用户点击发送
2. 插入用户消息
3. 插入 AI 占位消息，状态 `pending`
4. 连接 SSE
5. 收到 `message_start` -> 更新 AI 消息 id
6. 收到 `token` -> append 文本
7. 收到 `annotation_patch` -> 渲染对象 checklist
8. 收到 `plan_card` -> 更新计划卡区域
9. 收到 `message_end` -> 状态改 completed
10. 刷新 memory/context strip

---

## 8.3 需要单独封装的函数
建议封装：
- `openChatStream(sessionId, payload)`
- `handleChatStreamEvent(event)`
- `applyTokenDelta(messageId, delta)`
- `applyAnnotationPatch(messageId, annotations)`
- `applyPlanCards(messageId, planCards)`
- `finishStreamingMessage(messageId)`
- `failStreamingMessage(messageId, error)`

---

# 9. Prompt 装配器前端实现建议

## 9.1 最小可用能力
P0 先做到：
- 显示本次选中了哪些 block
- 可删除某个 block
- 可展开查看摘要
- 发送时仅提交选中 block ids

## 9.2 第二阶段能力
- 查看原始发送内容
- block pin 到本会话
- block 过期提示
- block scope 不一致错误提示

---

## 9.3 交互规则
### 新会话
- prompt bar 初始为空
- 不自动勾选当前行情

### 快捷分析按钮触发时
例如点击“最近20K”
- 请求后端 build 一个 `candles_20` block
- 自动加入已选 block
- 在 prompt bar 中可见

---

# 10. 多会话与多品种隔离的前端实现建议

## 10.1 切换品种
切换品种时必须调用：
- `getOrCreateBlankSessionForSymbol(symbol, contractId)`

前端不要把旧 session 的：
- draft
- selected blocks
- mounted replies
- memory summary
- active plan
带入新 symbol session。

---

## 10.2 会话切换时恢复内容
切换 session 时恢复：
- thread
- scroll position
- draft text
- attachments
- selected prompt blocks
- mounted reply strip
- context strip
- active model

---

## 10.3 会话侧栏（第二阶段）
若后续做 sidebar，建议支持：
- 搜索
- 置顶
- 草稿中标识
- 未读数
- 按 symbol 分组

---

# 11. 回复上图前端实现建议

## 11.1 回复级挂载状态
每条 AI 回复需记录：
- 是否已 mounted
- mounted 的对象 ids
- mounted mode

## 11.2 最小功能
P0 先实现：
- `[上图]`
- `[仅本条]`
- mounted reply strip 同步

## 11.3 第二阶段
- `[叠加]`
- `[替换]`
- 对象级勾选显示
- 图上对象回跳消息

---

# 12. 图表对象回跳消息实现建议

## 12.1 入口
在 annotation popover 中增加：
- 来源会话
- 来源回复
- 查看原消息

## 12.2 交互效果
点击后：
1. 激活对应 session
2. 渲染 thread
3. 定位到 source message
4. 高亮数秒
5. 展开消息对象区域

---

# 13. 与现有文件的推荐改造顺序

这是最重要的落地顺序建议。

## 第一批（先稳定右栏基础结构）
1. `replay_workbench.html`
2. `replay_workbench.css`
3. `replay_workbench_dom.js`
4. `replay_workbench_state.js`

目标：
- 先把容器结构和状态承载能力准备好

---

## 第二批（做消息流与多会话基础）
5. `replay_workbench_ai_threads.js`
6. `replay_workbench_ai_chat.js`

目标：
- 完成 session 切换、会话空白创建、消息渲染、消息发送

---

## 第三批（做 Prompt 与 Session Memory）
7. `replay_workbench_session_memory.js`
8. `replay_workbench_model_switcher.js`

目标：
- 完成上下文条、Prompt 装配器、handoff 预览

---

## 第四批（做图表联动）
9. `replay_workbench_chart_overlays.js`
10. `replay_workbench_annotation_panel.js`
11. `replay_workbench_annotation_popover.js`

目标：
- 完成回复上图、回复筛选、回跳消息

---

## 第五批（启动编排）
12. `replay_workbench_bootstrap.js`

目标：
- 把所有模块初始化串起来

---

# 14. P0 / P1 / P2 任务拆解

## P0（必须先做）

### 布局与容器
- [ ] 把右栏改成消息流优先布局
- [ ] 新增 context strip
- [ ] 新增 prompt selection bar
- [ ] 保证 composer 固定、thread 独立滚动

### 状态与会话
- [ ] 在 state 中加入 session/message/prompt block/stream 状态
- [ ] 支持新建空白 session
- [ ] 切换品种时创建该品种空白 session
- [ ] 每 session 独立保存草稿

### 消息流
- [ ] 渲染 user/assistant message cards
- [ ] 支持 AI 占位消息
- [ ] 支持流式 token 追加
- [ ] 支持 streaming/completed/failed 状态

### Prompt 装配
- [ ] 显示本次发送 block 摘要
- [ ] 支持添加/移除 block
- [ ] 默认不自动附带当前行情

### 回复上图
- [ ] 每条 AI 回复支持“上图”
- [ ] 每条 AI 回复支持“仅本条”
- [ ] mounted reply strip 显示当前已挂载回复

---

## P1（第二阶段）
- [ ] AI 回复对象 checklist
- [ ] Prompt assembler 展开态
- [ ] block pin 到本会话
- [ ] 图上 annotation 回跳原消息
- [ ] 标记管理器按回复筛选
- [ ] 模型切换 handoff 预览
- [ ] 停止生成 / 重新生成

---

## P2（增强体验）
- [ ] 左侧 session sidebar
- [ ] 会话搜索
- [ ] 会话按 symbol 分组
- [ ] 会话分支复制
- [ ] 未读数/草稿提示/pinned
- [ ] 回复叠加/替换显示
- [ ] 回复对象差异对比

---

# 15. 给前端实现者的最终说明

这次前端改造的重点，不是“在现有聊天框上多加几个按钮”，而是完成三件大事：

## 第一件：重新分配右栏空间
- 消息流最大化
- 其他模块全部压缩/折叠/让位

## 第二件：建立清晰的 session state
- 不同品种隔离
- 不同聊天隔离
- 不同请求的 prompt 选择隔离

## 第三件：让 AI 回复成为图表协作单元
- 回复可上图
- 图上可回跳消息
- 回复级 mounted state 清晰可见

如果严格按本拆解文档推进，你当前的前端结构不需要推倒重来，也能逐步进化成：

**一个消息流优先、会话隔离清晰、Prompt 可见可控、支持流式输出与回复上图的专业交易 AI 聊天工作区。**
