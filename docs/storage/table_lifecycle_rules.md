# Table Lifecycle Rules

This document records which blueprint tables are append-only and which are versioned, plus the operational rules that follow from Master Spec v2.

## Core Rules

- Observed facts must stay separate from derived interpretation.
- Append-only tables do not accept in-place updates as part of normal runtime.
- Versioned state tables may update the current materialized row, but they must preserve version identity and history.
- Rebuild may clear only rebuildable derived materializations, never the raw observation ground truth.
- AI is not part of the critical write path and does not mutate storage state automatically.

## Append-Only Tables

Observation layer:

- `observation_bar`
- `observation_trade_cluster`
- `observation_depth_event`
- `observation_gap_event`
- `observation_swing_event`
- `observation_absorption_event`
- `observation_adapter_payload`

Derived layer:

- `feature_slice`
- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `projection_snapshot`

Memory and interaction history:

- `memory_anchor_version`
- `anchor_interaction`

Trajectory layer:

- `event_episode`
- `event_episode_evidence`

Evaluation and tuning layer:

- `episode_evaluation`
- `tuning_recommendation`
- `profile_patch_candidate`
- `patch_validation_result`

Ops and audit layer:

- `ingestion_run_log`
- `rebuild_run_log`
- `dead_letter_payload`

Append-only rule:

- insert new rows only
- do not overwrite prior rows to "fix history"
- if interpretation changes, emit a new derived row with its own id and version metadata

## Versioned Tables

- `memory_anchor`
- `instrument_profile`
- `recognizer_build`
- `schema_registry`

### memory_anchor

`memory_anchor` is the current materialized state keyed by `anchor_id`.

Rules:

- current state may be upserted
- `current_version_id` must point at a historical row in `memory_anchor_version`
- historical anchor detail lives in append-only `memory_anchor_version`
- rebuild may clear `memory_anchor` current materialization and repopulate it later

### instrument_profile

Rules:

- each semantic profile revision gets a new `profile_version`
- rows are keyed by `(instrument, profile_version)`
- the repository may toggle `is_active` so only one active version per instrument remains
- updating the same version is allowed only to keep the recorded payload and active marker consistent
- ontology is fixed; only profile parameters vary

### recognizer_build

Rules:

- each recognizer release gets a new `engine_version`
- the repository may toggle `is_active` to maintain the current build pointer
- build metadata is auditable and never auto-promoted by AI

### schema_registry

Rules:

- seeded by migrations
- tracks lifecycle metadata for blueprint objects
- should change only through a schema migration, not through ad hoc runtime writes

## Rebuild Safety Rules

Allowed rebuild clear targets in the current implementation:

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

Rebuild must preserve:

- all `observation_*` tables
- `memory_anchor_version`
- `instrument_profile`
- `recognizer_build`
- `ingestion_run_log`
- `rebuild_run_log`
- `dead_letter_payload`

Reason:

- observations are the rebuild source of truth
- memory anchor history must survive even if current materialized state is rebuilt
- profile/build registries define which deterministic configuration produced derived rows
- operational logs must remain auditable

V1 safety constraint:

- `clear_derived_storage_for_rebuild(...)` rejects `window_start` and `window_end`
- only full-instrument rebuild clears are currently allowed
- this avoids silently deleting more data than the caller intended

## Dedupe Rules

Only the raw adapter payload mirror currently enforces built-in storage dedupe:

- table: `observation_adapter_payload`
- mechanism: partial unique index on `(instrument, dedup_key, payload_hash)`

All other append-only tables expect the caller to supply stable ids and only emit a new row when a logically new fact or derived result exists.

## Operator Notes

- Do not manually edit append-only tables to patch data quality issues.
- If derived state is wrong, keep observations, clear rebuildable derived tables, and rerun deterministic rebuild.
- If a profile or build is superseded, add a new version and switch `is_active`; do not mutate ontology or silently rewrite old version identities.
- Dead-letter rows are evidence, not temporary scratch data.
