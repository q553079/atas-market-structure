"""Initialize ClickHouse database and base table for ATAS tick data.

Usage:
  python scripts/init_clickhouse.py

Environment variables:
  CLICKHOUSE_HOST (default: 127.0.0.1)
  CLICKHOUSE_PORT (default: 8123)
  CLICKHOUSE_USER (default: default)
  CLICKHOUSE_PASSWORD (default: "")
  CLICKHOUSE_DB (default: market_data)
"""

from __future__ import annotations

import os

import clickhouse_connect


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def build_ddl(database: str) -> list[str]:
    create_db_sql = f"CREATE DATABASE IF NOT EXISTS {database}"

    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {database}.ticks_raw
    (
        symbol LowCardinality(String),
        event_time DateTime64(3, 'UTC'),
        price Float64,
        volume UInt32,
        direction Enum8('Bid' = 1, 'Ask' = 2),
        ts_unix_ms UInt64,
        event_date Date MATERIALIZED toDate(event_time),
        ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
    )
    ENGINE = MergeTree
    PARTITION BY (symbol, event_date)
    ORDER BY (symbol, event_time)
    SETTINGS index_granularity = 8192
    """

    return [create_db_sql, create_table_sql]


def main() -> None:
    host = _env("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(_env("CLICKHOUSE_PORT", "8123"))
    username = _env("CLICKHOUSE_USER", "default")
    password = _env("CLICKHOUSE_PASSWORD", "")
    database = _env("CLICKHOUSE_DB", "market_data")

    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=username,
        password=password,
    )

    for sql in build_ddl(database):
        client.command(sql)

    print(f"ClickHouse initialized: {database}.ticks_raw")


if __name__ == "__main__":
    main()
