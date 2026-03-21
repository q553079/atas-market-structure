from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RealtimeConfig:
    """Runtime settings for the low-latency Redis fan-out service."""

    host: str = "127.0.0.1"
    port: int = 8090
    redis_url: str = "redis://127.0.0.1:6379/0"
    tick_channel: str = "market_ticks"
    clickhouse_host: str = "127.0.0.1"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "market_data"
    clickhouse_table: str = "ticks_raw"
    batch_size: int = 5000
    flush_interval_seconds: float = 1.0
    connect_retries: int = 5
    retry_delay_seconds: float = 1.5

    @classmethod
    def from_env(cls) -> "RealtimeConfig":
        return cls(
            host=os.getenv("ATAS_RT_HOST", "127.0.0.1"),
            port=int(os.getenv("ATAS_RT_PORT", "8090")),
            redis_url=os.getenv("ATAS_RT_REDIS_URL", "redis://127.0.0.1:6379/0"),
            tick_channel=os.getenv("ATAS_RT_TICK_CHANNEL", "market_ticks"),
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            clickhouse_database=os.getenv("CLICKHOUSE_DB", "market_data"),
            clickhouse_table=os.getenv("ATAS_RT_CLICKHOUSE_TABLE", "ticks_raw"),
            batch_size=int(os.getenv("ATAS_RT_BATCH_SIZE", "5000")),
            flush_interval_seconds=float(os.getenv("ATAS_RT_FLUSH_INTERVAL_SECONDS", "1.0")),
            connect_retries=int(os.getenv("ATAS_RT_CONNECT_RETRIES", "5")),
            retry_delay_seconds=float(os.getenv("ATAS_RT_RETRY_DELAY_SECONDS", "1.5")),
        )
