from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

import pytest

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.app import MarketStructureApplication
from atas_market_structure.continuous_contract_service import (
    ContinuousContractService,
    ContinuousContractServiceError,
)
from atas_market_structure.models import (
    AdapterHistoryBarsPayload,
    ContinuousAdjustmentMode,
    RollMode,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository


@contextmanager
def _temp_repo():
    tmp = Path(tempfile.mkdtemp(prefix="atas-test-"))
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
    root_symbol: str = "NQ",
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


def test_roll_mode_none_returns_only_latest_contract_segment() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=_build_bars(start=t0, opens=[100.0, 101.0]))
        _ingest_history(
            repo,
            symbol="NQM6",
            chart_instance_id="chart-a",
            bars=_build_bars(start=t0 + timedelta(minutes=2), opens=[110.0, 111.0]),
        )

        service = ContinuousContractService(repository=repo)
        response = service.query_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.NONE,
            window_start=t0,
            window_end=t0 + timedelta(minutes=3),
        )

        assert response.roll_mode == RollMode.NONE
        assert response.count == 2
        assert len(response.contract_segments) == 1
        assert response.contract_segments[0].contract_symbol == "NQM6"
        assert {item.source_contract_symbol for item in response.candles} == {"NQM6"}
        assert response.warnings


def test_by_contract_start_builds_multiple_segments_and_dedupes_chart_instances() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        h6_bars = _build_bars(start=t0, opens=[100.0, 101.0])
        m6_bars = _build_bars(start=t0 + timedelta(minutes=2), opens=[110.0, 111.0])
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=h6_bars)
        _ingest_history(repo, symbol="NQM6", chart_instance_id="chart-a", bars=m6_bars)
        _ingest_history(repo, symbol="NQM6", chart_instance_id="chart-b", bars=m6_bars)

        service = ContinuousContractService(repository=repo)
        response = service.query_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.BY_CONTRACT_START,
            window_start=t0,
            window_end=t0 + timedelta(minutes=3),
            include_contract_markers=True,
        )

        assert response.count == 4
        assert [item.contract_symbol for item in response.contract_segments] == ["NQH6", "NQM6"]
        assert [item.source_contract_symbol for item in response.candles] == ["NQH6", "NQH6", "NQM6", "NQM6"]
        assert len(response.contract_markers) == 4


def test_manual_sequence_requires_explicit_order_and_respects_it() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=_build_bars(start=t0, opens=[100.0, 101.0]))
        _ingest_history(
            repo,
            symbol="NQM6",
            chart_instance_id="chart-a",
            bars=_build_bars(start=t0 + timedelta(minutes=2), opens=[110.0, 111.0]),
        )

        service = ContinuousContractService(repository=repo)
        with pytest.raises(ContinuousContractServiceError):
            service.query_continuous_bars(
                root_symbol="NQ",
                timeframe=Timeframe.MIN_1,
                roll_mode=RollMode.MANUAL_SEQUENCE,
                window_start=t0,
                window_end=t0 + timedelta(minutes=3),
            )

        response = service.query_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.MANUAL_SEQUENCE,
            window_start=t0,
            window_end=t0 + timedelta(minutes=3),
            manual_sequence=["NQH6", "NQM6"],
        )
        assert [item.contract_symbol for item in response.contract_segments] == ["NQH6", "NQM6"]


def test_by_volume_proxy_returns_explicit_error_until_supported() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=_build_bars(start=t0, opens=[100.0]))

        service = ContinuousContractService(repository=repo)
        with pytest.raises(ContinuousContractServiceError, match="by_volume_proxy"):
            service.query_continuous_bars(
                root_symbol="NQ",
                timeframe=Timeframe.MIN_1,
                roll_mode=RollMode.BY_VOLUME_PROXY,
                window_start=t0,
                window_end=t0,
            )


def test_adjustment_mode_gap_shift_differs_from_none() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=_build_bars(start=t0, opens=[100.0]))
        _ingest_history(repo, symbol="NQM6", chart_instance_id="chart-a", bars=_build_bars(start=t0 + timedelta(minutes=1), opens=[110.0]))

        service = ContinuousContractService(repository=repo)
        none_response = service.query_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.BY_CONTRACT_START,
            window_start=t0,
            window_end=t0 + timedelta(minutes=1),
            adjustment_mode=ContinuousAdjustmentMode.NONE,
        )
        gap_shift_response = service.query_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.BY_CONTRACT_START,
            window_start=t0,
            window_end=t0 + timedelta(minutes=1),
            adjustment_mode=ContinuousAdjustmentMode.GAP_SHIFT,
        )

        assert none_response.candles[1].open == 110.0
        assert gap_shift_response.candles[1].open == none_response.candles[0].close
        assert gap_shift_response.candles[1].adjustment_offset != 0.0


def test_mirror_endpoint_and_continuous_endpoint_return_different_semantics() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        _ingest_history(repo, symbol="NQH6", chart_instance_id="chart-a", bars=_build_bars(start=t0, opens=[100.0, 101.0]))
        _ingest_history(
            repo,
            symbol="NQM6",
            chart_instance_id="chart-a",
            bars=_build_bars(start=t0 + timedelta(minutes=2), opens=[110.0, 111.0]),
        )

        app = MarketStructureApplication(repository=repo)
        mirror_response = app.dispatch(
            "GET",
            "/api/v1/chart/mirror-bars?chart_instance_id=chart-a&contract_symbol=NQM6"
            "&timeframe=1m&window_start_utc=2026-03-22T09:30:00Z&window_end_utc=2026-03-22T09:33:00Z",
        )
        continuous_response = app.dispatch(
            "GET",
            "/api/v1/chart/continuous-bars?root_symbol=NQ&timeframe=1m&roll_mode=by_contract_start"
            "&adjustment_mode=none&include_contract_markers=true"
            "&window_start_utc=2026-03-22T09:30:00Z&window_end_utc=2026-03-22T09:33:00Z",
        )

        assert mirror_response.status_code == 200
        assert continuous_response.status_code == 200

        mirror_body = json.loads(mirror_response.body)
        continuous_body = json.loads(continuous_response.body)

        assert mirror_body["contract_symbol"] == "NQM6"
        assert len(mirror_body["bars"]) == 2
        assert mirror_body["bars"][0]["chart_instance_id"] == "chart-a"
        assert mirror_body["bars"][0]["contract_symbol"] == "NQM6"
        assert mirror_body["bars"][0]["bar_timestamp_utc"].endswith(("Z", "+00:00"))

        assert continuous_body["root_symbol"] == "NQ"
        assert continuous_body["roll_mode"] == "by_contract_start"
        assert continuous_body["adjustment_mode"] == "none"
        assert len(continuous_body["contract_segments"]) == 2
        assert len(continuous_body["candles"]) == 4
        assert continuous_body["candles"][0]["source_contract_symbol"] == "NQH6"
        assert continuous_body["candles"][-1]["source_contract_symbol"] == "NQM6"
        assert len(continuous_body["contract_markers"]) == 4
        assert continuous_body["candles"] != mirror_body["bars"]
