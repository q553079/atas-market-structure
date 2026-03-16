# Large Order Lifecycle Diagnosis

## Status

- `status`: `doctrine_accepted`
- `source_type`: `order-flow doctrine synthesis`

## Pattern Summary

This card is for diagnosing whether a large displayed order is:

- trapped
- getting unwound
- still in control
- or likely fake and being pulled

The key rule is:

- visibility alone is not evidence
- lifecycle plus outcome is the evidence

The operator should not treat a large order as support or resistance until the system can explain what happened to it after price interacted with it.

## Observed Facts To Preserve

- when the large order first appeared and how long it stayed visible
- whether it was hit, replenished, pulled, or moved
- aggressive volume traded against it
- price displacement or lack of displacement after interaction
- whether later acceptance occurred through or away from the level

## Derived Interpretation

These belong in `derived interpretation`:

- `trapped_large_order`
- `unwinding_large_order`
- `continuing_large_order_control`
- `spoof_risk`
- `absorbed_large_order`

## Confirmation Signals

- a real defending order stays, absorbs, and produces outcome in price
- a trapped order gets traded through and price accepts beyond it instead of snapping straight back
- a spoof candidate pulls before meaningful interaction or repeatedly disappears when pressure arrives

## No-Trade Conditions

- do not trust a large order only because it is bright or large on the screen
- do not call an order trapped before price has actually accepted through it
- do not assume fake liquidity if the order keeps staying, reloading, and producing real price rejection

## Management Notes

- track state transitions rather than static labels
- the same order can evolve from defending to trapped, or from relevant to irrelevant
- use this card most aggressively with `trapped_large_orders` and `live_depth` presets

## Review Questions

- what happened to the order when price first interacted with it
- did the order produce a result in price, or only visual noise
- was the operator trading the lifecycle evidence, or just reacting to the size display
