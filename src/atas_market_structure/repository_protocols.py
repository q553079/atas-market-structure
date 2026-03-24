from __future__ import annotations

# compatibility facade only; do not add new business logic or large protocol surfaces here

from datetime import datetime
from pathlib import Path
from typing import Protocol

from atas_market_structure.repository_chat import ChatRepository
from atas_market_structure.repository_evaluation_tuning import EvaluationTuningRepository
from atas_market_structure.repository_projection import ProjectionRepository
from atas_market_structure.repository_raw_ingestion import RawIngestionRepository
from atas_market_structure.repository_recognition import RecognitionRepository


class ChartCandleRepository(Protocol):
    """Low-level chart/raw-bar read-write surface used by projection helpers."""

    def initialize(self) -> None:
        ...

    def upsert_chart_candle(self, candle: "ChartCandle") -> "ChartCandle":
        ...

    def upsert_chart_candles(self, candles: list["ChartCandle"]) -> int:
        ...

    def replace_chart_candles(self, candles: list["ChartCandle"]) -> int:
        ...

    def list_chart_candles(
        self,
        symbol: str,
        timeframe: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list["ChartCandle"]:
        ...

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
        ...

    def purge_chart_candles(self, *, symbol: str | None, older_than: datetime) -> int:
        ...

    def delete_chart_candles_window(
        self,
        *,
        symbol: str,
        timeframe: str | None,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        ...

    def upsert_atas_chart_bars_raw(self, bars: list["AtasChartBarRaw"]) -> int:
        ...

    def list_atas_chart_bars_raw(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        limit: int = 5000,
    ) -> list["AtasChartBarRaw"]:
        ...

    def count_atas_chart_bars_raw(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> int:
        ...

    def get_atas_chart_bars_raw_coverage(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> tuple[datetime | None, datetime | None, int]:
        ...

    def purge_atas_chart_bars_raw(
        self,
        *,
        older_than: datetime,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
    ) -> int:
        ...

    def delete_atas_chart_bars_raw_window(
        self,
        *,
        chart_instance_id: str | None = None,
        contract_symbol: str | None = None,
        root_symbol: str | None = None,
        timeframe: str | None = None,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        ...


class IngestionRepository(RawIngestionRepository, Protocol):
    """Compatibility alias for existing ingestion-facing imports."""


class AnalysisRepository(
    RawIngestionRepository,
    RecognitionRepository,
    ProjectionRepository,
    EvaluationTuningRepository,
    ChatRepository,
    ChartCandleRepository,
    Protocol,
):
    """Aggregate repository contract used by the application wiring."""

    @property
    def workspace_root(self) -> Path:
        ...

    def initialize(self) -> None:
        ...

