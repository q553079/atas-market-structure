from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.chart_candle_service import ChartCandleService
from atas_market_structure.continuous_contract_service import ContinuousContractServiceError
from atas_market_structure.models import AdapterHistoryBarsPayload, ChartCandle, Timeframe
from atas_market_structure.repository import SQLiteAnalysisRepository


@contextmanager
def _temp_repo():
    tmp = Path(tempfile.mkdtemp(prefix="atas-chart-display-"))
    try:
        db_path = tmp / "data" / "market_structure.db"
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()
        yield repo
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _history_payload(
    *,
    symbol: str,
    root_symbol: str,
    chart_instance_id: str,
    bars: list[dict[str, object]],
    timeframe: str = "1m",
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "message_id": f"msg-{uuid4().hex[:8]}",
        "emitted_at": datetime.now(tz=UTC).isoformat(),
        "observed_window_start": bars[0]["started_at"],
        "observed_window_end": bars[-1]["ended_at"],
        "source": {
            "system": "ATAS",
            "instance_id": "DESKTOP-TEST",
            "chart_instance_id": chart_instance_id,
            "adapter_version": "0.1.0",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_name": "America/New_York",
            "chart_display_utc_offset_minutes": -300,
            "timestamp_basis": "chart_display_timezone",
            "timezone_capture_confidence": "high",
        },
        "instrument": {
            "symbol": symbol,
            "root_symbol": root_symbol,
            "contract_symbol": symbol,
            "venue": "CME",
            "tick_size": 0.25,
            "currency": "USD",
        },
        "display_timeframe": timeframe,
        "message_type": "history_bars",
        "bar_timeframe": timeframe,
        "bars": bars,
    }


def _build_bars(
    *,
    start: datetime,
    opens: list[float],
) -> list[dict[str, object]]:
    bars: list[dict[str, object]] = []
    for index, open_price in enumerate(opens):
        started_at = start + timedelta(minutes=index)
        bars.append(
            {
                "started_at": started_at.isoformat(),
                "ended_at": (started_at + timedelta(seconds=59)).isoformat(),
                "open": open_price,
                "high": open_price + 1.0,
                "low": open_price - 1.0,
                "close": open_price + 0.5,
                "volume": 10 + index,
                "delta": 2 + index,
                "bid_volume": 4 + index,
                "ask_volume": 6 + index,
                "bar_timestamp_utc": started_at.isoformat(),
                "original_bar_time_text": started_at.strftime("%Y-%m-%d %H:%M:%S ET"),
            }
        )
    return bars


def _ingest_history(
    repo: SQLiteAnalysisRepository,
    *,
    symbol: str,
    root_symbol: str,
    chart_instance_id: str,
    bars: list[dict[str, object]],
) -> None:
    service = AdapterIngestionService(repository=repo)
    payload = AdapterHistoryBarsPayload.model_validate(
        _history_payload(
            symbol=symbol,
            root_symbol=root_symbol,
            chart_instance_id=chart_instance_id,
            bars=bars,
        )
    )
    service.ingest_history_bars(payload)


def _upsert_chart_candles(
    repo: SQLiteAnalysisRepository,
    *,
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    opens: list[float],
) -> None:
    updated_at = datetime(2026, 3, 27, 0, 0, tzinfo=UTC)
    timeframe_delta = timedelta(minutes=1 if timeframe == Timeframe.MIN_1 else 5)
    candles: list[ChartCandle] = []
    for index, open_price in enumerate(opens):
        started_at = start + index * timeframe_delta
        candles.append(
            ChartCandle(
                symbol=symbol,
                timeframe=timeframe,
                started_at=started_at,
                ended_at=started_at + timeframe_delta,
                source_started_at=started_at,
                open=open_price,
                high=open_price + 1.0,
                low=open_price - 1.0,
                close=open_price + 0.5,
                volume=10 + index,
                tick_volume=10 + index,
                delta=2 + index,
                updated_at=updated_at,
            )
        )
    repo.upsert_chart_candles(candles)


def test_display_result_falls_back_to_chart_candles_without_contract_rollover() -> None:
    with _temp_repo() as repo:
        start = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        _upsert_chart_candles(
            repo,
            symbol="GC",
            timeframe=Timeframe.MIN_1,
            start=start,
            opens=[100.0, 101.0, 102.0],
        )
        service = ChartCandleService(repository=repo)

        result = service.get_display_candle_result(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=2, seconds=59),
        )

        assert [candle.open for candle in result.candles] == [100.0, 101.0, 102.0]
        assert result.event_annotations == []
        assert result.display_metadata["chart_data_source"] == "chart_candles"
        assert result.display_metadata["contract_rollover_applied"] is False


def test_display_result_overlays_true_contract_prices_and_marks_rollover() -> None:
    with _temp_repo() as repo:
        start = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        _upsert_chart_candles(
            repo,
            symbol="GC",
            timeframe=Timeframe.MIN_1,
            start=start,
            opens=[100.0, 101.0, 102.0, 103.0],
        )
        _ingest_history(repo, symbol="GC", root_symbol="GC", chart_instance_id="chart-root", bars=_build_bars(start=start, opens=[100.0, 101.0, 102.0, 103.0]))
        _ingest_history(repo, symbol="GCJ6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start, opens=[100.0, 101.0]))
        _ingest_history(repo, symbol="GCM6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start + timedelta(minutes=2), opens=[110.0, 111.0]))
        service = ChartCandleService(repository=repo)

        result = service.get_display_candle_result(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
        )

        assert [candle.open for candle in result.candles] == [100.0, 101.0, 110.0, 111.0]
        assert result.display_metadata["contract_rollover_applied"] is True
        assert result.display_metadata["contract_sequence"] == ["GCJ6", "GCM6"]
        assert len(result.display_metadata["contract_rollovers"]) == 1
        assert any("Ignored generic root-level contract GC" in warning for warning in result.display_metadata["warnings"])
        assert len(result.event_annotations) == 1
        assert result.event_annotations[0].event_kind == "换月"
        assert result.event_annotations[0].notes[0] == "GCJ6 -> GCM6"
        assert result.event_annotations[0].notes[1] == "真实成交价格，未做平移"


def test_display_result_can_render_from_raw_contract_bars_without_root_chart_candles() -> None:
    with _temp_repo() as repo:
        start = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        _ingest_history(repo, symbol="GCJ6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start, opens=[100.0, 101.0]))
        _ingest_history(repo, symbol="GCM6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start + timedelta(minutes=2), opens=[110.0, 111.0]))
        service = ChartCandleService(repository=repo)

        result = service.get_display_candle_result(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
        )

        assert [candle.open for candle in result.candles] == [100.0, 101.0, 110.0, 111.0]
        assert result.display_metadata["chart_data_source"] == "chart_candles_contract_splice"
        assert len(result.event_annotations) == 1


def test_display_result_can_skip_contract_overlay_for_fast_path() -> None:
    with _temp_repo() as repo:
        start = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        _upsert_chart_candles(
            repo,
            symbol="GC",
            timeframe=Timeframe.MIN_1,
            start=start,
            opens=[100.0, 101.0, 102.0, 103.0],
        )
        _ingest_history(repo, symbol="GCJ6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start, opens=[100.0, 101.0]))
        _ingest_history(repo, symbol="GCM6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start + timedelta(minutes=2), opens=[110.0, 111.0]))
        service = ChartCandleService(repository=repo)
        base_candles = service.get_candles(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
        )

        result = service.get_display_candle_result(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
            skip_contract_overlay=True,
        )

        assert [candle.open for candle in result.candles] == [candle.open for candle in base_candles]
        assert result.event_annotations == []
        assert result.display_metadata["chart_data_source"] == "chart_candles"
        assert result.display_metadata["contract_rollover_applied"] is False


def test_display_result_falls_back_when_contract_overlay_resolution_errors(monkeypatch) -> None:
    with _temp_repo() as repo:
        start = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        _upsert_chart_candles(
            repo,
            symbol="GC",
            timeframe=Timeframe.MIN_1,
            start=start,
            opens=[100.0, 101.0, 102.0, 103.0],
        )
        _ingest_history(repo, symbol="GCJ6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start, opens=[100.0, 101.0]))
        _ingest_history(repo, symbol="GCM6", root_symbol="GC", chart_instance_id="chart-a", bars=_build_bars(start=start + timedelta(minutes=2), opens=[110.0, 111.0]))
        service = ChartCandleService(repository=repo)

        def _raise_overlay_error(**_kwargs):
            raise ContinuousContractServiceError(
                "manual_sequence contradicts the observed contract start order in raw mirror data."
            )

        monkeypatch.setattr(service._continuous_contract_service, "query_continuous_bars", _raise_overlay_error)

        base_candles = service.get_candles(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
        )

        result = service.get_display_candle_result(
            "GC",
            Timeframe.MIN_1,
            start,
            start + timedelta(minutes=3, seconds=59),
        )

        assert [candle.open for candle in result.candles] == [candle.open for candle in base_candles]
        assert result.event_annotations == []
        assert result.display_metadata["chart_data_source"] == "chart_candles"
        assert result.display_metadata["contract_rollover_applied"] is False
        assert result.display_metadata["contract_sequence"] == ["GCJ6", "GCM6"]
        assert any(
            "contract_overlay_fallback: manual_sequence contradicts the observed contract start order in raw mirror data."
            == warning
            for warning in result.display_metadata["warnings"]
        )
