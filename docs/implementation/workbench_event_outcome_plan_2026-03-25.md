# Replay Workbench Event Outcome Ledger Plan

## Goal

Add a workbench-scoped Event Outcome Ledger so chat-derived events and promoted plans can be settled deterministically and summarized by kind, time window, preset, and model without changing recognition or `episode_evaluation`.

## Scope

- Add additive outcome-domain models and schema versions.
- Add focused SQLite persistence for outcome rows.
- Add a deterministic settlement service using `EventCandidate`, chart candles, and Prompt Trace references.
- Add read APIs for outcomes and summary/breakdown stats.
- Add lightweight frontend badges, summary stats, and detail viewing.

## Files Expected To Change

- `PLANS.md`
- `docs/implementation/workbench_event_outcome_plan_2026-03-25.md`
- `docs/implementation/workbench_event_outcome_design.md`
- `src/atas_market_structure/models/_schema_versions.py`
- `src/atas_market_structure/models/_workbench_event_outcomes.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/repository_chat.py`
- `src/atas_market_structure/repository_records.py`
- `src/atas_market_structure/repository_workbench_event_outcomes_sqlite.py`
- `src/atas_market_structure/repository_sqlite.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/workbench_event_outcome_service.py`
- `src/atas_market_structure/app_routes/__init__.py`
- `src/atas_market_structure/app_routes/_workbench_event_outcome_routes.py`
- `src/atas_market_structure/app.py`
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_event_api.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_event_outcome_panel.js`
- `tests/test_workbench_event_outcome_service.py`
- `tests/test_workbench_event_api.py`
- `tests/test_contract_schema_versions.py`

## Invariants To Preserve

- Recognition pipeline and `episode_evaluation` semantics stay untouched.
- AI remains outside the online recognition path.
- Existing event-stream, annotation, plan-card, and Prompt Trace contracts remain additive and backward compatible.
- Settlement rules remain explicit and auditable.

## Migration / Compatibility Strategy

- Persist outcome rows in a new focused SQLite module.
- Keep one ledger row per `event_id`, updated deterministically as more candles arrive.
- Allow unresolved open rows internally so not-yet-expired events are not misclassified.
- Decorate existing UI after render instead of rewriting the current event/plan rendering flow.

## Tests To Run

- `python -m pytest tests\test_workbench_event_outcome_service.py tests\test_workbench_event_api.py tests\test_contract_schema_versions.py -q`
- `node --check src\atas_market_structure\static\replay_workbench_event_api.js`
- `node --check src\atas_market_structure\static\replay_workbench_event_outcome_panel.js`

## Rollback Notes

- Remove application wiring for the new outcome service and routes.
- Leave stored outcome rows unused.
- Remove the frontend outcome controller from bootstrap while keeping the rest of the event system intact.
