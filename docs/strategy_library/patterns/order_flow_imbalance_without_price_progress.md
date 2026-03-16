# Order-Flow Imbalance Without Price Progress

## Status

- `status`: `doctrine_accepted`
- `source_type`: `imbalance-versus-travel doctrine synthesis`

## Pattern Summary

This card exists for a common false opportunity:

- aggressive flow looks strong
- delta or imbalance looks one-sided
- but price does not actually travel

When flow does not produce progress, the market is often absorbing, stalling, or already losing edge.

## Observed Facts To Preserve

- whether aggressive flow is clearly one-sided
- how much price progress is achieved per unit of aggression
- whether opposite-side liquidity keeps absorbing or reloading
- whether travel efficiency is shrinking over repeated attempts
- whether the market can actually clear the nearby level it claims to be attacking

## Derived Interpretation

These belong in `derived interpretation`:

- `imbalance_without_progress`
- `price_progress_failure`
- `aggression_absorbed`
- `travel_efficiency_decay`
- `one_sided_flow_not_enough`

## Confirmation Signals

- repeated same-side aggression fails to create meaningful travel
- price stalls at the same boundary despite continued imbalance
- later attempts become less efficient than earlier attempts

## No-Trade Conditions

- do not open from delta color or imbalance count alone
- do not keep adding when travel efficiency is shrinking
- do not call continuation healthy if aggression is being absorbed at the same edge

## Management Notes

- flow should be judged by what it accomplishes, not only by how loud it looks
- poor price progress often matters more than another burst of same-side aggression
- once price progress improves again, hand the read off to a real continuation card

## Review Questions

- did the operator trade aggression or actual travel
- was the market progressing less with each new burst
- where did absorption start dominating the narrative
