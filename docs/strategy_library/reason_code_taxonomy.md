# Reason Code Taxonomy

## Purpose

This file groups the current `reason_codes` into higher-level families for AI interpretation.

The goal is not to replace the existing `reason_codes`.
The goal is to let AI answer better questions such as:

- is this continuation, failure, or no-trade
- is the visible edge real, fake, or retreating
- is the move driven by acceptance, trap release, or only emotional extension

## Families

### 1. Opening Auction And Session Context

Use when the main problem is opening structure, gap context, or session handoff.

- `gap_opening_context`
- `gap_partial_fill`
- `post_fill_acceptance`
- `filled_and_rejected`
- `opening_inventory_correction`
- `opening_inventory_continuation`
- `overnight_imbalance_unwind`
- `first_drive_failed`
- `initial_balance_extension`
- `initial_balance_breakout_confirmed`
- `ib_extension_without_acceptance`
- `ib_false_break_return`
- `cross_session_inventory_transfer`
- `session_handoff_inherited_control`
- `prior_session_inventory_correction`
- `prior_session_zone_still_active`

AI interpretation:

- ask whether the opening move is still the active script
- ask whether outside trade became accepted or only printed a temporary extension
- suppress entries when session definitions are mixed or opening context is unresolved

### 2. Acceptance, Breakout, And Failed Break Logic

Use when the key problem is whether trade outside an old boundary became real.

- `failed_break`
- `outside_hold_failed`
- `returned_to_old_auction`
- `reentry_rotation`
- `liquidity_raid_only`
- `stop_run_not_breakout`
- `breakout_acceptance_confirmed`
- `returned_to_balance_after_sweep`
- `stop_cluster_cascade`
- `outside_acceptance_after_cascade`
- `cascade_exhaustion`
- `stop_release_without_rebuild`
- `caveman_failed_signal_bar`
- `strong_signal_fully_negated`
- `trigger_close_beyond_signal_extreme`
- `failed_breakout_scalp_reversal`

AI interpretation:

- separate sweep from breakout
- separate first extension from accepted outside trade
- ask whether the first retest confirmed the outside branch or invalidated it

### 3. Inventory, Trap, And Forced Exit Logic

Use when participant pain and forced repricing matter more than static geometry.

- `trapped_inventory`
- `failed_reclaim`
- `forced_exit_release`
- `inventory_flip`
- `forced_exit_burst`
- `short_covering_not_new_buying`
- `long_liquidation_not_new_selling`
- `initiative_takeover_confirmed`

AI interpretation:

- ask where the trapped side became objectively wrong
- separate forced exits from fresh initiative
- avoid late chasing once most release fuel is already spent

### 4. Passive Liquidity, False Depth, And Lifecycle Logic

Use when visible size is central but intent is unclear.

- `trapped_large_order`
- `unwinding_large_order`
- `continuing_large_order`
- `spoof_risk`
- `false_liquidity`
- `pull_before_touch`
- `displayed_size_without_defense`
- `visual_bait`
- `false_depth_signature`
- `near_touch_cancellation`
- `opposite_fill_then_cancel`
- `pull_rate_elevated`
- `liquidity_provider_retreat`
- `adverse_selection_risk`
- `defense_to_retreat_transition`
- `reprice_under_toxicity`

AI interpretation:

- ask whether size survived near touch
- ask whether the level still produced real outcome on revisit
- separate fake depth, trapped size, unwinding size, and rational retreat under toxicity

### 5. Defense, Continuation, And Measured Travel

Use when the move still claims to be trending or defending.

- `defended_bid`
- `repeated_replenishment`
- `support_upgrade`
- `upper_liquidity_target`
- `failed_cap`
- `shallow_pullback`
- `trend_continuation`
- `liquidity_attractor`
- `probe_entry`
- `ema20_reclaim`
- `manipulation_leg`
- `secondary_objective`
- `key_position`
- `measurement_ladder`
- `leg_continuity`
- `body_confirmation`
- `post_shock_resiliency`
- `spread_depth_rebuilt`
- `shock_repair_not_continuation`
- `first_pullback_hold_quality`
- `imbalance_without_progress`
- `price_progress_failure`
- `aggression_absorbed`
- `travel_efficiency_decay`
- `h2_l2_pullback_continuation`
- `second_attempt_trend_entry`
- `pullback_count_valid`
- `trend_origin_still_intact`

AI interpretation:

- continuation claims must still show travel efficiency
- defended levels must still produce outcome, not just visual persistence
- measured extension must stay contextual and not be forced after balance returns

### 6. Post-Harvest And Control Handoff

Use after a primary target, harvest, or obvious objective completion.

- `upper_objective_completed`
- `post_harvest_balance`
- `post_harvest_reversal_risk`
- `control_handoff`
- `old_winner_lost_control`
- `first_failed_defense`
- `temporary_pause_not_handoff`

AI interpretation:

- after harvest, stop asking only where continuation can go
- ask whether the old winner still defends the first meaningful revisit
- separate pause from real handoff

### 7. Cross-Symbol Leadership And Divergence

Use when ES / NQ or anchor / execution market disagreement matters.

- `anchor_market_leadership`
- `anchor_market_clearer_than_execution`
- `cross_symbol_confirmation`
- `lagger_should_not_lead`
- `leader_failure_divergence_trap`
- `anchor_market_failed_break`
- `lagger_false_follow`
- `cross_symbol_divergence_trap`

AI interpretation:

- leadership is dynamic, not permanent
- a lagger should not be trusted once the leader already lost hold quality
- ask which market was clearer first and whether that clarity still holds

### 8. No-Trade And Context Suppression

Use to suppress low-quality candidate promotion.

- `no_trade_garbage_time`
- `middle_of_auction_risk`
- `cross_timeframe_conflict`
- `event_noise_without_result`

AI interpretation:

- not every readable market is tradable
- these codes should outrank mediocre setup codes when edge quality is poor

## Priority Rule

When multiple families appear together, AI should usually resolve them in this order:

1. `No-Trade And Context Suppression`
2. `Opening Auction And Session Context`
3. `Acceptance, Breakout, And Failed Break Logic`
4. `Inventory, Trap, And Forced Exit Logic`
5. `Passive Liquidity, False Depth, And Lifecycle Logic`
6. `Post-Harvest And Control Handoff`
7. `Defense, Continuation, And Measured Travel`
8. `Cross-Symbol Leadership And Divergence`

The point is simple:

- first decide if the market should be suppressed
- then decide which session script is active
- then decide whether outside trade became real
- only after that should continuation details be promoted
