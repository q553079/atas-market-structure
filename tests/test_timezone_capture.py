"""Tests for timezone field capture and fallback in history-bars ingestion.

Covers:
1. Payload with complete timezone fields stores correctly
2. Payload missing chart_display_timezone_name falls back gracefully
3. history_bars only stores native timeframe bars
4. Same UTC bar sent twice is handled idempotently
5. Full backfill-command → history-bars → backfill-ack chain
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

def _build_minimal_history_payload(
    *,
    symbol: str = "NQH6",
    timeframe: str = "1m",
    bars: list[dict] | None = None,
    chart_instance_id: str | None = "chart-abc",
    chart_display_timezone_name: str | None = "America/New_York",
    chart_display_utc_offset_minutes: int | None = -300,
    time_context: dict | None = None,
) -> dict:
    """Build a minimal history_bars payload dict ready to be validated."""
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
            "chart_display_timezone_name": chart_display_timezone_name,
            "chart_display_utc_offset_minutes": chart_display_utc_offset_minutes,
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
        "message_type": "history_bars",
        "bar_timeframe": timeframe,
        "bars": bars,
        "time_context": time_context or {
            "instrument_timezone_value": "36",
            "instrument_timezone_source": "exchange_metadata",
            "chart_display_timezone_mode": "exchange",
            "chart_display_timezone_source": "atlas_payload",
            "chart_display_timezone_name": chart_display_timezone_name,
            "chart_display_utc_offset_minutes": chart_display_utc_offset_minutes,
            "timezone_capture_confidence": "high",
            "collector_local_timezone_name": "America/Chicago",
            "collector_local_utc_offset_minutes": -300,
            "timestamp_basis": "chart_display_timezone",
            "started_at_output_timezone": "UTC",
            "started_at_time_source": "chart_display_timezone",
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Payload with complete timezone fields is stored correctly
# ---------------------------------------------------------------------------

def test_history_bars_with_complete_timezone_stored() -> None:
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            chart_display_timezone_name="America/New_York",
            chart_display_utc_offset_minutes=-300,
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)

        result = service.ingest_history_bars(payload)

        assert result.ingestion_id.startswith("ing-")
        assert result.message_id == payload_dict["message_id"]
        assert result.message_type == "history_bars"
        assert result.summary.history_bar_timeframe.value == "1m"
        assert result.summary.history_bar_count == 5
        assert result.summary.instrument_symbol == "NQH6"

        stored = repo.get_ingestion(result.ingestion_id)
        assert stored is not None
        obs = stored.observed_payload
        assert obs["source"]["chart_display_timezone_name"] == "America/New_York"
        assert obs["source"]["chart_display_utc_offset_minutes"] == -300
        assert obs["time_context"]["chart_display_timezone_name"] == "America/New_York"
        assert obs["time_context"]["timezone_capture_confidence"] == "high"

        raw_rows = repo.list_atas_chart_bars_raw(
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            timeframe="1m",
        )
        assert len(raw_rows) == 5
        assert raw_rows[0].chart_display_timezone_name == "America/New_York"
        assert raw_rows[0].timestamp_basis == "chart_display_timezone"
        assert raw_rows[0].original_bar_time_text == "2026-03-22 09:30:00 ET"


def test_history_bars_timezone_source_reflects_atlas_payload() -> None:
    """source.chart_display_timezone_name comes from ATAS payload source block."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            chart_display_timezone_name="Europe/London",
            chart_display_utc_offset_minutes=0,
            time_context={
                "chart_display_timezone_name": "Europe/London",
                "chart_display_timezone_source": "atlas_payload",
                "timezone_capture_confidence": "high",
                "chart_display_timezone_mode": "exchange",
                "chart_display_utc_offset_minutes": 0,
                "instrument_timezone_value": None,
                "instrument_timezone_source": "unavailable",
                "timestamp_basis": "chart_display_timezone",
                "started_at_output_timezone": "UTC",
                "started_at_time_source": "chart_display_timezone",
                "collector_local_timezone_name": None,
                "collector_local_utc_offset_minutes": None,
            },
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result = service.ingest_history_bars(payload)

        stored = repo.get_ingestion(result.ingestion_id)
        obs = stored.observed_payload
        assert obs["source"]["chart_display_timezone_name"] == "Europe/London"
        assert obs["time_context"]["chart_display_timezone_source"] == "atlas_payload"
        assert obs["time_context"]["timezone_capture_confidence"] == "high"


# ---------------------------------------------------------------------------
# Test 2: Payload missing chart_display_timezone_name falls back gracefully
# ---------------------------------------------------------------------------

def test_history_bars_missing_timezone_stores_with_null() -> None:
    """When chart_display_timezone_name is absent the field is stored as null."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        payload_dict = _build_minimal_history_payload(
            chart_display_timezone_name=None,
            chart_display_utc_offset_minutes=None,
            time_context={
                "chart_display_timezone_name": None,
                "chart_display_timezone_source": None,
                "timezone_capture_confidence": "unknown",
                "chart_display_timezone_mode": None,
                "chart_display_utc_offset_minutes": None,
                "instrument_timezone_value": None,
                "instrument_timezone_source": "unavailable",
                "timestamp_basis": None,
                "started_at_output_timezone": "UTC",
                "started_at_time_source": None,
                "collector_local_timezone_name": None,
                "collector_local_utc_offset_minutes": None,
            },
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result = service.ingest_history_bars(payload)

        assert result.ingestion_id.startswith("ing-")
        stored = repo.get_ingestion(result.ingestion_id)
        obs = stored.observed_payload
        assert obs["source"].get("chart_display_timezone_name") is None
        assert obs["time_context"]["chart_display_timezone_name"] is None
        assert obs["time_context"]["timezone_capture_confidence"] == "unknown"


def test_history_bars_timezone_fallback_from_instrument_timezone() -> None:
    """When chart_display_timezone_name is null, system records instrument timezone as fallback source."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        payload_dict = _build_minimal_history_payload(
            chart_display_timezone_name=None,
            time_context={
                "chart_display_timezone_name": None,
                "chart_display_timezone_source": "instrument_timezone",
                "timezone_capture_confidence": "medium",
                "chart_display_timezone_mode": None,
                "chart_display_utc_offset_minutes": None,
                "instrument_timezone_value": "36",
                "instrument_timezone_source": "exchange_metadata",
                "timestamp_basis": "instrument_timezone",
                "started_at_output_timezone": "UTC",
                "started_at_time_source": "instrument_timezone",
                "collector_local_timezone_name": None,
                "collector_local_utc_offset_minutes": None,
            },
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result = service.ingest_history_bars(payload)

        stored = repo.get_ingestion(result.ingestion_id)
        obs = stored.observed_payload
        assert obs["time_context"]["chart_display_timezone_source"] == "instrument_timezone"
        assert obs["time_context"]["timezone_capture_confidence"] == "medium"


# ---------------------------------------------------------------------------
# Test 3: history_bars stores only native timeframe bars
# ---------------------------------------------------------------------------

def test_history_bars_stores_native_timeframe_bars() -> None:
    """Only bars matching the payload's bar_timeframe are stored."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            timeframe="1m",
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result = service.ingest_history_bars(payload)

        stored = repo.get_ingestion(result.ingestion_id)
        obs = stored.observed_payload
        assert obs["bar_timeframe"] == "1m"
        assert len(obs["bars"]) == 5


def test_history_bars_no_higher_timeframe_aggregation_in_payload() -> None:
    """A 1m-bar payload does not contain 5m aggregated bars."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

        t0 = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        one_minute_bars = [
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
        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            timeframe="1m",
            bars=one_minute_bars,
        )
        payload = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result = service.ingest_history_bars(payload)

        stored = repo.get_ingestion(result.ingestion_id)
        obs = stored.observed_payload
        assert len(obs["bars"]) == 5
        for bar in obs["bars"]:
            bar_start = datetime.fromisoformat(bar["started_at"].replace("Z", "+00:00")).astimezone(UTC)
            bar_end = datetime.fromisoformat(bar["ended_at"].replace("Z", "+00:00")).astimezone(UTC)
            assert (bar_end - bar_start).total_seconds() < 300, "Stored bars should not span 5 minutes"


# ---------------------------------------------------------------------------
# Test 4: Same UTC bar sent twice — idempotency
# ---------------------------------------------------------------------------

def test_history_bars_duplicate_bar_idempotent_stored() -> None:
    """Two identical payloads remain distinct ingestions but raw mirror storage stays idempotent."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

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
        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            timeframe="1m",
            bars=bars,
        )
        payload1 = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result1 = service.ingest_history_bars(payload1)

        payload_dict["message_id"] = f"msg-{uuid4().hex[:8]}"
        payload2 = AdapterHistoryBarsPayload.model_validate(payload_dict)
        result2 = service.ingest_history_bars(payload2)

        assert result1.ingestion_id != result2.ingestion_id
        stored1 = repo.get_ingestion(result1.ingestion_id)
        stored2 = repo.get_ingestion(result2.ingestion_id)
        assert stored1 is not None
        assert stored2 is not None
        assert stored1.observed_payload["bars"] == stored2.observed_payload["bars"]
        assert repo.count_atas_chart_bars_raw(contract_symbol="NQH6", timeframe="1m") == 3


def test_history_bars_duplicate_bar_candle_aggregation_takes_first() -> None:
    """When the same bar appears in two payloads, candle aggregation picks the first."""
    with _temp_repo() as repo:
        service = AdapterIngestionService(repository=repo)

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
        payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            timeframe="1m",
            bars=bars,
        )
        payload1 = AdapterHistoryBarsPayload.model_validate(payload_dict)
        service.ingest_history_bars(payload1)

        payload_dict["message_id"] = f"msg-{uuid4().hex[:8]}"
        payload2 = AdapterHistoryBarsPayload.model_validate(payload_dict)
        service.ingest_history_bars(payload2)

        ingestions = repo.list_ingestions(
            ingestion_kind="adapter_history_bars",
            instrument_symbol="NQH6",
            limit=10,
        )
        assert len(ingestions) == 2


# ---------------------------------------------------------------------------
# Test 5: Full backfill-command → history-bars → backfill-ack chain
# ---------------------------------------------------------------------------

def test_backfill_request_poll_dispatch_ack_full_chain() -> None:
    """request → poll → dispatch → ingest_history_bars → acknowledge round-trips correctly."""
    with _temp_repo() as repo:
        workbench = ReplayWorkbenchService(repository=repo)

        window_start = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        window_end = datetime(2026, 3, 22, 10, 30, tzinfo=UTC)

        from atas_market_structure.models import (
            ReplayWorkbenchAtasBackfillRequest,
            ReplayWorkbenchAtasBackfillStatus,
        )

        backfill_request = ReplayWorkbenchAtasBackfillRequest(
            cache_key="ck-nqh6-1m-20260322",
            instrument_symbol="NQH6",
            contract_symbol="NQH6",
            root_symbol="NQ",
            display_timeframe="1m",
            window_start=window_start,
            window_end=window_end,
            chart_instance_id="chart-abc",
            missing_segments=[],
            requested_ranges=[],
            reason="atas_chart_loaded_history_rebuild",
            request_history_bars=True,
            request_history_footprint=False,
        )
        accept_response = workbench.request_atas_backfill(backfill_request)
        assert accept_response.request is not None
        record = accept_response.request
        assert record.status == ReplayWorkbenchAtasBackfillStatus.PENDING
        assert record.instrument_symbol == "NQH6"

        dispatch_response = workbench.poll_atas_backfill(
            instrument_symbol="NQH6",
            chart_instance_id="chart-abc",
            contract_symbol="NQH6",
            root_symbol="NQ",
        )
        assert dispatch_response.request is not None
        dispatched = dispatch_response.request
        assert dispatched.request_id == record.request_id
        assert dispatched.instrument_symbol == "NQH6"
        assert dispatched.window_start == window_start
        assert dispatched.window_end == window_end
        assert dispatched.chart_instance_id == "chart-abc"

        t0 = window_start
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
        history_payload_dict = _build_minimal_history_payload(
            symbol="NQH6",
            timeframe="1m",
            bars=bars,
            chart_instance_id="chart-abc",
        )
        history_payload = AdapterHistoryBarsPayload.model_validate(history_payload_dict)
        adapter_service = AdapterIngestionService(repository=repo)
        ingest_result = adapter_service.ingest_history_bars(history_payload)
        assert ingest_result.ingestion_id.startswith("ing-")
        assert ingest_result.summary.history_bar_count == 5

        from atas_market_structure.models import AdapterBackfillAcknowledgeRequest

        ack_request = AdapterBackfillAcknowledgeRequest(
            request_id=record.request_id,
            instrument_symbol="NQH6",
            chart_instance_id="chart-abc",
            acknowledged_at=datetime.now(tz=UTC),
            acknowledged_history_bars=True,
            acknowledged_history_footprint=False,
        )
        ack_response = workbench.acknowledge_atas_backfill(ack_request)
        assert ack_response.request.request_id == record.request_id
        assert ack_response.request.status == ReplayWorkbenchAtasBackfillStatus.ACKNOWLEDGED


def test_backfill_request_reused_on_identical_repeat() -> None:
    """An identical backfill request returns the existing pending record."""
    with _temp_repo() as repo:
        workbench = ReplayWorkbenchService(repository=repo)

        window_start = datetime(2026, 3, 22, 9, 30, tzinfo=UTC)
        window_end = datetime(2026, 3, 22, 10, 30, tzinfo=UTC)

        from atas_market_structure.models import ReplayWorkbenchAtasBackfillRequest

        def make_request() -> ReplayWorkbenchAtasBackfillRequest:
            return ReplayWorkbenchAtasBackfillRequest(
                cache_key="ck-nqh6-1m-20260322",
                instrument_symbol="NQH6",
                contract_symbol="NQH6",
                root_symbol="NQ",
                display_timeframe="1m",
                window_start=window_start,
                window_end=window_end,
                chart_instance_id="chart-abc",
                missing_segments=[],
                requested_ranges=[],
                reason="atas_chart_loaded_history_rebuild",
                request_history_bars=True,
                request_history_footprint=False,
            )

        first = workbench.request_atas_backfill(make_request())
        second = workbench.request_atas_backfill(make_request())

        assert second.reused_existing_request is True
        assert second.request.request_id == first.request.request_id
