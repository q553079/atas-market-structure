# Fabio System Absorption Checklist

## Purpose

This document extracts the durable parts of the Fabio line and translates them into system-design doctrine.

The goal is not to clone a trader's exact execution style.
The goal is to absorb the parts that can survive tool decay:

- market-state first thinking
- location before signal
- aggression only matters when it produces an outcome
- acceptance and rejection as the real decision layer
- risk anchored to meaningful invalidation, not random distance

This checklist should guide future research, domain modeling, AI context design, and eventually ATAS data collection.

## Primary Source Note

This checklist is reinforced by the PDF:

- `E:\a订单流\book\量价分析\Fabio两种剥头皮交易策略的结构与可行性深度分析.pdf`

That document is especially valuable because it does not present Fabio as a bag of tips.
It presents a coherent operating system built around two complementary models and a disciplined environment switch.

## What This PDF Clarifies

The most important clarification from that document is this:

Fabio is not running one setup.
He is running a dual-model operating system:

- trend-following when the auction is imbalanced
- mean reversion when the auction is balanced

That matters for our system because it confirms that the core unit is not the trigger.
The core unit is the active market script.

## Fabio's Two-Model Operating System

### Model A: Trend-Following Imbalance

Core structure:

- identify an imbalanced market
- wait for a pullback into a meaningful location such as LVN or prior structural gap in participation
- require aggressive order-flow confirmation
- enter with small structural invalidation
- target the next high-probability balance or value region

Key ideas:

- do not trade inside balance just because price is moving
- do not chase the first blind break if confirmation is poor
- the best trade is often the continuation after the first pullback
- aggression is meaningful only when it is aligned with location and state

### Model B: Mean-Reversion Balance

Core structure:

- identify a balanced market or consolidation auction
- wait for a false break of the range edge
- require order-flow evidence that the breakout is failing
- wait for re-entry back into balance and often a second chance entry
- target the value center or another high-probability mean area

Key ideas:

- do not guess tops or bottoms before failure is visible
- a false breakout is not just a wick, it is a failed auction
- the best reversal often comes from other participants being trapped at the edge
- mean-reversion exit logic is different from trend exit logic

### Why This Matters

This document makes it clear that Fabio's real edge is:

- environment switching
- location discipline
- live confirmation
- different exit logic for different scripts

That is much more important than any single footprint pattern.

## What To Absorb, Not Copy

The system should absorb:

- how the auction is classified
- how location is prioritized
- how order flow is used as confirmation
- how acceptance or rejection changes the script
- how risk is tied to the actual reason for the trade

The system should not blindly copy:

- someone's exact entry pattern
- somebody else's threshold values
- one market's static setup labels
- chart cosmetics or platform-specific workflow

## Fabio Core Chain

The strongest reusable chain from this line is:

`market state -> location -> aggression -> acceptance or rejection -> risk`

If the system cannot explain all five of these layers, it is not actually reading the market script.

## Checklist

### 1. Start With Auction State

The system must first classify whether the market is acting more like:

- balance
- imbalance
- failed imbalance returning to balance
- transition from balance into expansion

This matters because the same order-flow signal means different things inside balance versus outside it.

System absorption:

- `environment_context` must explicitly encode balance versus imbalance state
- the system should support a script switch between trend continuation and mean reversion rather than forcing one universal setup engine
- support or resistance analysis must know whether a zone sits inside value, at value edge, or outside accepted trade
- AI should refuse to overreact to isolated aggression when the market is still clearly rotational

### 2. Treat Location As First-Class Context

Fabio does not start from "signal." He starts from location.

Location includes:

- value area edges
- POC-type acceptance centers
- low-volume rejection areas
- prior effort zones
- break-and-test locations
- gap and session references

System absorption:

- `key_zone` and `exertion_zone` remain first-class objects
- the system should distinguish trend locations from reversal locations
- examples:
  - trend model: LVN pullback, continuation support or resistance, break-and-test
  - mean-reversion model: range edge, failed auction edge, re-entry into value
- support and resistance must be tied to prior acceptance, rejection, and effort
- any live reaction without meaningful location should be ranked lower

### 3. Order Flow Is Confirmation, Not Background

Aggression matters when it appears at a location that already matters.
Big prints, footprint imbalance, delta pressure, or large displayed liquidity should not be treated as self-sufficient.

System absorption:

- `orderflow_reaction` should be evaluated in relation to `key_zone`
- the AI layer should phrase reactions as "confirms, weakens, or invalidates the zone script"
- isolated order-flow spikes away from important structure should be down-ranked
- the system should allow different confirmation logic per script:
  - trend continuation: aligned aggression
  - mean reversion: failed aggression, absorption, or trap evidence

### 4. Aggression Must Be Judged By Result

Large aggressive buying or selling only matters if it produces a visible result:

- price displacement
- inability of the other side to absorb
- acceptance beyond the level
- continuation after the burst

If aggression prints large numbers but price does not move, that is a different story.

System absorption:

- `initiative_drive` must always be paired with outcome measurement
- important comparisons include:
  - delta versus price travel
  - volume versus continuation
  - aggression versus absorption
- AI should distinguish between:
  - initiative that succeeded
  - initiative that stalled
  - initiative that got trapped
- in mean-reversion contexts, trapped initiative is often more important than raw initiative

### 5. Acceptance And Rejection Are The Real Decision Layer

The key question is not only "did price touch the level."
The key question is whether trade was accepted there or rejected there.

Acceptance often means:

- holding beyond the level
- building trade beyond it
- revisiting without immediate failure

Rejection often means:

- quick return
- inability to hold outside the zone
- aggression that cannot carry price

System absorption:

- `key_level_assessment` must explicitly encode defended, broken, and flipped states
- zone analysis should measure hold time, reclaim behavior, and follow-through
- AI explanations should focus on acceptance and rejection, not just touches
- the system should also encode "returned to balance" versus "held outside balance" because this is central to the dual-model switch

### 6. Big Orders Matter Through Lifecycle, Not Visibility Alone

Displayed size matters only after the system knows what happened to it:

- stayed and got hit
- stayed and defended
- got replenished
- got pulled before execution
- got moved

System absorption:

- `depth_elastic_context` should preserve significant order lifecycle summaries
- the system should prefer "large-liquidity track plus outcome" over raw DOM hoarding
- a bright heatmap stripe is not enough; outcome determines meaning

### 7. Support And Resistance Come From Prior Effort

A meaningful level is usually a price area where prior trade effort changed the market.

Examples:

- large executed volume with meaningful delta
- clear displacement from the zone
- defense on revisit
- failure on revisit with trapped inventory release

System absorption:

- `ObservedExertionZone` remains the backbone for support and resistance context
- the system should remember:
  - how the zone was created
  - how price left it
  - what happened when price returned
- AI should explain support or resistance as inventory and effort context, not just geometry
- the system should also remember whether the zone was born from:
  - continuation effort
  - failed auction
  - range defense

### 8. Stop Runs And Breakouts Must Be Separated

A sweep or stop run is not automatically a breakout.
A breakout is not automatically acceptance.

System absorption:

- the system must separate:
  - liquidity raid
  - break
  - hold
  - failure back into prior range
- `script_state` should distinguish failed break, reclaim, continuation, and trap release
- the failed-break branch should naturally feed the mean-reversion script rather than being treated as a generic reversal label

### 9. Risk Belongs Near The Actual Invalidation

The point of reading auction and order flow is not only direction.
It is also tighter, more meaningful invalidation.

System absorption:

- later execution assistance should anchor risk to:
  - aggression failure
  - failed hold outside balance
  - reclaim failure
  - defense failure on revisit
- the system should avoid generic swing-distance thinking when better invalidation evidence exists
- each script should carry its own target logic and invalidation logic

### 10. Session Structure Matters

Opening auction, initial balance, gap behavior, and session transition matter because they change what "good aggression" means.

System absorption:

- `session_narrative` should remain part of the script layer
- key levels should be tagged with session context when relevant
- AI should not treat Europe build and U.S. release as unrelated events
- the system should explicitly support:
  - London or low-volatility balance behavior
  - New York or high-volatility imbalance behavior
  - intraday model switching when the session changes character

### 11. One Market Can Be Primary, Another Can Be Anchor

Fabio-style thinking tends to reward deep familiarity with one primary instrument.
At the same time, a cleaner anchor market may still improve context.

System absorption:

- the system should support a primary analysis symbol
- `cross_symbol_context` should remain optional but powerful
- AI should be able to say "anchor market is clearer than execution market right now"

### 12. The System Should Explain, Not Merely Alert

The durable edge in this line is not "a signal fired."
It is "the market is doing this, at this place, for this reason."

System absorption:

- AI outputs should prioritize:
  - state
  - location
  - reaction
  - implication
- alerts without explanation should be treated as low-value

## Domain Objects To Strengthen

This line especially reinforces these domain objects:

- `environment_context`
- `key_zone`
- `exertion_zone`
- `orderflow_reaction`
- `level_revisit`
- `key_level_assessment`
- `cross_symbol_context`
- `session_narrative`

If future design work weakens these objects, the system is drifting away from the core doctrine.

## AI Responsibilities Under This Doctrine

The AI layer should be able to answer:

- What kind of auction state are we in?
- Which location matters most right now?
- What aggression is appearing there?
- Is price being accepted or rejected?
- Is this a continuation, failure, reclaim, or trap-release context?
- Where is the real invalidation?
- Should the operator focus, wait, or ignore?

The AI layer should not default to:

- naked buy or sell calls
- isolated delta alerts
- isolated heatmap alerts
- support or resistance labels without evidence chain

## Additional System Implications From This PDF

### 1. The Script Must Carry Its Own Exit Logic

This PDF makes one point unusually clear:

- trend trades should often target the next high-probability balance or prior value region
- mean-reversion trades should often target the value center rather than the far edge

So the system should not use one generic take-profit concept.

### 2. The System Must Remember Why A Trade Exists

If a move started as:

- imbalance continuation
- failed breakout back to value
- range defense

then later analysis and AI commentary must preserve that origin.
Otherwise the system will confuse trend management with reversion management.

### 3. No-Trade Is Part Of The Model

The PDF repeatedly reinforces that Fabio does not treat inactivity as failure.
He treats poor environment as a valid reason to stay out.

System absorption:

- `garbage_time_filter` must remain first-class
- lack of a valid script is itself a meaningful state
- AI should be allowed to say "wait" as a high-value output

### 4. Statistical Self-Knowledge Matters

The PDF stresses repeated execution, known losing streaks, and known sample behavior.

System absorption:

- the future review layer should preserve per-script outcome statistics
- AI should eventually learn to describe:
  - current environment
  - active script
  - historical expectancy of this script family
  - recent degradation or improvement

### 5. Semi-Automation Is Reasonable, Full Blind Automation Is Not

The PDF explicitly supports the idea of algorithmic assistance around alerts and trigger detection.
It does not argue for blind automated trading.

System absorption:

- the ATAS side can eventually automate alerting and evidence capture
- the analysis side can compress attention and context
- auto-execution should remain out of scope unless explicitly requested

## Implications For Future Research

When continuing to study Fabio, Andrea, or adjacent material, prioritize anything that helps the system better model:

- balance versus imbalance transitions
- acceptance and rejection logic
- location ranking
- aggression quality
- large-order lifecycle outcomes
- break-and-test behavior
- reclaim and failed-break logic
- session-structured context

Deprioritize content that is mostly:

- stylistic
- platform-specific cosmetics
- fixed execution tricks without broader context
- indicator stacking without auction meaning

## Design Test

The system has absorbed this line well if it can explain a setup like this:

1. the market was rotational and still inside balance
2. price approached a prior effort zone at value edge
3. aggressive selling appeared but failed to gain acceptance below the zone
4. displayed liquidity at the low got replenished instead of pulled
5. price reclaimed back into value
6. the short script weakened and the reclaim script strengthened
7. invalidation now sits near the failed acceptance, not at an arbitrary wide stop

If the system can only say "delta turned green" or "a level held," it has not absorbed enough.
