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
import time

import clickhouse_connect


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _ticks_to_chart_candles_mv_ddl(database: str, *, timeframe: str, interval_seconds: int) -> str:
    interval_label = f"{interval_seconds}s"
    return f"""
    CREATE MATERIALIZED VIEW IF NOT EXISTS {database}.ticks_raw_to_chart_candles_{interval_label}_mv
    TO {database}.chart_candles
    AS
    SELECT
        symbol AS symbol,
        '{timeframe}' AS timeframe,
        bucket_start AS started_at,
        bucket_start + toIntervalSecond({interval_seconds - 1}) AS ended_at,
        min(event_time) AS source_started_at,
        argMin(price, event_time) AS open,
        max(price) AS high,
        min(price) AS low,
        argMax(price, event_time) AS close,
        toInt64(sum(trade_volume)) AS volume,
        toInt64(count()) AS tick_volume,
        toInt64(sum(if(direction = 'Ask', toInt64(trade_volume), -toInt64(trade_volume)))) AS delta,
        max(event_time) AS updated_at
    FROM
    (
        SELECT
            symbol,
            event_time,
            price,
            volume AS trade_volume,
            direction,
            toStartOfInterval(event_time, INTERVAL {interval_seconds} second, 'UTC') AS bucket_start
        FROM {database}.ticks_raw
    )
    GROUP BY symbol, bucket_start
    """


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

    chart_candles_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {database}.chart_candles
    (
        symbol LowCardinality(String),
        timeframe LowCardinality(String),
        started_at DateTime64(3, 'UTC'),
        ended_at DateTime64(3, 'UTC'),
        source_started_at DateTime64(3, 'UTC'),
        open Float64,
        high Float64,
        low Float64,
        close Float64,
        volume Int64,
        tick_volume Int64,
        delta Int64,
        updated_at DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(updated_at)
    PARTITION BY (symbol, toYYYYMM(started_at))
    ORDER BY (symbol, timeframe, started_at, source_started_at)
    """

    ingestions_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {database}.ingestions
    (
        ingestion_id String,
        ingestion_kind LowCardinality(String),
        source_snapshot_id String,
        instrument_symbol LowCardinality(String),
        chart_instance_id Nullable(String),
        message_id Nullable(String),
        message_type Nullable(String),
        observed_window_start Nullable(DateTime64(3, 'UTC')),
        observed_window_end Nullable(DateTime64(3, 'UTC')),
        emitted_at Nullable(DateTime64(3, 'UTC')),
        observed_payload_json String,
        stored_at DateTime64(3, 'UTC'),
        version_at DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(version_at)
    PARTITION BY (ingestion_kind, toYYYYMM(stored_at))
    ORDER BY (ingestion_kind, instrument_symbol, source_snapshot_id, stored_at, ingestion_id)
    """

    ticks_to_chart_candles_mv_ddls = [
        _ticks_to_chart_candles_mv_ddl(database, timeframe="1m", interval_seconds=60),
        _ticks_to_chart_candles_mv_ddl(database, timeframe="5m", interval_seconds=300),
        _ticks_to_chart_candles_mv_ddl(database, timeframe="15m", interval_seconds=900),
        _ticks_to_chart_candles_mv_ddl(database, timeframe="30m", interval_seconds=1800),
        _ticks_to_chart_candles_mv_ddl(database, timeframe="1h", interval_seconds=3600),
        _ticks_to_chart_candles_mv_ddl(database, timeframe="4h", interval_seconds=14400),
    ]

    # ─── Pre-aggregated continuous-state candle view ──────────────────────────
    # Aggregates adapter_continuous_state messages into 1-minute buckets.
    # Replaces the need to query + re-aggregate 109,000+ raw JSON messages
    # on every UI build request.  Sub-100ms queries regardless of window size.
    continuous_state_candles_ddl = f"""
    CREATE TABLE IF NOT EXISTS {database}.continuous_state_candles
    (
        symbol             LowCardinality(String),
        timeframe          LowCardinality(String),
        bucket_start       DateTime64(3, 'UTC'),
        open_price         Float64,
        high_price        Float64,
        low_price         Float64,
        close_price       Float64,
        volume             Int64,
        net_delta         Int64,
        aggressive_buy    Int64,
        aggressive_sell   Int64,
        msg_count          UInt32,
        has_trade          UInt8,
        has_replenish      UInt8,
        has_liquidity      UInt8,
        has_drive          UInt8,
        has_phr            UInt8,
        latest_price       Float64,
        latest_observed_at DateTime64(3, 'UTC'),
        stored_at          DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(stored_at)
    PARTITION BY (symbol, toYYYYMMDD(bucket_start))
    ORDER BY (symbol, timeframe, bucket_start)
    """

    continuous_state_mv_ddl = f"""
    CREATE MATERIALIZED VIEW IF NOT EXISTS {database}.continuous_state_candles_mv
    TO {database}.continuous_state_candles
    AS
    SELECT
        instrument_symbol                                                    AS symbol,
        '1m'                                                                 AS timeframe,
        toStartOfInterval(
            toDateTime64(observed_window_end, 3, 'UTC'),
            INTERVAL 1 minute
        )                                                                    AS bucket_start,
        JSONExtractFloat(observed_payload_json, 'price_state', 'last_price')  AS open_price,
        JSONExtractFloat(observed_payload_json, 'price_state', 'last_price')  AS high_price,
        JSONExtractFloat(observed_payload_json, 'price_state', 'last_price')  AS low_price,
        JSONExtractFloat(observed_payload_json, 'price_state', 'last_price')  AS close_price,
        toInt64(JSONExtractUInt(observed_payload_json, 'trade_summary', 'volume'))        AS volume,
        toInt64(JSONExtractInt(observed_payload_json, 'trade_summary', 'net_delta'))     AS net_delta,
        toInt64(JSONExtractUInt(observed_payload_json, 'trade_summary', 'aggressive_buy_volume'))  AS aggressive_buy,
        toInt64(JSONExtractUInt(observed_payload_json, 'trade_summary', 'aggressive_sell_volume')) AS aggressive_sell,
        1                                                                     AS msg_count,
        if(JSONExtractUInt(observed_payload_json, 'trade_summary', 'volume') > 0, 1, 0) AS has_trade,
        if(JSONLength(observed_payload_json, 'same_price_replenishment') > 0, 1, 0)   AS has_replenish,
        if(JSONLength(observed_payload_json, 'significant_liquidity') > 0, 1, 0)       AS has_liquidity,
        if(JSONLength(observed_payload_json, 'active_initiative_drive') > 0, 1, 0)     AS has_drive,
        if(JSONLength(observed_payload_json, 'active_post_harvest_response') > 0, 1, 0) AS has_phr,
        JSONExtractFloat(observed_payload_json, 'price_state', 'last_price')  AS latest_price,
        toDateTime64(observed_window_end, 3, 'UTC')                           AS latest_observed_at,
        now64(3)                                                              AS stored_at
    FROM {database}.ingestions
    WHERE ingestion_kind = 'adapter_continuous_state'
    """

    # ─── Event pre-aggregate: replenishments per bucket ───────────────────────
    # Stores one row per replenishment event per minute bucket.
    # Used to reconstruct event_annotations without re-reading raw messages.
    continuous_state_events_ddl = f"""
    CREATE TABLE IF NOT EXISTS {database}.continuous_state_events
    (
        symbol             LowCardinality(String),
        bucket_start       DateTime64(3, 'UTC'),
        track_id           String,
        event_kind         LowCardinality(String),
        price              Float64,
        side               String,
        replenishment_count UInt32,
        observed_at        DateTime64(3, 'UTC'),
        stored_at          DateTime64(3, 'UTC')
    )
    ENGINE = ReplacingMergeTree(observed_at)
    PARTITION BY (symbol, toYYYYMMDD(bucket_start))
    ORDER BY (symbol, bucket_start, track_id, event_kind)
    """

    continuous_state_events_mv_ddl = f"""
    CREATE MATERIALIZED VIEW IF NOT EXISTS {database}.continuous_state_events_mv
    TO {database}.continuous_state_events
    AS
    SELECT
        instrument_symbol                                                                            AS symbol,
        toStartOfInterval(toDateTime64(observed_window_end, 3, 'UTC'), INTERVAL 1 minute)           AS bucket_start,
        JSONExtractString(observed_payload_json, 'same_price_replenishment', '0', 'track_id')         AS track_id,
        'same_price_replenishment'                                                                   AS event_kind,
        JSONExtractFloat(observed_payload_json, 'same_price_replenishment', '0', 'price')            AS price,
        JSONExtractString(observed_payload_json, 'same_price_replenishment', '0', 'side')            AS side,
        JSONExtractUInt(observed_payload_json, 'same_price_replenishment', '0', 'replenishment_count') AS replenishment_count,
        toDateTime64(observed_window_end, 3, 'UTC')                                                  AS observed_at,
        now64(3)                                                                                    AS stored_at
    FROM {database}.ingestions
    WHERE ingestion_kind = 'adapter_continuous_state'
      AND JSONLength(observed_payload_json, 'same_price_replenishment') > 0
    """

    return [
        create_db_sql,
        create_table_sql,
        chart_candles_table_sql,
        ingestions_table_sql,
        continuous_state_candles_ddl,
        continuous_state_mv_ddl,
        continuous_state_events_ddl,
        continuous_state_events_mv_ddl,
        *ticks_to_chart_candles_mv_ddls,
    ]


def _connect_with_retry(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    connect_retries: int,
    retry_delay_seconds: float,
):
    last_error: Exception | None = None
    for attempt in range(1, connect_retries + 1):
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
            )
            client.query("SELECT 1")
            return client
        except Exception as exc:
            last_error = exc
            print(
                f"ClickHouse connection attempt {attempt}/{connect_retries} failed: {exc}",
                flush=True,
            )
            time.sleep(retry_delay_seconds * attempt)

    raise RuntimeError("Unable to connect to ClickHouse after retries.") from last_error


def main() -> None:
    host = _env("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(_env("CLICKHOUSE_PORT", "8123"))
    username = _env("CLICKHOUSE_USER", "default")
    password = _env("CLICKHOUSE_PASSWORD", "")
    database = _env("CLICKHOUSE_DB", "market_data")
    connect_retries = _env_int("CLICKHOUSE_CONNECT_RETRIES", 5)
    retry_delay_seconds = _env_float("CLICKHOUSE_RETRY_DELAY_SECONDS", 1.5)

    client = _connect_with_retry(
        host=host,
        port=port,
        username=username,
        password=password,
        connect_retries=connect_retries,
        retry_delay_seconds=retry_delay_seconds,
    )

    try:
        for sql in build_ddl(database):
            client.command(sql)
    finally:
        client.close()

    print(f"ClickHouse initialized: {database}.ticks_raw")
    print(f"Materialized views created:")
    print(f"  {database}.continuous_state_candles_mv  →  {database}.continuous_state_candles")
    print(f"  {database}.continuous_state_events_mv  →  {database}.continuous_state_events")
    print(f"  {database}.ticks_raw_to_chart_candles_60s_mv   →  {database}.chart_candles (1m)")
    print(f"  {database}.ticks_raw_to_chart_candles_300s_mv  →  {database}.chart_candles (5m)")
    print(f"  {database}.ticks_raw_to_chart_candles_900s_mv  →  {database}.chart_candles (15m)")
    print(f"  {database}.ticks_raw_to_chart_candles_1800s_mv →  {database}.chart_candles (30m)")
    print(f"  {database}.ticks_raw_to_chart_candles_3600s_mv →  {database}.chart_candles (1h)")
    print(f"  {database}.ticks_raw_to_chart_candles_14400s_mv →  {database}.chart_candles (4h)")


if __name__ == "__main__":
    main()
