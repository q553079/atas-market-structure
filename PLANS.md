# PLANS.md

Use this file as an index for significant refactor or delivery plans.

## When to add a plan
Create a plan before changes such as:
- giant-file splits
- schema or contract changes
- repository/persistence refactors
- route reorganizations
- degraded-mode changes
- replay/projection rebuild changes

## Minimum plan sections
- Goal
- Scope
- Files expected to change
- Invariants to preserve
- Migration / compatibility strategy
- Tests to run
- Rollback notes

## Rule
Implementation should follow the approved plan instead of improvising broad rewrites.

## 2026-03-27 GC History Timestamp Trust Guardrail
- Goal
  Prevent corrupted historical K-line rebuilds by excluding low-confidence local-time fallback payloads from chart persistence, raw-mirror fallback reads, and replay snapshot history selection.
- Scope
  Add a focused history-payload trust helper, wire it into adapter history ingestion, chart backfill, raw-mirror fallback loading, and replay history-payload collection, then clean/rebuild affected GC chart data from trusted history only.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/history_payload_quality.py`
  `src/atas_market_structure/adapter_services.py`
  `src/atas_market_structure/chart_candle_service.py`
  `src/atas_market_structure/workbench_replay_service.py`
  `tests/test_new_modules.py`
  `tests/test_timezone_capture.py`
  `tests/test_app_workbench_routes.py`
- Invariants to preserve
  ClickHouse remains the primary K-line read store.
  SQLite remains append-only and auditable for stored ingestions.
  Existing adapter routes, replay builder contracts, and degraded mode names remain unchanged.
  AI stays outside the online deterministic recognition path.
- Migration / compatibility strategy
  Keep storing the original ingestion payloads in SQLite for auditability, but stop letting untrusted history timestamps reach chart-facing paths.
  Treat `python_guardrail_forced_utc_from_original_bar_time_text` and UTC/forced UTC payloads as trusted.
  Treat low-confidence local fallback payloads as audit-only and skip them for chart rebuild/read paths.
- Tests to run
  `python -m pytest tests\test_new_modules.py tests\test_timezone_capture.py tests\test_app_workbench_routes.py -q`
  `node --check src\atas_market_structure\static\replay_workbench_replay_loader.js`
  `node --check src\atas_market_structure\static\replay_workbench_bootstrap.js`
  `node --check src\atas_market_structure\static\replay_workbench_actions.js`
- Rollback notes
  Remove the trust helper wiring and revert to accepting all stored history payloads for chart-facing paths.
  Leave stored SQLite ingestions untouched; they remain available for later forensic cleanup.

## 2026-03-25 Options Strategy Environment
- Goal
  Upgrade SPX options analysis from a single-snapshot gamma-map output into a deterministic, context-aware environment assessment that compares recent hourly snapshots and maps the current structure to strategy-friendly market regimes.
- Scope
  Add an options context service that reads recent archived gamma-map history snapshots, computes additive environment scores and strategy-archetype suggestions, and exposes them through the existing archive-and-analyze automation path.
- Files expected to change
  `PLANS.md`
  `docs/implementation/options_strategy_environment_plan_2026-03-25.md`
  `src/atas_market_structure/options_context_services.py`
  `src/atas_market_structure/options_automation_services.py`
  `src/atas_market_structure/app_routes/_options_routes.py`
  `scripts/archive_downloaded_options_csv.py`
  `README.md`
  `tests/test_options_context_services.py`
  `tests/test_options_automation.py`
  `tests/test_app_options_routes.py`
- Invariants to preserve
  AI stays outside the recognition critical path and outside any online deterministic recognition result.
  Existing gamma-map generation remains available and compatible.
  Archive behavior remains append-only at the dated directory level and rebuildable from stored CSV snapshots.
  Existing options routes stay backward compatible; any new response fields are additive.
- Migration / compatibility strategy
  Keep `spx_gamma_map.py` as the current gamma-map engine and avoid adding new business logic there.
  Add a new options context module that consumes existing gamma-map summaries and history JSON files.
  Keep current route and script entrypoints, but extend them with additive context-analysis outputs.
  Treat strategy labels as environment-fit suggestions, not claims about actual market inventory.
- Tests to run
  `python -m pytest tests\\test_options_context_services.py tests\\test_options_automation.py tests\\test_app_options_routes.py tests\\test_spx_gamma_map.py -q`
- Rollback notes
  Stop calling the options context service from automation and routes.
  Leave the additive context artifact files unused.
  Keep archived CSV snapshots and gamma-map artifacts intact.

## 2026-03-25 Durable ATAS Backfill Persistence
- Goal
  Persist replay-workbench ATAS backfill request state in SQLite so request dedupe, dispatch lease, and post-ack cooldown survive process restarts.
- Scope
  Add additive SQLite persistence for ATAS backfill request records, wire replay service lifecycle writes/restore, and cover restart-survival behavior with targeted tests.
- Files expected to change
  `src/atas_market_structure/repository_protocols.py`
  `src/atas_market_structure/repository_sqlite.py`
  `src/atas_market_structure/repository_clickhouse.py`
  `src/atas_market_structure/workbench_replay_service.py`
  `tests/test_replay_backfill_persistence.py`
- Invariants to preserve
  ClickHouse remains the primary K-line store.
  SQLite remains the metadata/cache/event store.
  Existing ATAS backfill payload fields, statuses, and route contracts stay unchanged.
  Degraded mode and rebuildability stay intact.
- Migration / compatibility strategy
  Add one SQLite table for serialized backfill records plus query columns.
  Keep Hybrid repository routing metadata persistence to SQLite.
  Reload only recent records on startup and prune older terminal rows.
- Tests to run
  `python -m pytest tests\\test_replay_backfill_persistence.py tests\\test_raw_mirror_repository.py tests\\test_app_workbench_backfill_routes.py tests\\test_repository_sqlite_pragmas.py tests\\test_repository_hybrid.py tests\\test_init_clickhouse.py -q`
- Rollback notes
  Remove the additive table usage and restore the prior memory-only backfill registry. Existing SQLite data can remain unused.

## 2026-03-26 ATAS Pipeline Monitor
- Goal
  Add a monitoring UI that shows which ATAS bar data has landed, where it is stored, how much of it has been aggregated, and whether recent write activity is becoming too dense.
- Scope
  Add additive repository queries for raw/aggregated candle counts, a focused monitor service plus HTTP endpoints, and a standalone visual monitor page with contract switching and animated storage-pool flow.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/repository_protocols.py`
  `src/atas_market_structure/repository_records.py`
  `src/atas_market_structure/repository_sqlite.py`
  `src/atas_market_structure/repository_clickhouse.py`
  `src/atas_market_structure/workbench_pipeline_monitor_service.py`
  `src/atas_market_structure/app.py`
  `src/atas_market_structure/app_routes/_workbench_routes.py`
  `src/atas_market_structure/static/pipeline_monitor.html`
  `src/atas_market_structure/static/pipeline_monitor.css`
  `src/atas_market_structure/static/pipeline_monitor.js`
  `tests/test_app_workbench_pipeline_monitor_routes.py`
  `tests/test_repository_hybrid.py`
- Invariants to preserve
  ClickHouse remains the primary K-line read store.
  SQLite remains the metadata/raw mirror store.
  Existing replay workbench routes, data contracts, and main chart UX stay intact.
  No new production dependency is added for animation or physics.
- Migration / compatibility strategy
  Keep the monitor fully additive behind new routes and static assets.
  Use repository queries instead of scanning large payloads in memory.
  Label CK pools as root-symbol shared pools when contract-level raw bars flow into root-level chart aggregates.
- Tests to run
  `python -m pytest tests\\test_app_workbench_pipeline_monitor_routes.py tests\\test_repository_hybrid.py tests\\test_replay_backfill_persistence.py tests\\test_raw_mirror_repository.py tests\\test_repository_sqlite_pragmas.py tests\\test_app_workbench_backfill_routes.py tests\\test_init_clickhouse.py -q`
- Rollback notes
  Remove the new monitor routes and static page and leave the additive repository queries unused.

## 2026-03-25 Replay Workbench Event Backbone
- Goal
  Promote replay-workbench events into first-class persisted objects by adding EventCandidate, EventStream, and EventMemory as the source of truth behind chat-derived annotations and plan cards.
- Scope
  Add additive event-domain models, SQLite persistence, workbench event services, and HTTP APIs for event listing, extraction, patching, and lifecycle actions while keeping existing chat reply and projection flows working.
- Files expected to change
  `docs/implementation/workbench_event_backbone_plan_2026-03-25.md`
  `docs/implementation/workbench_event_backbone_design.md`
  `src/atas_market_structure/models/_schema_versions.py`
  `src/atas_market_structure/models/_workbench_events.py`
  `src/atas_market_structure/models/_chat.py`
  `src/atas_market_structure/models/_api_envelopes.py`
  `src/atas_market_structure/models/__init__.py`
  `src/atas_market_structure/repository_chat.py`
  `src/atas_market_structure/repository_records.py`
  `src/atas_market_structure/repository_workbench_events_sqlite.py`
  `src/atas_market_structure/repository_sqlite.py`
  `src/atas_market_structure/repository.py`
  `src/atas_market_structure/workbench_event_service.py`
  `src/atas_market_structure/workbench_chat_service.py`
  `src/atas_market_structure/workbench_services.py`
  `src/atas_market_structure/app.py`
  `src/atas_market_structure/app_routes/_chat_routes.py`
  `src/atas_market_structure/app_routes/_workbench_routes.py`
  `tests/test_app_chat_routes.py`
  `tests/test_chat_backend_e2e.py`
  `tests/test_workbench_event_service.py`
  `tests/test_workbench_event_api.py`
- Invariants to preserve
  Deterministic recognition, evaluation, and tuning remain unchanged and AI stays outside the recognition critical path.
  Existing chat annotations and plan cards remain available as compatibility projections.
  Append-only auditability and degraded-mode behavior remain intact.
  Existing chat/session/message contracts continue to work for current tests and UI consumers.
- Migration / compatibility strategy
  Add new SQLite tables and additive repository methods only.
  Keep reply responses returning annotations and plan cards, but derive them from persisted event candidates where possible.
  Use explicit service-side lifecycle transition functions instead of allowing arbitrary frontend state writes.

## 2026-03-25 Replay Workbench Integration Closeout
- Goal
  Non-destructively integrate the new event backbone, event overlay interactions, prompt trace visibility, and outcome ledger so the replay workbench closes the loop from AI reply to event stream, chart projection, trace auditability, and outcome feedback.
- Scope
  Fix contract and interaction mismatches across the new frontend and route layers, reduce event-panel DOM churn, tighten legacy plan-card fallback behind explicit debug gates, and document the integrated object/state flow and compatibility strategy.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_integration_closeout_plan_2026-03-25.md`
  `docs/implementation/workbench_integration_closeout_design.md`
  `src/atas_market_structure/static/replay_workbench_ai_chat.js`
  `src/atas_market_structure/static/replay_workbench_event_panel.js`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
  `tests/test_app_chat_routes.py`
- Invariants to preserve
  EventCandidate remains the source of truth; annotations and plan cards remain derived compatibility projections.
  Deterministic recognition, episode evaluation, and tuning flows remain unchanged.
  Prompt Trace and Outcome Ledger contracts stay additive and message-linked.
  Existing legacy fallback paths remain available, but only as explicit fallback and not as the default rendering/data path.
- Migration / compatibility strategy
  Keep old UI fallback code callable, but prefer structured event-stream and structured plan-card payloads on the main path.
  Avoid route or schema renames; only tighten error handling for missing prompt-trace query parameters.
  Limit frontend fixes to render-path stabilization and layout containment rather than broad UI rewrites.
- Tests to run
  `python -m pytest tests\\test_app_chat_routes.py tests\\test_workbench_event_service.py tests\\test_workbench_prompt_trace_service.py tests\\test_workbench_event_outcome_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py tests\\test_contract_schema_versions.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`
  `npx playwright test tests\\playwright_workbench_event_interaction.spec.js`
- Rollback notes
  Re-enable unconditional legacy plan-card parsing in the chat UI if structured cards are not available.
  Remove the event-panel render caching if it causes stale-card regressions.
  Drop the outcome summary height constraint if it creates unacceptable clipping on target screens.
  Leave prompt-trace full persistence for a follow-up thread; keep a nullable source trace reference field in the new event objects.
- Tests to run
  `python -m pytest tests\\test_workbench_event_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py tests\\test_workbench_projection_api.py tests\\test_contract_schema_versions.py tests\\test_file_size_budget.py -q`
- Rollback notes
  Stop calling the event service from chat reply finalization, leave the additive tables unused, and revert the new event endpoints. Existing annotations and plan-card persistence can keep operating directly.

## 2026-03-25 Replay Workbench Frontend Event Projection
- Goal
  Rewire replay-workbench event interaction so frontend event cards, chart spotlight, mounted overlays, and manual chart-created objects are driven by backend `EventCandidate` data instead of text-derived fallback objects.
- Scope
  Add focused frontend event modules, wire the middle event column to `event-stream`, implement hidden/hover/mounted/pinned projection states, and add the minimum additive backend route needed to persist manual chart-created event candidates.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_frontend_event_projection_plan_2026-03-25.md`
  `docs/implementation/workbench_frontend_event_projection_design.md`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/static/replay_workbench_state.js`
  `src/atas_market_structure/static/replay_workbench_dom.js`
  `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  `src/atas_market_structure/static/replay_workbench_ai_chat.js`
  `src/atas_market_structure/static/replay_workbench_event_api.js`
  `src/atas_market_structure/static/replay_workbench_event_panel.js`
  `src/atas_market_structure/static/replay_workbench_event_overlay.js`
  `src/atas_market_structure/static/replay_workbench_event_manual_tools.js`
  `tests/playwright_support/fake_workbench_ui_server.py`
  `tests/playwright_workbench_event_interaction.spec.js`
  If needed for manual persistence:
  `src/atas_market_structure/models/_workbench_events.py`
  `src/atas_market_structure/models/__init__.py`
  `src/atas_market_structure/workbench_event_service.py`
  `src/atas_market_structure/app_routes/_workbench_event_routes.py`
  `tests/test_workbench_event_api.py`
  `tests/test_workbench_event_service.py`
- Invariants to preserve
  Replay workbench layout stays intact.
  Deterministic recognition, evaluation, and tuning remain unchanged.
  AI stays outside the recognition critical path.
  Existing annotation and plan-card flows remain backward compatible.
  Legacy text parsing remains fallback-only, not the primary source.
- Migration / compatibility strategy
  Add new frontend modules and keep large legacy files as orchestration/facade glue only.
  Prefer backend event-stream payloads for event cards and overlays.
  Keep legacy extraction visible only as explicit fallback when backend event data is unavailable.
  Add only additive backend support if manual chart-created objects cannot be persisted via current event APIs.
- Tests to run
  `python -m pytest tests\test_workbench_event_service.py tests\test_workbench_event_api.py tests\test_app.py tests\test_workbench_projection_api.py -q`
  `npx playwright test tests/playwright_workbench_event_interaction.spec.js`
- Rollback notes
  Disable the new event modules in bootstrap and restore the old cluster-driven event column.
  Leave additive manual-create persistence unused.
  Keep stored event candidates and compatibility projections intact.

## 2026-03-25 Replay Workbench Prompt Trace
- Goal
  Make every replay-workbench AI reply traceable and auditable by persisting a user-readable Prompt Trace record that captures prompt blocks, replay window summaries, memory/context inputs, and the final prompt snapshot linked to the assistant message.
- Scope
  Add additive Prompt Trace models, SQLite persistence, chat-flow trace generation/linkage, query APIs, and a lightweight frontend drawer for viewing trace summaries and expanded snapshots without changing the existing AI business semantics.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_prompt_trace_plan_2026-03-25.md`
  `docs/implementation/workbench_prompt_trace_design.md`
  `src/atas_market_structure/models/_schema_versions.py`
  `src/atas_market_structure/models/_chat.py`
  `src/atas_market_structure/models/_workbench_prompt_traces.py`
  `src/atas_market_structure/models/__init__.py`
  `src/atas_market_structure/repository_chat.py`
  `src/atas_market_structure/repository_records.py`
  `src/atas_market_structure/repository_workbench_prompt_traces_sqlite.py`
  `src/atas_market_structure/repository_sqlite.py`
  `src/atas_market_structure/repository.py`
  `src/atas_market_structure/workbench_common.py`
  `src/atas_market_structure/workbench_prompt_trace_service.py`
  `src/atas_market_structure/workbench_chat_service.py`
  `src/atas_market_structure/workbench_event_service.py`
  `src/atas_market_structure/app_routes/__init__.py`
  `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
  `src/atas_market_structure/app.py`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/static/replay_workbench_dom.js`
  `src/atas_market_structure/static/replay_workbench_state.js`
  `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  `src/atas_market_structure/static/replay_workbench_ai_chat.js`
  `src/atas_market_structure/static/replay_workbench_ai_threads.js`
  `src/atas_market_structure/static/replay_workbench_prompt_trace_panel.js`
  `tests/test_app_chat_routes.py`
  `tests/test_chat_backend_e2e.py`
  `tests/test_contract_schema_versions.py`
  `tests/test_workbench_prompt_trace_service.py`
- Invariants to preserve
  Existing replay-workbench AI request semantics stay unchanged.
  Deterministic recognition, evaluation, and tuning remain untouched and AI stays outside the recognition critical path.
  Prompt Trace persistence is additive, queryable, and linked to assistant messages without breaking existing chat/message payloads.
  Attachments are summarized without persisting unnecessary raw image payloads inside Prompt Trace.
- Migration / compatibility strategy
  Add one focused SQLite repository module and one additive table for prompt traces.
  Add nullable `prompt_trace_id` to chat messages and keep old rows/messages valid.
  Generate traces from the existing chat request path, then patch them with resolved model name and attached event ids after reply finalization.
  Keep the frontend drawer summary-first; expose expanded snapshots on demand so old chats continue rendering even when no trace exists.
- Tests to run
  `python -m pytest tests\\test_workbench_prompt_trace_service.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py tests\\test_contract_schema_versions.py tests\\test_file_size_budget.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`
- Rollback notes
  Stop generating/storing prompt traces from chat reply preparation and remove the new prompt-trace routes from application dispatch.
  Leave additive SQLite rows and nullable message references unused.
  Keep existing chat/session/message routes and UI functional without Prompt Trace data.

## 2026-03-25 Replay Workbench Event Outcome Ledger
- Goal
  Add an additive Event Outcome Ledger so replay-workbench events and promoted plans can be settled deterministically into success, failure, timeout, or inconclusive results, then surfaced through lightweight accuracy statistics without touching the recognition or episode-evaluation core semantics.
- Scope
  Add focused outcome-domain models, SQLite persistence, a deterministic workbench outcome service, HTTP read APIs, and lightweight frontend badges/stats/detail UI driven by persisted `EventCandidate` and Prompt Trace references.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_event_outcome_plan_2026-03-25.md`
  `docs/implementation/workbench_event_outcome_design.md`
  `src/atas_market_structure/models/_schema_versions.py`
  `src/atas_market_structure/models/_workbench_event_outcomes.py`
  `src/atas_market_structure/models/__init__.py`
  `src/atas_market_structure/repository_chat.py`
  `src/atas_market_structure/repository_records.py`
  `src/atas_market_structure/repository_workbench_event_outcomes_sqlite.py`
  `src/atas_market_structure/repository_sqlite.py`
  `src/atas_market_structure/repository.py`
  `src/atas_market_structure/workbench_event_outcome_service.py`
  `src/atas_market_structure/app_routes/__init__.py`
  `src/atas_market_structure/app_routes/_workbench_event_outcome_routes.py`
  `src/atas_market_structure/app.py`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/static/replay_workbench_dom.js`
  `src/atas_market_structure/static/replay_workbench_state.js`
  `src/atas_market_structure/static/replay_workbench_event_api.js`
  `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  `src/atas_market_structure/static/replay_workbench_event_outcome_panel.js`
  `tests/test_workbench_event_outcome_service.py`
  `tests/test_workbench_event_api.py`
  `tests/test_contract_schema_versions.py`
- Invariants to preserve
  Deterministic recognition, review projection, episode evaluation, and tuning recommendation paths remain unchanged.
  AI stays outside the recognition critical path; outcome settlement uses persisted event facts plus replay/chart data only.
  Existing annotations, plan cards, event-stream routes, and Prompt Trace flows remain backward compatible.
  Outcome stats definitions remain explicit and only count settled rows unless an `open_count` field says otherwise.
- Migration / compatibility strategy
  Add one focused SQLite table and repository module for event outcomes instead of growing the legacy SQLite shell with more business logic.
  Keep settlement additive and workbench-scoped: `episode_evaluation` remains the recognition-layer episode judge, while Event Outcome Ledger evaluates chat/event objects.
  Allow unresolved/pending ledgers internally so open windows are not forced into false timeout/inconclusive states before expiry.
  Frontend badges and stats consume additive outcome APIs and degrade gracefully when no outcome row exists yet.
- Tests to run
  `python -m pytest tests\\test_workbench_event_outcome_service.py tests\\test_workbench_event_api.py tests\\test_contract_schema_versions.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_api.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_outcome_panel.js`
- Rollback notes
  Stop wiring the outcome service and routes from the application shell.
  Leave stored outcome rows unused and remove the frontend outcome controller from bootstrap.
  Existing event-stream, plan-card, Prompt Trace, and annotation flows continue without outcome badges or stats.

## 2026-03-27 ATAS Backfill Range Chunking
- Goal
  Prevent large single-range ATAS history-bar backfill requests from acknowledging without resending bars, especially for long `1m` catch-up windows after restarts.
- Scope
  Move ATAS backfill range chunking into a focused helper module and wire the replay workbench service to emit smaller `requested_ranges` while preserving the existing request contract.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/workbench_replay_backfill_ranges.py`
  `src/atas_market_structure/workbench_replay_service.py`
  `tests/test_workbench_replay_backfill_ranges.py`
- Invariants to preserve
  The replay/backfill HTTP contracts remain unchanged and still expose additive `requested_ranges`.
  Deterministic recognition and evaluation flows remain untouched.
  Existing small-window backfill requests should remain effectively unchanged.
- Migration / compatibility strategy
  Keep request persistence unchanged and chunk only the normalized `requested_ranges` path before requests are stored and dispatched.
  Reuse the existing timeframe bar budgets as per-request chunk limits so behavior stays aligned with current replay loading assumptions.
- Tests to run
  `python -m pytest tests\\test_workbench_replay_backfill_ranges.py -q`
- Rollback notes
  Remove the helper import and revert `requested_ranges` normalization to the previous unchunked behavior.
