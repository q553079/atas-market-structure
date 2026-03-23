# Recognition Pipeline V1

## Scope

This V1 implementation follows `docs/k_repair/replay_workbench_master_spec_v2.md` and the event-model docs under `docs/replay_workbench_event_model/`.

Hard constraints kept in code:

- AI is not on the deterministic recognition critical path.
- Observed facts stay in append-only observation/ingestion storage.
- Derived interpretation is emitted into append-only derived tables.
- Fixed ontology stays stable for regime, event hypothesis, phase, and evaluation objects.
- Missing depth/DOM degrades output instead of failing the pipeline.
- All derived outputs carry `schema_version`, `profile_version`, and `engine_version`.
- V1 closes the loop only for:
  - `momentum_continuation`
  - `balance_mean_reversion`
  - `absorption_to_reversal_preparation`

## Repo Scan And Reuse

Existing files reused as the backbone:

- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/storage_repository.py`
- `src/atas_market_structure/storage_models.py`
- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/services.py`
- `src/atas_market_structure/adapter_services.py`
- `src/atas_market_structure/ingestion_reliability_services.py`
- `src/atas_market_structure/app.py`

Recognition-specific modules added under `src/atas_market_structure/recognition/`:

- `feature_builder.py`
- `regime_updater.py`
- `anchor_manager.py`
- `event_updater.py`
- `belief_emitter.py`
- `episode_closer.py`
- `degraded_mode.py`
- `defaults.py`
- `pipeline.py`
- `types.py`

## Trigger Chain

Recognition runs only after raw data has already been stored.

Store-first trigger points:

- `market_structure` and `event_snapshot` through `IngestionOrchestrator`
- `process_context` and `depth_snapshot` through `IngestionReliabilityService`
- `adapter_history_bars` through `AdapterIngestionService`

This keeps ingestion durable even if downstream recognition later fails.

## Deterministic Pipeline

`DeterministicRecognitionService` executes the following sequence:

1. Bootstrap active `instrument_profile` and `recognizer_build` if missing.
2. Evaluate degraded mode, freshness, and completeness with `RecognitionQualityEvaluator`.
3. Read append-only observations and recent ingestions to build one `RecognitionFeatureVector`.
4. Persist one append-only `feature_slice`.
5. Build and persist append-only `regime_posterior`.
6. Refresh versioned `memory_anchor_version` rows plus append-only `anchor_interaction` rows.
7. Build and persist append-only `event_hypothesis_state` rows.
8. Build and persist one append-only `belief_state_snapshot`.
9. Close append-only `event_episode` and `event_episode_evidence` rows when the lead hypothesis resolves, invalidates, or gets replaced.

Observed vs derived separation in practice:

- Readers: ingestion tables and observation tables only.
- Writers: `feature_slice`, `regime_posterior`, `event_hypothesis_state`, `belief_state_snapshot`, `event_episode`, `event_episode_evidence`.
- Versioned state writers: `instrument_profile`, `recognizer_build`, `memory_anchor_version`, current `memory_anchor`.

## Evidence Buckets

V1 feature slices emit all required evidence buckets:

- `bar_structure`
- `volatility_range`
- `trend_efficiency`
- `initiative`
- `balance`
- `absorption`
- `depth_dom`
- `anchor_interaction`
- `path_dependency`

The current skeleton intentionally keeps scoring rules explicit and small:

- trend and initiative dominate momentum cases
- balance and anchor attraction dominate mean-reversion cases
- absorption and transition behavior dominate reversal-preparation cases

No generic black-box score is used.

## Degraded Recognition

The pipeline stays operational when some sources are missing.

Current degraded handling:

- No depth or DOM:
  - `data_status.depth_available = false`
  - `data_status.dom_available = false`
  - `depth_dom` bucket is marked unavailable
  - `recognition_mode = bar_anchor_only`
  - health/status still reports degraded reasons such as `degraded_no_depth` and `degraded_no_dom`
- Stale macro/process context:
  - `stale_macro` is attached in `data_status.degraded_modes`
  - regime and hypothesis probabilities are flattened before ranking
- Replay rebuild mode:
  - `recognition_mode = replay_rebuild_mode`
  - completeness is reduced to `gapped`
- No AI:
  - `no_ai` is recorded in `data_status`
  - recognition still runs normally because AI is off the critical path

## Belief State Output

`BeliefStateSnapshot` persists the main UI/review surface and currently includes:

- top 3 regime probabilities
- top 3 event hypotheses
- active anchors
- aggregated `missing_confirmation`
- aggregated `invalidating_signals_seen`
- aggregated `transition_watch`
- `data_status`
- `profile_version`
- `engine_version`
- `schema_version`

## Event Episode Output

`EventEpisodeBuilder` closes episodes from belief-state transitions.

V1 closure rules implemented:

- `resolved` lead hypothesis closes a `confirmed` episode
- `invalidated` lead hypothesis closes an `invalidated` episode
- lead-event replacement closes the previous event as `replaced`

Each closed episode carries:

- fixed `phase`
- terminal `resolution`
- optional `replacement_event_kind`
- condensed `key_evidence_summary`
- `data_status`
- `profile_version`
- `engine_version`
- `schema_version`

## Storage Lifecycle

Append-only derived tables used by this pipeline:

- `feature_slice`
- `regime_posterior`
- `event_hypothesis_state`
- `belief_state_snapshot`
- `event_episode`
- `event_episode_evidence`
- `anchor_interaction`

Versioned or current-state tables touched by this pipeline:

- `instrument_profile`
- `recognizer_build`
- `memory_anchor`
- `memory_anchor_version`

This keeps rebuild compatibility with the storage blueprint:

- raw observations remain immutable
- derived layers can be cleared and rebuilt from observations
- profile/build/anchor state remains versioned instead of overwritten in-place without history

## Samples

Canonical belief-state samples for the three V1 tradable-event paths:

- `samples/recognition/momentum_continuation.sample.json`
- `samples/recognition/balance_mean_reversion.sample.json`
- `samples/recognition/absorption_to_reversal_preparation.sample.json`

## Verification

Targeted test commands:

```powershell
python -m pytest tests/test_recognition_pipeline.py -q
python -m pytest tests/test_ingestion_reliability.py tests/test_app.py tests/test_recognition_pipeline.py -q
```

Current deterministic coverage checks:

- momentum continuation hypothesis dominance
- balance mean-reversion dominance
- absorption/reversal degraded execution without depth
- stale macro degraded mode while belief output still remains available
