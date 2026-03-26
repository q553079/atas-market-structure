from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from atas_market_structure.models import AdapterHistoryInventoryPayload, ReplayWorkbenchBackfillRange, Timeframe
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_replay_backfill_ranges import chunk_backfill_ranges
from atas_market_structure.workbench_services import ReplayWorkbenchService


@contextmanager
def _temp_repo():
    tmp = Path(tempfile.mkdtemp(prefix="atas-backfill-range-"))
    try:
        db_path = tmp / "data" / "market_structure.db"
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()
        yield repo
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _build_history_inventory_payload_dict(
    *,
    symbol: str = "GC",
    timeframe: str = "1m",
    chart_instance_id: str | None = "chart-gc-1m",
    first_loaded_bar_started_at_utc: datetime,
    latest_loaded_bar_started_at_utc: datetime,
    loaded_bar_count: int,
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "message_id": f"inventory-{uuid4().hex[:8]}",
        "emitted_at": datetime.now(tz=UTC).isoformat(),
        "observed_window_start": first_loaded_bar_started_at_utc.isoformat(),
        "observed_window_end": (latest_loaded_bar_started_at_utc + timedelta(seconds=59)).isoformat(),
        "source": {
            "system": "ATAS",
            "instance_id": "DESKTOP-TEST",
            "chart_instance_id": chart_instance_id,
            "adapter_version": "0.1.0",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_name": "America/New_York",
            "chart_display_utc_offset_minutes": -300,
        },
        "instrument": {
            "symbol": symbol,
            "root_symbol": symbol,
            "contract_symbol": symbol,
            "venue": "CME",
            "tick_size": 0.1,
            "currency": "USD",
        },
        "display_timeframe": timeframe,
        "message_type": "history_inventory",
        "bar_timeframe": timeframe,
        "loaded_bar_count": loaded_bar_count,
        "current_bar_count": loaded_bar_count,
        "latest_loaded_bar_index": max(loaded_bar_count - 1, 0),
        "first_loaded_bar_started_at_utc": first_loaded_bar_started_at_utc.isoformat(),
        "latest_loaded_bar_started_at_utc": latest_loaded_bar_started_at_utc.isoformat(),
        "latest_completed_bar_started_at_utc": latest_loaded_bar_started_at_utc.isoformat(),
        "time_context": {
            "instrument_timezone_value": "36",
            "instrument_timezone_source": "exchange_metadata",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_source": "atlas_payload",
            "chart_display_timezone_name": "America/New_York",
            "chart_display_utc_offset_minutes": -300,
            "timezone_capture_confidence": "high",
            "collector_local_timezone_name": "America/Chicago",
            "collector_local_utc_offset_minutes": -300,
            "timestamp_basis": "chart_display_timezone",
            "started_at_output_timezone": "UTC",
            "started_at_time_source": "chart_display_timezone",
        },
    }


def test_chunk_backfill_ranges_splits_large_minute_window() -> None:
    requested_range = ReplayWorkbenchBackfillRange(
        range_start=datetime(2026, 3, 26, 7, 1, 1, tzinfo=UTC),
        range_end=datetime(2026, 3, 26, 16, 50, 0, tzinfo=UTC),
    )

    chunked = chunk_backfill_ranges(
        display_timeframe=Timeframe.MIN_1,
        requested_ranges=[requested_range],
        max_bars_per_range=180,
    )

    assert len(chunked) == 4
    assert chunked[0].range_start == requested_range.range_start
    assert chunked[-1].range_end == requested_range.range_end
    assert chunked[0].range_end == datetime(2026, 3, 26, 10, 1, 0, tzinfo=UTC)
    assert chunked[1].range_start == datetime(2026, 3, 26, 10, 1, 1, tzinfo=UTC)
    assert chunked[1].range_end == datetime(2026, 3, 26, 13, 1, 0, tzinfo=UTC)
    assert chunked[2].range_start == datetime(2026, 3, 26, 13, 1, 1, tzinfo=UTC)
    assert chunked[2].range_end == datetime(2026, 3, 26, 16, 1, 0, tzinfo=UTC)
    assert chunked[3].range_start == datetime(2026, 3, 26, 16, 1, 1, tzinfo=UTC)


def test_chunk_backfill_ranges_keeps_small_window_unchanged() -> None:
    requested_range = ReplayWorkbenchBackfillRange(
        range_start=datetime(2026, 3, 26, 14, 30, 0, tzinfo=UTC),
        range_end=datetime(2026, 3, 26, 15, 0, 0, tzinfo=UTC),
    )

    chunked = chunk_backfill_ranges(
        display_timeframe=Timeframe.MIN_1,
        requested_ranges=[requested_range],
        max_bars_per_range=180,
    )

    assert chunked == [requested_range]


def test_ingest_history_inventory_queues_only_first_chunk_per_request() -> None:
    with _temp_repo() as repo:
        workbench = ReplayWorkbenchService(repository=repo)
        window_start = datetime(2026, 3, 26, 7, 1, tzinfo=UTC)
        window_end = datetime(2026, 3, 26, 16, 50, tzinfo=UTC)

        result = workbench.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=window_start,
                    latest_loaded_bar_started_at_utc=window_end,
                    loaded_bar_count=590,
                )
            )
        )

        requested_ranges = result["requested_ranges"]
        assert result["queued"] is True
        assert len(requested_ranges) == 1
        assert requested_ranges[0]["range_start"] == window_start
        assert requested_ranges[0]["range_end"] == datetime(2026, 3, 26, 10, 0, 59, tzinfo=UTC)
