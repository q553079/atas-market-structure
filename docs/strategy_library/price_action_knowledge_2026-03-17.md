# Price Action Knowledge Module

This note consolidates price-action doctrine from the local source pack into AI-usable knowledge.
It is intentionally more "knowledge-first" than "signal-first".
The goal is to help later AI analysis answer:

- what kind of market is this?
- what kind of entry is valid here?
- where should not open, and why?

## Source Scope

- `docs/strategy_library/_source_extracts/price_action/rose_gap_bar.txt`
- `docs/strategy_library/_source_extracts/price_action/rose_mother_bar.txt`
- `docs/strategy_library/_source_extracts/price_action/rose_mtr.txt`
- `docs/strategy_library/_source_extracts/price_action/rose_caveman.txt`
- `docs/strategy_library/_source_extracts/price_action/rose_strategy_compendium.txt`
- `docs/strategy_library/_source_extracts/price_action/abu_top_10_patterns.txt`
- `docs/strategy_library/_source_extracts/price_action/taifei_pa_foundation.txt`
- `docs/strategy_library/_source_extracts/price_action/fangfangtu_pa_foundation.txt`

`阿布百科全书8800-中文目录.pdf` is too large for full ingestion in this pass.
Treat it as a later selective-reference source, not a current blocking dependency.

## Foundation Model

### 1. Environment First, Signal Second

The most important price-action question is not "what pattern is this?"
It is "what environment is this?"

The base environment split from the PA trainee material is:

- breakout / spike
- narrow channel
- broad channel
- trading range

This matters because the same signal bar means different things in different environments.
A strong reversal bar in a tight trading range is often not enough.
A weak pullback bar in a strong trend can still be enough.

### 2. Breakout, Test, Pullback, Range, Reversal Are One Loop

The local PA notes repeatedly describe the same loop:

1. breakout tries to create new advantage
2. test checks whether breakout sponsors still defend
3. pullback reveals whether it is continuation or only repair
4. failure can return the market to range
5. repeated failure can become reversal

AI should treat these as one chain, not separate disconnected ideas.

### 3. Range Is Normal, Clean Trend Is Rare

The PA trainee notes heavily reinforce:

- market spends most time balancing
- many breakout attempts fail
- many reversal attempts also fail

Implication:

- in range edges, fading false breaks is often rational
- in trend environments, fading strong continuation too early is often a mistake
- in the middle of range, many signals should be suppressed

### 4. Price Control Matters More Than Pattern Naming

Several sources converge on the same doctrine:

- who got trapped?
- who is exiting?
- who still controls the retest?
- did the market actually accept outside, or just poke outside?

This is more important than whether a setup is named MTR, Caveman, H2, or final flag.

### 5. Where Not To Open Is First-Class Knowledge

Recurring no-trade principles from the source pack:

- do not open from the middle of a range
- do not fade a strong breakout only because it looks extended
- do not trust a weak signal bar in chop
- do not use range-fade logic once a true breakout is already being accepted
- do not force MTR logic in a background that is still only a shallow pullback
- do not assume a third push must reverse immediately; late trends can still overshoot

## Environment Diagnostics

### Breakout / Spike

Characteristics:

- consecutive trend bars
- closes near extremes
- little overlap
- little time for pullbacks

Operator meaning:

- only favor trend continuation or first pullback entries
- avoid fading without strong trap evidence

Do not open:

- against the spike from the first "looks too far" feeling
- inside the middle of the spike without a clear retest failure

### Narrow Channel

Characteristics:

- short pullbacks
- few bars in correction
- correction depth shallow

Operator meaning:

- continue preferring trend-direction entries
- treat countertrend setups as lower quality

Do not open:

- countertrend just because a signal bar appears
- late if the stop must sit too far from the original trend start

### Broad Channel

Characteristics:

- trend still intact
- pullbacks deeper and more visible
- countertrend traders can scalp successfully

Operator meaning:

- prefer buy-the-pullback / sell-the-rally with more selectivity
- evaluate whether pullback stays under 50 percent or grows too deep

Do not open:

- as if it were a clean breakout environment
- with blind continuation logic after pullbacks deepen past regime thresholds

### Trading Range

Characteristics:

- overlapping bars
- both sides keep making money near edges
- strong bars fail to follow through

Operator meaning:

- favor edge fades and failed-break logic
- suppress middle-of-range entries

Do not open:

- in the middle third of the range
- on weak signal bars
- on first breakout attempts without confirmation

## Entry Knowledge Families

### 1. Gap Bar Retracement Continuation

Core idea:

- a Gap Bar is not only a literal chart gap
- it can be a strong impulse bar, a sequence of strong impulse bars, or an implicit supply/demand imbalance zone

Best environment:

- breakout or strong trend
- first pullback after clean displacement

Required evidence:

- clear impulse away from balance
- minimal overlap
- first meaningful retracement
- retracement reaches a known reaction zone, often around the middle or deeper retrace band

What makes it work:

- early participants defend cost basis
- late participants use pullback to join
- the market has not yet returned to full balance

Where not to open:

- late in a messy trend after multiple retests
- when the supposed Gap Bar is really just overlapping chop
- when the retracement is already too deep and acceptance back into prior balance is visible

AI should ask:

- was the impulse truly clean, or just loud?
- is this the first retracement or a late recycle?
- did the pullback stall where continuation traders should defend?

Current library links:

- strengthens `pattern-gap-fill-balance-reclaim`
- strengthens `pattern-nq-failed-overhead-capping-in-ascent`

### 2. Mother Bar Auction Zones

Core idea:

- Mother Bar defines a temporary micro-auction
- its internal fractions define buy zone, sell zone, trap zone, and competition points

Best environment:

- trading range
- early trend pullback
- late third-leg wedge exhaustion

Required evidence:

- clear mother bar plus inside balance
- known context: range, leg 1/2 trend, or late leg 3 exhaustion
- price reaches outer zones, not just the middle

What makes it work:

- in range: most breaks fail, so trap zones can be faded
- in early trend: same structure can be used for continuation, not fade
- in late trend: third leg can flip the logic toward reversal

Where not to open:

- from the middle of the mother bar
- fading outer zones during already accepted breakout conditions
- using range-fade logic without asking which trend leg the market is in

AI should ask:

- is this mother bar inside a range, early trend, or late wedge?
- did price reach the trap zone or only the middle?
- is breakout being assumed before body closes prove it?

Current library links:

- strengthens `pattern-no-trade-garbage-time-context`
- strengthens `pattern-liquidity-raid-vs-breakout-acceptance`
- candidate for later formalization as a dedicated card

### 3. Major Trend Reversal Through Trapped Breakout Traders

Core idea:

- MTR is not "reversal because price looks high/low"
- it is reversal because a breakout side got trapped, then confirmation proves they are wrong

Best environment:

- late trend
- edge of key support/resistance
- wedge exhaustion
- failed breakout from a narrow range

Required evidence:

- strong signal bar
- trap bar that breaks beyond the signal then fails
- later body close through the signal bar's open or extreme

What makes it work:

- trapped breakout traders must exit
- their exits add fuel to the new direction
- the reversal is strongest when the market invalidates the exact area breakout traders relied on

Where not to open:

- before confirmation
- against a context that still looks like a normal pullback
- when the signal bar is weak and there is no real sponsor failure

AI should ask:

- who got trapped here?
- where do they have to exit?
- has price actually crossed the point that proves them wrong?

Current library links:

- strongly strengthens `pattern-trapped-inventory-release`
- strongly strengthens `pattern-failed-break-acceptance-reentry`

### 4. Caveman Failed Signal Bar Trigger

Core idea:

- a strong signal bar is followed immediately by a stronger opposite trigger bar
- the failure is so direct that an aggressive scalp entry becomes viable

Best environment:

- late trend
- failed breakout
- fast trap-and-release context

Required evidence:

- very strong signal bar
- opposite trigger bar closing beyond the signal bar's open or extreme
- room for at least scalp target and ideally 1R

What makes it work:

- one side used maximum effort
- the other side erased it immediately
- failed effort implies strong loss of control

Where not to open:

- if the signal bar is weak
- in overlapping chop
- if trigger does not clearly negate the signal bar

AI should ask:

- was the signal bar truly strong?
- did the trigger merely oppose it, or fully negate it?
- is this a scalp reversal, or already late and crowded?

Current library links:

- strengthens `pattern-trapped-inventory-release`
- overlaps with MTR execution logic

### 5. FOFS: Failure Of Failure Is Swing

Core idea:

- a first failure often only creates a scalp
- if the attempt to continue that failure also fails, the opposite swing can start

Best environment:

- range-to-break transition
- wedge top/bottom
- failed continuation after a trap

Required evidence:

- first side fails
- second side tries to exploit that failure
- second side also fails to gain control
- midpoint or structure-control line gets reclaimed

What makes it work:

- both short-term narratives get invalidated
- once the second narrative fails, trapped traders on both sides can fuel a bigger swing

Where not to open:

- before the second failure is visible
- if the market is still in a balanced middle with no control shift

AI should ask:

- what exactly failed first?
- what was the failure of that failure?
- after the second failure, who controls the midpoint or structure line?

Current library links:

- strengthens `pattern-control-handoff-after-harvest`
- strengthens `pattern-liquidity-raid-vs-breakout-acceptance`

### 6. H1 / H2 / L1 / L2 Pullback Entries

Core idea:

- entries after a pullback are not random
- first and second attempts after a pullback have distinct meanings

Best environment:

- trend or strong leg inside a range
- first or second pullback after impulse

Required evidence:

- clear prior trend
- actual pullback, not just two same-direction bars
- signal bar aligned with continuation attempt

What makes it work:

- trend traders re-enter on pullback completion
- second attempt often matters because the first one can fail in noisy pullbacks

Where not to open:

- taking H1 in a messy deep pullback with no strength
- continuing to count endlessly inside a channel that is degrading into a range
- treating every tiny pause as a valid count

AI should ask:

- is the market still in trend, or already in broad-channel/range conversion?
- is this a real first or second attempt, or bad counting inside noise?
- is the stop logical relative to pullback low/high and trend origin?

Current library links:

- strengthens `pattern-nq-failed-overhead-capping-in-ascent`
- strengthens `pattern-nq-probe-reversal-toward-upper-liquidity`

### 7. Final Flag And Late-Trend Reversal

Core idea:

- a continuation-looking flag can become a reversal trap late in trend
- final flags are continuation patterns in appearance, reversal patterns in outcome

Best environment:

- late bull or bear trend
- near magnet, measured move, channel edge, or climax zone

Required evidence:

- mature trend
- small sideways pause or tight range
- context showing reduced follow-through or nearby objective completion

What makes it work:

- traders still expect continuation
- if continuation fails, trapped trend followers fuel the reversal

Where not to open:

- treating every pause as final flag
- countertrend before the market proves continuation failure
- assuming reversal just because trend is old

AI should ask:

- is this just a normal flag, or a late flag near objective completion?
- did continuation actually fail, or has it simply paused?

Current library links:

- strengthens `pattern-control-handoff-after-harvest`
- strengthens `pattern-post-shock-resiliency-check`

### 8. Range Edge Reversal And Failed Break Fade

Core idea:

- in a range, first breakout attempts often fail
- the best entry is often not the breakout, but the failure back into the range

Best environment:

- established range
- repeated overlap
- both sides previously profitable near edges

Required evidence:

- clear edge
- failed break
- rejection or re-entry bar
- room back toward the middle or opposite edge

What makes it work:

- breakout traders get trapped
- range traders gain confidence
- price often rotates back through the auction

Where not to open:

- range middle
- after the market has already built accepted trade outside the range
- when breakout has strong follow-through and no rejection

AI should ask:

- is this still a range, or has the market already converted?
- did breakout traders get trapped, or are they winning?

Current library links:

- strongly strengthens `pattern-failed-break-acceptance-reentry`
- strongly strengthens `pattern-no-trade-garbage-time-context`

### 9. Buy Zone / Sell Zone Memory

Core idea:

- zones are created by where trapped traders want relief and where responsive traders want entry
- prior signal bars and their later extremes define memory bands

Best environment:

- range edges
- retest of prior trapped inventory zones
- failed trend continuation after strong signal bar

Required evidence:

- identifiable prior signal bar
- later move that trapped the original side
- revisit into their relief zone

What makes it work:

- trapped traders exit at cost or better
- responsive traders fade that relief flow

Where not to open:

- if no trapped inventory story exists
- if the zone is being hit during strong accepted breakout conditions

AI should ask:

- whose cost basis lives in this zone?
- will this revisit produce relief exits, fresh initiative, or both?

Current library links:

- strongly strengthens `pattern-trapped-inventory-release`
- strengthens `pattern-large-order-lifecycle-diagnosis`

### 10. Opening Reversal And Early Session Trap

Core idea:

- the first opening drive is often not the real day trend
- it can be a test, inventory correction, or trap before reversal

Best environment:

- session open
- early trend extension
- strong opening burst into prior support/resistance or gap structure

Required evidence:

- opening drive reaches meaningful reference
- follow-through degrades
- reversal bar or failed continuation forms

What makes it work:

- open injects emotional participation
- once that first burst fails, trapped opening traders can fuel reversal

Where not to open:

- blindly with the first opening burst
- without knowing whether the opening move is correction or continuation
- after the opening reversal already spent its best energy

AI should ask:

- was the opening drive real day control or only emotional opening flow?
- did the first reversal trap opening traders?

Current library links:

- strongly strengthens `pattern-opening-inventory-correction-vs-continuation`
- strengthens `pattern-initial-balance-extension-vs-true-breakout`

## Shared No-Trade Rules For AI

Suppress setup promotion when one or more of these are true:

- the market is in the middle of a clear range
- signal bar quality is weak and context does not rescue it
- breakout has no follow-through and no retest information yet
- reversal idea depends only on "too far" or "too many bars"
- trend origin is still intact, so the move is still more likely a pullback than a reversal
- the setup offers no logical stop or no clear target room

## How This Strengthens The Existing Library

Most useful reinforcement areas:

- explicit environment gating before setup promotion
- stronger explanation of trapped-trader fuel
- better separation of pullback versus reversal
- clearer rules for range-edge fade versus accepted breakout
- better "where not to open" knowledge for AI conversations

Existing strategy cards most strengthened by this note:

- `pattern-trapped-inventory-release`
- `pattern-failed-break-acceptance-reentry`
- `pattern-liquidity-raid-vs-breakout-acceptance`
- `pattern-no-trade-garbage-time-context`
- `pattern-opening-inventory-correction-vs-continuation`
- `pattern-initial-balance-extension-vs-true-breakout`

## Recommended Formalization Backlog

Highest-value future strategy cards to formalize from this knowledge module:

- `pattern-caveman-failed-signal-bar-trigger`
- `pattern-h2-l2-pullback-continuation-framework`
