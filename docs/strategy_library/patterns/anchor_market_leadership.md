# Anchor Market Leadership

## Status

- `status`: `doctrine_accepted`
- `source_type`: `cross-symbol leadership doctrine synthesis`

## Pattern Summary

This pattern describes the situation where one market is clearer, reaches the key level first, and provides the cleaner read for another market that is noisier or more reactive.

Typical example:

- ES is clearer than NQ
- ES reaches the decision zone first
- NQ is still noisy, late, or overstretched
- the better trade decision comes from the anchor market, not from forcing a read on the noisier market

The business value is simple:

- the cleaner market should lead interpretation
- the noisier market should not be promoted into leadership without evidence

## Observed Facts To Preserve

- which market reached the level first
- which market showed clearer acceptance or rejection first
- whether the secondary market confirmed quickly or lagged with noise
- whether the leading market produced a durable outcome
- whether the lagging market eventually synchronized or stayed unclear

## Derived Interpretation

These belong in `derived interpretation`:

- `anchor_market_leadership`
- `anchor_market_clearer_than_execution`
- `cross_symbol_confirmation`
- `lagger_should_not_lead`
- `anchor_first_reaction_valid`

## Confirmation Signals

- one market reaches the decision zone first and shows cleaner acceptance or rejection
- the lagging market is still noisy or late while the anchor market already produced outcome
- the lagging market later confirms in the same direction instead of immediately contradicting the anchor read

## No-Trade Conditions

- do not force leadership onto the noisier market just because it is moving faster
- do not call cross-symbol confirmation if the anchor market itself has not yet produced a clear outcome
- do not assume the lagging market must follow if it keeps failing to synchronize after the anchor move

## Management Notes

- this card is strongest when one symbol is obviously cleaner at the decision point
- anchor-market leadership is more useful for filtering bad entries than for inventing extra trades
- if the lagging market never confirms, the original cross-symbol read should be downgraded

## Review Questions

- which market was actually clearer at the decision point
- was the trade taken from the anchor market read or from noise in the lagging market
- did the lagging market confirm, or was the assumed follow-through never real
