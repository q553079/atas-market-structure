# External Microstructure Research Notes (2026-03-17)

## Purpose

This note captures externally sourced market-microstructure and auction-domain findings that are useful for the strategy library.

It is not a trading recommendation document.
It is a doctrine input for:

- AI analysis quality
- strategy-candidate filtering
- no-trade suppression
- future machine-readable card design

When a section says `Strategy inference`, that part is an inference for this repository's strategy layer rather than a direct claim from the source.

## Source Quality

- `official`: regulator or exchange documentation
- `academic`: paper or journal article
- `vendor education`: useful secondary source, lower authority than official or academic material

## 1. Order-Flow Imbalance Matters More Than Raw Volume

Sources:

- academic: [Cont, Kukanov, Stoikov, "The Price Impact of Order Book Events" (2010)](https://arxiv.org/abs/1011.6402)
- academic: [Easley, Lopez de Prado, O'Hara, "Flow Toxicity and Liquidity in a High-frequency World" (2012)](https://doi.org/10.1093/rfs/hhs053)

External finding:

- short-horizon price change is explained more robustly by order-flow imbalance than by raw trading volume alone
- imbalance interacts with market depth, so the same aggressive flow matters differently in thick and thin books
- toxicity rises when liquidity providers are likely trading against more informed or one-sided flow

Strategy inference:

- AI should rank `who is hitting whom, where, and against what depth` above simple volume spikes
- large prints without meaningful imbalance or without price progress should be downgraded
- a one-sided flow burst in a thin book deserves different treatment from the same burst in a thick book

No-trade implication:

- do not open just because volume expanded if the book did not lose balance in the same direction
- do not equate strong delta with strong edge when price is not advancing against the imbalance

Useful machine additions:

- `order_flow_imbalance_score`
- `price_progress_per_imbalance_unit`
- `depth_adjusted_imbalance_score`
- `toxicity_watch`

## 2. Book Resiliency After Aggression Decides Continuation Versus Repair

Sources:

- academic: [Xu, Gould, Howison, "Limit-order book resiliency after effective market orders" (2016)](https://arxiv.org/abs/1602.00731)
- academic: [Mastromatteo et al., "Order Flows and Limit Order Book Resiliency on the Meso-Scale" (2017)](https://arxiv.org/abs/1708.02715)

External finding:

- after liquidity shocks, spread, depth, and order intensity often normalize quickly
- the post-shock recovery pattern differs by aggressiveness of the initiating order
- continuation versus resiliency is visible in what the book does after the hit, not only during the hit

Strategy inference:

- the system should treat the first pullback after a sweep or burst as a decisive diagnostic checkpoint
- real continuation needs evidence that the new side can keep the gained ground after the shock
- if spread and depth normalize but price cannot extend, the move is more likely a completed shock than a durable takeover

No-trade implication:

- do not chase the first burst before the book shows whether it is rebuilding for continuation or repairing back toward balance
- do not assume the hit was weak only because the first counter-rotation appears; test whether the new side still holds control

Useful machine additions:

- `post_shock_resiliency_window_seconds`
- `spread_recovery_rate`
- `depth_recovery_rate`
- `first_pullback_hold_quality`

## 3. Persistent One-Way Order Flow Does Not Automatically Mean Immediate Price Continuation

Sources:

- academic: [Toke, "The adaptive nature of liquidity taking in limit order books" (2014)](https://arxiv.org/abs/1403.0842)

External finding:

- when order flow becomes more predictable in one direction, opposite-side liquidity can adapt
- price response does not scale mechanically with directional persistence because book participants respond

Strategy inference:

- repeated same-direction prints should not automatically upgrade a setup unless price is still making usable progress
- a trapped-side exit burst can coexist with rapidly adapting opposite-side liquidity

No-trade implication:

- do not keep adding to a direction simply because recent prints are one-way if price response is deteriorating
- do not treat persistence as edge when efficiency of travel is shrinking

Useful machine additions:

- `progress_decay_after_repeated_aggression`
- `same_side_flow_persistence`
- `travel_efficiency_ratio`

## 4. Stop-Loss Clusters Can Create Cascades, But Cascades Are Not Proof Of New Value

Sources:

- academic: [Osler, "Stop-loss orders and price cascades in currency markets" (2005)](https://www.sciencedirect.com/science/article/pii/S0261560604001147)

External finding:

- markets can accelerate rapidly once stop clusters are reached
- stop-driven response can be larger and last longer than other clustered order responses
- non-informative order flow can still move price materially

Strategy inference:

- a stop cascade should be modeled as a distinct business event, not automatically as genuine new initiative
- AI should separate `stop-release burst` from `new accepted auction`

No-trade implication:

- do not assume that a fast extension after a stop cluster proves durable continuation
- do not fade every cascade immediately either; wait to see whether outside trade becomes accepted or exhausts

Useful machine additions:

- `stop_cluster_cascade_watch`
- `outside_acceptance_after_cascade`
- `cascade_exhaustion_score`

## 5. Fake Depth Has Specific Regulatory Signatures

Sources:

- official: [CFTC final anti-disruptive trading guidance (2013)](https://www.cftc.gov/LawRegulation/FederalRegister/FinalRules/2013-12365.html)
- official: [CFTC spoofing enforcement release on Cobb-Webb (2023)](https://www.cftc.gov/PressRoom/PressReleases/8760-23)
- official: [CFTC spoofing enforcement release on Tower Research (2019)](https://www.cftc.gov/PressRoom/PressReleases/8074-19)

External finding:

- the CFTC explicitly treats creating an appearance of false market depth as spoofing-related behavior
- a recurring enforcement pattern is: genuine order on one side, larger displayed orders on the other side, cancellations after the genuine order receives fills
- visible size alone is not evidence of true directional intent

Strategy inference:

- AI should never promote `displayed size` into support or resistance without checking hold quality, refill behavior, and what happens when price gets near it
- a large displayed order that disappears as price approaches should bias toward `visual bait`, not `defense`

No-trade implication:

- do not open solely because a large order appears in the first few price levels
- do not assume same-price replenishment exists when size is mostly flashing and pulling

Useful machine additions:

- `displayed_size_pull_rate`
- `resting_size_survival_near_touch`
- `opposite_side_fill_then_cancel_pattern`
- `false_depth_signature_score`

## 6. Inventory Risk Explains Why Passive Liquidity Can Defend, Retreat, Or Requote

Sources:

- academic: [Avellaneda, Stoikov, "High-frequency trading in a limit order book" (2008)](https://math.nyu.edu/~avellane/HighFrequencyTrading.pdf)
- academic: [Easley, Lopez de Prado, O'Hara, "Flow Toxicity and Liquidity in a High-frequency World" (2012)](https://doi.org/10.1093/rfs/hhs053)

External finding:

- liquidity providers manage inventory risk and adverse-selection risk, not just directional conviction
- under toxic flow, passive liquidity may retreat or reprice rather than continue defending

Strategy inference:

- a large bid or offer can disappear because inventory or toxicity conditions changed, not because the original read was "wrong" in a simplistic sense
- the strategy library should diagnose `defense`, `retreat`, `inventory offload`, and `re-quote` as separate branches

No-trade implication:

- do not over-trust static DOM size when the inventory-holding side is under adverse-selection pressure
- do not label retreating liquidity as support or resistance failure until the post-retreat branch is visible

Useful machine additions:

- `liquidity_provider_retreat_watch`
- `inventory_pressure_proxy`
- `defense_to_retreat_transition`

## 7. Lead-Lag Is Dynamic, Not Permanent

Sources:

- academic: [Ma, Xiao, Mi, "Measuring the dynamic lead-lag relationship between the cash market and stock index futures market" (2022)](https://www.sciencedirect.com/science/article/pii/S1544612322002008)
- official: [CME FX Market Profile User Guide](https://www.cmegroup.com/tools-information/webhelp/fx-market-profile/Content/FXMarketProfile.pdf)

External finding:

- linked markets often show lead-lag behavior, but leadership changes over time and is not fixed forever
- comparative liquidity and order-book context help explain which market is clearer at a given moment

Strategy inference:

- cross-symbol cards should remain dynamic: `leader today` is a state, not an identity
- AI should prefer the market with cleaner acceptance or rejection and better liquidity context at the decision point

No-trade implication:

- do not force ES or NQ into permanent leadership roles
- do not assume lagging confirmation is valid if the prior leader has already degraded

Useful machine additions:

- `current_anchor_symbol`
- `cross_symbol_lead_quality`
- `leader_degradation_watch`

## 8. Initial-Balance And Value-Area Statistics Are Useful Only With Session-Specific Validation

Sources:

- vendor education: [ATAS, "How to improve trading using the Market Profile in ATAS"](https://atas.net/blog/how-to-improve-trading-using-the-market-profile/)

External finding:

- initial-balance and value-area behavior can be statistically useful, but breakout, extension, and day-type definitions are sensitive to session framing
- the source explicitly warns against using such statistics blindly

Strategy inference:

- AI should treat initial-balance logic as a contextual filter, not a self-sufficient trade signal
- `breakout`, `extension`, and `accepted outside trade` should stay separate labels

No-trade implication:

- do not open from an IB statistic alone without session-specific validation
- do not call every push beyond IB a breakout if price does not settle there

Useful machine additions:

- `initial_balance_definition_used`
- `ib_extension_vs_settlement`
- `value_area_reacceptance_state`

## Highest-Value New Card Candidates

These are proposed candidates, not yet wired into `strategy_index.json`.

- `pattern-post-shock-resiliency-check`
  - purpose: decide whether a sweep or burst is continuing or already repairing
- `pattern-stop-cluster-cascade-exhaustion`
  - purpose: separate stop-driven extension from accepted new auction
- `pattern-fake-depth-signature-context`
  - purpose: distinguish displayed size from bona fide defense
- `pattern-order-flow-imbalance-without-price-progress`
  - purpose: suppress trades where imbalance exists but price cannot travel
- `pattern-initial-balance-extension-vs-true-breakout`
  - purpose: keep IB logic contextual and session-specific
- `pattern-liquidity-provider-retreat-under-toxicity`
  - purpose: explain when passive size should be treated as retreating inventory rather than support or resistance

## Immediate AI-Level Recommendations

- Promote `hold quality after event` above `event happened`.
- Promote `price progress relative to imbalance` above `volume expanded`.
- Treat `displayed size` as suspicious until survival near touch and refill behavior are proven.
- Treat `stop cascade` as a separate branch from `new acceptance`.
- Treat `cross-symbol leadership` as dynamic, not static.
- Add more suppression logic for `large event, weak progress`.
