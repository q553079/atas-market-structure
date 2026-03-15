from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the local REST service."""

    host: str = "127.0.0.1"
    port: int = 8080
    database_path: Path = Path("data/market_structure.db")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "AppConfig":
        database_raw = os.getenv("ATAS_MS_DB_PATH", "data/market_structure.db")
        return cls(
            host=os.getenv("ATAS_MS_HOST", "127.0.0.1"),
            port=int(os.getenv("ATAS_MS_PORT", "8080")),
            database_path=Path(database_raw),
            log_level=os.getenv("ATAS_MS_LOG_LEVEL", "INFO"),
        )
