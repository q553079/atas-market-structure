from __future__ import annotations

import sqlite3
from typing import Any

from atas_market_structure.repository_records import StoredEventOutcomeLedger


class SQLiteWorkbenchEventOutcomeRepository:
    """Focused SQLite persistence for replay-workbench event outcome ledger rows."""

    def __init__(self, owner) -> None:
        self._owner = owner

    def initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_event_outcomes (
                outcome_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL,
                source_message_id TEXT,
                source_prompt_trace_id TEXT,
                analysis_preset TEXT,
                model_name TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                born_at TEXT NOT NULL,
                observed_price REAL,
                target_rule_json TEXT NOT NULL,
                invalidation_rule_json TEXT NOT NULL,
                evaluation_window_start TEXT NOT NULL,
                evaluation_window_end TEXT NOT NULL,
                expiry_policy_json TEXT NOT NULL,
                realized_outcome TEXT,
                outcome_label TEXT NOT NULL,
                mfe REAL,
                mae REAL,
                hit_target INTEGER NOT NULL,
                hit_stop INTEGER NOT NULL,
                timed_out INTEGER NOT NULL,
                inconclusive INTEGER NOT NULL,
                evaluated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES chat_event_candidates(event_id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
            """,
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_outcomes_session_evaluated "
            "ON chat_event_outcomes (session_id, evaluated_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_outcomes_kind_outcome "
            "ON chat_event_outcomes (event_kind, realized_outcome)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_event_outcomes_prompt_trace "
            "ON chat_event_outcomes (source_prompt_trace_id)"
        )

    def save_event_outcome(self, **kwargs: Any) -> StoredEventOutcomeLedger:
        with self._owner._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO chat_event_outcomes (
                    outcome_id, event_id, session_id, source_message_id, source_prompt_trace_id,
                    analysis_preset, model_name, symbol, timeframe, event_kind, born_at,
                    observed_price, target_rule_json, invalidation_rule_json,
                    evaluation_window_start, evaluation_window_end, expiry_policy_json,
                    realized_outcome, outcome_label, mfe, mae, hit_target, hit_stop,
                    timed_out, inconclusive, evaluated_at, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._row_values(kwargs),
            )
            connection.commit()
        stored = self.get_event_outcome(kwargs["outcome_id"])
        if stored is None:  # pragma: no cover
            raise RuntimeError(f"event outcome '{kwargs['outcome_id']}' was not persisted")
        return stored

    def get_event_outcome(self, outcome_id: str) -> StoredEventOutcomeLedger | None:
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_event_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()
        return self._row_to_event_outcome(row) if row is not None else None

    def get_event_outcome_by_event(self, event_id: str) -> StoredEventOutcomeLedger | None:
        with self._owner._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_event_outcomes WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_event_outcome(row) if row is not None else None

    def list_event_outcomes(
        self,
        *,
        session_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        event_id: str | None = None,
        event_kind: str | None = None,
        realized_outcome: str | None = None,
        limit: int = 500,
    ) -> list[StoredEventOutcomeLedger]:
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
        if event_kind is not None:
            clauses.append("event_kind = ?")
            parameters.append(event_kind)
        if realized_outcome is not None:
            clauses.append("realized_outcome = ?")
            parameters.append(realized_outcome)
        parameters.append(limit)
        with self._owner._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chat_event_outcomes WHERE {' AND '.join(clauses)} ORDER BY born_at DESC LIMIT ?",
                tuple(parameters),
            ).fetchall()
        return [self._row_to_event_outcome(row) for row in rows]

    def _row_values(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["outcome_id"],
            item["event_id"],
            item["session_id"],
            item.get("source_message_id"),
            item.get("source_prompt_trace_id"),
            item.get("analysis_preset"),
            item.get("model_name"),
            item["symbol"],
            item["timeframe"],
            item["event_kind"],
            self._owner._serialize_datetime(item["born_at"]),
            item.get("observed_price"),
            self._owner._serialize_json(item.get("target_rule", {})),
            self._owner._serialize_json(item.get("invalidation_rule", {})),
            self._owner._serialize_datetime(item["evaluation_window_start"]),
            self._owner._serialize_datetime(item["evaluation_window_end"]),
            self._owner._serialize_json(item.get("expiry_policy", {})),
            item.get("realized_outcome"),
            item.get("outcome_label", "pending"),
            item.get("mfe"),
            item.get("mae"),
            int(bool(item.get("hit_target", False))),
            int(bool(item.get("hit_stop", False))),
            int(bool(item.get("timed_out", False))),
            int(bool(item.get("inconclusive", False))),
            self._owner._serialize_datetime(item["evaluated_at"]),
            self._owner._serialize_json(item.get("metadata", {})),
            self._owner._serialize_datetime(item["created_at"]),
            self._owner._serialize_datetime(item["updated_at"]),
        )

    def _row_to_event_outcome(self, row: sqlite3.Row) -> StoredEventOutcomeLedger:
        return StoredEventOutcomeLedger(
            outcome_id=row["outcome_id"],
            event_id=row["event_id"],
            session_id=row["session_id"],
            source_message_id=row["source_message_id"],
            source_prompt_trace_id=row["source_prompt_trace_id"],
            analysis_preset=row["analysis_preset"],
            model_name=row["model_name"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            event_kind=row["event_kind"],
            born_at=self._owner._parse_datetime(row["born_at"]),
            observed_price=row["observed_price"],
            target_rule=self._owner._parse_json(row["target_rule_json"]),
            invalidation_rule=self._owner._parse_json(row["invalidation_rule_json"]),
            evaluation_window_start=self._owner._parse_datetime(row["evaluation_window_start"]),
            evaluation_window_end=self._owner._parse_datetime(row["evaluation_window_end"]),
            expiry_policy=self._owner._parse_json(row["expiry_policy_json"]),
            realized_outcome=row["realized_outcome"],
            outcome_label=row["outcome_label"],
            mfe=row["mfe"],
            mae=row["mae"],
            hit_target=bool(row["hit_target"]),
            hit_stop=bool(row["hit_stop"]),
            timed_out=bool(row["timed_out"]),
            inconclusive=bool(row["inconclusive"]),
            evaluated_at=self._owner._parse_datetime(row["evaluated_at"]),
            metadata=self._owner._parse_json(row["metadata_json"]),
            created_at=self._owner._parse_datetime(row["created_at"]),
            updated_at=self._owner._parse_datetime(row["updated_at"]),
        )
