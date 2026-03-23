from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from atas_market_structure.sqlite_migrations import SQLiteMigrationRunner
from atas_market_structure.storage_models import (
    AppliedMigration,
    ObservationTable,
    StoredAnchorInteraction,
    StoredBeliefStateSnapshot,
    StoredDeadLetterPayload,
    StoredEpisodeEvaluationRecord,
    StoredEventEpisodeEvidence,
    StoredEventEpisodeRecord,
    StoredEventHypothesisState,
    StoredFeatureSlice,
    StoredIngestionRunLogRecord,
    StoredInstrumentProfileVersion,
    StoredMemoryAnchor,
    StoredMemoryAnchorVersion,
    StoredObservationRecord,
    StoredPatchValidationResult,
    StoredProfilePatchCandidate,
    StoredProjectionSnapshot,
    StoredRebuildRunLog,
    StoredRecognizerBuildVersion,
    StoredRegimePosterior,
    StoredSchemaRegistryEntry,
    StoredTuningRecommendation,
    StorageLifecyclePolicy,
)


_BLUEPRINT_SCHEMA_VERSION = "1.0.0"
_OBSERVATION_TABLES: tuple[ObservationTable, ...] = (
    ObservationTable.BAR,
    ObservationTable.TRADE_CLUSTER,
    ObservationTable.DEPTH_EVENT,
    ObservationTable.GAP_EVENT,
    ObservationTable.SWING_EVENT,
    ObservationTable.ABSORPTION_EVENT,
    ObservationTable.ADAPTER_PAYLOAD,
)
_DERIVED_CLEAR_TABLES: tuple[str, ...] = (
    "feature_slice",
    "regime_posterior",
    "event_hypothesis_state",
    "belief_state_snapshot",
    "projection_snapshot",
    "memory_anchor",
    "anchor_interaction",
    "event_episode",
    "event_episode_evidence",
    "episode_evaluation",
    "tuning_recommendation",
    "profile_patch_candidate",
    "patch_validation_result",
)


class SQLiteStorageBlueprintRepository:
    """SQLite DAO for the Master Spec v2 storage blueprint."""

    def __init__(self, *, database_path: Path, migration_dir: Path | None = None) -> None:
        self._database_path = database_path
        self._migration_dir = migration_dir or Path(__file__).resolve().parents[2] / "schemas" / "sqlite_migrations"
        self._migration_runner = SQLiteMigrationRunner(
            database_path=database_path,
            migration_dir=self._migration_dir,
        )

    def initialize(self, *, target_version: str | None = None) -> list[AppliedMigration]:
        """Apply pending blueprint migrations."""

        return self._migration_runner.initialize(target_version=target_version)

    def list_applied_migrations(self) -> list[AppliedMigration]:
        """Return applied blueprint migrations."""

        return self._migration_runner.list_applied()

    def list_schema_registry_entries(self) -> list[StoredSchemaRegistryEntry]:
        """List schema_registry rows ordered by object_name."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    object_name,
                    object_kind,
                    lifecycle_policy,
                    schema_version,
                    notes,
                    registered_at
                FROM schema_registry
                ORDER BY object_name
                """,
            ).fetchall()
        return [self._row_to_schema_registry_entry(row) for row in rows]

    def save_observation_record(self, record: StoredObservationRecord) -> StoredObservationRecord:
        """Insert one append-only observation row."""

        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {record.table_name.value} (
                    observation_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    source_ingestion_id,
                    source_request_id,
                    dedup_key,
                    payload_hash,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.observation_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.source_ingestion_id,
                    record.source_request_id,
                    record.dedup_key,
                    record.payload_hash,
                    _dump_json(record.observation_payload),
                ),
            )
        return record

    def save_observation_adapter_payload(
        self,
        record: StoredObservationRecord,
        *,
        enable_dedupe: bool = True,
    ) -> StoredObservationRecord:
        """Insert one observation_adapter_payload row with optional dedupe."""

        if record.table_name is not ObservationTable.ADAPTER_PAYLOAD:
            raise ValueError("save_observation_adapter_payload requires ObservationTable.ADAPTER_PAYLOAD")
        if enable_dedupe and record.dedup_key is not None and record.payload_hash is not None:
            existing = self.get_observation_adapter_payload_by_dedupe(
                instrument_symbol=record.instrument_symbol,
                dedup_key=record.dedup_key,
                payload_hash=record.payload_hash,
            )
            if existing is not None:
                return existing
        return self.save_observation_record(record)

    def get_observation_adapter_payload_by_dedupe(
        self,
        *,
        instrument_symbol: str,
        dedup_key: str,
        payload_hash: str,
    ) -> StoredObservationRecord | None:
        """Return an existing deduped adapter payload row when present."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    observation_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    source_ingestion_id,
                    source_request_id,
                    dedup_key,
                    payload_hash,
                    payload_json
                FROM observation_adapter_payload
                WHERE instrument = ? AND dedup_key = ? AND payload_hash = ?
                ORDER BY ingested_at DESC
                LIMIT 1
                """,
                (instrument_symbol, dedup_key, payload_hash),
            ).fetchone()
        return self._row_to_observation_record(ObservationTable.ADAPTER_PAYLOAD, row) if row is not None else None

    def list_observation_records(
        self,
        *,
        table_name: ObservationTable,
        instrument_symbol: str | None = None,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        limit: int = 5000,
    ) -> list[StoredObservationRecord]:
        """List append-only observation rows for one table."""

        clauses: list[str] = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument = ?")
            parameters.append(instrument_symbol)
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    observation_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    source_ingestion_id,
                    source_request_id,
                    dedup_key,
                    payload_hash,
                    payload_json
                FROM {table_name.value}
                {where_sql}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_observation_record(table_name, row) for row in rows]

    def list_rebuild_observations(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        limit: int = 10000,
    ) -> list[StoredObservationRecord]:
        """Return one time-ordered observation feed suitable for rebuild."""

        unions = []
        parameters: list[Any] = []
        for table in _OBSERVATION_TABLES:
            clauses = ["instrument = ?"]
            table_parameters: list[Any] = [instrument_symbol]
            if market_time_after is not None:
                clauses.append("market_time >= ?")
                table_parameters.append(_to_iso(market_time_after))
            if market_time_before is not None:
                clauses.append("market_time <= ?")
                table_parameters.append(_to_iso(market_time_before))
            unions.append(
                f"""
                SELECT
                    '{table.value}' AS table_name,
                    observation_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    source_ingestion_id,
                    source_request_id,
                    dedup_key,
                    payload_hash,
                    payload_json
                FROM {table.value}
                WHERE {' AND '.join(clauses)}
                """,
            )
            parameters.extend(table_parameters)
        sql = "\nUNION ALL\n".join(unions)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {sql}
                ORDER BY market_time ASC, ingested_at ASC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [
            self._row_to_observation_record(ObservationTable(row["table_name"]), row)
            for row in rows
        ]

    def save_feature_slice(self, record: StoredFeatureSlice) -> StoredFeatureSlice:
        """Insert one append-only feature_slice row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feature_slice (
                    feature_slice_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    source_observation_table,
                    source_observation_id,
                    slice_kind,
                    window_start,
                    window_end,
                    data_status_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.feature_slice_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.source_observation_table,
                    record.source_observation_id,
                    record.slice_kind,
                    _to_optional_iso(record.window_start),
                    _to_optional_iso(record.window_end),
                    _dump_json(record.data_status),
                    _dump_json(record.feature_payload),
                ),
            )
        return record

    def list_feature_slices(self, *, instrument_symbol: str, limit: int = 500) -> list[StoredFeatureSlice]:
        """List recent feature_slice rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    feature_slice_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    source_observation_table,
                    source_observation_id,
                    slice_kind,
                    window_start,
                    window_end,
                    data_status_json,
                    payload_json
                FROM feature_slice
                WHERE instrument = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_feature_slice(row) for row in rows]

    def save_regime_posterior(self, record: StoredRegimePosterior) -> StoredRegimePosterior:
        """Insert one append-only regime_posterior row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO regime_posterior (
                    posterior_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    feature_slice_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.posterior_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.feature_slice_id,
                    _dump_json(record.posterior_payload),
                ),
            )
        return record

    def list_regime_posteriors(self, *, instrument_symbol: str, limit: int = 500) -> list[StoredRegimePosterior]:
        """List recent regime_posterior rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    posterior_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    feature_slice_id,
                    payload_json
                FROM regime_posterior
                WHERE instrument = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_regime_posterior(row) for row in rows]

    def save_event_hypothesis_state(self, record: StoredEventHypothesisState) -> StoredEventHypothesisState:
        """Insert one append-only event_hypothesis_state row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO event_hypothesis_state (
                    hypothesis_state_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    feature_slice_id,
                    hypothesis_kind,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.hypothesis_state_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.feature_slice_id,
                    record.hypothesis_kind,
                    _dump_json(record.hypothesis_payload),
                ),
            )
        return record

    def list_event_hypothesis_states(
        self,
        *,
        instrument_symbol: str,
        limit: int = 500,
    ) -> list[StoredEventHypothesisState]:
        """List recent event_hypothesis_state rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    hypothesis_state_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    feature_slice_id,
                    hypothesis_kind,
                    payload_json
                FROM event_hypothesis_state
                WHERE instrument = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_event_hypothesis_state(row) for row in rows]

    def save_belief_state_snapshot(self, record: StoredBeliefStateSnapshot) -> StoredBeliefStateSnapshot:
        """Insert one append-only belief_state_snapshot row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO belief_state_snapshot (
                    belief_state_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    data_status_json,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.belief_state_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.recognition_mode,
                    _dump_json(record.data_status),
                    _dump_json(record.belief_payload),
                ),
            )
        return record

    def list_belief_state_snapshots(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 100,
    ) -> list[StoredBeliefStateSnapshot]:
        """List recent belief_state_snapshot rows."""

        clauses = ["instrument = ?"]
        parameters: list[Any] = [instrument_symbol]
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        if session_date is not None:
            clauses.append("session_date = ?")
            parameters.append(session_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    belief_state_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    recognition_mode,
                    data_status_json,
                    payload_json
                FROM belief_state_snapshot
                WHERE {' AND '.join(clauses)}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_belief_state_snapshot(row) for row in rows]

    def save_projection_snapshot(self, record: StoredProjectionSnapshot) -> StoredProjectionSnapshot:
        """Insert one append-only projection_snapshot row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projection_snapshot (
                    projection_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    belief_state_id,
                    projection_kind,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.projection_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.belief_state_id,
                    record.projection_kind,
                    _dump_json(record.projection_payload),
                ),
            )
        return record

    def list_projection_snapshots(self, *, instrument_symbol: str, limit: int = 100) -> list[StoredProjectionSnapshot]:
        """List recent projection_snapshot rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    projection_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    belief_state_id,
                    projection_kind,
                    payload_json
                FROM projection_snapshot
                WHERE instrument = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_projection_snapshot(row) for row in rows]

    def upsert_memory_anchor(self, record: StoredMemoryAnchor) -> StoredMemoryAnchor:
        """Upsert current memory_anchor state while version history stays append-only."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_anchor (
                    anchor_id,
                    instrument,
                    anchor_type,
                    status,
                    freshness,
                    current_version_id,
                    reference_price,
                    reference_time,
                    schema_version,
                    profile_version,
                    engine_version,
                    anchor_payload_json,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(anchor_id) DO UPDATE SET
                    instrument = excluded.instrument,
                    anchor_type = excluded.anchor_type,
                    status = excluded.status,
                    freshness = excluded.freshness,
                    current_version_id = excluded.current_version_id,
                    reference_price = excluded.reference_price,
                    reference_time = excluded.reference_time,
                    schema_version = excluded.schema_version,
                    profile_version = excluded.profile_version,
                    engine_version = excluded.engine_version,
                    anchor_payload_json = excluded.anchor_payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.anchor_id,
                    record.instrument_symbol,
                    record.anchor_type,
                    record.status,
                    record.freshness,
                    record.current_version_id,
                    record.reference_price,
                    _to_optional_iso(record.reference_time),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    _dump_json(record.anchor_payload),
                    _to_iso(record.updated_at),
                ),
            )
        return record

    def list_memory_anchors(self, *, instrument_symbol: str, limit: int = 200) -> list[StoredMemoryAnchor]:
        """List current memory_anchor rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    anchor_id,
                    instrument,
                    anchor_type,
                    status,
                    freshness,
                    current_version_id,
                    reference_price,
                    reference_time,
                    schema_version,
                    profile_version,
                    engine_version,
                    anchor_payload_json,
                    updated_at
                FROM memory_anchor
                WHERE instrument = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_memory_anchor(row) for row in rows]

    def save_memory_anchor_version(self, record: StoredMemoryAnchorVersion) -> StoredMemoryAnchorVersion:
        """Insert one append-only memory_anchor_version row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_anchor_version (
                    anchor_version_id,
                    anchor_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    freshness,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.anchor_version_id,
                    record.anchor_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.freshness,
                    _dump_json(record.anchor_payload),
                ),
            )
        return record

    def list_memory_anchor_versions(self, *, anchor_id: str, limit: int = 200) -> list[StoredMemoryAnchorVersion]:
        """List append-only anchor versions for one anchor."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    anchor_version_id,
                    anchor_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    freshness,
                    payload_json
                FROM memory_anchor_version
                WHERE anchor_id = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (anchor_id, limit),
            ).fetchall()
        return [self._row_to_memory_anchor_version(row) for row in rows]

    def save_anchor_interaction(self, record: StoredAnchorInteraction) -> StoredAnchorInteraction:
        """Insert one append-only anchor_interaction row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO anchor_interaction (
                    anchor_interaction_id,
                    anchor_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    interaction_kind,
                    source_observation_table,
                    source_observation_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.anchor_interaction_id,
                    record.anchor_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.interaction_kind,
                    record.source_observation_table,
                    record.source_observation_id,
                    _dump_json(record.interaction_payload),
                ),
            )
        return record

    def list_anchor_interactions(self, *, anchor_id: str, limit: int = 500) -> list[StoredAnchorInteraction]:
        """List recent anchor_interaction rows for one anchor."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    anchor_interaction_id,
                    anchor_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    interaction_kind,
                    source_observation_table,
                    source_observation_id,
                    payload_json
                FROM anchor_interaction
                WHERE anchor_id = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (anchor_id, limit),
            ).fetchall()
        return [self._row_to_anchor_interaction(row) for row in rows]

    def save_event_episode_record(self, record: StoredEventEpisodeRecord) -> StoredEventEpisodeRecord:
        """Insert one append-only event_episode row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO event_episode (
                    episode_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    event_kind,
                    started_at,
                    ended_at,
                    resolution,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.episode_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.event_kind,
                    _to_iso(record.started_at),
                    _to_iso(record.ended_at),
                    record.resolution,
                    _dump_json(record.episode_payload),
                ),
            )
        return record

    def list_event_episode_records(self, *, instrument_symbol: str, limit: int = 200) -> list[StoredEventEpisodeRecord]:
        """List recent event_episode rows."""

        return self.list_event_episode_records_filtered(
            instrument_symbol=instrument_symbol,
            limit=limit,
        )

    def list_event_episode_records_filtered(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 200,
    ) -> list[StoredEventEpisodeRecord]:
        """List recent event_episode rows with optional market-time filters."""

        clauses = ["instrument = ?"]
        parameters: list[Any] = [instrument_symbol]
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        if session_date is not None:
            clauses.append("date(market_time) = ?")
            parameters.append(session_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    episode_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    event_kind,
                    started_at,
                    ended_at,
                    resolution,
                    payload_json
                FROM event_episode
                WHERE {' AND '.join(clauses)}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_event_episode_record(row) for row in rows]

    def save_event_episode_evidence(self, record: StoredEventEpisodeEvidence) -> StoredEventEpisodeEvidence:
        """Insert one append-only event_episode_evidence row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO event_episode_evidence (
                    evidence_id,
                    episode_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    evidence_kind,
                    source_observation_table,
                    source_observation_id,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.evidence_id,
                    record.episode_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    record.session_date,
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.evidence_kind,
                    record.source_observation_table,
                    record.source_observation_id,
                    _dump_json(record.evidence_payload),
                ),
            )
        return record

    def list_event_episode_evidence(self, *, episode_id: str, limit: int = 500) -> list[StoredEventEpisodeEvidence]:
        """List recent event_episode_evidence rows for one episode."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    evidence_id,
                    episode_id,
                    instrument,
                    market_time,
                    session_date,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    evidence_kind,
                    source_observation_table,
                    source_observation_id,
                    payload_json
                FROM event_episode_evidence
                WHERE episode_id = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (episode_id, limit),
            ).fetchall()
        return [self._row_to_event_episode_evidence(row) for row in rows]

    def save_episode_evaluation_record(self, record: StoredEpisodeEvaluationRecord) -> StoredEpisodeEvaluationRecord:
        """Insert one append-only episode_evaluation row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO episode_evaluation (
                    evaluation_id,
                    episode_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    event_kind,
                    evaluated_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.evaluation_id,
                    record.episode_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.event_kind,
                    _to_iso(record.evaluated_at),
                    _dump_json(record.evaluation_payload),
                ),
            )
        return record

    def list_episode_evaluation_records(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 200,
    ) -> list[StoredEpisodeEvaluationRecord]:
        """List recent episode_evaluation rows."""

        clauses = ["instrument = ?"]
        parameters: list[Any] = [instrument_symbol]
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        if session_date is not None:
            clauses.append("date(market_time) = ?")
            parameters.append(session_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    evaluation_id,
                    episode_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    event_kind,
                    evaluated_at,
                    payload_json
                FROM episode_evaluation
                WHERE {' AND '.join(clauses)}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_episode_evaluation_record(row) for row in rows]

    def save_tuning_recommendation(self, record: StoredTuningRecommendation) -> StoredTuningRecommendation:
        """Insert one append-only tuning_recommendation row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tuning_recommendation (
                    recommendation_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    episode_id,
                    evaluation_id,
                    source_kind,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.recommendation_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.profile_version,
                    record.engine_version,
                    record.episode_id,
                    record.evaluation_id,
                    record.source_kind,
                    _dump_json(record.recommendation_payload),
                ),
            )
        return record

    def list_tuning_recommendations(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 200,
    ) -> list[StoredTuningRecommendation]:
        """List recent tuning_recommendation rows."""

        clauses = ["instrument = ?"]
        parameters: list[Any] = [instrument_symbol]
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        if session_date is not None:
            clauses.append("date(market_time) = ?")
            parameters.append(session_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    recommendation_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    profile_version,
                    engine_version,
                    episode_id,
                    evaluation_id,
                    source_kind,
                    payload_json
                FROM tuning_recommendation
                WHERE {' AND '.join(clauses)}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_tuning_recommendation(row) for row in rows]

    def save_profile_patch_candidate(self, record: StoredProfilePatchCandidate) -> StoredProfilePatchCandidate:
        """Insert one append-only profile_patch_candidate row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profile_patch_candidate (
                    candidate_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    base_profile_version,
                    proposed_profile_version,
                    recommendation_id,
                    status,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.candidate_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.base_profile_version,
                    record.proposed_profile_version,
                    record.recommendation_id,
                    record.status,
                    _dump_json(record.patch_payload),
                ),
            )
        return record

    def list_profile_patch_candidates(
        self,
        *,
        instrument_symbol: str,
        market_time_after: datetime | None = None,
        market_time_before: datetime | None = None,
        session_date: str | None = None,
        limit: int = 200,
    ) -> list[StoredProfilePatchCandidate]:
        """List recent profile_patch_candidate rows."""

        clauses = ["instrument = ?"]
        parameters: list[Any] = [instrument_symbol]
        if market_time_after is not None:
            clauses.append("market_time >= ?")
            parameters.append(_to_iso(market_time_after))
        if market_time_before is not None:
            clauses.append("market_time <= ?")
            parameters.append(_to_iso(market_time_before))
        if session_date is not None:
            clauses.append("date(market_time) = ?")
            parameters.append(session_date)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    candidate_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    base_profile_version,
                    proposed_profile_version,
                    recommendation_id,
                    status,
                    payload_json
                FROM profile_patch_candidate
                WHERE {' AND '.join(clauses)}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_profile_patch_candidate(row) for row in rows]

    def save_patch_validation_result(self, record: StoredPatchValidationResult) -> StoredPatchValidationResult:
        """Insert one append-only patch_validation_result row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO patch_validation_result (
                    validation_result_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    candidate_id,
                    validation_status,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.validation_result_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.candidate_id,
                    record.validation_status,
                    _dump_json(record.validation_payload),
                ),
            )
        return record

    def list_patch_validation_results(
        self,
        *,
        candidate_id: str,
        limit: int = 200,
    ) -> list[StoredPatchValidationResult]:
        """List recent patch_validation_result rows for one candidate."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    validation_result_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    candidate_id,
                    validation_status,
                    payload_json
                FROM patch_validation_result
                WHERE candidate_id = ?
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (candidate_id, limit),
            ).fetchall()
        return [self._row_to_patch_validation_result(row) for row in rows]

    def save_instrument_profile_version(self, record: StoredInstrumentProfileVersion) -> StoredInstrumentProfileVersion:
        """Upsert a versioned instrument_profile row."""

        with self._connect() as connection:
            if record.is_active:
                connection.execute(
                    "UPDATE instrument_profile SET is_active = 0 WHERE instrument = ? AND profile_version <> ?",
                    (record.instrument_symbol, record.profile_version),
                )
            connection.execute(
                """
                INSERT INTO instrument_profile (
                    instrument,
                    profile_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    payload_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument, profile_version) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    ontology_version = excluded.ontology_version,
                    is_active = excluded.is_active,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.instrument_symbol,
                    record.profile_version,
                    record.schema_version,
                    record.ontology_version,
                    1 if record.is_active else 0,
                    _dump_json(record.profile_payload),
                    _to_iso(record.created_at),
                    _to_iso(record.updated_at),
                ),
            )
        return record

    def list_instrument_profile_versions(
        self,
        *,
        instrument_symbol: str,
        limit: int = 100,
    ) -> list[StoredInstrumentProfileVersion]:
        """List versioned instrument_profile rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    instrument,
                    profile_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    payload_json,
                    created_at,
                    updated_at
                FROM instrument_profile
                WHERE instrument = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (instrument_symbol, limit),
            ).fetchall()
        return [self._row_to_instrument_profile_version(row) for row in rows]

    def save_recognizer_build_version(self, record: StoredRecognizerBuildVersion) -> StoredRecognizerBuildVersion:
        """Upsert a versioned recognizer_build row."""

        with self._connect() as connection:
            if record.is_active:
                connection.execute(
                    "UPDATE recognizer_build SET is_active = 0 WHERE engine_version <> ?",
                    (record.engine_version,),
                )
            connection.execute(
                """
                INSERT INTO recognizer_build (
                    engine_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    status,
                    payload_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(engine_version) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    ontology_version = excluded.ontology_version,
                    is_active = excluded.is_active,
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.engine_version,
                    record.schema_version,
                    record.ontology_version,
                    1 if record.is_active else 0,
                    record.status,
                    _dump_json(record.build_payload),
                    _to_iso(record.created_at),
                    _to_iso(record.updated_at),
                ),
            )
        return record

    def list_recognizer_build_versions(self, *, limit: int = 100) -> list[StoredRecognizerBuildVersion]:
        """List versioned recognizer_build rows."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    engine_version,
                    schema_version,
                    ontology_version,
                    is_active,
                    status,
                    payload_json,
                    created_at,
                    updated_at
                FROM recognizer_build
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_recognizer_build_version(row) for row in rows]

    def save_ingestion_run_log_record(self, record: StoredIngestionRunLogRecord) -> StoredIngestionRunLogRecord:
        """Insert one append-only ingestion_run_log row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_run_log (
                    run_id,
                    endpoint,
                    ingestion_kind,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    request_id,
                    dedup_key,
                    payload_hash,
                    ingestion_id,
                    dead_letter_id,
                    outcome,
                    http_status,
                    detail_json,
                    started_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.endpoint,
                    record.ingestion_kind,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.request_id,
                    record.dedup_key,
                    record.payload_hash,
                    record.ingestion_id,
                    record.dead_letter_id,
                    record.outcome,
                    record.http_status,
                    _dump_json(record.detail),
                    _to_iso(record.started_at),
                    _to_iso(record.completed_at),
                ),
            )
        return record

    def list_ingestion_run_log_records(
        self,
        *,
        instrument_symbol: str | None = None,
        limit: int = 200,
    ) -> list[StoredIngestionRunLogRecord]:
        """List recent ingestion_run_log rows."""

        clauses: list[str] = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument = ?")
            parameters.append(instrument_symbol)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    run_id,
                    endpoint,
                    ingestion_kind,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    request_id,
                    dedup_key,
                    payload_hash,
                    ingestion_id,
                    dead_letter_id,
                    outcome,
                    http_status,
                    detail_json,
                    started_at,
                    completed_at
                FROM ingestion_run_log
                {where_sql}
                ORDER BY market_time DESC, completed_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_ingestion_run_log_record(row) for row in rows]

    def save_rebuild_run_log(self, record: StoredRebuildRunLog) -> StoredRebuildRunLog:
        """Insert one append-only rebuild_run_log row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rebuild_run_log (
                    rebuild_run_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    triggered_by,
                    reason,
                    status,
                    window_start,
                    window_end,
                    cleared_tables_json,
                    detail_json,
                    started_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.rebuild_run_id,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.triggered_by,
                    record.reason,
                    record.status,
                    _to_optional_iso(record.window_start),
                    _to_optional_iso(record.window_end),
                    _dump_json(record.cleared_tables),
                    _dump_json(record.detail),
                    _to_iso(record.started_at),
                    _to_optional_iso(record.completed_at),
                ),
            )
        return record

    def list_rebuild_run_logs(
        self,
        *,
        instrument_symbol: str | None = None,
        limit: int = 100,
    ) -> list[StoredRebuildRunLog]:
        """List recent rebuild_run_log rows."""

        clauses: list[str] = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument = ?")
            parameters.append(instrument_symbol)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    rebuild_run_id,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    triggered_by,
                    reason,
                    status,
                    window_start,
                    window_end,
                    cleared_tables_json,
                    detail_json,
                    started_at,
                    completed_at
                FROM rebuild_run_log
                {where_sql}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_rebuild_run_log(row) for row in rows]

    def save_dead_letter_payload(self, record: StoredDeadLetterPayload) -> StoredDeadLetterPayload:
        """Insert one append-only dead_letter_payload row."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO dead_letter_payload (
                    dead_letter_id,
                    endpoint,
                    ingestion_kind,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    request_id,
                    dedup_key,
                    payload_hash,
                    source_ingestion_id,
                    error_code,
                    error_detail_json,
                    raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.dead_letter_id,
                    record.endpoint,
                    record.ingestion_kind,
                    record.instrument_symbol,
                    _to_iso(record.market_time),
                    _to_iso(record.ingested_at),
                    record.schema_version,
                    record.request_id,
                    record.dedup_key,
                    record.payload_hash,
                    record.source_ingestion_id,
                    record.error_code,
                    _dump_json(record.error_detail),
                    record.raw_payload,
                ),
            )
        return record

    def list_dead_letter_payloads(
        self,
        *,
        instrument_symbol: str | None = None,
        limit: int = 200,
    ) -> list[StoredDeadLetterPayload]:
        """List recent dead_letter_payload rows."""

        clauses: list[str] = []
        parameters: list[Any] = []
        if instrument_symbol is not None:
            clauses.append("instrument = ?")
            parameters.append(instrument_symbol)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    dead_letter_id,
                    endpoint,
                    ingestion_kind,
                    instrument,
                    market_time,
                    ingested_at,
                    schema_version,
                    request_id,
                    dedup_key,
                    payload_hash,
                    source_ingestion_id,
                    error_code,
                    error_detail_json,
                    raw_payload
                FROM dead_letter_payload
                {where_sql}
                ORDER BY market_time DESC, ingested_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [self._row_to_dead_letter_payload(row) for row in rows]

    def clear_derived_storage_for_rebuild(
        self,
        *,
        instrument_symbol: str | None,
        reason: str,
        triggered_by: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> StoredRebuildRunLog:
        """Delete derived tables only, then record one rebuild_run_log row."""

        if window_start is not None or window_end is not None:
            raise ValueError(
                "Window-scoped rebuild clearing is not implemented in V1; "
                "omit window_start/window_end to run a full instrument rebuild clear.",
            )
        cleared_counts: dict[str, int] = {}
        started_at = datetime.now(tz=UTC)
        with self._connect() as connection:
            for table_name in _DERIVED_CLEAR_TABLES:
                if instrument_symbol is None:
                    cursor = connection.execute(f"DELETE FROM {table_name}")
                else:
                    cursor = connection.execute(
                        f"DELETE FROM {table_name} WHERE instrument = ?",
                        (instrument_symbol,),
                    )
                cleared_counts[table_name] = max(cursor.rowcount, 0)
        completed_at = datetime.now(tz=UTC)
        record = StoredRebuildRunLog(
            rebuild_run_id=f"rebuild-{completed_at.strftime('%Y%m%dT%H%M%S%fZ')}",
            instrument_symbol=instrument_symbol,
            market_time=completed_at,
            ingested_at=completed_at,
            schema_version=_BLUEPRINT_SCHEMA_VERSION,
            triggered_by=triggered_by,
            reason=reason,
            status="cleared",
            window_start=window_start,
            window_end=window_end,
            cleared_tables=list(_DERIVED_CLEAR_TABLES),
            detail={"cleared_counts": cleared_counts},
            started_at=started_at,
            completed_at=completed_at,
        )
        self.save_rebuild_run_log(record)
        return record

    def mirror_legacy_ingestion(
        self,
        *,
        ingestion_id: str,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, Any],
        stored_at: datetime,
    ) -> None:
        """Mirror legacy raw ingestions into blueprint observation_* tables."""

        payload_hash = _stable_payload_hash(observed_payload)
        seen_observation_ids: set[str] = set()
        request_id = self._extract_request_id(observed_payload) or source_snapshot_id
        schema_version = str(observed_payload.get("schema_version") or _BLUEPRINT_SCHEMA_VERSION)
        market_time = self._extract_market_time(observed_payload, fallback=stored_at)
        if ingestion_kind.startswith("adapter_"):
            self.save_observation_adapter_payload(
                StoredObservationRecord(
                    table_name=ObservationTable.ADAPTER_PAYLOAD,
                    observation_id=f"{ingestion_id}:adapter",
                    instrument_symbol=instrument_symbol,
                    market_time=market_time,
                    session_date=_session_date(market_time),
                    ingested_at=stored_at,
                    schema_version=schema_version,
                    source_ingestion_id=ingestion_id,
                    source_request_id=request_id,
                    dedup_key=request_id,
                    payload_hash=payload_hash,
                    observation_payload=observed_payload,
                ),
            )
        if ingestion_kind == "adapter_history_bars":
            for index, bar in enumerate(observed_payload.get("bars") or []):
                if not isinstance(bar, dict):
                    continue
                started_at = self._extract_market_time(bar, fallback=market_time)
                bar_id = bar.get("bar_timestamp_utc") or bar.get("started_at") or index
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.BAR,
                        observation_id=f"{ingestion_id}:bar:{bar_id}",
                        instrument_symbol=instrument_symbol,
                        market_time=started_at,
                        session_date=_session_date(started_at),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=bar,
                    ),
                )
        if ingestion_kind == "depth_snapshot":
            levels = observed_payload.get("significant_levels") or []
            if levels:
                for level in levels:
                    if not isinstance(level, dict):
                        continue
                    level_time = self._extract_market_time(level, fallback=market_time)
                    level_id = level.get("track_id") or _stable_payload_hash(level)
                    self.save_observation_record(
                        StoredObservationRecord(
                            table_name=ObservationTable.DEPTH_EVENT,
                            observation_id=f"{ingestion_id}:depth:{level_id}",
                            instrument_symbol=instrument_symbol,
                            market_time=level_time,
                            session_date=_session_date(level_time),
                            ingested_at=stored_at,
                            schema_version=schema_version,
                            source_ingestion_id=ingestion_id,
                            source_request_id=request_id,
                            dedup_key=None,
                            payload_hash=None,
                            observation_payload=level,
                        ),
                    )
            else:
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.DEPTH_EVENT,
                        observation_id=f"{ingestion_id}:depth:snapshot",
                        instrument_symbol=instrument_symbol,
                        market_time=market_time,
                        session_date=_session_date(market_time),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=observed_payload,
                    ),
                )
        if ingestion_kind == "event_snapshot":
            trigger_event = observed_payload.get("trigger_event")
            trade_cluster_payload = trigger_event if isinstance(trigger_event, dict) else observed_payload
            cluster_time = self._extract_market_time(trade_cluster_payload, fallback=market_time)
            self.save_observation_record(
                StoredObservationRecord(
                    table_name=ObservationTable.TRADE_CLUSTER,
                    observation_id=f"{ingestion_id}:cluster",
                    instrument_symbol=instrument_symbol,
                    market_time=cluster_time,
                    session_date=_session_date(cluster_time),
                    ingested_at=stored_at,
                    schema_version=schema_version,
                    source_ingestion_id=ingestion_id,
                    source_request_id=request_id,
                    dedup_key=None,
                    payload_hash=None,
                    observation_payload=trade_cluster_payload if isinstance(trade_cluster_payload, dict) else observed_payload,
                ),
            )
            for signal in self._iter_absorption_signals(observed_payload):
                signal_time = self._extract_market_time(signal, fallback=market_time)
                signal_id = _mirrored_observation_id(
                    ingestion_id=ingestion_id,
                    kind="absorption",
                    payload=signal,
                    primary_key=signal.get("observed_at"),
                )
                if signal_id in seen_observation_ids:
                    continue
                seen_observation_ids.add(signal_id)
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.ABSORPTION_EVENT,
                        observation_id=signal_id,
                        instrument_symbol=instrument_symbol,
                        market_time=signal_time,
                        session_date=_session_date(signal_time),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=signal,
                    ),
                )
        if ingestion_kind == "market_structure":
            for swing in self._iter_swing_points(observed_payload):
                swing_time = self._extract_market_time(swing, fallback=market_time)
                swing_id = _mirrored_observation_id(
                    ingestion_id=ingestion_id,
                    kind="swing",
                    payload=swing,
                    primary_key=swing.get("formed_at"),
                )
                if swing_id in seen_observation_ids:
                    continue
                seen_observation_ids.add(swing_id)
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.SWING_EVENT,
                        observation_id=swing_id,
                        instrument_symbol=instrument_symbol,
                        market_time=swing_time,
                        session_date=_session_date(swing_time),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=swing,
                    ),
                )
            for event in observed_payload.get("observed_events") or []:
                if not isinstance(event, dict):
                    continue
                if "gap" not in str(event.get("event_type") or ""):
                    continue
                event_time = self._extract_market_time(event, fallback=market_time)
                event_id = _mirrored_observation_id(
                    ingestion_id=ingestion_id,
                    kind="gap",
                    payload=event,
                    primary_key=event.get("observed_at"),
                )
                if event_id in seen_observation_ids:
                    continue
                seen_observation_ids.add(event_id)
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.GAP_EVENT,
                        observation_id=event_id,
                        instrument_symbol=instrument_symbol,
                        market_time=event_time,
                        session_date=_session_date(event_time),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=event,
                    ),
                )
            for signal in self._iter_absorption_signals(observed_payload):
                signal_time = self._extract_market_time(signal, fallback=market_time)
                signal_id = _mirrored_observation_id(
                    ingestion_id=ingestion_id,
                    kind="absorption",
                    payload=signal,
                    primary_key=signal.get("observed_at"),
                )
                if signal_id in seen_observation_ids:
                    continue
                seen_observation_ids.add(signal_id)
                self.save_observation_record(
                    StoredObservationRecord(
                        table_name=ObservationTable.ABSORPTION_EVENT,
                        observation_id=signal_id,
                        instrument_symbol=instrument_symbol,
                        market_time=signal_time,
                        session_date=_session_date(signal_time),
                        ingested_at=stored_at,
                        schema_version=schema_version,
                        source_ingestion_id=ingestion_id,
                        source_request_id=request_id,
                        dedup_key=None,
                        payload_hash=None,
                        observation_payload=signal,
                    ),
                )

    @staticmethod
    def _iter_swing_points(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        decision_layers = payload.get("decision_layers")
        if not isinstance(decision_layers, dict):
            return []
        swings: list[dict[str, Any]] = []
        for layer_items in decision_layers.values():
            if not isinstance(layer_items, list):
                continue
            for layer_item in layer_items:
                if not isinstance(layer_item, dict):
                    continue
                for swing in layer_item.get("swing_points") or []:
                    if isinstance(swing, dict):
                        swings.append(swing)
        return swings

    @staticmethod
    def _iter_absorption_signals(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        decision_layers = payload.get("decision_layers")
        if not isinstance(decision_layers, dict):
            return []
        signals: list[dict[str, Any]] = []
        for layer_items in decision_layers.values():
            if not isinstance(layer_items, list):
                continue
            for layer_item in layer_items:
                if not isinstance(layer_item, dict):
                    continue
                for signal in layer_item.get("orderflow_signals") or []:
                    if isinstance(signal, dict) and str(signal.get("signal_type") or "") == "absorption":
                        signals.append(signal)
        return signals

    @staticmethod
    def _extract_request_id(payload: dict[str, Any]) -> str | None:
        for key in (
            "snapshot_id",
            "event_snapshot_id",
            "process_context_id",
            "depth_snapshot_id",
            "message_id",
            "batch_id",
            "replay_snapshot_id",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _extract_market_time(self, payload: dict[str, Any], *, fallback: datetime) -> datetime:
        for key in (
            "market_time",
            "observed_at",
            "observed_window_end",
            "last_observed_at",
            "formed_at",
            "bar_timestamp_utc",
            "ended_at",
            "emitted_at",
            "created_at",
            "first_observed_at",
        ):
            parsed = _parse_optional_datetime(payload.get(key))
            if parsed is not None:
                return parsed
        return fallback

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @staticmethod
    def _row_to_schema_registry_entry(row: sqlite3.Row) -> StoredSchemaRegistryEntry:
        return StoredSchemaRegistryEntry(
            object_name=row["object_name"],
            object_kind=row["object_kind"],
            lifecycle_policy=StorageLifecyclePolicy(row["lifecycle_policy"]),
            schema_version=row["schema_version"],
            notes=row["notes"],
            registered_at=_parse_datetime(row["registered_at"]),
        )

    @staticmethod
    def _row_to_observation_record(table_name: ObservationTable, row: sqlite3.Row) -> StoredObservationRecord:
        return StoredObservationRecord(
            table_name=table_name,
            observation_id=row["observation_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            source_ingestion_id=row["source_ingestion_id"],
            source_request_id=row["source_request_id"],
            dedup_key=row["dedup_key"],
            payload_hash=row["payload_hash"],
            observation_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_feature_slice(row: sqlite3.Row) -> StoredFeatureSlice:
        return StoredFeatureSlice(
            feature_slice_id=row["feature_slice_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            source_observation_table=row["source_observation_table"],
            source_observation_id=row["source_observation_id"],
            slice_kind=row["slice_kind"],
            window_start=_parse_optional_datetime(row["window_start"]),
            window_end=_parse_optional_datetime(row["window_end"]),
            data_status=_load_json(row["data_status_json"]),
            feature_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_regime_posterior(row: sqlite3.Row) -> StoredRegimePosterior:
        return StoredRegimePosterior(
            posterior_id=row["posterior_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            feature_slice_id=row["feature_slice_id"],
            posterior_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_event_hypothesis_state(row: sqlite3.Row) -> StoredEventHypothesisState:
        return StoredEventHypothesisState(
            hypothesis_state_id=row["hypothesis_state_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            feature_slice_id=row["feature_slice_id"],
            hypothesis_kind=row["hypothesis_kind"],
            hypothesis_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_belief_state_snapshot(row: sqlite3.Row) -> StoredBeliefStateSnapshot:
        return StoredBeliefStateSnapshot(
            belief_state_id=row["belief_state_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            recognition_mode=row["recognition_mode"],
            data_status=_load_json(row["data_status_json"]),
            belief_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_projection_snapshot(row: sqlite3.Row) -> StoredProjectionSnapshot:
        return StoredProjectionSnapshot(
            projection_id=row["projection_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            belief_state_id=row["belief_state_id"],
            projection_kind=row["projection_kind"],
            projection_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_memory_anchor(row: sqlite3.Row) -> StoredMemoryAnchor:
        return StoredMemoryAnchor(
            anchor_id=row["anchor_id"],
            instrument_symbol=row["instrument"],
            anchor_type=row["anchor_type"],
            status=row["status"],
            freshness=row["freshness"],
            current_version_id=row["current_version_id"],
            reference_price=row["reference_price"],
            reference_time=_parse_optional_datetime(row["reference_time"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            anchor_payload=_load_json(row["anchor_payload_json"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_memory_anchor_version(row: sqlite3.Row) -> StoredMemoryAnchorVersion:
        return StoredMemoryAnchorVersion(
            anchor_version_id=row["anchor_version_id"],
            anchor_id=row["anchor_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            freshness=row["freshness"],
            anchor_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_anchor_interaction(row: sqlite3.Row) -> StoredAnchorInteraction:
        return StoredAnchorInteraction(
            anchor_interaction_id=row["anchor_interaction_id"],
            anchor_id=row["anchor_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            interaction_kind=row["interaction_kind"],
            source_observation_table=row["source_observation_table"],
            source_observation_id=row["source_observation_id"],
            interaction_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_event_episode_record(row: sqlite3.Row) -> StoredEventEpisodeRecord:
        return StoredEventEpisodeRecord(
            episode_id=row["episode_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            event_kind=row["event_kind"],
            started_at=_parse_datetime(row["started_at"]),
            ended_at=_parse_datetime(row["ended_at"]),
            resolution=row["resolution"],
            episode_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_event_episode_evidence(row: sqlite3.Row) -> StoredEventEpisodeEvidence:
        return StoredEventEpisodeEvidence(
            evidence_id=row["evidence_id"],
            episode_id=row["episode_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            session_date=row["session_date"],
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            evidence_kind=row["evidence_kind"],
            source_observation_table=row["source_observation_table"],
            source_observation_id=row["source_observation_id"],
            evidence_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_episode_evaluation_record(row: sqlite3.Row) -> StoredEpisodeEvaluationRecord:
        return StoredEpisodeEvaluationRecord(
            evaluation_id=row["evaluation_id"],
            episode_id=row["episode_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            event_kind=row["event_kind"],
            evaluated_at=_parse_datetime(row["evaluated_at"]),
            evaluation_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_tuning_recommendation(row: sqlite3.Row) -> StoredTuningRecommendation:
        return StoredTuningRecommendation(
            recommendation_id=row["recommendation_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            profile_version=row["profile_version"],
            engine_version=row["engine_version"],
            episode_id=row["episode_id"],
            evaluation_id=row["evaluation_id"],
            source_kind=row["source_kind"],
            recommendation_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_profile_patch_candidate(row: sqlite3.Row) -> StoredProfilePatchCandidate:
        return StoredProfilePatchCandidate(
            candidate_id=row["candidate_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            base_profile_version=row["base_profile_version"],
            proposed_profile_version=row["proposed_profile_version"],
            recommendation_id=row["recommendation_id"],
            status=row["status"],
            patch_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_patch_validation_result(row: sqlite3.Row) -> StoredPatchValidationResult:
        return StoredPatchValidationResult(
            validation_result_id=row["validation_result_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            candidate_id=row["candidate_id"],
            validation_status=row["validation_status"],
            validation_payload=_load_json(row["payload_json"]),
        )

    @staticmethod
    def _row_to_instrument_profile_version(row: sqlite3.Row) -> StoredInstrumentProfileVersion:
        return StoredInstrumentProfileVersion(
            instrument_symbol=row["instrument"],
            profile_version=row["profile_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            profile_payload=_load_json(row["payload_json"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_recognizer_build_version(row: sqlite3.Row) -> StoredRecognizerBuildVersion:
        return StoredRecognizerBuildVersion(
            engine_version=row["engine_version"],
            schema_version=row["schema_version"],
            ontology_version=row["ontology_version"],
            is_active=bool(row["is_active"]),
            status=row["status"],
            build_payload=_load_json(row["payload_json"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _row_to_ingestion_run_log_record(row: sqlite3.Row) -> StoredIngestionRunLogRecord:
        return StoredIngestionRunLogRecord(
            run_id=row["run_id"],
            endpoint=row["endpoint"],
            ingestion_kind=row["ingestion_kind"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            request_id=row["request_id"],
            dedup_key=row["dedup_key"],
            payload_hash=row["payload_hash"],
            ingestion_id=row["ingestion_id"],
            dead_letter_id=row["dead_letter_id"],
            outcome=row["outcome"],
            http_status=row["http_status"],
            detail=_load_json(row["detail_json"]),
            started_at=_parse_datetime(row["started_at"]),
            completed_at=_parse_datetime(row["completed_at"]),
        )

    @staticmethod
    def _row_to_rebuild_run_log(row: sqlite3.Row) -> StoredRebuildRunLog:
        return StoredRebuildRunLog(
            rebuild_run_id=row["rebuild_run_id"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            triggered_by=row["triggered_by"],
            reason=row["reason"],
            status=row["status"],
            window_start=_parse_optional_datetime(row["window_start"]),
            window_end=_parse_optional_datetime(row["window_end"]),
            cleared_tables=_load_json(row["cleared_tables_json"]),
            detail=_load_json(row["detail_json"]),
            started_at=_parse_datetime(row["started_at"]),
            completed_at=_parse_optional_datetime(row["completed_at"]),
        )

    @staticmethod
    def _row_to_dead_letter_payload(row: sqlite3.Row) -> StoredDeadLetterPayload:
        return StoredDeadLetterPayload(
            dead_letter_id=row["dead_letter_id"],
            endpoint=row["endpoint"],
            ingestion_kind=row["ingestion_kind"],
            instrument_symbol=row["instrument"],
            market_time=_parse_datetime(row["market_time"]),
            ingested_at=_parse_datetime(row["ingested_at"]),
            schema_version=row["schema_version"],
            request_id=row["request_id"],
            dedup_key=row["dedup_key"],
            payload_hash=row["payload_hash"],
            source_ingestion_id=row["source_ingestion_id"],
            error_code=row["error_code"],
            error_detail=_load_json(row["error_detail_json"]),
            raw_payload=row["raw_payload"],
        )


def _dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _load_json(value: str) -> Any:
    return json.loads(value)


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _to_optional_iso(value: datetime | None) -> str | None:
    return _to_iso(value) if value is not None else None


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return _parse_datetime(value)


def _session_date(value: datetime) -> str:
    return value.date().isoformat()


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_dump_json(payload).encode("utf-8")).hexdigest()


def _mirrored_observation_id(
    *,
    ingestion_id: str,
    kind: str,
    payload: dict[str, Any],
    primary_key: Any,
) -> str:
    stable_key = str(primary_key or "na")
    return f"{ingestion_id}:{kind}:{stable_key}:{_stable_payload_hash(payload)}"
