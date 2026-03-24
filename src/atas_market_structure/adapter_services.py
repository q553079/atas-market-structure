from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import re
from threading import Lock
from typing import Any
from uuid import uuid4

from atas_market_structure.adapter_bridge import AdapterPayloadBridge
from atas_market_structure.chart_identity import canonical_chart_instance_id, derive_root_symbol, normalize_symbol
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
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.services import IngestionOrchestrator

LOGGER = logging.getLogger(__name__)
AdapterPayloadType = (
    AdapterContinuousStatePayload
    | AdapterHistoryBarsPayload
    | AdapterHistoryFootprintPayload
    | AdapterTriggerBurstPayload
)

_LOCAL_TIMEZONE_FALLBACK_BASES = frozenset(
    {
        "collector_local_timezone_fallback",
        "chart_display_timezone_derived_from_local",
        "collector_local_time",
    }
)
_LOW_CONFIDENCE_VALUES = frozenset({"", "low", "medium", "unknown"})


class AdapterIngestionService:
    """Validates and stores low-latency adapter messages without forcing full analysis."""

    _UNRESOLVED_TICK_SIZE_LOG_INTERVAL = timedelta(minutes=1)
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
        recognition_service: DeterministicRecognitionService | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator or IngestionOrchestrator(repository=repository)
        self._bridge = bridge or AdapterPayloadBridge(regime_monitor=RegimeMonitor(repository=repository))
        self._recognition_service = recognition_service or DeterministicRecognitionService(repository=repository)
        self._unresolved_tick_size_logged_at: dict[str, datetime] = {}
        self._unresolved_tick_size_lock = Lock()

    def normalize_payload(self, payload: AdapterPayloadType) -> AdapterPayloadType:
        normalized = self._normalize_payload_instrument_identity(payload)
        normalized = self._normalize_payload_chart_identity(normalized)
        if isinstance(normalized, AdapterHistoryBarsPayload):
            normalized = self._repair_history_payload_utc_fallback(normalized)
            return self._drop_forming_history_bars(normalized)
        if isinstance(normalized, AdapterHistoryFootprintPayload):
            normalized = self._repair_history_footprint_payload_utc_fallback(normalized)
            return self._drop_forming_history_footprint_bars(normalized)
        return normalized

    def ingest_continuous_state(self, payload: AdapterContinuousStatePayload) -> AdapterAcceptedResponse:
        payload = self.normalize_payload(payload)
        self._warn_on_unresolved_tick_size("ingest_continuous_state", payload)
        summary = self.build_summary(payload)
        accepted, is_duplicate = self._store(
            ingestion_kind="adapter_continuous_state",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        if is_duplicate:
            LOGGER.info(
                "ingest_continuous_state: duplicate source_snapshot_id=%s symbol=%s ignored.",
                payload.message_id,
                payload.instrument.symbol,
            )
            return accepted
        return self.ingest_continuous_state_after_store(payload, accepted=accepted)

    def ingest_continuous_state_after_store(
        self,
        payload: AdapterContinuousStatePayload,
        *,
        accepted: AdapterAcceptedResponse,
    ) -> AdapterAcceptedResponse:
        self._bridge.regime_monitor.ingest_continuous_state(payload)
        LOGGER.info(
            "ingest_continuous_state: symbol=%s root_symbol=%s chart_instance_id=%s",
            payload.instrument.symbol,
            payload.instrument.root_symbol,
            payload.source.chart_instance_id,
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
        payload = self.normalize_payload(payload)
        self._warn_on_unresolved_tick_size("ingest_trigger_burst", payload)
        summary = self.build_summary(payload)
        accepted, is_duplicate = self._store(
            ingestion_kind="adapter_trigger_burst",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        if is_duplicate:
            LOGGER.info(
                "ingest_trigger_burst: duplicate source_snapshot_id=%s symbol=%s ignored.",
                payload.message_id,
                payload.instrument.symbol,
            )
            return accepted
        return self.ingest_trigger_burst_after_store(payload, accepted=accepted)

    def ingest_trigger_burst_after_store(
        self,
        payload: AdapterTriggerBurstPayload,
        *,
        accepted: AdapterAcceptedResponse,
    ) -> AdapterAcceptedResponse:
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
        payload = self.normalize_payload(payload)
        summary = self.build_summary(payload)
        accepted, is_duplicate = self._store(
            ingestion_kind="adapter_history_bars",
            source_snapshot_id=payload.message_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        if is_duplicate:
            LOGGER.info(
                "ingest_history_bars: duplicate source_snapshot_id=%s symbol=%s chart_instance_id=%s ignored.",
                payload.message_id,
                payload.instrument.symbol,
                payload.source.chart_instance_id,
            )
            return accepted
        return self.ingest_history_bars_after_store(payload, accepted=accepted)

    def ingest_history_bars_after_store(
        self,
        payload: AdapterHistoryBarsPayload,
        *,
        accepted: AdapterAcceptedResponse,
    ) -> AdapterAcceptedResponse:
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
        try:
            self._recognition_service.run_for_instrument(
                analysis_symbol,
                triggered_by="adapter_history_bars",
            )
        except Exception:  # pragma: no cover - defensive only
            LOGGER.exception("deterministic recognition failed after adapter_history_bars for %s", analysis_symbol)
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
        payload = self.normalize_payload(payload)
        summary = self.build_summary(payload)
        accepted, is_duplicate = self._store(
            ingestion_kind="adapter_history_footprint",
            source_snapshot_id=payload.batch_id,
            instrument_symbol=payload.instrument.symbol,
            observed_payload=payload.model_dump(mode="json"),
            message_id=payload.message_id,
            message_type=payload.message_type,
            summary=summary,
        )
        if is_duplicate:
            LOGGER.info(
                "ingest_history_footprint: duplicate source_snapshot_id=%s symbol=%s chart_instance_id=%s ignored.",
                payload.batch_id,
                payload.instrument.symbol,
                payload.source.chart_instance_id,
            )
            return accepted
        return self.ingest_history_footprint_after_store(payload, accepted=accepted)

    def ingest_history_footprint_after_store(
        self,
        payload: AdapterHistoryFootprintPayload,
        *,
        accepted: AdapterAcceptedResponse,
    ) -> AdapterAcceptedResponse:
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
    ) -> tuple[AdapterAcceptedResponse, bool]:
        existing = self._find_existing_ingestion(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
        )
        if existing is not None:
            return (
                AdapterAcceptedResponse(
                    ingestion_id=existing.ingestion_id,
                    message_id=message_id,
                    message_type=message_type,
                    stored_at=existing.stored_at,
                    summary=summary,
                ),
                True,
            )

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
        ), False

    def _find_existing_ingestion(
        self,
        *,
        ingestion_kind: str,
        instrument_symbol: str,
        source_snapshot_id: str,
    ) -> Any | None:
        existing = self._repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            limit=1,
        )
        return existing[0] if existing else None

    def build_summary(self, payload: AdapterPayloadType) -> AdapterAcceptedSummary:
        if isinstance(payload, AdapterContinuousStatePayload):
            return AdapterAcceptedSummary(
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
        if isinstance(payload, AdapterTriggerBurstPayload):
            return AdapterAcceptedSummary(
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
        if isinstance(payload, AdapterHistoryBarsPayload):
            return AdapterAcceptedSummary(
                instrument_symbol=payload.instrument.symbol,
                observed_window_start=payload.observed_window_start,
                observed_window_end=payload.observed_window_end,
                history_bar_count=len(payload.bars),
                history_bar_timeframe=payload.bar_timeframe,
            )
        return AdapterAcceptedSummary(
            instrument_symbol=payload.instrument.symbol,
            observed_window_start=payload.observed_window_start,
            observed_window_end=payload.observed_window_end,
            history_footprint_bar_count=len(payload.bars),
            history_footprint_timeframe=payload.bar_timeframe,
            history_footprint_chunk_index=payload.chunk_index,
            history_footprint_chunk_count=payload.chunk_count,
        )

    def describe_payload(self, payload: AdapterPayloadType) -> dict[str, Any]:
        payload = self.normalize_payload(payload)
        if isinstance(payload, AdapterContinuousStatePayload):
            return {
                "ingestion_kind": "adapter_continuous_state",
                "source_snapshot_id": payload.message_id,
                "message_id": payload.message_id,
                "message_type": payload.message_type,
                "summary": self.build_summary(payload),
            }
        if isinstance(payload, AdapterTriggerBurstPayload):
            return {
                "ingestion_kind": "adapter_trigger_burst",
                "source_snapshot_id": payload.message_id,
                "message_id": payload.message_id,
                "message_type": payload.message_type,
                "summary": self.build_summary(payload),
            }
        if isinstance(payload, AdapterHistoryBarsPayload):
            return {
                "ingestion_kind": "adapter_history_bars",
                "source_snapshot_id": payload.message_id,
                "message_id": payload.message_id,
                "message_type": payload.message_type,
                "summary": self.build_summary(payload),
            }
        return {
            "ingestion_kind": "adapter_history_footprint",
            "source_snapshot_id": payload.batch_id,
            "message_id": payload.message_id,
            "message_type": payload.message_type,
            "summary": self.build_summary(payload),
        }

    def ingest_adapter_payload_after_store(
        self,
        payload: AdapterPayloadType,
        *,
        accepted: AdapterAcceptedResponse,
    ) -> AdapterAcceptedResponse:
        payload = self.normalize_payload(payload)
        if isinstance(payload, AdapterContinuousStatePayload):
            return self.ingest_continuous_state_after_store(payload, accepted=accepted)
        if isinstance(payload, AdapterTriggerBurstPayload):
            return self.ingest_trigger_burst_after_store(payload, accepted=accepted)
        if isinstance(payload, AdapterHistoryBarsPayload):
            return self.ingest_history_bars_after_store(payload, accepted=accepted)
        return self.ingest_history_footprint_after_store(payload, accepted=accepted)

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

    def _normalize_payload_chart_identity(self, payload: AdapterPayloadType) -> AdapterPayloadType:
        normalized_chart_instance_id = canonical_chart_instance_id(
            payload.source.chart_instance_id,
            instrument_symbol=payload.instrument.symbol,
            contract_symbol=payload.instrument.contract_symbol or payload.instrument.symbol,
            display_timeframe=getattr(payload, "bar_timeframe", None) or payload.display_timeframe,
            venue=payload.instrument.venue,
            currency=payload.instrument.currency,
        )
        if normalized_chart_instance_id == payload.source.chart_instance_id:
            return payload
        LOGGER.info(
            "normalize_payload_chart_identity: message_id=%s chart_instance_id=%s -> %s symbol=%s contract_symbol=%s timeframe=%s",
            payload.message_id,
            payload.source.chart_instance_id,
            normalized_chart_instance_id,
            payload.instrument.symbol,
            payload.instrument.contract_symbol,
            getattr(getattr(payload, "bar_timeframe", None), "value", getattr(payload, "bar_timeframe", None))
            or payload.display_timeframe,
        )
        return payload.model_copy(
            update={
                "source": payload.source.model_copy(
                    update={"chart_instance_id": normalized_chart_instance_id}
                )
            }
        )

    def _normalize_payload_instrument_identity(self, payload: AdapterPayloadType) -> AdapterPayloadType:
        instrument = payload.instrument
        normalized_symbol = normalize_symbol(instrument.symbol) or instrument.symbol
        normalized_contract_symbol = normalize_symbol(instrument.contract_symbol) or normalized_symbol
        normalized_root_symbol = normalize_symbol(instrument.root_symbol)
        derived_root_symbol = (
            derive_root_symbol(normalized_contract_symbol)
            or derive_root_symbol(normalized_symbol)
        )

        next_root_symbol = normalized_root_symbol
        if next_root_symbol is None:
            next_root_symbol = derived_root_symbol
        elif (
            derived_root_symbol is not None
            and (
                len(next_root_symbol) < 2
                or next_root_symbol == normalized_contract_symbol
            )
            and derived_root_symbol != next_root_symbol
        ):
            next_root_symbol = derived_root_symbol

        if (
            normalized_symbol == instrument.symbol
            and normalized_contract_symbol == (instrument.contract_symbol or normalized_symbol)
            and next_root_symbol == instrument.root_symbol
        ):
            return payload

        LOGGER.info(
            "normalize_payload_instrument_identity: message_id=%s symbol=%s->%s contract_symbol=%s->%s root_symbol=%s->%s",
            payload.message_id,
            instrument.symbol,
            normalized_symbol,
            instrument.contract_symbol,
            normalized_contract_symbol,
            instrument.root_symbol,
            next_root_symbol,
        )
        return payload.model_copy(
            update={
                "instrument": instrument.model_copy(
                    update={
                        "symbol": normalized_symbol,
                        "contract_symbol": normalized_contract_symbol,
                        "root_symbol": next_root_symbol,
                    }
                )
            }
        )

    def _drop_forming_history_bars(self, payload: AdapterHistoryBarsPayload) -> AdapterHistoryBarsPayload:
        if not payload.bars:
            return payload
        emitted_at_utc = payload.emitted_at.astimezone(UTC)
        completed_bars = [
            bar for bar in payload.bars
            if bar.ended_at.astimezone(UTC) < emitted_at_utc
        ]
        dropped_count = len(payload.bars) - len(completed_bars)
        if dropped_count <= 0:
            return payload
        LOGGER.warning(
            "drop_forming_history_bars: message_id=%s dropped=%s emitted_at=%s latest_source_bar=%s chart_instance_id=%s",
            payload.message_id,
            dropped_count,
            emitted_at_utc.isoformat(),
            payload.bars[-1].started_at.astimezone(UTC).isoformat(),
            payload.source.chart_instance_id,
        )
        if completed_bars:
            return payload.model_copy(
                update={
                    "bars": completed_bars,
                    "observed_window_start": completed_bars[0].started_at,
                    "observed_window_end": completed_bars[-1].ended_at,
                }
            )
        return payload.model_copy(
            update={
                "bars": [],
                "observed_window_start": emitted_at_utc,
                "observed_window_end": emitted_at_utc,
            }
        )

    def _drop_forming_history_footprint_bars(
        self,
        payload: AdapterHistoryFootprintPayload,
    ) -> AdapterHistoryFootprintPayload:
        if not payload.bars:
            return payload
        emitted_at_utc = payload.emitted_at.astimezone(UTC)
        completed_bars = [
            bar for bar in payload.bars
            if bar.ended_at.astimezone(UTC) < emitted_at_utc
        ]
        dropped_count = len(payload.bars) - len(completed_bars)
        if dropped_count <= 0:
            return payload
        LOGGER.warning(
            "drop_forming_history_footprint_bars: message_id=%s dropped=%s emitted_at=%s latest_source_bar=%s chart_instance_id=%s",
            payload.message_id,
            dropped_count,
            emitted_at_utc.isoformat(),
            payload.bars[-1].started_at.astimezone(UTC).isoformat(),
            payload.source.chart_instance_id,
        )
        if completed_bars:
            return payload.model_copy(
                update={
                    "bars": completed_bars,
                    "observed_window_start": completed_bars[0].started_at,
                    "observed_window_end": completed_bars[-1].ended_at,
                }
            )
        return payload.model_copy(
            update={
                "bars": [],
                "observed_window_start": emitted_at_utc,
                "observed_window_end": emitted_at_utc,
            }
        )

    def _repair_history_payload_utc_fallback(
        self,
        payload: AdapterHistoryBarsPayload,
    ) -> AdapterHistoryBarsPayload:
        corrected_bars, correction_basis = self._repair_history_bar_collection(
            message_id=payload.message_id,
            bars=payload.bars,
            source=payload.source,
            time_context=payload.time_context,
        )
        if correction_basis is None:
            return payload
        update: dict[str, Any] = {
            "bars": corrected_bars,
            "observed_window_start": corrected_bars[0].started_at,
            "observed_window_end": corrected_bars[-1].ended_at,
            "source": payload.source.model_copy(update=self._build_guardrail_source_update(correction_basis)),
        }
        if payload.time_context is not None:
            update["time_context"] = payload.time_context.model_copy(
                update=self._build_guardrail_time_context_update(correction_basis)
            )
        return payload.model_copy(update=update)

    def _repair_history_footprint_payload_utc_fallback(
        self,
        payload: AdapterHistoryFootprintPayload,
    ) -> AdapterHistoryFootprintPayload:
        corrected_bars, correction_basis = self._repair_history_bar_collection(
            message_id=payload.message_id,
            bars=payload.bars,
            source=payload.source,
            time_context=payload.time_context,
        )
        if correction_basis is None:
            return payload
        update: dict[str, Any] = {
            "bars": corrected_bars,
            "observed_window_start": corrected_bars[0].started_at,
            "observed_window_end": corrected_bars[-1].ended_at,
            "source": payload.source.model_copy(update=self._build_guardrail_source_update(correction_basis)),
        }
        if payload.time_context is not None:
            update["time_context"] = payload.time_context.model_copy(
                update=self._build_guardrail_time_context_update(correction_basis)
            )
        return payload.model_copy(update=update)

    def _repair_history_bar_collection(
        self,
        *,
        message_id: str,
        bars: list[Any],
        source: Any,
        time_context: Any,
    ) -> tuple[list[Any], str | None]:
        if not bars:
            return list(bars), None

        timestamp_basis = self._coalesce_time_context_value(source, time_context, "timestamp_basis")
        timezone_confidence = self._coalesce_time_context_value(source, time_context, "timezone_capture_confidence")
        timezone_mode = self._coalesce_time_context_value(source, time_context, "chart_display_timezone_mode")
        local_offset_minutes = self._coalesce_time_context_value(source, time_context, "collector_local_utc_offset_minutes")
        if not self._should_apply_history_utc_guardrail(
            timestamp_basis=timestamp_basis,
            timezone_confidence=timezone_confidence,
            timezone_mode=timezone_mode,
            local_offset_minutes=local_offset_minutes,
        ):
            return list(bars), None

        expected_delta = timedelta(minutes=int(local_offset_minutes))
        corrected_bars: list[Any] = []
        parseable_count = 0
        corrected_count = 0

        for bar in bars:
            corrected_started_at = self._parse_original_bar_time_text_as_utc(bar.original_bar_time_text)
            if corrected_started_at is None:
                corrected_bars.append(bar)
                continue

            parseable_count += 1
            current_started_at = (bar.bar_timestamp_utc or bar.started_at).astimezone(UTC)
            delta = corrected_started_at - current_started_at
            if abs((delta - expected_delta).total_seconds()) > 2:
                corrected_bars.append(bar)
                continue

            corrected_count += 1
            duration = bar.ended_at.astimezone(UTC) - bar.started_at.astimezone(UTC)
            corrected_bars.append(
                bar.model_copy(
                    update={
                        "started_at": corrected_started_at,
                        "ended_at": corrected_started_at + duration,
                        "bar_timestamp_utc": corrected_started_at,
                    }
                )
            )

        if corrected_count <= 0:
            return list(bars), None
        if parseable_count != corrected_count:
            LOGGER.warning(
                "history_timezone_guardrail: skipped partial correction message_id=%s parseable=%s corrected=%s basis=%s mode=%s local_offset_minutes=%s",
                message_id,
                parseable_count,
                corrected_count,
                timestamp_basis,
                timezone_mode,
                local_offset_minutes,
            )
            return list(bars), None

        correction_basis = "python_guardrail_forced_utc_from_original_bar_time_text"
        LOGGER.warning(
            "history_timezone_guardrail: corrected message_id=%s bars=%s basis=%s mode=%s confidence=%s local_offset_minutes=%s",
            message_id,
            corrected_count,
            timestamp_basis,
            timezone_mode,
            timezone_confidence,
            local_offset_minutes,
        )
        return corrected_bars, correction_basis

    @staticmethod
    def _build_guardrail_source_update(correction_basis: str) -> dict[str, Any]:
        return {
            "chart_display_timezone_mode": "utc",
            "chart_display_timezone_name": "UTC",
            "chart_display_utc_offset_minutes": 0,
            "timestamp_basis": correction_basis,
            "timezone_capture_confidence": "guardrail",
        }

    @staticmethod
    def _build_guardrail_time_context_update(correction_basis: str) -> dict[str, Any]:
        return {
            "chart_display_timezone_mode": "utc",
            "chart_display_timezone_source": "python_guardrail",
            "chart_display_timezone_name": "UTC",
            "chart_display_utc_offset_minutes": 0,
            "timestamp_basis": correction_basis,
            "started_at_output_timezone": "UTC",
            "started_at_time_source": correction_basis,
            "timezone_capture_confidence": "guardrail",
        }

    @staticmethod
    def _coalesce_time_context_value(source: Any, time_context: Any, field_name: str) -> Any:
        source_value = getattr(source, field_name, None)
        if source_value is not None:
            return source_value
        if time_context is None:
            return None
        return getattr(time_context, field_name, None)

    @staticmethod
    def _should_apply_history_utc_guardrail(
        *,
        timestamp_basis: Any,
        timezone_confidence: Any,
        timezone_mode: Any,
        local_offset_minutes: Any,
    ) -> bool:
        if local_offset_minutes in (None, 0):
            return False
        normalized_basis = str(timestamp_basis or "").strip().lower()
        normalized_confidence = str(timezone_confidence or "").strip().lower()
        normalized_mode = str(timezone_mode or "").strip().lower()
        if normalized_basis in _LOCAL_TIMEZONE_FALLBACK_BASES:
            return True
        return normalized_mode == "local" and normalized_confidence in _LOW_CONFIDENCE_VALUES

    @staticmethod
    def _parse_original_bar_time_text_as_utc(value: str | None) -> datetime | None:
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            return None

        candidate = re.sub(r"\.(\d{6})\d+", r".\1", candidate)
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        elif candidate.endswith(" UTC") or candidate.endswith(" GMT"):
            candidate = candidate[:-4] + "+00:00"
        elif re.search(r"\s[A-Za-z]{2,5}$", candidate):
            return None

        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

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

    def _warn_on_unresolved_tick_size(
        self,
        operation: str,
        payload: AdapterContinuousStatePayload | AdapterTriggerBurstPayload,
    ) -> None:
        if payload.instrument.tick_size > 0:
            return

        warning_key = "|".join(
            (
                operation,
                payload.instrument.symbol or "",
                payload.instrument.root_symbol or "",
                payload.instrument.contract_symbol or "",
                payload.source.chart_instance_id or "",
            ),
        )
        now = datetime.now(tz=UTC)
        should_log = False
        with self._unresolved_tick_size_lock:
            last_logged_at = self._unresolved_tick_size_logged_at.get(warning_key)
            if last_logged_at is None or now - last_logged_at >= self._UNRESOLVED_TICK_SIZE_LOG_INTERVAL:
                self._unresolved_tick_size_logged_at[warning_key] = now
                should_log = True

        if should_log:
            LOGGER.warning(
                "%s: unresolved tick_size for symbol=%s root_symbol=%s contract_symbol=%s chart_instance_id=%s",
                operation,
                payload.instrument.symbol,
                payload.instrument.root_symbol,
                payload.instrument.contract_symbol,
                payload.source.chart_instance_id,
            )
