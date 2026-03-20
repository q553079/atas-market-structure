# Replay Workbench UI 缺口开发任务清单

基于以下文档与当前前端实现对照整理：
- `docs/replay_workbench_ui_ai_design.md`
- `docs/replay_workbench_ui_ai_schema_draft.md`
- `docs/replay_workbench_ui_interaction_state_table.md`
- `src/atas_market_structure/static/replay_workbench*.{html,js,css}`

---

## P0（优先立即补齐）

### P0-1 会话条 + 固定输入框 + 草稿恢复闭环
**目标**
- 确保每会话草稿、附件、分析模板、模型偏好切换后完整恢复。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 持久化 `activeAiThreadId / draft / attachments / analysisTemplate / activeModel`
- 切会话时恢复输入框、附件区、分析模板、会话摘要
- 新会话创建后继承合理默认值

### P0-2 AI 计划卡结构化输出增强
**目标**
- 让 Plan Card 更接近设计文档：可上图、只看此计划、查看图表、固定顶部、复制摘要、加入复盘。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench.css`

**改造点**
- 补齐 plan card 动作回调
- 支持 pinnedPlanId 持久化
- 支持复制摘要与加入复盘

### P0-3 AI 标记对象模型收敛
**目标**
- 收敛统一基础字段，保证 plan / annotation / session 之间关系稳定。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 确保 annotation 包含：`id/session_id/message_id/plan_id/symbol/timeframe/type/label/reason/start_time/end_time/expires_at/status/priority/confidence/visible/pinned/source_kind`
- 收敛 plan card 规范字段

### P0-4 生命周期与终止规则基础版补强
**目标**
- 保持现有生命周期推进逻辑，并补齐最基本的展示与摘要同步。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_chart_overlays.js`

**改造点**
- entry/sl/tp/zone 状态更新后刷新 session memory
- 后续补充终止态视觉（绿点/红叉/灰点/灰叉）

### P0-5 标记管理器基础版补齐
**目标**
- 在当前按会话/消息/对象类型筛选基础上，补足对象级动作。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench.css`

**改造点**
- 对象列表支持：定位、来源、显示/隐藏、仅显示此对象、固定/取消固定、删除
- 支持对象详情弹层

### P0-6 AI 切换 + Session Core Memory 摘要交接
**目标**
- 切换模型时保留主信息、关键对象、活动计划与最近问答。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`

**改造点**
- 保留 `summary/recent_3/minimal` 三种模式
- 切换后插入系统消息
- 自动刷新 handoff summary preview

### P0-7 顶部更多菜单与状态闭环
**目标**
- 补齐查看缓存、重置缓存、导出设置、最近同步时间。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench.css`

**改造点**
- `headerMoreMenu` 开合
- `lookupCache / invalidateCache / exportSettings`
- `statusSyncChip` 更新

### P0-8 附件预览与长文折叠增强
**目标**
- 提升聊天工作区可用性。

**涉及文件**
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench.css`

**改造点**
- 图片缩略图
- 删除单附件
- 长文折叠/展开

---

## P1（第二阶段）

### P1-1 按消息展开到对象级筛选
**文件**
- `replay_workbench_bootstrap.js`
- `replay_workbench.html`
- `replay_workbench.css`

### P1-2 图表点击对象详情卡 → 再回跳原消息
**文件**
- `replay_workbench_bootstrap.js`
- `replay_workbench.html`
- `replay_workbench.css`

### P1-3 聊天点击高亮图表增强
**文件**
- `replay_workbench_ai_threads.js`
- `replay_workbench_bootstrap.js`

### P1-4 多级 TP/SL 状态同步正规化
**文件**
- `replay_workbench_bootstrap.js`
- `replay_workbench_ai_chat.js`

### P1-5 抽屉区沉淀复盘材料
**文件**
- `replay_workbench_bootstrap.js`
- `replay_workbench_ai_threads.js`

### P1-6 AI 切换补充“重新发送完整上下文”
**文件**
- `replay_workbench_bootstrap.js`
- `replay_workbench_ai_chat.js`

---

## P2（增强体验）

### P2-1 会话对比视图
### P2-2 路径箭头剧本模式
### P2-3 当前主计划固定卡
### P2-4 场景化默认布局
### P2-5 历史归档与建议来源区分
### P2-6 数据库驱动品种搜索、最近使用、收藏置顶

---

## 建议的落地顺序
1. 先完成 P0-7 / P0-8 / P0-5（最直接提升 UI 可用性）
2. 再完成 P0-2 / P0-6（计划卡和 AI 交接）
3. 再完成 P0-3 / P0-4（对象模型和生命周期正规化）
4. 最后推进 P1 / P2
