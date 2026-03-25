from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any

from atas_market_structure.repository_records import StoredPromptTrace


class SQLiteWorkbenchPromptTraceRepository:
    """Focused SQLite persistence for replay-workbench prompt-trace records."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_prompt_traces (
                prompt_trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                analysis_type TEXT,
                analysis_range TEXT,
                analysis_style TEXT,
                selected_block_ids_json TEXT NOT NULL,
                pinned_block_ids_json TEXT NOT NULL,
                attached_event_ids_json TEXT NOT NULL,
                prompt_block_summaries_json TEXT NOT NULL,
                bar_window_summary_json TEXT NOT NULL,
                manual_selection_summary_json TEXT NOT NULL,
                memory_summary_json TEXT NOT NULL,
                final_system_prompt TEXT NOT NULL,
                final_user_prompt TEXT NOT NULL,
                model_name TEXT,
                model_input_hash TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id),
                FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
            )
            """,
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_prompt_traces_session_created "
            "ON chat_prompt_traces (session_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_prompt_traces_message "
            "ON chat_prompt_traces (message_id)"
        )

    def save_prompt_trace(self, **kwargs: Any) -> StoredPromptTrace:
        with self._owner._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_prompt_traces (
                    prompt_trace_id, session_id, message_id, symbol, timeframe,
                    analysis_type, analysis_range, analysis_style,
                    selected_block_ids_json, pinned_block_ids_json, attached_event_ids_json,
                    prompt_block_summaries_json, bar_window_summary_json, manual_selection_summary_json,
                    memory_summary_json, final_system_prompt, final_user_prompt, model_name,
                    model_input_hash, snapshot_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._row_values(kwargs),
            )
            connection.commit()
        stored = self.get_prompt_trace(kwargs["prompt_trace_id"])
        if stored is None:  # pragma: no cover
            raise RuntimeError(f"prompt trace '{kwargs['prompt_trace_id']}' was not persisted")
        return stored

    def get_prompt_trace(self, prompt_trace_id: str) -> StoredPromptTrace | None:
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_prompt_traces WHERE prompt_trace_id = ?",
                (prompt_trace_id,),
            ).fetchone()
        return self._row_to_prompt_trace(row) if row is not None else None

    def list_prompt_traces(
        self,
        *,
        session_id: str | None = None,
        message_id: str | None = None,
        limit: int = 200,
    ) -> list[StoredPromptTrace]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(session_id)
        if message_id is not None:
            clauses.append("message_id = ?")
            parameters.append(message_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._owner._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_prompt_traces {where_clause} ORDER BY created_at DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_prompt_trace(row) for row in rows]

    def update_prompt_trace(self, prompt_trace_id: str, **updates: Any) -> StoredPromptTrace | None:
        if not updates:
            return self.get_prompt_trace(prompt_trace_id)
        mapping = {
            "attached_event_ids": ("attached_event_ids_json", self._owner._serialize_any_json),
            "prompt_block_summaries": ("prompt_block_summaries_json", self._owner._serialize_any_json),
            "bar_window_summary": ("bar_window_summary_json", self._owner._serialize_json),
            "manual_selection_summary": ("manual_selection_summary_json", self._owner._serialize_json),
            "memory_summary": ("memory_summary_json", self._owner._serialize_json),
            "final_system_prompt": "final_system_prompt",
            "final_user_prompt": "final_user_prompt",
            "model_name": "model_name",
            "snapshot": ("snapshot_json", self._owner._serialize_json),
            "metadata": ("metadata_json", self._owner._serialize_json),
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
            return self.get_prompt_trace(prompt_trace_id)
        parameters.append(prompt_trace_id)
        with self._owner._connect() as connection:
            connection.execute(
                f"UPDATE chat_prompt_traces SET {', '.join(clauses)} WHERE prompt_trace_id = ?",
                tuple(parameters),
            )
            connection.commit()
        return self.get_prompt_trace(prompt_trace_id)

    def get_prompt_trace_by_message(self, message_id: str) -> StoredPromptTrace | None:
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_prompt_traces WHERE message_id = ? ORDER BY created_at DESC LIMIT 1",
                (message_id,),
            ).fetchone()
        return self._row_to_prompt_trace(row) if row is not None else None

    def _row_values(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["prompt_trace_id"],
            item["session_id"],
            item["message_id"],
            item["symbol"],
            item["timeframe"],
            item.get("analysis_type"),
            item.get("analysis_range"),
            item.get("analysis_style"),
            self._owner._serialize_any_json(item.get("selected_block_ids", [])),
            self._owner._serialize_any_json(item.get("pinned_block_ids", [])),
            self._owner._serialize_any_json(item.get("attached_event_ids", [])),
            self._owner._serialize_any_json(item.get("prompt_block_summaries", [])),
            self._owner._serialize_json(item.get("bar_window_summary", {})),
            self._owner._serialize_json(item.get("manual_selection_summary", {})),
            self._owner._serialize_json(item.get("memory_summary", {})),
            item.get("final_system_prompt", ""),
            item.get("final_user_prompt", ""),
            item.get("model_name"),
            item["model_input_hash"],
            self._owner._serialize_json(item.get("snapshot", {})),
            self._owner._serialize_json(item.get("metadata", {})),
            self._owner._serialize_datetime(item["created_at"]),
            self._owner._serialize_datetime(item["updated_at"]),
        )

    def _row_to_prompt_trace(self, row: sqlite3.Row) -> StoredPromptTrace:
        return StoredPromptTrace(
            prompt_trace_id=row["prompt_trace_id"],
            session_id=row["session_id"],
            message_id=row["message_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            analysis_type=row["analysis_type"],
            analysis_range=row["analysis_range"],
            analysis_style=row["analysis_style"],
            selected_block_ids=self._owner._parse_any_json(row["selected_block_ids_json"]),
            pinned_block_ids=self._owner._parse_any_json(row["pinned_block_ids_json"]),
            attached_event_ids=self._owner._parse_any_json(row["attached_event_ids_json"]),
            prompt_block_summaries=self._owner._parse_any_json(row["prompt_block_summaries_json"]),
            bar_window_summary=self._owner._parse_json(row["bar_window_summary_json"]),
            manual_selection_summary=self._owner._parse_json(row["manual_selection_summary_json"]),
            memory_summary=self._owner._parse_json(row["memory_summary_json"]),
            final_system_prompt=row["final_system_prompt"],
            final_user_prompt=row["final_user_prompt"],
            model_name=row["model_name"],
            model_input_hash=row["model_input_hash"],
            snapshot=self._owner._parse_json(row["snapshot_json"]),
            metadata=self._owner._parse_json(row["metadata_json"]),
            created_at=self._owner._parse_datetime(row["created_at"]),
            updated_at=self._owner._parse_datetime(row["updated_at"]),
        )
