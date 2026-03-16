# Trapped Inventory Release

## Status

- `status`: `doctrine_accepted`
- `source_type`: `auction and inventory doctrine synthesis`

## Pattern Summary

This pattern describes the sequence where one side entered with conviction, failed to keep control, and later became the fuel for the opposite move.

The important distinction is:

- a failed level is not enough
- a quick poke through a level is not enough
- what matters is whether inventory is now trapped outside accepted trade and forced to exit on the wrong side

This is one of the highest-value business chains because it converts a static level into participant pain and forced repricing.

## Observed Facts To Preserve

- where the original drive or defense came from
- whether the side first appeared in initiative or in passive defense
- where the first failure happened
- whether price accepted beyond the failed level
- whether the failed side got a re-entry chance and still could not recover
- whether the opposite direction accelerated after the failure

## Derived Interpretation

These belong in `derived interpretation`:

- `trapped_inventory_release`
- `failed_defense_now_fuel`
- `failed_break_holder_trapped`
- `forced_exit_release`
- `inventory_flip_confirmed`

## Confirmation Signals

- price accepts beyond the original defended or breakout level instead of only wicking through it
- the trapped side gets a reclaim chance and still cannot recover the level
- the opposite side accelerates after the failed reclaim as trapped inventory is forced out

## No-Trade Conditions

- do not call inventory trapped before price has actually accepted beyond the failed level
- do not chase the release if the market is still rotating around the failed level with no clear acceptance
- do not assume trapped inventory if the side that supposedly failed can immediately reclaim and hold its level again

## Management Notes

- separate first failure from true trap confirmation
- the best release often comes after the failed side cannot recover on the first meaningful retest
- once trapped inventory has substantially released, late chasing becomes lower quality and often hands off into balance

## Review Questions

- where exactly did the original side become wrong, not just uncomfortable
- did the market truly accept beyond the failure point, or only test it briefly
- was the trade taken on real trapped inventory release, or just on a fast move without inventory evidence
