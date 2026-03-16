# Mother Bar Auction Zones

## Status

- `status`: `human_refined`
- `source_type`: `price-action micro-auction doctrine synthesis`

## Pattern Summary

This pattern treats a Mother Bar not as a simple inside-bar trigger, but as a temporary micro-auction with internal zones that behave differently depending on context.

The same Mother Bar can support three different scripts:

- range fade around outer trap zones
- early-trend continuation from the trend-side zone
- late-leg reversal when the third push is already near exhaustion

The card exists to stop AI from using one fixed rule for every Mother Bar.

## Observed Facts To Preserve

- which bar defines the mother range
- whether the next bars stay inside and confirm short-term balance
- whether the environment is trading range, early trend, or late third-leg exhaustion
- whether price reaches outer buy or sell zones rather than only the middle
- whether body closes at competition points increase breakout odds
- whether the market accepts outside the mother range or rejects back inside

## Derived Interpretation

These belong in `derived interpretation`:

- `mother_bar_auction`
- `mother_bar_trap_zone`
- `mother_bar_context_switch`
- `mother_bar_breakout_confirmation`
- `mother_bar_middle_is_noise`

## Confirmation Signals

- outer-zone tests reject cleanly in range conditions
- trend-side zone holds during leg one or leg two continuation context
- body closes beyond the key competition point and then outside-hold quality supports breakout continuation

## No-Trade Conditions

- do not open from the middle of the mother range
- do not apply range-fade logic if the market is already accepting outside the mother bar
- do not ignore whether the market is in early trend, late wedge, or plain chop

## Management Notes

- the mother bar is a map, not a trade by itself
- the middle of the mother bar is usually poor location unless a breakout has already proven itself
- when context shifts, the valid side of the mother bar shifts with it

## Review Questions

- was the mother bar interpreted in the correct environment
- did the operator open from an outer zone or from the middle of the auction
- was breakout assumed before body closes and outside hold proved it
