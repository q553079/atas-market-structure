# Storage Blueprint

This document describes the local SQLite storage blueprint implemented for Master Spec v2 in V1.

## Goals

- Keep raw observations durable even when recognition or AI is unavailable.
- Separate observed facts from derived interpretation.
- Keep observation, feature, posterior, belief, episode, and evaluation records append-only.
- Keep mutable state objects versioned.
- Support replay-safe rebuild from observation tables.
- Stay compatible with the existing repository and application startup path.

## Implementation Files

- `schemas/sqlite_migrations/0001_storage_blueprint_tables.sql`
- `schemas/sqlite_migrations/0002_storage_blueprint_indexes.sql`
- `schemas/sqlite_migrations/0003_storage_blueprint_registry_seed.sql`
- `src/atas_market_structure/sqlite_migrations.py`
- `src/atas_market_structure/storage_models.py`
- `src/atas_market_structure/storage_repository.py`
- `src/atas_market_structure/repository.py`

## SQLite Runtime Rules

Both the migration runner and the blueprint repository open SQLite with:

- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=30000`
- `PRAGMA synchronous=NORMAL`

This matches the spec requirement that V1 remains SQLite-based while still supporting concurrent readers, append-heavy writes, and safe local rebuild operations.

## Migration Model

`SQLiteMigrationRunner` applies ordered `.sql` files from `schemas/sqlite_migrations/`.

Migration state is stored in `schema_migrations`:

- `version`
- `name`
- `checksum`
- `applied_at`

Behavior:

- Fresh initialization creates the migration table and applies all migrations in version order.
- Partial initialization can stop at a target version.
- Re-running initialization is idempotent.
- A checksum mismatch raises an error instead of silently drifting schema state.

## Table Groups

### Observation Layer

Append-only observed-fact tables:

- `observation_bar`
- `observation_trade_cluster`
- `observation_depth_event`
- `observation_gap_event`
- `observation_swing_event`
- `observation_absorption_event`
- `observation_adapter_payload`

Common shape:

- stable row id
- `instrument`
- `market_time`
- `session_date`
- `ingested_at`
- `schema_version`
- optional source ids
- optional dedupe fields
- raw JSON payload

`observation_adapter_payload` also has a partial unique dedupe index on:

- `(instrument, dedup_key, payload_hash)`

This gives V1 a local idempotency hook without introducing a queue or external storage.

### Feature Layer

- `feature_slice`

This table is append-only and stores deterministic windowed features derived from observations. It carries:

- `profile_version`
- `engine_version`
- `data_status_json`

### State Layer

- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `projection_snapshot`

These tables are append-only. They preserve the separation between observed facts and derived interpretation by only storing derived outputs after the raw observation layer already exists.

### Memory Layer

- `memory_anchor`
- `memory_anchor_version`
- `anchor_interaction`

`memory_anchor` is the current materialized state keyed by `anchor_id`.

`memory_anchor_version` is append-only history for each anchor.

`anchor_interaction` is append-only and records how live observations interact with historical anchors.

### Trajectory Layer

- `event_episode`
- `event_episode_evidence`

Both are append-only. The episode table stores the closed trajectory snapshot. Evidence stays separate and can reference source observation rows.

### Evaluation and Tuning Layer

- `episode_evaluation`
- `tuning_recommendation`
- `profile_patch_candidate`
- `patch_validation_result`

All four are append-only. No patch is auto-applied here; the storage layer only persists auditable records.

### Version and Ops Layer

- `instrument_profile`
- `recognizer_build`
- `ingestion_run_log`
- `rebuild_run_log`
- `dead_letter_payload`
- `schema_registry`

`instrument_profile` and `recognizer_build` are versioned state tables.

`ingestion_run_log`, `rebuild_run_log`, and `dead_letter_payload` are append-only audit tables.

`schema_registry` stores lifecycle metadata seeded by migration `0003`.

## Index Strategy

The schema adds explicit indexes for high-frequency reads, especially:

- `(instrument, market_time DESC)` on observation and derived tables
- `(instrument, session_date, market_time DESC)` on observation tables
- profile/build lookup indexes
- episode/evaluation linkage indexes
- dead-letter and run-log audit indexes

This keeps V1 efficient for the dominant access pattern:

- read by `instrument`
- filter by `market_time`
- replay or rebuild in time order

## Repository Layer

`SQLiteStorageBlueprintRepository` is the typed DAO layer for the blueprint tables.

It provides:

- typed dataclass models for all storage objects
- migration initialization and inspection
- typed save/list APIs per table family
- dedupe support for adapter payload ingestion
- rebuild observation feed assembly
- a safe `clear_derived_storage_for_rebuild(...)` entry point

## Existing Runtime Compatibility

The blueprint layer is added under the existing repository instead of replacing it.

`SQLiteAnalysisRepository` now:

- initializes the storage blueprint before legacy tables
- delegates unknown storage methods to the blueprint repository
- mirrors selected legacy writes into the new blueprint tables

Current mirror coverage includes:

- raw ingestions into `observation_adapter_payload`
- history bars into `observation_bar`
- depth snapshots into `observation_depth_event`
- event snapshots into `observation_trade_cluster` and observed absorption rows
- market structure payloads into observed swing, gap, and absorption rows
- belief states, episodes, evaluations, profiles, recognizer builds, dead letters, and ingestion run logs

This keeps the current app and replay entry points running while building out the spec-compliant storage layer.

## Rebuild Hooks

Two rebuild-oriented APIs are implemented:

- `list_rebuild_observations(...)`
- `clear_derived_storage_for_rebuild(...)`

`list_rebuild_observations(...)` produces one time-ordered feed across all `observation_*` tables for a single instrument.

`clear_derived_storage_for_rebuild(...)` deletes only rebuildable materialized state and records a `rebuild_run_log` row. In V1 it supports full-instrument clears only; window-scoped clears are rejected explicitly so the caller cannot accidentally request a partial rebuild and receive a wider delete than expected.

It intentionally preserves:

- observation tables
- `memory_anchor_version`
- `instrument_profile`
- `recognizer_build`
- operational history tables

It currently clears:

- `feature_slice`
- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `projection_snapshot`
- `memory_anchor`
- `anchor_interaction`
- `event_episode`
- `event_episode_evidence`
- `episode_evaluation`
- `tuning_recommendation`
- `profile_patch_candidate`
- `patch_validation_result`

The presence of `memory_anchor_version` means the current anchor materialization can be rebuilt without losing anchor history.

## Required Metadata

The blueprint schema preserves the spec requirement that critical outputs carry version metadata.

Derived and versioned state tables include:

- `schema_version`
- `profile_version` where applicable
- `engine_version` where applicable

Freshness and completeness style metadata is stored where the current runtime already emits it:

- `feature_slice.data_status_json`
- `belief_state_snapshot.data_status_json`
- `memory_anchor.freshness`
- `memory_anchor_version.freshness`

## How To Initialize

The normal application path already initializes the blueprint through `SQLiteAnalysisRepository.initialize()`.

Direct initialization is also possible:

```python
from pathlib import Path

from atas_market_structure.storage_repository import SQLiteStorageBlueprintRepository

repository = SQLiteStorageBlueprintRepository(
    database_path=Path("data/market_structure.db"),
)
repository.initialize()
```

## Test Coverage

The blueprint is covered by:

- `tests/test_storage_migrations.py`
- `tests/test_storage_blueprint_repository.py`

These tests verify:

- fresh initialization
- upgrade from partial migration state
- WAL mode
- required table creation
- schema registry seeding
- adapter payload dedupe
- versioned memory anchor behavior
- rebuild clearing rules
- legacy write mirroring into blueprint tables
