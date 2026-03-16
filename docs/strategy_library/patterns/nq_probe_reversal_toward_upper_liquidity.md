# NQ Probe Reversal Toward Upper Liquidity

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes a small-risk probe reversal where:

- price is still under a visible upper liquidity band
- a smaller test entry is taken after local downside failure or non-continuation
- the reversal is not justified by a random bounce
- it is justified by `liquidity attraction` toward the upper band
- later price mean-reverts back toward `EMA20` and can transition into a small reversal trend

The key idea is:

- the first entry is small because it is still a proof trade
- the trade becomes more valid only after the market starts showing acceptance upward

## Observed Facts To Preserve

These belong in `observed facts`:

- a visible upper liquidity band remains above price
- price tests lower but does not continue cleanly
- local reversal begins from a smaller test area
- the reversal starts reducing the distance to the upper liquidity band
- price later reclaims or mean-reverts toward `EMA20`
- after reclaiming `EMA20`, the move can transition into a small uptrend rather than a one-bar bounce

## System Mapping

### 1. Liquidity Attractor

Use:

- `DepthSnapshotPayload.significant_levels`
- `ObservedLargeLiquidityLevel`

Important facts:

- `side`
- `price`
- `distance_from_price_ticks`
- `heat_score`
- `seconds_visible`

This is the destination pressure or attraction point.

### 2. Small Probe

Use:

- `ObservedLiquidityEpisode`
- `ObservedEventMarker`

Important facts:

- the local test zone
- whether price failed to continue lower
- rejection distance
- whether liquidity was replenished or pulled

This is the "small try" part.
The system should keep it explicitly small and conditional, not label it as a full reversal by default.

### 3. Reversal Drive

Use:

- `ObservedInitiativeDrive`

Important facts:

- first upward push after the failed continuation
- `price_travel_ticks`
- `net_delta`
- `continuation_seconds`

This is what upgrades the trade from a probe into a usable reversal attempt.

### 4. Measured Return

Use:

- `ObservedMeasuredMove`

Important facts:

- distance traveled back toward the upper liquidity
- measured multiple of the local test range or manipulation leg
- whether the first body-confirmed threshold was cleared

This captures whether the bounce is only noise or a meaningful reclaim.

### 5. EMA20 Reclaim

For now, keep this in:

- `decision_layers.setup_context[*].raw_features`
- `decision_layers.execution_context[*].raw_features`

Recommended facts:

- `ema20_distance_ticks`
- `ema20_slope`
- `ema20_reclaim_confirmed`
- `bars_above_ema20_after_reclaim`

This keeps the EMA logic as observed context rather than turning it into a hard-coded signal engine.

## Derived Interpretation

These belong in `derived interpretation`:

- `liquidity_attractor_present`
- `small_probe_reversal_candidate`
- `upper_liquidity_magnet_active`
- `ema20_mean_reversion_in_progress`
- `micro_reversal_trend_active`

The system should only promote the later labels once price actually reclaims the path upward.

## Risk Logic

This pattern is useful because risk stays small at the beginning.

The first trade thesis is not:

- "trend has already reversed"

It is:

- "price is showing that it still prefers the upper liquidity, so a small-risk reversal proof is acceptable"

That means the event should preserve:

- probe entry area
- local invalidation area
- first reclaim threshold
- distance to upper attractor

## Revisit Logic

Later review should ask:

- did the first probe only bounce to `EMA20` and fail
- or did `EMA20` become the first acceptance checkpoint for a broader reversal
- did price eventually tag the upper liquidity band
- did the upper band reject price or get absorbed

This turns the pattern into a replayable script instead of a one-off chart annotation.

## Recommended Future Fields

The most useful future fields for the ATAS collector are:

- `attractor_price`
- `distance_to_attractor_ticks`
- `probe_entry_price`
- `probe_invalidation_ticks`
- `ema20_distance_ticks`
- `ema20_reclaim_confirmed`
- `micro_reversal_state`
- `attractor_tagged`

## Why This Pattern Matters

This pattern is valuable because it reduces decision fatigue.

Instead of forcing the trader to constantly ask:

- "is this just a bounce"
- "is this a real small reversal"
- "is price still pulled toward upper liquidity"

the system can keep those facts alive and describe the progression:

- failed downside continuation
- small probe reversal
- return to EMA20
- possible micro-trend continuation toward upper liquidity

## Confirmation Signals

- downside continuation fails cleanly instead of extending with acceptance lower
- the upper liquidity attractor remains relevant while price starts reducing the distance to it
- price reclaims a usable threshold such as EMA20 or the last local pivot after the probe

## No-Trade Conditions

- do not bottom-pick purely because price is down; failed downside continuation must be visible first
- do not size the first probe like a full reversal when the market has not yet shown upward acceptance
- do not keep buying if the upper attractor disappears or the broader script still clearly favors downside continuation

## Review Questions

- was the probe actually taken after downside failure, or was it an emotional catch attempt
- what evidence upgraded the idea from a probe into a real reversal candidate
- did the move reclaim a meaningful threshold, or only print a brief bounce before failing
