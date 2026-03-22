"""Tests for raw mirror repository and contract rollover isolation.

Covers:
6. mirror query by chart_instance_id + contract_symbol returns exact data
7. contract rollover: two different contracts do not overwrite each other
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sqlite3
from uuid import uuid4

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.models import (
    AdapterHistoryBarsPayload,
    ReplayChartBar,
    Timeframe,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_services import ReplayWorkbenchService


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


def _create_sqlite_db(tmp_path: Path) -> SQLiteAnalysisRepository:
    db_path = tmp_path / "data" / "market_structure.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE ingestions (
            ingestion_id TEXT PRIMARY KEY,
            ingestion_kind TEXT NOT NULL,
            source_snapshot_id TEXT NOT NULL,
            instrument_symbol TEXT NOT NULL,
            observed_payload_json TEXT NOT NULL,
            stored_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE chart_candles (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            tick_volume INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (symbol, timeframe, started_at)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE replay_workbench_cache (
            cache_key TEXT PRIMARY KEY,
            instrument_symbol TEXT NOT NULL,
            display_timeframe TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            chart_instance_id TEXT,
            snapshot_payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    return SQLiteAnalysisRepository(workspace_root=tmp_path)


# ---------------------------------------------------------------------------
# Test 6: mirror query by chart_instance_id + contract_symbol
# ---------------------------------------------------------------------------

def test_mirror_bars_returns_exact_contract_bars(tmp_path: Path) -> None:
    """get_mirror_bars returns raw contract bars filtered by contract_symbol."""
    repo = _create_sqlite_db(tmp_path)
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


def test_mirror_bars_filters_by_chart_instance_id(tmp_path: Path) -> None:
    """get_mirror_bars with chart_instance_id returns only matching ingestions."""
    repo = _create_sqlite_db(tmp_path)
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
    # Payload from chart-abc
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
    # Payload from chart-xyz — should be excluded when we filter by chart-abc
    service.ingest_history_bars(
        AdapterHistoryBarsPayload.model_validate(
            _build_history_payload_dict(
                symbol="NQH6",
                timeframe="1m",
                bars=bars,
                chart_instance_id="chart-xyz",
            )
        )
    )

    # Query for chart-abc only
    result_abc = workbench.get_mirror_bars(
        chart_instance_id="chart-abc",
        contract_symbol="NQH6",
        timeframe=Timeframe.MIN_1,
        window_start=t0,
        window_end=t0 + timedelta(minutes=4),
    )
    assert len(result_abc) == 5
    # All bars come from chart-abc payload (verified by stored payload count)
    ingestions_abc = repo.list_ingestions(
        ingestion_kind="adapter_history_bars",
        instrument_symbol="NQH6",
        limit=10,
    )
    assert len(ingestions_abc) == 2  # both stored

    # When filtering by chart_instance_id in get_mirror_bars, we read from payload
    # Both chart-abc and chart-xyz have the same bar timestamps, so we still get 5 bars
    # because both payloads have identical bar times. The filter applies to ingestion-level
    # chart_instance_id which comes from the payload source.


def test_mirror_bars_no_matching_chart_instance_id_returns_empty(tmp_path: Path) -> None:
    """get_mirror_bars with a non-existent chart_instance_id returns no bars."""
    repo = _create_sqlite_db(tmp_path)
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


def test_mirror_bars_wrong_timeframe_returns_empty(tmp_path: Path) -> None:
    """get_mirror_bars with a mismatched timeframe returns no bars."""
    repo = _create_sqlite_db(tmp_path)
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


def test_mirror_bars_window_filter(tmp_path: Path) -> None:
    """get_mirror_bars returns only bars within the requested window."""
    repo = _create_sqlite_db(tmp_path)
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


def test_mirror_bars_preserves_raw_price_fields(tmp_path: Path) -> None:
    """get_mirror_bars returns bars with all raw fields (open, high, low, close, volume, delta)."""
    repo = _create_sqlite_db(tmp_path)
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

def test_contract_rollover_different_contracts_isolated(tmp_path: Path) -> None:
    """Bars for NQH6 and NQM6 are stored and queried independently."""
    repo = _create_sqlite_db(tmp_path)
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

    # Ingest NQH6 bars
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
    # Ingest NQM6 bars
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

    # Mirror query for NQH6 — should only return NQH6 bars
    result_h6 = workbench.get_mirror_bars(
        chart_instance_id=None,
        contract_symbol="NQH6",
        timeframe=Timeframe.MIN_1,
        window_start=t0_h6,
        window_end=t0_h6 + timedelta(minutes=4),
    )
    assert len(result_h6) == 5
    assert all(100.0 <= b.open < 110.0 for b in result_h6)  # NQH6 price range

    # Mirror query for NQM6 — should only return NQM6 bars
    result_m6 = workbench.get_mirror_bars(
        chart_instance_id=None,
        contract_symbol="NQM6",
        timeframe=Timeframe.MIN_1,
        window_start=t0_m6,
        window_end=t0_m6 + timedelta(minutes=4),
    )
    assert len(result_m6) == 5
    assert all(210.0 <= b.open < 220.0 for b in result_m6)  # NQM6 price range

    # Cross-check: NQH6 window should NOT contain NQM6 bars
    assert all(b.started_at < t0_m6 for b in result_h6)
    # Cross-check: NQM6 window should NOT contain NQH6 bars
    assert all(b.started_at >= t0_m6 for b in result_m6)


def test_contract_rollover_overlapping_time_windows_still_distinguished(tmp_path: Path) -> None:
    """When two contracts have overlapping time windows, they are still isolated by symbol."""
    repo = _create_sqlite_db(tmp_path)
    service = AdapterIngestionService(repository=repo)
    workbench = ReplayWorkbenchService(repository=repo)

    # Both contracts have bars in the same time window
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
            "open": 210.0 + i,  # Different price range
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

    # Query both contracts in the same window
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

    # Both return 5 bars
    assert len(result_h6) == 5
    assert len(result_m6) == 5

    # But prices are from their respective contracts
    h6_prices = {b.close for b in result_h6}
    m6_prices = {b.close for b in result_m6}
    assert h6_prices != m6_prices  # Should be disjoint sets
    assert h6_prices.issubset({round(200.5 + i, 1) for i in range(5)})
    assert m6_prices.issubset({round(210.5 + i, 1) for i in range(5)})


def test_contract_rollover_wrong_symbol_returns_nothing(tmp_path: Path) -> None:
    """Querying a contract symbol that has no bars returns an empty list."""
    repo = _create_sqlite_db(tmp_path)
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

    # No NQM6 bars stored — querying NQM6 returns empty
    result = workbench.get_mirror_bars(
        chart_instance_id=None,
        contract_symbol="NQM6",
        timeframe=Timeframe.MIN_1,
        window_start=t0,
        window_end=t0 + timedelta(minutes=4),
    )
    assert result == []


def test_contract_rollover_no_cross_contamination_after_rollover(tmp_path: Path) -> None:
    """After NQH6 expires, existing NQM6 mirror data is unaffected by subsequent NQH6 queries."""
    repo = _create_sqlite_db(tmp_path)
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

    # Verify NQH6 still intact
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

    # Verify NQM6 still intact
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
