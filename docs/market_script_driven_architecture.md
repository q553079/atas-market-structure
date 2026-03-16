# Market-Script-Driven Architecture

See also [`fabio_system_absorption_checklist.md`](fabio_system_absorption_checklist.md) for the dual-model auction and order-flow doctrine.
See also [`shuyin_gap_fill_system_absorption_checklist.md`](shuyin_gap_fill_system_absorption_checklist.md) for the opening-gap and post-fill acceptance doctrine in index futures.

## Purpose

This system should not be designed as an indicator collector.

Indicator edges decay. Tool combinations change. Personnel changes. Market microstructure evolves.
What lasts longer is the underlying capital-behavior logic:

- environment shapes what kind of trade is even possible
- important price zones are created by prior effort, inventory, and acceptance or rejection
- order flow only matters when it is read inside that broader script
- execution should react to live evidence, not to static labels

The goal of the system is therefore not "find a permanent indicator."
The goal is to help the operator read the market script with less cognitive load.

## Core Doctrine

- `environment before signal`
  - A strong signal in the wrong environment is often noise.
- `zone before direction`
  - We care where price is interacting before we care about what trade to place.
- `reaction before prediction`
  - The system should monitor what happens at a zone, not pretend to know the future in advance.
- `observed facts before interpretation`
  - Volume, delta, depth, timing, and reaction belong in observed storage.
  - "support", "trap", "accumulation", and "failed defense" belong in derived analysis.
- `context before event`
  - No single imbalance, delta burst, or heatmap stripe should be treated as sufficient on its own.
- `AI as attention compression, not oracle`
  - The AI layer should reduce operator fatigue by organizing the script and live reactions.
  - It should not act like a black-box entry generator.

## Trading Model

The system should model trading as the interaction between:

- `The Setup`
  - pre-market and higher-timeframe environment assessment
  - key-zone preparation
  - scenario building
- `The Reaction`
  - what order flow and price behavior do when price reaches those zones

The setup provides the script.
The reaction confirms, weakens, or invalidates the script.

## The Market Script Loop

### 1. Pre-Market Script

This layer defines what kind of day or session we may be in.

It should answer:

- Is the environment more likely to behave like range, trend, squeeze, expansion, or machine chop?
- Are we in a positive gamma or negative gamma style environment?
- Did the session open with a meaningful RTH gap relative to prior range or prior value?
- Are we early in a weekly build, mid-cycle absorption, or late-cycle climax?
- Which sessions matter most today?
- Which external anchors should be watched first, such as ES for NQ?

Outputs from this layer:

- `environment_context`
- `session_narrative`
- `key_zones`
- `scenario_tree`

### 2. Live Zone Monitoring

This layer waits for price to approach something that matters.

It should answer:

- Is price approaching a historically important exertion zone?
- Is there unfinished auction, prior effort, option-wall influence, or cross-symbol confluence nearby?
- Is the approach orderly, overlapping, impulsive, squeezed, or exhausted?
- Is the current segment a narrow channel, wide channel, wedge, balance, or vacuum path?

Outputs from this layer:

- `structure_segment`
- `approach_state`
- `cross_symbol_context`

### 3. Order-Flow Reaction

This layer watches the live evidence at or near the zone.

It should answer:

- Is there absorption?
- Is there aggressive initiative?
- Is a displayed large order being filled, replenished, pulled, or ignored?
- Is the move creating a trap?
- Is liquidity thinning into a vacuum move?
- Is delta confirming the push, or is delta failing to move price?
- Is prior inventory being defended, unwound, or trapped?

Outputs from this layer:

- `orderflow_reaction`
- `liquidity_behavior`
- `level_revisit`

### 4. Script Update

This layer converts the live evidence back into context.

It should answer:

- Did the zone hold?
- Did the zone fail?
- Did the zone flip from support to resistance, or vice versa?
- Is this now a continuation script, a failed-break script, a reclaim script, or a trap release?
- Is this still a valid tradeable environment, or has it become garbage time?

Outputs from this layer:

- `key_level_assessment`
- `script_state`
- `attention_prompt`

## Domain Model

### `environment_context`

Observed facts:

- session timing
- volatility regime
- gap state
- positive or negative gamma proxy when available
- range size, overlap, pace, and expansion or compression markers
- garbage-time indicators

Derived interpretation:

- range day candidate
- trend day candidate
- squeeze candidate
- climax candidate
- garbage time

### `key_zone`

Observed facts:

- prior exertion zones
- RTH gap references and post-fill levels
- high-volume price clusters
- strong delta pockets
- unfinished auctions
- session extremes
- option walls or external reference levels
- cross-symbol anchor levels

Derived interpretation:

- support
- resistance
- pivot
- magnet
- likely target

### `exertion_zone`

Observed facts:

- establishing volume
- establishing delta
- price-level concentration
- initiating side
- move distance after the effort
- whether the zone later got revisited

Derived interpretation:

- strong support candidate
- strong resistance candidate
- trapped inventory watch
- broken level
- flipped level

### `level_revisit`

Observed facts:

- revisit timestamp
- revisit volume
- revisit delta
- revisit trade count
- reaction distance
- defense or failure
- post-break follow-through

Derived interpretation:

- defended revisit
- failed defense
- trapped longs
- trapped shorts
- stop-release continuation

### `orderflow_reaction`

Observed facts:

- absorption
- initiative buying or selling
- delta divergence
- unfinished auction interaction
- vacuum move
- trap behavior
- large-liquidity fill or pull

Derived interpretation:

- reaction confirms script
- reaction weakens script
- reaction invalidates script

### `structure_segment`

Observed facts:

- overlap ratio
- swing spacing
- channel width
- wedge compression
- balance boundaries
- expansion speed

Derived interpretation:

- narrow channel
- broad channel
- wedge
- balance
- expansion leg
- exhaustion leg

### `cross_symbol_context`

Observed facts:

- ES interaction at key level
- NQ interaction at corresponding level
- timing lead or lag
- divergence or confirmation

Derived interpretation:

- ES-leading rejection
- ES-leading breakout
- NQ noise with ES clarity
- cross-symbol confirmation

### `garbage_time_filter`

Observed facts:

- narrow rotation
- high overlap
- repeated wick noise
- low directional follow-through
- positive-gamma style pinning when available

Derived interpretation:

- no-trade zone
- low-efficiency environment
- stand aside until release

## What The AI Layer Should Actually Do

The AI layer should help the operator by answering:

- What is today's most likely script?
- What zones matter most right now?
- Which zone is being approached next?
- What is the live reaction at that zone?
- Does the reaction confirm, weaken, or invalidate the script?
- Is this still a tradeable environment or garbage time?

The AI layer should not default to:

- "buy now"
- "sell now"
- single-signal alerts with no context
- blind pattern labeling

## Implications For ATAS Data Collection

The ATAS side should be designed to capture enough observed facts to rebuild the script.

### Continuous Base Layer

Always-on, low-overhead data:

- multi-timeframe bar summaries
- one-second price-path features
- one-second trade and delta summaries
- best bid and ask updates
- local depth imbalance
- significant large-liquidity tracks only
- session and clock state

### Triggered High-Fidelity Layer

Only around meaningful events:

- approach to key zone
- first touch of key zone
- large-order fill or pull
- absorption candidate
- trap candidate
- vacuum release
- failed defense or reclaim

This layer should include:

- buffered raw trade window
- buffered near-price depth window
- footprint or price-level summaries
- revisit-specific measurements

### Memory Layer

Short-lived contextual memory:

- significant large-order tracks
- exertion zones
- revisit outcomes
- broken and flipped levels
- short-term manipulation or defense traces

This layer should not keep full raw DOM forever.

## Must-Have Data For Phase 1

- `environment_context` inputs
  - session timing
  - volatility and overlap proxies
  - garbage-time markers
- `key_zone` inputs
  - large executed volume by price or zone
  - delta by price or zone
  - prior exertion origin
  - unfinished auction markers
- `orderflow_reaction` inputs
  - aggressive volume bursts
  - absorption and replenishment evidence
  - large-liquidity fill or pull evidence
  - local depth imbalance
- `level_revisit` inputs
  - revisit timestamp
  - revisit delta
  - revisit volume
  - reaction distance
  - failure distance
  - post-break follow-through
- `cross_symbol_context` inputs
  - at minimum, an optional ES anchor feed for NQ analysis

## Nice-To-Have Data Later

- market-by-order data when supported
- external option and gamma inputs
- better cross-symbol synchronization
- replay-grade raw event windows
- richer structure geometry classification

## Explicit Non-Goals

- Do not try to preserve every indicator.
- Do not store the full order book forever by default.
- Do not label everything at the source adapter.
- Do not confuse one reaction with a full script.
- Do not add auto-trading logic in this phase.

## Design Test

The architecture is on the right path if, at any moment, the system can explain:

- what environment we are in
- which zones matter
- why those zones matter
- what price is doing at the zone
- what order flow is doing at the zone
- whether the live reaction confirms or breaks the current script
- whether the operator should focus, wait, or ignore
