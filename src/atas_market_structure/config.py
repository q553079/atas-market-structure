from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market_structure.db"


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the local REST service."""

    host: str = "127.0.0.1"
    port: int = 8080
    # Use an absolute default so restarting the server from a different working directory
    # does not silently create/attach a different SQLite file.
    database_path: Path = DEFAULT_DB_PATH
    log_level: str = "INFO"
    ai_provider: str = "openai_compatible"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ai_model: str = "gpt-5-mini"
    ai_timeout_seconds: float = 90.0
    storage_mode: str = "sqlite"
    clickhouse_host: str = "127.0.0.1"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "market_data"
    clickhouse_chart_candles_table: str = "chart_candles"
    clickhouse_ingestions_table: str = "ingestions"
    clickhouse_enable_ingestions: bool = False
    clickhouse_connect_retries: int = 5
    clickhouse_retry_delay_seconds: float = 1.5

    @classmethod
    def from_env(cls) -> "AppConfig":
        database_raw = os.getenv("ATAS_MS_DB_PATH")
        if database_raw:
            candidate = Path(database_raw)
            database_path = candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)
        else:
            database_path = DEFAULT_DB_PATH

        return cls(
            host=os.getenv("ATAS_MS_HOST", "127.0.0.1"),
            port=int(os.getenv("ATAS_MS_PORT", "8080")),
            database_path=database_path,
            log_level=os.getenv("ATAS_MS_LOG_LEVEL", "INFO"),
            ai_provider=os.getenv("ATAS_MS_AI_PROVIDER", "openai_compatible"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            ai_model=os.getenv("ATAS_MS_AI_MODEL", "gpt-5-mini"),
            ai_timeout_seconds=float(os.getenv("ATAS_MS_AI_TIMEOUT_SECONDS", "90")),
            storage_mode=os.getenv("ATAS_MS_STORAGE_MODE", "sqlite").strip().lower(),
            clickhouse_host=os.getenv("ATAS_MS_CLICKHOUSE_HOST", os.getenv("CLICKHOUSE_HOST", "127.0.0.1")),
            clickhouse_port=int(os.getenv("ATAS_MS_CLICKHOUSE_PORT", os.getenv("CLICKHOUSE_PORT", "8123"))),
            clickhouse_user=os.getenv("ATAS_MS_CLICKHOUSE_USER", os.getenv("CLICKHOUSE_USER", "default")),
            clickhouse_password=os.getenv("ATAS_MS_CLICKHOUSE_PASSWORD", os.getenv("CLICKHOUSE_PASSWORD", "")),
            clickhouse_database=os.getenv("ATAS_MS_CLICKHOUSE_DATABASE", os.getenv("CLICKHOUSE_DB", "market_data")),
            clickhouse_chart_candles_table=os.getenv("ATAS_MS_CLICKHOUSE_CHART_CANDLES_TABLE", "chart_candles"),
            clickhouse_ingestions_table=os.getenv("ATAS_MS_CLICKHOUSE_INGESTIONS_TABLE", "ingestions"),
            clickhouse_enable_ingestions=_env_bool(
                "ATAS_MS_CLICKHOUSE_ENABLE_INGESTIONS",
                default=_env_bool("CLICKHOUSE_ENABLE_INGESTIONS", default=False),
            ),
            clickhouse_connect_retries=int(
                os.getenv("ATAS_MS_CLICKHOUSE_CONNECT_RETRIES", os.getenv("CLICKHOUSE_CONNECT_RETRIES", "5"))
            ),
            clickhouse_retry_delay_seconds=float(
                os.getenv(
                    "ATAS_MS_CLICKHOUSE_RETRY_DELAY_SECONDS",
                    os.getenv("CLICKHOUSE_RETRY_DELAY_SECONDS", "1.5"),
                )
            ),
        )
