from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from atas_market_structure.realtime_config import RealtimeConfig


LOGGER = logging.getLogger(__name__)
INSERT_COLUMNS = ("symbol", "event_time", "price", "volume", "direction", "ts_unix_ms")
TickRow = tuple[str, datetime, float, int, str, int]


def _table_name(config: RealtimeConfig) -> str:
    return f"{config.clickhouse_database}.{config.clickhouse_table}"


def _coerce_text_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    raise TypeError(f"Unsupported Redis payload type: {type(payload)!r}")


def _build_clickhouse_client(config: RealtimeConfig) -> Client:
    return clickhouse_connect.get_client(
        host=config.clickhouse_host,
        port=config.clickhouse_port,
        username=config.clickhouse_user,
        password=config.clickhouse_password,
        database=config.clickhouse_database,
    )


async def _reconnect_clickhouse_client(client: Client, config: RealtimeConfig) -> Client:
    try:
        await asyncio.to_thread(client.close)
    except Exception:
        LOGGER.warning("Failed to close ClickHouse client cleanly during reconnect.", exc_info=True)
    return await asyncio.to_thread(_build_clickhouse_client, config)


def _parse_tick_row(payload_text: str) -> TickRow | None:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        LOGGER.warning("Dropping malformed tick payload: invalid JSON.")
        return None

    try:
        symbol = str(payload["symbol"])
        timestamp = float(payload["timestamp"])
        price = float(payload["price"])
        volume = int(payload["volume"])
        direction = str(payload["direction"])
    except (KeyError, TypeError, ValueError):
        LOGGER.warning("Dropping malformed tick payload: missing or invalid required fields.")
        return None

    if volume < 0:
        LOGGER.warning("Dropping malformed tick payload: volume must be non-negative.")
        return None

    if direction not in {"Bid", "Ask"}:
        LOGGER.warning("Dropping malformed tick payload: direction must be Bid or Ask.")
        return None

    event_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    ts_unix_ms = int(round(timestamp * 1000))
    return (symbol, event_time, price, volume, direction, ts_unix_ms)


async def _flush_buffer(client: Client, table_name: str, buffer: list[TickRow]) -> bool:
    if not buffer:
        return True

    rows = list(buffer)
    try:
        await asyncio.to_thread(client.insert, table_name, rows, column_names=INSERT_COLUMNS)
    except Exception:
        LOGGER.exception("Failed to flush %s ticks into ClickHouse table %s.", len(rows), table_name)
        return False

    LOGGER.info("Flushed %s ticks into ClickHouse table %s.", len(rows), table_name)
    return True


async def run_tick_persistence_worker(redis_client: Redis, config: RealtimeConfig) -> None:
    pubsub: PubSub = redis_client.pubsub()
    client = await asyncio.to_thread(_build_clickhouse_client, config)
    table_name = _table_name(config)
    buffer: list[TickRow] = []
    loop = asyncio.get_running_loop()
    last_flush_at = loop.time()

    LOGGER.info(
        "Starting tick persistence worker: channel=%s batch_size=%s flush_interval=%.3fs table=%s",
        config.tick_channel,
        config.batch_size,
        config.flush_interval_seconds,
        table_name,
    )

    await pubsub.subscribe(config.tick_channel)

    try:
        while True:
            timeout = config.flush_interval_seconds
            if buffer:
                elapsed = loop.time() - last_flush_at
                timeout = max(0.0, config.flush_interval_seconds - elapsed)

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
            if message is not None:
                row = _parse_tick_row(_coerce_text_payload(message["data"]))
                if row is not None:
                    buffer.append(row)

                while len(buffer) < config.batch_size:
                    pending_message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.0)
                    if pending_message is None:
                        break
                    row = _parse_tick_row(_coerce_text_payload(pending_message["data"]))
                    if row is not None:
                        buffer.append(row)

            should_flush_by_size = len(buffer) >= config.batch_size
            should_flush_by_time = bool(buffer) and (loop.time() - last_flush_at) >= config.flush_interval_seconds
            if not (should_flush_by_size or should_flush_by_time):
                continue

            flushed = await _flush_buffer(client, table_name, buffer)
            if flushed:
                buffer.clear()
                last_flush_at = loop.time()
                continue

            try:
                client = await _reconnect_clickhouse_client(client, config)
            except Exception:
                LOGGER.exception("Failed to reconnect ClickHouse client after batch insert failure.")
            await asyncio.sleep(min(config.flush_interval_seconds, 1.0) or 1.0)
    except asyncio.CancelledError:
        if buffer:
            LOGGER.info("Stopping tick persistence worker, flushing final %s ticks.", len(buffer))
            await _flush_buffer(client, table_name, buffer)
        raise
    finally:
        try:
            await pubsub.unsubscribe(config.tick_channel)
        finally:
            await pubsub.aclose()
            await asyncio.to_thread(client.close)
