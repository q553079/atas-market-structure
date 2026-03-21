from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis, from_url
from redis.asyncio.client import PubSub

from atas_market_structure.realtime_config import RealtimeConfig
from atas_market_structure.realtime_persistence import run_tick_persistence_worker


LOGGER = logging.getLogger(__name__)


def _coerce_text_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    raise TypeError(f"Unsupported Redis payload type: {type(payload)!r}")


async def _forward_ticks_to_websocket(websocket: WebSocket, pubsub: PubSub) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        await websocket.send_text(_coerce_text_payload(message["data"]))


async def _wait_for_client_disconnect(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(code=message.get("code", 1000), reason=message.get("reason"))


def _app_config(app: FastAPI) -> RealtimeConfig:
    return cast(RealtimeConfig, app.state.config)


def _redis_client(app: FastAPI) -> Redis:
    return cast(Redis, app.state.redis)


def _persistence_task(app: FastAPI) -> asyncio.Task[None]:
    return cast(asyncio.Task[None], app.state.persistence_task)


def _log_background_task_failure(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return

    exception = task.exception()
    if exception is not None:
        LOGGER.exception("Background persistence worker stopped unexpectedly.", exc_info=exception)


async def _wait_for_redis_ready(redis_client: Redis, config: RealtimeConfig) -> None:
    last_error: Exception | None = None
    for attempt in range(1, config.connect_retries + 1):
        try:
            await redis_client.ping()
            return
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "Redis connection attempt %s/%s failed: %s",
                attempt,
                config.connect_retries,
                exc,
            )
            await asyncio.sleep(config.retry_delay_seconds * attempt)
    raise RuntimeError("Unable to connect to Redis after retries.") from last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = _app_config(app)
    redis_client = from_url(
        config.redis_url,
        encoding="utf-8",
        decode_responses=True,
        health_check_interval=30,
    )
    app.state.redis = redis_client
    await _wait_for_redis_ready(redis_client, config)
    persistence_task = asyncio.create_task(
        run_tick_persistence_worker(redis_client, config),
        name="tick-persistence-worker",
    )
    persistence_task.add_done_callback(_log_background_task_failure)
    app.state.persistence_task = persistence_task
    try:
        yield
    finally:
        persistence_task.cancel()
        await asyncio.gather(persistence_task, return_exceptions=True)
        await redis_client.aclose()


def create_app(config: RealtimeConfig | None = None) -> FastAPI:
    config = config or RealtimeConfig.from_env()
    app = FastAPI(
        title="ATAS Realtime Fan-out Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config = config

    @app.get("/health", response_class=JSONResponse)
    async def healthcheck() -> JSONResponse:
        await _redis_client(app).ping()
        persistence_task = _persistence_task(app)
        if persistence_task.cancelled():
            return JSONResponse({"status": "degraded", "persistence_worker": "cancelled"}, status_code=503)
        if persistence_task.done():
            exception = persistence_task.exception()
            detail = exception.__class__.__name__ if exception is not None else "stopped"
            return JSONResponse({"status": "degraded", "persistence_worker": detail}, status_code=503)
        return JSONResponse({"status": "ok", "persistence_worker": "running"})

    @app.post("/api/tick", status_code=status.HTTP_200_OK, response_class=JSONResponse)
    async def publish_tick(request: Request) -> JSONResponse:
        raw_body = await request.body()
        if not raw_body:
            raise HTTPException(status_code=400, detail="Request body must not be empty.")
        try:
            payload_text = raw_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Request body must be UTF-8 JSON.") from exc

        await _redis_client(request.app).publish(_app_config(request.app).tick_channel, payload_text)
        return JSONResponse({"status": "ok"})

    @app.websocket("/ws/stream")
    async def stream_ticks(websocket: WebSocket) -> None:
        redis_client = _redis_client(websocket.app)
        channel = _app_config(websocket.app).tick_channel
        pubsub = redis_client.pubsub()
        producer_task: asyncio.Task[None] | None = None
        disconnect_task: asyncio.Task[None] | None = None

        await websocket.accept()
        await pubsub.subscribe(channel)

        try:
            producer_task = asyncio.create_task(_forward_ticks_to_websocket(websocket, pubsub))
            disconnect_task = asyncio.create_task(_wait_for_client_disconnect(websocket))
            done, pending = await asyncio.wait(
                {producer_task, disconnect_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                exception = task.exception()
                if exception is None:
                    continue
                if isinstance(exception, WebSocketDisconnect):
                    raise exception
                if isinstance(exception, RuntimeError):
                    LOGGER.info("WebSocket stream closed: %s", exception)
                    return
                raise exception
        except WebSocketDisconnect:
            LOGGER.info("WebSocket client disconnected from %s.", channel)
        finally:
            if producer_task is not None and not producer_task.done():
                producer_task.cancel()
            if disconnect_task is not None and not disconnect_task.done():
                disconnect_task.cancel()
            await asyncio.gather(
                *(task for task in (producer_task, disconnect_task) if task is not None),
                return_exceptions=True,
            )
            try:
                await pubsub.unsubscribe(channel)
            finally:
                await pubsub.aclose()

    return app


app = create_app()


def main() -> None:
    import uvicorn

    config = RealtimeConfig.from_env()
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
