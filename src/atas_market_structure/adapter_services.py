from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from atas_market_structure.adapter_bridge import AdapterPayloadBridge
from atas_market_structure.models import (
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
        self._bridge = bridge or AdapterPayloadBridge(regime_monitor=RegimeMonitor())

    def ingest_continuous_state(self, payload: AdapterContinuousStatePayload) -> AdapterAcceptedResponse:
        self._bridge.regime_monitor.ingest_continuous_state(payload)
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
        self._purge_expired_history(payload.instrument.symbol)
        self._bridge.regime_monitor.ingest_history_bars(payload)
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
        self._purge_expired_history(payload.instrument.symbol)
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

    def _purge_expired_history(self, instrument_symbol: str) -> None:
        retention_days = self._HISTORY_RETENTION_DAYS_BY_SYMBOL.get(
            instrument_symbol.upper(),
            self._DEFAULT_HISTORY_RETENTION_DAYS,
        )
        cutoff = datetime.now(tz=UTC) - timedelta(days=retention_days)
        self._repository.purge_ingestions(
            ingestion_kinds=["adapter_history_bars", "adapter_history_footprint"],
            instrument_symbol=instrument_symbol,
            cutoff=cutoff,
        )
