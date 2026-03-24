from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ProjectionRepository(Protocol):
    """Projection/read-model surface for chart and raw mirror queries.

    Allowed to own:
    chart candles, raw mirrored ATAS bars, continuous-bar query dependencies.

    Must not own:
    recognition semantics, tuning patch lineage, chat session state.
    """

    def upsert_chart_candles(self, candles: list[object]) -> int:
        ...

    def list_chart_candles(
        self,
        symbol: str,
        timeframe: str,
        window_start: datetime,
        window_end: datetime,
        limit: int = 20000,
    ) -> list[object]:
        ...

    def count_chart_candles(self, symbol: str, timeframe: str) -> int:
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
    ) -> list[object]:
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
