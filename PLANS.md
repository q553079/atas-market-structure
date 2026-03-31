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

## 2026-03-27 Replay Workbench Button Reliability Cleanup
- Goal
  Remove dead frontend button-binding paths and standardize live button actions behind one idempotent, anti-double-click binding flow so chart and AI controls stay reliable as new buttons are added.
- Scope
  Keep the existing replay/AI features and route contracts, delete the unused legacy binding module, and tighten the active bootstrap binding layer with shared button helpers, immediate feedback, and screenshot/send responsiveness improvements.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench_bindings.js`
- Invariants to preserve
  Existing button ids, DOM structure, and public frontend route contracts stay compatible.
  AI remains outside the online deterministic recognition path.
  No new production dependency is added.
- Migration / compatibility strategy
  Treat `replay_workbench_bootstrap.js` as the only active button binding entrypoint.
  Keep existing button semantics, but route key actions through a shared binding helper with action locks and user feedback.
  Delete the unused legacy binding module only after verifying nothing imports it.
- Tests to run
  `docker compose -f compose.yaml -f docker-compose.yml up -d --build atas-market-structure`
  Request `http://127.0.0.1:8080/workbench/replay` and confirm the updated bootstrap version string is served.
- Rollback notes
  Restore the deleted legacy module and revert the bootstrap helper wiring.
  Static asset rollback is sufficient; no persisted data or backend contracts are touched.

## 2026-03-27 Compose Dev Source Mount
- Goal
  Stop requiring image rebuilds for every frontend or main-service code change by mounting the local source tree directly into the Dockerized development services.
- Scope
  Update the development compose services so the workbench app and realtime API read Python/static code from the workspace while preserving existing data volumes and service names.
- Files expected to change
  `PLANS.md`
  `compose.yaml`
  `docker-compose.yml`
- Invariants to preserve
  Existing service names, ports, env var names, and data volumes remain unchanged.
  SQLite/ClickHouse persistent data remains on their current volumes.
  No route contracts or business logic are changed.
- Migration / compatibility strategy
  Add source bind mounts only for code paths under active development.
  Keep the built image path available, but let mounted workspace files override `/app/src` and `/app/scripts` at runtime.
  Expect Python code changes to require container restart, while static file reads can reflect mounted files immediately.
- Tests to run
  `docker compose -f compose.yaml -f docker-compose.yml up -d atas-market-structure realtime-api`
  Verify `/workbench/replay` returns the updated static asset version without rebuilding the image.
- Rollback notes
  Remove the added bind mounts and restart the services to return to image-only runtime behavior.

## 2026-03-27 GC Recent Rollover Continuous Repair
- Goal
  Make recent GC rollover repairable on a display-only read path by removing generic root-symbol contamination from continuous sequencing and adding an additive adjustment mode that anchors repaired history to the latest contract price basis.
- Scope
  Keep raw mirrored history append-only, refine continuous-contract segment resolution for explicit contract sequences, and extend continuous adjustment options without changing write-path persistence.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/models/_enums.py`
  `src/atas_market_structure/continuous_contract_service.py`
  `tests/test_continuous_contract_service.py`
- Invariants to preserve
  Raw contract history remains auditable and unmodified.
  ClickHouse and SQLite write paths remain unchanged.
  Existing routes stay backward compatible; the new adjustment mode is additive.
  AI stays outside the online deterministic recognition path.
- Migration / compatibility strategy
  Keep existing `gap_shift` semantics unchanged for callers that already rely on it.
  Filter generic root-symbol rows only when explicit contract rows are present in the same continuous query window.
  Add a latest-basis adjustment mode as an additive enum value so callers can opt in explicitly.
- Tests to run
  `python -m pytest tests\\test_continuous_contract_service.py -q`
- Rollback notes
  Remove the additive adjustment mode and revert the generic-root filtering logic; stored raw and chart data remain untouched.

## 2026-03-27 GC Display Contract Rollover Markers
- Goal
  Keep recent GC chart prices on their true source contracts while making the rollover visually continuous by splicing explicit contract bars on the read path and marking the contract switch point instead of shifting prices.
- Scope
  Add a shared chart-display helper that prefers explicit contract raw bars when multiple contracts are present, emits additive rollover annotations/metadata, and reuses that display path from both the fast chart endpoint and replay snapshot builds.
- Files expected to change
  `PLANS.md`
  `src/atas_market_structure/chart_candle_service.py`
  `src/atas_market_structure/app_routes/_workbench_routes.py`
  `src/atas_market_structure/workbench_replay_service.py`
  `src/atas_market_structure/static/replay_workbench_actions.js`
  `tests/test_chart_candle_service.py`
- Invariants to preserve
  Raw mirrored contract history remains append-only and auditable.
  ClickHouse remains the primary main-chart read store.
  Real traded OHLC values are not shifted or rewritten for display.
  Existing replay/event payload contracts stay backward compatible; any added fields are additive.
- Migration / compatibility strategy
  Keep the earlier continuous adjustment modes available, but stop using price-shifted continuity for the main chart display path.
  Emit rollover markers through additive metadata/event annotations so the current frontend event layer can render them without a chart-library rewrite.
  Overlay display-repaired candles by timestamp onto existing history snapshots instead of destructively replacing broader coverage.
- Tests to run
  `python -m pytest tests\test_continuous_contract_service.py tests\test_chart_candle_service.py -q`
  `node --check src\atas_market_structure\static\replay_workbench_actions.js`
- Rollback notes
  Stop calling the display splice helper from the route and replay build path.
  Remove the additive rollover annotations/metadata.
  Leave stored raw bars and chart candles untouched.

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

## 2026-03-31 Replay Workbench Attention-First UI Delivery
- Goal
  Deliver the replay workbench attention-first UI in phased, additive slices so the product moves from multi-panel sprawl to a chart-first, structured-answer, nearby-context workflow without breaking deterministic recognition, existing chat history, or current route compatibility.
- Scope
  Freeze additive semantics for reply/context/event state first, then reshape the first screen, introduce structured answer cards and cautious-output rules, convert the event stream into a nearby-context dock, make Prompt/Context governance explicit, add a default-collapsed Change Inspector, and finish with incremental-rendering and motion stability work.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_attention_first_ui_delivery_plan_2026-03-31.md`
  `docs/implementation/workbench_attention_first_ui_contracts_2026-03-31.md`
  `docs/implementation/workbench_attention_first_ui_phase0_mapping_2026-03-31.md`
  `docs/implementation/workbench_attention_first_ui_phase0_codex_prompt_pack_2026-03-31.md`
  `docs/workbench/replay_workbench_attention_first_ui_v1.md`
  `src/atas_market_structure/models/_schema_versions.py`
  `src/atas_market_structure/models/_chat.py`
  `src/atas_market_structure/models/_workbench_prompt_traces.py`
  `src/atas_market_structure/models/__init__.py`
  `src/atas_market_structure/workbench_chat_service.py`
  `src/atas_market_structure/workbench_event_service.py`
  `src/atas_market_structure/workbench_prompt_trace_service.py`
  `src/atas_market_structure/app_routes/_workbench_routes.py`
  `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/static/replay_workbench_dom.js`
  `src/atas_market_structure/static/replay_workbench_state.js`
  `src/atas_market_structure/static/replay_workbench_bootstrap.js`
  `src/atas_market_structure/static/replay_workbench_ai_chat.js`
  `src/atas_market_structure/static/replay_workbench_ai_threads.js`
  `src/atas_market_structure/static/replay_workbench_event_panel.js`
  `src/atas_market_structure/static/replay_workbench_prompt_trace_panel.js`
  `src/atas_market_structure/static/replay_workbench_answer_cards.js`
  `src/atas_market_structure/static/replay_workbench_nearby_context.js`
  `src/atas_market_structure/static/replay_workbench_context_recipe.js`
  `src/atas_market_structure/static/replay_workbench_change_inspector.js`
  `tests/test_app_chat_routes.py`
  `tests/test_chat_backend_e2e.py`
  `tests/test_contract_schema_versions.py`
  `tests/test_workbench_prompt_trace_service.py`
- Invariants to preserve
  The recognition pipeline and degraded-mode behavior remain unchanged, and AI stays outside the online deterministic recognition path.
  All new UI/state payload fields remain additive and backward compatible.
  Existing viewport behavior must not regress: no reset on ordinary refresh, stream update, or context-panel interaction.
  Large compatibility-shell frontend files should not absorb new business logic once focused modules exist.
- Migration / compatibility strategy
  Execute in phases. First freeze shared semantics such as `chart_visible_window`, `reply_window_anchor`, `assertion_level`, prompt-block versioning, and nearby-event rules through a dedicated contract spec plus a Phase 0 mapping doc that assigns each field to an existing persistence or state container. Then layer in new surfaces behind additive metadata and focused frontend modules while keeping legacy rendering paths alive as compatibility fallbacks.
  Delay Change Inspector until structured answer cards, viewport binding, and prompt/context versioning are stable enough to support semantic diffs instead of noisy text diffs.
- Tests to run
  `python -m pytest tests\\test_app_chat_routes.py tests\\test_chat_backend_e2e.py tests\\test_workbench_prompt_trace_service.py tests\\test_contract_schema_versions.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_nearby_context.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`
- Rollback notes
  Roll back by phase, keeping additive metadata rows and payload fields in place while disabling the corresponding new frontend modules or route wiring.
  Revert the active surface to the prior compatibility UI instead of deleting stored prompt traces, chat rows, or additive event/context metadata.

## 2026-03-31 Replay Workbench Nearby Context Phase 0 Closeout
- Scope
  Close the Phase 0 event-side additive contracts by projecting stable presentation facts into event metadata and route payloads, then extract nearby-context derivation from the legacy event panel into a dedicated frontend module without changing the visible primary layout.
- Invariants to preserve
  The deterministic recognition pipeline, K-line generation/aggregation/live-tail paths, and degraded-mode behavior remain untouched.
  No database schema changes or new production dependencies are introduced.
  Ordinary event refresh, reply sync, and nearby-context recomputation must not reset the chart viewport or clear reply focus.
  Legacy event payloads without the new metadata must remain usable and must not be misclassified as fixed-anchor or nearby by default.
- Compatibility approach
  Persist only stable event facts in additive `metadata.presentation` fields and keep transient classifications such as `nearby`, `influencing`, `historical`, and `stale_state` as frontend-derived view state.
  Keep `replay_workbench_event_panel.js` as a facade/wiring layer and move new nearby-context business logic into `replay_workbench_nearby_context.js`, with minimal bootstrap wiring only.
- Tests
  `python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_event_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_nearby_context.js`
  `npx playwright test tests\\playwright_workbench_event_interaction.spec.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
- Rollback notes
  Remove the new nearby-context module wiring and stop projecting the additive presentation metadata in the workbench event service and route responses, leaving legacy event-panel behavior intact.

## 2026-03-31 Replay Workbench Attention-First Phase 1 First-Screen Convergence
- Scope
  Reshape the default replay workbench first screen into the attention-first four-module path of chart workspace, input composer, AI workspace, and nearby/event context while sinking low-frequency AI/event utilities behind secondary collapsed entry points.
- Invariants to preserve
  The deterministic recognition pipeline, backend route contracts, K-line/rendering paths, and existing viewport reset rules remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, change-inspector state, prompt-trace access, event-panel interactions, and active-session persistence must survive layout changes.
  No feature is deleted; low-frequency controls may be reordered, collapsed, or moved behind secondary entry points only.
- Compatibility approach
  Keep existing DOM ids for all current controls and panels, reuse collapsible/more-menu patterns instead of creating a new workflow, and treat `replay_workbench_bootstrap.js`, `replay_workbench_ai_threads.js`, and `replay_workbench_event_panel.js` as wiring/facade layers only.
  Preserve current event-panel and prompt/change-inspector rendering paths, but reduce first-screen competition by default-collapsing secondary AI utilities and consolidating redundant quick-entry affordances.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_dom.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
  `npx playwright test tests\\playwright_workbench_event_interaction.spec.js`
- Rollback notes
  Revert the new first-screen shell and secondary-collapse wiring while leaving underlying session, reply-focus, nearby-context, and prompt/change-inspector state untouched so the prior multi-panel layout continues to function.

## 2026-03-31 Replay Workbench Attention-First Phase 2 Structured Answer Cards
- Scope
  Upgrade assistant replies from generic chat bubbles into additive structured answer cards with `Full / Compact / Skim` presentation, visible `assertion_level`, and cautious-output sections, while keeping legacy messages, prompt trace, mounted replies, active reply focus, and change-inspector flows compatible.
- Invariants to preserve
  The deterministic recognition pipeline, backend contracts, K-line/rendering/live-tail paths, and viewport reset rules remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, mounted reply state, prompt trace actions, regenerate actions, context recipe visibility, and change inspector state must survive the rendering upgrade.
  Legacy assistant messages without `meta.workbench_ui` must continue to render and interact without crashes.
- Compatibility approach
  Put new card parsing/rendering in `replay_workbench_answer_cards.js` and keep `replay_workbench_ai_threads.js` focused on orchestration and wiring.
  Preserve existing `chat-message` / `chat-bubble` / `chat-bubble-body` wrappers and `data-message-action` buttons so legacy event decoration, prompt-trace hooks, and mounted-reply actions continue to work.
  Use `meta.workbench_ui` when present, fall back to legacy bubble rendering when absent, and synthesize only minimal pending-card shell metadata on the client for in-flight replies.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
  `npx playwright test tests\\playwright_event_structured_priority.spec.js`
- Rollback notes
  Revert the answer-card module wiring and card-specific styling while keeping stored chat messages, additive `meta.workbench_ui`, active reply state, and prompt trace data intact so the prior bubble renderer continues to function.

## 2026-03-31 Replay Workbench Attention-First Phase 3 Nearby Context Dock
- Scope
  Convert the visible event-stream reading path into a grouped, window-local Nearby Context Dock that derives `刚发生 / 仍在影响当前窗口 / 固定锚点` from the current chart window, active reply, reply-window anchor, and visible or mounted objects, while keeping backend event history intact.
- Invariants to preserve
  The deterministic recognition pipeline, backend Python contracts, K-line/rendering/live-tail paths, and viewport reset rules remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, answer cards, context recipe, change inspector, prompt trace access, and existing event-panel button actions must keep working.
  Nearby, influencing, and historical remain frontend-derived only; legacy events without presentation metadata must stay usable but must not be promoted to fixed-anchor by fallback logic.
- Compatibility approach
  Move the grouping and window-binding derivation into `replay_workbench_nearby_context.js`, keep `replay_workbench_event_panel.js` as facade/wiring plus grouped rendering, and reuse existing DOM ids in the event column so the visible layout stays stable.
  Preserve full event history in memory and behind a lightweight history affordance while capping the default front-surface nearby items to a small set appropriate for first-screen reading.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_nearby_context.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `npx playwright test tests\\playwright_workbench_event_interaction.spec.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
- Rollback notes
  Revert the grouped nearby-dock rendering and wiring while leaving additive event presentation metadata, active reply anchors, and backend event history untouched so the previous flat event list remains available.

## 2026-03-31 Replay Workbench Attention-First Phase 4 Context Recipe Governance And Trace Explainability
- Scope
  Make the replay workbench reply context inspectable by adding a dedicated Context Recipe summary and expanded view, surfacing prompt-governance metadata and exact block-version usage, and aligning the third-layer Prompt Trace with the same context-version and reply-window facts.
- Invariants to preserve
  The deterministic recognition pipeline, event-recognition chain, K-line generation/aggregation/live-tail paths, and public degraded-mode behavior remain unchanged.
  No database schema changes or new production dependencies are introduced, and all contract changes stay additive through `response_payload`, `snapshot`, `metadata`, or `full_payload`.
  Expanding or collapsing Context Recipe and Prompt Trace must not reset the chart viewport, active session, or active reply focus, and legacy messages or prompt blocks without governance fields must remain readable.
- Compatibility approach
  Move Context Recipe rendering logic into `replay_workbench_context_recipe.js` and keep `replay_workbench_ai_threads.js` as orchestration and state wiring only.
  Reuse existing additive backend fields for `context_version`, `reply_window`, `reply_window_anchor`, and block governance metadata, supplementing only UI-friendly projections where needed without renaming public payload fields.
  Keep Prompt Trace as a third-layer panel, but align its wording and block-version presentation with the Context Recipe so the same reply describes the same context on both surfaces.
- Tests
  `python -m pytest tests\\test_workbench_prompt_trace_service.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
- Rollback notes
  Remove the dedicated Context Recipe module wiring and the extra trace explainability projections while preserving stored additive metadata so the previous inline recipe rendering and legacy Prompt Trace summary continue to function.

## 2026-03-31 Replay Workbench Attention-First Phase 5 Change Inspector
- Scope
  Add a dedicated replay-workbench change-inspector module that stays default-collapsed, compares only eligible structured assistant replies, and explains reply/context/event/object deltas as semantic changes rather than raw long-text diffs.
- Invariants to preserve
  The deterministic recognition pipeline, backend Python contracts, K-line generation/aggregation/live-tail paths, and viewport reset rules remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, answer-card rendering, context-recipe visibility, nearby-context behavior, session persistence, and existing prompt-trace actions must survive inspector open/close and mode changes.
  Legacy messages and ineligible reply pairs must remain readable without forcing a compare path, and new replies must not auto-steal focus by opening the inspector.
- Compatibility approach
  Move inspector eligibility, comparison, and rendering logic into `replay_workbench_change_inspector.js`, keeping `replay_workbench_ai_threads.js` limited to orchestration and state wiring.
  Reuse the existing additive `state.changeInspector` shape by treating `open=false` as `collapsed` and `mode` as `peek` or `expanded`, while removing the old raw text-diff path and degrading to hidden or lightweight cues for ineligible comparisons.
  Prefer `meta.workbench_ui`, answer-card summaries, and context-recipe metadata as stable semantic sources, while falling back conservatively for legacy messages without misclassifying them as comparable structured replies.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
  `npx playwright test tests\\playwright_event_structured_priority.spec.js`
- Rollback notes
  Remove the dedicated change-inspector module wiring and restore the prior inline compare presentation while leaving additive reply metadata, answer-card state, and persisted change-inspector identifiers untouched so the legacy reply view keeps functioning.

## 2026-03-31 Replay Workbench Attention-First Phase 6 Incremental Rendering And Stability
- Scope
  Improve replay workbench rendering stability by adding a focused render-stability module for keyed patching, scroll/focus/hover preservation, and restrained transition coordination across AI reply cards, nearby context, change inspector, and context recipe surfaces.
- Invariants to preserve
  The deterministic recognition pipeline, backend contracts, K-line generation/aggregation/live-tail paths, and viewport reset rules remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, answer-card semantics, nearby-context grouping, context recipe state, change-inspector state, prompt-trace access, and active-session persistence must survive any render optimization.
  No new production dependency is introduced, and no public route contract, enum, or degraded-mode behavior is changed.
- Compatibility approach
  Keep initial full render paths as fallback, but route subsequent single-item updates through focused keyed or targeted patch helpers in `replay_workbench_render_stability.js`.
  Limit `replay_workbench_bootstrap.js`, `replay_workbench_ai_threads.js`, and `replay_workbench_event_panel.js` to orchestration and wiring; keep business semantics in their existing feature modules.
  If a targeted patch cannot safely apply, fall back to the existing full-surface render after capturing and restoring scroll/focus/selection state.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_render_stability.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_nearby_context.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
  `npx playwright test tests\\playwright_workbench_event_interaction.spec.js`
  `npx playwright test tests\\playwright_event_structured_priority.spec.js`
- Rollback notes
  Remove the render-stability module wiring and revert each surface to its prior full rerender path while leaving additive UI state, reply metadata, and nearby/change-inspector/context-recipe contracts intact.

## 2026-03-31 Replay Workbench Attention-First Post-Phase-6 Bootstrap AI Controls Split
- Scope
  Extract the replay workbench AI controls wiring from `replay_workbench_bootstrap.js` into a focused frontend module without changing the current attention-first behavior, DOM ids, state shape, or analysis preset semantics.
- Invariants to preserve
  The deterministic recognition pipeline, backend/public contracts, K-line generation/aggregation/live-tail paths, and viewport reset rules remain unchanged.
  `aiKlineAnalysisButton`, `aiMoreButton`, `aiSecondaryControls`, `analysisTypeSelect`, `analysisSendCurrentButton`, `analysisSendNewButton`, `focusRegionsButton`, `liveDepthButton`, `manualRegionButton`, and `selectedBarButton` must keep their current behavior.
  Change Inspector stays default-collapsed, the main AI send path remains intact, and no new production dependency is introduced.
- Compatibility approach
  Keep `replay_workbench_bootstrap.js` as orchestration and dependency assembly only, and move the AI controls button wiring plus local busy helpers into a dedicated `replay_workbench_ai_controls.js` module.
  Inject existing helpers such as `bindClickAction`, `setSecondaryControlsOpen`, `persistSessions`, `renderSnapshot`, and `aiChat` so the split does not rename public fields or duplicate business semantics.
- Tests
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_controls.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `npx playwright test tests\\playwright_replay_ui_fix.spec.js`
  `npx playwright test tests\\playwright_event_structured_priority.spec.js`
- Rollback notes
  Remove the dedicated AI-controls module and restore the previous inline button wiring in `replay_workbench_bootstrap.js` while leaving the current attention-first UI surface and analysis template contracts unchanged.

## 2026-03-31 Replay Workbench Attention-First UI Structure Correction
- Goal
  Fix the largest remaining first-screen structural mismatches against the attention-first design by removing the independent event column, reducing first-screen action noise, and shifting AI reading priority from thread-first to answer-first.
- Scope
  Limit this pass to frontend layout, shell ordering, and visibility strategy across the replay workbench first screen. Keep all existing event, reply, prompt-trace, and change-inspector capabilities, but move them into the intended reading hierarchy.
- Files expected to change
  `PLANS.md`
  `docs/implementation/workbench_attention_first_ui_structure_correction_2026-03-31.md`
  `src/atas_market_structure/static/replay_workbench.html`
  `src/atas_market_structure/static/replay_workbench.css`
  `src/atas_market_structure/static/replay_workbench_dom.js`
  `src/atas_market_structure/static/replay_workbench_ai_threads.js`
  `src/atas_market_structure/static/replay_workbench_answer_cards.js`
  `tests/playwright_replay_ui_fix.spec.js`
  `tests/playwright_workbench_event_interaction.spec.js`
  `tests/playwright_event_structured_priority.spec.js`
- Invariants to preserve
  Event backend contracts, `nearby / influencing / fixed_anchor / historical` semantics, and chart/event overlay semantics remain unchanged.
  `activeReplyId`, `activeReplyWindowAnchor`, render stability, legacy message compatibility, and scroll/focus preservation must keep working.
  Change Inspector stays default-collapsed, Prompt Trace stays third-layer, and no new production dependency is added.
- Migration / compatibility strategy
  Reuse existing DOM ids and event-panel data paths, but move `eventStreamPanel` under the AI reading path instead of keeping it as a first-screen middle column.
  Promote the active structured reply into a dedicated answer slot above the thread, keep the thread as a lower reading layer, and sink secondary chart/composer/session actions behind collapsed or more-entry shells rather than deleting them.
- Tests to run
  `python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_event_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py tests\\test_workbench_prompt_trace_service.py tests\\test_app_chat_routes.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_answer_cards.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_context_recipe.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_change_inspector.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_dom.js`
  `npx playwright test "tests/playwright_replay_ui_fix.spec.js" "tests/playwright_workbench_event_interaction.spec.js" "tests/playwright_event_structured_priority.spec.js"`
- Rollback notes
  Restore the prior multi-column shell and thread-first AI surface while keeping additive metadata, stored chat replies, event history, and prompt-trace data intact.

## 2026-03-31 Replay Workbench Attention-First Performance Hot Path Cleanup
- Scope
  Tighten the frontend hot paths for region drag, AI/event local rerender boundaries, and attention-first acceptance checks without redesigning the workbench or changing backend semantics. Extract the region drag runtime, render routing, and event/chat decoration ownership out of the existing bootstrap and event-panel facades so the split is structural, not cosmetic.
- Invariants to preserve
  Region selection semantics, viewport reset rules, answer-card / nearby-context / context-recipe / change-inspector behavior, public route contracts, schema/enums, and deterministic recognition boundaries remain unchanged.
- Compatibility approach
  Keep existing full-render behavior as the safe fallback, but move high-frequency drag updates to cached `requestAnimationFrame` scheduling, prefer targeted event/chat decoration updates, route local chart interactions through narrower render helpers, and keep bootstrap/event-panel as orchestration-only facades over focused modules.
- Tests
  `python -m pytest tests\\test_contract_schema_versions.py tests\\test_workbench_event_service.py tests\\test_workbench_event_api.py tests\\test_chat_backend_e2e.py tests\\test_workbench_prompt_trace_service.py tests\\test_app_chat_routes.py -q`
  `node --check src\\atas_market_structure\\static\\replay_workbench_bootstrap.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_event_panel.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_render_stability.js`
  `node --check src\\atas_market_structure\\static\\replay_workbench_chart_interactions.js`
  `node --check src\\atas_market_structure\\static\\init_lightweight_chart.js`
  `npx playwright test "tests/playwright_replay_ui_fix.spec.js" "tests/playwright_workbench_event_interaction.spec.js" "tests/playwright_event_structured_priority.spec.js"`
- Rollback notes
  Revert the new drag scheduler/cache, restore the previous AI/event full-rerender triggers, and drop the additive acceptance assertions; no persisted data or backend contracts need migration.
