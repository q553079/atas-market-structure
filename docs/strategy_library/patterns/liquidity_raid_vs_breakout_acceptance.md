# Liquidity Raid Vs Breakout Acceptance

## Status

- `status`: `doctrine_accepted`
- `source_type`: `auction and stop-run doctrine synthesis`

## Pattern Summary

This pattern separates a liquidity raid from a real breakout.

The dangerous confusion is:

- price sweeps a visible edge
- stops release a fast burst
- the burst looks convincing
- but outside trade never becomes accepted

A sweep is only a business event.
The real decision is whether price can hold and build outside the old boundary.

## Observed Facts To Preserve

- which edge was swept: range edge, value edge, gap edge, or prior defended zone
- whether the sweep began from inside balance or from an already accepted imbalance
- how much of the move came from the first burst versus later hold quality
- whether aggressive flow continued after the sweep or disappeared immediately
- whether price held outside the old boundary or returned back inside
- whether the first pullback after the sweep was defended or failed

## Derived Interpretation

These belong in `derived interpretation`:

- `liquidity_raid_only`
- `stop_run_not_breakout`
- `breakout_acceptance_confirmed`
- `returned_to_balance_after_sweep`
- `outside_hold_quality_decides`

## Confirmation Signals

- the sweep pushes through a meaningful edge and forces obvious stop release
- outside price either builds and holds, or quickly stalls and returns inside
- the first pullback after the sweep reveals whether fresh control exists or not

## No-Trade Conditions

- do not chase the first sweep just because it ran stops beyond a visible boundary
- do not fade the sweep before outside hold quality actually fails
- do not call breakout confirmed if price has not yet held and built outside the old area

## Management Notes

- the first burst is often the worst location because it mixes information with emotion
- the best read usually comes after outside hold or outside failure is proven
- if price returns and accepts back inside the old auction, the breakout story should be downgraded fast

## Review Questions

- was the operator trading the sweep itself instead of the hold quality after the sweep
- did outside trade become accepted, or was it only a stop run
- was the reversal or continuation thesis formed before the market proved which branch it had chosen
