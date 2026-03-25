# AGENTS.md

## Project identity
- This repo is an ATAS market-structure recognition and replay-workbench system.
- It is NOT an auto-trading system.
- AI must NOT enter the critical recognition path.
- AI may assist review, explanation, and tuning suggestions, but must not directly determine online recognition results.

## V1 scope
- Only support:
  - momentum_continuation
  - balance_mean_reversion
  - absorption_to_reversal_preparation
- Do not expand ontology unless explicitly requested.

## Architecture rules
- Preserve the pipeline:
  observation -> feature_slice -> regime_posterior -> event_hypotheses -> memory_anchors -> belief_state -> event_episode -> episode_evaluation -> tuning_recommendation
- Keep write path and read path separate.
- Append-only data must remain rebuildable and auditable.
- Degraded mode must be preserved.

## File growth rules
- Do not add new business logic to compatibility facade files.
- If a service/repository file exceeds the agreed limit, split it first.
- New code must go into the closest domain module, not back into old giant files.
- If an old giant file is kept for compatibility, add a clear header comment that it is facade-only and must not take new business logic.

### Size guidance
- service/repository files: soft 500, hard 800 lines
- route/controller files: soft 300, hard 500 lines
- model/schema files: soft 300, hard 450 lines
- test files: soft 400, hard 700 lines

## Change workflow
- Before coding, output:
  1. files to change
  2. files not to change
  3. plan
  4. risks
  5. tests to run
- After coding:
  - run relevant tests
  - summarize changed contracts
  - list remaining risks
  - note any follow-up splits or cleanup still needed

## Safety rails
- Do not add new production dependencies without explicit approval.
- Do not silently rename schema_version, enum values, degraded mode names, route contracts, or public payload fields.
- Do not convert the repo into a generic quant platform or execution engine.

## Refactor rule
- For giant-file splits, route reorganizations, schema changes, persistence refactors, or other major work, write a short plan first and index it in `PLANS.md`.
- Each plan should cover scope, invariants to preserve, migration or compatibility approach, tests, and rollback notes.

## Review rule
- During review, follow `code_review.md`.
