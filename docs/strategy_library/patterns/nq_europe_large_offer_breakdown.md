# NQ Europe Large Offer Breakdown

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes a Europe-session NQ breakdown where:

- a large displayed sell wall remains visible above price
- aggressive flow supports downside continuation
- price gets pressed lower while the upper wall keeps acting as a cap

The key point is not the heatmap band alone.
The key point is the combination of:

- `displayed liquidity pressure`
- `aggressive execution`
- `downside travel`
- `later revisit value`

## Observed Facts To Preserve

These should stay in `observed facts`, not in interpretation:

- session: `europe`
- instrument: `NQ`
- a significant ask-side liquidity track persists above price
- the wall remains close enough to act as a cap while price trends lower
- aggressive flow appears during the release leg
- price travels a measurable distance away from the origin
- later, the same wall or its price band can be revisited

## System Mapping

### 1. Displayed Liquidity

Use:

- `DepthSnapshotPayload.significant_levels`
- `ObservedLargeLiquidityLevel`

Important facts:

- `side = sell`
- `price`
- `max_seen_size`
- `distance_from_price_ticks`
- `touch_count`
- `replenishment_count`
- `pull_count`
- `price_reaction_ticks`

This is the passive cap.

### 2. Breakdown Drive

Use:

- `ObservedInitiativeDrive`

Important facts:

- downside `side`
- `aggressive_volume`
- `net_delta`
- `consumed_price_levels`
- `price_travel_ticks`
- `continuation_seconds`

This is the active push.

Important note:

- the system should not guess from the image whether the push was driven by aggressive buying or aggressive selling
- the actual aggressor side must come from ATAS trade and delta data

### 3. Manipulation / Release Leg

Use:

- `ObservedManipulationLeg`

Important facts:

- start and end of the forcing leg
- `displacement_ticks`
- `primary_objective_ticks`
- `secondary_objective_ticks`
- whether the move completed the first and second objectives

This object captures the causal leg, not only the later result.

### 4. Measured Travel

Use:

- `ObservedMeasuredMove`

Important facts:

- achieved distance in ticks
- achieved distance as:
  - `x manipulation leg`
  - `x local range amplitude`
- body-confirmed threshold
- next ladder target

This is where the system records:

- how far the breakdown actually went
- whether it only completed `1x`
- or extended to `2x` and beyond

### 5. Future Key Level

Use:

- `ObservedExertionZone`
- `DerivedKeyLevelAssessment`

If the breakdown origin later proves important, the upper cap zone becomes:

- a future resistance area
- or a flip area if later reclaimed

This is why the event must survive beyond the immediate move.

## Derived Interpretation

These belong in `derived interpretation`, not in raw observation:

- `offer_led_breakdown`
- `displayed_liquidity_cap_present`
- `pressure_assisted_release`
- `strong_resistance_candidate`
- `revisit_needed_for_confirmation`

The system should only promote these labels after enough facts exist.

## Revisit Logic

The later revisit is often more important than the first move.

When price returns to the original cap zone, the system should ask:

- is the same ask liquidity still present
- does new sell liquidity rebuild at the same band
- does price get rejected quickly again
- is the old wall gone and price accepted above it

That gives very different meanings:

- wall rebuilds and price rejects again
  - resistance gets stronger
- wall disappears and price accepts above
  - prior suppressor may have been absorbed or exhausted

## Recommended Future Fields

These are the most useful extra fields when the ATAS collector is built:

- `wall_persistence_seconds`
- `wall_heat_score`
- `release_started_at`
- `release_origin_price`
- `release_travel_ticks`
- `release_multiple_of_manip_leg`
- `release_multiple_of_local_range`
- `revisit_outcome`

## Why This Pattern Matters

This is not just a one-off chart annotation.
It is a reusable NQ script:

- visible upper pressure
- active release lower
- measurable distance
- future resistance memory

That makes it a good candidate for both:

- real-time AI attention compression
- later replay and support or resistance research

## Confirmation Signals

- the upper sell wall remains close enough to keep capping price during the release
- downside initiative expands into measurable travel instead of stalling immediately
- on revisit, the original cap zone still rejects or rebuilds as resistance

## No-Trade Conditions

- do not short only because a bright wall is visible if price has not actually released lower
- do not short in the middle of balance when there is no clean downside travel away from the cap
- do not keep pressing the short if price is already accepting above the old cap and the wall is no longer rebuilding

## Review Questions

- did the wall produce a real downside outcome, or did it only look heavy on the screen
- was the short taken after most of the measurable travel was already completed
- when price revisited the cap, did it reject again or begin accepting above it
