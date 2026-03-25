# Replay Workbench Event Outcome Ledger Design

## Purpose

Event Outcome Ledger evaluates replay-workbench event objects. It does not replace `episode_evaluation`, which evaluates deterministic recognition episodes.

## Relation To Episode Evaluation

- `episode_evaluation`
  Evaluates recognition-layer event episodes produced by the deterministic pipeline.
- `event_outcome_ledger`
  Evaluates workbench-layer `EventCandidate` objects and promoted plans shown to the operator.

The two systems can coexist and later be compared, but they should not share names or semantics blindly.

## Object Model

Primary persisted object:

- `EventOutcomeLedger`

Key fields:

- `outcome_id`
- `event_id`
- `session_id`
- `source_message_id`
- `source_prompt_trace_id`
- `analysis_preset`
- `model_name`
- `symbol`
- `timeframe`
- `event_kind`
- `born_at`
- `observed_price`
- `target_rule`
- `invalidation_rule`
- `evaluation_window_start`
- `evaluation_window_end`
- `expiry_policy`
- `realized_outcome`
- `outcome_label`
- `mfe`
- `mae`
- `hit_target`
- `hit_stop`
- `timed_out`
- `inconclusive`
- `evaluated_at`
- `metadata`

`realized_outcome` is nullable so open windows can stay pending. User-facing settled badges remain:

- `success`
- `failure`
- `timeout`
- `inconclusive`

## Settlement Rules

Minimum deterministic rule set:

1. `success`
   Target rule is hit before invalidation rule.
2. `failure`
   Invalidation rule is hit before target rule.
3. `timeout`
   Evaluation window expires without a settled result.
4. `inconclusive`
   Data is missing or one candle hits both target and invalidation so order cannot be known.

Open windows remain pending internally until expiry or settlement.

## Supported Event Kinds In This Slice

First-class deterministic settlement is implemented for:

- `key_level`
- `price_zone`
- `market_event`
- `plan_intent`

Other kinds can still persist a ledger row, but may stay pending or settle to `inconclusive` when no explicit rule can be derived.

## Evaluation Inputs

Priority order:

1. `EventCandidate` fields
2. `EventCandidate.metadata`
3. `EventCandidate.invalidation_rule`
4. `EventCandidate.evaluation_window`
5. linked Prompt Trace metadata for `analysis_preset` and `model_name`
6. chart candles for price-path evaluation

## Stats Definitions

Summary and breakdown stats count:

- `total_count`
- `settled_count`
- `open_count`
- `success_count`
- `failure_count`
- `timeout_count`
- `inconclusive_count`
- `accuracy_rate`
- `failure_rate`
- `timeout_rate`
- `inconclusive_rate`

Rates are computed over `settled_count`, not `total_count`.

## Time Window Breakdown

`by-time-window` groups rows by UTC hour bucket derived from `born_at`:

- example: `2026-03-25 09:00 UTC`

This keeps the grouping explicit and auditable.

## Compatibility Strategy

- Outcome APIs are additive.
- Existing event cards and plan cards keep rendering even when no outcome exists.
- Frontend badges are decoration-only on top of current event and plan markup.
