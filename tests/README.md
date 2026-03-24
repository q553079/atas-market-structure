# Test Layout

Split tests by behavior boundary so future changes do not regrow giant suites.

Current route-oriented layout:

- `test_app.py`: smoke coverage only
- `test_app_ingestion_routes.py`
- `test_app_workbench_routes.py`
- `test_app_workbench_live_routes.py`
- `test_app_workbench_backfill_routes.py`
- `test_app_review_routes.py`
- `test_app_chat_routes.py`

Current chat E2E layout:

- `test_chat_backend_e2e.py`
- `test_chat_backend_context_e2e.py`
- `test_chat_backend_stream_e2e.py`
- `test_chat_backend_lifecycle_e2e.py`

Rules:

- keep transport contract tests separate from domain semantics tests
- keep degraded-mode tests separate from normal-path tests
- if a test file crosses the soft limit, split by theme before adding more cases

Contract and closeout layers:

- `test_contract_*.py`: schema names, enum values, API aliases, response envelopes
- `test_domain_*.py`: event lifecycle and evaluation/tuning mapping semantics
- `test_integration_*.py`: repository + service chain coverage across frozen boundaries
- `test_degraded_*.py`: degraded/high-availability acceptance, malformed payload survival, rebuild stability
- `test_file_size_budget.py`: lightweight structure guard against file-growth regressions
