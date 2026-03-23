from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import shutil
import tempfile

from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchAtasBackfillStatus,
)
from atas_market_structure.repository import SQLiteAnalysisRepository
from atas_market_structure.workbench_services import ReplayWorkbenchService


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


def test_backfill_command_and_ack_roundtrip_preserves_identity_fields() -> None:
    with _temp_repo() as repo:
        service = ReplayWorkbenchService(repository=repo)
        request = ReplayWorkbenchAtasBackfillRequest(
            cache_key="NQ|1m|2026-03-22T09:30:00Z|2026-03-22T10:00:00Z",
            instrument_symbol="NQH6",
            contract_symbol="NQH6",
            root_symbol="NQ",
            target_contract_symbol="NQH6",
            target_root_symbol="NQ",
            display_timeframe="1m",
            window_start=datetime(2026, 3, 22, 9, 30, tzinfo=UTC),
            window_end=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
            chart_instance_id="chart-abc",
            requested_ranges=[],
            missing_segments=[],
            request_history_bars=True,
            request_history_footprint=True,
            reason="manual_repair",
        )

        accepted = service.request_atas_backfill(request)
        dispatched = service.poll_atas_backfill(
            instrument_symbol="NQH6",
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            root_symbol="NQ",
        )
        assert accepted.request.request_id == dispatched.request.request_id
        assert dispatched.request.target_contract_symbol == "NQH6"
        assert dispatched.request.target_root_symbol == "NQ"

        ack_payload = AdapterBackfillAcknowledgeRequest.model_validate(
            {
                "request_id": accepted.request.request_id,
                "cache_key": request.cache_key,
                "instrument_symbol": "NQH6",
                "chart_instance_id": "chart-abc",
                "acknowledged_at": "2026-03-22T10:01:00Z",
                "acknowledged_history_bars": True,
                "acknowledged_history_footprint": True,
                "latest_loaded_bar_started_at": "2026-03-22T10:00:00Z",
                "note": "collector resend completed",
            }
        )
        response = service.acknowledge_atas_backfill(ack_payload)

        assert response.request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED
        assert response.request.cache_key == request.cache_key
        assert response.request.instrument_symbol == "NQH6"
        assert response.request.contract_symbol == "NQH6"
        assert response.request.root_symbol == "NQ"
        assert response.request.target_contract_symbol == "NQH6"
        assert response.request.target_root_symbol == "NQ"
        assert response.request.chart_instance_id == "chart-abc"
        assert response.request.acknowledged_chart_instance_id == "chart-abc"
        assert response.request.acknowledged_history_bars is True
        assert response.request.acknowledged_history_footprint is True
        assert response.request.latest_loaded_bar_started_at == datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
        assert response.request.note == "collector resend completed"


def test_backfill_ack_requires_matching_request_identity() -> None:
    with _temp_repo() as repo:
        service = ReplayWorkbenchService(repository=repo)
        request = ReplayWorkbenchAtasBackfillRequest(
            cache_key="ck-identity",
            instrument_symbol="NQM6",
            contract_symbol="NQM6",
            root_symbol="NQ",
            display_timeframe="1m",
            window_start=datetime(2026, 3, 22, 9, 30, tzinfo=UTC),
            window_end=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
            chart_instance_id="chart-main",
            requested_ranges=[],
            missing_segments=[],
            request_history_bars=True,
            request_history_footprint=False,
            reason="manual_repair",
        )
        accepted = service.request_atas_backfill(request)

        response = service.acknowledge_atas_backfill(
            AdapterBackfillAcknowledgeRequest(
                request_id=accepted.request.request_id,
                cache_key="ck-identity",
                instrument_symbol="NQM6",
                chart_instance_id="chart-other",
                acknowledged_at=datetime(2026, 3, 22, 10, 1, tzinfo=UTC),
                acknowledged_history_bars=True,
                acknowledged_history_footprint=False,
            )
        )

        assert response.request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED
        assert response.request.acknowledged_chart_instance_id == "chart-other"
        assert response.request.chart_instance_id == "chart-main"
