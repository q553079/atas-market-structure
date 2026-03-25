# Replay Workbench Prompt Trace Plan

## Goal
Make replay-workbench AI replies traceable and auditable by persisting one Prompt Trace per assistant reply, with a user-readable summary plus an expandable full snapshot.

## Scope
- Add additive Prompt Trace models and schema versions.
- Persist traces in SQLite and link them to assistant chat messages.
- Generate traces during the existing reply flow without changing model behavior.
- Expose query APIs by `prompt_trace_id`, `message_id`, and `session_id`.
- Add a lightweight frontend drawer for trace summaries and expanded snapshots.

## Files Expected To Change
- `PLANS.md`
- `docs/implementation/workbench_prompt_trace_plan_2026-03-25.md`
- `docs/implementation/workbench_prompt_trace_design.md`
- `src/atas_market_structure/models/_schema_versions.py`
- `src/atas_market_structure/models/_chat.py`
- `src/atas_market_structure/models/_workbench_prompt_traces.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/repository_chat.py`
- `src/atas_market_structure/repository_records.py`
- `src/atas_market_structure/repository_workbench_prompt_traces_sqlite.py`
- `src/atas_market_structure/repository_sqlite.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/workbench_common.py`
- `src/atas_market_structure/workbench_prompt_trace_service.py`
- `src/atas_market_structure/workbench_chat_service.py`
- `src/atas_market_structure/workbench_event_service.py`
- `src/atas_market_structure/app_routes/__init__.py`
- `src/atas_market_structure/app_routes/_workbench_prompt_trace_routes.py`
- `src/atas_market_structure/app.py`
- `src/atas_market_structure/static/replay_workbench.html`
- `src/atas_market_structure/static/replay_workbench.css`
- `src/atas_market_structure/static/replay_workbench_dom.js`
- `src/atas_market_structure/static/replay_workbench_state.js`
- `src/atas_market_structure/static/replay_workbench_bootstrap.js`
- `src/atas_market_structure/static/replay_workbench_ai_chat.js`
- `src/atas_market_structure/static/replay_workbench_ai_threads.js`
- `src/atas_market_structure/static/replay_workbench_prompt_trace_panel.js`
- `tests/test_app_chat_routes.py`
- `tests/test_chat_backend_e2e.py`
- `tests/test_contract_schema_versions.py`
- `tests/test_workbench_prompt_trace_service.py`

## Invariants To Preserve
- No AI logic changes in the recognition path.
- Existing chat reply behavior and payload meanings remain intact.
- Existing event backbone and annotation/plan-card compatibility projections keep working.
- Prompt Trace is additive and old messages without traces remain readable.

## Migration / Compatibility Strategy
- Store Prompt Trace in a new SQLite table and add a nullable `prompt_trace_id` column to `chat_messages`.
- Build trace summaries from already selected prompt blocks, memory, request flags, and replay/session context.
- Save the initial trace before model execution, then patch in the final resolved model name and attached event ids after reply finalization.
- Keep frontend rendering summary-first and tolerate missing traces gracefully.

## Tests To Run
- `python -m pytest tests\\test_workbench_prompt_trace_service.py tests\\test_chat_backend_e2e.py tests\\test_app_chat_routes.py tests\\test_contract_schema_versions.py tests\\test_file_size_budget.py -q`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_chat.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_ai_threads.js`
- `node --check src\\atas_market_structure\\static\\replay_workbench_prompt_trace_panel.js`

## Rollback Notes
- Stop creating Prompt Trace rows from the chat reply flow.
- Remove prompt-trace routes from dispatch.
- Ignore the additive `prompt_trace_id` column and stored prompt-trace rows.
