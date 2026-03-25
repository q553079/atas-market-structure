## Goal

Refactor replay workbench event interaction so `EventCandidate` becomes the main frontend event source, with hidden-by-default chart projection, hover spotlight, click-to-mount, pin support, and minimal manual chart-created candidates persisted through the event backbone.

## Scope

- Replace middle event column primary data source from local text extraction / chart clusters to backend `event-stream`.
- Add focused frontend modules for event API access, event panel rendering, event overlay lifecycle, and manual chart event creation.
- Preserve current workbench layout, chart main battlefield, and right-side chat/control structure.
- Keep legacy text-driven extraction and annotation flows only as explicit fallback paths.
- Add the minimum additive backend route needed for manual event candidate creation if the current event API cannot persist manual objects.

## Files expected to change

- `PLANS.md`
- `docs/implementation/workbench_frontend_event_projection_plan_2026-03-25.md`
- `docs/implementation/workbench_frontend_event_projection_design.md`
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_event_api.js`
- `src/atas_market_structure/static/replay_workbench_event_panel.js`
- `src/atas_market_structure/static/replay_workbench_event_overlay.js`
- `src/atas_market_structure/static/replay_workbench_event_manual_tools.js`
- `tests/playwright_support/fake_workbench_ui_server.py`
- `tests/playwright_workbench_event_interaction.spec.js`

If required for manual persistence:

- `src/atas_market_structure/models/_workbench_events.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/workbench_event_service.py`
- `src/atas_market_structure/app_routes/_workbench_event_routes.py`
- `tests/test_workbench_event_api.py`
- `tests/test_workbench_event_service.py`

## Invariants to preserve

- Deterministic recognition, evaluation, and tuning chains remain unchanged.
- AI stays out of the recognition critical path.
- Existing annotation / plan-card flows keep working as compatibility projections.
- Existing replay workbench layout stays intact.
- Existing public routes remain backward compatible; any new fields or routes are additive.
- Legacy fallback parsing is not deleted, but it must no longer be the primary event source.

## Migration / compatibility strategy

- Introduce new frontend modules and call them from current bootstrap wiring instead of adding more business logic into the existing large files.
- Keep event-stream rendering isolated from legacy reply-extraction rendering so rollout can remain incremental.
- Prefer `EventCandidate` payloads for event panel and overlay rendering; when unavailable, clearly mark legacy fallback usage and keep it non-primary.
- Use unified `event_id` for panel, overlay, and source jump behavior.
- For manual chart objects, add one additive create route only if the current backend lacks a persistence entrypoint.

## Tests to run

- `python -m pytest tests\test_workbench_event_service.py tests\test_workbench_event_api.py tests\test_app.py tests\test_workbench_projection_api.py -q`
- `npx playwright test tests/playwright_workbench_event_interaction.spec.js`

## Rollback notes

- Stop calling the new event frontend modules from bootstrap and fall back to the existing event cluster / reply-extraction presentation.
- Leave any additive manual-create route unused.
- Keep persisted event candidates intact; only the frontend presentation path rolls back.
