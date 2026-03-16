# Machine-Readable Strategy Template

## Purpose

This template defines the machine-readable layer for the strategy library.

The goal is not to preserve prose only.
The goal is to preserve enough structured context so these downstream components can use it directly:

- replay builder
- strategy candidate matching
- AI review
- AI chat presets
- operator entry replay review

## Output Files

Use these two files together:

- single strategy card:
  - [strategy_card.template.json](D:/docker/atas-market-structure/docs/strategy_library/strategy_card.template.json)
- strategy index:
  - [strategy_index.template.json](D:/docker/atas-market-structure/docs/strategy_library/strategy_index.template.json)

## Authoring Rules

1. Keep `observed evidence` separate from `interpretation`.
2. Write explicit `no_trade_conditions`. This is mandatory.
3. Prefer stable tags over free-form prose where possible.
4. Every strategy must say:
   - where it is relevant
   - what must be observed
   - what confirms it
   - what invalidates it
   - where the operator should not open
5. `preferred_presets` must map to the replay workbench AI buttons.
6. `event_kinds` and `reason_codes` should align with replay packet data, not invented labels.

## Required Top-Level Fields

- `schema_version`
- `strategy_id`
- `title`
- `status`
- `source_path`
- `instrument_scope`
- `session_scope`
- `timeframe_scope`
- `preferred_presets`
- `context_tags`
- `event_kinds`
- `reason_codes`
- `summary`
- `when_relevant`
- `required_evidence`
- `confirmation_signals`
- `invalidation_signals`
- `no_trade_conditions`
- `entry_archetypes`
- `management_notes`
- `review_questions`
- `machine_hints`

## Suggested Controlled Values

### `status`

- `machine_only`
- `human_refined`
- `doctrine_accepted`

### `preferred_presets`

- `general`
- `recent_20_bars`
- `recent_20_minutes`
- `focus_regions`
- `trapped_large_orders`
- `live_depth`

### `session_scope`

- `asia`
- `europe`
- `us_premarket`
- `us_regular`
- `us_after_hours`
- `cross_session`
- `all`

### `timeframe_scope`

- `macro_context`
- `intraday_bias`
- `setup_context`
- `execution_context`
- `cross_timeframe`

## `machine_hints` Guidance

`machine_hints` is for code and AI routing, not human explanation.

Minimum useful members:

- `candidate_priority`
- `match_requirements`
- `disqualifiers`
- `focus_region_bias`
- `entry_review_bias`

Example intent:

- `candidate_priority`
  - how aggressively the strategy should be surfaced when multiple candidates match
- `match_requirements`
  - tags or event combinations that must be present
- `disqualifiers`
  - conditions that should suppress the strategy even if some tags match
- `focus_region_bias`
  - whether the strategy should bias toward support, resistance, pivot, gap edge, etc.
- `entry_review_bias`
  - what kinds of operator mistakes matter most for this strategy

## Example Mapping

Example for a replenished bid launchpad pattern:

- `event_kinds`
  - `same_price_replenishment`
  - `significant_liquidity`
  - `initiative_drive`
- `reason_codes`
  - `defended_bid`
  - `repeated_replenishment`
  - `upper_liquidity_target`
- `preferred_presets`
  - `focus_regions`
  - `trapped_large_orders`
  - `live_depth`

## Minimum Quality Bar

Do not mark a strategy as reusable unless:

- `no_trade_conditions` is specific
- `required_evidence` is concrete
- `invalidation_signals` is actionable
- `review_questions` would actually help replay review

If those are weak, keep the card at `human_refined`, not `doctrine_accepted`.
