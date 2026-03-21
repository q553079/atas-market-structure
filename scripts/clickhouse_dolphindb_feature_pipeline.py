from __future__ import annotations

"""
Feature pipeline: ClickHouse -> Pandas -> DolphinDB -> ClickHouse

This script is designed for Windows + Docker (WSL2) local deployments where:
1. Raw tick data is stored in ClickHouse.
2. Complex feature extraction is performed in an in-memory DolphinDB node.
3. Aggregated 1-minute features are written back to ClickHouse.

Recommended Python packages:
    pip install clickhouse-connect dolphindb pandas pyarrow

Example:
    python scripts/clickhouse_dolphindb_feature_pipeline.py ^
        --symbols NQ ES YM ^
        --start 2026-02-01T00:00:00Z ^
        --end 2026-03-01T00:00:00Z
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gc
import logging
import time
from typing import Iterator, Sequence
from uuid import uuid4

import clickhouse_connect
import dolphindb as ddb
import dolphindb.settings as ddb_keys
import pandas as pd


LOGGER = logging.getLogger("clickhouse_dolphindb_feature_pipeline")


@dataclass(frozen=True)
class ClickHouseConfig:
    host: str = "127.0.0.1"
    port: int = 8123
    username: str = "default"
    password: str = ""
    database: str = "default"
    raw_table: str = "market_ticks"
    feature_table: str = "market_features_1m"
    connect_retries: int = 5
    retry_delay_seconds: float = 1.5


@dataclass(frozen=True)
class DolphinDBConfig:
    host: str = "127.0.0.1"
    port: int = 8848
    username: str = "admin"
    password: str = "123456"
    connect_retries: int = 5
    retry_delay_seconds: float = 1.5


@dataclass(frozen=True)
class PipelineConfig:
    symbols: tuple[str, ...]
    start_time: datetime
    end_time: datetime
    chunk_days: int = 1


FEATURE_COLUMNS = (
    "symbol",
    "window_time",
    "open",
    "high",
    "low",
    "close",
    "total_volume",
    "delta",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 1-minute OHLCV + delta features with DolphinDB.")
    parser.add_argument("--symbols", nargs="+", default=["NQ", "ES", "YM"], help="List of futures symbols.")
    parser.add_argument(
        "--start",
        default=None,
        help="UTC start time in ISO-8601 format, for example 2026-02-01T00:00:00Z.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="UTC end time in ISO-8601 format, for example 2026-03-01T00:00:00Z.",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=1,
        help="Process the requested range in day-sized chunks to control Python and DolphinDB memory usage.",
    )
    parser.add_argument("--ch-host", default="127.0.0.1")
    parser.add_argument("--ch-port", type=int, default=8123)
    parser.add_argument("--ch-user", default="default")
    parser.add_argument("--ch-password", default="")
    parser.add_argument("--ch-database", default="default")
    parser.add_argument("--ch-raw-table", default="market_ticks")
    parser.add_argument("--ch-feature-table", default="market_features_1m")
    parser.add_argument("--ddb-host", default="127.0.0.1")
    parser.add_argument("--ddb-port", type=int, default=8848)
    parser.add_argument("--ddb-user", default="admin")
    parser.add_argument("--ddb-password", default="123456")
    return parser.parse_args()


def parse_utc_datetime(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_pipeline_config(args: argparse.Namespace) -> tuple[ClickHouseConfig, DolphinDBConfig, PipelineConfig]:
    utc_now = datetime.now(timezone.utc)
    default_end = utc_now
    default_start = utc_now - timedelta(days=30)

    clickhouse_config = ClickHouseConfig(
        host=args.ch_host,
        port=args.ch_port,
        username=args.ch_user,
        password=args.ch_password,
        database=args.ch_database,
        raw_table=args.ch_raw_table,
        feature_table=args.ch_feature_table,
    )
    dolphindb_config = DolphinDBConfig(
        host=args.ddb_host,
        port=args.ddb_port,
        username=args.ddb_user,
        password=args.ddb_password,
    )
    pipeline_config = PipelineConfig(
        symbols=tuple(dict.fromkeys(symbol.strip().upper() for symbol in args.symbols if symbol.strip())),
        start_time=parse_utc_datetime(args.start, default_start),
        end_time=parse_utc_datetime(args.end, default_end),
        chunk_days=max(1, args.chunk_days),
    )
    return clickhouse_config, dolphindb_config, pipeline_config


def connect_clickhouse(config: ClickHouseConfig):
    last_error: Exception | None = None
    for attempt in range(1, config.connect_retries + 1):
        try:
            client = clickhouse_connect.get_client(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                database=config.database,
            )
            client.query("SELECT 1")
            return client
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            last_error = exc
            LOGGER.warning(
                "ClickHouse connection attempt %s/%s failed: %s",
                attempt,
                config.connect_retries,
                exc,
            )
            time.sleep(config.retry_delay_seconds * attempt)
    raise RuntimeError("Unable to connect to ClickHouse after retries.") from last_error


def connect_dolphindb(config: DolphinDBConfig) -> ddb.Session:
    last_error: Exception | None = None
    for attempt in range(1, config.connect_retries + 1):
        try:
            session = ddb.Session(show_output=False)
            session.connect(config.host, config.port, config.username, config.password)
            session.run("1+1")
            return session
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            last_error = exc
            LOGGER.warning(
                "DolphinDB connection attempt %s/%s failed: %s",
                attempt,
                config.connect_retries,
                exc,
            )
            time.sleep(config.retry_delay_seconds * attempt)
    raise RuntimeError("Unable to connect to DolphinDB after retries.") from last_error


def quote_identifier(identifier: str) -> str:
    parts = [part.strip() for part in identifier.split(".") if part.strip()]
    return ".".join(f"`{part}`" for part in parts)


def quote_string_list(values: Sequence[str]) -> str:
    escaped_values = []
    for value in values:
        escaped_values.append("'" + value.replace("'", "''") + "'")
    return ", ".join(escaped_values)


def to_ch_datetime64_literal(ts: datetime) -> str:
    utc_ts = ts.astimezone(timezone.utc)
    return utc_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def ensure_feature_table(client, config: ClickHouseConfig) -> None:
    full_table_name = f"{config.database}.{config.feature_table}"
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {quote_identifier(full_table_name)}
    (
        symbol String,
        window_time DateTime('UTC'),
        open Float64,
        high Float64,
        low Float64,
        close Float64,
        total_volume Int32,
        delta Int32
    )
    ENGINE = MergeTree
    PARTITION BY (symbol, toYYYYMM(window_time))
    ORDER BY (symbol, window_time)
    """
    client.command(ddl)


def iter_time_chunks(start_time: datetime, end_time: datetime, chunk_days: int) -> Iterator[tuple[datetime, datetime]]:
    cursor = start_time
    step = timedelta(days=chunk_days)
    while cursor < end_time:
        chunk_end = min(cursor + step, end_time)
        yield cursor, chunk_end
        cursor = chunk_end


def fetch_ticks_dataframe(
    client,
    config: ClickHouseConfig,
    symbols: Sequence[str],
    chunk_start: datetime,
    chunk_end: datetime,
) -> pd.DataFrame:
    full_raw_table = f"{config.database}.{config.raw_table}"
    query = f"""
    SELECT
        symbol,
        timestamp AS event_time,
        price,
        toInt32(volume) AS volume,
        direction
    FROM {quote_identifier(full_raw_table)}
    WHERE symbol IN ({quote_string_list(symbols)})
      AND timestamp >= toDateTime64('{to_ch_datetime64_literal(chunk_start)}', 3, 'UTC')
      AND timestamp < toDateTime64('{to_ch_datetime64_literal(chunk_end)}', 3, 'UTC')
    ORDER BY symbol, event_time
    """

    df = client.query_df(query)
    if df.empty:
        return df

    df["symbol"] = df["symbol"].astype("string")
    df["direction"] = df["direction"].astype("string")
    df["price"] = df["price"].astype("float64")
    df["volume"] = df["volume"].astype("int32")
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)
    return df


def upload_ticks_to_dolphindb(session: ddb.Session, ticks_df: pd.DataFrame, temp_table_name: str) -> None:
    # Explicit DolphinDB types reduce ambiguity during upload and make the
    # downstream aggregation script more predictable.
    ticks_df.__DolphinDB_Type__ = {
        "symbol": ddb_keys.DT_SYMBOL,
        "event_time": ddb_keys.DT_NANOTIMESTAMP,
        "price": ddb_keys.DT_DOUBLE,
        "volume": ddb_keys.DT_INT,
        "direction": ddb_keys.DT_SYMBOL,
    }
    session.upload({temp_table_name: ticks_df})


def compute_features_in_dolphindb(session: ddb.Session, temp_table_name: str) -> pd.DataFrame:
    script = f"""
    select
        symbol,
        bar(event_time, 1m) as window_time,
        first(price) as open,
        max(price) as high,
        min(price) as low,
        last(price) as close,
        int(sum(volume)) as total_volume,
        int(sum(iif(direction = `Ask, volume, -volume))) as delta
    from {temp_table_name}
    group by symbol, bar(event_time, 1m)
    order by symbol, window_time
    """
    result = session.run(script)
    if isinstance(result, pd.DataFrame):
        return result
    return pd.DataFrame(result)


def cleanup_dolphindb_table(session: ddb.Session, temp_table_name: str) -> None:
    try:
        session.undef(temp_table_name, "VAR")
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        LOGGER.warning("Failed to release DolphinDB temp table %s: %s", temp_table_name, exc)


def normalize_feature_dataframe(feature_df: pd.DataFrame) -> pd.DataFrame:
    if feature_df.empty:
        return feature_df

    normalized = feature_df.loc[:, FEATURE_COLUMNS].copy()
    normalized["symbol"] = normalized["symbol"].astype("string")
    normalized["open"] = normalized["open"].astype("float64")
    normalized["high"] = normalized["high"].astype("float64")
    normalized["low"] = normalized["low"].astype("float64")
    normalized["close"] = normalized["close"].astype("float64")
    normalized["total_volume"] = normalized["total_volume"].astype("int32")
    normalized["delta"] = normalized["delta"].astype("int32")

    window_time = pd.to_datetime(normalized["window_time"], utc=True)
    # ClickHouse target column is DateTime('UTC'), so we normalize to second precision.
    normalized["window_time"] = window_time.dt.floor("s").dt.to_pydatetime()
    return normalized


def insert_features_into_clickhouse(client, config: ClickHouseConfig, feature_df: pd.DataFrame) -> None:
    if feature_df.empty:
        return

    full_feature_table = f"{config.database}.{config.feature_table}"
    row_data = feature_df.loc[:, FEATURE_COLUMNS].to_numpy().tolist()
    client.insert(
        full_feature_table,
        row_data,
        column_names=list(FEATURE_COLUMNS),
    )


def process_chunk(
    ch_client,
    ddb_session: ddb.Session,
    ch_config: ClickHouseConfig,
    pipeline_config: PipelineConfig,
    chunk_start: datetime,
    chunk_end: datetime,
) -> None:
    ticks_df = fetch_ticks_dataframe(
        client=ch_client,
        config=ch_config,
        symbols=pipeline_config.symbols,
        chunk_start=chunk_start,
        chunk_end=chunk_end,
    )
    if ticks_df.empty:
        LOGGER.info("No tick data found for %s -> %s", chunk_start.isoformat(), chunk_end.isoformat())
        return

    temp_table_name = f"ticks_tmp_{uuid4().hex}"
    LOGGER.info(
        "Loaded %s tick rows from ClickHouse for %s -> %s",
        len(ticks_df),
        chunk_start.isoformat(),
        chunk_end.isoformat(),
    )

    try:
        upload_ticks_to_dolphindb(ddb_session, ticks_df, temp_table_name)
        features_df = compute_features_in_dolphindb(ddb_session, temp_table_name)
        features_df = normalize_feature_dataframe(features_df)
        insert_features_into_clickhouse(ch_client, ch_config, features_df)
        LOGGER.info(
            "Wrote %s feature rows back to ClickHouse for %s -> %s",
            len(features_df),
            chunk_start.isoformat(),
            chunk_end.isoformat(),
        )
    finally:
        # Always release DolphinDB-side objects before moving to the next chunk.
        cleanup_dolphindb_table(ddb_session, temp_table_name)

        # Release Python-side objects eagerly as well because a month of ticks
        # across multiple futures symbols can become very large.
        del ticks_df
        if "features_df" in locals():
            del features_df
        gc.collect()


def run_pipeline(
    ch_config: ClickHouseConfig,
    ddb_config: DolphinDBConfig,
    pipeline_config: PipelineConfig,
) -> None:
    if not pipeline_config.symbols:
        raise ValueError("At least one symbol must be provided.")
    if pipeline_config.start_time >= pipeline_config.end_time:
        raise ValueError("start_time must be earlier than end_time.")

    ch_client = connect_clickhouse(ch_config)
    ddb_session = connect_dolphindb(ddb_config)

    try:
        ensure_feature_table(ch_client, ch_config)
        for chunk_start, chunk_end in iter_time_chunks(
            pipeline_config.start_time,
            pipeline_config.end_time,
            pipeline_config.chunk_days,
        ):
            process_chunk(
                ch_client=ch_client,
                ddb_session=ddb_session,
                ch_config=ch_config,
                pipeline_config=pipeline_config,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
            )
    finally:
        try:
            ddb_session.close()
        except Exception:  # pragma: no cover - depends on runtime environment
            LOGGER.warning("Failed to close DolphinDB session cleanly.", exc_info=True)
        try:
            ch_client.close()
        except Exception:  # pragma: no cover - depends on runtime environment
            LOGGER.warning("Failed to close ClickHouse client cleanly.", exc_info=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    args = parse_args()
    ch_config, ddb_config, pipeline_config = build_pipeline_config(args)
    run_pipeline(ch_config, ddb_config, pipeline_config)


if __name__ == "__main__":
    main()
