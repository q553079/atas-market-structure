# Thread Coordination

Update this file before or after cross-thread changes that could affect another workstream.
If this file changed since the last read, re-read it before continuing.

## Stable Boundaries

- Do not modify the ATAS collector.
- Do not modify replay or workbench routes.
- Do not modify existing replay, AI, or adapter contracts in `src/atas_market_structure/models.py`.
- Do not directly change UI behavior logic.

## Current Work Split

- Main code thread
  - focused on code and UI-adjacent work
  - currently moving toward `real-time AI chat + preset analysis buttons`
- Strategy-library thread
  - focused on `docs/strategy_library`
  - producing human-readable cards plus machine-readable strategy outputs

## Strategy-Library Deliverables

- Keep human-readable cards in `docs/strategy_library`.
- Create one machine-readable card JSON per strategy.
- Maintain a unified index at `docs/strategy_library/strategy_index.json`.
- Include the fields already enforced by the existing templates:
  - `preferred_presets`
  - `event_kinds`
  - `reason_codes`
  - `required_evidence`
  - `invalidation_signals`
  - `no_trade_conditions`
  - `machine_hints`

## Interface Requirements For Active AI Surfaces

- Provide `event_kind -> strategy_id` mappings.
- Provide `reason_code -> strategy_id` mappings.
- Provide `button preset -> strategy filters` mappings.
- Prefer strategy outputs that strengthen:
  - where not to open
  - false opportunity conditions
  - higher-timeframe and lower-timeframe mismatch errors
  - large-order lifecycle diagnosis
  - post-harvest balance versus reversal differentiation
  - same-price replenishment upgrade criteria
  - gap fill, manipulation leg, and measured move validity boundaries

## Current Strategy-Library Status

- Existing pattern cards have been strengthened with explicit `No-Trade Conditions` and `Review Questions`.
- New pattern cards were added for:
  - `NQ Gap Fill Balance Reclaim`
  - `NQ Manipulation Leg Context`
  - `NQ Measured Move Ladder Context`
  - `Large Order Lifecycle Diagnosis`
- Additional business-chain cards were added for:
  - `Trapped Inventory Release`
  - `Failed Break Acceptance Re-Entry`
  - `Control Handoff After Harvest`
  - `False Liquidity And Pull Behavior`
  - `No-Trade Garbage Time Context`
- Additional session-handoff cards were added for:
  - `Cross-Session Inventory Transfer`
  - `Opening Inventory Correction Vs Continuation`
- Additional opening-auction card was added for:
  - `Initial Balance Extension Vs True Breakout`
- Additional cross-symbol cards were added for:
  - `Anchor Market Leadership`
  - `Leader Failure Divergence Trap`
- Additional breakout-versus-release cards were added for:
  - `Liquidity Raid Vs Breakout Acceptance`
  - `Forced Exit Burst Vs Initiative Continuation`
- Additional microstructure diagnostic cards were added for:
  - `Post-Shock Resiliency Check`
  - `Fake Depth Signature Context`
  - `Stop-Cluster Cascade Exhaustion`
  - `Order-Flow Imbalance Without Price Progress`
  - `Liquidity Provider Retreat Under Toxicity`
- Machine-readable JSON cards now exist under `docs/strategy_library/machine/`.
- Unified machine-readable index now exists at `docs/strategy_library/strategy_index.json`.
- JSON parse and path validation passed for the new machine-readable outputs.

## Coordination Notes

- If another thread needs new strategy ids, add them here before wiring code against them.
- External research memo added at `docs/strategy_library/external_microstructure_research_2026-03-17.md`.
- Structured research index added at `docs/strategy_library/external_doctrine_index.json`.
- Full cross-framework expansion overlay added at `docs/strategy_library/strategy_framework_expansions_2026-03-17.md`.
- Machine-readable framework overlay added at `docs/strategy_library/strategy_framework_overlays.json`.
- Reason-code family taxonomy added at `docs/strategy_library/reason_code_taxonomy.md` and `docs/strategy_library/reason_code_taxonomy.json`.
- Preset AI routing support added at `docs/strategy_library/preset_ai_routing_profiles.json`.
- AI briefing ranking support added at `docs/strategy_library/ai_briefing_priority_matrix.md` and `docs/strategy_library/ai_briefing_priority_matrix.json`.
- Price-action knowledge module added at `docs/strategy_library/price_action_knowledge_2026-03-17.md` and `docs/strategy_library/price_action_knowledge.json`.
- This module is knowledge-first and does not change code contracts or UI logic.
- All current research-index candidate cards are now implemented.
- Newly added strategy ids:
  - `pattern-trapped-inventory-release`
  - `pattern-failed-break-acceptance-reentry`
  - `pattern-control-handoff-after-harvest`
  - `pattern-false-liquidity-and-pull-behavior`
  - `pattern-no-trade-garbage-time-context`
  - `pattern-cross-session-inventory-transfer`
  - `pattern-opening-inventory-correction-vs-continuation`
  - `pattern-anchor-market-leadership`
  - `pattern-leader-failure-divergence-trap`
  - `pattern-liquidity-raid-vs-breakout-acceptance`
  - `pattern-forced-exit-burst-vs-initiative-continuation`
  - `pattern-post-shock-resiliency-check`
  - `pattern-fake-depth-signature-context`
  - `pattern-stop-cluster-cascade-exhaustion`
  - `pattern-order-flow-imbalance-without-price-progress`
  - `pattern-liquidity-provider-retreat-under-toxicity`
  - `pattern-initial-balance-extension-vs-true-breakout`
  - `pattern-gap-bar-retracement-continuation`
  - `pattern-major-trend-reversal-trap-confirmation`
  - `pattern-mother-bar-auction-zones`
- If the active preset names change, update this file and `strategy_index.json` together.
- If a file in `docs/strategy_library` is changed by another thread, note the reason here to avoid duplicate normalization work.

- Deferred source note:
  - `E:/a订单流/book/价格行为/阿布百科全书8800-中文目录.pdf` is too large for full ingestion in this pass and should be used selectively later.
