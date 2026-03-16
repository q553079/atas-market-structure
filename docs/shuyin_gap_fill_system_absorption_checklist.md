# Shuyin Gap Fill System Absorption Checklist

## Purpose

This document distills the `gap fill` line into durable system doctrine for index futures.

This is not meant as a verbatim transcript of any single livestream.
It is a system-design synthesis of the gap-fill logic you described and the broader opening-auction logic that repeatedly appears in index futures trading.

The goal is to absorb what survives beyond any single presenter's style:

- the opening gap as a script anchor
- gap fill as a test of old value, not a magical destination
- the difference between filling a gap and accepting trade after the fill
- the relationship between gap, prior value, opening auction, and day type

## What This Line Actually Emphasizes

The strongest version of this line does not say:

- every gap should fill

It says something closer to:

- a session gap changes the opening auction
- the gap creates a context problem that the market must solve
- the important question is how price behaves as it approaches, enters, fills, or rejects that gap reference

For the system, this means `gap fill` is not a standalone setup.
It is an opening-script framework.

## Source Boundary

Because this line is mostly explained in livestreams, the system should avoid pretending that every detail is a fixed public rulebook.

So this document captures:

- the durable ideas
- the observable evidence chain
- the system objects that should carry those ideas

It does not claim to reproduce a fixed proprietary checklist word-for-word.

## Core Thesis

In index futures, a meaningful `RTH gap` is often one of the cleanest day-session anchors.

What matters is not only:

- whether the gap fills

What matters more is:

- where the open is relative to prior range and prior value
- how the market approaches the fill
- whether the fill is accepted or rejected
- whether the gap acts as magnet, springboard, or failure point

## Gap Fill Core Chain

The most reusable chain from this line is:

`gap context -> opening auction response -> fill attempt -> post-fill acceptance or rejection -> day script`

If the system cannot explain all five layers, it is not actually reading the opening gap correctly.

## Define The Gap Correctly

For index futures, the system should distinguish at least:

- `RTH close-to-open gap`
  - today's RTH open versus the prior RTH close
- `range gap`
  - today's RTH open outside the prior RTH range
- `value gap`
  - today's RTH open outside the prior value area

These are not interchangeable.
Different gap definitions support different scripts.

## Checklist

### 1. Treat The Gap As An Opening Auction Problem

A gap is not just empty chart space.
It is an opening auction displacement.

System absorption:

- `environment_context` should explicitly store gap state at the session open
- the system should classify whether the opening auction begins inside or outside prior range and prior value
- AI should frame the day as "what is the market trying to do with this opening displacement?"

### 2. Gap Fill Is A Test Of Old Value

When the market moves back toward the gap, it is often testing prior accepted price.
The real question is whether that old value will be reaccepted.

System absorption:

- `gap_fill_attempt` should be treated as an observed event family
- the system should track:
  - first touch of the gap edge
  - partial fill
  - full fill
  - trade through prior close
  - trade into prior value
- AI should ask "did price merely touch the reference, or was trade accepted there?"

### 3. Filling The Gap Is Not The Same As Acceptance

A market can:

- fill the gap and reject
- fill the gap and accept
- partially fill and reverse
- never fill and trend away

This is one of the most important distinctions.

System absorption:

- `post_fill_acceptance_state` should be first-class derived context
- the system should separate:
  - `filled_and_rejected`
  - `filled_and_accepted`
  - `partial_fill_rejection`
  - `no_fill_imbalance`
- AI should avoid simplistic "gap filled, thesis complete" outputs

### 4. Partial Fills Carry Information

Partial fill behavior is often highly informative.
A shallow fill may mean:

- the old reference is still magnetic but not dominant
- the new imbalance remains stronger
- the day is not rotational enough for full repair

System absorption:

- the system should record fill depth as a percentage of the gap
- `partial_fill_depth` should be a measurable observed fact
- gap scripts should treat 20%, 50%, and near-complete repair as different contexts

### 5. Gap Context Must Be Read With Prior Value

Not all gaps mean the same thing.
The same opening gap behaves differently depending on where it sits relative to prior value.

System absorption:

- `gap_reference` should include:
  - prior RTH close
  - prior high and low
  - prior value area high and low
  - prior POC when available
- the system should ask:
  - did we open inside prior value?
  - outside value but inside range?
  - outside both value and range?
- AI should rank gap scripts differently based on this placement

### 6. Opening Tempo Matters

The first drive after the open matters.
So does the character of the attempt to fill.

Questions that matter:

- was the approach smooth or impulsive?
- did the move to the gap happen on initiative or on drift?
- did delta and volume expand into the fill?
- did price hesitate, absorb, or snap through?

System absorption:

- `opening_auction_state` should capture first-drive character
- the system should preserve:
  - opening range behavior
  - time to first fill attempt
  - speed of approach
  - delta into the fill
  - reaction immediately after the fill

### 7. Gap Fill Interacts With Day Type

Gap behavior is one of the best day-type clues in index futures.

Useful branches include:

- `gap_and_go`
- `fill_and_go`
- `fill_and_reverse`
- `partial_fill_trap`
- `failed_fill_then_trend`
- `full_repair_back_to_value`

System absorption:

- `script_state` should allow explicit gap-driven day-script branches
- AI should update the likely day type as the fill logic unfolds

### 8. Gap Fill Is A Context Anchor, Not A Blind Entry

The gap should focus attention.
It should not force a trade.

System absorption:

- the AI layer should use the gap to rank attention, not to auto-generate entries
- `reaction before prediction` still applies
- no-trade is valid if the fill logic is noisy or contradictory

### 9. Overnight Inventory And Session Hand-Off Matter

Many gap-fill behaviors are really inventory-transfer behaviors.
The open is often deciding whether overnight positioning will be corrected, absorbed, or extended.

System absorption:

- the system should preserve:
  - overnight high and low
  - overnight midpoint or key auction center
  - overnight directional inventory proxy
- AI should be able to say whether the open is correcting overnight imbalance or building on it

### 10. Gap Fill Needs Cross-Symbol Context

For ES and NQ, the cleaner gap behavior in one market can help interpret the other.

System absorption:

- `cross_symbol_context` should be able to compare:
  - which market filled first
  - which market rejected first
  - whether one market accepted back into prior value while the other lagged
- AI should be able to identify anchor-market leadership during gap resolution

### 11. The Best Gap Logic Is Often Session-Specific

In index futures, gap logic is strongest around the U.S. regular session open.

System absorption:

- the system should treat `RTH` gaps as primary
- overnight price motion is still important, but the script anchor should be explicit about session boundaries
- ATAS collection and analysis should not mix all hours together without session tags

### 12. The System Should Explain The Gap Script In Plain Language

High-value AI commentary should sound like:

- we opened above prior value but could not hold outside it
- the first fill attempt was accepted and the market is rotating back into old value
- price only partially repaired the gap and initiative buying resumed

Low-value commentary sounds like:

- gap almost filled
- support held
- bullish signal

## Domain Objects To Strengthen

This line especially reinforces these domain objects:

- `environment_context`
- `gap_reference`
- `opening_auction_state`
- `gap_fill_attempt`
- `post_fill_acceptance_state`
- `key_zone`
- `cross_symbol_context`
- `script_state`

## Proposed Observed Objects

### `gap_reference`

Observed facts:

- symbol
- session date
- prior RTH close
- current RTH open
- gap direction
- gap size in points and ticks
- prior range relation
- prior value relation

### `gap_fill_attempt`

Observed facts:

- first touch timestamp
- fill depth percentage
- full-fill timestamp when applicable
- delta during approach
- volume during approach
- speed of approach

### `post_fill_acceptance_state`

Observed facts:

- hold time beyond fill reference
- rejection distance
- reclaim or failure back through fill line
- whether price entered prior value
- whether price held inside prior value

These should stay in observed storage before interpretation.

## Proposed Derived Objects

### `derived_gap_script`

Derived interpretation candidates:

- `gap_and_go_candidate`
- `fill_and_reverse_candidate`
- `fill_and_accept_candidate`
- `partial_fill_trap_candidate`
- `inventory_correction_candidate`
- `failed_gap_repair_candidate`

### `gap_key_level_assessment`

Derived interpretation:

- gap edge as support
- gap edge as resistance
- prior close as pivot
- prior value edge as acceptance gate

## AI Responsibilities Under This Doctrine

The AI layer should be able to answer:

- What kind of opening gap do we have today?
- Where did we open relative to prior range and prior value?
- Is the current move an attempt to repair the gap or extend away from it?
- Was the fill accepted or rejected?
- Did the fill change the day script?
- Is the market correcting overnight inventory or expressing new initiative?
- Which gap-related levels deserve attention next?

The AI layer should not default to:

- "gaps always fill"
- "the fill is the trade"
- "partial fill means failure"
- generic support or resistance labels without opening context

## Implications For ATAS Data Collection

The ATAS side should preserve enough evidence to rebuild the opening-gap script.

### Must-Have

- prior RTH close
- current RTH open
- prior high and low
- prior value area high and low when available
- first 1 to 5 minute price path
- time to first gap-touch
- delta and volume into the fill attempt
- reaction after touch or full fill
- overnight high and low
- session tags

### Nice-To-Have

- cross-symbol synchronization for ES and NQ
- opening range state
- DOM behavior near prior close and value edge
- high-fidelity trigger window around first fill and post-fill reaction

## Additional System Implications

### 1. Gap Fill Should Become A First-Class Key-Zone Family

Gap references are not just miscellaneous lines.
They are among the most important session anchors in index futures.

### 2. The Opening Script Should Be Able To End In "Wait"

Many opens are too noisy.
The system must be allowed to say:

- the gap is informative, but the fill logic is not clean yet

### 3. Gap Logic Should Be Stored As Process, Not Snapshot

A single screenshot of price at the prior close is weak.
The real information is in:

- how price got there
- how quickly
- with what order-flow character
- what happened after touching it

## Design Test

The system has absorbed this line well if it can explain a scenario like this:

1. ES opens above the prior RTH range and prior value
2. the first drive fails to extend cleanly
3. price rotates down into the gap on weakening initiative
4. the gap fully fills and trades back into prior value
5. trade is accepted inside value rather than instantly rejected
6. the original `gap and go` script weakens
7. the day script shifts toward repair and rotation instead of continuation

If the system can only say "the gap filled," it has not absorbed enough.
