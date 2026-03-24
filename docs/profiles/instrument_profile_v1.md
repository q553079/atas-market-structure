# Instrument Profile V1

This document describes the `instrument_profile_v1` infrastructure implemented for Master Spec v2.

## Scope

The implementation keeps one fixed ontology across instruments and limits per-instrument variation to bounded parameters only.

Hard constraints enforced in code:

- ontology is fixed for regime, event hypothesis, phase, and evaluation semantics
- profile changes affect only normalization, tempo, thresholds, weights, decay, priors, and safety bounds
- `allow_ai_auto_apply` is always `false`
- patch candidates are auditable, comparable, and versionable
- invalid or out-of-bounds parameters are rejected before promotion
- AI is not allowed to rewrite ontology or auto-promote profile patches

## Repo Scan And Reuse

Existing files reused as the backbone:

- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/models/_enums.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/repository_recognition.py`
- `src/atas_market_structure/repository_evaluation_tuning.py`
- `src/atas_market_structure/repository.py` (compatibility facade only)
- `src/atas_market_structure/storage_repository.py`
- `src/atas_market_structure/storage_models.py`
- `src/atas_market_structure/recognition/defaults.py`
- `src/atas_market_structure/ontology.py`
- `docs/k_repair/replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/replay_workbench_hidden_state_event_memory_model.md`

Profile-specific files added for this thread:

- `src/atas_market_structure/profile_services.py`
- `src/atas_market_structure/profile_loader.py`
- `schemas/instrument_profile_v1.schema.json`
- `samples/profiles/ES.yaml`
- `samples/profiles/NQ.yaml`
- `samples/profiles/GC.yaml`
- `samples/profiles/CL.yaml`
- `tests/test_profile_services.py`

## Schema Shape

`InstrumentProfile` is now a strict typed model with `extra="forbid"`.

Top-level fields:

- `instrument`
- `profile_version`
- `schema_version`
- `ontology_version`
- `is_active`
- `created_at`
- `normalization`
- `time_windows`
- `thresholds`
- `weights`
- `decay`
- `priors`
- `safety`

The current JSON schema lives at `schemas/instrument_profile_v1.schema.json`.

## Fixed Fields Versus Adjustable Fields

Immutable or fixed fields:

- `instrument`
- `instrument_symbol`
- `profile_version`
- `schema_version`
- `ontology_version`
- `is_active`
- `created_at`
- `normalization.price_unit`
- `normalization.tick_size`
- `normalization.displacement_normalizer`
- `normalization.volume_normalizer`
- `safety.allow_ai_auto_apply`
- `safety.require_offline_validation`

Reason:

- these fields define identity, ontology contract, or hard safety posture
- mutating them through a patch would violate Master Spec v2 or break replay reproducibility

Adjustable sections:

- `normalization`
- `time_windows`
- `thresholds`
- `weights`
- `decay`
- `priors`
- selected `safety` bounds

These are bounded parameter surfaces only. The profile is not an arbitrary JSON payload bucket.

## Sample Profiles

V1 ships with:

- `samples/profiles/ES.yaml`
- `samples/profiles/NQ.yaml`
- `samples/profiles/GC.yaml`
- `samples/profiles/CL.yaml`

`ES` and `NQ` are the primary concrete examples.

`GC` and `CL` are conservative stubs that keep the same ontology and parameter surface while only adjusting bounded defaults such as:

- range normalization
- anchor operating distance
- momentum and anchor thresholds
- evidence bucket weights
- decay horizons

## Parameter Metadata Registry

`get_parameter_metadata_registry(...)` produces the bounded adjustable registry used for validation and preview.

Each adjustable parameter carries:

- `path`
- `value_type`
- `min`
- `max`
- `step`
- `safe_default`
- `criticality`
- `applies_to_events`
- `description`

Criticality currently uses:

- `low`
- `medium`
- `high`
- `critical`

The registry maps parameters to the three V1 tradable events only:

- `momentum_continuation`
- `balance_mean_reversion`
- `absorption_to_reversal_preparation`

This keeps parameter intent explicit and prevents hidden cross-event tuning.

## Build And Load Flow

`profile_services.py` provides:

- `default_tick_size_for_symbol(...)`
- `build_instrument_profile_v1(...)`
- `get_parameter_metadata_registry(...)`
- `InstrumentProfileService`

`profile_loader.py` provides:

- strict YAML loading for one file
- bulk loading from `samples/profiles/`

`recognition/defaults.py` now bootstraps from the same profile builder so runtime defaults and sample profiles share one bounded source of truth.

## Patch Candidate And Boundary Validation

`InstrumentProfileService.validate_patch(...)` accepts nested patch payloads, dotted-path payloads, and `suggested_changes[path].to` input.

Validation stages:

1. normalize the patch into dotted parameter paths
2. reject immutable or ontology-related fields
3. reject `safety.allow_ai_auto_apply`
4. reject unknown parameter paths
5. coerce numeric values to the expected primitive type
6. enforce `min` and `max`
7. enforce `step`
8. ignore no-op changes with warnings
9. produce compare/preview output only when the patch is valid

Rejected cases include:

- illegal parameter names
- ontology mutations
- out-of-bounds values
- wrong numeric type
- invalid step increments
- attempts to enable AI auto-apply

## Compare And Preview Output

Successful validation produces:

- `ProfilePatchCandidate`
- `ProfilePatchValidationResult`
- `ProfilePatchPreview`

Preview output includes:

- base profile version
- proposed profile version
- candidate parameter paths
- per-field diffs
- `from` and `to` values
- parameter metadata
- aggregated risk notes
- `requires_human_review: true`
- `allow_ai_auto_apply: false`

`InstrumentProfileService.compare_profiles(...)` is the read-only helper for preview generation. It raises on invalid patches instead of returning a partial compare.

## Audit And Persistence

Profile patch auditing reuses the storage blueprint tables added in the storage thread:

- `profile_patch_candidate`
- `patch_validation_result`

Current repository ownership for these writes is split across focused repository modules; do not add new profile/tuning persistence logic back into `repository.py`.

Repository bridge methods:

- `save_profile_patch_candidate(...)`
- `list_profile_patch_candidates(...)`
- `save_patch_validation_result(...)`
- `list_patch_validation_results(...)`

Persistence behavior:

- accepted patches are stored for operator review
- rejected patches may also be stored when `persist=True`
- validation status is explicit and auditable
- no patch is auto-applied to `instrument_profile`

This preserves compare, audit, and rollback safety:

- compare against a known base version
- validate before promotion
- store candidate and validation records
- promote only via explicit offline review flow
- roll back by switching active `profile_version`, not by mutating ontology

## Risk Notes

Risk notes are generated from metadata and change magnitude. Current rules flag cases such as:

- high or critical parameter moves
- moves more than 20% away from the safe default
- moves more than 25% from the current profile
- material threshold shifts
- low evidence weights
- large prior shifts
- large tempo-window shifts

These notes are operator-facing warnings, not auto-apply logic.

## Safety Boundaries

The implemented infrastructure deliberately does not do the following:

- does not let AI modify ontology
- does not let AI enable auto-apply
- does not let arbitrary JSON keys slip into the profile
- does not silently overwrite an existing semantic profile version
- does not move recognition onto a black-box scoring model

This keeps the profile layer explainable and rebuild-safe.

## Verification

Primary tests:

- `python -m pytest tests/test_profile_services.py -q`

Useful regression coverage after profile changes:

- `python -m pytest tests/test_storage_blueprint_repository.py -q`
- `python -m pytest tests/test_storage_migrations.py -q`
- `python -m pytest tests/test_recognition_pipeline.py -q`
- `python -m pytest tests/test_ingestion_reliability.py -q`
- `python -m pytest tests/test_app_review_routes.py -q`
- `python -m pytest tests/test_contract_schema_versions.py -q`

Covered behaviors include:

- sample profile loading
- schema presence
- metadata registry defaults
- preview diff generation
- immutable ontology rejection
- `allow_ai_auto_apply` rejection
- rejected patch audit persistence
