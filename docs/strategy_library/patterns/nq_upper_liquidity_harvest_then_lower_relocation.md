# NQ Upper Liquidity Harvest Then Lower Relocation

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes what often happens after upper liquidity has already been harvested:

- price finishes eating the visible upper pocket
- the immediate continuation starts losing efficiency
- the market begins searching for lower liquidity
- after the harvest, the tape often shifts into:
  - small balance
  - pullback
  - or a larger reversal

The key idea is:

- the harvest itself is one event
- what happens after the harvest is a second event and must be recorded separately

## Observed Facts To Preserve

- upper liquidity pocket was reached and consumed
- harvest completion time
- same-side continuation distance after completion
- post-harvest balance width
- post-harvest pullback distance
- post-harvest reversal distance
- whether price later searched for lower liquidity

## System Mapping

### 1. Harvest Completion

Use:

- `ObservedInitiativeDrive`
- `ObservedLargeLiquidityLevel`

Important facts:

- which drive completed the harvest
- which liquidity pocket was harvested
- whether it was partial or complete

### 2. Post-Harvest Response

Use:

- `ObservedPostHarvestResponse`

Important facts:

- `harvest_completed_at`
- `continuation_ticks_after_completion`
- `consolidation_range_ticks`
- `pullback_ticks`
- `reversal_ticks`
- `post_harvest_delta`
- `outcome`

## Derived Interpretation

These belong in `derived interpretation`:

- `harvest_completed`
- `post_harvest_consolidation`
- `post_harvest_pullback`
- `post_harvest_reversal_watch`
- `lower_liquidity_relocation_active`

## Recommended Future Fields

- `harvest_completed_at`
- `harvest_completed_price`
- `post_harvest_state`
- `post_harvest_outcome`
- `next_lower_liquidity_price`
- `lower_liquidity_reached`

## Confirmation Signals

- the upper objective is actually harvested instead of only touched
- same-side continuation loses efficiency soon after the harvest completes
- price begins balancing, pulling back, or searching lower from the harvested zone

## No-Trade Conditions

- do not chase continuation in the same direction after the objective is already complete and no new base has formed
- do not force a reversal immediately after harvest if price has not yet accepted lower or broken balance
- do not overread every pause after harvest as a major reversal when the market is only rotating narrowly

## Review Questions

- was the upper objective truly complete before the operator changed bias
- did the market shift into balance first, or did it immediately prove deeper reversal intent
- was the trade idea a justified post-harvest response read, or just late chasing after the move was done
