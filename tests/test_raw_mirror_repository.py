"""Tests for raw mirror repository and contract rollover isolation.

Covers:
6. mirror query by chart_instance_id + contract_symbol returns exact data
7. contract rollover: two different contracts do not overwrite each other
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.models import (
    AdapterHistoryBarsPayload,
    RollMode,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_services import ReplayWorkbenchService


# ---------------------------------------------------------------------------
# Temp-dir fixture (avoids pytest's Windows temp permission issue)
# ---------------------------------------------------------------------------

@contextmanager
def _temp_repo():
    """Create a temp SQLite repo that auto-deletes after the test."""
    tmp = Path(tempfile.mkdtemp(prefix="atas-test-"))
    try:
        db_path = tmp / "data" / "market_structure.db"
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()
        yield repo
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_history_payload_dict(
    *,
    symbol: str = "NQH6",
    timeframe: str | Timeframe = "1m",
    bars: list[dict] | None = None,
    chart_instance_id: str | None = "chart-abc",
    chart_display_timezone_name: str | None = "America/New_York",
    message_id: str | None = None,
) -> dict:
    """Build a minimal history_bars payload dict."""
    if bars is None:
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 25,
                "delta": 5,
                "bid_volume": 10,
                "ask_volume": 15,
                "bar_timestamp_utc": (t0 + timedelta(minutes=i)).isoformat(),
                "original_bar_time_text": f"{(t0 + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')} ET",
            }
            for i in range(5)
        ]
    return {
        "schema_version": "1.0.0",
        "message_id": message_id or f"msg-{uuid4().hex[:8]}",
        "emitted_at": datetime.now(tz=UTC).isoformat(),
        "observed_window_start": bars[0]["started_at"],
        "observed_window_end": bars[-1]["ended_at"],
        "source": {
            "system": "ATAS",
            "instance_id": "DESKTOP-TEST",
            "chart_instance_id": chart_instance_id,
            "adapter_version": "0.1.0",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_name": chart_display_timezone_name,
            "chart_display_utc_offset_minutes": -300,
        },
        "instrument": {
            "symbol": symbol,
            "root_symbol": symbol[:2] if len(symbol) >= 2 else symbol,
            "contract_symbol": symbol,
            "venue": "CME",
            "tick_size": 0.25,
            "currency": "USD",
        },
        "display_timeframe": str(timeframe),
        "message_type": "history_bars",
        "bar_timeframe": str(timeframe) if isinstance(timeframe, Timeframe) else timeframe,
        "bars": bars,
        "time_context": {
            "instrument_timezone_value": "36",
            "instrument_timezone_source": "exchange_metadata",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_source": "atlas_payload",
            "chart_display_timezone_name": chart_display_timezone_name,
            "chart_display_utc_offset_minutes": -300,
            "timezone_capture_confidence": "high",
            "collector_local_timezone_name": "America/Chicago",
            "collector_local_utc_offset_minutes": -300,
            "timestamp_basis": "chart_display_timezone",
            "started_at_output_timezone": "UTC",
            "started_at_time_source": "chart_display_timezone",
        },
    }


# ---------------------------------------------------------------------------
# Test 6: mirror query by chart_instance_id + contract_symbol
# ---------------------------------------------------------------------------

def test_mirror_bars_returns_exact_contract_bars() -> None:
    """get_mirror_bars returns raw contract bars filtered by contract_symbol."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 200.0 + i,
                "high": 201.0 + i,
                "low": 199.0 + i,
                "close": 200.5 + i,
                "volume": 50,
                "delta": 10,
                "bid_volume": 20,
                "ask_volume": 30,
            }
            for i in range(10)
        ]
        payload_dict = _build_history_payload_dict(
            symbol="NQH6",
            timeframe="1m",
            bars=bars,
            chart_instance_id="chart-abc",
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        service.ingest_history_bars(payload)

        result = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=9),
        )

        assert len(result) == 10
        assert all(b.open >= 200.0 for b in result)
        assert result[0].started_at == t0


def test_mirror_bars_filters_by_chart_instance_id() -> None:
    """get_mirror_bars with chart_instance_id returns only matching ingestions."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 25,
                "delta": 5,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars,
                    chart_instance_id="chart-abc",
                )
            )
        )
        bars_xyz = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 300.0 + i,  # Different price range
                "high": 301.0 + i,
                "low": 299.0 + i,
                "close": 300.5 + i,
                "volume": 30,
                "delta": 8,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars_xyz,
                    chart_instance_id="chart-xyz",
                )
            )
        )

        # Query for chart-abc only — only that ingestion's bars are returned
        result_abc = workbench.get_mirror_bars(
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        assert len(result_abc) == 5
        # chart-abc bars have open in range [100, 104]
        assert all(100.0 <= b.open < 105.0 for b in result_abc)

        # Query for chart-xyz only — only that ingestion's bars are returned
        result_xyz = workbench.get_mirror_bars(
            chart_instance_id="chart-xyz",
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        assert len(result_xyz) == 5
        # chart-xyz bars have open in range [300, 304]
        assert all(300.0 <= b.open < 305.0 for b in result_xyz)

        # No chart_instance_id filter — all bars returned
        result_all = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        # Both ingestions contribute bars (same time window)
        assert len(result_all) == 10


def test_mirror_bars_no_matching_chart_instance_id_returns_empty() -> None:
    """get_mirror_bars with a non-existent chart_instance_id returns no bars."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 25,
                "delta": 5,
            }
            for i in range(3)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars,
                    chart_instance_id="chart-abc",
                )
            )
        )

        result = workbench.get_mirror_bars(
            chart_instance_id="chart-nonexistent",
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=2),
        )
        assert result == []


def test_mirror_bars_wrong_timeframe_returns_empty() -> None:
    """get_mirror_bars with a mismatched timeframe returns no bars."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 25,
                "delta": 5,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars,
                )
            )
        )

        # Request 5m bars — stored bars are 1m → filter discards them
        result = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_5,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        assert result == []


def test_mirror_bars_window_filter() -> None:
    """get_mirror_bars returns only bars within the requested window."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 25,
                "delta": 5,
            }
            for i in range(10)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars,
                )
            )
        )

        # Request window covering only bars 3-6 (indices 3,4,5,6)
        window_start = t0 + timedelta(minutes=3)
        window_end = t0 + timedelta(minutes=6)

        result = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=window_start,
            window_end=window_end,
        )

        assert len(result) == 4
        for bar in result:
            assert window_start <= bar.started_at <= window_end


def test_mirror_bars_preserves_raw_price_fields() -> None:
    """get_mirror_bars returns bars with all raw fields (open, high, low, close, volume, delta)."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": t0.isoformat(),
                "ended_at": (t0 + timedelta(seconds=59)).isoformat(),
                "open": 150.0,
                "high": 155.0,
                "low": 148.0,
                "close": 153.0,
                "volume": 1000,
                "delta": 200,
                "bid_volume": 400,
                "ask_volume": 600,
            }
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars,
                )
            )
        )

        result = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0 - timedelta(hours=1),
            window_end=t0 + timedelta(hours=1),
        )

        assert len(result) == 1
        bar = result[0]
        assert bar.open == 150.0
        assert bar.high == 155.0
        assert bar.low == 148.0
        assert bar.close == 153.0
        assert bar.volume == 1000
        assert bar.delta == 200


# ---------------------------------------------------------------------------
# Test 7: Contract rollover — two contracts do not overwrite each other
# ---------------------------------------------------------------------------

def test_contract_rollover_different_contracts_isolated() -> None:
    """Bars for NQH6 and NQM6 are stored and queried independently."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0_h6 = datetime(2026, 3, 16, 9, 30, tzinfo=UTC)  # NQH6 window
        t0_m6 = datetime(2026, 3, 20, 9, 30, tzinfo=UTC)  # NQM6 window (rollover)

        bars_h6 = [
            {
                "started_at": (t0_h6 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0_h6 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 200.0 + i,
                "high": 201.0 + i,
                "low": 199.0 + i,
                "close": 200.5 + i,
                "volume": 50,
                "delta": 10,
            }
            for i in range(5)
        ]
        bars_m6 = [
            {
                "started_at": (t0_m6 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0_m6 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 210.0 + i,
                "high": 211.0 + i,
                "low": 209.0 + i,
                "close": 210.5 + i,
                "volume": 60,
                "delta": 12,
            }
            for i in range(5)
        ]

        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=bars_h6,
                    chart_instance_id="chart-abc",
                )
            )
        )
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQM6",
                    timeframe="1m",
                    bars=bars_m6,
                    chart_instance_id="chart-abc",
                )
            )
        )

        result_h6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0_h6,
            window_end=t0_h6 + timedelta(minutes=4),
        )
        assert len(result_h6) == 5
        assert all(200.0 <= b.open < 210.0 for b in result_h6)  # NQH6 price range

        result_m6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQM6",
            timeframe=Timeframe.MIN_1,
            window_start=t0_m6,
            window_end=t0_m6 + timedelta(minutes=4),
        )
        assert len(result_m6) == 5
        assert all(210.0 <= b.open < 220.0 for b in result_m6)  # NQM6 price range

        assert all(b.started_at < t0_m6 for b in result_h6)
        assert all(b.started_at >= t0_m6 for b in result_m6)


def test_contract_rollover_overlapping_time_windows_still_distinguished() -> None:
    """When two contracts have overlapping time windows, they are still isolated by symbol."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 20, 9, 30, tzinfo=UTC)
        bars_h6 = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 200.0 + i,
                "high": 201.0 + i,
                "low": 199.0 + i,
                "close": 200.5 + i,
                "volume": 50,
                "delta": 10,
            }
            for i in range(5)
        ]
        bars_m6 = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 210.0 + i,
                "high": 211.0 + i,
                "low": 209.0 + i,
                "close": 210.5 + i,
                "volume": 60,
                "delta": 12,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(symbol="NQH6", timeframe="1m", bars=bars_h6)
            )
        )
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(symbol="NQM6", timeframe="1m", bars=bars_m6)
            )
        )

        result_h6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        result_m6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQM6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )

        assert len(result_h6) == 5
        assert len(result_m6) == 5

        h6_prices = {b.close for b in result_h6}
        m6_prices = {b.close for b in result_m6}
        assert h6_prices != m6_prices
        assert h6_prices.issubset({round(200.5 + i, 1) for i in range(5)})
        assert m6_prices.issubset({round(210.5 + i, 1) for i in range(5)})


def test_contract_rollover_wrong_symbol_returns_nothing() -> None:
    """Querying a contract symbol that has no bars returns an empty list."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 20, 9, 30, tzinfo=UTC)
        bars = [
            {
                "started_at": (t0 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 200.0 + i,
                "high": 201.0 + i,
                "low": 199.0 + i,
                "close": 200.5 + i,
                "volume": 50,
                "delta": 10,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(symbol="NQH6", timeframe="1m", bars=bars)
            )
        )

        result = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQM6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=4),
        )
        assert result == []


def test_contract_rollover_no_cross_contamination_after_rollover() -> None:
    """After NQH6 expires, existing NQM6 mirror data is unaffected by subsequent NQH6 queries."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0_h6 = datetime(2026, 3, 16, 9, 30, tzinfo=UTC)  # NQH6 active
        t0_m6 = datetime(2026, 3, 20, 9, 30, tzinfo=UTC)  # NQM6 active (after rollover)

        bars_h6 = [
            {
                "started_at": (t0_h6 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0_h6 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 200.0 + i,
                "high": 201.0 + i,
                "low": 199.0 + i,
                "close": 200.5 + i,
                "volume": 50,
                "delta": 10,
            }
            for i in range(5)
        ]
        bars_m6 = [
            {
                "started_at": (t0_m6 + timedelta(minutes=i)).isoformat(),
                "ended_at": (t0_m6 + timedelta(minutes=i + 1) - timedelta(seconds=1)).isoformat(),
                "open": 210.0 + i,
                "high": 211.0 + i,
                "low": 209.0 + i,
                "close": 210.5 + i,
                "volume": 60,
                "delta": 12,
            }
            for i in range(5)
        ]
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(symbol="NQH6", timeframe="1m", bars=bars_h6)
            )
        )
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(symbol="NQM6", timeframe="1m", bars=bars_m6)
            )
        )

        result_h6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0_h6,
            window_end=t0_h6 + timedelta(minutes=4),
        )
        assert len(result_h6) == 5
        assert result_h6[0].open == 200.0
        assert result_h6[-1].open == 204.0

        result_m6 = workbench.get_mirror_bars(
            chart_instance_id=None,
            contract_symbol="NQM6",
            timeframe=Timeframe.MIN_1,
            window_start=t0_m6,
            window_end=t0_m6 + timedelta(minutes=4),
        )
        assert len(result_m6) == 5
        assert result_m6[0].open == 210.0
        assert result_m6[-1].open == 214.0


def test_mirror_and_continuous_queries_return_different_semantics() -> None:
    """Mirror queries return raw contract bars; continuous queries return root-symbol derived segments."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        workbench = ReplayWorkbenchService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=[
                        {
                            "started_at": t0.isoformat(),
                            "ended_at": (t0 + timedelta(seconds=59)).isoformat(),
                            "open": 200.0,
                            "high": 201.0,
                            "low": 199.0,
                            "close": 200.5,
                            "volume": 25,
                            "delta": 5,
                            "bar_timestamp_utc": t0.isoformat(),
                            "original_bar_time_text": "2026-03-22 09:30:00 ET",
                        }
                    ],
                )
            )
        )
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQM6",
                    timeframe="1m",
                    bars=[
                        {
                            "started_at": (t0 + timedelta(minutes=1)).isoformat(),
                            "ended_at": (t0 + timedelta(minutes=1, seconds=59)).isoformat(),
                            "open": 210.0,
                            "high": 211.0,
                            "low": 209.0,
                            "close": 210.5,
                            "volume": 30,
                            "delta": 7,
                            "bar_timestamp_utc": (t0 + timedelta(minutes=1)).isoformat(),
                            "original_bar_time_text": "2026-03-22 09:31:00 ET",
                        }
                    ],
                )
            )
        )

        mirror = workbench.get_mirror_bars(
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            timeframe=Timeframe.MIN_1,
            window_start=t0,
            window_end=t0 + timedelta(minutes=1),
        )
        continuous = workbench.get_continuous_bars(
            root_symbol="NQ",
            timeframe=Timeframe.MIN_1,
            roll_mode=RollMode.BY_CONTRACT_START,
            window_start=t0,
            window_end=t0 + timedelta(minutes=1),
        )

        assert len(mirror) == 1
        assert len(continuous) == 2
        assert mirror[0].open == 200.0
        assert mirror[0].bar_timestamp_utc == t0
        assert [bar.open for bar in continuous] == [200.0, 210.0]
        assert [bar.bar_timestamp_utc for bar in continuous] == [t0, t0 + timedelta(minutes=1)]


def test_raw_mirror_repository_root_symbol_filter_returns_multiple_contracts() -> None:
    """Repository root_symbol queries return all matching contracts without mixing chart instances."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQH6",
                    timeframe="1m",
                    bars=[
                        {
                            "started_at": t0.isoformat(),
                            "ended_at": (t0 + timedelta(seconds=59)).isoformat(),
                            "open": 100.0,
                            "high": 101.0,
                            "low": 99.0,
                            "close": 100.5,
                            "volume": 10,
                            "delta": 2,
                            "bar_timestamp_utc": t0.isoformat(),
                            "original_bar_time_text": "2026-03-22 09:30:00 ET",
                        }
                    ],
                    chart_instance_id="chart-abc",
                )
            )
        )
        service.ingest_history_bars(
            AdapterHistoryBarsPayload.model_validate(
                _build_history_payload_dict(
                    symbol="NQM6",
                    timeframe="1m",
                    bars=[
                        {
                            "started_at": (t0 + timedelta(minutes=1)).isoformat(),
                            "ended_at": (t0 + timedelta(minutes=1, seconds=59)).isoformat(),
                            "open": 110.0,
                            "high": 111.0,
                            "low": 109.0,
                            "close": 110.5,
                            "volume": 11,
                            "delta": 3,
                            "bar_timestamp_utc": (t0 + timedelta(minutes=1)).isoformat(),
                            "original_bar_time_text": "2026-03-22 09:31:00 ET",
                        }
                    ],
                    chart_instance_id="chart-abc",
                )
            )
        )

        rows = repo.list_atas_chart_bars_raw(root_symbol="NQ", timeframe="1m", limit=10)
        assert len(rows) == 2
        assert {row.contract_symbol for row in rows} == {"NQH6", "NQM6"}
        assert {row.root_symbol for row in rows} == {"NQ"}


def test_raw_mirror_repository_same_key_upsert_is_idempotent() -> None:
    """The raw mirror primary key stays idempotent for repeated UTC bars from the same chart+contract."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)
        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        payload = AdapterHistoryBarsPayload.model_validate(
            _build_history_payload_dict(
                symbol="NQH6",
                timeframe="1m",
                bars=[
                    {
                        "started_at": t0.isoformat(),
                        "ended_at": (t0 + timedelta(seconds=59)).isoformat(),
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": 100.5,
                        "volume": 10,
                        "delta": 2,
                        "bar_timestamp_utc": t0.isoformat(),
                        "original_bar_time_text": "2026-03-22 09:30:00 ET",
                    }
                ],
                chart_instance_id="chart-abc",
            )
        )

        service.ingest_history_bars(payload)
        service.ingest_history_bars(payload.model_copy(update={"message_id": "msg-repeat"}))

        rows = repo.list_atas_chart_bars_raw(
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            timeframe="1m",
            limit=10,
        )
        assert len(rows) == 1
        assert rows[0].bar_timestamp_utc == t0
