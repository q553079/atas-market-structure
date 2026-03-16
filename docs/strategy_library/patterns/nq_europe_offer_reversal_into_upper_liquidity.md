# NQ Europe Offer Reversal Into Upper Liquidity

## Status

- `status`: `doctrine_accepted`
- `source_type`: `user-provided chart example`

## Pattern Summary

This pattern describes a Europe-session reversal where:

- an upper sell wall first acts as visible pressure
- lower liquidity and local support begin to build underneath price
- aggressive orders start lifting the market from below
- price stops respecting the earlier suppression
- the move then accelerates upward and starts eating the upper liquidity band

This is not the same as a simple breakout.
It is closer to:

- `initial suppression`
- `lower support or attraction build`
- `aggressive reversal release`
- `upper liquidity harvest`

That is why the manipulation footprint feels obvious:

- one side first shapes expectation
- then the move flips and uses that earlier structure as fuel

## Observed Facts To Preserve

These belong in `observed facts`:

- session: `europe`
- a large ask-side liquidity band remains visible above price
- lower-side support or liquidity response appears before the reversal
- price begins to push upward from the lower zone
- aggressive flow participates in the upward release
- price reaches into the upper liquidity band
- part of the upper liquidity starts getting consumed rather than merely respected

## System Mapping

### 1. Upper Pressure Band

Use:

- `DepthSnapshotPayload.significant_levels`
- `ObservedLargeLiquidityLevel`

Important facts:

- `side = sell`
- `price`
- `max_seen_size`
- `distance_from_price_ticks`
- `replenishment_count`
- `pull_count`
- `executed_volume_estimate`

This is the earlier cap and later target.

### 2. Lower Push Zone

Use:

- `ObservedLiquidityEpisode`
- `ObservedExertionZone`

Important facts:

- lower defended or responsive zone
- executed volume against the zone
- rejection distance
- whether support was rebuilt or re-engaged

This is what gives the reversal its base.

### 3. Upward Release

Use:

- `ObservedInitiativeDrive`

Important facts:

- `side = buy`
- `aggressive_volume`
- `net_delta`
- `price_travel_ticks`
- `consumed_price_levels`
- `continuation_seconds`

This is the active engine that turns a defended base into a real upward move.

### 4. Measured Travel

Use:

- `ObservedMeasuredMove`

Important facts:

- distance from the lower push zone to the upper liquidity band
- distance as:
  - `x manipulation leg`
  - `x local range amplitude`
- body-confirmed ladder progress
- next extension threshold

This records whether the move merely bounced or truly expanded into a liquidity-taking campaign.

### 5. Upper Liquidity Consumption

Use:

- `ObservedLargeLiquidityLevel`
- `ObservedEventMarker`
- future raw trade or raw depth windows

Important facts:

- whether the upper wall stayed
- whether it got partially consumed
- whether it pulled before touch
- whether price accepted through it

This is where suppression turns into either:

- a completed squeeze
- or only a temporary poke into resistance

## Derived Interpretation

These belong in `derived interpretation`, not in raw observation:

- `offer_suppression_reversal`
- `lower_support_enabled_release`
- `aggressive_buy_reclaim`
- `upper_liquidity_harvest`
- `manipulation_trace_present`

The system should not promote these labels until it sees both:

- lower support response
- upward consumption or challenge of the upper wall

## Revisit Logic

This pattern becomes even more valuable after the first move.

When price later returns to the lower release zone, the system should ask:

- does the same support area still respond
- was the upper liquidity truly consumed or only tested
- does the old upper band become a new support or flip area
- was the reversal only a squeeze, or the start of a broader directional move

This determines whether the event becomes:

- a one-time trap and squeeze
- or a durable structural shift

## Recommended Future Fields

The most useful future fields for the ATAS collector are:

- `suppression_band_price`
- `suppression_band_persistence_seconds`
- `lower_support_zone_id`
- `release_origin_price`
- `release_travel_ticks`
- `release_multiple_of_manip_leg`
- `release_multiple_of_local_range`
- `upper_liquidity_consumed_ratio`
- `upper_band_revisit_outcome`

## Why This Pattern Matters

This pattern is important because it combines both sides of the tape:

- passive suppression above
- active response from below
- then forced repricing upward into old overhead liquidity

For AI assistance, this is exactly the kind of event that should reduce attention load:

- where did suppression begin
- where did the reversal truly activate
- how far did it travel
- did it actually consume the upper liquidity

That is much more useful than just saying "price reversed."

## Confirmation Signals

- lower support or responsive buying appears before the upward release begins
- aggressive buy flow reclaims price back toward the upper band instead of only producing a weak bounce
- the upper band gets consumed, pulled, or accepted through rather than merely tagged once

## No-Trade Conditions

- do not buy only because the upper wall exists; the lower support response must appear first
- do not buy a random bounce in the middle of a range with no obvious suppression-to-release sequence
- do not keep buying if the upper band remains intact and price cannot show real upward acceptance

## Review Questions

- what evidence proved that lower support was real before the reversal was taken
- did the move truly harvest upper liquidity, or only squeeze into it briefly
- was the long entry aligned with the broader session script or fighting a stronger overhead context
