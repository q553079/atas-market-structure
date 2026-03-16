# Fake Depth Signature Context

## Status

- `status`: `doctrine_accepted`
- `source_type`: `false-depth and spoof-risk doctrine synthesis`

## Pattern Summary

This card upgrades the generic false-liquidity read into a higher-confidence signature.

The point is not to prove illegal intent.
The point is to identify when displayed depth is too unreliable to be promoted into support or resistance.

## Observed Facts To Preserve

- whether large displayed size repeatedly appears near an active level
- whether that size cancels or relocates as price approaches
- whether the opposite side receives real fills while the displayed side disappears
- whether same-price replenishment is real or only cosmetic
- whether any actual defense appears after the size is shown

## Derived Interpretation

These belong in `derived interpretation`:

- `false_depth_signature`
- `near_touch_cancellation`
- `opposite_fill_then_cancel`
- `pull_rate_elevated`
- `displayed_size_untrusted`

## Confirmation Signals

- large displayed size repeatedly disappears near touch
- opposite-side fills occur while the displayed side fails to stand in
- visible size does not create the reaction that a defended level should create

## No-Trade Conditions

- do not lean on the first few price levels from brightness alone
- do not call same-price replenishment if the size mostly cancels before pressure arrives
- do not fade price only because a large wall appears if that wall has not produced outcome

## Management Notes

- repeated cancellation behavior is more valuable than one isolated flash
- this card should usually hand off into continuation or failure cards once real outcome appears
- visible size without survival near touch should be downgraded fast

## Review Questions

- did the displayed depth survive near touch
- was the level real structure or only visual bait
- did the operator trade the screen image instead of the actual outcome
