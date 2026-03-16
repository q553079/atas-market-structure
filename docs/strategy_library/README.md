# Strategy Library

This folder stores durable trading doctrine extracted from:

- books and PDFs
- livestream replays
- creator-specific playbooks
- refined subtitle reviews

The purpose is not to collect random tips.
The purpose is to preserve reusable market logic in a structured form so later AI analysis can reason from context, not from isolated indicators.

## Structure

- `creators/`
  - creator-specific doctrine notes and video-derived strategy cards
- `patterns/`
  - reusable event templates that are not tied to one creator only
- machine-readable templates
  - [MACHINE_READABLE_TEMPLATE.md](D:/docker/atas-market-structure/docs/strategy_library/MACHINE_READABLE_TEMPLATE.md)
  - [strategy_card.template.json](D:/docker/atas-market-structure/docs/strategy_library/strategy_card.template.json)
  - [strategy_index.template.json](D:/docker/atas-market-structure/docs/strategy_library/strategy_index.template.json)

## Workflow

1. Ingest the local video into `data/video_ingest/<source_id>/`
2. Generate machine transcript files and an editable `.srt`
3. If needed, manually correct the subtitle file
4. Distill the corrected content into a strategy card under `docs/strategy_library/creators/`
5. Keep low-confidence observations clearly marked until subtitle quality is improved

## Status Rules

- `machine_only`
  - extracted from auto transcription only
- `human_refined`
  - subtitle or transcript corrected by a human
- `doctrine_accepted`
  - distilled into stable system language and safe to reuse broadly

## Current Entries

- `creators/baocangdawang/2025-08-23-live-replay.md`
  - first-pass card generated from the local replay file
  - ready for subtitle refinement
- `patterns/nq_europe_large_offer_breakdown.md`
  - reusable pattern for Europe-session NQ upper sell-wall pressure plus measured downside release
- `patterns/nq_probe_reversal_toward_upper_liquidity.md`
  - reusable pattern for small probe reversal, liquidity attraction, and EMA20 mean reversion back toward upper liquidity
- `patterns/nq_europe_offer_reversal_into_upper_liquidity.md`
  - reusable pattern for Europe-session suppression, lower support release, and upward consumption of prior upper liquidity
- `patterns/nq_failed_overhead_capping_in_ascent.md`
  - reusable pattern for shallow pullback continuation when overhead sell liquidity fails to truly stop a strong ascent
- `patterns/nq_replenished_bid_launchpad_into_upper_liquidity.md`
  - reusable pattern for same-price bid replenishment, aggressive buyers defending the level, and a launch toward upper liquidity
- `patterns/nq_upper_liquidity_harvest_then_lower_relocation.md`
  - reusable pattern for post-harvest behavior after upper liquidity is consumed, including balance, pullback, and larger reversal outcomes
