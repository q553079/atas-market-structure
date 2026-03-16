# No-Trade Garbage Time Context

## Status

- `status`: `doctrine_accepted`
- `source_type`: `environment and execution discipline synthesis`

## Pattern Summary

This card defines the environment where many things appear active but none of them are good enough to justify opening risk.

Typical features include:

- event noise without clear result
- conflicting higher-timeframe and lower-timeframe signals
- price stuck in the middle of an auction
- visible liquidity that does not resolve anything
- repeated micro reversals with no durable acceptance

This is the discipline card.
Its job is to say:

- not every readable market is a tradable market

## Observed Facts To Preserve

- whether price is in the middle of a wider balance or auction
- whether higher-timeframe and lower-timeframe logic conflict
- whether recent events created real follow-through or only repeated noise
- whether important levels are being approached or only random internal prices are trading
- whether displayed liquidity is producing outcome or just attention churn

## Derived Interpretation

These belong in `derived interpretation`:

- `no_trade_garbage_time`
- `middle_of_auction_risk`
- `cross_timeframe_conflict`
- `event_noise_without_result`
- `insufficient_edge_to_open`

## Confirmation Signals

- multiple event tags appear but none produce durable acceptance or displacement
- higher-timeframe context points one way while local execution logic points the other with no clear resolution
- price remains inside non-edge territory where both sides are still being recycled

## No-Trade Conditions

- do not open in the middle of balance because recent candles feel active
- do not open when lower-timeframe triggers conflict with stronger higher-timeframe location and no handoff is visible
- do not mistake repeated event labels for real edge when none of them produce outcome

## Management Notes

- this card should outrank mediocre setup cards when context quality is poor
- the best use is to suppress low-quality candidate promotion before the operator invents a trade
- once a real edge appears at a true boundary with acceptance or rejection, this card should downgrade itself

## Review Questions

- was the operator opening because the market was tradable or just because it was moving
- did any observed event actually produce outcome, or only noise and attention churn
- was there a real edge boundary nearby, or was the trade opened in auction middle
