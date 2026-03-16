# NQ Failed Overhead Capping In Ascent

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes a strong upward campaign where:

- price has already launched higher from a lower base
- visible sell liquidity remains above price and keeps trying to cap the move
- price briefly pulls back but does not truly lose structure
- aggressive orders keep lifting the market
- the trend resumes and the overhead liquidity gets challenged or consumed

This is important because a visible overhead wall does not automatically mean reversal.
In a strong ascent, the wall can become:

- a temporary pause point
- a shallow pullback anchor
- and later a liquidity target to be harvested

## Observed Facts To Preserve

These belong in `observed facts`:

- a large ask-side liquidity band stays visible above price during the ascent
- price reaches toward the band and stalls briefly
- the pullback is relatively shallow
- price holds above the more important lower release area
- aggressive orders continue to print during the renewed lift
- price resumes upward and presses back into the same upper band

## System Mapping

### 1. Overhead Capping Band

Use:

- `DepthSnapshotPayload.significant_levels`
- `ObservedLargeLiquidityLevel`

Important facts:

- `side = sell`
- `price`
- `max_seen_size`
- `distance_from_price_ticks`
- `replenishment_count`
- `pull_count`
- `executed_volume_estimate`

This is the cap that fails to stop the trend.

### 2. Shallow Pullback

Use:

- `ObservedLiquidityEpisode`
- `ObservedSecondFeature`
- `decision_layers.execution_context[*].raw_features`

Important facts:

- pullback origin
- pullback depth in ticks
- whether the pullback stayed above the more important support or drive origin
- whether price quickly reaccepted higher trade

The pullback is part of the script, not a contradiction to it.

### 3. Persistent Aggressive Lift

Use:

- `ObservedInitiativeDrive`

Important facts:

- repeated or persistent buy-side aggression
- `net_delta`
- `price_travel_ticks`
- `continuation_seconds`
- `consumed_price_levels`

This is what upgrades the event from "pause under resistance" to "trend continuation under pressure."

### 4. Measured Continuation

Use:

- `ObservedMeasuredMove`

Important facts:

- distance achieved after the pullback
- distance as:
  - `x manipulation leg`
  - `x local range amplitude`
- body-confirmed threshold progress
- next extension target

This lets the system describe whether the trend merely retested or actually re-expanded.

### 5. Trend Memory

Use:

- `ObservedExertionZone`
- `DerivedKeyLevelAssessment`

The lower holding area can later become:

- a support zone
- a continuation base
- or the origin of the last strong drive before overhead liquidity consumption

## Derived Interpretation

These belong in `derived interpretation`:

- `failed_overhead_capping`
- `shallow_pullback_continuation`
- `aggressive_buy_persistence`
- `upper_liquidity_harvest_continuation`
- `strong_trend_despite_overhead_pressure`

The system should only promote these labels after it sees both:

- shallow pullback behavior
- renewed aggressive lift into the upper band

## Risk Logic

This pattern matters because it prevents overreacting to visible overhead liquidity.

The correct question is not:

- "is there a wall above price"

The better questions are:

- did the wall actually force deeper acceptance lower
- was the pullback shallow or structurally damaging
- did aggressive buyers return quickly

If the answers are:

- shallow pullback
- quick reclaim
- renewed buy aggression

then the event is closer to continuation than to reversal.

## Revisit Logic

Later review should ask:

- did the upper wall finally get consumed
- did the pullback hold become a later support
- did the first cap attempt weaken the ascent or merely pause it
- on revisit, does the old upper wall act as support, resistance, or no longer matter

## Recommended Future Fields

The most useful future fields for the ATAS collector are:

- `cap_attempt_count`
- `cap_attempt_hold_seconds`
- `pullback_depth_ticks`
- `pullback_depth_vs_last_drive_multiple`
- `reclaim_seconds_after_pullback`
- `renewed_aggressive_buy_volume`
- `upper_liquidity_consumed_ratio`
- `trend_continuation_after_cap_ticks`

## Why This Pattern Matters

This is a high-value anti-bias pattern.

It teaches the system:

- overhead liquidity is important
- but it is not automatically bearish
- strong trends often pause, absorb, and continue

That makes it a key script for reducing human fatigue:

- do not short every visible wall
- track whether the wall is actually winning
- track whether buyers keep reasserting control

## Confirmation Signals

- the pullback stays shallow relative to the prior drive and holds above the more important release area
- aggressive buyers return quickly after the pause instead of allowing a deeper acceptance lower
- price re-engages the same upper band with enough pressure to threaten another harvest attempt

## No-Trade Conditions

- do not fade the wall automatically before it proves it can force deeper acceptance lower
- do not buy continuation if the pullback already damaged the prior drive origin or key support
- do not keep adding long if the move is running straight into stronger higher-timeframe resistance with no renewed lift

## Review Questions

- did the wall actually stop the trend, or did it only pause it
- was the pullback shallow enough to preserve continuation logic
- did the long entry wait for renewed aggression, or was it placed while the market was still vulnerable to a deeper failure
