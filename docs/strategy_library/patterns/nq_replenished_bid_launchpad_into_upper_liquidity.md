# NQ Replenished Bid Launchpad Into Upper Liquidity

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes a strong local launch area where:

- the same bid price keeps getting replenished
- sellers keep hitting that level
- price does not lose the level cleanly
- buyers continue printing aggressive orders from the same area
- the market later uses that defended area as a launchpad toward upper liquidity

The key idea is:

- this is not support just because a line exists there
- it becomes meaningful because the same level keeps getting reloaded and survives pressure

## Observed Facts To Preserve

- one bid price or narrow bid zone is replenished repeatedly
- aggressive sellers keep trading into that zone
- price rejection from the zone stays small and controlled
- buyers later start lifting from that same defended area
- the move begins targeting higher visible liquidity

## System Mapping

### 1. Replenished Bid

Use:

- `ObservedLargeLiquidityLevel`
- `LiquidityMemoryRecord`

Important facts:

- `price`
- `current_size`
- `max_seen_size`
- `touch_count`
- `replenishment_count`
- `executed_volume_estimate`

### 2. Zone Interaction

Use:

- `ObservedLiquidityEpisode`

Important facts:

- `executed_volume_against`
- `replenishment_count`
- `price_rejection_ticks`
- `seconds_held`

### 3. Upward Release

Use:

- `ObservedInitiativeDrive`
- `ObservedMeasuredMove`

Important facts:

- aggressive buy volume after the defense
- delta alignment
- measured travel toward upper liquidity

## Derived Interpretation

These belong in `derived interpretation`:

- `same_price_replenishment_present`
- `defended_bid_launchpad`
- `buyers_hitting_same_level`
- `upper_liquidity_target_active`

## Recommended Future Fields

- `same_price_replenishment_count`
- `buyers_hitting_same_level_count`
- `launchpad_hold_seconds`
- `launchpad_rejection_ticks`
- `launchpad_to_target_ticks`
- `upper_liquidity_tagged`

## Confirmation Signals

- the same price or narrow zone gets reloaded across multiple tests instead of appearing only once
- price stops making clean lower lows and begins reclaiming from the defended area
- an upper liquidity target remains available and price starts traveling toward it

## No-Trade Conditions

- do not buy because one large bid flashes on the DOM without repeated same-price replenishment
- do not buy if replenishment stops and price starts accepting below the defended zone
- do not call the zone strong support when the bigger context is still pushing directly into a stronger opposing region above

## Review Questions

- what specific evidence justified upgrading the level from visible support to strong defended support
- did the entry wait for reclaimed structure, or was it placed too early against active sell pressure
- after the launch, did the defended area remain valid on revisit or fail immediately
