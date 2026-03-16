# Failed Break Acceptance Re-Entry

## Status

- `status`: `doctrine_accepted`
- `source_type`: `auction failure doctrine synthesis`

## Pattern Summary

This pattern describes a breakout or breakdown attempt that first looks valid, then loses acceptance, and finally re-enters the prior accepted area.

The chain matters because many bad trades happen here:

- traders chase the break
- the move does not hold outside
- price re-enters the old auction
- trapped followers become the fuel for the opposite rotation

This is not just a false break by appearance.
It is a failed break because acceptance outside the old area never stabilizes.

## Observed Facts To Preserve

- which boundary was broken first
- whether trade held outside the boundary or returned quickly
- how much continuation happened outside the break
- whether the first re-entry back inside old value or old range held
- whether trapped breakout participants exited on the re-entry
- whether the re-entry developed into rotation, reversal, or only a local reset

## Derived Interpretation

These belong in `derived interpretation`:

- `failed_break_acceptance_reentry`
- `outside_hold_failed`
- `returned_to_old_auction`
- `breakout_follower_trap`
- `reentry_rotation_candidate`

## Confirmation Signals

- outside trade fails to hold and returns inside the prior accepted area
- the re-entry back inside is held instead of instantly rejected again
- follow-through after re-entry shows rotation toward the other side of the prior auction or toward a meaningful interior target

## No-Trade Conditions

- do not fade every first break before outside-hold quality is known
- do not call the break failed if price has not yet re-entered and held inside the old area
- do not trade the re-entry if the broader environment is strongly imbalanced and the return inside still looks temporary

## Management Notes

- the best business read is often the first accepted re-entry, not the first outside poke
- once price is clearly back inside old auction, the target logic should shift toward internal references rather than the breakout headline
- if re-entry cannot hold, the failed-break read is weaker and may only be noise

## Review Questions

- was the operator chasing a break that never showed real outside acceptance
- when price re-entered, did it hold inside old value or only flicker back in
- did the reversal or rotation thesis come from true re-entry evidence or from emotional fading
