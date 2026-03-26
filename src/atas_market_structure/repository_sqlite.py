from __future__ import annotations

# legacy implementation shell under active split; route new domain persistence logic to repository_* modules first

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from atas_market_structure.repository_records import *
from atas_market_structure.repository_workbench_events_sqlite import SQLiteWorkbenchEventRepository
from atas_market_structure.repository_workbench_event_outcomes_sqlite import SQLiteWorkbenchEventOutcomeRepository
from atas_market_structure.repository_workbench_prompt_traces_sqlite import SQLiteWorkbenchPromptTraceRepository
from atas_market_structure.storage_models import (
    StoredBeliefStateSnapshot,
    StoredDeadLetterPayload,
    StoredEpisodeEvaluationRecord,
    StoredEventEpisodeRecord,
    StoredIngestionRunLogRecord,
    StoredInstrumentProfileVersion,
    StoredPatchValidationResult,
    StoredProfilePatchCandidate,
    StoredRecognizerBuildVersion,
    StoredTuningRecommendation,
)
from atas_market_structure.storage_repository import SQLiteStorageBlueprintRepository

logger = logging.getLogger(__name__)

class SQLiteAnalysisRepository:
    """SQLite persistence for observed facts, derived analysis, liquidity memory, and replay workbench chat state."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._storage_blueprint_repository = SQLiteStorageBlueprintRepository(database_path=database_path)
        self._workbench_event_repository = SQLiteWorkbenchEventRepository(owner=self)
        self._workbench_event_outcome_repository = SQLiteWorkbenchEventOutcomeRepository(owner=self)
        self._workbench_prompt_trace_repository = SQLiteWorkbenchPromptTraceRepository(owner=self)
        self._sqlite_pragma_fallbacks_logged: set[str] = set()

    def __getattr__(self, name: str) -> Any:
        for target in (
            self._storage_blueprint_repository,
            self._workbench_event_repository,
            self._workbench_event_outcome_repository,
            self._workbench_prompt_trace_repository,
        ):
            try:
                return getattr(target, name)
            except AttributeError:
                continue
        raise AttributeError(name)

    @property
    def workspace_root(self) -> Path:
        return self._database_path.parent.parent

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_blueprint_repository.initialize()
        with self._connect() as connection:
            self._workbench_event_repository.initialize(connection)
            self._workbench_event_outcome_repository.initialize(connection)
            self._workbench_prompt_trace_repository.initialize(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestions (
                    ingestion_id TEXT PRIMARY KEY,
                    ingestion_kind TEXT NOT NULL,
                    source_snapshot_id TEXT NOT NULL,
                    instrument_symbol TEXT NOT NULL,
                    observed_payload_json TEXT NOT NULL,
                    stored_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    ingestion_id TEXT NOT NULL,
                    route_key TEXT NOT NULL,
                    analysis_payload_json TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    FOREIGN KEY (ingestion_id) REFERENCES ingestions(ingestion_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS belief_state_snapshots (
                    belief_state_id TEXT PRIMARY KEY,
                    instrument_symbol TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    recognition_mode TEXT NOT NULL,
                    belief_payload_json TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_episodes (
                    episode_id TEXT PRIMARY KEY,
                    instrument_symbol TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    episode_payload_json TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL UNIQUE,
                    instrument_symbol TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    evaluation_payload_json TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS instrument_profiles (
                    instrument_symbol TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    ontology_version TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    profile_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (instrument_symbol, profile_version)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recognizer_builds (
                    engine_version TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    ontology_version TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    build_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_dead_letters (
                    dead_letter_id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    ingestion_kind TEXT NOT NULL,
                    instrument_symbol TEXT,
                    source_snapshot_id TEXT,
                    request_id TEXT,
                    dedup_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    error_detail_json TEXT NOT NULL,
                    ingestion_id TEXT,
                    stored_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_idempotency_keys (
                    endpoint TEXT NOT NULL,
                    dedup_key TEXT NOT NULL,
                    request_id TEXT,
                    payload_hash TEXT NOT NULL,
                    ingestion_id TEXT NOT NULL,
                    response_payload_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (endpoint, dedup_key)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_run_logs (
                    run_id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    ingestion_kind TEXT NOT NULL,
                    instrument_symbol TEXT,
                    request_id TEXT,
                    dedup_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    ingestion_id TEXT,
                    dead_letter_id TEXT,
                    detail_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS liquidity_memories (
                    memory_id TEXT PRIMARY KEY,
                    track_key TEXT NOT NULL UNIQUE,
                    instrument_symbol TEXT NOT NULL,
                    coverage_state TEXT NOT NULL,
                    observed_track_json TEXT NOT NULL,
                    derived_summary_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    contract_id TEXT,
                    timeframe TEXT NOT NULL,
                    window_range_json TEXT NOT NULL,
                    active_model TEXT,
                    status TEXT NOT NULL,
                    draft_text TEXT NOT NULL,
                    draft_attachments_json TEXT NOT NULL,
                    selected_prompt_block_ids_json TEXT NOT NULL,
                    pinned_context_block_ids_json TEXT NOT NULL,
                    include_memory_summary INTEGER NOT NULL DEFAULT 0,
                    include_recent_messages INTEGER NOT NULL DEFAULT 0,
                    mounted_reply_ids_json TEXT NOT NULL,
                    active_plan_id TEXT,
                    memory_summary_id TEXT,
                    unread_count INTEGER NOT NULL,
                    scroll_offset INTEGER NOT NULL,
                    pinned INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_message_id TEXT,
                    prompt_trace_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reply_title TEXT,
                    stream_buffer TEXT NOT NULL,
                    model TEXT,
                    annotations_json TEXT NOT NULL,
                    plan_cards_json TEXT NOT NULL,
                    mounted_to_chart INTEGER NOT NULL,
                    mounted_object_ids_json TEXT NOT NULL,
                    is_key_conclusion INTEGER NOT NULL,
                    request_payload_json TEXT NOT NULL,
                    response_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
                    FOREIGN KEY (prompt_trace_id) REFERENCES chat_prompt_traces(prompt_trace_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_prompt_blocks (
                    block_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    contract_id TEXT,
                    timeframe TEXT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview_text TEXT NOT NULL,
                    full_payload_json TEXT NOT NULL,
                    selected_by_default INTEGER NOT NULL,
                    pinned INTEGER NOT NULL,
                    ephemeral INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_memories (
                    memory_summary_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    summary_version INTEGER NOT NULL,
                    active_model TEXT,
                    symbol TEXT NOT NULL,
                    contract_id TEXT,
                    timeframe TEXT NOT NULL,
                    window_range_json TEXT NOT NULL,
                    user_goal_summary TEXT NOT NULL,
                    market_context_summary TEXT NOT NULL,
                    key_zones_summary_json TEXT NOT NULL,
                    active_plans_summary_json TEXT NOT NULL,
                    invalidated_plans_summary_json TEXT NOT NULL,
                    important_messages_json TEXT NOT NULL,
                    current_user_intent TEXT NOT NULL,
                    latest_question TEXT NOT NULL,
                    latest_answer_summary TEXT NOT NULL,
                    selected_annotations_json TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_annotations (
                    annotation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    plan_id TEXT,
                    symbol TEXT NOT NULL,
                    contract_id TEXT,
                    timeframe TEXT,
                    annotation_type TEXT NOT NULL,
                    subtype TEXT,
                    label TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    expires_at TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER,
                    confidence REAL,
                    visible INTEGER NOT NULL,
                    pinned INTEGER NOT NULL,
                    source_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
                    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_plan_cards (
                    plan_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_type TEXT,
                    entry_price REAL,
                    entry_price_low REAL,
                    entry_price_high REAL,
                    stop_price REAL,
                    take_profits_json TEXT NOT NULL,
                    invalidations_json TEXT NOT NULL,
                    time_validity TEXT,
                    risk_reward REAL,
                    confidence REAL,
                    priority INTEGER,
                    status TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
                    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
                )
                """,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chart_candles (
                    symbol          TEXT    NOT NULL,
                    timeframe       TEXT    NOT NULL,
                    started_at      TEXT    NOT NULL,
                    ended_at        TEXT    NOT NULL,
                    source_started_at TEXT  NOT NULL,
                    open            REAL    NOT NULL,
                    high            REAL    NOT NULL,
                    low             REAL    NOT NULL,
                    close           REAL    NOT NULL,
                    volume          INTEGER NOT NULL DEFAULT 0,
                    tick_volume     INTEGER NOT NULL DEFAULT 0,
                    delta           INTEGER NOT NULL DEFAULT 0,
                    updated_at      TEXT    NOT NULL,
                    PRIMARY KEY (symbol, timeframe, started_at)
                )
                """,
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_chart_candles_symbol_tf_started "
                "ON chart_candles (symbol, timeframe, started_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS atas_chart_bars_raw (
                    chart_instance_id TEXT NOT NULL DEFAULT '',
                    root_symbol TEXT,
                    contract_symbol TEXT NOT NULL DEFAULT '',
                    symbol TEXT NOT NULL,
                    venue TEXT,
                    timeframe TEXT NOT NULL,
                    bar_timestamp_utc TEXT,
                    started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT NOT NULL,
                    source_started_at TEXT NOT NULL,
                    original_bar_time_text TEXT,
                    timestamp_basis TEXT,
                    chart_display_timezone_mode TEXT,
                    chart_display_timezone_name TEXT,
                    chart_display_utc_offset_minutes INTEGER,
                    instrument_timezone_value TEXT,
                    instrument_timezone_source TEXT,
                    collector_local_timezone_name TEXT,
                    collector_local_utc_offset_minutes INTEGER,
                    timezone_capture_confidence TEXT,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER,
                    bid_volume INTEGER,
                    ask_volume INTEGER,
                    delta INTEGER,
                    trade_count INTEGER,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (chart_instance_id, contract_symbol, timeframe, started_at_utc)
                )
                """,
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_atas_chart_bars_raw_contract_tf_started "
                "ON atas_chart_bars_raw (contract_symbol, timeframe, started_at_utc DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_atas_chart_bars_raw_root_tf_started "
                "ON atas_chart_bars_raw (root_symbol, timeframe, started_at_utc DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS atas_backfill_requests (
                    request_id TEXT PRIMARY KEY,
                    cache_key TEXT NOT NULL,
                    instrument_symbol TEXT NOT NULL,
                    contract_symbol TEXT,
                    root_symbol TEXT,
                    target_contract_symbol TEXT,
                    target_root_symbol TEXT,
                    display_timeframe TEXT NOT NULL,
                    chart_instance_id TEXT,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    expires_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_atas_backfill_requests_status_requested "
                "ON atas_backfill_requests (status, requested_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_atas_backfill_requests_symbol_tf_requested "
                "ON atas_backfill_requests (instrument_symbol, display_timeframe, requested_at DESC)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_belief_state_symbol_time ON belief_state_snapshots (instrument_symbol, observed_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_event_episodes_symbol_end ON event_episodes (instrument_symbol, ended_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_episode_evaluations_symbol_time ON episode_evaluations (instrument_symbol, evaluated_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_instrument_profiles_symbol_active ON instrument_profiles (instrument_symbol, is_active, created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_recognizer_builds_active_created ON recognizer_builds (is_active, created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dead_letters_endpoint_time ON ingestion_dead_letters (endpoint, stored_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dead_letters_symbol_time ON ingestion_dead_letters (instrument_symbol, stored_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_dead_letters_hash ON ingestion_dead_letters (payload_hash, stored_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_request_id ON ingestion_idempotency_keys (request_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_ingestion_id ON ingestion_idempotency_keys (ingestion_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_endpoint_time ON ingestion_run_logs (endpoint, completed_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_outcome_time ON ingestion_run_logs (outcome, completed_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_symbol_time ON ingestion_run_logs (instrument_symbol, completed_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestions_symbol_time ON ingestions (instrument_symbol, stored_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestions_kind_snapshot ON ingestions (ingestion_kind, source_snapshot_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_analyses_ingestion ON analyses (ingestion_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_liquidity_memories_symbol_expiry ON liquidity_memories (instrument_symbol, expires_at, updated_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace_symbol ON chat_sessions (workspace_id, symbol, updated_at)")
            try:
                connection.execute("ALTER TABLE chat_sessions ADD COLUMN include_memory_summary INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE chat_sessions ADD COLUMN include_recent_messages INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE chat_messages ADD COLUMN prompt_trace_id TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE chart_candles ADD COLUMN source_started_at TEXT NOT NULL DEFAULT ''")
                connection.execute("UPDATE chart_candles SET source_started_at = started_at WHERE source_started_at = ''")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE chart_candles ADD COLUMN source_timezone TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                connection.execute("ALTER TABLE atas_chart_bars_raw ADD COLUMN bar_timestamp_utc TEXT")
                connection.execute(
                    "UPDATE atas_chart_bars_raw SET bar_timestamp_utc = started_at_utc "
                    "WHERE bar_timestamp_utc IS NULL OR bar_timestamp_utc = ''"
                )
            except sqlite3.OperationalError:
                pass
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_time ON chat_messages (session_id, created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_prompt_trace ON chat_messages (prompt_trace_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_prompt_blocks_session_kind ON chat_prompt_blocks (session_id, kind, created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_annotations_session_message ON chat_annotations (session_id, message_id, created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_plan_cards_session_message ON chat_plan_cards (session_id, message_id, created_at)")
            connection.commit()

    def save_ingestion(self, *, ingestion_id: str, ingestion_kind: str, source_snapshot_id: str, instrument_symbol: str, observed_payload: dict[str, Any], stored_at: datetime) -> StoredIngestion:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestions (
                    ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload_json, stored_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, self._serialize_json(observed_payload), self._serialize_datetime(stored_at)),
            )
            connection.commit()
        self._storage_blueprint_repository.mirror_legacy_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=observed_payload,
            stored_at=stored_at,
        )
        return StoredIngestion(ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload, stored_at)

    def save_analysis(self, *, analysis_id: str, ingestion_id: str, route_key: str, analysis_payload: dict[str, Any], stored_at: datetime) -> StoredAnalysis:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses (analysis_id, ingestion_id, route_key, analysis_payload_json, stored_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (analysis_id, ingestion_id, route_key, self._serialize_json(analysis_payload), self._serialize_datetime(stored_at)),
            )
            connection.commit()
        return StoredAnalysis(analysis_id, ingestion_id, route_key, analysis_payload, stored_at)

    def save_belief_state(
        self,
        *,
        belief_state_id: str,
        instrument_symbol: str,
        observed_at: datetime,
        stored_at: datetime,
        schema_version: str,
        profile_version: str,
        engine_version: str,
        recognition_mode: str,
        belief_payload: dict[str, Any],
    ) -> StoredBeliefState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO belief_state_snapshots (
                    belief_state_id,
                    instrument_symbol,
                    observed_at,
                    stored_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    belief_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    belief_state_id,
                    instrument_symbol,
                    self._serialize_datetime(observed_at),
                    self._serialize_datetime(stored_at),
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    self._serialize_json(belief_payload),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_belief_state_snapshot(
            StoredBeliefStateSnapshot(
                belief_state_id=belief_state_id,
                instrument_symbol=instrument_symbol,
                market_time=observed_at,
                session_date=observed_at.date().isoformat(),
                ingested_at=stored_at,
                schema_version=schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                recognition_mode=recognition_mode,
                data_status=belief_payload.get("data_status", {}) if isinstance(belief_payload.get("data_status"), dict) else {},
                belief_payload=belief_payload,
            ),
        )
        beliefs = self.list_belief_states(instrument_symbol=instrument_symbol, limit=500)
        for belief in beliefs:
            if belief.belief_state_id == belief_state_id:
                return belief
        return StoredBeliefState(
            belief_state_id=belief_state_id,
            instrument_symbol=instrument_symbol,
            observed_at=observed_at,
            stored_at=stored_at,
            schema_version=schema_version,
            profile_version=profile_version,
            engine_version=engine_version,
            recognition_mode=recognition_mode,
            belief_payload=belief_payload,
        )

    def get_latest_belief_state(self, instrument_symbol: str) -> StoredBeliefState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    belief_state_id,
                    instrument_symbol,
                    observed_at,
                    stored_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    belief_payload_json
                FROM belief_state_snapshots
                WHERE instrument_symbol = ?
                ORDER BY observed_at DESC, stored_at DESC
                LIMIT 1
                """,
                (instrument_symbol,),
            ).fetchone()
        if row is None:
            return None
        return StoredBeliefState(
            belief_state_id=row["belief_state_id"],
            instrument_symbol=row["instrument_symbol"],
            observed_at=self._parse_datetime(row["observed_at"]),
            stored_at=self._parse_datetime(row["stored_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            recognition_mode=row["recognition_mode"],
            belief_payload=self._parse_json(row["belief_payload_json"]),
        )

    def list_belief_states(
        self,
        *,
        instrument_symbol: str,
        observed_at_after: datetime | None = None,
        observed_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredBeliefState]:
        if observed_at_after is not None or observed_at_before is not None or session_date is not None:
            rows = self._storage_blueprint_repository.list_belief_state_snapshots(
                instrument_symbol=instrument_symbol,
                market_time_after=observed_at_after,
                market_time_before=observed_at_before,
                session_date=session_date,
                limit=limit,
            )
            return [
                StoredBeliefState(
                    belief_state_id=row.belief_state_id,
                    instrument_symbol=row.instrument_symbol,
                    observed_at=row.market_time,
                    stored_at=row.ingested_at,
                    schema_version=row.schema_version,
                    profile_version=row.profile_version,
                    engine_version=row.engine_version,
                    recognition_mode=row.recognition_mode,
                    belief_payload=row.belief_payload,
                )
                for row in rows
            ]
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    belief_state_id,
                    instrument_symbol,
                    observed_at,
                    stored_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    belief_payload_json
                FROM belief_state_snapshots
                WHERE instrument_symbol = ?
                ORDER BY observed_at DESC, stored_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [
            StoredBeliefState(
                belief_state_id=row["belief_state_id"],
                instrument_symbol=row["instrument_symbol"],
                observed_at=self._parse_datetime(row["observed_at"]),
                stored_at=self._parse_datetime(row["stored_at"]),
                schema_version=row["schema_version"],
                profile_version=row["profile_version"],
                engine_version=row["engine_version"],
                recognition_mode=row["recognition_mode"],
                belief_payload=self._parse_json(row["belief_payload_json"]),
            )
            for row in rows
        ]

    def save_event_episode(
        self,
        *,
        episode_id: str,
        instrument_symbol: str,
        event_kind: str,
        started_at: datetime,
        ended_at: datetime,
        resolution: str,
        schema_version: str,
        profile_version: str,
        engine_version: str,
        episode_payload: dict[str, Any],
    ) -> StoredEventEpisode:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO event_episodes (
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    started_at,
                    ended_at,
                    resolution,
                    schema_version,
                    profile_version,
                    engine_version,
                    episode_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    self._serialize_datetime(started_at),
                    self._serialize_datetime(ended_at),
                    resolution,
                    schema_version,
                    profile_version,
                    engine_version,
                    self._serialize_json(episode_payload),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_event_episode_record(
            StoredEventEpisodeRecord(
                episode_id=episode_id,
                instrument_symbol=instrument_symbol,
                market_time=ended_at,
                ingested_at=ended_at,
                schema_version=schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                event_kind=event_kind,
                started_at=started_at,
                ended_at=ended_at,
                resolution=resolution,
                episode_payload=episode_payload,
            ),
        )
        episode = self.get_event_episode(episode_id)
        if episode is not None:
            return episode
        return StoredEventEpisode(
            episode_id=episode_id,
            instrument_symbol=instrument_symbol,
            event_kind=event_kind,
            started_at=started_at,
            ended_at=ended_at,
            resolution=resolution,
            schema_version=schema_version,
            profile_version=profile_version,
            engine_version=engine_version,
            episode_payload=episode_payload,
        )

    def get_event_episode(self, episode_id: str) -> StoredEventEpisode | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    started_at,
                    ended_at,
                    resolution,
                    schema_version,
                    profile_version,
                    engine_version,
                    episode_payload_json
                FROM event_episodes
                WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredEventEpisode(
            episode_id=row["episode_id"],
            instrument_symbol=row["instrument_symbol"],
            event_kind=row["event_kind"],
            started_at=self._parse_datetime(row["started_at"]),
            ended_at=self._parse_datetime(row["ended_at"]),
            resolution=row["resolution"],
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            episode_payload=self._parse_json(row["episode_payload_json"]),
        )

    def list_event_episodes(
        self,
        *,
        instrument_symbol: str,
        ended_at_after: datetime | None = None,
        ended_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredEventEpisode]:
        if ended_at_after is not None or ended_at_before is not None or session_date is not None:
            rows = self._storage_blueprint_repository.list_event_episode_records_filtered(
                instrument_symbol=instrument_symbol,
                market_time_after=ended_at_after,
                market_time_before=ended_at_before,
                session_date=session_date,
                limit=limit,
            )
            return [
                StoredEventEpisode(
                    episode_id=row.episode_id,
                    instrument_symbol=row.instrument_symbol,
                    event_kind=row.event_kind,
                    started_at=row.started_at,
                    ended_at=row.ended_at,
                    resolution=row.resolution,
                    schema_version=row.schema_version,
                    profile_version=row.profile_version,
                    engine_version=row.engine_version,
                    episode_payload=row.episode_payload,
                )
                for row in rows
            ]
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    started_at,
                    ended_at,
                    resolution,
                    schema_version,
                    profile_version,
                    engine_version,
                    episode_payload_json
                FROM event_episodes
                WHERE instrument_symbol = ?
                ORDER BY ended_at DESC, started_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [
            StoredEventEpisode(
                episode_id=row["episode_id"],
                instrument_symbol=row["instrument_symbol"],
                event_kind=row["event_kind"],
                started_at=self._parse_datetime(row["started_at"]),
                ended_at=self._parse_datetime(row["ended_at"]),
                resolution=row["resolution"],
                schema_version=row["schema_version"],
                profile_version=row["profile_version"],
                engine_version=row["engine_version"],
                episode_payload=self._parse_json(row["episode_payload_json"]),
            )
            for row in rows
        ]

    def save_episode_evaluation(
        self,
        *,
        evaluation_id: str,
        episode_id: str,
        instrument_symbol: str,
        event_kind: str,
        evaluated_at: datetime,
        schema_version: str,
        profile_version: str,
        engine_version: str,
        evaluation_payload: dict[str, Any],
    ) -> StoredEpisodeEvaluation:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO episode_evaluations (
                    evaluation_id,
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    evaluated_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    evaluation_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    self._serialize_datetime(evaluated_at),
                    schema_version,
                    profile_version,
                    engine_version,
                    self._serialize_json(evaluation_payload),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_episode_evaluation_record(
            StoredEpisodeEvaluationRecord(
                evaluation_id=evaluation_id,
                episode_id=episode_id,
                instrument_symbol=instrument_symbol,
                market_time=evaluated_at,
                ingested_at=evaluated_at,
                schema_version=schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                event_kind=event_kind,
                evaluated_at=evaluated_at,
                evaluation_payload=evaluation_payload,
            ),
        )
        evaluation = self.get_episode_evaluation(episode_id)
        if evaluation is not None:
            return evaluation
        return StoredEpisodeEvaluation(
            evaluation_id=evaluation_id,
            episode_id=episode_id,
            instrument_symbol=instrument_symbol,
            event_kind=event_kind,
            evaluated_at=evaluated_at,
            schema_version=schema_version,
            profile_version=profile_version,
            engine_version=engine_version,
            evaluation_payload=evaluation_payload,
        )

    def get_episode_evaluation(self, episode_id: str) -> StoredEpisodeEvaluation | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    evaluation_id,
                    episode_id,
                    instrument_symbol,
                    event_kind,
                    evaluated_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    evaluation_payload_json
                FROM episode_evaluations
                WHERE episode_id = ?
                ORDER BY evaluated_at DESC
                LIMIT 1
                """,
                (episode_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredEpisodeEvaluation(
            evaluation_id=row["evaluation_id"],
            episode_id=row["episode_id"],
            instrument_symbol=row["instrument_symbol"],
            event_kind=row["event_kind"],
            evaluated_at=self._parse_datetime(row["evaluated_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            evaluation_payload=self._parse_json(row["evaluation_payload_json"]),
        )

    def list_episode_evaluations(
        self,
        *,
        instrument_symbol: str,
        evaluated_at_after: datetime | None = None,
        evaluated_at_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredEpisodeEvaluation]:
        rows = self._storage_blueprint_repository.list_episode_evaluation_records(
            instrument_symbol=instrument_symbol,
            market_time_after=evaluated_at_after,
            market_time_before=evaluated_at_before,
            session_date=session_date,
            limit=limit,
        )
        return [
            StoredEpisodeEvaluation(
                evaluation_id=row.evaluation_id,
                episode_id=row.episode_id,
                instrument_symbol=row.instrument_symbol,
                event_kind=row.event_kind,
                evaluated_at=row.evaluated_at,
                schema_version=row.schema_version,
                profile_version=row.profile_version,
                engine_version=row.engine_version,
                evaluation_payload=row.evaluation_payload,
            )
            for row in rows
        ]

    def save_instrument_profile(
        self,
        *,
        instrument_symbol: str,
        profile_version: str,
        schema_version: str,
        ontology_version: str,
        is_active: bool,
        profile_payload: dict[str, Any],
        created_at: datetime,
    ) -> StoredInstrumentProfile:
        with self._connect() as connection:
            if is_active:
                connection.execute(
                    "UPDATE instrument_profiles SET is_active = 0 WHERE instrument_symbol = ? AND profile_version != ?",
                    (instrument_symbol, profile_version),
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO instrument_profiles (
                    instrument_symbol,
                    profile_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    profile_payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instrument_symbol,
                    profile_version,
                    schema_version,
                    ontology_version,
                    int(is_active),
                    self._serialize_json(profile_payload),
                    self._serialize_datetime(created_at),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_instrument_profile_version(
            StoredInstrumentProfileVersion(
                instrument_symbol=instrument_symbol,
                profile_version=profile_version,
                schema_version=schema_version,
                ontology_version=ontology_version,
                is_active=is_active,
                profile_payload=profile_payload,
                created_at=created_at,
                updated_at=created_at,
            ),
        )
        profile = self.get_active_instrument_profile(instrument_symbol)
        if profile is not None and profile.profile_version == profile_version:
            return profile
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    instrument_symbol,
                    profile_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    profile_payload_json,
                    created_at
                FROM instrument_profiles
                WHERE instrument_symbol = ? AND profile_version = ?
                """,
                (instrument_symbol, profile_version),
            ).fetchone()
        if row is None:
            return StoredInstrumentProfile(
                instrument_symbol=instrument_symbol,
                profile_version=profile_version,
                schema_version=schema_version,
                ontology_version=ontology_version,
                is_active=is_active,
                profile_payload=profile_payload,
                created_at=created_at,
            )
        return StoredInstrumentProfile(
            instrument_symbol=row["instrument_symbol"],
            profile_version=row["profile_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            profile_payload=self._parse_json(row["profile_payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    def get_active_instrument_profile(self, instrument_symbol: str) -> StoredInstrumentProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    instrument_symbol,
                    profile_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    profile_payload_json,
                    created_at
                FROM instrument_profiles
                WHERE instrument_symbol = ?
                ORDER BY is_active DESC, created_at DESC
                LIMIT 1
                """,
                (instrument_symbol,),
            ).fetchone()
        if row is None:
            return None
        return StoredInstrumentProfile(
            instrument_symbol=row["instrument_symbol"],
            profile_version=row["profile_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            profile_payload=self._parse_json(row["profile_payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    def save_recognizer_build(
        self,
        *,
        engine_version: str,
        schema_version: str,
        ontology_version: str,
        is_active: bool,
        status: str,
        build_payload: dict[str, Any],
        created_at: datetime,
    ) -> StoredRecognizerBuild:
        with self._connect() as connection:
            if is_active:
                connection.execute(
                    "UPDATE recognizer_builds SET is_active = 0 WHERE engine_version != ?",
                    (engine_version,),
                )
            connection.execute(
                """
                INSERT OR IGNORE INTO recognizer_builds (
                    engine_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    status,
                    build_payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    engine_version,
                    schema_version,
                    ontology_version,
                    int(is_active),
                    status,
                    self._serialize_json(build_payload),
                    self._serialize_datetime(created_at),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_recognizer_build_version(
            StoredRecognizerBuildVersion(
                engine_version=engine_version,
                schema_version=schema_version,
                ontology_version=ontology_version,
                is_active=is_active,
                status=status,
                build_payload=build_payload,
                created_at=created_at,
                updated_at=created_at,
            ),
        )
        build = self.get_active_recognizer_build()
        if build is not None and build.engine_version == engine_version:
            return build
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    engine_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    status,
                    build_payload_json,
                    created_at
                FROM recognizer_builds
                WHERE engine_version = ?
                """,
                (engine_version,),
            ).fetchone()
        if row is None:
            return StoredRecognizerBuild(
                engine_version=engine_version,
                schema_version=schema_version,
                ontology_version=ontology_version,
                is_active=is_active,
                status=status,
                build_payload=build_payload,
                created_at=created_at,
            )
        return StoredRecognizerBuild(
            engine_version=row["engine_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            status=row["status"],
            build_payload=self._parse_json(row["build_payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    def get_active_recognizer_build(self) -> StoredRecognizerBuild | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    engine_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    status,
                    build_payload_json,
                    created_at
                FROM recognizer_builds
                ORDER BY is_active DESC, created_at DESC
                LIMIT 1
                """,
            ).fetchone()
        if row is None:
            return None
        return StoredRecognizerBuild(
            engine_version=row["engine_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            status=row["status"],
            build_payload=self._parse_json(row["build_payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
        )

    def save_tuning_recommendation(
        self,
        *,
        recommendation_id: str,
        instrument_symbol: str,
        market_time: datetime,
        ingested_at: datetime,
        schema_version: str,
        profile_version: str,
        engine_version: str,
        episode_id: str | None,
        evaluation_id: str | None,
        source_kind: str,
        recommendation_payload: dict[str, Any],
    ) -> StoredTuningRecommendationRecord:
        record = self._storage_blueprint_repository.save_tuning_recommendation(
            StoredTuningRecommendation(
                recommendation_id=recommendation_id,
                instrument_symbol=instrument_symbol,
                market_time=market_time,
                ingested_at=ingested_at,
                schema_version=schema_version,
                profile_version=profile_version,
                engine_version=engine_version,
                episode_id=episode_id,
                evaluation_id=evaluation_id,
                source_kind=source_kind,
                recommendation_payload=recommendation_payload,
            ),
        )
        return StoredTuningRecommendationRecord(
            recommendation_id=record.recommendation_id,
            instrument_symbol=record.instrument_symbol,
            market_time=record.market_time,
            ingested_at=record.ingested_at,
            schema_version=record.schema_version,
            profile_version=record.profile_version,
            engine_version=record.engine_version,
            episode_id=record.episode_id,
            evaluation_id=record.evaluation_id,
            source_kind=record.source_kind,
            recommendation_payload=record.recommendation_payload,
        )

    def list_tuning_recommendations(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredTuningRecommendationRecord]:
        rows = self._storage_blueprint_repository.list_tuning_recommendations(
            instrument_symbol=instrument_symbol,
            market_time_after=market_time_after,
            market_time_before=market_time_before,
            session_date=session_date,
            limit=limit,
        )
        return [
            StoredTuningRecommendationRecord(
                recommendation_id=row.recommendation_id,
                instrument_symbol=row.instrument_symbol,
                market_time=row.market_time,
                ingested_at=row.ingested_at,
                schema_version=row.schema_version,
                profile_version=row.profile_version,
                engine_version=row.engine_version,
                episode_id=row.episode_id,
                evaluation_id=row.evaluation_id,
                source_kind=row.source_kind,
                recommendation_payload=row.recommendation_payload,
            )
            for row in rows
        ]

    def save_profile_patch_candidate(
        self,
        *,
        candidate_id: str,
        instrument_symbol: str,
        market_time: datetime,
        ingested_at: datetime,
        schema_version: str,
        base_profile_version: str,
        proposed_profile_version: str,
        recommendation_id: str | None,
        status: str,
        patch_payload: dict[str, Any],
    ) -> StoredProfilePatchCandidateRecord:
        record = self._storage_blueprint_repository.save_profile_patch_candidate(
            StoredProfilePatchCandidate(
                candidate_id=candidate_id,
                instrument_symbol=instrument_symbol,
                market_time=market_time,
                ingested_at=ingested_at,
                schema_version=schema_version,
                base_profile_version=base_profile_version,
                proposed_profile_version=proposed_profile_version,
                recommendation_id=recommendation_id,
                status=status,
                patch_payload=patch_payload,
            ),
        )
        return StoredProfilePatchCandidateRecord(
            candidate_id=record.candidate_id,
            instrument_symbol=record.instrument_symbol,
            market_time=record.market_time,
            ingested_at=record.ingested_at,
            schema_version=record.schema_version,
            base_profile_version=record.base_profile_version,
            proposed_profile_version=record.proposed_profile_version,
            recommendation_id=record.recommendation_id,
            status=record.status,
            patch_payload=record.patch_payload,
        )

    def list_profile_patch_candidates(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredProfilePatchCandidateRecord]:
        rows = self._storage_blueprint_repository.list_profile_patch_candidates(
            instrument_symbol=instrument_symbol,
            market_time_after=market_time_after,
            market_time_before=market_time_before,
            session_date=session_date,
            limit=limit,
        )
        return [
            StoredProfilePatchCandidateRecord(
                candidate_id=row.candidate_id,
                instrument_symbol=row.instrument_symbol,
                market_time=row.market_time,
                ingested_at=row.ingested_at,
                schema_version=row.schema_version,
                base_profile_version=row.base_profile_version,
                proposed_profile_version=row.proposed_profile_version,
                recommendation_id=row.recommendation_id,
                status=row.status,
                patch_payload=row.patch_payload,
            )
            for row in rows
        ]

    def save_patch_validation_result(
        self,
        *,
        validation_result_id: str,
        instrument_symbol: str,
        market_time: datetime,
        ingested_at: datetime,
        schema_version: str,
        candidate_id: str,
        validation_status: str,
        validation_payload: dict[str, Any],
    ) -> StoredPatchValidationResultRecord:
        record = self._storage_blueprint_repository.save_patch_validation_result(
            StoredPatchValidationResult(
                validation_result_id=validation_result_id,
                instrument_symbol=instrument_symbol,
                market_time=market_time,
                ingested_at=ingested_at,
                schema_version=schema_version,
                candidate_id=candidate_id,
                validation_status=validation_status,
                validation_payload=validation_payload,
            ),
        )
        return StoredPatchValidationResultRecord(
            validation_result_id=record.validation_result_id,
            instrument_symbol=record.instrument_symbol,
            market_time=record.market_time,
            ingested_at=record.ingested_at,
            schema_version=record.schema_version,
            candidate_id=record.candidate_id,
            validation_status=record.validation_status,
            validation_payload=record.validation_payload,
        )

    def list_patch_validation_results(
        self,
        *,
        candidate_id: str,
        limit: int = 100,
    ) -> list[StoredPatchValidationResultRecord]:
        rows = self._storage_blueprint_repository.list_patch_validation_results(
            candidate_id=candidate_id,
            limit=limit,
        )
        return [
            StoredPatchValidationResultRecord(
                validation_result_id=row.validation_result_id,
                instrument_symbol=row.instrument_symbol,
                market_time=row.market_time,
                ingested_at=row.ingested_at,
                schema_version=row.schema_version,
                candidate_id=row.candidate_id,
                validation_status=row.validation_status,
                validation_payload=row.validation_payload,
            )
            for row in rows
        ]

    def save_patch_promotion_history(
        self,
        *,
        promotion_id: str,
        candidate_id: str,
        instrument_symbol: str,
        promoted_profile_version: str,
        previous_profile_version: str,
        promoted_at: datetime,
        promoted_by: str,
        promotion_notes: str,
        detail: dict[str, Any],
    ) -> StoredPatchPromotionHistoryRecord:
        from atas_market_structure.storage_models import StoredPatchPromotionHistory

        record = self._storage_blueprint_repository.save_patch_promotion_history(
            StoredPatchPromotionHistory(
                promotion_id=promotion_id,
                candidate_id=candidate_id,
                instrument_symbol=instrument_symbol,
                promoted_profile_version=promoted_profile_version,
                previous_profile_version=previous_profile_version,
                promoted_at=promoted_at,
                promoted_by=promoted_by,
                promotion_notes=promotion_notes,
                detail=detail,
            ),
        )
        return StoredPatchPromotionHistoryRecord(
            promotion_id=record.promotion_id,
            candidate_id=record.candidate_id,
            instrument_symbol=record.instrument_symbol,
            promoted_profile_version=record.promoted_profile_version,
            previous_profile_version=record.previous_profile_version,
            promoted_at=record.promoted_at,
            promoted_by=record.promoted_by,
            promotion_notes=record.promotion_notes,
            detail=record.detail,
        )

    def get_patch_promotion(self, promotion_id: str) -> StoredPatchPromotionHistoryRecord | None:
        row = self._storage_blueprint_repository.get_patch_promotion(promotion_id)
        if row is None:
            return None
        return StoredPatchPromotionHistoryRecord(
            promotion_id=row.promotion_id,
            candidate_id=row.candidate_id,
            instrument_symbol=row.instrument_symbol,
            promoted_profile_version=row.promoted_profile_version,
            previous_profile_version=row.previous_profile_version,
            promoted_at=row.promoted_at,
            promoted_by=row.promoted_by,
            promotion_notes=row.promotion_notes,
            detail=row.detail,
        )

    def list_patch_promotions(
        self,
        *,
        candidate_id: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 200,
    ) -> list[StoredPatchPromotionHistoryRecord]:
        rows = self._storage_blueprint_repository.list_patch_promotions(
            candidate_id=candidate_id,
            instrument_symbol=instrument_symbol,
            limit=limit,
        )
        return [
            StoredPatchPromotionHistoryRecord(
                promotion_id=row.promotion_id,
                candidate_id=row.candidate_id,
                instrument_symbol=row.instrument_symbol,
                promoted_profile_version=row.promoted_profile_version,
                previous_profile_version=row.previous_profile_version,
                promoted_at=row.promoted_at,
                promoted_by=row.promoted_by,
                promotion_notes=row.promotion_notes,
                detail=row.detail,
            )
            for row in rows
        ]

    def get_instrument_profile_version(
        self,
        instrument_symbol: str,
        profile_version: str,
    ) -> StoredInstrumentProfile | None:
        rows = self._storage_blueprint_repository.list_instrument_profile_versions(
            instrument_symbol=instrument_symbol,
            limit=100,
        )
        for row in rows:
            if row.profile_version == profile_version:
                return StoredInstrumentProfile(
                    instrument_symbol=row.instrument_symbol,
                    profile_version=row.profile_version,
                    schema_version=row.schema_version,
                    ontology_version=row.ontology_version,
                    is_active=row.is_active,
                    profile_payload=row.profile_payload,
                    created_at=row.created_at,
                )
        return None

    def list_instrument_profile_versions(
        self,
        instrument_symbol: str,
        limit: int = 100,
    ) -> list[StoredInstrumentProfile]:
        rows = self._storage_blueprint_repository.list_instrument_profile_versions(
            instrument_symbol=instrument_symbol,
            limit=limit,
        )
        return [
            StoredInstrumentProfile(
                instrument_symbol=row.instrument_symbol,
                profile_version=row.profile_version,
                schema_version=row.schema_version,
                ontology_version=row.ontology_version,
                is_active=row.is_active,
                profile_payload=row.profile_payload,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def save_dead_letter(
        self,
        *,
        dead_letter_id: str,
        endpoint: str,
        ingestion_kind: str,
        instrument_symbol: str | None,
        source_snapshot_id: str | None,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        raw_payload: str,
        error_code: str,
        error_detail: dict[str, Any],
        ingestion_id: str | None,
        stored_at: datetime,
    ) -> StoredIngestionDeadLetter:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_dead_letters (
                    dead_letter_id,
                    endpoint,
                    ingestion_kind,
                    instrument_symbol,
                    source_snapshot_id,
                    request_id,
                    dedup_key,
                    payload_hash,
                    raw_payload,
                    error_code,
                    error_detail_json,
                    ingestion_id,
                    stored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dead_letter_id,
                    endpoint,
                    ingestion_kind,
                    instrument_symbol,
                    source_snapshot_id,
                    request_id,
                    dedup_key,
                    payload_hash,
                    raw_payload,
                    error_code,
                    self._serialize_json(error_detail),
                    ingestion_id,
                    self._serialize_datetime(stored_at),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_dead_letter_payload(
            StoredDeadLetterPayload(
                dead_letter_id=dead_letter_id,
                endpoint=endpoint,
                ingestion_kind=ingestion_kind,
                instrument_symbol=instrument_symbol,
                market_time=stored_at,
                ingested_at=stored_at,
                schema_version="1.0.0",
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                source_ingestion_id=ingestion_id,
                error_code=error_code,
                error_detail=error_detail,
                raw_payload=raw_payload,
            ),
        )
        return StoredIngestionDeadLetter(
            dead_letter_id=dead_letter_id,
            endpoint=endpoint,
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            raw_payload=raw_payload,
            error_code=error_code,
            error_detail=error_detail,
            ingestion_id=ingestion_id,
            stored_at=stored_at,
        )

    def list_dead_letters(
        self,
        *,
        endpoint: str | None = None,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 100,
        stored_at_after: datetime | None = None,
    ) -> list[StoredIngestionDeadLetter]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if endpoint is not None:
            clauses.append("endpoint = ?")
            parameters.append(endpoint)
        if ingestion_kind is not None:
            clauses.append("ingestion_kind = ?")
            parameters.append(ingestion_kind)
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        if stored_at_after is not None:
            clauses.append("stored_at >= ?")
            parameters.append(self._serialize_datetime(stored_at_after))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT dead_letter_id, endpoint, ingestion_kind, instrument_symbol, "
            "source_snapshot_id, request_id, dedup_key, payload_hash, raw_payload, "
            "error_code, error_detail_json, ingestion_id, stored_at "
            f"FROM ingestion_dead_letters {where_clause} "
            "ORDER BY stored_at DESC LIMIT ?"
        )
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [self._row_to_dead_letter(row) for row in rows]

    def get_ingestion_idempotency_key(
        self,
        *,
        endpoint: str,
        dedup_key: str,
    ) -> StoredIngestionIdempotencyKey | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    endpoint,
                    dedup_key,
                    request_id,
                    payload_hash,
                    ingestion_id,
                    response_payload_json,
                    first_seen_at,
                    last_seen_at,
                    duplicate_count
                FROM ingestion_idempotency_keys
                WHERE endpoint = ? AND dedup_key = ?
                """,
                (endpoint, dedup_key),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_idempotency_key(row)

    def save_ingestion_idempotency_key(
        self,
        *,
        endpoint: str,
        dedup_key: str,
        request_id: str | None,
        payload_hash: str,
        ingestion_id: str,
        response_payload: dict[str, Any],
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> StoredIngestionIdempotencyKey:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO ingestion_idempotency_keys (
                    endpoint,
                    dedup_key,
                    request_id,
                    payload_hash,
                    ingestion_id,
                    response_payload_json,
                    first_seen_at,
                    last_seen_at,
                    duplicate_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    endpoint,
                    dedup_key,
                    request_id,
                    payload_hash,
                    ingestion_id,
                    self._serialize_json(response_payload),
                    self._serialize_datetime(first_seen_at),
                    self._serialize_datetime(last_seen_at),
                ),
            )
            connection.commit()
        stored = self.get_ingestion_idempotency_key(endpoint=endpoint, dedup_key=dedup_key)
        if stored is not None:
            return stored
        return StoredIngestionIdempotencyKey(
            endpoint=endpoint,
            dedup_key=dedup_key,
            request_id=request_id,
            payload_hash=payload_hash,
            ingestion_id=ingestion_id,
            response_payload=response_payload,
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            duplicate_count=0,
        )

    def touch_ingestion_idempotency_key(
        self,
        *,
        endpoint: str,
        dedup_key: str,
        seen_at: datetime,
    ) -> StoredIngestionIdempotencyKey | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_idempotency_keys
                SET duplicate_count = duplicate_count + 1,
                    last_seen_at = ?
                WHERE endpoint = ? AND dedup_key = ?
                """,
                (self._serialize_datetime(seen_at), endpoint, dedup_key),
            )
            connection.commit()
        return self.get_ingestion_idempotency_key(endpoint=endpoint, dedup_key=dedup_key)

    def save_ingestion_run_log(
        self,
        *,
        run_id: str,
        endpoint: str,
        ingestion_kind: str,
        instrument_symbol: str | None,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        outcome: str,
        http_status: int,
        ingestion_id: str | None,
        dead_letter_id: str | None,
        detail: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
    ) -> StoredIngestionRunLog:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_run_logs (
                    run_id,
                    endpoint,
                    ingestion_kind,
                    instrument_symbol,
                    request_id,
                    dedup_key,
                    payload_hash,
                    outcome,
                    http_status,
                    ingestion_id,
                    dead_letter_id,
                    detail_json,
                    started_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    endpoint,
                    ingestion_kind,
                    instrument_symbol,
                    request_id,
                    dedup_key,
                    payload_hash,
                    outcome,
                    http_status,
                    ingestion_id,
                    dead_letter_id,
                    self._serialize_json(detail),
                    self._serialize_datetime(started_at),
                    self._serialize_datetime(completed_at),
                ),
            )
            connection.commit()
        self._storage_blueprint_repository.save_ingestion_run_log_record(
            StoredIngestionRunLogRecord(
                run_id=run_id,
                endpoint=endpoint,
                ingestion_kind=ingestion_kind,
                instrument_symbol=instrument_symbol,
                market_time=completed_at,
                ingested_at=completed_at,
                schema_version="1.0.0",
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                ingestion_id=ingestion_id,
                dead_letter_id=dead_letter_id,
                outcome=outcome,
                http_status=http_status,
                detail=detail,
                started_at=started_at,
                completed_at=completed_at,
            ),
        )
        return StoredIngestionRunLog(
            run_id=run_id,
            endpoint=endpoint,
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            outcome=outcome,
            http_status=http_status,
            ingestion_id=ingestion_id,
            dead_letter_id=dead_letter_id,
            detail=detail,
            started_at=started_at,
            completed_at=completed_at,
        )

    def list_ingestion_run_logs(
        self,
        *,
        endpoint: str | None = None,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
        completed_at_after: datetime | None = None,
    ) -> list[StoredIngestionRunLog]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if endpoint is not None:
            clauses.append("endpoint = ?")
            parameters.append(endpoint)
        if ingestion_kind is not None:
            clauses.append("ingestion_kind = ?")
            parameters.append(ingestion_kind)
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        if outcome is not None:
            clauses.append("outcome = ?")
            parameters.append(outcome)
        if completed_at_after is not None:
            clauses.append("completed_at >= ?")
            parameters.append(self._serialize_datetime(completed_at_after))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT run_id, endpoint, ingestion_kind, instrument_symbol, request_id, dedup_key, "
            "payload_hash, outcome, http_status, ingestion_id, dead_letter_id, detail_json, "
            f"started_at, completed_at FROM ingestion_run_logs {where_clause} "
            "ORDER BY completed_at DESC LIMIT ?"
        )
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [self._row_to_run_log(row) for row in rows]

    def save_or_update_liquidity_memory(self, *, memory_id: str, track_key: str, instrument_symbol: str, coverage_state: str, observed_track: dict[str, Any], derived_summary: dict[str, Any], expires_at: datetime, updated_at: datetime) -> StoredLiquidityMemory:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO liquidity_memories (
                    memory_id, track_key, instrument_symbol, coverage_state, observed_track_json, derived_summary_json, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    memory_id = excluded.memory_id,
                    instrument_symbol = excluded.instrument_symbol,
                    coverage_state = excluded.coverage_state,
                    observed_track_json = excluded.observed_track_json,
                    derived_summary_json = excluded.derived_summary_json,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (memory_id, track_key, instrument_symbol, coverage_state, self._serialize_json(observed_track), self._serialize_json(derived_summary), self._serialize_datetime(expires_at), self._serialize_datetime(updated_at)),
            )
            connection.commit()
        return StoredLiquidityMemory(memory_id, track_key, instrument_symbol, coverage_state, observed_track, derived_summary, expires_at, updated_at)

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload_json, stored_at FROM ingestions WHERE ingestion_id = ?",
                (ingestion_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredIngestion(row["ingestion_id"], row["ingestion_kind"], row["source_snapshot_id"], row["instrument_symbol"], self._parse_json(row["observed_payload_json"]), self._parse_datetime(row["stored_at"]))

    def get_analysis(self, analysis_id: str) -> StoredAnalysis | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT analysis_id, ingestion_id, route_key, analysis_payload_json, stored_at FROM analyses WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredAnalysis(row["analysis_id"], row["ingestion_id"], row["route_key"], self._parse_json(row["analysis_payload_json"]), self._parse_datetime(row["stored_at"]))

    def update_ingestion_observed_payload(self, *, ingestion_id: str, observed_payload: dict[str, Any]) -> StoredIngestion | None:
        with self._connect() as connection:
            connection.execute("UPDATE ingestions SET observed_payload_json = ? WHERE ingestion_id = ?", (self._serialize_json(observed_payload), ingestion_id))
            connection.commit()
        return self.get_ingestion(ingestion_id)

    def list_ingestions(self, *, ingestion_kind: str | None = None, instrument_symbol: str | None = None, source_snapshot_id: str | None = None, limit: int = 100, stored_at_after: datetime | None = None, stored_at_before: datetime | None = None) -> list[StoredIngestion]:
        clauses = []
        parameters: list[Any] = []
        if ingestion_kind is not None:
            clauses.append("ingestion_kind = ?")
            parameters.append(ingestion_kind)
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        if source_snapshot_id is not None:
            clauses.append("source_snapshot_id = ?")
            parameters.append(source_snapshot_id)
        if stored_at_after is not None:
            clauses.append("stored_at >= ?")
            parameters.append(self._serialize_datetime(stored_at_after))
        if stored_at_before is not None:
            clauses.append("stored_at <= ?")
            parameters.append(self._serialize_datetime(stored_at_before))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload_json, stored_at FROM ingestions {where_clause} ORDER BY stored_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [StoredIngestion(row["ingestion_id"], row["ingestion_kind"], row["source_snapshot_id"], row["instrument_symbol"], self._parse_json(row["observed_payload_json"]), self._parse_datetime(row["stored_at"])) for row in rows]

    def purge_ingestions(self, *, ingestion_kinds: list[str], instrument_symbol: str | None, cutoff: datetime) -> int:
        if not ingestion_kinds:
            return 0
        clauses = [f"ingestion_kind IN ({','.join('?' for _ in ingestion_kinds)})", "stored_at < ?"]
        parameters: list[Any] = [*ingestion_kinds, self._serialize_datetime(cutoff)]
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        with self._connect() as connection:
            cursor = connection.execute(f"DELETE FROM ingestions WHERE {' AND '.join(clauses)}", tuple(parameters))
            connection.commit()
        return cursor.rowcount

    def get_liquidity_memory_by_track_key(self, track_key: str) -> StoredLiquidityMemory | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT memory_id, track_key, instrument_symbol, coverage_state, observed_track_json, derived_summary_json, expires_at, updated_at FROM liquidity_memories WHERE track_key = ?",
                (track_key,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_liquidity_memory(row)

    def list_liquidity_memories(self, *, instrument_symbol: str | None = None, as_of: datetime | None = None, limit: int = 100) -> list[StoredLiquidityMemory]:
        clauses = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        if as_of is not None:
            clauses.append("expires_at > ?")
            parameters.append(self._serialize_datetime(as_of))
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT memory_id, track_key, instrument_symbol, coverage_state, observed_track_json, derived_summary_json, expires_at, updated_at FROM liquidity_memories {where_clause} ORDER BY updated_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [self._row_to_liquidity_memory(row) for row in rows]

    def expire_liquidity_memories(self, cutoff: datetime) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM liquidity_memories WHERE expires_at <= ?", (self._serialize_datetime(cutoff),))
            connection.commit()
        return cursor.rowcount

    def save_chat_session(self, *, session_id: str, workspace_id: str, title: str, symbol: str, contract_id: str | None, timeframe: str, window_range: dict[str, Any], active_model: str | None, status: str, draft_text: str, draft_attachments: list[dict[str, Any]], selected_prompt_block_ids: list[str], pinned_context_block_ids: list[str], include_memory_summary: bool, include_recent_messages: bool, mounted_reply_ids: list[str], active_plan_id: str | None, memory_summary_id: str | None, unread_count: int, scroll_offset: int, pinned: bool, created_at: datetime, updated_at: datetime) -> StoredChatSession:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, workspace_id, title, symbol, contract_id, timeframe, window_range_json, active_model, status,
                    draft_text, draft_attachments_json, selected_prompt_block_ids_json, pinned_context_block_ids_json,
                    include_memory_summary, include_recent_messages, mounted_reply_ids_json, active_plan_id, memory_summary_id, unread_count, scroll_offset, pinned, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, workspace_id, title, symbol, contract_id, timeframe, self._serialize_json(window_range), active_model, status,
                    draft_text, self._serialize_any_json(draft_attachments), self._serialize_any_json(selected_prompt_block_ids), self._serialize_any_json(pinned_context_block_ids),
                    int(include_memory_summary), int(include_recent_messages), self._serialize_any_json(mounted_reply_ids), active_plan_id, memory_summary_id, unread_count, scroll_offset, int(pinned), self._serialize_datetime(created_at), self._serialize_datetime(updated_at),
                ),
            )
            connection.commit()
        return self.get_chat_session(session_id)  # type: ignore[return-value]

    def get_chat_session(self, session_id: str) -> StoredChatSession | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return self._row_to_chat_session(row) if row is not None else None

    def list_chat_sessions(self, *, workspace_id: str | None = None, symbol: str | None = None, include_archived: bool = False, limit: int = 200) -> list[StoredChatSession]:
        clauses = []
        parameters: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            parameters.append(workspace_id)
        if symbol is not None:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if not include_archived:
            clauses.append("status != 'archived'")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM chat_sessions {where_clause} ORDER BY pinned DESC, updated_at DESC LIMIT ?", (*parameters, limit)).fetchall()
        return [self._row_to_chat_session(row) for row in rows]

    def update_chat_session(self, session_id: str, **updates: Any) -> StoredChatSession | None:
        if not updates:
            return self.get_chat_session(session_id)
        mapping = {
            "workspace_id": "workspace_id",
            "title": "title",
            "symbol": "symbol",
            "contract_id": "contract_id",
            "timeframe": "timeframe",
            "window_range": ("window_range_json", self._serialize_json),
            "active_model": "active_model",
            "status": "status",
            "draft_text": "draft_text",
            "draft_attachments": ("draft_attachments_json", self._serialize_any_json),
            "selected_prompt_block_ids": ("selected_prompt_block_ids_json", self._serialize_any_json),
            "pinned_context_block_ids": ("pinned_context_block_ids_json", self._serialize_any_json),
            "include_memory_summary": ("include_memory_summary", lambda value: int(bool(value))),
            "include_recent_messages": ("include_recent_messages", lambda value: int(bool(value))),
            "mounted_reply_ids": ("mounted_reply_ids_json", self._serialize_any_json),
            "active_plan_id": "active_plan_id",
            "memory_summary_id": "memory_summary_id",
            "unread_count": "unread_count",
            "scroll_offset": "scroll_offset",
            "pinned": ("pinned", lambda value: int(bool(value))),
            "updated_at": ("updated_at", self._serialize_datetime),
        }
        clauses = []
        parameters: list[Any] = []
        for key, value in updates.items():
            target = mapping.get(key)
            if target is None:
                continue
            if isinstance(target, tuple):
                column, serializer = target
                clauses.append(f"{column} = ?")
                parameters.append(serializer(value))
            else:
                clauses.append(f"{target} = ?")
                parameters.append(value)
        if not clauses:
            return self.get_chat_session(session_id)
        parameters.append(session_id)
        with self._connect() as connection:
            connection.execute(f"UPDATE chat_sessions SET {', '.join(clauses)} WHERE session_id = ?", tuple(parameters))
            connection.commit()
        return self.get_chat_session(session_id)

    def save_chat_message(self, *, message_id: str, session_id: str, parent_message_id: str | None, role: str, content: str, status: str, reply_title: str | None, stream_buffer: str, model: str | None, annotations: list[str], plan_cards: list[str], mounted_to_chart: bool, mounted_object_ids: list[str], is_key_conclusion: bool, request_payload: dict[str, Any], response_payload: dict[str, Any], created_at: datetime, updated_at: datetime, prompt_trace_id: str | None = None) -> StoredChatMessage:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    message_id, session_id, parent_message_id, prompt_trace_id, role, content, status, reply_title, stream_buffer, model,
                    annotations_json, plan_cards_json, mounted_to_chart, mounted_object_ids_json, is_key_conclusion,
                    request_payload_json, response_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id, session_id, parent_message_id, prompt_trace_id, role, content, status, reply_title, stream_buffer, model,
                    self._serialize_any_json(annotations), self._serialize_any_json(plan_cards), int(mounted_to_chart), self._serialize_any_json(mounted_object_ids), int(is_key_conclusion),
                    self._serialize_json(request_payload), self._serialize_json(response_payload), self._serialize_datetime(created_at), self._serialize_datetime(updated_at),
                ),
            )
            connection.commit()
        return self.get_chat_message(message_id)  # type: ignore[return-value]

    def get_chat_message(self, message_id: str) -> StoredChatMessage | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM chat_messages WHERE message_id = ?", (message_id,)).fetchone()
        return self._row_to_chat_message(row) if row is not None else None

    def list_chat_messages(self, *, session_id: str, limit: int = 200, latest: bool = False) -> list[StoredChatMessage]:
        order = "DESC" if latest else "ASC"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at {order} LIMIT ?",
                (session_id, limit),
            ).fetchall()
        messages = [self._row_to_chat_message(row) for row in rows]
        if latest:
            messages.reverse()
        return messages

    def update_chat_message(self, message_id: str, **updates: Any) -> StoredChatMessage | None:
        if not updates:
            return self.get_chat_message(message_id)
        mapping = {
            "content": "content",
            "status": "status",
            "reply_title": "reply_title",
            "stream_buffer": "stream_buffer",
            "model": "model",
            "prompt_trace_id": "prompt_trace_id",
            "annotations": ("annotations_json", self._serialize_any_json),
            "plan_cards": ("plan_cards_json", self._serialize_any_json),
            "mounted_to_chart": ("mounted_to_chart", lambda value: int(bool(value))),
            "mounted_object_ids": ("mounted_object_ids_json", self._serialize_any_json),
            "is_key_conclusion": ("is_key_conclusion", lambda value: int(bool(value))),
            "request_payload": ("request_payload_json", self._serialize_json),
            "response_payload": ("response_payload_json", self._serialize_json),
            "updated_at": ("updated_at", self._serialize_datetime),
        }
        clauses = []
        parameters: list[Any] = []
        for key, value in updates.items():
            target = mapping.get(key)
            if target is None:
                continue
            if isinstance(target, tuple):
                column, serializer = target
                clauses.append(f"{column} = ?")
                parameters.append(serializer(value))
            else:
                clauses.append(f"{target} = ?")
                parameters.append(value)
        if not clauses:
            return self.get_chat_message(message_id)
        parameters.append(message_id)
        with self._connect() as connection:
            connection.execute(f"UPDATE chat_messages SET {', '.join(clauses)} WHERE message_id = ?", tuple(parameters))
            connection.commit()
        return self.get_chat_message(message_id)

    def save_prompt_block(self, *, block_id: str, session_id: str, symbol: str, contract_id: str | None, timeframe: str | None, kind: str, title: str, preview_text: str, full_payload: dict[str, Any], selected_by_default: bool, pinned: bool, ephemeral: bool, created_at: datetime, expires_at: datetime | None) -> StoredPromptBlock:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_prompt_blocks (
                    block_id, session_id, symbol, contract_id, timeframe, kind, title, preview_text, full_payload_json,
                    selected_by_default, pinned, ephemeral, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (block_id, session_id, symbol, contract_id, timeframe, kind, title, preview_text, self._serialize_json(full_payload), int(selected_by_default), int(pinned), int(ephemeral), self._serialize_datetime(created_at), self._serialize_datetime_optional(expires_at)),
            )
            connection.commit()
        return self.get_prompt_block(block_id)  # type: ignore[return-value]

    def get_prompt_block(self, block_id: str) -> StoredPromptBlock | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM chat_prompt_blocks WHERE block_id = ?", (block_id,)).fetchone()
        return self._row_to_prompt_block(row) if row is not None else None

    def list_prompt_blocks(self, *, session_id: str, kind: str | None = None, limit: int = 200) -> list[StoredPromptBlock]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(kind)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM chat_prompt_blocks WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?", tuple(parameters)).fetchall()
        return [self._row_to_prompt_block(row) for row in rows]

    def save_or_update_session_memory(self, *, memory_summary_id: str, session_id: str, summary_version: int, active_model: str | None, symbol: str, contract_id: str | None, timeframe: str, window_range: dict[str, Any], user_goal_summary: str, market_context_summary: str, key_zones_summary: list[str], active_plans_summary: list[str], invalidated_plans_summary: list[str], important_messages: list[str], current_user_intent: str, latest_question: str, latest_answer_summary: str, selected_annotations: list[str], last_updated_at: datetime) -> StoredSessionMemory:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_session_memories (
                    memory_summary_id, session_id, summary_version, active_model, symbol, contract_id, timeframe, window_range_json,
                    user_goal_summary, market_context_summary, key_zones_summary_json, active_plans_summary_json,
                    invalidated_plans_summary_json, important_messages_json, current_user_intent, latest_question,
                    latest_answer_summary, selected_annotations_json, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    memory_summary_id = excluded.memory_summary_id,
                    summary_version = excluded.summary_version,
                    active_model = excluded.active_model,
                    symbol = excluded.symbol,
                    contract_id = excluded.contract_id,
                    timeframe = excluded.timeframe,
                    window_range_json = excluded.window_range_json,
                    user_goal_summary = excluded.user_goal_summary,
                    market_context_summary = excluded.market_context_summary,
                    key_zones_summary_json = excluded.key_zones_summary_json,
                    active_plans_summary_json = excluded.active_plans_summary_json,
                    invalidated_plans_summary_json = excluded.invalidated_plans_summary_json,
                    important_messages_json = excluded.important_messages_json,
                    current_user_intent = excluded.current_user_intent,
                    latest_question = excluded.latest_question,
                    latest_answer_summary = excluded.latest_answer_summary,
                    selected_annotations_json = excluded.selected_annotations_json,
                    last_updated_at = excluded.last_updated_at
                """,
                (
                    memory_summary_id, session_id, summary_version, active_model, symbol, contract_id, timeframe, self._serialize_json(window_range),
                    user_goal_summary, market_context_summary, self._serialize_any_json(key_zones_summary), self._serialize_any_json(active_plans_summary),
                    self._serialize_any_json(invalidated_plans_summary), self._serialize_any_json(important_messages), current_user_intent, latest_question,
                    latest_answer_summary, self._serialize_any_json(selected_annotations), self._serialize_datetime(last_updated_at),
                ),
            )
            connection.commit()
        return self.get_session_memory(session_id)  # type: ignore[return-value]

    def get_session_memory(self, session_id: str) -> StoredSessionMemory | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM chat_session_memories WHERE session_id = ?", (session_id,)).fetchone()
        return self._row_to_session_memory(row) if row is not None else None

    def save_chat_annotation(self, *, annotation_id: str, session_id: str, message_id: str, plan_id: str | None, symbol: str, contract_id: str | None, timeframe: str | None, annotation_type: str, subtype: str | None, label: str, reason: str, start_time: datetime, end_time: datetime | None, expires_at: datetime | None, status: str, priority: int | None, confidence: float | None, visible: bool, pinned: bool, source_kind: str, payload: dict[str, Any], created_at: datetime, updated_at: datetime) -> StoredChatAnnotation:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_annotations (
                    annotation_id, session_id, message_id, plan_id, symbol, contract_id, timeframe, annotation_type, subtype,
                    label, reason, start_time, end_time, expires_at, status, priority, confidence, visible, pinned,
                    source_kind, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id, session_id, message_id, plan_id, symbol, contract_id, timeframe, annotation_type, subtype,
                    label, reason, self._serialize_datetime(start_time), self._serialize_datetime_optional(end_time), self._serialize_datetime_optional(expires_at), status,
                    priority, confidence, int(visible), int(pinned), source_kind, self._serialize_json(payload), self._serialize_datetime(created_at), self._serialize_datetime(updated_at),
                ),
            )
            connection.commit()
        annotations = self.list_chat_annotations(session_id=session_id, message_id=message_id, limit=1000)
        for item in annotations:
            if item.annotation_id == annotation_id:
                return item
        raise RuntimeError(f"annotation '{annotation_id}' was not persisted")

    def list_chat_annotations(self, *, session_id: str, message_id: str | None = None, status: str | None = None, visible_only: bool = False, limit: int = 500) -> list[StoredChatAnnotation]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if message_id is not None:
            clauses.append("message_id = ?")
            parameters.append(message_id)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if visible_only:
            clauses.append("visible = 1")
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM chat_annotations WHERE {' AND '.join(clauses)} ORDER BY created_at ASC LIMIT ?", tuple(parameters)).fetchall()
        return [self._row_to_chat_annotation(row) for row in rows]

    def save_chat_plan_card(self, *, plan_id: str, session_id: str, message_id: str, title: str, side: str, entry_type: str | None, entry_price: float | None, entry_price_low: float | None, entry_price_high: float | None, stop_price: float | None, take_profits: list[dict[str, Any]], invalidations: list[str], time_validity: str | None, risk_reward: float | None, confidence: float | None, priority: int | None, status: str, source_kind: str, notes: str, payload: dict[str, Any], created_at: datetime, updated_at: datetime) -> StoredChatPlanCard:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_plan_cards (
                    plan_id, session_id, message_id, title, side, entry_type, entry_price, entry_price_low, entry_price_high,
                    stop_price, take_profits_json, invalidations_json, time_validity, risk_reward, confidence, priority,
                    status, source_kind, notes, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id, session_id, message_id, title, side, entry_type, entry_price, entry_price_low, entry_price_high,
                    stop_price, self._serialize_any_json(take_profits), self._serialize_any_json(invalidations), time_validity, risk_reward, confidence, priority,
                    status, source_kind, notes, self._serialize_json(payload), self._serialize_datetime(created_at), self._serialize_datetime(updated_at),
                ),
            )
            connection.commit()
        plans = self.list_chat_plan_cards(session_id=session_id, message_id=message_id, limit=1000)
        for item in plans:
            if item.plan_id == plan_id:
                return item
        raise RuntimeError(f"plan '{plan_id}' was not persisted")

    def list_chat_plan_cards(self, *, session_id: str, message_id: str | None = None, status: str | None = None, limit: int = 500) -> list[StoredChatPlanCard]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if message_id is not None:
            clauses.append("message_id = ?")
            parameters.append(message_id)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM chat_plan_cards WHERE {' AND '.join(clauses)} ORDER BY created_at ASC LIMIT ?", tuple(parameters)).fetchall()
        return [self._row_to_chat_plan_card(row) for row in rows]

    def save_atas_backfill_request(
        self,
        record: "ReplayWorkbenchAtasBackfillRecord",
    ) -> "ReplayWorkbenchAtasBackfillRecord":
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO atas_backfill_requests (
                    request_id, cache_key, instrument_symbol, contract_symbol, root_symbol,
                    target_contract_symbol, target_root_symbol, display_timeframe, chart_instance_id,
                    status, requested_at, acknowledged_at, expires_at, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    cache_key = excluded.cache_key,
                    instrument_symbol = excluded.instrument_symbol,
                    contract_symbol = excluded.contract_symbol,
                    root_symbol = excluded.root_symbol,
                    target_contract_symbol = excluded.target_contract_symbol,
                    target_root_symbol = excluded.target_root_symbol,
                    display_timeframe = excluded.display_timeframe,
                    chart_instance_id = excluded.chart_instance_id,
                    status = excluded.status,
                    requested_at = excluded.requested_at,
                    acknowledged_at = excluded.acknowledged_at,
                    expires_at = excluded.expires_at,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.request_id,
                    record.cache_key,
                    record.instrument_symbol,
                    record.contract_symbol,
                    record.root_symbol,
                    record.target_contract_symbol,
                    record.target_root_symbol,
                    record.display_timeframe.value,
                    record.chart_instance_id,
                    record.status.value,
                    self._serialize_datetime(record.requested_at),
                    self._serialize_datetime_optional(record.acknowledged_at),
                    self._serialize_datetime(record.expires_at),
                    self._serialize_any_json(record.model_dump(mode="json")),
                    self._serialize_datetime(datetime.now(tz=UTC)),
                ),
            )
            connection.commit()
        return record

    def list_recent_atas_backfill_requests(
        self,
        *,
        requested_since: datetime,
        statuses: list[str] | None = None,
        limit: int = 500,
    ) -> list["ReplayWorkbenchAtasBackfillRecord"]:
        clauses = ["requested_at >= ?"]
        parameters: list[Any] = [self._serialize_datetime(requested_since)]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(status.value if hasattr(status, "value") else str(status) for status in statuses)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM atas_backfill_requests WHERE {' AND '.join(clauses)} ORDER BY requested_at DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_atas_backfill_request(row) for row in rows]

    def purge_atas_backfill_requests(
        self,
        *,
        requested_before: datetime,
        statuses: list[str] | None = None,
    ) -> int:
        clauses = ["requested_at < ?"]
        parameters: list[Any] = [self._serialize_datetime(requested_before)]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(status.value if hasattr(status, "value") else str(status) for status in statuses)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM atas_backfill_requests WHERE {' AND '.join(clauses)}",
                tuple(parameters),
            )
            connection.commit()
        return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        self._apply_pragma_with_fallback(connection, "journal_mode=WAL")
        self._apply_pragma_with_fallback(connection, "synchronous=NORMAL")
        return connection

    def _apply_pragma_with_fallback(self, connection: sqlite3.Connection, pragma: str) -> None:
        try:
            connection.execute(f"PRAGMA {pragma}")
        except sqlite3.OperationalError as exc:
            if pragma not in self._sqlite_pragma_fallbacks_logged:
                logger.warning(
                    "SQLite pragma disabled for this runtime: db=%s pragma=%s detail=%s",
                    self._database_path,
                    pragma,
                    exc,
                )
                self._sqlite_pragma_fallbacks_logged.add(pragma)

    def _row_to_atas_backfill_request(self, row: sqlite3.Row) -> "ReplayWorkbenchAtasBackfillRecord":
        from atas_market_structure.models._replay import ReplayWorkbenchAtasBackfillRecord

        return ReplayWorkbenchAtasBackfillRecord.model_validate(self._parse_json(row["payload_json"]))

    def _row_to_liquidity_memory(self, row: sqlite3.Row) -> StoredLiquidityMemory:
        return StoredLiquidityMemory(
            memory_id=row["memory_id"],
            track_key=row["track_key"],
            instrument_symbol=row["instrument_symbol"],
            coverage_state=row["coverage_state"],
            observed_track=self._parse_json(row["observed_track_json"]),
            derived_summary=self._parse_json(row["derived_summary_json"]),
            expires_at=self._parse_datetime(row["expires_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_dead_letter(self, row: sqlite3.Row) -> StoredIngestionDeadLetter:
        return StoredIngestionDeadLetter(
            dead_letter_id=row["dead_letter_id"],
            endpoint=row["endpoint"],
            ingestion_kind=row["ingestion_kind"],
            instrument_symbol=row["instrument_symbol"],
            source_snapshot_id=row["source_snapshot_id"],
            request_id=row["request_id"],
            dedup_key=row["dedup_key"],
            payload_hash=row["payload_hash"],
            raw_payload=row["raw_payload"],
            error_code=row["error_code"],
            error_detail=self._parse_json(row["error_detail_json"]),
            ingestion_id=row["ingestion_id"],
            stored_at=self._parse_datetime(row["stored_at"]),
        )

    def _row_to_idempotency_key(self, row: sqlite3.Row) -> StoredIngestionIdempotencyKey:
        return StoredIngestionIdempotencyKey(
            endpoint=row["endpoint"],
            dedup_key=row["dedup_key"],
            request_id=row["request_id"],
            payload_hash=row["payload_hash"],
            ingestion_id=row["ingestion_id"],
            response_payload=self._parse_json(row["response_payload_json"]),
            first_seen_at=self._parse_datetime(row["first_seen_at"]),
            last_seen_at=self._parse_datetime(row["last_seen_at"]),
            duplicate_count=int(row["duplicate_count"]),
        )

    def _row_to_run_log(self, row: sqlite3.Row) -> StoredIngestionRunLog:
        return StoredIngestionRunLog(
            run_id=row["run_id"],
            endpoint=row["endpoint"],
            ingestion_kind=row["ingestion_kind"],
            instrument_symbol=row["instrument_symbol"],
            request_id=row["request_id"],
            dedup_key=row["dedup_key"],
            payload_hash=row["payload_hash"],
            outcome=row["outcome"],
            http_status=int(row["http_status"]),
            ingestion_id=row["ingestion_id"],
            dead_letter_id=row["dead_letter_id"],
            detail=self._parse_json(row["detail_json"]),
            started_at=self._parse_datetime(row["started_at"]),
            completed_at=self._parse_datetime(row["completed_at"]),
        )

    def _row_to_chat_session(self, row: sqlite3.Row) -> StoredChatSession:
        return StoredChatSession(
            session_id=row["session_id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            symbol=row["symbol"],
            contract_id=row["contract_id"],
            timeframe=row["timeframe"],
            window_range=self._parse_json(row["window_range_json"]),
            active_model=row["active_model"],
            status=row["status"],
            draft_text=row["draft_text"],
            draft_attachments=self._parse_any_json(row["draft_attachments_json"]),
            selected_prompt_block_ids=self._parse_any_json(row["selected_prompt_block_ids_json"]),
            pinned_context_block_ids=self._parse_any_json(row["pinned_context_block_ids_json"]),
            include_memory_summary=bool(row["include_memory_summary"]),
            include_recent_messages=bool(row["include_recent_messages"]),
            mounted_reply_ids=self._parse_any_json(row["mounted_reply_ids_json"]),
            active_plan_id=row["active_plan_id"],
            memory_summary_id=row["memory_summary_id"],
            unread_count=row["unread_count"],
            scroll_offset=row["scroll_offset"],
            pinned=bool(row["pinned"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_chat_message(self, row: sqlite3.Row) -> StoredChatMessage:
        return StoredChatMessage(
            message_id=row["message_id"],
            session_id=row["session_id"],
            parent_message_id=row["parent_message_id"],
            prompt_trace_id=row["prompt_trace_id"] if "prompt_trace_id" in row.keys() else None,
            role=row["role"],
            content=row["content"],
            status=row["status"],
            reply_title=row["reply_title"],
            stream_buffer=row["stream_buffer"],
            model=row["model"],
            annotations=self._parse_any_json(row["annotations_json"]),
            plan_cards=self._parse_any_json(row["plan_cards_json"]),
            mounted_to_chart=bool(row["mounted_to_chart"]),
            mounted_object_ids=self._parse_any_json(row["mounted_object_ids_json"]),
            is_key_conclusion=bool(row["is_key_conclusion"]),
            request_payload=self._parse_json(row["request_payload_json"]),
            response_payload=self._parse_json(row["response_payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_prompt_block(self, row: sqlite3.Row) -> StoredPromptBlock:
        return StoredPromptBlock(
            block_id=row["block_id"],
            session_id=row["session_id"],
            symbol=row["symbol"],
            contract_id=row["contract_id"],
            timeframe=row["timeframe"],
            kind=row["kind"],
            title=row["title"],
            preview_text=row["preview_text"],
            full_payload=self._parse_json(row["full_payload_json"]),
            selected_by_default=bool(row["selected_by_default"]),
            pinned=bool(row["pinned"]),
            ephemeral=bool(row["ephemeral"]),
            created_at=self._parse_datetime(row["created_at"]),
            expires_at=self._parse_datetime_optional(row["expires_at"]),
        )

    def _row_to_session_memory(self, row: sqlite3.Row) -> StoredSessionMemory:
        return StoredSessionMemory(
            memory_summary_id=row["memory_summary_id"],
            session_id=row["session_id"],
            summary_version=row["summary_version"],
            active_model=row["active_model"],
            symbol=row["symbol"],
            contract_id=row["contract_id"],
            timeframe=row["timeframe"],
            window_range=self._parse_json(row["window_range_json"]),
            user_goal_summary=row["user_goal_summary"],
            market_context_summary=row["market_context_summary"],
            key_zones_summary=self._parse_any_json(row["key_zones_summary_json"]),
            active_plans_summary=self._parse_any_json(row["active_plans_summary_json"]),
            invalidated_plans_summary=self._parse_any_json(row["invalidated_plans_summary_json"]),
            important_messages=self._parse_any_json(row["important_messages_json"]),
            current_user_intent=row["current_user_intent"],
            latest_question=row["latest_question"],
            latest_answer_summary=row["latest_answer_summary"],
            selected_annotations=self._parse_any_json(row["selected_annotations_json"]),
            last_updated_at=self._parse_datetime(row["last_updated_at"]),
        )

    def _row_to_chat_annotation(self, row: sqlite3.Row) -> StoredChatAnnotation:
        return StoredChatAnnotation(
            annotation_id=row["annotation_id"],
            session_id=row["session_id"],
            message_id=row["message_id"],
            plan_id=row["plan_id"],
            symbol=row["symbol"],
            contract_id=row["contract_id"],
            timeframe=row["timeframe"],
            annotation_type=row["annotation_type"],
            subtype=row["subtype"],
            label=row["label"],
            reason=row["reason"],
            start_time=self._parse_datetime(row["start_time"]),
            end_time=self._parse_datetime_optional(row["end_time"]),
            expires_at=self._parse_datetime_optional(row["expires_at"]),
            status=row["status"],
            priority=row["priority"],
            confidence=row["confidence"],
            visible=bool(row["visible"]),
            pinned=bool(row["pinned"]),
            source_kind=row["source_kind"],
            payload=self._parse_json(row["payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_chat_plan_card(self, row: sqlite3.Row) -> StoredChatPlanCard:
        return StoredChatPlanCard(
            plan_id=row["plan_id"],
            session_id=row["session_id"],
            message_id=row["message_id"],
            title=row["title"],
            side=row["side"],
            entry_type=row["entry_type"],
            entry_price=row["entry_price"],
            entry_price_low=row["entry_price_low"],
            entry_price_high=row["entry_price_high"],
            stop_price=row["stop_price"],
            take_profits=self._parse_any_json(row["take_profits_json"]),
            invalidations=self._parse_any_json(row["invalidations_json"]),
            time_validity=row["time_validity"],
            risk_reward=row["risk_reward"],
            confidence=row["confidence"],
            priority=row["priority"],
            status=row["status"],
            source_kind=row["source_kind"],
            notes=row["notes"],
            payload=self._parse_json(row["payload_json"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _row_to_atas_chart_bar_raw(self, row: sqlite3.Row) -> "AtasChartBarRaw":
        from atas_market_structure.models._enums import Timeframe
        from atas_market_structure.models._replay import AtasChartBarRaw

        return AtasChartBarRaw(
            chart_instance_id=row["chart_instance_id"] or None,
            root_symbol=row["root_symbol"] or None,
            contract_symbol=row["contract_symbol"] or None,
            symbol=row["symbol"],
            venue=row["venue"] or None,
            timeframe=Timeframe(row["timeframe"]),
            bar_timestamp_utc=self._parse_datetime(row["bar_timestamp_utc"]) if row["bar_timestamp_utc"] else None,
            started_at_utc=self._parse_datetime(row["started_at_utc"]),
            ended_at_utc=self._parse_datetime(row["ended_at_utc"]),
            source_started_at=self._parse_datetime(row["source_started_at"]),
            original_bar_time_text=row["original_bar_time_text"] or None,
            timestamp_basis=row["timestamp_basis"] or None,
            chart_display_timezone_mode=row["chart_display_timezone_mode"] or None,
            chart_display_timezone_name=row["chart_display_timezone_name"] or None,
            chart_display_utc_offset_minutes=row["chart_display_utc_offset_minutes"],
            instrument_timezone_value=row["instrument_timezone_value"] or None,
            instrument_timezone_source=row["instrument_timezone_source"] or None,
            collector_local_timezone_name=row["collector_local_timezone_name"] or None,
            collector_local_utc_offset_minutes=row["collector_local_utc_offset_minutes"],
            timezone_capture_confidence=row["timezone_capture_confidence"] or None,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            bid_volume=row["bid_volume"],
            ask_volume=row["ask_volume"],
            delta=row["delta"],
            trade_count=row["trade_count"],
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _serialize_json(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=True,
            default=SQLiteAnalysisRepository._json_default,
        )

    @staticmethod
    def _serialize_any_json(value: Any) -> str:
        return json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=True,
            default=SQLiteAnalysisRepository._json_default,
        )

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
            return timestamp.isoformat()
        raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")

    @staticmethod
    def _parse_json(value: str) -> dict[str, Any]:
        return json.loads(value)

    @staticmethod
    def _parse_any_json(value: str) -> Any:
        return json.loads(value)

    @staticmethod
    def _serialize_datetime(value: datetime) -> str:
        timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return timestamp.isoformat()

    @classmethod
    def _serialize_datetime_optional(cls, value: datetime | None) -> str | None:
        if value is None:
            return None
        return cls._serialize_datetime(value)

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        # Ensure UTC awareness — the codebase convention is UTC everywhere.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @classmethod
    def _parse_datetime_optional(cls, value: str | None) -> datetime | None:
        if value is None:
            return None
        return cls._parse_datetime(value)

    # ─── Chart Candles ──────────────────────────────────────────────────────────

    def upsert_chart_candle(self, candle: "ChartCandle") -> "ChartCandle":
        """Insert or update a single chart candle using exact replacement semantics."""
        from atas_market_structure.models._replay import ChartCandle as ChartCandleModel

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chart_candles
                    (symbol, timeframe, started_at, ended_at,
                     source_started_at, open, high, low, close, volume, tick_volume, delta, updated_at,
                     source_timezone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, started_at) DO UPDATE SET
                    source_started_at = MIN(chart_candles.source_started_at, excluded.source_started_at),
                    open        = excluded.open,
                    high        = excluded.high,
                    low         = excluded.low,
                    close       = excluded.close,
                    volume      = excluded.volume,
                    tick_volume = excluded.tick_volume,
                    delta       = excluded.delta,
                    ended_at    = excluded.ended_at,
                    updated_at  = excluded.updated_at,
                    source_timezone = COALESCE(NULLIF(excluded.source_timezone, ''), chart_candles.source_timezone)
                """,
                (
                    candle.symbol,
                    candle.timeframe.value,
                    self._serialize_datetime(candle.started_at),
                    self._serialize_datetime(candle.ended_at),
                    self._serialize_datetime(candle.source_started_at or candle.started_at),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    candle.tick_volume,
                    candle.delta,
                    self._serialize_datetime(candle.updated_at),
                    candle.source_timezone or "",
                ),
            )
            conn.commit()
        return candle

    def upsert_chart_candles(self, candles: list["ChartCandle"]) -> int:
        """Bulk upsert a list of chart candles using exact replacement semantics."""
        if not candles:
            return 0
        rows = [
            (
                c.symbol,
                c.timeframe.value,
                self._serialize_datetime(c.started_at),
                self._serialize_datetime(c.ended_at),
                self._serialize_datetime(c.source_started_at or c.started_at),
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.tick_volume,
                c.delta,
                self._serialize_datetime(c.updated_at),
                c.source_timezone or "",
            )
            for c in candles
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO chart_candles
                    (symbol, timeframe, started_at, ended_at,
                     source_started_at, open, high, low, close, volume, tick_volume, delta, updated_at,
                     source_timezone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, started_at) DO UPDATE SET
                    source_started_at = MIN(chart_candles.source_started_at, excluded.source_started_at),
                    open        = excluded.open,
                    high        = excluded.high,
                    low         = excluded.low,
                    close       = excluded.close,
                    volume      = excluded.volume,
                    tick_volume = excluded.tick_volume,
                    delta       = excluded.delta,
                    ended_at    = excluded.ended_at,
                    updated_at  = excluded.updated_at,
                    source_timezone = COALESCE(NULLIF(excluded.source_timezone, ''), chart_candles.source_timezone)
                """,
                rows,
            )
            conn.commit()
        return len(candles)

    def replace_chart_candles(self, candles: list["ChartCandle"]) -> int:
        """Compatibility alias for exact chart-candle upserts."""
        return self.upsert_chart_candles(candles)

    def list_chart_candles(
        self,
        symbol: str,
        timeframe: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list["ChartCandle"]:
        """Return pre-aggregated chart candles for a symbol/timeframe/window.

        The returned list is ordered ASC by started_at, ready for the UI.
        """
        from atas_market_structure.models._replay import ChartCandle as ChartCandleModel
        from atas_market_structure.models._enums import Timeframe

        tf_value = Timeframe(timeframe).value
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, timeframe, started_at, ended_at,
                       source_started_at, open, high, low, close, volume, tick_volume, delta,
                       updated_at, source_timezone
                  FROM chart_candles
                 WHERE symbol    = ?
                   AND timeframe = ?
                   AND started_at >= ?
                   AND started_at <= ?
                 ORDER BY started_at ASC
                 LIMIT ?
                """,
                (
                    symbol,
                    tf_value,
                    self._serialize_datetime(window_start),
                    self._serialize_datetime(window_end),
                    limit,
                ),
            ).fetchall()

        return [
            ChartCandleModel(
                symbol=row["symbol"],
                timeframe=Timeframe(row["timeframe"]),
                started_at=self._parse_datetime(row["started_at"]),
                ended_at=self._parse_datetime(row["ended_at"]),
                source_started_at=self._parse_datetime_optional(row["source_started_at"]) or self._parse_datetime(row["started_at"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                tick_volume=row["tick_volume"],
                delta=row["delta"],
                updated_at=self._parse_datetime(row["updated_at"]),
                source_timezone=row["source_timezone"] or None,
            )
            for row in rows
        ]

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
        """Return total candle count for a symbol/timeframe, useful for backfill status."""
        from atas_market_structure.models._enums import Timeframe

        tf_value = Timeframe(timeframe).value
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM chart_candles WHERE symbol = ? AND timeframe = ?",
                (symbol, tf_value),
            ).fetchone()
        return row["cnt"] if row else 0

    def purge_chart_candles(self, *, symbol: str | None, older_than: datetime) -> int:
        """Delete chart candle rows older than a cutoff. Returns row count."""
        where_parts = ["updated_at < ?"]
        params: list[Any] = [self._serialize_datetime(older_than)]
        if symbol:
            where_parts.insert(0, "symbol = ?")
            params.insert(0, symbol)
        where_clause = "WHERE " + " AND ".join(where_parts)
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM chart_candles {where_clause}", tuple(params))
            conn.commit()
        return cur.rowcount

    def delete_chart_candles_window(
        self,
        *,
        symbol: str,
        timeframe: str | None,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Delete chart candles overlapping one UTC window for exact repair/reload flows."""
        from atas_market_structure.models._enums import Timeframe

        where_parts = [
            "symbol = ?",
            "started_at <= ?",
            "ended_at >= ?",
        ]
        params: list[Any] = [
            symbol,
            self._serialize_datetime(window_end),
            self._serialize_datetime(window_start),
        ]
        if timeframe is not None:
            where_parts.append("timeframe = ?")
            params.append(Timeframe(timeframe).value)

        where_clause = "WHERE " + " AND ".join(where_parts)
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM chart_candles {where_clause}", tuple(params))
            conn.commit()
        return cur.rowcount

    def upsert_atas_chart_bars_raw(self, bars: list["AtasChartBarRaw"]) -> int:
        """Upsert raw mirrored ATAS chart bars without duplicating repeated UTC bars."""
        if not bars:
            return 0

        rows = [
            (
                bar.chart_instance_id or "",
                bar.root_symbol,
                bar.contract_symbol or "",
                bar.symbol,
                bar.venue,
                bar.timeframe.value,
                self._serialize_datetime(bar.bar_timestamp_utc) if bar.bar_timestamp_utc is not None else None,
                self._serialize_datetime(bar.started_at_utc),
                self._serialize_datetime(bar.ended_at_utc),
                self._serialize_datetime(bar.source_started_at),
                bar.original_bar_time_text,
                bar.timestamp_basis,
                bar.chart_display_timezone_mode,
                bar.chart_display_timezone_name,
                bar.chart_display_utc_offset_minutes,
                bar.instrument_timezone_value,
                bar.instrument_timezone_source,
                bar.collector_local_timezone_name,
                bar.collector_local_utc_offset_minutes,
                bar.timezone_capture_confidence,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.bid_volume,
                bar.ask_volume,
                bar.delta,
                bar.trade_count,
                self._serialize_datetime(bar.updated_at),
            )
            for bar in bars
        ]

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO atas_chart_bars_raw (
                    chart_instance_id, root_symbol, contract_symbol, symbol, venue, timeframe,
                    bar_timestamp_utc,
                    started_at_utc, ended_at_utc, source_started_at, original_bar_time_text,
                    timestamp_basis, chart_display_timezone_mode, chart_display_timezone_name,
                    chart_display_utc_offset_minutes, instrument_timezone_value, instrument_timezone_source,
                    collector_local_timezone_name, collector_local_utc_offset_minutes,
                    timezone_capture_confidence, open, high, low, close, volume, bid_volume,
                    ask_volume, delta, trade_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chart_instance_id, contract_symbol, timeframe, started_at_utc) DO UPDATE SET
                    root_symbol = excluded.root_symbol,
                    symbol = excluded.symbol,
                    venue = excluded.venue,
                    bar_timestamp_utc = COALESCE(excluded.bar_timestamp_utc, atas_chart_bars_raw.bar_timestamp_utc),
                    ended_at_utc = excluded.ended_at_utc,
                    source_started_at = excluded.source_started_at,
                    original_bar_time_text = excluded.original_bar_time_text,
                    timestamp_basis = excluded.timestamp_basis,
                    chart_display_timezone_mode = excluded.chart_display_timezone_mode,
                    chart_display_timezone_name = excluded.chart_display_timezone_name,
                    chart_display_utc_offset_minutes = excluded.chart_display_utc_offset_minutes,
                    instrument_timezone_value = excluded.instrument_timezone_value,
                    instrument_timezone_source = excluded.instrument_timezone_source,
                    collector_local_timezone_name = excluded.collector_local_timezone_name,
                    collector_local_utc_offset_minutes = excluded.collector_local_utc_offset_minutes,
                    timezone_capture_confidence = excluded.timezone_capture_confidence,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    bid_volume = excluded.bid_volume,
                    ask_volume = excluded.ask_volume,
                    delta = excluded.delta,
                    trade_count = excluded.trade_count,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            conn.commit()
        return len(bars)

    def list_atas_chart_bars_raw(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        limit: int = 5000,
    ) -> list["AtasChartBarRaw"]:
        from atas_market_structure.models._enums import Timeframe

        where_parts: list[str] = []
        params: list[Any] = []
        if chart_instance_id is not None:
            where_parts.append("chart_instance_id = ?")
            params.append(chart_instance_id)
        if contract_symbol is not None:
            where_parts.append("contract_symbol = ?")
            params.append(contract_symbol)
        if root_symbol is not None:
            where_parts.append("root_symbol = ?")
            params.append(root_symbol)
        if timeframe is not None:
            where_parts.append("timeframe = ?")
            params.append(Timeframe(timeframe).value)
        if window_start is not None:
            where_parts.append("started_at_utc >= ?")
            params.append(self._serialize_datetime(window_start))
        if window_end is not None:
            where_parts.append("started_at_utc <= ?")
            params.append(self._serialize_datetime(window_end))

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = (
            "SELECT chart_instance_id, root_symbol, contract_symbol, symbol, venue, timeframe, "
            "bar_timestamp_utc, started_at_utc, ended_at_utc, source_started_at, original_bar_time_text, "
            "timestamp_basis, chart_display_timezone_mode, chart_display_timezone_name, "
            "chart_display_utc_offset_minutes, instrument_timezone_value, instrument_timezone_source, "
            "collector_local_timezone_name, collector_local_utc_offset_minutes, timezone_capture_confidence, "
            "open, high, low, close, volume, bid_volume, ask_volume, delta, trade_count, updated_at "
            f"FROM atas_chart_bars_raw {where_clause} ORDER BY started_at_utc ASC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_atas_chart_bar_raw(row) for row in rows]

    def count_atas_chart_bars_raw(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> int:
        from atas_market_structure.models._enums import Timeframe

        where_parts: list[str] = []
        params: list[Any] = []
        if chart_instance_id is not None:
            where_parts.append("chart_instance_id = ?")
            params.append(chart_instance_id)
        if contract_symbol is not None:
            where_parts.append("contract_symbol = ?")
            params.append(contract_symbol)
        if root_symbol is not None:
            where_parts.append("root_symbol = ?")
            params.append(root_symbol)
        if timeframe is not None:
            where_parts.append("timeframe = ?")
            params.append(Timeframe(timeframe).value)
        if window_start is not None:
            where_parts.append("started_at_utc >= ?")
            params.append(self._serialize_datetime(window_start))
        if window_end is not None:
            where_parts.append("started_at_utc <= ?")
            params.append(self._serialize_datetime(window_end))

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"SELECT COUNT(*) AS cnt FROM atas_chart_bars_raw {where_clause}"
        with self._connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        return row["cnt"] if row else 0

    def get_atas_chart_bars_raw_coverage(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> tuple[datetime | None, datetime | None, int]:
        from atas_market_structure.models._enums import Timeframe

        where_parts: list[str] = []
        params: list[Any] = []
        if chart_instance_id is not None:
            where_parts.append("chart_instance_id = ?")
            params.append(chart_instance_id)
        if contract_symbol is not None:
            where_parts.append("contract_symbol = ?")
            params.append(contract_symbol)
        if root_symbol is not None:
            where_parts.append("root_symbol = ?")
            params.append(root_symbol)
        if timeframe is not None:
            where_parts.append("timeframe = ?")
            params.append(Timeframe(timeframe).value)
        if window_start is not None:
            where_parts.append("started_at_utc >= ?")
            params.append(self._serialize_datetime(window_start))
        if window_end is not None:
            where_parts.append("started_at_utc <= ?")
            params.append(self._serialize_datetime(window_end))

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = (
            "SELECT "
            "MIN(started_at_utc) AS first_started_at_utc, "
            "MAX(started_at_utc) AS last_started_at_utc, "
            "COUNT(*) AS cnt "
            f"FROM atas_chart_bars_raw {where_clause}"
        )
        with self._connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
        if row is None:
            return None, None, 0
        first_started_at = (
            self._parse_datetime(row["first_started_at_utc"])
            if row["first_started_at_utc"] is not None
            else None
        )
        last_started_at = (
            self._parse_datetime(row["last_started_at_utc"])
            if row["last_started_at_utc"] is not None
            else None
        )
        return first_started_at, last_started_at, int(row["cnt"] or 0)

    def purge_atas_chart_bars_raw(
        self,
        *,
        older_than: datetime,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
    ) -> int:
        where_parts = ["updated_at < ?"]
        params: list[Any] = [self._serialize_datetime(older_than)]
        if chart_instance_id is not None:
            where_parts.insert(0, "chart_instance_id = ?")
            params.insert(0, chart_instance_id)
        if contract_symbol is not None:
            where_parts.insert(0, "contract_symbol = ?")
            params.insert(0, contract_symbol)
        if root_symbol is not None:
            where_parts.insert(0, "root_symbol = ?")
            params.insert(0, root_symbol)

        where_clause = "WHERE " + " AND ".join(where_parts)
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM atas_chart_bars_raw {where_clause}", tuple(params))
            conn.commit()
        return cur.rowcount

    def delete_atas_chart_bars_raw_window(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Delete raw mirrored chart bars overlapping one UTC window for manual repair flows."""
        from atas_market_structure.models._enums import Timeframe

        where_parts = [
            "started_at_utc <= ?",
            "ended_at_utc >= ?",
        ]
        params: list[Any] = [
            self._serialize_datetime(window_end),
            self._serialize_datetime(window_start),
        ]
        if chart_instance_id is not None:
            where_parts.insert(0, "chart_instance_id = ?")
            params.insert(0, chart_instance_id)
        if contract_symbol is not None:
            where_parts.insert(0, "contract_symbol = ?")
            params.insert(0, contract_symbol)
        if root_symbol is not None:
            where_parts.insert(0, "root_symbol = ?")
            params.insert(0, root_symbol)
        if timeframe is not None:
            where_parts.append("timeframe = ?")
            params.append(Timeframe(timeframe).value)

        where_clause = "WHERE " + " AND ".join(where_parts)
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM atas_chart_bars_raw {where_clause}", tuple(params))
            conn.commit()
        return cur.rowcount

    def list_atas_pipeline_contracts(self, limit: int = 100) -> list[StoredPipelineContractOverview]:
        minute_1 = "1m"
        today = datetime.now(tz=UTC).date().isoformat()
        query = """
            SELECT
                contract_symbol,
                COALESCE(NULLIF(root_symbol, ''), NULLIF(symbol, ''), contract_symbol) AS effective_root_symbol,
                MAX(started_at_utc) AS latest_raw_started_at,
                MAX(updated_at) AS latest_raw_updated_at,
                SUM(CASE WHEN timeframe = ? THEN 1 ELSE 0 END) AS total_raw_1m_count,
                SUM(CASE WHEN timeframe = ? AND substr(started_at_utc, 1, 10) = ? THEN 1 ELSE 0 END) AS today_raw_1m_count
            FROM atas_chart_bars_raw
            WHERE contract_symbol <> ''
            GROUP BY contract_symbol, COALESCE(NULLIF(root_symbol, ''), NULLIF(symbol, ''), contract_symbol)
            ORDER BY latest_raw_updated_at DESC, contract_symbol ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (minute_1, minute_1, today, limit)).fetchall()
        return [
            StoredPipelineContractOverview(
                contract_symbol=row["contract_symbol"],
                root_symbol=row["effective_root_symbol"],
                latest_raw_started_at=self._parse_datetime_optional(row["latest_raw_started_at"]),
                latest_raw_updated_at=self._parse_datetime_optional(row["latest_raw_updated_at"]),
                total_raw_1m_count=int(row["total_raw_1m_count"] or 0),
                today_raw_1m_count=int(row["today_raw_1m_count"] or 0),
            )
            for row in rows
        ]

    def list_atas_raw_bar_daily_counts(
        self,
        *,
        contract_symbol: str,
        timeframe: str,
        limit: int = 30,
    ) -> list[StoredPipelineDailyCount]:
        from atas_market_structure.models._enums import Timeframe

        query = """
            SELECT
                substr(started_at_utc, 1, 10) AS bar_date,
                timeframe,
                COUNT(*) AS candle_count,
                MAX(updated_at) AS latest_updated_at
            FROM atas_chart_bars_raw
            WHERE contract_symbol = ?
              AND timeframe = ?
            GROUP BY bar_date, timeframe
            ORDER BY bar_date DESC
            LIMIT ?
        """
        tf_value = Timeframe(timeframe).value
        with self._connect() as conn:
            rows = conn.execute(query, (contract_symbol, tf_value, limit)).fetchall()
        return [
            StoredPipelineDailyCount(
                bar_date=row["bar_date"],
                timeframe=row["timeframe"],
                candle_count=int(row["candle_count"] or 0),
                latest_updated_at=self._parse_datetime_optional(row["latest_updated_at"]),
            )
            for row in rows
        ]

    def count_atas_chart_bars_raw_updated_since(
        self,
        *,
        contract_symbol: str,
        timeframe: str,
        updated_since: datetime,
    ) -> int:
        from atas_market_structure.models._enums import Timeframe

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM atas_chart_bars_raw
                WHERE contract_symbol = ?
                  AND timeframe = ?
                  AND updated_at >= ?
                """,
                (
                    contract_symbol,
                    Timeframe(timeframe).value,
                    self._serialize_datetime(updated_since),
                ),
            ).fetchone()
        return int(row["cnt"] or 0) if row is not None else 0

    def list_chart_candle_daily_counts(
        self,
        *,
        symbol: str,
        timeframes: list[str],
        limit: int = 90,
    ) -> list[StoredPipelineDailyCount]:
        from atas_market_structure.models._enums import Timeframe

        if not timeframes:
            return []
        normalized_timeframes = [Timeframe(item).value for item in timeframes]
        placeholders = ", ".join("?" for _ in normalized_timeframes)
        query = f"""
            SELECT
                substr(started_at, 1, 10) AS bar_date,
                timeframe,
                COUNT(*) AS candle_count,
                MAX(updated_at) AS latest_updated_at
            FROM chart_candles
            WHERE symbol = ?
              AND timeframe IN ({placeholders})
            GROUP BY bar_date, timeframe
            ORDER BY bar_date DESC, timeframe ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (symbol, *normalized_timeframes, limit)).fetchall()
        return [
            StoredPipelineDailyCount(
                bar_date=row["bar_date"],
                timeframe=row["timeframe"],
                candle_count=int(row["candle_count"] or 0),
                latest_updated_at=self._parse_datetime_optional(row["latest_updated_at"]),
            )
            for row in rows
        ]

    def count_chart_candles_updated_since(
        self,
        *,
        symbol: str,
        timeframe: str,
        updated_since: datetime,
    ) -> int:
        from atas_market_structure.models._enums import Timeframe

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM chart_candles
                WHERE symbol = ?
                  AND timeframe = ?
                  AND updated_at >= ?
                """,
                (
                    symbol,
                    Timeframe(timeframe).value,
                    self._serialize_datetime(updated_since),
                ),
            ).fetchone()
        return int(row["cnt"] or 0) if row is not None else 0
