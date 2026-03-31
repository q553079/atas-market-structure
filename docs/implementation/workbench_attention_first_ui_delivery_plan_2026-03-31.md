# Replay Workbench Attention-First UI Delivery Plan

## Goal

把 `docs/workbench/replay_workbench_attention_first_ui_v1.md` 从方向文档落成一组可执行、可验收、可回滚的实施阶段，逐步把 replay workbench 从“多面板堆叠”改成“主图 + 结构化答复 + 附近上下文 + 第三层追踪”的注意力优先工作台。

## Scope

- 冻结并落实 replay workbench UI 需要的术语、状态和 additive metadata。
- 收敛首屏布局，只保留主路径所需的主要模块。
- 将 AI 回复从聊天气泡升级为结构化答复卡。
- 将事件流改造成 `Nearby Context Dock`。
- 将 `Context Recipe`、Prompt 治理和 `Prompt Trace` 提升为可查、可控、可回滚的二级/三级能力。
- 在结构化回复稳定之后，再引入默认折叠的 `Change Inspector`。
- 最后处理增量渲染、视图保位和动效稳定性。

## Non-goals

- 不改 recognition pipeline。
- 不让 AI 进入在线识别主路径。
- 不扩展 V1 ontology。
- 不把本项目改造成通用量化平台或执行引擎。
- 不在本计划内引入新生产依赖。

## Files Expected To Change

- `PLANS.md`
- `docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_phase0_codex_prompt_pack_2026-03-31.md`
- `docs/workbench/replay_workbench_attention_first_ui_v1.md`
- `src/atas_market_structure/models/_schema_versions.py`
- `src/atas_market_structure/models/_chat.py`
- `src/atas_market_structure/models/_workbench_prompt_traces.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/workbench_chat_service.py`
- `src/atas_market_structure/workbench_event_service.py`
- `src/atas_market_structure/workbench_prompt_trace_service.py`
- `src/atas_market_structure/app_routes/_workbench_routes.py`
- `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
- `src/atas_market_structure/static/replay_workbench_prompt_trace_panel.js`
- `src/atas_market_structure/static/replay_workbench_answer_cards.js`
- `src/atas_market_structure/static/replay_workbench_nearby_context.js`
- `src/atas_market_structure/static/replay_workbench_context_recipe.js`
- `src/atas_market_structure/static/replay_workbench_change_inspector.js`
- `tests/test_app_chat_routes.py`
- `tests/test_chat_backend_e2e.py`
- `tests/test_contract_schema_versions.py`
- `tests/test_workbench_prompt_trace_service.py`

## Invariants To Preserve

- Recognition pipeline stays untouched:
  - `observation -> feature_slice -> regime_posterior -> event_hypotheses -> memory_anchors -> belief_state -> event_episode -> episode_evaluation -> tuning_recommendation`
- AI remains outside the online deterministic recognition path.
- All new payload fields are additive and backward compatible.
- Existing route contracts, enum values, degraded mode names, and schema-version semantics are not silently renamed.
- Raw persisted event/chat/prompt-trace history remains auditable.
- Existing chart viewport should not reset except when:
  - user changes `symbol`
  - user changes `timeframe`
  - user explicitly requests reset
- New business logic should not be added back into giant compatibility shells once extracted.

## Frontend Split Rule

The current workbench frontend has several large files. This plan must reduce further growth before adding major new behavior.

- `replay_workbench.html`
  - layout shell only
- `replay_workbench.css`
  - shared tokens and compatibility styles only
- `replay_workbench_ai_threads.js`
  - session/thread orchestration only
- `replay_workbench_event_panel.js`
  - legacy event-panel compatibility only until nearby-context extraction completes

New UI logic should go into focused modules instead:

- `replay_workbench_answer_cards.js`
- `replay_workbench_nearby_context.js`
- `replay_workbench_context_recipe.js`
- `replay_workbench_change_inspector.js`

## Additive Contracts To Freeze In Phase 0

### Reply metadata

Every assistant reply intended for the structured workbench UI should eventually expose additive metadata fields:

- `reply_window`
- `reply_window_anchor`
- `reply_session_date`
- `alignment_state`
- `assertion_level`
- `stale_state`
- `object_count`
- `context_version`
- `source_event_ids`
- `source_object_ids`

### Prompt block metadata

Prompt-context items should expose additive metadata fields:

- `block_id`
- `block_version`
- `source_kind`
- `scope`
- `editable`
- `pinned`

### Event metadata

Nearby-context rendering should be able to distinguish:

- `nearby_event`
- `influencing_event`
- `fixed_anchor`
- `source_prompt_trace_id`

## Delivery Strategy

## Phase 0: Freeze Terms, State, And Contracts

### Outcome

Create one shared semantic layer for viewport, reply, context, and diff behavior before changing visible UI.

Primary spec artifact:

- `docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md`
- `docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md`

### Backend work

- Define additive reply metadata in chat-service output.
- Define prompt block version/scope/editability metadata.
- Define nearby/influencing event flags or enough source metadata to derive them consistently.
- Ensure Prompt Trace can resolve concrete `block_version` values.
- Freeze exact field placement across `request_payload`, `response_payload`, `snapshot`, `metadata`, and `full_payload`.

### Frontend work

- Add state holders for:
  - `chart_visible_window`
  - `active_reply_id`
  - `active_reply_window_anchor`
  - `context_version`
- Ensure server-sent `message.meta.workbench_ui` survives client normalization instead of being overwritten by local fallback meta.
- Do not change primary layout yet.

### Exit criteria

- Same reply/event/context object means the same thing in frontend and backend.
- `reply_window_anchor` is stable and comparable.
- `assertion_level` rules are frozen.
- Phase 0 mapping doc identifies exact code touchpoints and compatibility defaults for every additive field.

## Phase 1: Reshape The Surface

### Outcome

Reduce the primary workbench surface to:

- `Chart Workspace`
- `Input Composer`
- `AI Workspace`
- `Nearby Context Dock`

### Frontend work

- Move low-frequency panels behind drawers or secondary toggles.
- Keep Prompt Trace and tuning/debug in third-layer surfaces.
- Make the user’s first action obvious without reading the whole screen.

### Constraints

- No major animation work yet.
- Do not introduce new business logic into the giant files unless it is facade-only wiring.

### Exit criteria

- Default first screen has at most four long-lived modules.
- Event AI / reply extraction / prompt internals are no longer competing with the main answer path on first render.

## Phase 2: Structured Answer Cards And Cautious Output

### Outcome

Assistant replies become structured workbench cards instead of generic chat bubbles.

### Frontend work

- Implement `Full / Compact / Skim`.
- Promote `结论 / 时间 / 对象 / 风险` into stable card sections.
- Add visible `assertion_level`.
- Render `失效条件` and `不确定性` according to the cautious-output rules.

### Backend work

- Emit additive structured metadata needed by the card shell.
- Keep legacy message content intact for compatibility and auditing.

### Exit criteria

- Strong conclusions cannot render without visible invalidation conditions.
- `高不确定` and `上下文不足` cannot look like confident trade calls.

## Phase 3: Nearby Context Dock And Window Binding

### Outcome

The current event stream column becomes a window-local context dock instead of a permanent parallel workflow.

### Frontend work

- Replace the current long event list with grouped nearby-context sections:
  - `刚发生`
  - `仍在影响当前窗口`
  - `固定锚点`
- Bind reply cards, chart objects, and nearby-context rows through `reply_window_anchor`.
- Surface `stale_state`.

### Backend work

- Provide enough event metadata to consistently decide nearby vs influencing vs fixed anchor.

### Exit criteria

- Old events leave the front-stage when they are no longer nearby or influencing.
- Dragging the chart window can rehydrate appropriate nearby items without mixing today/yesterday semantics.

## Phase 4: Context Recipe, Prompt Governance, And Trace

### Outcome

AI context becomes both visible and governable.

### Frontend work

- Add `Context Recipe` summary strip and expanded view.
- Distinguish read-only vs editable prompt blocks.
- Allow version-aware inspection and rollback for editable context.

### Backend work

- Expose `block_version`, `scope`, `editable`, and source-kind metadata.
- Extend Prompt Trace so it can answer “which exact block version did this reply use?”

### Exit criteria

- User can inspect current context composition without opening raw debug data.
- User can tell whether a reply used current or outdated pinned context.

## Phase 5: Change Inspector

### Outcome

Add a Codex-like, default-collapsed inspector that explains semantic changes between comparable replies.

### Frontend work

- Implement `Collapsed / Peek / Expanded`.
- Limit comparisons to compatible replies sharing `reply_window_anchor` semantics.
- Keep `Change Inspector` folded by default.

### Backend work

- No full-text diff support.
- Only additive metadata required for semantic comparisons.

### Exit criteria

- The inspector answers “what changed?” without becoming a noisy text-diff viewer.
- It never steals the default reading path from the main answer card.

## Phase 6: Incremental Rendering, Motion, And Stability

### Outcome

Make the new surface feel stable under live updates and dense reading.

### Frontend work

- Replace full-list `innerHTML` rewrites with keyed or targeted updates where practical.
- Preserve scroll, hover, selection, and focus on single-item updates.
- Add limited, meaningful transitions for:
  - card entry
  - full/compact collapse
  - inspector open/close

### Exit criteria

- Single-message or single-event updates do not visibly disrupt the user’s current reading or cursor focus.

## Dependency Order

Do not change this order:

1. Freeze semantics and additive contracts.
2. Reduce surface and create the answer-card path.
3. Bind nearby context and viewport semantics.
4. Make context governable and traceable.
5. Add semantic-diff inspection.
6. Optimize rendering and motion.

## Testing Plan

### During planning / contract freeze

- Review additive payload examples for reply, context block, and nearby event semantics.
- Confirm no existing route contract or enum was silently renamed.

### During implementation

- `python -m pytest tests\\test_app_chat_routes.py tests\\test_chat_backend_e2e.py tests\\test_workbench_prompt_trace_service.py tests\\test_contract_schema_versions.py -q`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_nearby_context.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`

### Manual acceptance checks

- Reply generation does not reset viewport.
- Nearby-context item count stays bounded in normal reading mode.
- Cross-day anchors are visibly distinguished from ephemeral context.
- `上下文不足` replies cannot render as strong trade calls.
- `Change Inspector` is collapsed by default.

## Rollback Notes

- Roll back by phase, not by broad rewrite.
- If a phase fails:
  - keep additive metadata fields in place
  - stop wiring the new frontend module
  - fall back to the prior compatibility surface
- Do not delete stored prompt traces, chat rows, or additive event metadata merely because a UI phase is rolled back.
