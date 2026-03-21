from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Iterator, Sequence

from atas_market_structure.config import AppConfig
from atas_market_structure.repository import StoredIngestion
from atas_market_structure.repository_clickhouse import ClickHouseChartCandleRepository


LOGGER = logging.getLogger("atas_market_structure.ingestion_backfill")


@dataclass(frozen=True)
class BackfillConfig:
    sqlite_path: Path
    batch_size: int = 5000
    ingestion_kinds: tuple[str, ...] = ()
    instrument_symbol: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    dry_run: bool = False
    connect_retries: int = 5
    retry_delay_seconds: float = 1.5


@dataclass(frozen=True)
class SQLiteCursorKey:
    stored_at: str
    ingestion_id: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill existing SQLite ingestions rows into the ClickHouse ingestions store."
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
        help="How many ingestion rows to read from SQLite and insert into ClickHouse per batch.",
    )
    parser.add_argument(
        "--ingestion-kinds",
        nargs="*",
        default=[],
        help="Optional ingestion kind allowlist, for example --ingestion-kinds adapter_continuous_state replay_workbench_snapshot.",
    )
    parser.add_argument(
        "--instrument-symbol",
        default=None,
        help="Optional instrument symbol filter, for example NQ.",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Optional inclusive UTC lower bound on stored_at, ISO-8601 format.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional inclusive UTC upper bound on stored_at, ISO-8601 format.",
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

    ingestion_kinds = tuple(
        dict.fromkeys(item.strip() for item in args.ingestion_kinds if item.strip())
    )
    instrument_symbol = args.instrument_symbol.strip().upper() if isinstance(args.instrument_symbol, str) and args.instrument_symbol.strip() else None

    return BackfillConfig(
        sqlite_path=sqlite_path,
        batch_size=max(1, int(args.batch_size)),
        ingestion_kinds=ingestion_kinds,
        instrument_symbol=instrument_symbol,
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
    return normalize_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def open_sqlite_connection(sqlite_path: Path) -> sqlite3.Connection:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def count_matching_ingestions(connection: sqlite3.Connection, config: BackfillConfig) -> int:
    conditions, parameters = build_sqlite_filters(config=config, after_key=None)
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    row = connection.execute(
        f"SELECT COUNT(*) AS row_count FROM ingestions WHERE {where_clause}",
        parameters,
    ).fetchone()
    return int(row["row_count"]) if row is not None else 0


def iter_sqlite_ingestion_batches(
    connection: sqlite3.Connection,
    config: BackfillConfig,
) -> Iterator[list[sqlite3.Row]]:
    after_key: SQLiteCursorKey | None = None
    while True:
        conditions, parameters = build_sqlite_filters(config=config, after_key=after_key)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        rows = connection.execute(
            f"""
            SELECT
                ingestion_id,
                ingestion_kind,
                source_snapshot_id,
                instrument_symbol,
                observed_payload_json,
                stored_at
            FROM ingestions
            WHERE {where_clause}
            ORDER BY stored_at ASC, ingestion_id ASC
            LIMIT ?
            """,
            [*parameters, config.batch_size],
        ).fetchall()

        if not rows:
            return

        yield rows
        last_row = rows[-1]
        after_key = SQLiteCursorKey(
            stored_at=str(last_row["stored_at"]),
            ingestion_id=str(last_row["ingestion_id"]),
        )


def build_sqlite_filters(
    *,
    config: BackfillConfig,
    after_key: SQLiteCursorKey | None,
) -> tuple[list[str], list[object]]:
    conditions: list[str] = []
    parameters: list[object] = []

    if config.ingestion_kinds:
        placeholders = ", ".join("?" for _ in config.ingestion_kinds)
        conditions.append(f"ingestion_kind IN ({placeholders})")
        parameters.extend(config.ingestion_kinds)
    if config.instrument_symbol is not None:
        conditions.append("instrument_symbol = ?")
        parameters.append(config.instrument_symbol)
    if config.start_at is not None:
        conditions.append("stored_at >= ?")
        parameters.append(serialize_datetime(config.start_at))
    if config.end_at is not None:
        conditions.append("stored_at <= ?")
        parameters.append(serialize_datetime(config.end_at))
    if after_key is not None:
        conditions.append("(stored_at > ? OR (stored_at = ? AND ingestion_id > ?))")
        parameters.extend([after_key.stored_at, after_key.stored_at, after_key.ingestion_id])

    return conditions, parameters


def row_to_stored_ingestion(row: sqlite3.Row) -> StoredIngestion:
    stored_at = parse_datetime(str(row["stored_at"]))
    if stored_at is None:
        raise ValueError("SQLite ingestions row is missing stored_at.")

    return StoredIngestion(
        ingestion_id=str(row["ingestion_id"]),
        ingestion_kind=str(row["ingestion_kind"]),
        source_snapshot_id=str(row["source_snapshot_id"]),
        instrument_symbol=str(row["instrument_symbol"]),
        observed_payload=json.loads(str(row["observed_payload_json"])),
        stored_at=stored_at,
    )


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
        ingestions_table=app_config.clickhouse_ingestions_table,
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

    raise RuntimeError("Unable to initialize ClickHouse ingestion repository after retries.") from last_error


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
        total_rows = count_matching_ingestions(connection, backfill_config)
        LOGGER.info("Found %s SQLite ingestions rows to process.", total_rows)
        if total_rows == 0:
            return

        for batch_rows in iter_sqlite_ingestion_batches(connection, backfill_config):
            ingestions = [row_to_stored_ingestion(row) for row in batch_rows]
            if repository is not None:
                repository.save_ingestions(ingestions)
            migrated_rows += len(ingestions)
            batches += 1

            if batches == 1 or batches % 10 == 0 or migrated_rows >= total_rows:
                LOGGER.info(
                    "Processed %s/%s ingestion rows across %s batch(es).",
                    migrated_rows,
                    total_rows,
                    batches,
                )

    elapsed = time.perf_counter() - started
    mode = "dry-run scanned" if backfill_config.dry_run else "migrated"
    LOGGER.info(
        "SQLite -> ClickHouse ingestion backfill complete: %s %s rows in %.2fs.",
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
