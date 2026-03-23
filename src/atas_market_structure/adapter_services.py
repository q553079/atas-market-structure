from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4

from atas_market_structure.adapter_bridge import AdapterPayloadBridge
from atas_market_structure.models import (
    AtasChartBarRaw,
    AdapterAcceptedResponse,
    AdapterAcceptedSummary,
    AdapterBridgedArtifact,
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
)
from atas_market_structure.regime_monitor_services import RegimeMonitor
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.services import IngestionOrchestrator

LOGGER = logging.getLogger(__name__)


class AdapterIngestionService:
    """Validates and stores low-latency adapter messages without forcing full analysis."""

    _HISTORY_RETENTION_DAYS_BY_SYMBOL = {
        "NQ": 30,
        "ES": 15,
    }
    _DEFAULT_HISTORY_RETENTION_DAYS = 15

    def __init__(
        self,
        repository: AnalysisRepository,
        orchestrator: IngestionOrchestrator | None = None,
        bridge: AdapterPayloadBridge | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator or IngestionOrchestrator(repository=repository)
        self._bridge = bridge or AdapterPayloadBridge(regime_monitor=RegimeMonitor(repository=repository))

    def ingest_continuous_state(self, payload: AdapterContinuousStatePayload) -> AdapterAcceptedResponse:
        self._bridge.regime_monitor.ingest_continuous_state(payload)
        LOGGER.info(
            "ingest_continuous_state: symbol=%s root_symbol=%s chart_instance_id=%s",
            payload.instrument.symbol,
            payload.instrument.root_symbol,
            payload.source.chart_instance_id,
        )
        summary = AdapterAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            observed_window_start=payload.observed_window_start,
            observed_window_end=payload.observed_window_end,
            significant_liquidity_count=len(payload.significant_liquidity),
            has_gap_reference=payload.gap_reference is not None,
            has_active_initiative_drive=payload.active_initiative_drive is not None,
            has_active_manipulation_leg=payload.active_manipulation_leg is not None,
            has_active_measured_move=payload.active_measured_move is not None,
            has_active_post_harvest_response=payload.active_post_harvest_response is not None,
        )
        accepted = self._store(
            ingestion_kind="adapter_continuous_state",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        durable_outputs: list[AdapterBridgedArtifact] = []
        bridge_errors: list[str] = []
        try:
            bridged = self._orchestrator.ingest_market_structure(self._bridge.build_market_structure(payload))
            durable_outputs.append(
                AdapterBridgedArtifact(
                    ingestion_kind="market_structure",
                    source_snapshot_id=bridged.analysis.source_snapshot_id,
                    ingestion_id=bridged.ingestion_id,
                    analysis_id=bridged.analysis_id,
                    route_key=bridged.route_key,
                ),
            )
        except Exception as exc:
            bridge_errors.append(f"market_structure bridge failed: {exc}")
        return AdapterAcceptedResponse(
            ingestion_id=accepted.ingestion_id,
            message_id=accepted.message_id,
            message_type=accepted.message_type,
            stored_at=accepted.stored_at,
            summary=accepted.summary,
            durable_outputs=durable_outputs,
            bridge_errors=bridge_errors,
        )

    def ingest_trigger_burst(self, payload: AdapterTriggerBurstPayload) -> AdapterAcceptedResponse:
        summary = AdapterAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            observed_window_start=payload.observed_window_start,
            observed_window_end=payload.observed_window_end,
            trigger_type=payload.trigger.trigger_type,
            reason_codes=payload.trigger.reason_codes,
            trade_event_count=(
                len(payload.pre_window.trade_events)
                + len(payload.event_window.trade_events)
                + len(payload.post_window.trade_events)
            ),
            depth_event_count=(
                len(payload.pre_window.depth_events)
                + len(payload.event_window.depth_events)
                + len(payload.post_window.depth_events)
            ),
            second_feature_count=(
                len(payload.pre_window.second_features)
                + len(payload.event_window.second_features)
                + len(payload.post_window.second_features)
            ),
        )
        accepted = self._store(
            ingestion_kind="adapter_trigger_burst",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        durable_outputs: list[AdapterBridgedArtifact] = []
        bridge_errors: list[str] = []
        try:
            bridged = self._orchestrator.ingest_event_snapshot(self._bridge.build_event_snapshot(payload))
            durable_outputs.append(
                AdapterBridgedArtifact(
                    ingestion_kind="event_snapshot",
                    source_snapshot_id=bridged.analysis.source_snapshot_id,
                    ingestion_id=bridged.ingestion_id,
                    analysis_id=bridged.analysis_id,
                    route_key=bridged.route_key,
                ),
            )
        except Exception as exc:
            bridge_errors.append(f"event_snapshot bridge failed: {exc}")
        return AdapterAcceptedResponse(
            ingestion_id=accepted.ingestion_id,
            message_id=accepted.message_id,
            message_type=accepted.message_type,
            stored_at=accepted.stored_at,
            summary=accepted.summary,
            durable_outputs=durable_outputs,
            bridge_errors=bridge_errors,
        )

    def ingest_history_bars(self, payload: AdapterHistoryBarsPayload) -> AdapterAcceptedResponse:
        self._purge_expired_history(
            instrument_symbol=payload.instrument.symbol,
            root_symbol=payload.instrument.root_symbol,
            contract_symbol=payload.instrument.contract_symbol,
        )
        self._bridge.regime_monitor.ingest_history_bars(payload)
        raw_mirror_bars = self._build_raw_mirror_bars(payload)
        raw_written = self._repository.upsert_atas_chart_bars_raw(raw_mirror_bars)
        analysis_symbol = (payload.instrument.root_symbol or payload.instrument.symbol).upper()
        bars_dicts = [b.model_dump() for b in payload.bars]
        self._bridge.regime_monitor.persist_history_bars_native(
            symbol=analysis_symbol,
            bars=bars_dicts,
            native_timeframe=payload.bar_timeframe,
        )
        LOGGER.info(
            "ingest_history_bars: raw_written=%s analysis_symbol=%s contract_symbol=%s chart_instance_id=%s timeframe=%s bars=%s",
            raw_written,
            analysis_symbol,
            payload.instrument.contract_symbol,
            payload.source.chart_instance_id,
            payload.bar_timeframe.value,
            len(payload.bars),
        )
        summary = AdapterAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            observed_window_start=payload.observed_window_start,
            observed_window_end=payload.observed_window_end,
            history_bar_count=len(payload.bars),
            history_bar_timeframe=payload.bar_timeframe,
        )
        accepted = self._store(
            ingestion_kind="adapter_history_bars",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        return AdapterAcceptedResponse(
            ingestion_id=accepted.ingestion_id,
            message_id=accepted.message_id,
            message_type=accepted.message_type,
            stored_at=accepted.stored_at,
            summary=accepted.summary,
            durable_outputs=[],
            bridge_errors=[],
        )

    def ingest_history_footprint(self, payload: AdapterHistoryFootprintPayload) -> AdapterAcceptedResponse:
        self._purge_expired_history(
            instrument_symbol=payload.instrument.symbol,
            root_symbol=payload.instrument.root_symbol,
            contract_symbol=payload.instrument.contract_symbol,
        )
        LOGGER.info(
            "ingest_history_footprint: symbol=%s contract_symbol=%s chart_instance_id=%s timeframe=%s chunk=%s/%s bars=%s",
            payload.instrument.symbol,
            payload.instrument.contract_symbol,
            payload.source.chart_instance_id,
            payload.bar_timeframe.value,
            payload.chunk_index,
            payload.chunk_count,
            len(payload.bars),
        )
        summary = AdapterAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            observed_window_start=payload.observed_window_start,
            observed_window_end=payload.observed_window_end,
            history_footprint_bar_count=len(payload.bars),
            history_footprint_timeframe=payload.bar_timeframe,
            history_footprint_chunk_index=payload.chunk_index,
            history_footprint_chunk_count=payload.chunk_count,
        )
        accepted = self._store(
            ingestion_kind="adapter_history_footprint",
            source_snapshot_id=payload.batch_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        return AdapterAcceptedResponse(
            ingestion_id=accepted.ingestion_id,
            message_id=accepted.message_id,
            message_type=accepted.message_type,
            stored_at=accepted.stored_at,
            summary=accepted.summary,
            durable_outputs=[],
            bridge_errors=[],
        )

    def _store(
        self,
        *,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, object],
        message_id: str,
        message_type: str,
        summary: AdapterAcceptedSummary,
    ) -> AdapterAcceptedResponse:
        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind=ingestion_kind,
            source_snapshot_id=source_snapshot_id,
            instrument_symbol=instrument_symbol,
            observed_payload=observed_payload,
            stored_at=stored_at,
        )
        return AdapterAcceptedResponse(
            ingestion_id=ingestion_id,
            message_id=message_id,
            message_type=message_type,
            stored_at=stored_at,
            summary=summary,
        )

    def _purge_expired_history(
        self,
        *,
        instrument_symbol: str,
        root_symbol: str | None,
        contract_symbol: str | None,
    ) -> None:
        retention_key = (root_symbol or instrument_symbol).upper()
        retention_days = self._HISTORY_RETENTION_DAYS_BY_SYMBOL.get(
            retention_key,
            self._DEFAULT_HISTORY_RETENTION_DAYS,
        )
        cutoff = datetime.now(tz=UTC) - timedelta(days=retention_days)
        self._repository.purge_ingestions(
            ingestion_kinds=["adapter_history_bars", "adapter_history_footprint"],
            instrument_symbol=instrument_symbol,
            cutoff=cutoff,
        )
        self._repository.purge_atas_chart_bars_raw(
            older_than=cutoff,
            contract_symbol=(contract_symbol or instrument_symbol).upper(),
            root_symbol=retention_key,
        )
        LOGGER.info(
            "_purge_expired_history: instrument_symbol=%s root_symbol=%s contract_symbol=%s retention_days=%s cutoff=%s",
            instrument_symbol,
            root_symbol,
            contract_symbol,
            retention_days,
            cutoff.isoformat(),
        )

    def _build_raw_mirror_bars(self, payload: AdapterHistoryBarsPayload) -> list[AtasChartBarRaw]:
        timezone_mode = payload.source.chart_display_timezone_mode or (
            payload.time_context.chart_display_timezone_mode if payload.time_context is not None else None
        )
        timezone_name = payload.source.chart_display_timezone_name or (
            payload.time_context.chart_display_timezone_name if payload.time_context is not None else None
        )
        timezone_offset = payload.source.chart_display_utc_offset_minutes
        if timezone_offset is None and payload.time_context is not None:
            timezone_offset = payload.time_context.chart_display_utc_offset_minutes
        instrument_timezone_value = payload.source.instrument_timezone_value
        if instrument_timezone_value is None and payload.time_context is not None:
            instrument_timezone_value = payload.time_context.instrument_timezone_value
        instrument_timezone_value = None if instrument_timezone_value is None else str(instrument_timezone_value)
        instrument_timezone_source = payload.source.instrument_timezone_source or (
            payload.time_context.instrument_timezone_source if payload.time_context is not None else None
        )
        collector_local_timezone_name = payload.source.collector_local_timezone_name or (
            payload.time_context.collector_local_timezone_name if payload.time_context is not None else None
        )
        collector_local_utc_offset_minutes = payload.source.collector_local_utc_offset_minutes
        if collector_local_utc_offset_minutes is None and payload.time_context is not None:
            collector_local_utc_offset_minutes = payload.time_context.collector_local_utc_offset_minutes
        timestamp_basis = payload.source.timestamp_basis or (
            payload.time_context.timestamp_basis if payload.time_context is not None else None
        )
        timezone_capture_confidence = payload.source.timezone_capture_confidence or (
            payload.time_context.timezone_capture_confidence if payload.time_context is not None else None
        )
        updated_at = datetime.now(tz=UTC)
        timeframe = payload.bar_timeframe

        raw_bars: list[AtasChartBarRaw] = []
        for bar in payload.bars:
            started_at_utc = bar.bar_timestamp_utc or bar.started_at
            raw_bars.append(
                AtasChartBarRaw(
                    chart_instance_id=payload.source.chart_instance_id,
                    root_symbol=payload.instrument.root_symbol,
                    contract_symbol=payload.instrument.contract_symbol or payload.instrument.symbol,
                    symbol=payload.instrument.symbol,
                    venue=payload.instrument.venue,
                    timeframe=timeframe,
                    bar_timestamp_utc=bar.bar_timestamp_utc.astimezone(UTC) if bar.bar_timestamp_utc is not None else None,
                    started_at_utc=started_at_utc.astimezone(UTC),
                    ended_at_utc=bar.ended_at.astimezone(UTC),
                    source_started_at=bar.started_at.astimezone(UTC),
                    original_bar_time_text=bar.original_bar_time_text,
                    timestamp_basis=timestamp_basis,
                    chart_display_timezone_mode=timezone_mode,
                    chart_display_timezone_name=timezone_name,
                    chart_display_utc_offset_minutes=timezone_offset,
                    instrument_timezone_value=instrument_timezone_value,
                    instrument_timezone_source=instrument_timezone_source,
                    collector_local_timezone_name=collector_local_timezone_name,
                    collector_local_utc_offset_minutes=collector_local_utc_offset_minutes,
                    timezone_capture_confidence=timezone_capture_confidence,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    bid_volume=bar.bid_volume,
                    ask_volume=bar.ask_volume,
                    delta=bar.delta,
                    trade_count=getattr(bar, "trade_count", None),
                    updated_at=updated_at,
                )
            )
        return raw_bars
