# H2 L2 Pullback Continuation Framework

## Status

- `status`: `doctrine_accepted`
- `source_type`: `price-action pullback counting doctrine synthesis`

## Pattern Summary

This pattern formalizes H1, H2, L1, and L2 pullback entries as a continuation framework rather than a blind bar-counting exercise.

The business distinction is:

- counting only matters when the underlying trend still exists
- the second attempt is often better because the first countertrend push already failed
- endless counting inside chop is not doctrine, it is self-deception

This framework is about deciding whether a pullback is still corrective or has already degraded into range or reversal.

## Observed Facts To Preserve

- what the prior trend or trend leg looked like before the pullback began
- whether the pullback stayed corrective or started to look broad and overlapping
- where the first attempt happened and whether it failed cleanly or only looked weak
- where the second attempt formed relative to EMA, breakout point, channel edge, or prior high/low
- whether the trend origin remained intact
- whether continuation resumed after the counted entry or the count kept stretching into wedge or range behavior

## Derived Interpretation

These belong in `derived interpretation`:

- `h2_l2_pullback_continuation`
- `second_attempt_trend_entry`
- `pullback_count_valid`
- `trend_origin_still_intact`
- `counting_inside_chop_not_valid`

## Confirmation Signals

- a clear prior trend or trend leg exists before the pullback
- the pullback remains corrective instead of becoming accepted reversal structure
- the second attempt forms from a meaningful continuation location and resumes trend travel

## No-Trade Conditions

- do not count endlessly inside chop and call it H2 or L2
- do not treat a weak H1 or L1 as equal to a strong H2 or L2
- do not use the framework once trend origin is broken or the pullback has become too broad
- do not open from the middle of a range just because a count exists

## Management Notes

- H2 and L2 are often higher quality than first entries because the first countertrend attempt already failed
- if the second attempt fails too, reassess whether the market is becoming range, wedge, or reversal
- the best versions usually test a meaningful continuation reference instead of printing randomly in open space

## Review Questions

- was the market still in valid continuation context or already in range
- was the count based on real attempts, or was the operator forcing labels onto noise
- did the entry come from a meaningful continuation location
- did the operator mistake a second entry for a guaranteed entry
