# NQ Gap Fill Balance Reclaim

## Status

- `status`: `doctrine_accepted`
- `source_type`: `opening-gap doctrine synthesis`

## Pattern Summary

This pattern describes a U.S. session gap that begins repairing back toward old value and then tries to reclaim balance.

The important distinction is:

- a gap touch is not enough
- a gap fill is not enough
- what matters is whether trade is accepted after the fill or deep partial fill

The setup becomes useful when the open creates a context problem and the market starts solving it by rotating back into prior accepted price.

## Observed Facts To Preserve

- session open occurs with a meaningful RTH gap relative to prior close or value
- price approaches the gap on initiative or orderly repair, not random drift only
- first touch, partial fill, and full fill are recorded separately
- price reaction after the fill or deep partial fill is preserved
- acceptance back into prior value or prior close is measured, not assumed

## Derived Interpretation

These belong in `derived interpretation`:

- `gap_repair_in_progress`
- `gap_fill_balance_reclaim`
- `filled_and_accepted`
- `partial_fill_rejection`
- `open_to_old_value_rotation`

## Confirmation Signals

- the gap repair is supported by repeatable approach quality, not a single erratic spike
- after the fill or deep partial fill, trade begins holding inside old value instead of rejecting immediately
- follow-through confirms that the gap acted as a path back into balance rather than a one-touch magnet

## No-Trade Conditions

- do not trade just because a gap exists; the gap must still be the active script anchor
- do not fade or follow the fill blindly if post-fill acceptance is not visible yet
- do not treat overnight noise and U.S. regular-session gap behavior as the same thing without session context

## Management Notes

- separate `partial fill`, `full fill`, and `accepted after fill`
- if price fills and immediately rejects, the script changes from balance reclaim to fill failure
- if price accepts back into old value, focus should shift toward rotation targets instead of the original gap headline

## Review Questions

- was the operator trading the gap itself, or the post-fill acceptance or rejection
- did price truly accept back into old value after the fill, or only tag it briefly
- was the opening context strong enough to keep the gap as the main script anchor
