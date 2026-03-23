# Ingestion Reliability Operations

This document covers the store-first ingestion plane implemented for the replay workbench. It follows `docs/k_repair/replay_workbench_master_spec_v2.md` and keeps AI outside the critical path: raw observations are durably stored before any downstream recognition or enrichment runs.

## Scope

Reliable ingestion endpoints:

- `POST /api/v1/ingest/market-structure`
- `POST /api/v1/ingest/event-snapshot`
- `POST /api/v1/ingest/process-context`
- `POST /api/v1/ingest/depth-snapshot`
- `POST /api/v1/ingest/adapter-payload`

Health and quality endpoints:

- `GET /health/ingestion`
- `GET /health/data-quality`

## Reliability Model

Each ingestion request follows the same sequence:

1. Decode and parse the request body.
2. Validate against the endpoint schema.
3. Compute `payload_hash` and derive an idempotency key from `request_id` or canonical payload hash.
4. Persist the raw observed payload in the append-only ingestion store.
5. Record the idempotency key and run log.
6. Trigger non-critical downstream processing.

Operational rules:

- Raw observation persistence is the first durable step.
- Downstream failures do not roll back stored observations.
- Depth/DOM absence degrades health state but does not reject the ingest.
- No message queue is required for V1. Reliability is provided locally by SQLite-backed persistence, dead letters, and run logs.

## Endpoint Behavior

All reliable ingestion endpoints provide:

- Schema validation via Pydantic models.
- Raw payload persistence in `ingestions`.
- Dead-letter quarantine in `ingestion_dead_letters` when parsing, validation, idempotency-conflict, or downstream handling fails.
- Duplicate protection in `ingestion_idempotency_keys`.
- Run-log rows in `ingestion_run_logs`.
- Standard JSON responses with `profile_version`, `engine_version`, `schema_version`, and `data_status`.

Response conventions:

- `201 Created`: raw payload stored and downstream completed or intentionally skipped.
- `200 OK`: duplicate request absorbed by idempotency.
- `202 Accepted`: raw payload stored, downstream failed, dead letter created.
- `400 Bad Request`: invalid JSON.
- `409 Conflict`: same idempotency key reused with a different payload hash.
- `422 Unprocessable Entity`: schema validation failure.

## Dead Letter Handling

Dead letters are stored in the `ingestion_dead_letters` table with:

- `dead_letter_id`
- `endpoint`
- `ingestion_kind`
- `request_id`
- `dedup_key`
- `payload_hash`
- `raw_payload`
- `error_code`
- `error_detail`
- `ingestion_id` when raw persistence already succeeded
- `stored_at`

Typical `error_code` values:

- `invalid_json`
- `validation_error`
- `idempotency_conflict`
- `downstream_failure`

Recommended operator flow:

1. Check `GET /health/ingestion` for recent dead-letter count and the latest `recent_runs`.
2. Query the latest dead-letter rows from the repository or local SQLite database.
3. Inspect `error_code`, `error_detail`, and `raw_payload`.
4. If `ingestion_id` is present, do not re-submit blindly; the raw observation is already stored.
5. Fix the downstream/service issue, then replay only the affected post-store step if needed.
6. If the payload itself is invalid, regenerate the source payload and submit a new request id or corrected canonical payload.

Operator note:

- A dead letter created after raw persistence means observation durability succeeded and only the downstream side failed.
- A dead letter without `ingestion_id` means the request never passed durable raw-ingestion storage.

## Health States

The ingestion plane exposes four states:

- `healthy`
- `degraded`
- `rebuild_required`
- `paused`

Degraded reasons are explicit and stable:

- `degraded_no_depth`
- `degraded_no_dom`
- `degraded_no_ai`
- `degraded_stale_macro`
- `replay_rebuild_mode`

State derivation:

- `paused`: `runtime/ingestion.paused` exists under the repository workspace root.
- `rebuild_required`: replay snapshot integrity or replay snapshot `data_status.degraded_modes` indicates rebuild mode.
- `degraded`: any degraded reason is active and the system is not paused or in rebuild-required mode.
- `healthy`: none of the degraded conditions are active.

## Degrade Trigger Conditions

`degraded_no_depth`

- No recent `depth_snapshot` exists.
- Or the latest depth snapshot is stale.
- Or `coverage_state` is `depth_unavailable` or `interrupted`.

`degraded_no_dom`

- Depth is unavailable.
- Or the latest depth snapshot lacks `best_bid` or `best_ask`.

`degraded_no_ai`

- The ingestion plane was started without AI availability.
- This never blocks raw ingestion.

`degraded_stale_macro`

- No recent macro context exists from `market_structure` or `process_context`.
- Or the latest macro input is older than the configured freshness threshold.

`replay_rebuild_mode`

- The latest replay snapshot reports integrity status `missing_local_history`, `gaps_detected`, or `no_live_data`.
- Or replay snapshot `data_status.degraded_modes` includes `replay_rebuild`.

## Health Endpoint Example

Example `GET /health/ingestion` response:

```json
{
  "status": "degraded",
  "degraded_reasons": [
    "degraded_no_depth",
    "degraded_no_dom",
    "degraded_no_ai"
  ],
  "profile_version": "profile_unassigned",
  "engine_version": "engine_unassigned",
  "schema_version": "1.0.0",
  "freshness": "fresh",
  "completeness": "partial",
  "data_status": {
    "data_freshness_ms": 2400,
    "feature_completeness": 0.6,
    "depth_available": false,
    "dom_available": false,
    "ai_available": false,
    "degraded_modes": [
      "no_depth",
      "no_dom",
      "no_ai"
    ],
    "freshness": "fresh",
    "completeness": "partial"
  },
  "last_success_at": "2026-03-23T08:31:02Z",
  "last_dead_letter_at": "2026-03-23T08:30:18Z",
  "last_run_at": "2026-03-23T08:31:02Z",
  "metrics": {
    "total_count": 8,
    "accepted_count": 6,
    "duplicate_count": 1,
    "dead_letter_count": 1,
    "downstream_failure_count": 0
  },
  "recent_runs": [
    {
      "run_id": "run-20260323T083102Z-01",
      "endpoint": "/api/v1/ingest/market-structure",
      "ingestion_kind": "market_structure",
      "instrument_symbol": "ESM6",
      "request_id": "snap-20260323-083100",
      "dedup_key": "snap-20260323-083100",
      "payload_hash": "8c830d...",
      "outcome": "accepted",
      "http_status": 201,
      "ingestion_id": "ing-20260323-083102",
      "dead_letter_id": null,
      "detail": {
        "downstream_status": "completed"
      },
      "started_at": "2026-03-23T08:31:02Z",
      "completed_at": "2026-03-23T08:31:02Z"
    }
  ]
}
```

## Data Quality Endpoint Example

Example `GET /health/data-quality?instrument_symbol=ESM6` response:

```json
{
  "status": "degraded",
  "degraded_reasons": [
    "degraded_no_depth",
    "degraded_no_dom",
    "degraded_no_ai"
  ],
  "instrument_symbol": "ESM6",
  "profile_version": "profile_unassigned",
  "engine_version": "engine_unassigned",
  "schema_version": "1.0.0",
  "freshness": "fresh",
  "completeness": "partial",
  "data_status": {
    "data_freshness_ms": 2400,
    "feature_completeness": 0.6,
    "depth_available": false,
    "dom_available": false,
    "ai_available": false,
    "degraded_modes": [
      "no_depth",
      "no_dom",
      "no_ai"
    ],
    "freshness": "fresh",
    "completeness": "partial"
  },
  "source_statuses": [
    {
      "source_kind": "market_structure",
      "latest_observed_at": "2026-03-23T08:31:00Z",
      "available": true,
      "freshness_ms": 2400
    },
    {
      "source_kind": "process_context",
      "latest_observed_at": "2026-03-23T08:30:58Z",
      "available": true,
      "freshness_ms": 4400
    },
    {
      "source_kind": "depth_snapshot",
      "latest_observed_at": null,
      "available": false,
      "freshness_ms": null
    }
  ]
}
```

## Pause / Resume

To pause the ingestion plane without stopping the service:

1. Create `runtime/ingestion.paused` under the repository workspace root.
2. Confirm `GET /health/ingestion` returns `status = "paused"`.
3. Remove the sentinel file to resume normal status evaluation.

Important:

- The pause sentinel changes reported health state only.
- It does not delete previously stored observations.
- If you want request rejection while paused, that is a separate policy decision and is not part of this V1 implementation.

## Testing

Relevant test coverage:

- `tests/test_ingestion_reliability.py`
- selected replay-builder regression coverage in `tests/test_app.py`

Recommended commands:

```powershell
pytest tests\test_ingestion_reliability.py -q
pytest tests\test_app.py -q -k "market_structure_ingestion_returns_derived_analysis or event_snapshot_ingestion_supports_execution_reversal_route or depth_snapshot_updates_significant_liquidity_memory or adapter_continuous_state_ingestion_is_stored or adapter_trigger_burst_ingestion_is_stored or adapter_history_bars_ingestion_and_replay_builder_prefers_atas_history"
```
