from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.depth_services import DepthMonitoringService
from atas_market_structure.models import (
    AdapterAcceptedResponse,
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    BeliefDataStatus,
    DataQualityResponse,
    DataQualitySourceStatus,
    DepthCoverageState,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    DegradedMode,
    EventSnapshotPayload,
    IngestionErrorResponse,
    IngestionHealthResponse,
    IngestionMetricsSnapshot,
    IngestionRunLogEntry,
    MarketStructurePayload,
    ProcessContextPayload,
    ReliableIngestionResponse,
    ServiceHealthStatus,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.services import IngestionOrchestrator


AdapterPayloadType = (
    AdapterContinuousStatePayload
    | AdapterHistoryBarsPayload
    | AdapterHistoryFootprintPayload
    | AdapterTriggerBurstPayload
)

RELIABILITY_SCHEMA_VERSION = "1.0.0"
DEFAULT_PROFILE_VERSION = "profile_unassigned"
DEFAULT_ENGINE_VERSION = "engine_unassigned"
MACRO_STALE_AFTER = timedelta(minutes=20)
DEPTH_STALE_AFTER = timedelta(minutes=2)
RUN_LOG_WINDOW = timedelta(hours=1)
PAUSE_SENTINEL = Path("runtime") / "ingestion.paused"

DEGRADED_REASON_MAP = {
    DegradedMode.NO_DEPTH: "degraded_no_depth",
    DegradedMode.NO_DOM: "degraded_no_dom",
    DegradedMode.NO_AI: "degraded_no_ai",
    DegradedMode.STALE_MACRO: "degraded_stale_macro",
    DegradedMode.REPLAY_REBUILD: "replay_rebuild_mode",
}


@dataclass(frozen=True)
class ReliabilityResult:
    status_code: int
    body: ReliableIngestionResponse | IngestionErrorResponse | IngestionHealthResponse | DataQualityResponse


@dataclass(frozen=True)
class _PayloadSpec:
    endpoint: str
    ingestion_kind: str


class IngestionReliabilityService:
    """Implements store-first ingestion, dead letters, idempotency, and health reporting."""

    def __init__(
        self,
        *,
        repository: AnalysisRepository,
        orchestrator: IngestionOrchestrator,
        depth_monitoring_service: DepthMonitoringService,
        adapter_ingestion_service: AdapterIngestionService,
        ai_available: bool,
        recognition_service: DeterministicRecognitionService | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator
        self._depth_monitoring_service = depth_monitoring_service
        self._adapter_ingestion_service = adapter_ingestion_service
        self._ai_available = ai_available
        self._recognition_service = recognition_service or DeterministicRecognitionService(
            repository=repository,
            ai_available=ai_available,
        )

    def ingest_market_structure(self, body: bytes) -> ReliabilityResult:
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(endpoint="/api/v1/ingest/market-structure", ingestion_kind="market_structure"),
            validator=MarketStructurePayload.model_validate,
            request_id_extractor=lambda payload: payload.snapshot_id,
            instrument_extractor=lambda payload: payload.instrument.symbol,
            source_id_extractor=lambda payload: payload.snapshot_id,
            schema_version_extractor=lambda payload: payload.schema_version,
            after_store=lambda payload, ingestion_id, stored_at: self._orchestrator.ingest_market_structure_after_store(
                payload,
                ingestion_id=ingestion_id,
                stored_at=stored_at,
            ),
        )

    def ingest_event_snapshot(self, body: bytes) -> ReliabilityResult:
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(endpoint="/api/v1/ingest/event-snapshot", ingestion_kind="event_snapshot"),
            validator=EventSnapshotPayload.model_validate,
            request_id_extractor=lambda payload: payload.event_snapshot_id,
            instrument_extractor=lambda payload: payload.instrument.symbol,
            source_id_extractor=lambda payload: payload.event_snapshot_id,
            schema_version_extractor=lambda payload: payload.schema_version,
            after_store=lambda payload, ingestion_id, stored_at: self._orchestrator.ingest_event_snapshot_after_store(
                payload,
                ingestion_id=ingestion_id,
                stored_at=stored_at,
            ),
        )

    def ingest_process_context(self, body: bytes) -> ReliabilityResult:
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(endpoint="/api/v1/ingest/process-context", ingestion_kind="process_context"),
            validator=ProcessContextPayload.model_validate,
            request_id_extractor=lambda payload: payload.process_context_id,
            instrument_extractor=lambda payload: payload.instrument.symbol,
            source_id_extractor=lambda payload: payload.process_context_id,
            schema_version_extractor=lambda payload: payload.schema_version,
            after_store=self._process_context_after_store,
        )

    def ingest_depth_snapshot(self, body: bytes) -> ReliabilityResult:
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(endpoint="/api/v1/ingest/depth-snapshot", ingestion_kind="depth_snapshot"),
            validator=DepthSnapshotPayload.model_validate,
            request_id_extractor=lambda payload: payload.depth_snapshot_id,
            instrument_extractor=lambda payload: payload.instrument.symbol,
            source_id_extractor=lambda payload: payload.depth_snapshot_id,
            schema_version_extractor=lambda payload: payload.schema_version,
            after_store=self._depth_after_store,
        )

    def ingest_adapter_payload(self, body: bytes) -> ReliabilityResult:
        spec = _PayloadSpec(endpoint="/api/v1/ingest/adapter-payload", ingestion_kind="adapter_payload")
        started_at = datetime.now(tz=UTC)
        raw_payload_text = self._decode_body(body)
        raw_payload_hash = self._hash_bytes(body)
        parsed, parse_error = self._parse_json_body(raw_payload_text)
        if parse_error is not None:
            return self._invalid_json_result(
                spec=spec,
                started_at=started_at,
                raw_payload_text=raw_payload_text,
                payload_hash=raw_payload_hash,
                detail={"message": parse_error.msg, "position": parse_error.pos},
            )

        try:
            payload = self._validate_adapter_payload(parsed)
        except ValidationError as exc:
            payload_hash = self._hash_json(parsed)
            dedup_key = self._extract_request_id(parsed) or payload_hash
            return self._validation_error_result(
                spec=spec,
                started_at=started_at,
                raw_payload_text=raw_payload_text,
                payload_hash=payload_hash,
                dedup_key=dedup_key,
                request_id=self._extract_request_id(parsed),
                instrument_symbol=self._extract_instrument_symbol(parsed),
                source_snapshot_id=self._extract_request_id(parsed),
                schema_version=self._extract_schema_version(parsed),
                detail=json.loads(exc.json()),
            )
        except ValueError as exc:
            payload_hash = self._hash_json(parsed)
            dedup_key = self._extract_request_id(parsed) or payload_hash
            return self._validation_error_result(
                spec=spec,
                started_at=started_at,
                raw_payload_text=raw_payload_text,
                payload_hash=payload_hash,
                dedup_key=dedup_key,
                request_id=self._extract_request_id(parsed),
                instrument_symbol=self._extract_instrument_symbol(parsed),
                source_snapshot_id=self._extract_request_id(parsed),
                schema_version=self._extract_schema_version(parsed),
                detail={"message": str(exc)},
            )

        metadata = self._adapter_ingestion_service.describe_payload(payload)
        return self._process_validated_payload(
            payload=payload,
            spec=_PayloadSpec(endpoint=spec.endpoint, ingestion_kind=metadata["ingestion_kind"]),
            request_id=metadata["message_id"],
            instrument_symbol=payload.instrument.symbol,
            source_snapshot_id=metadata["source_snapshot_id"],
            payload_hash=self._hash_json(payload.model_dump(mode="json")),
            raw_payload_text=raw_payload_text,
            response_schema_version=RELIABILITY_SCHEMA_VERSION,
            started_at=started_at,
            after_store=lambda item, ingestion_id, stored_at: self._adapter_ingestion_service.ingest_adapter_payload_after_store(
                item,
                accepted=AdapterAcceptedResponse(
                    ingestion_id=ingestion_id,
                    message_id=metadata["message_id"],
                    message_type=metadata["message_type"],
                    stored_at=stored_at,
                    summary=metadata["summary"],
                    durable_outputs=[],
                    bridge_errors=[],
                ),
            ),
        )

    def get_ingestion_health(self, *, instrument_symbol: str | None = None) -> ReliabilityResult:
        now = datetime.now(tz=UTC)
        data_quality = self._build_data_quality(instrument_symbol=instrument_symbol)
        recent_logs = self._repository.list_ingestion_run_logs(
            instrument_symbol=instrument_symbol,
            limit=20,
            completed_at_after=now - RUN_LOG_WINDOW,
        )
        metrics = IngestionMetricsSnapshot(
            total_count=len(recent_logs),
            accepted_count=sum(1 for item in recent_logs if item.outcome == "accepted"),
            duplicate_count=sum(1 for item in recent_logs if item.outcome == "duplicate"),
            dead_letter_count=sum(1 for item in recent_logs if item.outcome == "dead_lettered"),
            downstream_failure_count=sum(1 for item in recent_logs if item.outcome == "downstream_failed"),
        )
        dead_letters = self._repository.list_dead_letters(
            instrument_symbol=instrument_symbol,
            limit=1,
            stored_at_after=now - RUN_LOG_WINDOW,
        )
        body = IngestionHealthResponse(
            status=data_quality.status,
            degraded_reasons=data_quality.degraded_reasons,
            profile_version=data_quality.profile_version,
            engine_version=data_quality.engine_version,
            schema_version=RELIABILITY_SCHEMA_VERSION,
            data_status=data_quality.data_status,
            freshness=data_quality.freshness,
            completeness=data_quality.completeness,
            last_success_at=self._find_last_success_at(instrument_symbol=instrument_symbol),
            last_dead_letter_at=dead_letters[0].stored_at if dead_letters else None,
            last_run_at=recent_logs[0].completed_at if recent_logs else None,
            metrics=metrics,
            recent_runs=[
                IngestionRunLogEntry(
                    run_id=item.run_id,
                    endpoint=item.endpoint,
                    ingestion_kind=item.ingestion_kind,
                    instrument_symbol=item.instrument_symbol,
                    request_id=item.request_id,
                    dedup_key=item.dedup_key,
                    payload_hash=item.payload_hash,
                    outcome=item.outcome,
                    http_status=item.http_status,
                    ingestion_id=item.ingestion_id,
                    dead_letter_id=item.dead_letter_id,
                    detail=item.detail,
                    started_at=item.started_at,
                    completed_at=item.completed_at,
                )
                for item in recent_logs
            ],
        )
        return ReliabilityResult(status_code=200, body=body)

    def get_data_quality(self, *, instrument_symbol: str | None = None) -> ReliabilityResult:
        return ReliabilityResult(status_code=200, body=self._build_data_quality(instrument_symbol=instrument_symbol))

    def _process_context_after_store(self, payload: ProcessContextPayload, ingestion_id: str, stored_at: datetime) -> dict[str, Any]:
        recognition = self._recognition_service.try_run_for_instrument(
            payload.instrument.symbol,
            triggered_by="process_context",
        )
        return {
            "process_context_id": payload.process_context_id,
            "stored_only": True,
            "ingestion_id": ingestion_id,
            "stored_at": stored_at,
            "recognition": self._recognition_summary(recognition),
        }

    def _depth_after_store(self, payload: DepthSnapshotPayload, ingestion_id: str, stored_at: datetime) -> dict[str, Any]:
        depth_result = self._depth_monitoring_service.ingest_depth_snapshot_after_store(
            payload,
            ingestion_id=ingestion_id,
            stored_at=stored_at,
        )
        recognition = self._recognition_service.try_run_for_instrument(
            payload.instrument.symbol,
            triggered_by="depth_snapshot",
        )
        return {
            **depth_result.model_dump(mode="json"),
            "recognition": self._recognition_summary(recognition),
        }

    def _ingest_payload(
        self,
        *,
        body: bytes,
        spec: _PayloadSpec,
        validator,
        request_id_extractor,
        instrument_extractor,
        source_id_extractor,
        schema_version_extractor,
        after_store,
    ) -> ReliabilityResult:
        started_at = datetime.now(tz=UTC)
        raw_payload_text = self._decode_body(body)
        raw_payload_hash = self._hash_bytes(body)
        parsed, parse_error = self._parse_json_body(raw_payload_text)
        if parse_error is not None:
            return self._invalid_json_result(
                spec=spec,
                started_at=started_at,
                raw_payload_text=raw_payload_text,
                payload_hash=raw_payload_hash,
                detail={"message": parse_error.msg, "position": parse_error.pos},
            )

        try:
            payload = validator(parsed)
        except ValidationError as exc:
            payload_hash = self._hash_json(parsed)
            request_id = self._extract_request_id(parsed)
            dedup_key = request_id or payload_hash
            return self._validation_error_result(
                spec=spec,
                started_at=started_at,
                raw_payload_text=raw_payload_text,
                payload_hash=payload_hash,
                dedup_key=dedup_key,
                request_id=request_id,
                instrument_symbol=self._extract_instrument_symbol(parsed),
                source_snapshot_id=request_id,
                schema_version=self._extract_schema_version(parsed),
                detail=json.loads(exc.json()),
            )

        request_id = request_id_extractor(payload)
        return self._process_validated_payload(
            payload=payload,
            spec=spec,
            request_id=request_id,
            instrument_symbol=instrument_extractor(payload),
            source_snapshot_id=source_id_extractor(payload),
            payload_hash=self._hash_json(payload.model_dump(mode="json")),
            raw_payload_text=raw_payload_text,
            response_schema_version=schema_version_extractor(payload) or RELIABILITY_SCHEMA_VERSION,
            started_at=started_at,
            after_store=after_store,
        )

    def _process_validated_payload(
        self,
        *,
        payload,
        spec: _PayloadSpec,
        request_id: str | None,
        instrument_symbol: str | None,
        source_snapshot_id: str | None,
        payload_hash: str,
        raw_payload_text: str,
        response_schema_version: str,
        started_at: datetime,
        after_store,
    ) -> ReliabilityResult:
        dedup_key = request_id or payload_hash
        versions = self._resolve_versions(instrument_symbol=instrument_symbol)
        existing = self._repository.get_ingestion_idempotency_key(endpoint=spec.endpoint, dedup_key=dedup_key)
        if existing is not None:
            if existing.payload_hash != payload_hash:
                return self._idempotency_conflict_result(
                    spec=spec,
                    started_at=started_at,
                    raw_payload_text=raw_payload_text,
                    payload_hash=payload_hash,
                    dedup_key=dedup_key,
                    request_id=request_id,
                    instrument_symbol=instrument_symbol,
                    source_snapshot_id=source_snapshot_id,
                    schema_version=response_schema_version,
                    versions=versions,
                    existing_ingestion_id=existing.ingestion_id,
                )
            self._repository.touch_ingestion_idempotency_key(
                endpoint=spec.endpoint,
                dedup_key=dedup_key,
                seen_at=datetime.now(tz=UTC),
            )
            body = self._build_duplicate_response(
                existing_response=existing.response_payload,
                endpoint=spec.endpoint,
                ingestion_kind=spec.ingestion_kind,
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                instrument_symbol=instrument_symbol,
                schema_version=response_schema_version,
            )
            self._save_run_log(
                endpoint=spec.endpoint,
                ingestion_kind=spec.ingestion_kind,
                instrument_symbol=instrument_symbol,
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                outcome="duplicate",
                http_status=200,
                ingestion_id=body.ingestion_id,
                dead_letter_id=body.dead_letter_id,
                detail={"duplicate_of": existing.ingestion_id},
                started_at=started_at,
            )
            return ReliabilityResult(status_code=200, body=body)

        stored_at = datetime.now(tz=UTC)
        ingestion_id = f"ing-{uuid4().hex}"
        self._repository.save_ingestion(
            ingestion_id=ingestion_id,
            ingestion_kind=spec.ingestion_kind,
            source_snapshot_id=source_snapshot_id or dedup_key,
            instrument_symbol=instrument_symbol or "unknown",
            observed_payload=payload.model_dump(mode="json"),
            stored_at=stored_at,
        )

        try:
            downstream_result = after_store(payload, ingestion_id, stored_at)
        except Exception as exc:
            dead_letter = self._repository.save_dead_letter(
                dead_letter_id=f"dlq-{uuid4().hex}",
                endpoint=spec.endpoint,
                ingestion_kind=spec.ingestion_kind,
                instrument_symbol=instrument_symbol,
                source_snapshot_id=source_snapshot_id,
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                raw_payload=raw_payload_text,
                error_code="downstream_failure",
                error_detail={"message": str(exc), "type": type(exc).__name__},
                ingestion_id=ingestion_id,
                stored_at=datetime.now(tz=UTC),
            )
            body = self._build_success_response(
                endpoint=spec.endpoint,
                ingestion_kind=spec.ingestion_kind,
                status="accepted_with_dead_letter",
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                duplicate=False,
                stored_at=stored_at,
                ingestion_id=ingestion_id,
                dead_letter_id=dead_letter.dead_letter_id,
                downstream_status="failed",
                downstream_result=None,
                instrument_symbol=instrument_symbol,
                schema_version=response_schema_version,
            )
            self._repository.save_ingestion_idempotency_key(
                endpoint=spec.endpoint,
                dedup_key=dedup_key,
                request_id=request_id,
                payload_hash=payload_hash,
                ingestion_id=ingestion_id,
                response_payload=body.model_dump(mode="json"),
                first_seen_at=stored_at,
                last_seen_at=stored_at,
            )
            self._save_run_log(
                endpoint=spec.endpoint,
                ingestion_kind=spec.ingestion_kind,
                instrument_symbol=instrument_symbol,
                request_id=request_id,
                dedup_key=dedup_key,
                payload_hash=payload_hash,
                outcome="downstream_failed",
                http_status=202,
                ingestion_id=ingestion_id,
                dead_letter_id=dead_letter.dead_letter_id,
                detail={"type": type(exc).__name__, "message": str(exc)},
                started_at=started_at,
            )
            return ReliabilityResult(status_code=202, body=body)

        downstream_payload = self._coerce_downstream_result(downstream_result)
        downstream_status = "skipped" if downstream_payload.get("stored_only") else "completed"
        body = self._build_success_response(
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            status="accepted",
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            duplicate=False,
            stored_at=stored_at,
            ingestion_id=ingestion_id,
            dead_letter_id=None,
            downstream_status=downstream_status,
            downstream_result=downstream_payload,
            instrument_symbol=instrument_symbol,
            schema_version=response_schema_version,
        )
        self._repository.save_ingestion_idempotency_key(
            endpoint=spec.endpoint,
            dedup_key=dedup_key,
            request_id=request_id,
            payload_hash=payload_hash,
            ingestion_id=ingestion_id,
            response_payload=body.model_dump(mode="json"),
            first_seen_at=stored_at,
            last_seen_at=stored_at,
        )
        self._save_run_log(
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=instrument_symbol,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            outcome="accepted",
            http_status=201,
            ingestion_id=ingestion_id,
            dead_letter_id=None,
            detail={"downstream_status": downstream_status},
            started_at=started_at,
        )
        return ReliabilityResult(status_code=201, body=body)

    def _build_duplicate_response(
        self,
        *,
        existing_response: dict[str, Any],
        endpoint: str,
        ingestion_kind: str,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        instrument_symbol: str | None,
        schema_version: str,
    ) -> ReliableIngestionResponse:
        stored = ReliableIngestionResponse.model_validate(existing_response)
        current = self._build_data_quality(instrument_symbol=instrument_symbol)
        return stored.model_copy(
            update={
                "endpoint": endpoint,
                "ingestion_kind": ingestion_kind,
                "status": "duplicate",
                "request_id": request_id,
                "dedup_key": dedup_key,
                "payload_hash": payload_hash,
                "duplicate": True,
                "profile_version": current.profile_version,
                "engine_version": current.engine_version,
                "schema_version": schema_version,
                "data_status": current.data_status,
                "freshness": current.freshness,
                "completeness": current.completeness,
            },
        )

    def _build_success_response(
        self,
        *,
        endpoint: str,
        ingestion_kind: str,
        status: str,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        duplicate: bool,
        stored_at: datetime | None,
        ingestion_id: str | None,
        dead_letter_id: str | None,
        downstream_status: str,
        downstream_result: dict[str, Any] | None,
        instrument_symbol: str | None,
        schema_version: str,
    ) -> ReliableIngestionResponse:
        data_quality = self._build_data_quality(instrument_symbol=instrument_symbol)
        return ReliableIngestionResponse(
            endpoint=endpoint,
            ingestion_kind=ingestion_kind,
            status=status,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            duplicate=duplicate,
            stored_at=stored_at,
            ingestion_id=ingestion_id,
            dead_letter_id=dead_letter_id,
            downstream_status=downstream_status,
            downstream_result=downstream_result,
            profile_version=data_quality.profile_version,
            engine_version=data_quality.engine_version,
            schema_version=schema_version,
            data_status=data_quality.data_status,
            freshness=data_quality.freshness,
            completeness=data_quality.completeness,
        )

    def _invalid_json_result(
        self,
        *,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_payload_text: str,
        payload_hash: str,
        detail: dict[str, Any],
    ) -> ReliabilityResult:
        versions = self._resolve_versions(instrument_symbol=None)
        dead_letter = self._repository.save_dead_letter(
            dead_letter_id=f"dlq-{uuid4().hex}",
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=None,
            source_snapshot_id=None,
            request_id=None,
            dedup_key=payload_hash,
            payload_hash=payload_hash,
            raw_payload=raw_payload_text,
            error_code="invalid_json",
            error_detail=detail,
            ingestion_id=None,
            stored_at=datetime.now(tz=UTC),
        )
        body = IngestionErrorResponse(
            error="invalid_json",
            detail=detail,
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            request_id=None,
            dedup_key=payload_hash,
            payload_hash=payload_hash,
            dead_letter_id=dead_letter.dead_letter_id,
            profile_version=versions[0],
            engine_version=versions[1],
            schema_version=RELIABILITY_SCHEMA_VERSION,
        )
        self._save_run_log(
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=None,
            request_id=None,
            dedup_key=payload_hash,
            payload_hash=payload_hash,
            outcome="dead_lettered",
            http_status=400,
            ingestion_id=None,
            dead_letter_id=dead_letter.dead_letter_id,
            detail=detail,
            started_at=started_at,
        )
        return ReliabilityResult(status_code=400, body=body)

    def _validation_error_result(
        self,
        *,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_payload_text: str,
        payload_hash: str,
        dedup_key: str,
        request_id: str | None,
        instrument_symbol: str | None,
        source_snapshot_id: str | None,
        schema_version: str,
        detail: Any,
    ) -> ReliabilityResult:
        versions = self._resolve_versions(instrument_symbol=instrument_symbol)
        dead_letter = self._repository.save_dead_letter(
            dead_letter_id=f"dlq-{uuid4().hex}",
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            raw_payload=raw_payload_text,
            error_code="validation_error",
            error_detail={"errors": detail},
            ingestion_id=None,
            stored_at=datetime.now(tz=UTC),
        )
        body = IngestionErrorResponse(
            error="validation_error",
            detail=detail,
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            dead_letter_id=dead_letter.dead_letter_id,
            profile_version=versions[0],
            engine_version=versions[1],
            schema_version=schema_version or RELIABILITY_SCHEMA_VERSION,
        )
        self._save_run_log(
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=instrument_symbol,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            outcome="dead_lettered",
            http_status=422,
            ingestion_id=None,
            dead_letter_id=dead_letter.dead_letter_id,
            detail={"errors": detail},
            started_at=started_at,
        )
        return ReliabilityResult(status_code=422, body=body)

    def _idempotency_conflict_result(
        self,
        *,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_payload_text: str,
        payload_hash: str,
        dedup_key: str,
        request_id: str | None,
        instrument_symbol: str | None,
        source_snapshot_id: str | None,
        schema_version: str,
        versions: tuple[str, str],
        existing_ingestion_id: str,
    ) -> ReliabilityResult:
        detail = {
            "message": "The same request id/dedup key was submitted with a different payload hash.",
            "existing_ingestion_id": existing_ingestion_id,
        }
        dead_letter = self._repository.save_dead_letter(
            dead_letter_id=f"dlq-{uuid4().hex}",
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=instrument_symbol,
            source_snapshot_id=source_snapshot_id,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            raw_payload=raw_payload_text,
            error_code="idempotency_conflict",
            error_detail=detail,
            ingestion_id=None,
            stored_at=datetime.now(tz=UTC),
        )
        body = IngestionErrorResponse(
            error="idempotency_conflict",
            detail=detail,
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            dead_letter_id=dead_letter.dead_letter_id,
            profile_version=versions[0],
            engine_version=versions[1],
            schema_version=schema_version,
        )
        self._save_run_log(
            endpoint=spec.endpoint,
            ingestion_kind=spec.ingestion_kind,
            instrument_symbol=instrument_symbol,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            outcome="dead_lettered",
            http_status=409,
            ingestion_id=None,
            dead_letter_id=dead_letter.dead_letter_id,
            detail=detail,
            started_at=started_at,
        )
        return ReliabilityResult(status_code=409, body=body)

    def _build_data_quality(self, *, instrument_symbol: str | None) -> DataQualityResponse:
        latest_market = self._latest_ingestion("market_structure", instrument_symbol=instrument_symbol)
        latest_process = self._latest_ingestion("process_context", instrument_symbol=instrument_symbol)
        latest_depth = self._latest_ingestion("depth_snapshot", instrument_symbol=instrument_symbol)
        latest_event = self._latest_ingestion("event_snapshot", instrument_symbol=instrument_symbol)
        latest_adapter = self._latest_adapter_ingestion(instrument_symbol=instrument_symbol)
        now = datetime.now(tz=UTC)

        macro_dt = self._latest_timestamp(
            self._extract_payload_timestamp(latest_market.observed_payload) if latest_market is not None else None,
            self._extract_payload_timestamp(latest_process.observed_payload) if latest_process is not None else None,
        )
        latest_any = self._latest_timestamp(
            macro_dt,
            self._extract_payload_timestamp(latest_depth.observed_payload) if latest_depth is not None else None,
            self._extract_payload_timestamp(latest_event.observed_payload) if latest_event is not None else None,
            self._extract_payload_timestamp(latest_adapter.observed_payload) if latest_adapter is not None else None,
        )

        depth_available = self._depth_available(latest_depth)
        dom_available = self._dom_available(latest_depth)
        degraded_modes: list[DegradedMode] = []
        if not depth_available:
            degraded_modes.append(DegradedMode.NO_DEPTH)
        if not dom_available:
            degraded_modes.append(DegradedMode.NO_DOM)
        if not self._ai_available:
            degraded_modes.append(DegradedMode.NO_AI)
        if macro_dt is None or now - macro_dt > MACRO_STALE_AFTER:
            degraded_modes.append(DegradedMode.STALE_MACRO)
        if self._replay_rebuild_active(instrument_symbol=instrument_symbol):
            degraded_modes.append(DegradedMode.REPLAY_REBUILD)

        unique_modes: list[DegradedMode] = []
        for item in degraded_modes:
            if item not in unique_modes:
                unique_modes.append(item)

        freshness = self._classify_freshness(latest_any)
        completeness = "complete" if not unique_modes else "partial"
        if DegradedMode.REPLAY_REBUILD in unique_modes:
            completeness = "gapped"

        feature_completeness = 1.0
        if DegradedMode.REPLAY_REBUILD in unique_modes:
            feature_completeness = 0.5
        elif not depth_available and not dom_available:
            feature_completeness = 0.6
        elif not depth_available or not dom_available:
            feature_completeness = 0.75
        if DegradedMode.STALE_MACRO in unique_modes:
            feature_completeness = min(feature_completeness, 0.7)
        if DegradedMode.NO_AI in unique_modes:
            feature_completeness = min(feature_completeness, 0.95)

        freshness_ms = 0
        if latest_any is not None:
            freshness_ms = max(0, int((now - latest_any).total_seconds() * 1000))

        data_status = BeliefDataStatus(
            data_freshness_ms=freshness_ms,
            feature_completeness=feature_completeness,
            depth_available=depth_available,
            dom_available=dom_available,
            ai_available=self._ai_available,
            degraded_modes=unique_modes,
            freshness=freshness,
            completeness=completeness,
        )

        status = ServiceHealthStatus.HEALTHY
        if self._pause_sentinel_path().exists():
            status = ServiceHealthStatus.PAUSED
        elif DegradedMode.REPLAY_REBUILD in unique_modes:
            status = ServiceHealthStatus.REBUILD_REQUIRED
        elif unique_modes:
            status = ServiceHealthStatus.DEGRADED

        profile_version, engine_version = self._resolve_versions(instrument_symbol=instrument_symbol)
        return DataQualityResponse(
            status=status,
            degraded_reasons=[DEGRADED_REASON_MAP[item] for item in unique_modes],
            instrument_symbol=instrument_symbol,
            profile_version=profile_version,
            engine_version=engine_version,
            schema_version=RELIABILITY_SCHEMA_VERSION,
            data_status=data_status,
            freshness=data_status.freshness,
            completeness=data_status.completeness,
            source_statuses=[
                self._build_source_status("market_structure", latest_market),
                self._build_source_status("process_context", latest_process),
                self._build_source_status("depth_snapshot", latest_depth),
                self._build_source_status("event_snapshot", latest_event),
                self._build_source_status("adapter_payload", latest_adapter),
            ],
        )

    def _build_source_status(self, source_kind: str, stored_ingestion) -> DataQualitySourceStatus:
        observed_at = None
        if stored_ingestion is not None:
            observed_at = self._extract_payload_timestamp(stored_ingestion.observed_payload)
        freshness_ms = None
        if observed_at is not None:
            freshness_ms = max(0, int((datetime.now(tz=UTC) - observed_at).total_seconds() * 1000))
        return DataQualitySourceStatus(
            source_kind=source_kind,
            latest_observed_at=observed_at,
            available=observed_at is not None,
            freshness_ms=freshness_ms,
        )

    def _depth_available(self, stored_ingestion) -> bool:
        if stored_ingestion is None:
            return False
        payload = stored_ingestion.observed_payload
        observed_at = self._extract_payload_timestamp(payload)
        if observed_at is None or datetime.now(tz=UTC) - observed_at > DEPTH_STALE_AFTER:
            return False
        coverage_state = payload.get("coverage_state")
        return coverage_state not in {
            DepthCoverageState.UNAVAILABLE.value,
            DepthCoverageState.INTERRUPTED.value,
        }

    def _dom_available(self, stored_ingestion) -> bool:
        if not self._depth_available(stored_ingestion):
            return False
        payload = stored_ingestion.observed_payload
        return payload.get("best_bid") is not None and payload.get("best_ask") is not None

    def _replay_rebuild_active(self, *, instrument_symbol: str | None) -> bool:
        stored = self._latest_ingestion("replay_workbench_snapshot", instrument_symbol=instrument_symbol)
        if stored is None:
            return False
        payload = stored.observed_payload
        data_status = payload.get("data_status")
        if isinstance(data_status, dict):
            modes = data_status.get("degraded_modes") or []
            if any(mode in {DegradedMode.REPLAY_REBUILD.value, "replay_rebuild"} for mode in modes):
                return True
        integrity = payload.get("integrity")
        if isinstance(integrity, dict):
            return integrity.get("status") in {"missing_local_history", "gaps_detected", "no_live_data"}
        return False

    def _latest_ingestion(self, ingestion_kind: str, *, instrument_symbol: str | None) -> Any:
        items = self._repository.list_ingestions(
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            limit=1,
        )
        return items[0] if items else None

    def _latest_adapter_ingestion(self, *, instrument_symbol: str | None) -> Any:
        candidates = [
            self._latest_ingestion("adapter_continuous_state", instrument_symbol=instrument_symbol),
            self._latest_ingestion("adapter_trigger_burst", instrument_symbol=instrument_symbol),
            self._latest_ingestion("adapter_history_bars", instrument_symbol=instrument_symbol),
            self._latest_ingestion("adapter_history_footprint", instrument_symbol=instrument_symbol),
        ]
        ranked = [
            (self._extract_payload_timestamp(item.observed_payload), item)
            for item in candidates
            if item is not None and self._extract_payload_timestamp(item.observed_payload) is not None
        ]
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return ranked[0][1]

    def _find_last_success_at(self, *, instrument_symbol: str | None) -> datetime | None:
        recent = self._repository.list_ingestion_run_logs(
            instrument_symbol=instrument_symbol,
            limit=100,
        )
        for item in recent:
            if item.outcome in {"accepted", "downstream_failed"} and item.ingestion_id is not None:
                return item.completed_at
        return None

    def _resolve_versions(self, *, instrument_symbol: str | None) -> tuple[str, str]:
        profile = (
            self._repository.get_active_instrument_profile(instrument_symbol)
            if instrument_symbol is not None
            else None
        )
        build = self._repository.get_active_recognizer_build()
        profile_version = profile.profile_version if profile is not None else DEFAULT_PROFILE_VERSION
        engine_version = build.engine_version if build is not None else DEFAULT_ENGINE_VERSION
        return profile_version, engine_version

    def _save_run_log(
        self,
        *,
        endpoint: str,
        ingestion_kind: str,
        instrument_symbol: str | None,
        request_id: str | None,
        dedup_key: str,
        payload_hash: str,
        outcome: str,
        http_status: int,
        ingestion_id: str | None,
        dead_letter_id: str | None,
        detail: dict[str, Any],
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(tz=UTC)
        self._repository.save_ingestion_run_log(
            run_id=f"run-{uuid4().hex}",
            endpoint=endpoint,
            ingestion_kind=ingestion_kind,
            instrument_symbol=instrument_symbol,
            request_id=request_id,
            dedup_key=dedup_key,
            payload_hash=payload_hash,
            outcome=outcome,
            http_status=http_status,
            ingestion_id=ingestion_id,
            dead_letter_id=dead_letter_id,
            detail=detail,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _recognition_summary(result) -> dict[str, Any]:
        return {
            "triggered": result.triggered,
            "market_time": result.market_time.isoformat() if result.market_time is not None else None,
            "profile_version": result.profile_version,
            "engine_version": result.engine_version,
            "recognition_mode": result.recognition_mode.value if result.recognition_mode is not None else None,
            "feature_slice_id": result.feature_slice_id,
            "belief_state_id": result.belief_state.belief_state_id if result.belief_state is not None else None,
            "closed_episode_ids": [item.episode_id for item in result.closed_episodes],
            "notes": result.notes,
        }

    @staticmethod
    def _parse_json_body(raw_payload_text: str) -> tuple[dict[str, Any], json.JSONDecodeError | None]:
        try:
            parsed = json.loads(raw_payload_text or "{}")
        except json.JSONDecodeError as exc:
            return {}, exc
        if not isinstance(parsed, dict):
            return {"value": parsed}, None
        return parsed, None

    @staticmethod
    def _decode_body(body: bytes) -> str:
        return body.decode("utf-8", errors="replace")

    @staticmethod
    def _hash_bytes(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    @staticmethod
    def _hash_json(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=_json_default)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_request_id(payload: dict[str, Any]) -> str | None:
        for key in ("snapshot_id", "event_snapshot_id", "process_context_id", "depth_snapshot_id", "message_id", "batch_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_instrument_symbol(payload: dict[str, Any]) -> str | None:
        instrument = payload.get("instrument")
        if isinstance(instrument, dict):
            symbol = instrument.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                return symbol.strip()
        return None

    @staticmethod
    def _extract_schema_version(payload: dict[str, Any]) -> str:
        value = payload.get("schema_version")
        return value.strip() if isinstance(value, str) and value.strip() else RELIABILITY_SCHEMA_VERSION

    @staticmethod
    def _extract_payload_timestamp(payload: dict[str, Any]) -> datetime | None:
        for key in ("observed_at", "emitted_at", "stored_at"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                try:
                    return _parse_datetime(value)
                except ValueError:
                    continue
            if isinstance(value, datetime):
                return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return None

    @staticmethod
    def _classify_freshness(latest_at: datetime | None) -> str:
        if latest_at is None:
            return "offline"
        lag_seconds = max(0, int((datetime.now(tz=UTC) - latest_at).total_seconds()))
        if lag_seconds <= 10:
            return "fresh"
        if lag_seconds <= 60:
            return "delayed"
        return "stale"

    @staticmethod
    def _latest_timestamp(*values: datetime | None) -> datetime | None:
        available = [item for item in values if item is not None]
        if not available:
            return None
        return max(available)

    @staticmethod
    def _coerce_downstream_result(result: Any) -> dict[str, Any]:
        if isinstance(result, (AdapterAcceptedResponse, DepthSnapshotAcceptedResponse)):
            return result.model_dump(mode="json")
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        if isinstance(result, dict):
            return result
        return {"value": result}

    def _validate_adapter_payload(self, payload: dict[str, Any]) -> AdapterPayloadType:
        message_type = payload.get("message_type")
        if message_type == "continuous_state":
            return AdapterContinuousStatePayload.model_validate(payload)
        if message_type == "trigger_burst":
            return AdapterTriggerBurstPayload.model_validate(payload)
        if message_type == "history_bars":
            return AdapterHistoryBarsPayload.model_validate(payload)
        if message_type == "history_footprint":
            return AdapterHistoryFootprintPayload.model_validate(payload)
        raise ValueError(f"Unsupported adapter message_type: {message_type!r}")

    def _pause_sentinel_path(self) -> Path:
        return self._repository.workspace_root / PAUSE_SENTINEL


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo is not None else value.replace(tzinfo=UTC).isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")
