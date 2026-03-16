# Opening Inventory Correction Vs Continuation

## Status

- `status`: `doctrine_accepted`
- `source_type`: `opening-auction and overnight inventory doctrine synthesis`

## Pattern Summary

This pattern separates two very different open behaviors:

- the open corrects overnight inventory first
- the open continues the overnight or prior-session direction without meaningful correction

This matters because a strong first move at the open is often misread.
The open can look directional while actually only unwinding inventory imbalance before the real session script begins.

## Observed Facts To Preserve

- overnight or prior-session directional inventory bias
- where the RTH open occurs relative to prior close, value, and overnight range
- whether the first drive after the open extends the prior direction or corrects it
- whether the correction is accepted or only a short-lived flush
- whether continuation after the open is built on acceptance or only on emotional opening flow
- whether the first opening drive fails and flips the script

## Derived Interpretation

These belong in `derived interpretation`:

- `opening_inventory_correction`
- `opening_inventory_continuation`
- `overnight_imbalance_unwind`
- `first_drive_failed`
- `open_script_reversal`

## Confirmation Signals

- the open either clearly corrects back toward old value or clearly accepts further in the prior direction
- the first opening drive produces follow-through consistent with correction or continuation rather than random spike behavior
- later trade confirms that the first opening move was inventory logic, not just opening noise

## No-Trade Conditions

- do not chase the first opening burst before determining whether it is correction or true continuation
- do not call correction complete if price has not yet shown acceptance back into old value or back through the correcting path
- do not assume continuation is real if the first drive extends but immediately loses hold quality

## Management Notes

- the open should be treated as an inventory decision point, not as an automatic signal
- if the first drive fails, the opposite opening script often becomes stronger than the original burst
- once correction is complete and accepted, target logic should shift from open emotion to session structure

## Review Questions

- was the operator trading real opening continuation or only an overnight inventory unwind
- did the first drive hold acceptance, or did it fail after the first emotional burst
- was the open interpreted in relation to prior value and overnight positioning, or in isolation
