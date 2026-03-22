from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
import sqlite3
import time
from typing import Iterator, Mapping, Sequence

from atas_market_structure.config import AppConfig
from atas_market_structure.models._enums import Timeframe
from atas_market_structure.models._replay import ChartCandle
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository


LOGGER = logging.getLogger("atas_market_structure.chart_candle_backfill")


@dataclass(frozen=True)
class BackfillConfig:
    sqlite_path: Path
    batch_size: int = 5000
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    start_at: datetime | None = None
    end_at: datetime | None = None
    dry_run: bool = False
    connect_retries: int = 5
    retry_delay_seconds: float = 1.5


@dataclass(frozen=True)
class SQLiteCursorKey:
    symbol: str
    timeframe: str
    started_at: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill existing SQLite chart_candles rows into the ClickHouse chart candle store."
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="SQLite database path. Defaults to ATAS_MS_DB_PATH or the project's standard data path.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="How many chart_candles rows to read from SQLite and insert into ClickHouse per batch.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=[],
        help="Optional symbol allowlist, for example --symbols NQ ES YM.",
    )
    parser.add_argument(
        "--timeframes",
        nargs="*",
        default=[],
        help="Optional timeframe allowlist, for example --timeframes 1m 5m 15m.",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Optional inclusive UTC lower bound on started_at, ISO-8601 format.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional inclusive UTC upper bound on started_at, ISO-8601 format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and validate SQLite rows without inserting anything into ClickHouse.",
    )
    parser.add_argument(
        "--connect-retries",
        type=int,
        default=5,
        help="How many times to retry ClickHouse initialization before failing.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=1.5,
        help="Base delay between ClickHouse initialization retries.",
    )
    return parser.parse_args(argv)


def build_backfill_config(args: argparse.Namespace, app_config: AppConfig) -> BackfillConfig:
    sqlite_path = Path(args.sqlite_path) if args.sqlite_path else app_config.database_path
    if not sqlite_path.is_absolute():
        sqlite_path = (Path.cwd() / sqlite_path).resolve()

    symbols = tuple(dict.fromkeys(symbol.strip().upper() for symbol in args.symbols if symbol.strip()))
    timeframes = tuple(
        dict.fromkeys(Timeframe(timeframe.strip()).value for timeframe in args.timeframes if timeframe.strip())
    )

    return BackfillConfig(
        sqlite_path=sqlite_path,
        batch_size=max(1, int(args.batch_size)),
        symbols=symbols,
        timeframes=timeframes,
        start_at=parse_utc_datetime(args.start),
        end_at=parse_utc_datetime(args.end),
        dry_run=bool(args.dry_run),
        connect_retries=max(1, int(args.connect_retries)),
        retry_delay_seconds=max(0.1, float(args.retry_delay_seconds)),
    )


def parse_utc_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return normalize_utc(parsed)


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def serialize_datetime(value: datetime) -> str:
    return normalize_utc(value).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    return normalize_utc(datetime.fromisoformat(value))


def open_sqlite_connection(sqlite_path: Path) -> sqlite3.Connection:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def sqlite_has_column(connection: sqlite3.Connection, *, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def count_matching_chart_candles(connection: sqlite3.Connection, config: BackfillConfig) -> int:
    conditions, parameters = build_sqlite_filters(config=config, after_key=None)
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    row = connection.execute(
        f"SELECT COUNT(*) AS row_count FROM chart_candles WHERE {where_clause}",
        parameters,
    ).fetchone()
    return int(row["row_count"]) if row is not None else 0


def iter_sqlite_chart_candle_batches(
    connection: sqlite3.Connection,
    config: BackfillConfig,
) -> Iterator[list[sqlite3.Row]]:
    source_started_at_expr = (
        "COALESCE(NULLIF(source_started_at, ''), started_at) AS source_started_at"
        if sqlite_has_column(connection, table="chart_candles", column="source_started_at")
        else "started_at AS source_started_at"
    )
    source_timezone_expr = (
        "COALESCE(NULLIF(source_timezone, ''), '') AS source_timezone"
        if sqlite_has_column(connection, table="chart_candles", column="source_timezone")
        else "'' AS source_timezone"
    )

    after_key: SQLiteCursorKey | None = None
    while True:
        conditions, parameters = build_sqlite_filters(config=config, after_key=after_key)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        rows = connection.execute(
            f"""
            SELECT
                symbol,
                timeframe,
                started_at,
                ended_at,
                {source_started_at_expr},
                open,
                high,
                low,
                close,
                volume,
                tick_volume,
                delta,
                updated_at,
                {source_timezone_expr}
            FROM chart_candles
            WHERE {where_clause}
            ORDER BY symbol ASC, timeframe ASC, started_at ASC
            LIMIT ?
            """,
            [*parameters, config.batch_size],
        ).fetchall()

        if not rows:
            return

        yield rows
        last_row = rows[-1]
        after_key = SQLiteCursorKey(
            symbol=str(last_row["symbol"]),
            timeframe=str(last_row["timeframe"]),
            started_at=str(last_row["started_at"]),
        )


def build_sqlite_filters(
    *,
    config: BackfillConfig,
    after_key: SQLiteCursorKey | None,
) -> tuple[list[str], list[object]]:
    conditions: list[str] = []
    parameters: list[object] = []

    if config.symbols:
        conditions.append(build_in_clause("symbol", config.symbols))
        parameters.extend(config.symbols)
    if config.timeframes:
        conditions.append(build_in_clause("timeframe", config.timeframes))
        parameters.extend(config.timeframes)
    if config.start_at is not None:
        conditions.append("started_at >= ?")
        parameters.append(serialize_datetime(config.start_at))
    if config.end_at is not None:
        conditions.append("started_at <= ?")
        parameters.append(serialize_datetime(config.end_at))
    if after_key is not None:
        conditions.append(
            "("
            "symbol > ? OR "
            "(symbol = ? AND timeframe > ?) OR "
            "(symbol = ? AND timeframe = ? AND started_at > ?)"
            ")"
        )
        parameters.extend(
            [
                after_key.symbol,
                after_key.symbol,
                after_key.timeframe,
                after_key.symbol,
                after_key.timeframe,
                after_key.started_at,
            ]
        )

    return conditions, parameters


def build_in_clause(column_name: str, values: Sequence[str]) -> str:
    placeholders = ", ".join("?" for _ in values)
    return f"{column_name} IN ({placeholders})"


def row_to_chart_candle(row: Mapping[str, object]) -> ChartCandle:
    started_at = parse_datetime(_as_optional_str(_row_value(row, "started_at")))
    ended_at = parse_datetime(_as_optional_str(_row_value(row, "ended_at")))
    updated_at = parse_datetime(_as_optional_str(_row_value(row, "updated_at")))

    if started_at is None or ended_at is None or updated_at is None:
        raise ValueError("SQLite chart_candles row is missing started_at, ended_at, or updated_at.")

    source_started_at = parse_datetime(_as_optional_str(_row_value(row, "source_started_at"))) or started_at
    source_timezone = _as_optional_str(_row_value(row, "source_timezone"))

    return ChartCandle(
        symbol=str(_row_value(row, "symbol")),
        timeframe=Timeframe(str(_row_value(row, "timeframe"))),
        started_at=started_at,
        ended_at=ended_at,
        source_started_at=source_started_at,
        open=float(_row_value(row, "open")),
        high=float(_row_value(row, "high")),
        low=float(_row_value(row, "low")),
        close=float(_row_value(row, "close")),
        volume=int(_row_value(row, "volume")),
        tick_volume=int(_row_value(row, "tick_volume")),
        delta=int(_row_value(row, "delta")),
        updated_at=updated_at,
        source_timezone=source_timezone or None,
    )


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _row_value(row: Mapping[str, object], key: str) -> object:
    return row[key]


def initialize_clickhouse_repository(
    app_config: AppConfig,
    backfill_config: BackfillConfig,
) -> ClickHouseChartCandleRepository:
    repository = ClickHouseChartCandleRepository(
        host=app_config.clickhouse_host,
        port=app_config.clickhouse_port,
        username=app_config.clickhouse_user,
        password=app_config.clickhouse_password,
        database=app_config.clickhouse_database,
        table=app_config.clickhouse_chart_candles_table,
        workspace_root=backfill_config.sqlite_path.parent.parent,
    )

    last_error: Exception | None = None
    for attempt in range(1, backfill_config.connect_retries + 1):
        try:
            repository.initialize()
            return repository
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "ClickHouse initialization attempt %s/%s failed: %s",
                attempt,
                backfill_config.connect_retries,
                exc,
            )
            time.sleep(backfill_config.retry_delay_seconds * attempt)

    raise RuntimeError("Unable to initialize ClickHouse chart candle repository after retries.") from last_error


def run_backfill(app_config: AppConfig, backfill_config: BackfillConfig) -> None:
    if backfill_config.start_at and backfill_config.end_at and backfill_config.start_at > backfill_config.end_at:
        raise ValueError("--start must be earlier than or equal to --end.")

    repository = None
    if not backfill_config.dry_run:
        repository = initialize_clickhouse_repository(app_config, backfill_config)

    migrated_rows = 0
    batches = 0
    started = time.perf_counter()

    with open_sqlite_connection(backfill_config.sqlite_path) as connection:
        total_rows = count_matching_chart_candles(connection, backfill_config)
        LOGGER.info("Found %s SQLite chart_candles rows to process.", total_rows)
        if total_rows == 0:
            return

        for batch_rows in iter_sqlite_chart_candle_batches(connection, backfill_config):
            candles = [row_to_chart_candle(row) for row in batch_rows]
            if repository is not None:
                repository.upsert_chart_candles(candles)
            migrated_rows += len(candles)
            batches += 1

            if batches == 1 or batches % 10 == 0 or migrated_rows >= total_rows:
                LOGGER.info(
                    "Processed %s/%s rows across %s batch(es).",
                    migrated_rows,
                    total_rows,
                    batches,
                )

    elapsed = time.perf_counter() - started
    mode = "dry-run scanned" if backfill_config.dry_run else "migrated"
    LOGGER.info(
        "SQLite -> ClickHouse chart_candles backfill complete: %s %s rows in %.2fs.",
        mode,
        migrated_rows,
        elapsed,
    )


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    app_config = AppConfig.from_env()
    args = parse_args(argv)
    backfill_config = build_backfill_config(args, app_config)
    run_backfill(app_config, backfill_config)


if __name__ == "__main__":
    main()
