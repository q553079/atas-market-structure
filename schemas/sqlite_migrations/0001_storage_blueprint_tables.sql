CREATE TABLE IF NOT EXISTS schema_registry (
    object_name TEXT PRIMARY KEY,
    object_kind TEXT NOT NULL,
    lifecycle_policy TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    notes TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_bar (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_trade_cluster (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_depth_event (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_gap_event (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_swing_event (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_absorption_event (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_adapter_payload (
    observation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_ingestion_id TEXT,
    source_request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_slice (
    feature_slice_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    source_observation_table TEXT,
    source_observation_id TEXT,
    slice_kind TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    data_status_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regime_posterior (
    posterior_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    feature_slice_id TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_hypothesis_state (
    hypothesis_state_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    feature_slice_id TEXT,
    hypothesis_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS belief_state_snapshot (
    belief_state_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    recognition_mode TEXT NOT NULL,
    data_status_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projection_snapshot (
    projection_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    belief_state_id TEXT,
    projection_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_anchor (
    anchor_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    anchor_type TEXT NOT NULL,
    status TEXT NOT NULL,
    freshness TEXT,
    current_version_id TEXT,
    reference_price REAL,
    reference_time TEXT,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    anchor_payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_anchor_version (
    anchor_version_id TEXT PRIMARY KEY,
    anchor_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    freshness TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anchor_interaction (
    anchor_interaction_id TEXT PRIMARY KEY,
    anchor_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    interaction_kind TEXT NOT NULL,
    source_observation_table TEXT,
    source_observation_id TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_episode (
    episode_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    resolution TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_episode_evidence (
    evidence_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    session_date TEXT,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    source_observation_table TEXT,
    source_observation_id TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episode_evaluation (
    evaluation_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tuning_recommendation (
    recommendation_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    episode_id TEXT,
    evaluation_id TEXT,
    source_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_patch_candidate (
    candidate_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    base_profile_version TEXT NOT NULL,
    proposed_profile_version TEXT NOT NULL,
    recommendation_id TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patch_validation_result (
    validation_result_id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instrument_profile (
    instrument TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (instrument, profile_version)
);

CREATE TABLE IF NOT EXISTS recognizer_build (
    engine_version TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_run_log (
    run_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    ingestion_kind TEXT NOT NULL,
    instrument TEXT,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    ingestion_id TEXT,
    dead_letter_id TEXT,
    outcome TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    detail_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rebuild_run_log (
    rebuild_run_id TEXT PRIMARY KEY,
    instrument TEXT,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    triggered_by TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    cleared_tables_json TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS dead_letter_payload (
    dead_letter_id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    ingestion_kind TEXT NOT NULL,
    instrument TEXT,
    market_time TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    request_id TEXT,
    dedup_key TEXT,
    payload_hash TEXT,
    source_ingestion_id TEXT,
    error_code TEXT NOT NULL,
    error_detail_json TEXT NOT NULL,
    raw_payload TEXT NOT NULL
);
