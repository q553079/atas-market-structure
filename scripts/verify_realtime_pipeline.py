from __future__ import annotations

import asyncio
import json
import os
from time import sleep, time
from urllib import request
from urllib.error import URLError
import uuid

import clickhouse_connect
import websockets


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _base_http_url() -> str:
    return _env("ATAS_RT_BASE_URL", "http://127.0.0.1:8090").rstrip("/")


def _ws_url() -> str:
    return _env("ATAS_RT_WS_URL", "ws://127.0.0.1:8090/ws/stream")


def _clickhouse_client():
    retries = _env_int("CLICKHOUSE_CONNECT_RETRIES", 5)
    retry_delay_seconds = _env_float("CLICKHOUSE_RETRY_DELAY_SECONDS", 1.5)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client = clickhouse_connect.get_client(
                host=_env("CLICKHOUSE_HOST", "127.0.0.1"),
                port=int(_env("CLICKHOUSE_PORT", "8123")),
                username=_env("CLICKHOUSE_USER", "default"),
                password=_env("CLICKHOUSE_PASSWORD", ""),
                database=_env("CLICKHOUSE_DB", "market_data"),
            )
            client.query("SELECT 1")
            return client
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            sleep(retry_delay_seconds * attempt)
    raise RuntimeError("Unable to connect to ClickHouse after retries.") from last_error


def _table_name() -> str:
    return f"{_env('CLICKHOUSE_DB', 'market_data')}.{_env('ATAS_RT_CLICKHOUSE_TABLE', 'ticks_raw')}"


def _wait_for_healthcheck(url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time() + timeout_seconds
    while time() < deadline:
        try:
            with request.urlopen(f"{url}/health", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return
        except (OSError, URLError, json.JSONDecodeError):
            pass
        sleep(0.5)
    raise TimeoutError(f"Realtime service did not become healthy within {timeout_seconds:.1f}s.")


def _post_tick(url: str, body: str) -> None:
    req = request.Request(
        f"{url}/api/tick",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        response.read()


def _tick_exists(symbol: str, ts_unix_ms: int) -> bool:
    client = _clickhouse_client()
    try:
        query = (
            f"SELECT count() FROM {_table_name()} "
            f"WHERE symbol = '{symbol}' AND ts_unix_ms = {ts_unix_ms}"
        )
        result = client.query(query)
        return bool(result.result_rows[0][0])
    finally:
        client.close()


async def _verify_websocket_and_post(http_url: str, ws_url: str, raw_tick: str) -> str:
    async with websockets.connect(ws_url, max_size=None) as websocket:
        await asyncio.sleep(0.2)
        await asyncio.to_thread(_post_tick, http_url, raw_tick)
        message = await asyncio.wait_for(websocket.recv(), timeout=5)
        if not isinstance(message, str):
            raise TypeError(f"Unexpected websocket message type: {type(message)!r}")
        return message


def _wait_for_clickhouse(symbol: str, ts_unix_ms: int, timeout_seconds: float = 10.0) -> None:
    deadline = time() + timeout_seconds
    while time() < deadline:
        if _tick_exists(symbol, ts_unix_ms):
            return
        sleep(0.25)
    raise TimeoutError(f"Tick {symbol}/{ts_unix_ms} was not flushed to ClickHouse within {timeout_seconds:.1f}s.")


async def main() -> None:
    http_url = _base_http_url()
    ws_url = _ws_url()
    _wait_for_healthcheck(http_url)

    symbol = f"NQ_TEST_{uuid.uuid4().hex[:8].upper()}"
    ts_unix_ms = int(time() * 1000)
    tick_payload = {
        "symbol": symbol,
        "timestamp": ts_unix_ms / 1000.0,
        "price": 18500.25,
        "volume": 2,
        "direction": "Ask",
    }
    raw_tick = json.dumps(tick_payload, separators=(",", ":"))

    websocket_message = await _verify_websocket_and_post(http_url, ws_url, raw_tick)
    if websocket_message != raw_tick:
        raise AssertionError("WebSocket payload mismatch: tick was not forwarded verbatim.")

    _wait_for_clickhouse(symbol, ts_unix_ms)
    print(f"Realtime pipeline verified successfully for {symbol}.")


if __name__ == "__main__":
    asyncio.run(main())
