# Options Strategy Environment Plan (2026-03-25)

## Goal
Upgrade SPX options analysis from a single-snapshot gamma-map output into a deterministic, context-aware environment assessment that compares recent hourly snapshots and maps the current structure to strategy-friendly market regimes.

## Scope
- Add an options context service that reads recent archived gamma-map history snapshots.
- Compute additive deterministic environment scores such as range-harvest, breakout pressure, downside hedge demand, and short-vol vs long-gamma friendliness.
- Produce additive strategy-archetype recommendations based on those scores.
- Expose the context analysis through the existing archive-and-analyze automation path and document the new outputs.

## Files expected to change
- `PLANS.md`
- `docs/implementation/options_strategy_environment_plan_2026-03-25.md`
- `src/atas_market_structure/options_context_services.py`
- `src/atas_market_structure/options_automation_services.py`
- `src/atas_market_structure/app_routes/_options_routes.py`
- `scripts/archive_downloaded_options_csv.py`
- `README.md`
- `tests/test_options_context_services.py`
- `tests/test_options_automation.py`
- `tests/test_app_options_routes.py`

## Invariants to preserve
- AI stays outside the recognition critical path and outside any online deterministic recognition result.
- Existing gamma-map generation remains available and compatible.
- Archive behavior remains append-only at the dated directory level and rebuildable from stored CSV snapshots.
- Existing options routes stay backward compatible; any new response fields are additive.

## Migration / compatibility strategy
- Keep `spx_gamma_map.py` as the current gamma-map engine and avoid adding new business logic there.
- Add a new options context module that consumes existing gamma-map summaries and history JSON files.
- Keep current route and script entrypoints, but extend them with additive context-analysis outputs.
- Treat strategy labels as environment-fit suggestions, not claims about actual market inventory.

## Tests to run
- `python -m pytest tests\\test_options_context_services.py tests\\test_options_automation.py tests\\test_app_options_routes.py tests\\test_spx_gamma_map.py -q`

## Rollback notes
- Stop calling the options context service from automation and routes.
- Leave the additive context artifact files unused.
- Keep archived CSV snapshots and gamma-map artifacts intact.
