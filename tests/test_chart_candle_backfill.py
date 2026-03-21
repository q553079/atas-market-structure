from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3

from atas_market_structure.chart_candle_backfill import (
    BackfillConfig,
    count_matching_chart_candles,
    iter_sqlite_chart_candle_batches,
    open_sqlite_connection,
    row_to_chart_candle,
)


def _create_sqlite_chart_candles_table(database_path: Path, *, include_source_started_at: bool) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(database_path)) as connection:
        source_column = "source_started_at TEXT NOT NULL," if include_source_started_at else ""
        connection.execute(
            f"""
            CREATE TABLE chart_candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                {source_column}
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                tick_volume INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe, started_at)
            )
            """
        )
        connection.commit()


def test_iter_sqlite_chart_candle_batches_supports_older_sqlite_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    _create_sqlite_chart_candles_table(database_path, include_source_started_at=False)

    started_at = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
    with sqlite3.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO chart_candles
            (symbol, timeframe, started_at, ended_at, open, high, low, close, volume, tick_volume, delta, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "NQ",
                "1m",
                started_at.isoformat(),
                (started_at + timedelta(minutes=1)).isoformat(),
                100.0,
                101.0,
                99.5,
                100.5,
                25,
                3,
                5,
                (started_at + timedelta(minutes=1)).isoformat(),
            ),
        )
        connection.commit()

    with open_sqlite_connection(database_path) as connection:
        rows = list(iter_sqlite_chart_candle_batches(connection, BackfillConfig(sqlite_path=database_path, batch_size=10)))

    assert len(rows) == 1
    assert len(rows[0]) == 1

    candle = row_to_chart_candle(rows[0][0])
    assert candle.source_started_at == started_at


def test_iter_sqlite_chart_candle_batches_applies_filters_and_keyset_pagination(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "market_structure.db"
    _create_sqlite_chart_candles_table(database_path, include_source_started_at=True)

    started_at = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
    rows = [
        ("ES", "1m", started_at, started_at),
        ("NQ", "1m", started_at + timedelta(minutes=1), started_at + timedelta(minutes=1, seconds=5)),
        ("NQ", "5m", started_at + timedelta(minutes=5), started_at + timedelta(minutes=5)),
    ]
    with sqlite3.connect(str(database_path)) as connection:
        for symbol, timeframe, bucket_start, source_started_at in rows:
            connection.execute(
                """
                INSERT INTO chart_candles
                (
                    symbol, timeframe, started_at, ended_at, source_started_at,
                    open, high, low, close, volume, tick_volume, delta, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    timeframe,
                    bucket_start.isoformat(),
                    (bucket_start + timedelta(minutes=1)).isoformat(),
                    source_started_at.isoformat(),
                    100.0,
                    101.0,
                    99.5,
                    100.5,
                    25,
                    3,
                    5,
                    (bucket_start + timedelta(minutes=1)).isoformat(),
                ),
            )
        connection.commit()

    config = BackfillConfig(
        sqlite_path=database_path,
        batch_size=1,
        symbols=("NQ",),
        timeframes=("1m",),
        start_at=started_at,
        end_at=started_at + timedelta(minutes=2),
    )

    with open_sqlite_connection(database_path) as connection:
        assert count_matching_chart_candles(connection, config) == 1
        batches = list(iter_sqlite_chart_candle_batches(connection, config))

    assert len(batches) == 1
    assert len(batches[0]) == 1

    candle = row_to_chart_candle(batches[0][0])
    assert candle.symbol == "NQ"
    assert candle.timeframe.value == "1m"
    assert candle.started_at == started_at + timedelta(minutes=1)
    assert candle.source_started_at == started_at + timedelta(minutes=1, seconds=5)
