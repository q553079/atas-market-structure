CREATE INDEX IF NOT EXISTS idx_observation_bar_instrument_market_time
ON observation_bar (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_bar_instrument_session_market_time
ON observation_bar (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_trade_cluster_instrument_market_time
ON observation_trade_cluster (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_trade_cluster_instrument_session_market_time
ON observation_trade_cluster (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_depth_event_instrument_market_time
ON observation_depth_event (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_depth_event_instrument_session_market_time
ON observation_depth_event (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_gap_event_instrument_market_time
ON observation_gap_event (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_gap_event_instrument_session_market_time
ON observation_gap_event (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_swing_event_instrument_market_time
ON observation_swing_event (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_swing_event_instrument_session_market_time
ON observation_swing_event (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_absorption_event_instrument_market_time
ON observation_absorption_event (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_absorption_event_instrument_session_market_time
ON observation_absorption_event (instrument, session_date, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_observation_adapter_payload_instrument_market_time
ON observation_adapter_payload (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_observation_adapter_payload_instrument_session_market_time
ON observation_adapter_payload (instrument, session_date, market_time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_observation_adapter_payload_dedupe
ON observation_adapter_payload (instrument, dedup_key, payload_hash)
WHERE dedup_key IS NOT NULL AND payload_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_feature_slice_instrument_market_time
ON feature_slice (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_feature_slice_profile_version
ON feature_slice (profile_version);
CREATE INDEX IF NOT EXISTS idx_feature_slice_engine_version
ON feature_slice (engine_version);

CREATE INDEX IF NOT EXISTS idx_regime_posterior_instrument_market_time
ON regime_posterior (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_regime_posterior_profile_version
ON regime_posterior (profile_version);
CREATE INDEX IF NOT EXISTS idx_regime_posterior_engine_version
ON regime_posterior (engine_version);

CREATE INDEX IF NOT EXISTS idx_event_hypothesis_state_instrument_market_time
ON event_hypothesis_state (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_event_hypothesis_state_profile_version
ON event_hypothesis_state (profile_version);
CREATE INDEX IF NOT EXISTS idx_event_hypothesis_state_engine_version
ON event_hypothesis_state (engine_version);

CREATE INDEX IF NOT EXISTS idx_belief_state_snapshot_instrument_market_time
ON belief_state_snapshot (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_belief_state_snapshot_profile_version
ON belief_state_snapshot (profile_version);
CREATE INDEX IF NOT EXISTS idx_belief_state_snapshot_engine_version
ON belief_state_snapshot (engine_version);

CREATE INDEX IF NOT EXISTS idx_projection_snapshot_instrument_market_time
ON projection_snapshot (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_projection_snapshot_belief_state_id
ON projection_snapshot (belief_state_id);

CREATE INDEX IF NOT EXISTS idx_memory_anchor_instrument_reference_time
ON memory_anchor (instrument, reference_time DESC);
CREATE INDEX IF NOT EXISTS idx_memory_anchor_current_version
ON memory_anchor (current_version_id);

CREATE INDEX IF NOT EXISTS idx_memory_anchor_version_anchor_market_time
ON memory_anchor_version (anchor_id, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_memory_anchor_version_instrument_market_time
ON memory_anchor_version (instrument, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_anchor_interaction_anchor_market_time
ON anchor_interaction (anchor_id, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_anchor_interaction_instrument_market_time
ON anchor_interaction (instrument, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_event_episode_instrument_market_time
ON event_episode (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_event_episode_profile_version
ON event_episode (profile_version);
CREATE INDEX IF NOT EXISTS idx_event_episode_engine_version
ON event_episode (engine_version);

CREATE INDEX IF NOT EXISTS idx_event_episode_evidence_episode_id
ON event_episode_evidence (episode_id);
CREATE INDEX IF NOT EXISTS idx_event_episode_evidence_instrument_market_time
ON event_episode_evidence (instrument, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_episode_evaluation_episode_id
ON episode_evaluation (episode_id);
CREATE INDEX IF NOT EXISTS idx_episode_evaluation_instrument_market_time
ON episode_evaluation (instrument, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_tuning_recommendation_instrument_market_time
ON tuning_recommendation (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_tuning_recommendation_evaluation_id
ON tuning_recommendation (evaluation_id);

CREATE INDEX IF NOT EXISTS idx_profile_patch_candidate_instrument_market_time
ON profile_patch_candidate (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_profile_patch_candidate_recommendation_id
ON profile_patch_candidate (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_profile_patch_candidate_proposed_profile_version
ON profile_patch_candidate (proposed_profile_version);

CREATE INDEX IF NOT EXISTS idx_patch_validation_result_candidate_id
ON patch_validation_result (candidate_id);
CREATE INDEX IF NOT EXISTS idx_patch_validation_result_instrument_market_time
ON patch_validation_result (instrument, market_time DESC);

CREATE INDEX IF NOT EXISTS idx_instrument_profile_instrument_active
ON instrument_profile (instrument, is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recognizer_build_active_created
ON recognizer_build (is_active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingestion_run_log_instrument_market_time
ON ingestion_run_log (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_log_outcome_completed
ON ingestion_run_log (outcome, completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_rebuild_run_log_instrument_market_time
ON rebuild_run_log (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_rebuild_run_log_status_started
ON rebuild_run_log (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_dead_letter_payload_instrument_market_time
ON dead_letter_payload (instrument, market_time DESC);
CREATE INDEX IF NOT EXISTS idx_dead_letter_payload_error_code_time
ON dead_letter_payload (error_code, ingested_at DESC);
