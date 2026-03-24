# Contributing

## Formal Code Boundaries

Authoritative implementation directories:

- `src/atas_market_structure/`: application assembly, routes, services, repositories, models
- `tests/`: contract, domain, integration, degraded/high-availability, and structure-guard tests
- `schemas/`: generated JSON schema artifacts for stable contracts
- `samples/`: canonical payload and response samples that must validate against current code contracts
- `docs/`: architecture, ADR, and normative API/contract notes

Historical or planning material:

- `docs/k_repair/` remains useful context, but it is not the authoritative code-entry map once implementation has diverged.
- When a historical doc conflicts with `README.md`, `src/atas_market_structure/README.md`, or module-level READMEs, follow the implementation-facing documents and code.

## Temporary And Diagnostic Work

Committed reusable diagnostics belong in:

- `tools/`: reusable inspection, export, or one-off recovery utilities that may be rerun by another engineer
- `scripts/`: operator-facing launch, bootstrap, or CI-friendly maintenance scripts
- `tmp/`: local-only outputs, screenshots, transcripts, pytest scratch space, generated media, and disposable debugging artifacts

Do not commit temporary files to the repository root. This includes:

- `_tmp_*`
- `tmp_*`
- ad hoc `check_*.py` probes
- temporary diff output
- temporary pytest output
- screenshots, recordings, exported SVG/PNG/JSON/TXT artifacts

## Large-File Anti-Regrowth Rules

Historical giant files were split during the second consolidation pass. Keep the split stable:

- `src/atas_market_structure/workbench_services.py` is a compatibility facade only; do not add new business logic there.
- `src/atas_market_structure/repository.py` is a compatibility facade only; do not add new business logic there.
- `src/atas_market_structure/app.py` may assemble dependencies and register routes, but must not grow back into a route/logic monolith.

New logic should go to the closest focused module first:

- workbench projection read models -> `workbench_projection_services.py`
- replay build/cache/backfill flows -> `workbench_replay_service.py`
- workbench review aggregation -> `workbench_review_service.py`
- chat/session/annotation helpers -> `workbench_chat_service.py`
- raw append-only ingestion persistence -> `repository_raw_ingestion.py`
- recognition outputs/state persistence -> `repository_recognition.py`
- projection/read queries -> `repository_projection.py`
- evaluation/tuning lineage -> `repository_evaluation_tuning.py`
- chat storage -> `repository_chat.py`

## Contracts, Schemas, And Samples

- New writes must emit canonical `schema_version` names defined in `src/atas_market_structure/models/_schema_versions.py`.
- `tools/export_json_schemas.py` owns the generated artifacts in `schemas/`.
- `samples/contracts/` and `samples/responses/` must reflect current serialized field names, not legacy alias-accepted input names.
- If a compatibility alias is still accepted on read, document that as compatibility behavior; do not use the alias in new canonical samples unless the endpoint truly serializes it that way.

## Before Opening A PR

Run the focused guards that match your change:

```powershell
$env:PYTHONPATH = "$PWD\src"
python tools/export_json_schemas.py
python -m pytest tests/test_sample_validation.py tests/test_file_size_budget.py -q
```
