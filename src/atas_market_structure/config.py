from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market_structure.db"


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
        )
