from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from typing import Iterable

import clickhouse_connect


TIMEFRAMES: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
}


@dataclass(frozen=True)
class BackfillConfig:
    host: str
    port: int
    username: str
    password: str
    database: str
    ticks_table: str
    chart_table: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    start: datetime | None
    end: datetime | None
    dry_run: bool
    replace_existing: bool


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _dt_literal(value: datetime) -> str:
    dt = value.astimezone(UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing full-history chart_candles buckets from ClickHouse ticks_raw."
    )
    parser.add_argument("--host", default=_env("ATAS_MS_CLICKHOUSE_HOST", _env("CLICKHOUSE_HOST", "127.0.0.1")))
    parser.add_argument("--port", type=int, default=int(_env("ATAS_MS_CLICKHOUSE_PORT", _env("CLICKHOUSE_PORT", "8123"))))
    parser.add_argument("--user", default=_env("ATAS_MS_CLICKHOUSE_USER", _env("CLICKHOUSE_USER", "default")))
    parser.add_argument("--password", default=_env("ATAS_MS_CLICKHOUSE_PASSWORD", _env("CLICKHOUSE_PASSWORD", "")))
    parser.add_argument("--database", default=_env("ATAS_MS_CLICKHOUSE_DATABASE", _env("CLICKHOUSE_DB", "market_data")))
    parser.add_argument("--ticks-table", default=_env("ATAS_RT_CLICKHOUSE_TABLE", "ticks_raw"))
    parser.add_argument("--chart-table", default=_env("ATAS_MS_CLICKHOUSE_CHART_CANDLES_TABLE", "chart_candles"))
    parser.add_argument("--symbols", nargs="*", default=[], help="Optional symbol allowlist. Defaults to all symbols in ticks_raw.")
    parser.add_argument(
        "--timeframes",
        nargs="*",
        default=list(TIMEFRAMES.keys()),
        help="Target timeframes. Defaults: 1m 5m 15m 30m 1h 4h.",
    )
    parser.add_argument("--start", default=None, help="Inclusive UTC lower bound on tick event_time, ISO-8601.")
    parser.add_argument("--end", default=None, help="Inclusive UTC upper bound on tick event_time, ISO-8601.")
    parser.add_argument("--dry-run", action="store_true", help="Only print plan; do not write chart_candles.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing chart_candles buckets in scope before insert (default only fills missing buckets).",
    )
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> BackfillConfig:
    tfs = tuple(dict.fromkeys(tf.strip() for tf in args.timeframes if tf.strip()))
    for tf in tfs:
        if tf not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {tf}")
    symbols = tuple(dict.fromkeys(item.strip().upper() for item in args.symbols if item.strip()))
    start = _parse_datetime(args.start)
    end = _parse_datetime(args.end)
    if start is not None and end is not None and end < start:
        raise ValueError("--end must be greater than or equal to --start")
    return BackfillConfig(
        host=args.host,
        port=int(args.port),
        username=args.user,
        password=args.password,
        database=args.database,
        ticks_table=args.ticks_table,
        chart_table=args.chart_table,
        symbols=symbols,
        timeframes=tfs,
        start=start,
        end=end,
        dry_run=bool(args.dry_run),
        replace_existing=bool(args.replace_existing),
    )


def _build_tick_where(*, symbol: str, start: datetime | None, end: datetime | None) -> str:
    clauses = [f"symbol = {_quote_string(symbol)}"]
    if start is not None:
        clauses.append(f"event_time >= toDateTime64('{_dt_literal(start)}', 3, 'UTC')")
    if end is not None:
        clauses.append(f"event_time <= toDateTime64('{_dt_literal(end)}', 3, 'UTC')")
    return " AND ".join(clauses)


def _build_chart_where(*, symbol: str, timeframe: str, start: datetime | None, end: datetime | None) -> str:
    clauses = [
        f"symbol = {_quote_string(symbol)}",
        f"timeframe = {_quote_string(timeframe)}",
    ]
    if start is not None:
        clauses.append(f"started_at >= toDateTime64('{_dt_literal(start)}', 3, 'UTC')")
    if end is not None:
        clauses.append(f"started_at <= toDateTime64('{_dt_literal(end)}', 3, 'UTC')")
    return " AND ".join(clauses)


def _iter_symbols(client, cfg: BackfillConfig) -> list[str]:
    if cfg.symbols:
        return list(cfg.symbols)
    where = []
    if cfg.start is not None:
        where.append(f"event_time >= toDateTime64('{_dt_literal(cfg.start)}', 3, 'UTC')")
    if cfg.end is not None:
        where.append(f"event_time <= toDateTime64('{_dt_literal(cfg.end)}', 3, 'UTC')")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
    SELECT DISTINCT symbol
    FROM {cfg.database}.{cfg.ticks_table}
    {where_sql}
    ORDER BY symbol
    """
    return [str(row[0]).upper() for row in client.query(query).result_rows]


def _count_source_buckets(client, cfg: BackfillConfig, *, symbol: str, tf_seconds: int) -> int:
    where_sql = _build_tick_where(symbol=symbol, start=cfg.start, end=cfg.end)
    query = f"""
    SELECT count()
    FROM
    (
        SELECT toStartOfInterval(event_time, INTERVAL {tf_seconds} second, 'UTC') AS bucket_start
        FROM {cfg.database}.{cfg.ticks_table}
        WHERE {where_sql}
        GROUP BY bucket_start
    )
    """
    rows = client.query(query).result_rows
    return int(rows[0][0]) if rows else 0


def _count_chart_buckets(client, cfg: BackfillConfig, *, symbol: str, timeframe: str) -> int:
    where_sql = _build_chart_where(symbol=symbol, timeframe=timeframe, start=cfg.start, end=cfg.end)
    query = f"""
    SELECT count()
    FROM
    (
        SELECT started_at
        FROM {cfg.database}.{cfg.chart_table}
        WHERE {where_sql}
        GROUP BY started_at
    )
    """
    rows = client.query(query).result_rows
    return int(rows[0][0]) if rows else 0


def _delete_chart_scope(client, cfg: BackfillConfig, *, symbol: str, timeframe: str) -> None:
    where_sql = _build_chart_where(symbol=symbol, timeframe=timeframe, start=cfg.start, end=cfg.end)
    client.command("SET mutations_sync = 2")
    client.command(f"ALTER TABLE {cfg.database}.{cfg.chart_table} DELETE WHERE {where_sql}")


def _insert_backfill(client, cfg: BackfillConfig, *, symbol: str, timeframe: str, tf_seconds: int) -> None:
    tick_where_sql = _build_tick_where(symbol=symbol, start=cfg.start, end=cfg.end)
    chart_where_sql = _build_chart_where(symbol=symbol, timeframe=timeframe, start=cfg.start, end=cfg.end)

    if cfg.replace_existing:
        select_sql = f"""
        SELECT
            agg.symbol AS symbol,
            {_quote_string(timeframe)} AS timeframe,
            agg.bucket_start AS started_at,
            agg.bucket_start + toIntervalSecond({tf_seconds - 1}) AS ended_at,
            agg.source_started_at AS source_started_at,
            agg.open AS open,
            agg.high AS high,
            agg.low AS low,
            agg.close AS close,
            agg.volume AS volume,
            agg.tick_volume AS tick_volume,
            agg.delta AS delta,
            agg.updated_at AS updated_at
        FROM
        (
            SELECT
                symbol,
                toStartOfInterval(event_time, INTERVAL {tf_seconds} second, 'UTC') AS bucket_start,
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
                    direction
                FROM {cfg.database}.{cfg.ticks_table}
            )
            WHERE {tick_where_sql}
            GROUP BY symbol, bucket_start
        ) AS agg
        """
    else:
        select_sql = f"""
        SELECT
            agg.symbol AS symbol,
            {_quote_string(timeframe)} AS timeframe,
            agg.bucket_start AS started_at,
            agg.bucket_start + toIntervalSecond({tf_seconds - 1}) AS ended_at,
            agg.source_started_at AS source_started_at,
            agg.open AS open,
            agg.high AS high,
            agg.low AS low,
            agg.close AS close,
            agg.volume AS volume,
            agg.tick_volume AS tick_volume,
            agg.delta AS delta,
            agg.updated_at AS updated_at
        FROM
        (
            SELECT
                symbol,
                toStartOfInterval(event_time, INTERVAL {tf_seconds} second, 'UTC') AS bucket_start,
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
                    direction
                FROM {cfg.database}.{cfg.ticks_table}
            )
            WHERE {tick_where_sql}
            GROUP BY symbol, bucket_start
        ) AS agg
        WHERE (agg.symbol, agg.bucket_start) NOT IN
        (
            SELECT symbol, started_at
            FROM {cfg.database}.{cfg.chart_table}
            WHERE {chart_where_sql}
            GROUP BY symbol, started_at
        )
        """

    insert_sql = f"""
    INSERT INTO {cfg.database}.{cfg.chart_table}
    (
        symbol, timeframe, started_at, ended_at, source_started_at,
        open, high, low, close, volume, tick_volume, delta, updated_at
    )
    {select_sql}
    """
    client.command(insert_sql)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "None"
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _print_header(cfg: BackfillConfig, symbols: Iterable[str]) -> None:
    print("=== ticks_raw -> chart_candles backfill ===")
    print(f"ClickHouse: {cfg.host}:{cfg.port} db={cfg.database}")
    print(f"ticks_table={cfg.ticks_table} chart_table={cfg.chart_table}")
    print(f"symbols={', '.join(symbols) if symbols else '(none)'}")
    print(f"timeframes={', '.join(cfg.timeframes)}")
    print(f"start={_fmt_dt(cfg.start)} end={_fmt_dt(cfg.end)}")
    print(f"dry_run={cfg.dry_run} replace_existing={cfg.replace_existing}")
    print()


def main() -> None:
    args = _parse_args()
    cfg = _build_config(args)

    client = clickhouse_connect.get_client(
        host=cfg.host,
        port=cfg.port,
        username=cfg.username,
        password=cfg.password,
        database=cfg.database,
    )

    try:
        symbols = _iter_symbols(client, cfg)
        _print_header(cfg, symbols)

        if not symbols:
            print("No symbols found in ticks_raw for the selected scope.")
            return

        total_inserted = 0
        total_source = 0
        total_after = 0

        for symbol in symbols:
            print(f"[symbol={symbol}]")
            for timeframe in cfg.timeframes:
                tf_seconds = TIMEFRAMES[timeframe]
                source_count = _count_source_buckets(client, cfg, symbol=symbol, tf_seconds=tf_seconds)
                before_count = _count_chart_buckets(client, cfg, symbol=symbol, timeframe=timeframe)

                if source_count == 0:
                    print(f"  tf={timeframe:>3} source=0 before={before_count} inserted=0 after={before_count}")
                    continue

                if cfg.dry_run:
                    after_count = before_count
                    inserted = 0
                else:
                    if cfg.replace_existing:
                        _delete_chart_scope(client, cfg, symbol=symbol, timeframe=timeframe)
                    _insert_backfill(client, cfg, symbol=symbol, timeframe=timeframe, tf_seconds=tf_seconds)
                    after_count = _count_chart_buckets(client, cfg, symbol=symbol, timeframe=timeframe)
                    inserted = max(0, after_count - before_count)

                total_source += source_count
                total_after += after_count
                total_inserted += inserted
                print(
                    f"  tf={timeframe:>3} source={source_count} before={before_count} "
                    f"inserted={inserted} after={after_count}"
                )
            print()

        print("=== summary ===")
        print(f"total_source_buckets={total_source}")
        print(f"total_chart_buckets_after={total_after}")
        print(f"total_inserted_buckets={total_inserted}")
        if cfg.dry_run:
            print("dry-run mode: no rows were written.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
