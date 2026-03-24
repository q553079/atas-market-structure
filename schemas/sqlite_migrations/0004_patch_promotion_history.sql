-- 0004_patch_promotion_history.sql
-- Append-only patch promotion history table.
-- Records each promotion event: candidate -> promoted profile version.
-- One candidate can have multiple promotions (e.g., re-promoted after rollback).
-- Append-only: no UPDATE/DELETE allowed on this table.

CREATE TABLE IF NOT EXISTS patch_promotion_history (
    promotion_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    promoted_profile_version TEXT NOT NULL,
    previous_profile_version TEXT NOT NULL,
    promoted_at TEXT NOT NULL,
    promoted_by TEXT NOT NULL,
    promotion_notes TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_patch_promotion_candidate
    ON patch_promotion_history(candidate_id);

CREATE INDEX IF NOT EXISTS idx_patch_promotion_instrument
    ON patch_promotion_history(instrument);

CREATE INDEX IF NOT EXISTS idx_patch_promotion_promoted_at
    ON patch_promotion_history(promoted_at);
