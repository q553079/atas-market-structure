# Initial Balance Extension Vs True Breakout

## Status

- `status`: `human_refined`
- `source_type`: `opening-auction and initial-balance doctrine synthesis`

## Pattern Summary

This card separates an initial-balance extension from a true breakout.

The dangerous shortcut is:

- price trades outside initial balance
- the extension looks statistically important
- the operator calls it a breakout too early

The real question is whether outside trade becomes accepted.

## Observed Facts To Preserve

- which initial-balance definition is being used
- whether price only tagged outside IB or built there
- whether the extension occurred with opening inventory, gap, or value context
- whether the first retest outside IB held or failed
- whether price re-entered IB or prior value after the extension

## Derived Interpretation

These belong in `derived interpretation`:

- `initial_balance_extension`
- `initial_balance_breakout_confirmed`
- `ib_extension_without_acceptance`
- `value_area_reacceptance_state`
- `ib_false_break_return`

## Confirmation Signals

- price extends outside IB and does more than print a one-touch poke
- the first retest outside IB holds or the market clearly accepts a new auction there
- follow-through supports the outside branch instead of instantly returning inside

## No-Trade Conditions

- do not trade IB statistics alone without current opening context
- do not call the first extension a breakout before outside acceptance is visible
- do not mix overnight range logic and RTH initial-balance logic without defining which session is active

## Management Notes

- IB extension is an observation; breakout is a later judgment
- if the extension fails and price re-enters IB, downgrade the breakout narrative quickly
- if outside trade holds, target logic should shift from opening reaction to session expansion

## Review Questions

- did the operator trade the IB headline or the outside acceptance after it
- was the session definition clear before using the IB read
- after extension, did price build outside or fall back into the old opening structure
