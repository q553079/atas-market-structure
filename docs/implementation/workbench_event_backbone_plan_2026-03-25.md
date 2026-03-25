# Replay Workbench Event Backbone Plan

## Goal
Build the first backend backbone for `EventCandidate`, `EventStream`, and `EventMemory` so replay-workbench events stop being chat byproducts and become persisted, auditable source-of-truth objects.

## Scope
- Add additive event-domain models and schema-versioned API envelopes.
- Add SQLite-backed persistence for event candidates, stream entries, and memory entries.
- Add service-side lifecycle transitions and promotion logic.
- Integrate chat reply finalization so event candidates are extracted first and annotations/plan cards become derived projections.
- Add minimal HTTP APIs for list, extract, patch, promote, mount, and ignore flows.

## Files Expected To Change
- `PLANS.md`
- `docs/implementation/workbench_event_backbone_design.md`
- `src/atas_market_structure/models/_schema_versions.py`
- `src/atas_market_structure/models/_workbench_events.py`
- `src/atas_market_structure/models/_chat.py`
- `src/atas_market_structure/models/_api_envelopes.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/repository_chat.py`
- `src/atas_market_structure/repository_records.py`
- `src/atas_market_structure/repository_workbench_events_sqlite.py`
- `src/atas_market_structure/repository_sqlite.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/workbench_event_service.py`
- `src/atas_market_structure/workbench_chat_service.py`
- `src/atas_market_structure/workbench_services.py`
- `src/atas_market_structure/app.py`
- `src/atas_market_structure/app_routes/_chat_routes.py`
- `src/atas_market_structure/app_routes/_workbench_routes.py`
- `tests/test_workbench_event_service.py`
- `tests/test_workbench_event_api.py`
- compatibility test files already covering chat reply flows

## Invariants To Preserve
- Recognition pipeline remains deterministic and untouched.
- AI does not enter the recognition critical path.
- Chat annotations and plan cards remain available to current consumers.
- Append-only event history remains rebuildable and auditable.
- Degraded mode naming and current public route contracts remain stable.

## Migration / Compatibility Strategy
- Use additive tables and additive repository methods.
- Keep `annotation` and `plan_card` storage, but create them from event candidates when possible.
- Preserve existing chat reply response shape while introducing new event-stream endpoints.
- Keep structured-output support; weaken raw text fallback so it no longer acts as the primary fact source.

## Tests To Run
- `python -m pytest tests/test_workbench_event_service.py tests/test_workbench_event_api.py -q`
- `python -m pytest tests/test_chat_backend_e2e.py tests/test_app_chat_routes.py -q`
- `python -m pytest tests/test_workbench_projection_api.py tests/test_contract_schema_versions.py tests/test_file_size_budget.py -q`

## Rollback Notes
- Remove event-service integration from chat reply finalization.
- Leave additive event tables unused.
- Keep existing direct annotation/plan-card derivation path as the fallback implementation.
