from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredIngestion:
    ingestion_id: str
    ingestion_kind: str
    source_snapshot_id: str
    instrument_symbol: str
    observed_payload: dict[str, Any]
    stored_at: datetime


@dataclass(frozen=True)
class StoredAnalysis:
    analysis_id: str
    ingestion_id: str
    route_key: str
    analysis_payload: dict[str, Any]
    stored_at: datetime


@dataclass(frozen=True)
class StoredLiquidityMemory:
    memory_id: str
    track_key: str
    instrument_symbol: str
    coverage_state: str
    observed_track: dict[str, Any]
    derived_summary: dict[str, Any]
    expires_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredChatSession:
    session_id: str
    workspace_id: str
    title: str
    symbol: str
    contract_id: str | None
    timeframe: str
    window_range: dict[str, Any]
    active_model: str | None
    status: str
    draft_text: str
    draft_attachments: list[dict[str, Any]]
    selected_prompt_block_ids: list[str]
    pinned_context_block_ids: list[str]
    include_memory_summary: bool
    include_recent_messages: bool
    mounted_reply_ids: list[str]
    active_plan_id: str | None
    memory_summary_id: str | None
    unread_count: int
    scroll_offset: int
    pinned: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredChatMessage:
    message_id: str
    session_id: str
    parent_message_id: str | None
    role: str
    content: str
    status: str
    reply_title: str | None
    stream_buffer: str
    model: str | None
    annotations: list[str]
    plan_cards: list[str]
    mounted_to_chart: bool
    mounted_object_ids: list[str]
    is_key_conclusion: bool
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredPromptBlock:
    block_id: str
    session_id: str
    symbol: str
    contract_id: str | None
    timeframe: str | None
    kind: str
    title: str
    preview_text: str
    full_payload: dict[str, Any]
    selected_by_default: bool
    pinned: bool
    ephemeral: bool
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True)
class StoredSessionMemory:
    memory_summary_id: str
    session_id: str
    summary_version: int
    active_model: str | None
    symbol: str
    contract_id: str | None
    timeframe: str
    window_range: dict[str, Any]
    user_goal_summary: str
    market_context_summary: str
    key_zones_summary: list[str]
    active_plans_summary: list[str]
    invalidated_plans_summary: list[str]
    important_messages: list[str]
    current_user_intent: str
    latest_question: str
    latest_answer_summary: str
    selected_annotations: list[str]
    last_updated_at: datetime


@dataclass(frozen=True)
class StoredChatAnnotation:
    annotation_id: str
    session_id: str
    message_id: str
    plan_id: str | None
    symbol: str
    contract_id: str | None
    timeframe: str | None
    annotation_type: str
    subtype: str | None
    label: str
    reason: str
    start_time: datetime
    end_time: datetime | None
    expires_at: datetime | None
    status: str
    priority: int | None
    confidence: float | None
    visible: bool
    pinned: bool
    source_kind: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredChatPlanCard:
    plan_id: str
    session_id: str
    message_id: str
    title: str
    side: str
    entry_type: str | None
    entry_price: float | None
    entry_price_low: float | None
    entry_price_high: float | None
    stop_price: float | None
    take_profits: list[dict[str, Any]]
    invalidations: list[str]
    time_validity: str | None
    risk_reward: float | None
    confidence: float | None
    priority: int | None
    status: str
    source_kind: str
    notes: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AnalysisRepository(Protocol):
    def initialize(self) -> None:
        ...

    def save_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, Any],
        stored_at: datetime,
    ) -> StoredIngestion:
        ...

    def save_analysis(
        self,
        *,
        analysis_id: str,
        ingestion_id: str,
        route_key: str,
        analysis_payload: dict[str, Any],
        stored_at: datetime,
    ) -> StoredAnalysis:
        ...

    def save_or_update_liquidity_memory(
        self,
        *,
        memory_id: str,
        track_key: str,
        instrument_symbol: str,
        coverage_state: str,
        observed_track: dict[str, Any],
        derived_summary: dict[str, Any],
        expires_at: datetime,
        updated_at: datetime,
    ) -> StoredLiquidityMemory:
        ...

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        ...

    def get_analysis(self, analysis_id: str) -> StoredAnalysis | None:
        ...

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, Any],
    ) -> StoredIngestion | None:
        ...

    def list_ingestions(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        source_snapshot_id: str | None = None,
        limit: int = 100,
    ) -> list[StoredIngestion]:
        ...

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        ...

    def get_liquidity_memory_by_track_key(self, track_key: str) -> StoredLiquidityMemory | None:
        ...

    def list_liquidity_memories(
        self,
        *,
        instrument_symbol: str | None = None,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> list[StoredLiquidityMemory]:
        ...

    def expire_liquidity_memories(self, cutoff: datetime) -> int:
        ...

    def save_chat_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        title: str,
        symbol: str,
        contract_id: str | None,
        timeframe: str,
        window_range: dict[str, Any],
        active_model: str | None,
        status: str,
        draft_text: str,
        draft_attachments: list[dict[str, Any]],
        selected_prompt_block_ids: list[str],
        pinned_context_block_ids: list[str],
        include_memory_summary: bool,
        include_recent_messages: bool,
        mounted_reply_ids: list[str],
        active_plan_id: str | None,
        memory_summary_id: str | None,
        unread_count: int,
        scroll_offset: int,
        pinned: bool,
        created_at: datetime,
        updated_at: datetime,
    ) -> StoredChatSession:
        ...

    def get_chat_session(self, session_id: str) -> StoredChatSession | None:
        ...

    def list_chat_sessions(
        self,
        *,
        workspace_id: str | None = None,
        symbol: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> list[StoredChatSession]:
        ...

    def update_chat_session(self, session_id: str, **updates: Any) -> StoredChatSession | None:
        ...

    def save_chat_message(
        self,
        *,
        message_id: str,
        session_id: str,
        parent_message_id: str | None,
        role: str,
        content: str,
        status: str,
        reply_title: str | None,
        stream_buffer: str,
        model: str | None,
        annotations: list[str],
        plan_cards: list[str],
        mounted_to_chart: bool,
        mounted_object_ids: list[str],
        is_key_conclusion: bool,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> StoredChatMessage:
        ...

    def get_chat_message(self, message_id: str) -> StoredChatMessage | None:
        ...

    def list_chat_messages(self, *, session_id: str, limit: int = 200) -> list[StoredChatMessage]:
        ...

    def update_chat_message(self, message_id: str, **updates: Any) -> StoredChatMessage | None:
        ...

    def save_prompt_block(
        self,
        *,
        block_id: str,
        session_id: str,
        symbol: str,
        contract_id: str | None,
        timeframe: str | None,
        kind: str,
        title: str,
        preview_text: str,
        full_payload: dict[str, Any],
        selected_by_default: bool,
        pinned: bool,
        ephemeral: bool,
        created_at: datetime,
        expires_at: datetime | None,
    ) -> StoredPromptBlock:
        ...

    def get_prompt_block(self, block_id: str) -> StoredPromptBlock | None:
        ...

    def list_prompt_blocks(self, *, session_id: str, kind: str | None = None, limit: int = 200) -> list[StoredPromptBlock]:
        ...

    def save_or_update_session_memory(
        self,
        *,
        memory_summary_id: str,
        session_id: str,
        summary_version: int,
        active_model: str | None,
        symbol: str,
        contract_id: str | None,
        timeframe: str,
        window_range: dict[str, Any],
        user_goal_summary: str,
        market_context_summary: str,
        key_zones_summary: list[str],
        active_plans_summary: list[str],
        invalidated_plans_summary: list[str],
        important_messages: list[str],
        current_user_intent: str,
        latest_question: str,
        latest_answer_summary: str,
        selected_annotations: list[str],
        last_updated_at: datetime,
    ) -> StoredSessionMemory:
        ...

    def get_session_memory(self, session_id: str) -> StoredSessionMemory | None:
        ...

    def save_chat_annotation(
        self,
        *,
        annotation_id: str,
        session_id: str,
        message_id: str,
        plan_id: str | None,
        symbol: str,
        contract_id: str | None,
        timeframe: str | None,
        annotation_type: str,
        subtype: str | None,
        label: str,
        reason: str,
        start_time: datetime,
        end_time: datetime | None,
        expires_at: datetime | None,
        status: str,
        priority: int | None,
        confidence: float | None,
        visible: bool,
        pinned: bool,
        source_kind: str,
        payload: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> StoredChatAnnotation:
        ...

    def list_chat_annotations(
        self,
        *,
        session_id: str,
        message_id: str | None = None,
        status: str | None = None,
        visible_only: bool = False,
        limit: int = 500,
    ) -> list[StoredChatAnnotation]:
        ...

    def save_chat_plan_card(
        self,
        *,
        plan_id: str,
        session_id: str,
        message_id: str,
        title: str,
        side: str,
        entry_type: str | None,
        entry_price: float | None,
        entry_price_low: float | None,
        entry_price_high: float | None,
        stop_price: float | None,
        take_profits: list[dict[str, Any]],
        invalidations: list[str],
        time_validity: str | None,
        risk_reward: float | None,
        confidence: float | None,
        priority: int | None,
        status: str,
        source_kind: str,
        notes: str,
        payload: dict[str, Any],
        created_at: datetime,
        updated_at: datetime,
    ) -> StoredChatPlanCard:
        ...

    def list_chat_plan_cards(
        self,
        *,
        session_id: str,
        message_id: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[StoredChatPlanCard]:
        ...


class SQLiteAnalysisRepository:
    """SQLite persistence for observed facts, derived analysis, liquidity memory, and replay workbench chat state."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
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
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestions_symbol_time ON ingestions (instrument_symbol, stored_at)")
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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_time ON chat_messages (session_id, created_at)")
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

    def list_ingestions(self, *, ingestion_kind: str | None = None, instrument_symbol: str | None = None, source_snapshot_id: str | None = None, limit: int = 100) -> list[StoredIngestion]:
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

    def save_chat_message(self, *, message_id: str, session_id: str, parent_message_id: str | None, role: str, content: str, status: str, reply_title: str | None, stream_buffer: str, model: str | None, annotations: list[str], plan_cards: list[str], mounted_to_chart: bool, mounted_object_ids: list[str], is_key_conclusion: bool, request_payload: dict[str, Any], response_payload: dict[str, Any], created_at: datetime, updated_at: datetime) -> StoredChatMessage:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (
                    message_id, session_id, parent_message_id, role, content, status, reply_title, stream_buffer, model,
                    annotations_json, plan_cards_json, mounted_to_chart, mounted_object_ids_json, is_key_conclusion,
                    request_payload_json, response_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id, session_id, parent_message_id, role, content, status, reply_title, stream_buffer, model,
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

    def list_chat_messages(self, *, session_id: str, limit: int = 200) -> list[StoredChatMessage]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?", (session_id, limit)).fetchall()
        return [self._row_to_chat_message(row) for row in rows]

    def update_chat_message(self, message_id: str, **updates: Any) -> StoredChatMessage | None:
        if not updates:
            return self.get_chat_message(message_id)
        mapping = {
            "content": "content",
            "status": "status",
            "reply_title": "reply_title",
            "stream_buffer": "stream_buffer",
            "model": "model",
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

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

    @staticmethod
    def _serialize_json(value: dict[str, Any]) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _serialize_any_json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=True)

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
        """Insert or update a single chart candle.  Raises on validation error."""
        from atas_market_structure.models._replay import ChartCandle as ChartCandleModel

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chart_candles
                    (symbol, timeframe, started_at, ended_at,
                     open, high, low, close, volume, tick_volume, delta, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, started_at) DO UPDATE SET
                    high        = MAX(excluded.high,  chart_candles.high),
                    low         = MIN(excluded.low,   chart_candles.low),
                    close       = excluded.close,
                    volume      = chart_candles.volume    + (excluded.volume    - MAX(chart_candles.open, chart_candles.high, chart_candles.low, chart_candles.close)),
                    tick_volume = chart_candles.tick_volume + excluded.tick_volume,
                    delta       = chart_candles.delta       + excluded.delta,
                    updated_at  = excluded.updated_at
                """,
                (
                    candle.symbol,
                    candle.timeframe.value,
                    self._serialize_datetime(candle.started_at),
                    self._serialize_datetime(candle.ended_at),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    candle.tick_volume,
                    candle.delta,
                    self._serialize_datetime(candle.updated_at),
                ),
            )
            conn.commit()
        return candle

    def upsert_chart_candles(self, candles: list["ChartCandle"]) -> int:
        """Bulk upsert a list of chart candles. Returns number of rows written."""
        if not candles:
            return 0
        rows = [
            (
                c.symbol,
                c.timeframe.value,
                self._serialize_datetime(c.started_at),
                self._serialize_datetime(c.ended_at),
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.tick_volume,
                c.delta,
                self._serialize_datetime(c.updated_at),
            )
            for c in candles
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO chart_candles
                    (symbol, timeframe, started_at, ended_at,
                     open, high, low, close, volume, tick_volume, delta, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, started_at) DO UPDATE SET
                    high        = MAX(excluded.high,  chart_candles.high),
                    low         = MIN(excluded.low,   chart_candles.low),
                    close       = excluded.close,
                    volume      = chart_candles.volume      + excluded.volume,
                    tick_volume = chart_candles.tick_volume + excluded.tick_volume,
                    delta       = chart_candles.delta       + excluded.delta,
                    updated_at  = excluded.updated_at
                """,
                rows,
            )
            conn.commit()
        return len(candles)

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
                       open, high, low, close, volume, tick_volume, delta, updated_at
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
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                tick_volume=row["tick_volume"],
                delta=row["delta"],
                updated_at=self._parse_datetime(row["updated_at"]),
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
