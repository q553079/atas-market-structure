# Replay Workbench Attention-First UI Structure Correction

## Goal

对齐 attention-first 设计文档在首屏结构上的前三个最高优先级偏差：

- 去掉首屏独立事件列，让 Nearby Context 回到 AI 主阅读路径
- 收敛首屏主动作和长期常驻模块
- 让 AI Workspace 从线程中心更接近结构化答复中心

## Scope

- 只改 replay workbench 前端的 layout、默认可见性、阅读顺序和兼容编排。
- 保留现有事件面板、答复卡、Context Recipe、Change Inspector 的 contract 与交互能力。
- 允许新增 focused frontend module 或 focused shell region，但不把新业务逻辑塞回 giant facade files。

## Files Expected To Change

- `PLANS.md`
- `docs/implementation/workbench_attention_first_ui_structure_correction_2026-03-31.md`
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_answer_cards.js`
- `tests/playwright_replay_ui_fix.spec.js`
- `tests/playwright_workbench_event_interaction.spec.js`
- `tests/playwright_event_structured_priority.spec.js`

## Invariants To Preserve

- Deterministic recognition pipeline、V1 ontology、K 线后端生成语义、live-tail 数据治理语义保持不变。
- 不改 event backend contracts，不改 `nearby / influencing / fixed_anchor / historical` 语义。
- 不改 `activeReplyId`、`activeReplyWindowAnchor`、legacy message compatibility、render stability、scroll/focus preservation。
- Change Inspector 继续默认折叠，Prompt Trace 继续第三层，不新增生产依赖。

## Migration / Compatibility Strategy

- 顶层去掉独立事件列，但保留 `eventStreamPanel` / `eventStreamList` / history shell / hover-select-pin-mount 现有能力，只调整容器层级和默认可见性。
- 让 `nearbyContextDock` 变成 AI 工作区里的真实 dock shell，承接当前回答摘要与事件列表，而不是继续保留一个总结 skeleton 加一个独立中列。
- 把 active reply 提升到专门答复位；线程保留，但默认降级为后续阅读层。
- 高频但次要的 chart / composer / session 动作下沉到折叠区或次级入口，避免删除既有功能。

## Tests To Run

- `python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_event_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py tests\\test_workbench_prompt_trace_service.py tests\\test_app_chat_routes.py -q`
- `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_dom.js`
- `npx playwright test "tests/playwright_replay_ui_fix.spec.js" "tests/playwright_workbench_event_interaction.spec.js" "tests/playwright_event_structured_priority.spec.js"`

## Rollback Notes

- 恢复顶层 chart / event / AI 三列布局，把 `eventStreamPanel` 放回旧位置。
- 恢复线程里的 active reply 主位，移除独立答复位和首屏动作收敛 shell。
- 保留所有 additive DOM id、前端状态和后端事件/答复数据，不做任何数据迁移或清理。
