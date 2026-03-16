# ATAS Required Fields Checklist

## Purpose

This document converts the current market-script doctrine into a concrete ATAS collection checklist.

The goal is not to collect "more data."
The goal is to collect the minimum set of durable observed facts needed to rebuild:

- support and resistance from prior effort
- liquidity attraction and suppression
- manipulation legs and measured travel
- gap-fill and opening-auction scripts
- revisit behavior and short-term memory

This checklist is object-first, not indicator-first.

## Design Rule

The collector should be designed around these questions:

- what happened
- where it happened
- how far it pushed
- whether price accepted or rejected it
- what should be remembered when price revisits the area

That means the collector should preserve:

- `observed facts`
- event timing
- measured travel
- reference prices
- revisit outcomes

It should not preserve:

- every DOM change forever
- chart cosmetics
- unsupported explanations at source time

## Collection Layers

### 1. Continuous Base Layer

Always-on, lower-overhead fields:

- session code and clock state
- multi-timeframe bars
- second-level price path
- second-level trade and delta summaries
- best bid and ask state
- significant liquidity tracks only
- current gap state

This layer keeps the script alive.

### 2. Triggered High-Fidelity Layer

Only around meaningful events:

- approach to key zone
- first touch of gap edge
- large-liquidity fill or pull
- failed downside continuation
- upward or downward release
- measured move threshold confirmation

This layer should preserve a short raw window before and after the event.

### 3. Short-Lived Memory Layer

Retain only high-value remembered facts:

- significant large-order tracks
- exertion zones
- revisit results
- gap references still open or recently repaired
- manipulation traces

Default memory horizon:

- `depth memory`: about `3 days`
- `script memory`: at least same-day plus recent prior session references

## Required Object Families

### A. Session And Environment

These fields support:

- Europe build versus U.S. release
- opening context
- gap scripts
- garbage-time filtering

Required fields:

- `symbol`
- `venue`
- `tick_size`
- `session_code`
- `session_started_at`
- `session_ended_at`
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

Suggested storage target:

- `ObservedSessionWindow`
- `decision_layers.*.raw_features`

### B. Price Path And Bars

These fields support:

- structure segments
- measured travel
- EMA20 mean reversion context
- range amplitude and opening range logic

Required fields:

- `bar_start`
- `bar_end`
- `timeframe`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `delta`
- `trade_count`
- `bid_volume`
- `ask_volume`
- `ticks`

Recommended computed facts:

- `ema20`
- `ema20_distance_ticks`
- `ema20_slope`
- `opening_range_high`
- `opening_range_low`
- `opening_range_size_ticks`
- `local_range_size_ticks`
- `overlap_ratio`

Suggested storage target:

- `ObservedContextWindow`
- `ObservedSecondFeature`
- `decision_layers.*.raw_features`

### C. Significant Displayed Liquidity

These fields support:

- large upper pressure bands
- lower support building
- liquidity attraction
- spoof versus fill versus real defense
- same-price replenishment strength

Required fields:

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
- `same_price_replenishment_count`
- `pull_count`
- `move_count`
- `price_reaction_ticks`
- `heat_score`
- `coverage_state`

Suggested storage target:

- `ObservedLargeLiquidityLevel`
- `LiquidityMemoryRecord`

### D. Trade And Aggression

These fields support:

- initiative drives
- delta-confirmed release
- failure to continue
- upward or downward repricing

Required fields:

- `event_time`
- `price`
- `size`
- `aggressor_side`
- `best_bid_before`
- `best_ask_before`
- `best_bid_after`
- `best_ask_after`
- `local_sequence`

Recommended aggregate fields per second or event window:

- `aggressive_buy_volume`
- `aggressive_sell_volume`
- `net_delta`
- `trade_count`
- `burst_per_second`
- `consumed_price_levels`

Suggested storage target:

- raw event layer
- `ObservedSecondFeature`
- `ObservedInitiativeDrive`

### E. Zone Interaction

These fields support:

- small probe entries
- failed continuation
- defended base
- absorption and non-response
- same-price defended launchpads

Required fields:

- `zone_low`
- `zone_high`
- `started_at`
- `ended_at`
- `executed_volume_against`
- `replenishment_count`
- `buyers_hitting_same_level_count`
- `sellers_hitting_same_level_count`
- `pull_count`
- `price_rejection_ticks`
- `max_resting_bid_or_ask`
- `seconds_held`

Suggested storage target:

- `ObservedLiquidityEpisode`

### F. Initiative Drive

These fields support:

- the active push itself
- who moved the market
- whether the push had real continuation

Required fields:

- `drive_id`
- `started_at`
- `ended_at`
- `side`
- `price_low`
- `price_high`
- `aggressive_volume`
- `net_delta`
- `trade_count`
- `consumed_price_levels`
- `price_travel_ticks`
- `max_counter_move_ticks`
- `continuation_seconds`

Suggested storage target:

- `ObservedInitiativeDrive`

### G. Manipulation Leg

These fields support:

- forcing legs
- trap setup
- later measured travel

Required fields:

- `leg_id`
- `started_at`
- `ended_at`
- `side`
- `price_low`
- `price_high`
- `displacement_ticks`
- `linked_zone_id`
- `primary_objective_ticks`
- `secondary_objective_ticks`
- `primary_objective_reached`
- `secondary_objective_reached`

Suggested storage target:

- `ObservedManipulationLeg`

### H. Measured Move

These fields support:

- `1x` manipulation leg
- `2x` manipulation leg
- `x` local range amplitude
- body-confirmed threshold ladders

Required fields:

- `measurement_id`
- `measured_subject_id`
- `measured_subject_kind`
- `started_at`
- `ended_at`
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

Suggested storage target:

- `ObservedMeasuredMove`

### I. Exertion Zone

These fields support:

- support and resistance from prior effort
- trapped inventory watch
- flip logic
- revisit importance

Required fields:

- `zone_id`
- `source_drive_id`
- `side`
- `price_low`
- `price_high`
- `established_at`
- `last_interacted_at`
- `establishing_volume`
- `establishing_delta`
- `establishing_trade_count`
- `peak_price_level_volume`
- `revisit_count`
- `successful_reengagement_count`
- `failed_reengagement_count`
- `last_revisit_delta`
- `last_revisit_volume`
- `last_revisit_trade_count`
- `last_defended_reaction_ticks`
- `last_failed_break_ticks`
- `post_failure_delta`
- `post_failure_move_ticks`

Suggested storage target:

- `ObservedExertionZone`
- `DerivedKeyLevelAssessment`

### J. Gap Reference

These fields support:

- whether a gap exists
- whether it is partially filled
- whether a full fill remains likely
- whether the fill was accepted or rejected

Required fields:

- `gap_id`
- `session_code`
- `opened_at`
- `direction`
- `prior_reference_price`
- `current_open_price`
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

Suggested storage target:

- `ObservedGapReference`
- `DerivedGapAssessment`

### K. Cross-Session Sequence

These fields support:

- Europe build and U.S. release
- session hand-off
- multi-stage campaigns

Required fields:

- `sequence_id`
- `started_at`
- `last_observed_at`
- `session_sequence`
- `price_zone_low`
- `price_zone_high`
- `start_price`
- `latest_price`
- `linked_episode_ids`
- `linked_drive_ids`
- `linked_exertion_zone_ids`
- `linked_event_ids`

Suggested storage target:

- `ObservedCrossSessionSequence`

### L. Post-Harvest Response

These fields support:

- what happened after a visible liquidity objective was already completed
- whether price balanced, pulled back, or fully reversed
- whether lower liquidity became the next magnet after an upper harvest

Required fields:

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

Suggested storage target:

- `ObservedPostHarvestResponse`

## Pattern Coverage Map

### 1. Europe Large Offer Breakdown

Must preserve:

- upper ask wall
- downside initiative drive
- measured downside travel
- later revisit of the suppressor band

Critical objects:

- `ObservedLargeLiquidityLevel`
- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`
- `ObservedExertionZone`

### 2. Probe Reversal Toward Upper Liquidity

Must preserve:

- upper attractor band
- local failed continuation
- small probe zone
- upward reclaim toward EMA20

Critical objects:

- `ObservedLargeLiquidityLevel`
- `ObservedLiquidityEpisode`
- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`
- `ema20_*` raw features

### 3. Europe Offer Reversal Into Upper Liquidity

Must preserve:

- earlier suppression band
- lower support build
- upward initiative release
- actual consumption or challenge of upper liquidity

Critical objects:

- `ObservedLargeLiquidityLevel`
- `ObservedLiquidityEpisode`
- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`
- `ObservedExertionZone`

### 4. Gap Fill Script

Must preserve:

- prior RTH close and current open
- gap size
- first touch
- partial or full fill depth
- acceptance or rejection after fill

Critical objects:

- `ObservedGapReference`
- `ObservedMeasuredMove`
- `ObservedSessionWindow`

### 5. Failed Overhead Capping In Ascent

Must preserve:

- visible upper sell wall during an ongoing ascent
- shallow pullback rather than structural failure
- renewed aggressive lift after the pullback
- later challenge or consumption of the same upper wall

Critical objects:

- `ObservedLargeLiquidityLevel`
- `ObservedLiquidityEpisode`
- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`
- `ema20_*` and pullback-depth raw features

### 6. Replenished Bid Launchpad Into Upper Liquidity

Must preserve:

- same-price bid replenishment
- aggressive selling absorbed at the same level
- buyers repeatedly lifting from the defended area
- later move toward upper liquidity

Critical objects:

- `ObservedLargeLiquidityLevel`
- `ObservedLiquidityEpisode`
- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`

### 7. Upper Liquidity Harvest Then Lower Relocation

Must preserve:

- upper liquidity completion
- immediate continuation after completion
- post-harvest balance or pullback
- possible larger reversal toward lower liquidity

Critical objects:

- `ObservedInitiativeDrive`
- `ObservedLargeLiquidityLevel`
- `ObservedPostHarvestResponse`

## Trigger Conditions For High-Fidelity Burst

High-fidelity capture should start when any of these occur:

- price comes within `X ticks` of a significant liquidity track
- a significant liquidity track changes from `active` to `pulled`, `filled`, or `partially_filled`
- an initiative drive begins from a known exertion zone
- a measured move crosses `1.0x`, `2.0x`, or another configured threshold
- a gap is first touched
- a gap transitions from untouched to partial fill
- `EMA20` reclaim or failure occurs near a key zone
- an overhead liquidity band fails to stop price after a shallow pullback
- the same defended level is replenished multiple times while aggressive orders keep hitting it
- a completed harvest shifts into post-harvest pullback or reversal

The burst window should include:

- short pre-event raw buffer
- event-time raw burst
- short post-event raw buffer

## What The Collector Can Defer

These can stay out of phase-1 ATAS collection if needed:

- full-book permanent DOM storage
- full historical MBO replay
- complex SMC labels at source time
- fixed setup names
- auto-trading outputs

## Minimum Viable Collector Output

If the ATAS side can only do one practical first version, it should still emit:

- stable session references
- 1-second trade and price-path summaries
- significant liquidity tracks only
- initiative drives
- exertion zones
- gap references
- measured moves
- short high-fidelity windows around trigger events

That is enough for the local service to reconstruct:

- support and resistance context
- manipulation and measured travel
- liquidity attraction and suppression
- gap-fill scripts
- revisit logic

## Design Test

The checklist is complete enough if the system can later explain a case like this:

1. Europe session builds under a visible upper sell wall
2. price first respects the wall
3. lower support responds and aggressive buying starts lifting price
4. the move travels `2x` the local manipulation leg
5. price reaches and starts consuming the old upper liquidity
6. the old suppressor band becomes a key revisit zone

If the collector cannot preserve each of those steps as observed facts, the checklist is still missing something important.
