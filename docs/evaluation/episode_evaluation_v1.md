# Episode Evaluation V1

This document describes the `episode_evaluation_v1` implementation added for Master Spec v2.

## Scope

The goal of `episode_evaluation_v1` is not PnL accounting.

It standardizes where deterministic recognition was early, late, overconfident, or slow to switch so the output can feed:

- replay review
- operator diagnosis
- offline tuning review
- AI tuning input preparation

Hard constraints kept in the implementation:

- no trading PnL logic
- no AI-generated final evaluation truth
- fixed failure-mode ontology only
- deterministic rule review first
- evaluation stays aligned with belief state, event episode, and instrument profile structures

## Repo Scan And Reuse

Existing files reused:

- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/models/_enums.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/repository.py`
- `src/atas_market_structure/profile_services.py`
- `src/atas_market_structure/recognition/pipeline.py`
- `src/atas_market_structure/recognition/episode_closer.py`
- `docs/k_repair/replay_workbench_master_spec_v2.md`
- `docs/replay_workbench_event_model/replay_workbench_event_reasoning_playbook.md`
- `docs/replay_workbench_event_model/replay_workbench_hidden_state_event_memory_model.md`
- `docs/replay_workbench_event_model/replay_workbench_tradable_event_templates.md`

Files added for this thread:

- `src/atas_market_structure/evaluation_services.py`
- `tests/test_episode_evaluation.py`
- `samples/episode_evaluations/*.json`

Files updated for this thread:

- `src/atas_market_structure/models/_enums.py`
- `src/atas_market_structure/models/_replay.py`
- `src/atas_market_structure/models/__init__.py`
- `src/atas_market_structure/recognition/types.py`
- `src/atas_market_structure/recognition/pipeline.py`

## Data Structure

`EpisodeEvaluation` now carries the `episode_evaluation_v1` shape:

- `evaluation_id`
- `episode_id`
- `instrument`
- `session`
- `bar_tf`
- `market_time_start`
- `market_time_end`
- `profile_version`
- `engine_version`
- `schema_version`
- `initial_regime_top1`
- `initial_regime_prob`
- `evaluated_event_kind`
- `initial_phase`
- `initial_prob`
- `declared_time_window`
- `anchor_context`
- `lifecycle`
- `outcome`
- `scores`
- `diagnosis`
- `tuning_hints`
- `evaluated_at`

Nested objects:

- `EpisodeEvaluationDeclaredTimeWindow`
- `EpisodeEvaluationLifecycle`
- `EpisodeEvaluationOutcome`
- `EpisodeEvaluationScorecard`
- `EpisodeEvaluationDiagnosis`
- `EpisodeEvaluationTuningHints`

## Review Sources

The model supports:

- `rule_review_v1`
- `human_review_v1`
- `hybrid_review_v1`

V1 generator support is implemented only for `rule_review_v1`.

## Failure Mode Ontology

The fixed V1 failure modes are:

- `none`
- `early_confirmation`
- `late_confirmation`
- `late_invalidation`
- `missed_transition`
- `false_positive`
- `false_negative`

No additional ad hoc labels are introduced.

## Five Scores

The scorecard uses the Master Spec v2 scale `-2 / -1 / 0 / +1 / +2`.

Dimensions:

- `hypothesis_selection_score`
- `confirmation_timing_score`
- `invalidation_timing_score`
- `transition_handling_score`
- `calibration_score`

Current rule-review interpretation:

- positive values mean the engine handled that dimension appropriately
- zero means neutral or not applicable
- negative values indicate a timing, selection, or calibration problem worth review

## rule_review_v1 Logic

`EpisodeEvaluationService` reconstructs one review context from:

- one closed `EventEpisode`
- belief-state history around the episode window
- the active `InstrumentProfile`

Rule-review flow:

1. collect belief snapshots inside the episode window plus one prior and one next snapshot when available
2. extract the event-specific hypothesis state from each relevant belief
3. reconstruct lifecycle landmarks:
   - first validation
   - peak probability
   - first invalidation
   - downgrade time
4. derive the declared time window from the profile:
   - momentum uses `strong` or `normal` based on the initial top regime
   - balance and absorption/reversal use `normal`
5. score the five dimensions
6. collapse the scores into one primary failure mode
7. produce structured diagnosis and bounded tuning hints
8. persist the append-only evaluation record

## Diagnosis Output

The structured diagnosis is designed as AI-ready but still deterministic.

It includes:

- `primary_failure_mode`
- `supporting_reasons`
- `missing_confirmation`
- `invalidating_signals_seen`
- `candidate_parameters`
- `suggested_direction`

`candidate_parameters` are always selected from the bounded profile metadata registry introduced in Thread 05.

## Tuning Hint Rules

The rule review does not auto-patch profiles.

It only proposes bounded offline-review candidates such as:

- early confirmation
  - increase confirmation thresholds
  - increase the event `bars_min`
- late confirmation
  - decrease confirmation threshold
  - increase event `bars_max`
  - increase the event prior
- late invalidation
  - increase active hypothesis threshold
  - decrease weakening drop threshold
  - reduce the dominant event weight
- missed transition
  - increase path dependency weight
  - increase anchor interaction weight
  - increase replacement-event prior
- false positive
  - reduce event prior
  - increase confirmation threshold
  - reduce the dominant event weight
- false negative
  - increase event prior
  - decrease active hypothesis threshold
  - increase the dominant event weight

These are diagnostic hints only. Promotion still requires the existing profile patch validation flow.

## Pipeline Integration

`DeterministicRecognitionService` now evaluates any newly closed episodes immediately after `EventEpisodeBuilder` emits them.

This keeps the loop:

- observations
- feature / belief / episode
- episode evaluation

closed inside the deterministic stack without adding AI to the critical path.

Stored records continue to use the existing append-only repository path:

- legacy table: `episode_evaluations`
- storage blueprint table: `episode_evaluation`

## Sample Payloads

Current sample results live under `samples/episode_evaluations/`:

- `momentum_confirmed_none.sample.json`
- `momentum_early_confirmation.sample.json`
- `balance_late_invalidation.sample.json`
- `balance_missed_transition.sample.json`
- `momentum_false_positive.sample.json`

## Verification

Primary tests:

- `python -m pytest tests/test_episode_evaluation.py -q`

Recommended regressions after changing evaluation rules:

- `python -m pytest tests/test_recognition_pipeline.py -q`
- `python -m pytest tests/test_profile_services.py -q`
- `python -m pytest tests/test_storage_blueprint_repository.py -q`
- `python -m pytest tests/test_app.py -q`

Covered behaviors:

- timely confirmed review with `primary_failure_mode = none`
- early confirmation detection
- late invalidation detection
- missed transition detection
- false positive detection
- false negative detection
- evaluation persistence
- sample payload contract loading
