from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from atas_market_structure.ingestion_backfill import (
    BackfillConfig,
    count_matching_ingestions,
    iter_sqlite_ingestion_batches,
    open_sqlite_connection,
    row_to_stored_ingestion,
)


def _create_sqlite_ingestions_table(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(database_path)) as connection:
        connection.execute(
            """
            CREATE TABLE ingestions (
                ingestion_id TEXT PRIMARY KEY,
                ingestion_kind TEXT NOT NULL,
                source_snapshot_id TEXT NOT NULL,
                instrument_symbol TEXT NOT NULL,
                observed_payload_json TEXT NOT NULL,
                stored_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def test_iter_sqlite_ingestion_batches_reads_rows_in_batches(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    _create_sqlite_ingestions_table(database_path)

    base_time = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
    with sqlite3.connect(str(database_path)) as connection:
        for offset in range(3):
            stored_at = base_time + timedelta(minutes=offset)
            connection.execute(
                """
                INSERT INTO ingestions
                (ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload_json, stored_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"ing-{offset}",
                    "adapter_continuous_state",
                    f"msg-{offset}",
                    "NQ",
                    '{"message_id":"msg"}',
                    stored_at.isoformat(),
                ),
            )
        connection.commit()

    with open_sqlite_connection(database_path) as connection:
        batches = list(
            iter_sqlite_ingestion_batches(
                connection,
                BackfillConfig(sqlite_path=database_path, batch_size=2),
            )
        )

    assert len(batches) == 2
    assert [row["ingestion_id"] for row in batches[0]] == ["ing-0", "ing-1"]
    assert [row["ingestion_id"] for row in batches[1]] == ["ing-2"]


def test_iter_sqlite_ingestion_batches_applies_filters(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    _create_sqlite_ingestions_table(database_path)

    base_time = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
    rows = [
        ("ing-a", "adapter_continuous_state", "msg-a", "NQ", base_time),
        ("ing-b", "adapter_history_bars", "msg-b", "NQ", base_time + timedelta(minutes=1)),
        ("ing-c", "adapter_continuous_state", "msg-c", "ES", base_time + timedelta(minutes=2)),
    ]
    with sqlite3.connect(str(database_path)) as connection:
        for ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, stored_at in rows:
            connection.execute(
                """
                INSERT INTO ingestions
                (ingestion_id, ingestion_kind, source_snapshot_id, instrument_symbol, observed_payload_json, stored_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ingestion_id,
                    ingestion_kind,
                    source_snapshot_id,
                    instrument_symbol,
                    '{"message_id":"msg"}',
                    stored_at.isoformat(),
                ),
            )
        connection.commit()

    config = BackfillConfig(
        sqlite_path=database_path,
        batch_size=10,
        ingestion_kinds=("adapter_continuous_state",),
        instrument_symbol="NQ",
        start_at=base_time,
        end_at=base_time + timedelta(minutes=1),
    )

    with open_sqlite_connection(database_path) as connection:
        assert count_matching_ingestions(connection, config) == 1
        batches = list(iter_sqlite_ingestion_batches(connection, config))

    assert len(batches) == 1
    assert len(batches[0]) == 1

    stored = row_to_stored_ingestion(batches[0][0])
    assert stored.ingestion_id == "ing-a"
    assert stored.ingestion_kind == "adapter_continuous_state"
    assert stored.instrument_symbol == "NQ"
