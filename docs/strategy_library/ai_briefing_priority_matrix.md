# AI Briefing Priority Matrix

## Purpose

This file defines how AI should prioritize strategy candidates and shape `ai_briefing` outputs by preset.

It does not replace:

- `strategy_index.json`
- `reason_code_taxonomy.json`
- `preset_ai_routing_profiles.json`

It adds one more layer:

- which strategies are `primary`
- which strategies are `secondary`
- which strategies are `suppressors`
- what order the briefing should follow

## Core Rule

AI should not start by asking:

- where can I enter

AI should start by asking:

- should this market be suppressed
- which branch is actually active
- what would make the active branch invalid

## Global Briefing Order

1. `suppression_precheck`
2. `active_session_or_context`
3. `dominant_branch`
4. `candidate_setups`
5. `no_trade_and_trap_checks`
6. `trigger_and_invalidation`

## Preset Intent

- `recent_20_bars`
  - fastest branch diagnosis
  - protect against chasing bursts that already lost quality
- `recent_20_minutes`
  - opening / session script first
  - protect against misreading opening extensions as true breakouts
- `focus_regions`
  - strongest suppression and edge-location discipline
  - protect against trading the middle or mistaking visible size for real structure
- `trapped_large_orders`
  - participant pain, forced exits, and lifecycle state
  - protect against misreading trapped inventory or retreating passive liquidity
- `live_depth`
  - maximum skepticism toward displayed size
  - protect against brightness bias and shallow DOM storytelling

## Companion File

Machine-readable matrix:

- `docs/strategy_library/ai_briefing_priority_matrix.json`
