from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterHistoryInventoryPayload,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_services import ReplayWorkbenchService


@contextmanager
def _temp_repo():
    tmp = Path(tempfile.mkdtemp(prefix="atas-backfill-persist-"))
    try:
        db_path = tmp / "data" / "market_structure.db"
        repo = SQLiteAnalysisRepository(database_path=db_path)
        repo.initialize()
        yield repo
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _build_history_inventory_payload_dict(
    *,
    symbol: str = "NQH6",
    timeframe: str = "1m",
    chart_instance_id: str | None = "chart-auto-nqh6-1m",
    first_loaded_bar_started_at_utc: datetime | None = None,
    latest_loaded_bar_started_at_utc: datetime | None = None,
    loaded_bar_count: int = 5,
    current_bar_count: int | None = None,
) -> dict[str, object]:
    if first_loaded_bar_started_at_utc is None:
        first_loaded_bar_started_at_utc = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
    if latest_loaded_bar_started_at_utc is None:
        latest_loaded_bar_started_at_utc = first_loaded_bar_started_at_utc + timedelta(
            minutes=max(loaded_bar_count - 1, 0)
        )
    current_bar_count = current_bar_count if current_bar_count is not None else loaded_bar_count
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
            "root_symbol": symbol[:2] if len(symbol) >= 2 else symbol,
            "contract_symbol": symbol,
            "venue": "CME",
            "tick_size": 0.25,
            "currency": "USD",
        },
        "display_timeframe": timeframe,
        "message_type": "history_inventory",
        "bar_timeframe": timeframe,
        "loaded_bar_count": loaded_bar_count,
        "current_bar_count": current_bar_count,
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


def test_restart_restores_pending_history_inventory_backfill_guard() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
        workbench1 = ReplayWorkbenchService(repository=repo)

        first = workbench1.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=4),
                    loaded_bar_count=5,
                )
            )
        )

        workbench2 = ReplayWorkbenchService(repository=repo)
        second = workbench2.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=5),
                    loaded_bar_count=6,
                )
            )
        )

        assert first["queued"] is True
        assert second["queued"] is False
        assert second["status"] == "deferred"
        assert second["reason"] == "history_inventory_backfill_in_flight"
        assert second["request_id"] == first["request_id"]


def test_restart_restores_dispatched_backfill_lease() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
        workbench1 = ReplayWorkbenchService(repository=repo)

        first = workbench1.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=4),
                    loaded_bar_count=5,
                )
            )
        )
        dispatch1 = workbench1.poll_atas_backfill(
            instrument_symbol="NQH6",
            chart_instance_id="chart-auto-nqh6-1m",
            contract_symbol="NQH6",
            root_symbol="NQ",
        )

        workbench2 = ReplayWorkbenchService(repository=repo)
        second = workbench2.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=5),
                    loaded_bar_count=6,
                )
            )
        )
        dispatch2 = workbench2.poll_atas_backfill(
            instrument_symbol="NQH6",
            chart_instance_id="chart-auto-nqh6-1m",
            contract_symbol="NQH6",
            root_symbol="NQ",
        )

        assert first["queued"] is True
        assert dispatch1.request is not None
        assert second["queued"] is False
        assert second["status"] == "deferred"
        assert second["reason"] == "history_inventory_backfill_in_flight"
        assert second["request_id"] == dispatch1.request.request_id
        assert dispatch2.request is None


def test_restart_restores_acknowledged_backfill_cooldown() -> None:
    with _temp_repo() as repo:
        t0 = datetime(2026, 3, 23, 9, 30, tzinfo=UTC)
        workbench1 = ReplayWorkbenchService(repository=repo)

        workbench1.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=4),
                    loaded_bar_count=5,
                )
            )
        )
        dispatch = workbench1.poll_atas_backfill(
            instrument_symbol="NQH6",
            chart_instance_id="chart-auto-nqh6-1m",
            contract_symbol="NQH6",
            root_symbol="NQ",
        )
        assert dispatch.request is not None
        workbench1.acknowledge_atas_backfill(
            AdapterBackfillAcknowledgeRequest(
                request_id=dispatch.request.request_id,
                cache_key=dispatch.request.cache_key,
                instrument_symbol="NQH6",
                chart_instance_id="chart-auto-nqh6-1m",
                acknowledged_at=datetime.now(tz=UTC),
                acknowledged_history_bars=True,
                acknowledged_history_footprint=False,
                latest_loaded_bar_started_at=t0 + timedelta(minutes=4),
            )
        )

        workbench2 = ReplayWorkbenchService(repository=repo)
        second = workbench2.ingest_history_inventory(
            AdapterHistoryInventoryPayload.model_validate(
                _build_history_inventory_payload_dict(
                    first_loaded_bar_started_at_utc=t0,
                    latest_loaded_bar_started_at_utc=t0 + timedelta(minutes=5),
                    loaded_bar_count=6,
                )
            )
        )

        assert second["queued"] is False
        assert second["status"] == "deferred"
        assert second["reason"] == "history_inventory_backfill_cooldown"
        assert second["request_id"] == dispatch.request.request_id
