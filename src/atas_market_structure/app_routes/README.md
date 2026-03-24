# Route Module Boundaries

`app.py` may assemble services, inject dependencies, register route handlers, and manage lifecycle.

Route modules may:

- decode HTTP method/path/query/body
- validate transport-level envelopes
- call one application service
- translate exceptions into HTTP responses

Route modules must not:

- implement recognition logic
- implement repository persistence logic
- grow custom orchestration branches already owned by services
- change workbench/chat/review payload contracts without a contract thread

Current split:

- `_health_routes.py`
- `_ingestion_routes.py`
- `_review_routes.py`
- `_workbench_routes.py`
- `_tuning_routes.py`

When adding a new route, place it in the closest existing module or create a new focused route module. Do not grow `app.py` back into a dispatch monolith.
