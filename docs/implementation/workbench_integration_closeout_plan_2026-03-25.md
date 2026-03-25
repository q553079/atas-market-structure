# Replay Workbench Integration Closeout Plan (2026-03-25)

## Goal
Close the loop across the four delivered workbench threads so EventCandidate-backed events, Prompt Trace, chart overlays, and Outcome Ledger behave as one integrated system without breaking the existing deterministic recognition, evaluation, or tuning pipelines.

## Scope
- Stabilize the main frontend render path around `event-stream` API data.
- Make structured event/plan payloads the default source while keeping legacy text parsing as an explicit fallback only.
- Ensure Prompt Trace query behavior is route-safe and consistent with other workbench APIs.
- Reduce UI churn in the event column so hover, mount, and overlay click interactions remain stable under repeated `renderSnapshot()` calls.
- Document the integrated state flow, compatibility seams, and remaining gaps.

## Files Expected To Change
- `PLANS.md`
- `docs/implementation/workbench_integration_closeout_plan_2026-03-25.md`
- `docs/implementation/workbench_integration_closeout_design.md`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
- `tests/test_app_chat_routes.py`

## Invariants To Preserve
- `EventCandidate` stays the source of truth; annotation and plan-card payloads remain derived projections.
- AI remains outside the deterministic recognition critical path.
- Existing workbench route names, schema versions, and lifecycle enum values remain unchanged.
- Legacy fallback code remains available for debugging or controlled rollback, but not as the normal user path.

## Migration / Compatibility Strategy
- Keep the old vertical-event-stream compatibility facade in `replay_workbench.html`, but rely on `app.renderEventPanel()` when the modular event controller is present.
- Keep `parsePlanCardsFromReply()` in the chat controller for explicit debug fallback only.
- Return a standard HTTP 400 JSON payload for missing `session_id` on prompt-trace list queries instead of raising an uncaught exception.
- Prefer small render guards and CSS containment over structural UI rewrites.

## Tests To Run
- `python -m pytest tests\test_app_chat_routes.py tests\test_workbench_event_service.py tests\test_workbench_prompt_trace_service.py tests\test_workbench_event_outcome_service.py tests\test_workbench_event_api.py tests\test_chat_backend_e2e.py tests\test_contract_schema_versions.py -q`
- `node --check src\atas_market_structure\static\replay_workbench_ai_chat.js`
- `node --check src\atas_market_structure\static\replay_workbench_event_panel.js`
- `node --check src\atas_market_structure\static\replay_workbench_prompt_trace_panel.js`
- `npx playwright test tests\playwright_workbench_event_interaction.spec.js`

## Rollback Notes
- Re-enable unconditional text-to-plan fallback if structured plan cards prove unavailable in a target environment.
- Remove event-panel render caching if it creates stale markup that cannot be corrected by `syncCardClasses()`.
- Relax the outcome-summary height cap if a downstream layout expects the full panel to expand inline.
