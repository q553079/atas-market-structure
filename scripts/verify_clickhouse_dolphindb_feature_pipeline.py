from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
import sys
from uuid import uuid4

import pandas as pd
from pandas.testing import assert_frame_equal


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import clickhouse_dolphindb_feature_pipeline as pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the ClickHouse -> DolphinDB -> ClickHouse feature pipeline.")
    parser.add_argument("--ch-host", default="127.0.0.1")
    parser.add_argument("--ch-port", type=int, default=8123)
    parser.add_argument("--ch-user", default="default")
    parser.add_argument("--ch-password", default="")
    parser.add_argument("--ch-database", default="market_data")
    parser.add_argument("--ddb-host", default="127.0.0.1")
    parser.add_argument("--ddb-port", type=int, default=8848)
    parser.add_argument("--ddb-user", default="admin")
    parser.add_argument("--ddb-password", default="123456")
    parser.add_argument(
        "--keep-tables",
        action="store_true",
        help="Keep the temporary ClickHouse tables after the verification run for debugging.",
    )
    return parser.parse_args()


def build_clickhouse_config(args: argparse.Namespace, raw_table: str, feature_table: str) -> pipeline.ClickHouseConfig:
    return pipeline.ClickHouseConfig(
        host=args.ch_host,
        port=args.ch_port,
        username=args.ch_user,
        password=args.ch_password,
        database=args.ch_database,
        raw_table=raw_table,
        feature_table=feature_table,
    )


def build_dolphindb_config(args: argparse.Namespace) -> pipeline.DolphinDBConfig:
    return pipeline.DolphinDBConfig(
        host=args.ddb_host,
        port=args.ddb_port,
        username=args.ddb_user,
        password=args.ddb_password,
    )


def create_database_and_tables(client, config: pipeline.ClickHouseConfig) -> None:
    client.command(f"CREATE DATABASE IF NOT EXISTS {pipeline.quote_identifier(config.database)}")

    raw_table_name = f"{config.database}.{config.raw_table}"
    raw_ddl = f"""
    CREATE TABLE IF NOT EXISTS {pipeline.quote_identifier(raw_table_name)}
    (
        symbol String,
        timestamp DateTime64(3, 'UTC'),
        price Float64,
        volume Int32,
        direction String
    )
    ENGINE = MergeTree
    PARTITION BY (symbol, toYYYYMM(timestamp))
    ORDER BY (symbol, timestamp)
    """
    client.command(raw_ddl)
    pipeline.ensure_feature_table(client, config)


def build_synthetic_ticks(base_time: datetime, symbol_a: str, symbol_b: str) -> tuple[list[list[object]], pd.DataFrame]:
    rows = [
        [symbol_a, base_time + timedelta(seconds=5, milliseconds=100), 100.0, 3, "Ask"],
        [symbol_a, base_time + timedelta(seconds=20, milliseconds=200), 101.5, 2, "Ask"],
        [symbol_a, base_time + timedelta(seconds=40, milliseconds=300), 99.5, 4, "Bid"],
        [symbol_a, base_time + timedelta(minutes=1, seconds=10, milliseconds=100), 102.0, 1, "Bid"],
        [symbol_a, base_time + timedelta(minutes=1, seconds=50, milliseconds=200), 103.0, 5, "Ask"],
        [symbol_b, base_time + timedelta(seconds=15), 200.0, 2, "Bid"],
        [symbol_b, base_time + timedelta(seconds=45), 201.0, 7, "Ask"],
    ]

    expected = pd.DataFrame(
        [
            [symbol_a, base_time, 100.0, 101.5, 99.5, 99.5, 9, 1],
            [symbol_a, base_time + timedelta(minutes=1), 102.0, 103.0, 102.0, 103.0, 6, 4],
            [symbol_b, base_time, 200.0, 201.0, 200.0, 201.0, 9, 5],
        ],
        columns=list(pipeline.FEATURE_COLUMNS),
    )
    return rows, expected


def insert_ticks(client, config: pipeline.ClickHouseConfig, rows: list[list[object]]) -> None:
    raw_table_name = f"{config.database}.{config.raw_table}"
    client.insert(
        raw_table_name,
        rows,
        column_names=["symbol", "timestamp", "price", "volume", "direction"],
    )


def fetch_features(client, config: pipeline.ClickHouseConfig) -> pd.DataFrame:
    feature_table_name = f"{config.database}.{config.feature_table}"
    query = f"""
    SELECT
        symbol,
        window_time,
        open,
        high,
        low,
        close,
        total_volume,
        delta
    FROM {pipeline.quote_identifier(feature_table_name)}
    ORDER BY symbol, window_time
    """
    feature_df = client.query_df(query)
    return normalize_feature_dataframe(feature_df)


def normalize_feature_dataframe(feature_df: pd.DataFrame) -> pd.DataFrame:
    if feature_df.empty:
        return feature_df

    normalized = feature_df.loc[:, pipeline.FEATURE_COLUMNS].copy()
    normalized["symbol"] = normalized["symbol"].astype("string")
    normalized["window_time"] = pd.to_datetime(normalized["window_time"], utc=True).dt.floor("s")
    normalized["open"] = normalized["open"].astype("float64")
    normalized["high"] = normalized["high"].astype("float64")
    normalized["low"] = normalized["low"].astype("float64")
    normalized["close"] = normalized["close"].astype("float64")
    normalized["total_volume"] = normalized["total_volume"].astype("int32")
    normalized["delta"] = normalized["delta"].astype("int32")
    return normalized.sort_values(["symbol", "window_time"]).reset_index(drop=True)


def drop_temp_tables(client, config: pipeline.ClickHouseConfig) -> None:
    client.command(f"DROP TABLE IF EXISTS {pipeline.quote_identifier(f'{config.database}.{config.feature_table}')}")
    client.command(f"DROP TABLE IF EXISTS {pipeline.quote_identifier(f'{config.database}.{config.raw_table}')}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    args = parse_args()
    suffix = uuid4().hex[:8]
    raw_table = f"market_ticks_selfcheck_{suffix}"
    feature_table = f"market_features_1m_selfcheck_{suffix}"
    symbol_a = f"CHK_{suffix}_A"
    symbol_b = f"CHK_{suffix}_B"
    base_time = datetime(2026, 3, 1, 14, 30, tzinfo=UTC)

    ch_config = build_clickhouse_config(args, raw_table=raw_table, feature_table=feature_table)
    ddb_config = build_dolphindb_config(args)
    bootstrap_config = pipeline.ClickHouseConfig(
        host=args.ch_host,
        port=args.ch_port,
        username=args.ch_user,
        password=args.ch_password,
        database="default",
    )
    bootstrap_client = pipeline.connect_clickhouse(bootstrap_config)
    try:
        create_database_and_tables(bootstrap_client, ch_config)
    finally:
        bootstrap_client.close()

    ch_client = pipeline.connect_clickhouse(ch_config)

    try:
        rows, expected_df = build_synthetic_ticks(base_time, symbol_a, symbol_b)
        insert_ticks(ch_client, ch_config, rows)

        pipeline.run_pipeline(
            ch_config=ch_config,
            ddb_config=ddb_config,
            pipeline_config=pipeline.PipelineConfig(
                symbols=(symbol_a, symbol_b),
                start_time=base_time,
                end_time=base_time + timedelta(minutes=2),
                chunk_days=1,
            ),
        )

        actual_df = fetch_features(ch_client, ch_config)
        expected_df = normalize_feature_dataframe(expected_df)
        assert_frame_equal(actual_df, expected_df, check_dtype=False, check_exact=True)
        print("ClickHouse -> DolphinDB -> ClickHouse pipeline verification passed.")
        print(f"Temporary feature table: {ch_config.database}.{ch_config.feature_table}")
    finally:
        try:
            ch_client.close()
        finally:
            if not args.keep_tables:
                cleanup_client = pipeline.connect_clickhouse(ch_config)
                try:
                    drop_temp_tables(cleanup_client, ch_config)
                finally:
                    cleanup_client.close()


if __name__ == "__main__":
    main()
