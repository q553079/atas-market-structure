from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any

from atas_market_structure.repository_records import (
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventStreamEntry,
)


class SQLiteWorkbenchEventRepository:
    """Focused SQLite persistence for replay-workbench event backbone objects."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_event_candidates (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                candidate_kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                anchor_start_ts TEXT,
                anchor_end_ts TEXT,
                price_lower REAL,
                price_upper REAL,
                price_ref REAL,
                side_hint TEXT,
                confidence REAL,
                evidence_refs_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_message_id TEXT,
                source_prompt_trace_id TEXT,
                lifecycle_state TEXT NOT NULL,
                invalidation_rule_json TEXT NOT NULL,
                evaluation_window_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                dedup_key TEXT,
                promoted_projection_type TEXT,
                promoted_projection_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
            """,
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_candidates_session_updated "
            "ON chat_event_candidates (session_id, updated_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_candidates_message "
            "ON chat_event_candidates (source_message_id, session_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_event_stream_entries (
                stream_entry_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                candidate_kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                anchor_start_ts TEXT,
                anchor_end_ts TEXT,
                price_lower REAL,
                price_upper REAL,
                price_ref REAL,
                side_hint TEXT,
                confidence REAL,
                evidence_refs_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_message_id TEXT,
                source_prompt_trace_id TEXT,
                lifecycle_state TEXT NOT NULL,
                invalidation_rule_json TEXT NOT NULL,
                evaluation_window_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                stream_action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES chat_event_candidates(event_id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
            """,
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_stream_session_created "
            "ON chat_event_stream_entries (session_id, created_at DESC)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_event_memory_entries (
                memory_entry_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                candidate_kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                anchor_start_ts TEXT,
                anchor_end_ts TEXT,
                price_lower REAL,
                price_upper REAL,
                price_ref REAL,
                side_hint TEXT,
                confidence REAL,
                evidence_refs_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_message_id TEXT,
                source_prompt_trace_id TEXT,
                lifecycle_state TEXT NOT NULL,
                invalidation_rule_json TEXT NOT NULL,
                evaluation_window_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                memory_bucket TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES chat_event_candidates(event_id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
            """,
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_memory_session_updated "
            "ON chat_event_memory_entries (session_id, updated_at DESC)"
        )

    def save_event_candidate(self, **kwargs: Any) -> StoredEventCandidate:
        with self._owner._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_event_candidates (
                    event_id, session_id, candidate_kind, title, summary, symbol, timeframe,
                    anchor_start_ts, anchor_end_ts, price_lower, price_upper, price_ref, side_hint,
                    confidence, evidence_refs_json, source_type, source_message_id, source_prompt_trace_id,
                    lifecycle_state, invalidation_rule_json, evaluation_window_json, metadata_json, dedup_key,
                    promoted_projection_type, promoted_projection_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._candidate_row(kwargs),
            )
            connection.commit()
        stored = self.get_event_candidate(kwargs["event_id"])
        if stored is None:  # pragma: no cover
            raise RuntimeError(f"event candidate '{kwargs['event_id']}' was not persisted")
        return stored

    def list_event_candidates_by_session(
        self,
        *,
        session_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        source_message_id: str | None = None,
        lifecycle_state: str | None = None,
        candidate_kind: str | None = None,
        limit: int = 500,
    ) -> list[StoredEventCandidate]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if symbol is not None:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if timeframe is not None:
            clauses.append("timeframe = ?")
            parameters.append(timeframe)
        if source_message_id is not None:
            clauses.append("source_message_id = ?")
            parameters.append(source_message_id)
        if lifecycle_state is not None:
            clauses.append("lifecycle_state = ?")
            parameters.append(lifecycle_state)
        if candidate_kind is not None:
            clauses.append("candidate_kind = ?")
            parameters.append(candidate_kind)
        parameters.append(limit)
        with self._owner._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_event_candidates WHERE {' AND '.join(clauses)} ORDER BY created_at ASC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_event_candidate(row) for row in rows]

    def get_event_candidate(self, event_id: str) -> StoredEventCandidate | None:
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_event_candidates WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_event_candidate(row) if row is not None else None

    def patch_event_candidate(self, event_id: str, **updates: Any) -> StoredEventCandidate | None:
        if not updates:
            return self.get_event_candidate(event_id)
        mapping = {
            "title": "title",
            "summary": "summary",
            "side_hint": "side_hint",
            "confidence": "confidence",
            "invalidation_rule": ("invalidation_rule_json", self._owner._serialize_json),
            "evaluation_window": ("evaluation_window_json", self._owner._serialize_json),
            "metadata": ("metadata_json", self._owner._serialize_json),
            "lifecycle_state": "lifecycle_state",
            "promoted_projection_type": "promoted_projection_type",
            "promoted_projection_id": "promoted_projection_id",
            "updated_at": ("updated_at", self._owner._serialize_datetime),
        }
        clauses: list[str] = []
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
            return self.get_event_candidate(event_id)
        parameters.append(event_id)
        with self._owner._connect() as connection:
            connection.execute(
                f"UPDATE chat_event_candidates SET {', '.join(clauses)} WHERE event_id = ?",
                tuple(parameters),
            )
            connection.commit()
        return self.get_event_candidate(event_id)

    def transition_event_candidate_state(
        self,
        event_id: str,
        *,
        lifecycle_state: str,
        updated_at: datetime,
        metadata: dict[str, Any] | None = None,
        promoted_projection_type: str | None = None,
        promoted_projection_id: str | None = None,
    ) -> StoredEventCandidate | None:
        current = self.get_event_candidate(event_id)
        if current is None:
            return None
        merged_metadata = dict(current.metadata)
        if metadata:
            merged_metadata.update(metadata)
        return self.patch_event_candidate(
            event_id,
            lifecycle_state=lifecycle_state,
            metadata=merged_metadata,
            promoted_projection_type=promoted_projection_type,
            promoted_projection_id=promoted_projection_id,
            updated_at=updated_at,
        )

    def save_event_stream_entry(self, **kwargs: Any) -> StoredEventStreamEntry:
        with self._owner._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_event_stream_entries (
                    stream_entry_id, event_id, session_id, candidate_kind, title, summary, symbol, timeframe,
                    anchor_start_ts, anchor_end_ts, price_lower, price_upper, price_ref, side_hint,
                    confidence, evidence_refs_json, source_type, source_message_id, source_prompt_trace_id,
                    lifecycle_state, invalidation_rule_json, evaluation_window_json, metadata_json,
                    stream_action, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._stream_row(kwargs),
            )
            connection.commit()
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_event_stream_entries WHERE stream_entry_id = ?",
                (kwargs["stream_entry_id"],),
            ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(f"event stream entry '{kwargs['stream_entry_id']}' was not persisted")
        return self._row_to_event_stream_entry(row)

    def list_event_stream_entries(
        self,
        *,
        session_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        source_message_id: str | None = None,
        event_id: str | None = None,
        limit: int = 1000,
    ) -> list[StoredEventStreamEntry]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if symbol is not None:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if timeframe is not None:
            clauses.append("timeframe = ?")
            parameters.append(timeframe)
        if source_message_id is not None:
            clauses.append("source_message_id = ?")
            parameters.append(source_message_id)
        if event_id is not None:
            clauses.append("event_id = ?")
            parameters.append(event_id)
        parameters.append(limit)
        with self._owner._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_event_stream_entries WHERE {' AND '.join(clauses)} ORDER BY created_at ASC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_event_stream_entry(row) for row in rows]

    def save_event_memory_entry(self, **kwargs: Any) -> StoredEventMemoryEntry:
        with self._owner._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_event_memory_entries (
                    memory_entry_id, event_id, session_id, candidate_kind, title, summary, symbol, timeframe,
                    anchor_start_ts, anchor_end_ts, price_lower, price_upper, price_ref, side_hint,
                    confidence, evidence_refs_json, source_type, source_message_id, source_prompt_trace_id,
                    lifecycle_state, invalidation_rule_json, evaluation_window_json, metadata_json,
                    memory_bucket, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._memory_row(kwargs),
            )
            connection.commit()
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_event_memory_entries WHERE memory_entry_id = ?",
                (kwargs["memory_entry_id"],),
            ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError(f"event memory entry '{kwargs['memory_entry_id']}' was not persisted")
        return self._row_to_event_memory_entry(row)

    def list_event_memory_entries(
        self,
        *,
        session_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        event_id: str | None = None,
        limit: int = 500,
    ) -> list[StoredEventMemoryEntry]:
        clauses = ["session_id = ?"]
        parameters: list[Any] = [session_id]
        if symbol is not None:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if timeframe is not None:
            clauses.append("timeframe = ?")
            parameters.append(timeframe)
        if event_id is not None:
            clauses.append("event_id = ?")
            parameters.append(event_id)
        parameters.append(limit)
        with self._owner._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_event_memory_entries WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_event_memory_entry(row) for row in rows]

    def _candidate_row(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["event_id"],
            item["session_id"],
            item["candidate_kind"],
            item["title"],
            item.get("summary", ""),
            item["symbol"],
            item["timeframe"],
            self._owner._serialize_datetime_optional(item.get("anchor_start_ts")),
            self._owner._serialize_datetime_optional(item.get("anchor_end_ts")),
            item.get("price_lower"),
            item.get("price_upper"),
            item.get("price_ref"),
            item.get("side_hint"),
            item.get("confidence"),
            self._owner._serialize_any_json(item.get("evidence_refs", [])),
            item["source_type"],
            item.get("source_message_id"),
            item.get("source_prompt_trace_id"),
            item["lifecycle_state"],
            self._owner._serialize_json(item.get("invalidation_rule", {})),
            self._owner._serialize_json(item.get("evaluation_window", {})),
            self._owner._serialize_json(item.get("metadata", {})),
            item.get("dedup_key"),
            item.get("promoted_projection_type"),
            item.get("promoted_projection_id"),
            self._owner._serialize_datetime(item["created_at"]),
            self._owner._serialize_datetime(item["updated_at"]),
        )

    def _stream_row(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["stream_entry_id"],
            item["event_id"],
            item["session_id"],
            item["candidate_kind"],
            item["title"],
            item.get("summary", ""),
            item["symbol"],
            item["timeframe"],
            self._owner._serialize_datetime_optional(item.get("anchor_start_ts")),
            self._owner._serialize_datetime_optional(item.get("anchor_end_ts")),
            item.get("price_lower"),
            item.get("price_upper"),
            item.get("price_ref"),
            item.get("side_hint"),
            item.get("confidence"),
            self._owner._serialize_any_json(item.get("evidence_refs", [])),
            item["source_type"],
            item.get("source_message_id"),
            item.get("source_prompt_trace_id"),
            item["lifecycle_state"],
            self._owner._serialize_json(item.get("invalidation_rule", {})),
            self._owner._serialize_json(item.get("evaluation_window", {})),
            self._owner._serialize_json(item.get("metadata", {})),
            item["stream_action"],
            self._owner._serialize_datetime(item["created_at"]),
            self._owner._serialize_datetime(item["updated_at"]),
        )

    def _memory_row(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["memory_entry_id"],
            item["event_id"],
            item["session_id"],
            item["candidate_kind"],
            item["title"],
            item.get("summary", ""),
            item["symbol"],
            item["timeframe"],
            self._owner._serialize_datetime_optional(item.get("anchor_start_ts")),
            self._owner._serialize_datetime_optional(item.get("anchor_end_ts")),
            item.get("price_lower"),
            item.get("price_upper"),
            item.get("price_ref"),
            item.get("side_hint"),
            item.get("confidence"),
            self._owner._serialize_any_json(item.get("evidence_refs", [])),
            item["source_type"],
            item.get("source_message_id"),
            item.get("source_prompt_trace_id"),
            item["lifecycle_state"],
            self._owner._serialize_json(item.get("invalidation_rule", {})),
            self._owner._serialize_json(item.get("evaluation_window", {})),
            self._owner._serialize_json(item.get("metadata", {})),
            item["memory_bucket"],
            self._owner._serialize_datetime(item["created_at"]),
            self._owner._serialize_datetime(item["updated_at"]),
        )

    def _row_to_event_candidate(self, row: sqlite3.Row) -> StoredEventCandidate:
        return StoredEventCandidate(
            event_id=row["event_id"],
            session_id=row["session_id"],
            candidate_kind=row["candidate_kind"],
            title=row["title"],
            summary=row["summary"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            anchor_start_ts=self._owner._parse_datetime_optional(row["anchor_start_ts"]),
            anchor_end_ts=self._owner._parse_datetime_optional(row["anchor_end_ts"]),
            price_lower=row["price_lower"],
            price_upper=row["price_upper"],
            price_ref=row["price_ref"],
            side_hint=row["side_hint"],
            confidence=row["confidence"],
            evidence_refs=self._owner._parse_any_json(row["evidence_refs_json"]),
            source_type=row["source_type"],
            source_message_id=row["source_message_id"],
            source_prompt_trace_id=row["source_prompt_trace_id"],
            lifecycle_state=row["lifecycle_state"],
            invalidation_rule=self._owner._parse_json(row["invalidation_rule_json"]),
            evaluation_window=self._owner._parse_json(row["evaluation_window_json"]),
            metadata=self._owner._parse_json(row["metadata_json"]),
            dedup_key=row["dedup_key"],
            promoted_projection_type=row["promoted_projection_type"],
            promoted_projection_id=row["promoted_projection_id"],
            created_at=self._owner._parse_datetime(row["created_at"]),
            updated_at=self._owner._parse_datetime(row["updated_at"]),
        )

    def _row_to_event_stream_entry(self, row: sqlite3.Row) -> StoredEventStreamEntry:
        return StoredEventStreamEntry(
            stream_entry_id=row["stream_entry_id"],
            event_id=row["event_id"],
            session_id=row["session_id"],
            candidate_kind=row["candidate_kind"],
            title=row["title"],
            summary=row["summary"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            anchor_start_ts=self._owner._parse_datetime_optional(row["anchor_start_ts"]),
            anchor_end_ts=self._owner._parse_datetime_optional(row["anchor_end_ts"]),
            price_lower=row["price_lower"],
            price_upper=row["price_upper"],
            price_ref=row["price_ref"],
            side_hint=row["side_hint"],
            confidence=row["confidence"],
            evidence_refs=self._owner._parse_any_json(row["evidence_refs_json"]),
            source_type=row["source_type"],
            source_message_id=row["source_message_id"],
            source_prompt_trace_id=row["source_prompt_trace_id"],
            lifecycle_state=row["lifecycle_state"],
            invalidation_rule=self._owner._parse_json(row["invalidation_rule_json"]),
            evaluation_window=self._owner._parse_json(row["evaluation_window_json"]),
            metadata=self._owner._parse_json(row["metadata_json"]),
            stream_action=row["stream_action"],
            created_at=self._owner._parse_datetime(row["created_at"]),
            updated_at=self._owner._parse_datetime(row["updated_at"]),
        )

    def _row_to_event_memory_entry(self, row: sqlite3.Row) -> StoredEventMemoryEntry:
        return StoredEventMemoryEntry(
            memory_entry_id=row["memory_entry_id"],
            event_id=row["event_id"],
            session_id=row["session_id"],
            candidate_kind=row["candidate_kind"],
            title=row["title"],
            summary=row["summary"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            anchor_start_ts=self._owner._parse_datetime_optional(row["anchor_start_ts"]),
            anchor_end_ts=self._owner._parse_datetime_optional(row["anchor_end_ts"]),
            price_lower=row["price_lower"],
            price_upper=row["price_upper"],
            price_ref=row["price_ref"],
            side_hint=row["side_hint"],
            confidence=row["confidence"],
            evidence_refs=self._owner._parse_any_json(row["evidence_refs_json"]),
            source_type=row["source_type"],
            source_message_id=row["source_message_id"],
            source_prompt_trace_id=row["source_prompt_trace_id"],
            lifecycle_state=row["lifecycle_state"],
            invalidation_rule=self._owner._parse_json(row["invalidation_rule_json"]),
            evaluation_window=self._owner._parse_json(row["evaluation_window_json"]),
            metadata=self._owner._parse_json(row["metadata_json"]),
            memory_bucket=row["memory_bucket"],
            created_at=self._owner._parse_datetime(row["created_at"]),
            updated_at=self._owner._parse_datetime(row["updated_at"]),
        )
