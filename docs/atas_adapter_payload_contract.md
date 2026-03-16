# ATAS Adapter Payload Contract

## Status

- `status`: `proposed_contract`
- `scope`: phase-1 adapter-to-local-service integration
- `transport`: local REST over HTTP

This document turns the collector checklist into a formal payload contract for the future ATAS adapter.

The contract is intentionally split into:

- `continuous_state`
- `trigger_burst`
- `durable_snapshot`

This keeps ATAS lightweight during live trading while still preserving the evidence needed for later AI analysis and replay.

## Contract Principles

- `observed facts only`
  - the adapter should emit measurements, references, timing, and outcomes
  - it should not emit strategy conclusions like "go long now"
- `continuous low-load, triggered high-fidelity`
  - always-on payloads should stay compact
  - raw detail should be emitted only when a meaningful event occurs
- `Windows and PowerShell friendly`
  - JSON over HTTP
  - UTF-8
  - small, explicit objects
- `stable identifiers`
  - every important object should have an id that survives updates and revisits

## Message Families

### 1. `continuous_state`

Purpose:

- always-on, low-overhead adapter stream
- preserves the current market script state without sending full raw replay data

Recommended cadence:

- every `1 second`
- or every `250ms` to `1000ms` depending on performance budget

Suggested endpoint:

- `POST /api/v1/adapter/continuous-state`

### 2. `trigger_burst`

Purpose:

- event-driven high-fidelity burst
- captures short raw windows around important interactions

Trigger examples:

- price approaches significant liquidity
- large-liquidity track gets pulled or filled
- first touch of a gap
- measured move crosses `1.0x` or `2.0x`
- failed continuation becomes a probe reversal
- overhead wall fails to stop the ascent

Suggested endpoint:

- `POST /api/v1/adapter/trigger-burst`

### 3. `durable_snapshot`

Purpose:

- lower-frequency durable state handoff for the existing domain model
- as of the current implementation, this bridge is performed server-side after raw adapter storage
- the current server bridge targets:
  - `market_structure` from `continuous_state`
  - `event_snapshot` from `trigger_burst`
- `depth_snapshot` remains a separate direct ingestion path

Recommended cadence:

- every `5m` or `10m`
- and additionally on important event boundaries

Suggested endpoints:

- `POST /api/v1/ingestions/market-structure`
- `POST /api/v1/ingestions/event-snapshot`
- `POST /api/v1/ingestions/depth-snapshot`

## Common Envelope

Every adapter message should include:

```json
{
  "schema_version": "1.0.0",
  "message_id": "adapter-msg-...",
  "message_type": "continuous_state",
  "emitted_at": "2026-03-16T14:30:01Z",
  "observed_window_start": "2026-03-16T14:30:00Z",
  "observed_window_end": "2026-03-16T14:30:01Z",
  "source": {
    "system": "ATAS",
    "instance_id": "DESKTOP-ATAS-01",
    "adapter_version": "0.4.0"
  },
  "instrument": {
    "symbol": "NQM6",
    "venue": "CME",
    "tick_size": 0.25,
    "currency": "USD"
  }
}
```

Required common fields:

- `schema_version`
- `message_id`
- `message_type`
- `emitted_at`
- `observed_window_start`
- `observed_window_end`
- `source`
- `instrument`

## `continuous_state` Contract

Purpose:

- current script state
- current session references
- current significant liquidity
- current measured push or pull

### Required top-level fields

- common envelope
- `session_context`
- `price_state`
- `trade_summary`
- `significant_liquidity`

### Optional top-level fields

- `gap_reference`
- `active_initiative_drive`
- `active_manipulation_leg`
- `active_measured_move`
- `active_post_harvest_response`
- `active_zone_interaction`
- `ema_context`
- `reference_levels`

### `session_context`

Required fields:

- `session_code`
- `trading_date`
- `is_rth_open`
- `prior_rth_close`
- `prior_rth_high`
- `prior_rth_low`
- `prior_value_area_low`
- `prior_value_area_high`
- `prior_point_of_control`
- `overnight_high`
- `overnight_low`
- `overnight_mid`

### `price_state`

Required fields:

- `last_price`
- `best_bid`
- `best_ask`
- `local_range_low`
- `local_range_high`
- `opening_range_low`
- `opening_range_high`
- `opening_range_size_ticks`

### `trade_summary`

Required fields:

- `trade_count`
- `volume`
- `aggressive_buy_volume`
- `aggressive_sell_volume`
- `net_delta`

### `significant_liquidity[]`

Each item should include:

- `track_id`
- `side`
- `price`
- `current_size`
- `max_seen_size`
- `distance_from_price_ticks`
- `first_observed_at`
- `last_observed_at`
- `status`
- `touch_count`
- `executed_volume_estimate`
- `replenishment_count`
- `pull_count`
- `move_count`
- `price_reaction_ticks`
- `heat_score`

### `gap_reference`

If a gap is active or recently relevant:

- `gap_id`
- `direction`
- `opened_at`
- `gap_low`
- `gap_high`
- `gap_size_ticks`
- `first_touch_at`
- `max_fill_ticks`
- `fill_ratio`
- `fill_attempt_count`
- `accepted_inside_gap`
- `rejected_from_gap`
- `fully_filled_at`

### `active_initiative_drive`

If a live drive is in progress:

- `drive_id`
- `side`
- `started_at`
- `price_low`
- `price_high`
- `aggressive_volume`
- `net_delta`
- `trade_count`
- `consumed_price_levels`
- `price_travel_ticks`
- `max_counter_move_ticks`
- `continuation_seconds`

### `active_manipulation_leg`

If a forcing leg is active or just completed:

- `leg_id`
- `side`
- `started_at`
- `ended_at`
- `price_low`
- `price_high`
- `displacement_ticks`
- `primary_objective_ticks`
- `secondary_objective_ticks`
- `primary_objective_reached`
- `secondary_objective_reached`

### `active_measured_move`

If a live measured move ladder is active:

- `measurement_id`
- `measured_subject_id`
- `measured_subject_kind`
- `side`
- `anchor_price`
- `latest_price`
- `achieved_distance_ticks`
- `reference_kind`
- `reference_id`
- `reference_distance_ticks`
- `achieved_multiple`
- `body_confirmed_threshold_multiple`
- `next_target_multiple`
- `invalidated`

### `active_post_harvest_response`

If a visible liquidity objective has just been completed:

- `response_id`
- `harvest_subject_id`
- `harvest_subject_kind`
- `harvest_side`
- `harvest_completed_at`
- `harvested_price_low`
- `harvested_price_high`
- `completion_ratio`
- `continuation_ticks_after_completion`
- `consolidation_range_ticks`
- `pullback_ticks`
- `reversal_ticks`
- `seconds_to_first_pullback`
- `seconds_to_reversal`
- `reached_next_opposing_liquidity`
- `next_opposing_liquidity_price`
- `post_harvest_delta`
- `outcome`

### `active_zone_interaction`

If a small probe, failed continuation, or defense is active:

- `zone_id`
- `zone_low`
- `zone_high`
- `started_at`
- `executed_volume_against`
- `replenishment_count`
- `buyers_hitting_same_level_count`
- `sellers_hitting_same_level_count`
- `pull_count`
- `price_rejection_ticks`
- `seconds_held`

### `ema_context`

Recommended optional fields:

- `ema20`
- `ema20_distance_ticks`
- `ema20_slope`
- `ema20_reclaim_confirmed`
- `bars_above_ema20_after_reclaim`

## `trigger_burst` Contract

Purpose:

- preserve raw evidence around meaningful events
- keep the adapter lightweight the rest of the time

### Required top-level fields

- common envelope
- `trigger`
- `pre_window`
- `event_window`
- `post_window`

### `trigger`

Required fields:

- `trigger_id`
- `trigger_type`
- `triggered_at`
- `price`
- `reason_codes`

Recommended `trigger_type` values:

- `significant_liquidity_near_touch`
- `liquidity_pull`
- `liquidity_fill`
- `gap_first_touch`
- `gap_partial_fill`
- `measured_move_threshold`
- `probe_reversal_candidate`
- `failed_overhead_capping`
- `offer_reversal_release`
- `harvest_completed`
- `post_harvest_pullback`
- `post_harvest_reversal`

### `pre_window`, `event_window`, `post_window`

Each window may contain:

- `trade_events`
- `depth_events`
- `second_features`
- `price_levels`
- `bookmarks`

### `trade_events[]`

Each event:

- `event_time`
- `local_sequence`
- `price`
- `size`
- `aggressor_side`
- `best_bid_before`
- `best_ask_before`
- `best_bid_after`
- `best_ask_after`

### `depth_events[]`

Each event:

- `event_time`
- `track_id`
- `side`
- `price`
- `size_before`
- `size_after`
- `status_before`
- `status_after`
- `distance_from_price_ticks`

### `second_features[]`

Each item:

- `second_started_at`
- `second_ended_at`
- `open`
- `high`
- `low`
- `close`
- `trade_count`
- `volume`
- `delta`
- `best_bid`
- `best_ask`
- `depth_imbalance`

### `bookmarks[]`

Bookmarks help later replay:

- `kind`
- `event_time`
- `price`
- `notes`

Useful bookmark kinds:

- `probe_entry`
- `probe_invalidation`
- `ema20_reclaim`
- `upper_liquidity_touch`
- `gap_edge_touch`
- `measured_1x`
- `measured_2x`

## `durable_snapshot` Contract

Purpose:

- keep using the current service contracts
- map adapter facts into durable higher-level ingestions

The current server automatically transforms stored adapter payloads into:

- `MarketStructurePayload` from `continuous_state`
- `EventSnapshotPayload` from `trigger_burst`

Each adapter response now carries:

- raw adapter `ingestion_id`
- `durable_outputs`: durable ingestion and analysis ids created by the bridge
- `bridge_errors`: non-fatal bridge failures if raw storage succeeded but durable transformation failed

Recommended mapping:

- `continuous_state.significant_liquidity`
  - feeds `DepthSnapshotPayload.significant_levels`
- `continuous_state.active_initiative_drive`
  - feeds `ObservedInitiativeDrive`
- `continuous_state.active_measured_move`
  - feeds `ObservedMeasuredMove`
- `continuous_state.active_manipulation_leg`
  - feeds `ObservedManipulationLeg`
- `continuous_state.gap_reference`
  - feeds `ObservedGapReference`
- `trigger_burst` highlights
  - feed `observed_events`

## JSON Examples

This contract is accompanied by sample files:

- [atas_adapter.continuous_state.sample.json](/D:/docker/atas-market-structure/samples/atas_adapter.continuous_state.sample.json)
- [atas_adapter.trigger_burst.sample.json](/D:/docker/atas-market-structure/samples/atas_adapter.trigger_burst.sample.json)

## Non-Goals

The adapter should not:

- emit auto-trading commands
- emit hard-coded trade recommendations
- persist the full order book forever
- label everything as SMC or ICT objects at source time
- hide timing order inside over-aggregated summaries

## Design Test

The contract is good enough if the adapter can explain a case like this:

1. price rallies into visible upper liquidity
2. the cap tries to hold but only causes a shallow pullback
3. aggressive buyers return quickly
4. the move reclaims `EMA20`
5. price pushes back into the same upper wall
6. the wall starts getting consumed

If that full sequence can be preserved without guessing, the contract is on the right track.
