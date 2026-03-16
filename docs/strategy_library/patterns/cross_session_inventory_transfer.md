# Cross-Session Inventory Transfer

## Status

- `status`: `human_refined`
- `source_type`: `multi-session auction and inventory doctrine synthesis`

## Pattern Summary

This pattern describes how one session builds pressure, defense, or trapped inventory, and the next session decides whether to inherit that work, neutralize it, or reverse it.

The business value is high because many operators overreact to the new session as if it started from zero.
It usually did not.

The key question is:

- did the new session inherit unfinished control from the prior session
- or did it open in a way that forces inventory correction first

## Observed Facts To Preserve

- which session built the key zone or campaign
- where the next session opened relative to that inherited zone
- whether the inherited side defended the first meaningful revisit
- whether the new session accelerated in the same direction or corrected through the prior session build
- whether the prior-session level still produced outcome on first handoff interaction
- whether the new session accepted beyond the inherited level or rejected from it

## Derived Interpretation

These belong in `derived interpretation`:

- `cross_session_inventory_transfer`
- `session_handoff_inherited_control`
- `prior_session_inventory_correction`
- `handoff_failed_and_reversed`
- `prior_session_zone_still_active`

## Confirmation Signals

- the new session opens close enough to the inherited zone for that level to matter immediately
- the first meaningful interaction proves whether the prior session side still controls the level
- continuation or correction after the handoff is supported by real acceptance, not just by the first opening burst

## No-Trade Conditions

- do not assume the new session starts from zero when prior-session inventory is still nearby and active
- do not force prior-session logic when the new session opens too far away for that inventory to matter
- do not call inheritance or correction before the first meaningful handoff interaction shows acceptance or rejection

## Management Notes

- session handoff is strongest when the new session opens near a prior-session build, suppressor, or launch area
- inherited control is more credible after the first defense or first accepted continuation, not before
- if the handoff fails quickly, the prior-session work may become fuel for correction rather than continuation

## Review Questions

- what exactly did the prior session hand off into the new one: control, trapped inventory, or only a visible level
- did the new session inherit and use that inventory, or immediately start correcting it
- was the trade opened before the session handoff actually showed who was in control
