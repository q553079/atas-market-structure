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


class SQLiteAnalysisRepository:
    """SQLite persistence for observed facts, derived analysis, and 3-day liquidity memory."""

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
                CREATE INDEX IF NOT EXISTS idx_ingestions_symbol_time
                ON ingestions (instrument_symbol, stored_at)
                """,
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analyses_ingestion
                ON analyses (ingestion_id)
                """,
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_liquidity_memories_symbol_expiry
                ON liquidity_memories (instrument_symbol, expires_at, updated_at)
                """,
            )
            connection.commit()

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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestions (
                    ingestion_id,
                    ingestion_kind,
                    source_snapshot_id,
                    instrument_symbol,
                    observed_payload_json,
                    stored_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ingestion_id,
                    ingestion_kind,
                    source_snapshot_id,
                    instrument_symbol,
                    self._serialize_json(observed_payload),
                    self._serialize_datetime(stored_at),
                ),
            )
            connection.commit()
        return StoredIngestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=observed_payload,
            stored_at=stored_at,
        )

    def save_analysis(
        self,
        *,
        analysis_id: str,
        ingestion_id: str,
        route_key: str,
        analysis_payload: dict[str, Any],
        stored_at: datetime,
    ) -> StoredAnalysis:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analyses (
                    analysis_id,
                    ingestion_id,
                    route_key,
                    analysis_payload_json,
                    stored_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    ingestion_id,
                    route_key,
                    self._serialize_json(analysis_payload),
                    self._serialize_datetime(stored_at),
                ),
            )
            connection.commit()
        return StoredAnalysis(
            analysis_id=analysis_id,
            ingestion_id=ingestion_id,
            route_key=route_key,
            analysis_payload=analysis_payload,
            stored_at=stored_at,
        )

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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO liquidity_memories (
                    memory_id,
                    track_key,
                    instrument_symbol,
                    coverage_state,
                    observed_track_json,
                    derived_summary_json,
                    expires_at,
                    updated_at
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
                (
                    memory_id,
                    track_key,
                    instrument_symbol,
                    coverage_state,
                    self._serialize_json(observed_track),
                    self._serialize_json(derived_summary),
                    self._serialize_datetime(expires_at),
                    self._serialize_datetime(updated_at),
                ),
            )
            connection.commit()
        return StoredLiquidityMemory(
            memory_id=memory_id,
            track_key=track_key,
            instrument_symbol=instrument_symbol,
            coverage_state=coverage_state,
            observed_track=observed_track,
            derived_summary=derived_summary,
            expires_at=expires_at,
            updated_at=updated_at,
        )

    def get_ingestion(self, ingestion_id: str) -> StoredIngestion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol,
                       observed_payload_json, stored_at
                FROM ingestions
                WHERE ingestion_id = ?
                """,
                (ingestion_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredIngestion(
            ingestion_id=row["ingestion_id"],
            ingestion_kind=row["ingestion_kind"],
            source_snapshot_id=row["source_snapshot_id"],
            instrument_symbol=row["instrument_symbol"],
            observed_payload=self._parse_json(row["observed_payload_json"]),
            stored_at=self._parse_datetime(row["stored_at"]),
        )

    def get_analysis(self, analysis_id: str) -> StoredAnalysis | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT analysis_id, ingestion_id, route_key, analysis_payload_json, stored_at
                FROM analyses
                WHERE analysis_id = ?
                """,
                (analysis_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredAnalysis(
            analysis_id=row["analysis_id"],
            ingestion_id=row["ingestion_id"],
            route_key=row["route_key"],
            analysis_payload=self._parse_json(row["analysis_payload_json"]),
            stored_at=self._parse_datetime(row["stored_at"]),
        )

    def update_ingestion_observed_payload(
        self,
        *,
        ingestion_id: str,
        observed_payload: dict[str, Any],
    ) -> StoredIngestion | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestions
                SET observed_payload_json = ?
                WHERE ingestion_id = ?
                """,
                (
                    self._serialize_json(observed_payload),
                    ingestion_id,
                ),
            )
            connection.commit()
        return self.get_ingestion(ingestion_id)

    def list_ingestions(
        self,
        *,
        ingestion_kind: str | None = None,
        instrument_symbol: str | None = None,
        limit: int = 100,
    ) -> list[StoredIngestion]:
        clauses = []
        parameters: list[Any] = []
        if ingestion_kind is not None:
            clauses.append("ingestion_kind = ?")
            parameters.append(ingestion_kind)
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol,
                   observed_payload_json, stored_at
            FROM ingestions
            {where_clause}
            ORDER BY stored_at DESC
            LIMIT ?
        """
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [
            StoredIngestion(
                ingestion_id=row["ingestion_id"],
                ingestion_kind=row["ingestion_kind"],
                source_snapshot_id=row["source_snapshot_id"],
                instrument_symbol=row["instrument_symbol"],
                observed_payload=self._parse_json(row["observed_payload_json"]),
                stored_at=self._parse_datetime(row["stored_at"]),
            )
            for row in rows
        ]

    def purge_ingestions(
        self,
        *,
        ingestion_kinds: list[str],
        instrument_symbol: str | None,
        cutoff: datetime,
    ) -> int:
        if not ingestion_kinds:
            return 0

        clauses = [
            f"ingestion_kind IN ({','.join('?' for _ in ingestion_kinds)})",
            "stored_at < ?",
        ]
        parameters: list[Any] = [*ingestion_kinds, self._serialize_datetime(cutoff)]
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                DELETE FROM ingestions
                WHERE {' AND '.join(clauses)}
                """,
                tuple(parameters),
            )
            connection.commit()
        return cursor.rowcount

    def get_liquidity_memory_by_track_key(self, track_key: str) -> StoredLiquidityMemory | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT memory_id, track_key, instrument_symbol, coverage_state, observed_track_json,
                       derived_summary_json, expires_at, updated_at
                FROM liquidity_memories
                WHERE track_key = ?
                """,
                (track_key,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_liquidity_memory(row)

    def list_liquidity_memories(
        self,
        *,
        instrument_symbol: str | None = None,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> list[StoredLiquidityMemory]:
        clauses = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument_symbol = ?")
            parameters.append(instrument_symbol)
        if as_of is not None:
            clauses.append("expires_at > ?")
            parameters.append(self._serialize_datetime(as_of))

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT memory_id, track_key, instrument_symbol, coverage_state, observed_track_json,
                   derived_summary_json, expires_at, updated_at
            FROM liquidity_memories
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ?
        """
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [self._row_to_liquidity_memory(row) for row in rows]

    def expire_liquidity_memories(self, cutoff: datetime) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM liquidity_memories
                WHERE expires_at <= ?
                """,
                (self._serialize_datetime(cutoff),),
            )
            connection.commit()
        return cursor.rowcount

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

    @staticmethod
    def _serialize_json(value: dict[str, Any]) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _parse_json(value: str) -> dict[str, Any]:
        return json.loads(value)

    @staticmethod
    def _serialize_datetime(value: datetime) -> str:
        timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return timestamp.isoformat()

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)
