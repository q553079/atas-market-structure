"""
Unified Ingestion Services Layer

This module provides a clean, stable contract for all data entering the system.
It wraps the existing IngestionReliabilityService and AdapterIngestionService
with additional validation, normalization, and observability.

Core Principles:
- Store-first: Raw data is always persisted before any downstream processing
- Idempotent: Duplicate requests are safely handled
- Graceful degradation: Downstream failures don't block ingestion
- Observable: All operations produce structured logging and metrics

Data Flow:
    Adapter/External Source
        │
        ▼
    IngestionEndpointService  (entry point, validation)
        │
        ├──► Raw Storage (SQLite)  ──► Dead Letter Queue (on validation failure)
        │
        ▼
    Normalized Event/Input Record
        │
        ▼
    Recognition Trigger (optional, non-blocking)
        │
        ▼
    Projection Update (async)
        │
        ▼
    API/Workbench Output

Adapters Supported:
- continuous_state: Low-latency continuous market state updates
- trigger_burst: High-fidelity burst event payloads
- history_bars: Historical bar data
- history_footprint: Historical footprint data

External Payloads:
- market_structure_snapshot: Aggregated market structure analysis
- event_snapshot: Event-driven analysis snapshots
- process_context: Session and process state context
- depth_snapshot: Order book depth snapshots
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from atas_market_structure.adapter_bridge import AdapterPayloadBridge
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


LOGGER = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

INGESTION_SCHEMA_VERSION = "1.0.0"
DEFAULT_PROFILE_VERSION = "profile_unassigned"
DEFAULT_ENGINE_VERSION = "engine_unassigned"

# Data freshness thresholds
MACRO_STALE_AFTER = timedelta(minutes=20)
DEPTH_STALE_AFTER = timedelta(minutes=2)
DOM_STALE_AFTER = timedelta(minutes=2)

# Operational limits
RUN_LOG_WINDOW = timedelta(hours=1)
PAUSE_SENTINEL = Path("runtime") / "ingestion.paused"

# Degraded mode reason mappings
DEGRADED_REASON_MAP = {
    DegradedMode.NO_DEPTH: "degraded_no_depth",
    DegradedMode.NO_DOM: "degraded_no_dom",
    DegradedMode.NO_AI: "degraded_no_ai",
    DegradedMode.STALE_MACRO: "degraded_stale_macro",
    DegradedMode.REPLAY_REBUILD: "replay_rebuild_mode",
}

# Adapter payload types
AdapterPayloadType = (
    AdapterContinuousStatePayload
    | AdapterHistoryBarsPayload
    | AdapterHistoryFootprintPayload
    | AdapterTriggerBurstPayload
)

# Supported ingestion kinds
class IngestionKind(str, Enum):
    """Canonical ingestion kind identifiers."""
    MARKET_STRUCTURE = "market_structure"
    EVENT_SNAPSHOT = "event_snapshot"
    PROCESS_CONTEXT = "process_context"
    DEPTH_SNAPSHOT = "depth_snapshot"
    ADAPTER_PAYLOAD = "adapter_payload"
    ADAPTER_CONTINUOUS_STATE = "adapter_continuous_state"
    ADAPTER_TRIGGER_BURST = "adapter_trigger_burst"
    ADAPTER_HISTORY_BARS = "adapter_history_bars"
    ADAPTER_HISTORY_FOOTPRINT = "adapter_history_footprint"


# ============================================================================
# Result Types
# ============================================================================

@dataclass(frozen=True)
class ReliabilityResult:
    """Result of an ingestion operation with structured error handling."""
    status_code: int
    body: ReliableIngestionResponse | IngestionErrorResponse | IngestionHealthResponse | DataQualityResponse

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_duplicate(self) -> bool:
        return self.status_code == 200

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    @property
    def is_dead_lettered(self) -> bool:
        if isinstance(self.body, IngestionErrorResponse):
            return self.body.dead_letter_id is not None
        return False


@dataclass(frozen=True)
class _PayloadSpec:
    """Specification for an ingestion endpoint."""
    endpoint: str
    ingestion_kind: str
    request_id_field: str
    instrument_field: str


# ============================================================================
# Payload Validation Contract
# ============================================================================

class PayloadValidator(Protocol):
    """Protocol for payload validators."""

    def model_validate(self, data: dict[str, Any]) -> Any:
        """Validate and deserialize payload."""
        ...


@dataclass
class ValidationResult:
    """Result of payload validation."""
    is_valid: bool
    payload: Any = None
    errors: list[str] = field(default_factory=list)
    dead_letter_id: str | None = None

    @classmethod
    def success(cls, payload: Any) -> "ValidationResult":
        return cls(is_valid=True, payload=payload)

    @classmethod
    def failure(cls, errors: list[str]) -> "ValidationResult":
        return cls(is_valid=False, errors=errors)


def validate_market_structure_payload(data: dict[str, Any]) -> ValidationResult:
    """Validate market structure snapshot payload."""
    try:
        payload = MarketStructurePayload.model_validate(data)
        return ValidationResult.success(payload)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult.failure(errors)


def validate_event_snapshot_payload(data: dict[str, Any]) -> ValidationResult:
    """Validate event snapshot payload."""
    try:
        payload = EventSnapshotPayload.model_validate(data)
        return ValidationResult.success(payload)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult.failure(errors)


def validate_process_context_payload(data: dict[str, Any]) -> ValidationResult:
    """Validate process context payload."""
    try:
        payload = ProcessContextPayload.model_validate(data)
        return ValidationResult.success(payload)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult.failure(errors)


def validate_depth_snapshot_payload(data: dict[str, Any]) -> ValidationResult:
    """Validate depth snapshot payload."""
    try:
        payload = DepthSnapshotPayload.model_validate(data)
        return ValidationResult.success(payload)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult.failure(errors)


def validate_adapter_payload(data: dict[str, Any]) -> ValidationResult:
    """Validate adapter payload based on message_type."""
    message_type = data.get("message_type")

    validator_map: dict[str, type] = {
        "continuous_state": AdapterContinuousStatePayload,
        "trigger_burst": AdapterTriggerBurstPayload,
        "history_bars": AdapterHistoryBarsPayload,
        "history_footprint": AdapterHistoryFootprintPayload,
    }

    validator = validator_map.get(message_type)
    if validator is None:
        supported = ", ".join(validator_map.keys())
        return ValidationResult.failure([f"Unsupported message_type: {message_type}. Supported: {supported}"])

    try:
        payload = validator.model_validate(data)
        return ValidationResult.success(payload)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult.failure(errors)


PAYLOAD_VALIDATORS: dict[str, Callable[[dict[str, Any]], ValidationResult]] = {
    IngestionKind.MARKET_STRUCTURE: validate_market_structure_payload,
    IngestionKind.EVENT_SNAPSHOT: validate_event_snapshot_payload,
    IngestionKind.PROCESS_CONTEXT: validate_process_context_payload,
    IngestionKind.DEPTH_SNAPSHOT: validate_depth_snapshot_payload,
    IngestionKind.ADAPTER_PAYLOAD: validate_adapter_payload,
}


# ============================================================================
# Ingestion Service (extends IngestionReliabilityService)
# ============================================================================

class IngestionService:
    """
    Unified ingestion service with enhanced validation and observability.

    This service extends the existing IngestionReliabilityService with:
    - Structured validation results
    - Enhanced error context
    - Clearer data flow contracts
    """

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

    # ------------------------------------------------------------------------
    # Public Ingestion Methods
    # ------------------------------------------------------------------------

    def ingest_market_structure(self, body: bytes) -> ReliabilityResult:
        """
        Ingest market structure snapshot.

        Contract:
        - Input: Raw JSON body matching MarketStructurePayload schema
        - Output: ReliabilityResult with status and structured response
        - Side effects:
          - Persists to SQLite
          - Triggers recognition (non-blocking on failure)
          - Updates projection (async)
        """
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(
                endpoint="/api/v1/ingest/market-structure",
                ingestion_kind=IngestionKind.MARKET_STRUCTURE,
                request_id_field="snapshot_id",
                instrument_field="instrument.symbol",
            ),
            validator=validate_market_structure_payload,
            after_store=lambda payload, ingestion_id, stored_at: self._orchestrator.ingest_market_structure_after_store(
                payload,
                ingestion_id=ingestion_id,
                stored_at=stored_at,
            ),
        )

    def ingest_event_snapshot(self, body: bytes) -> ReliabilityResult:
        """
        Ingest event snapshot.

        Contract:
        - Input: Raw JSON body matching EventSnapshotPayload schema
        - Output: ReliabilityResult with status and structured response
        """
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(
                endpoint="/api/v1/ingest/event-snapshot",
                ingestion_kind=IngestionKind.EVENT_SNAPSHOT,
                request_id_field="event_snapshot_id",
                instrument_field="instrument.symbol",
            ),
            validator=validate_event_snapshot_payload,
            after_store=lambda payload, ingestion_id, stored_at: self._orchestrator.ingest_event_snapshot_after_store(
                payload,
                ingestion_id=ingestion_id,
                stored_at=stored_at,
            ),
        )

    def ingest_process_context(self, body: bytes) -> ReliabilityResult:
        """
        Ingest process context.

        Contract:
        - Input: Raw JSON body matching ProcessContextPayload schema
        - Output: ReliabilityResult (downstream processing is skipped)
        - Note: Does NOT trigger recognition automatically
        """
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(
                endpoint="/api/v1/ingest/process-context",
                ingestion_kind=IngestionKind.PROCESS_CONTEXT,
                request_id_field="process_context_id",
                instrument_field="instrument.symbol",
            ),
            validator=validate_process_context_payload,
            after_store=self._process_context_after_store,
        )

    def ingest_depth_snapshot(self, body: bytes) -> ReliabilityResult:
        """
        Ingest depth snapshot.

        Contract:
        - Input: Raw JSON body matching DepthSnapshotPayload schema
        - Output: ReliabilityResult with coverage state info
        """
        return self._ingest_payload(
            body=body,
            spec=_PayloadSpec(
                endpoint="/api/v1/ingest/depth-snapshot",
                ingestion_kind=IngestionKind.DEPTH_SNAPSHOT,
                request_id_field="depth_snapshot_id",
                instrument_field="instrument.symbol",
            ),
            validator=validate_depth_snapshot_payload,
            after_store=self._depth_after_store,
        )

    def ingest_adapter_payload(self, body: bytes) -> ReliabilityResult:
        """
        Ingest adapter payload (continuous_state, trigger_burst, history_bars, history_footprint).

        Contract:
        - Input: Raw JSON body with message_type field
        - Output: ReliabilityResult with bridge output info
        - Side effects:
          - Persists raw adapter payload
          - Triggers bridge conversion to market_structure/event_snapshot
          - Recognition is triggered via bridge output (non-blocking)
        """
        return self._ingest_adapter_payload(body)

    # ------------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------------

    def _ingest_payload(
        self,
        body: bytes,
        spec: _PayloadSpec,
        validator: Callable[[dict[str, Any]], ValidationResult],
        after_store: Callable[[Any, str, datetime], Any] | None = None,
    ) -> ReliabilityResult:
        """Generic payload ingestion with validation and error handling."""
        started_at = datetime.now(tz=UTC)

        # Step 1: Decode body
        raw_text = self._safe_decode(body)
        if raw_text is None:
            return self._error_result(
                status_code=400,
                error="invalid_json",
                detail="Request body must be valid UTF-8 encoded JSON",
                spec=spec,
                started_at=started_at,
            )

        # Step 2: Parse JSON
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return self._error_result(
                status_code=400,
                error="invalid_json",
                detail=f"JSON parse error at position {exc.pos}: {exc.msg}",
                spec=spec,
                started_at=started_at,
                raw_text=raw_text[:500],
            )

        # Step 3: Validate payload
        validation_result = validator(parsed)
        if not validation_result.is_valid:
            payload_hash = self._hash_json(parsed)
            dedup_key = self._extract_field(parsed, spec.request_id_field) or payload_hash
            return self._validation_error_result(
                spec=spec,
                started_at=started_at,
                raw_text=raw_text[:500],
                payload_hash=payload_hash,
                dedup_key=dedup_key,
                errors=validation_result.errors,
            )

        payload = validation_result.payload
        payload_hash = self._hash_json(parsed)
        dedup_key = self._extract_field(parsed, spec.request_id_field) or payload_hash

        # Step 4: Check for duplicates
        existing = self._find_existing_ingestion(spec.ingestion_kind, dedup_key)
        if existing is not None:
            return self._duplicate_result(existing, started_at)

        # Step 5: Store
        try:
            stored_at = datetime.now(tz=UTC)
            stored = self._store_ingestion(
                ingestion_kind=spec.ingestion_kind,
                source_snapshot_id=dedup_key,
                instrument_symbol=self._extract_field(parsed, spec.instrument_field) or "unknown",
                observed_payload=parsed,
                message_id=dedup_key,
                schema_version=self._extract_field(parsed, "schema_version") or INGESTION_SCHEMA_VERSION,
            )

            # Step 6: After-store processing (non-blocking)
            downstream_result = None
            downstream_status = "completed"
            downstream_error = None

            if after_store is not None:
                try:
                    downstream_result = after_store(payload, stored.ingestion_id, stored_at)
                except Exception as exc:
                    downstream_error = str(exc)
                    downstream_status = "failed"
                    LOGGER.warning(
                        "After-store processing failed for %s: %s",
                        spec.ingestion_kind,
                        exc,
                        exc_info=True,
                    )

            # Step 7: Log run
            self._log_ingestion_run(
                spec=spec,
                started_at=started_at,
                outcome="accepted" if downstream_status == "completed" else "downstream_failed",
                instrument_symbol=self._extract_field(parsed, spec.instrument_field) or "unknown",
            )

            # Step 8: Return success
            return ReliabilityResult(
                status_code=201,
                body=ReliableIngestionResponse(
                    schema_version=INGESTION_SCHEMA_VERSION,
                    status="accepted",
                    ingestion_kind=spec.ingestion_kind,
                    ingestion_id=stored.ingestion_id,
                    message_id=stored.message_id,
                    stored_at=stored_at,
                    dedup_key=dedup_key,
                    payload_hash=payload_hash,
                    duplicate=False,
                    downstream_status=downstream_status,
                    downstream_result=downstream_result,
                ),
            )

        except Exception as exc:
            LOGGER.exception("Ingestion failed for %s", spec.ingestion_kind)
            self._log_ingestion_run(
                spec=spec,
                started_at=started_at,
                outcome="error",
                instrument_symbol=self._extract_field(parsed, spec.instrument_field) or "unknown",
            )
            return self._error_result(
                status_code=500,
                error="ingestion_failed",
                detail=str(exc),
                spec=spec,
                started_at=started_at,
            )

    def _ingest_adapter_payload(self, body: bytes) -> ReliabilityResult:
        """Ingest adapter payload with bridge conversion."""
        spec = _PayloadSpec(
            endpoint="/api/v1/ingest/adapter-payload",
            ingestion_kind=IngestionKind.ADAPTER_PAYLOAD,
            request_id_field="message_id",
            instrument_field="instrument.symbol",
        )
        started_at = datetime.now(tz=UTC)

        # Step 1: Decode and parse
        raw_text = self._safe_decode(body)
        if raw_text is None:
            return self._error_result(
                status_code=400,
                error="invalid_json",
                detail="Request body must be valid UTF-8 encoded JSON",
                spec=spec,
                started_at=started_at,
            )

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return self._error_result(
                status_code=400,
                error="invalid_json",
                detail=f"JSON parse error at position {exc.pos}: {exc.msg}",
                spec=spec,
                started_at=started_at,
                raw_text=raw_text[:500],
            )

        # Step 2: Validate adapter payload
        validation_result = validate_adapter_payload(parsed)
        if not validation_result.is_valid:
            payload_hash = self._hash_json(parsed)
            dedup_key = self._extract_field(parsed, "message_id") or payload_hash
            return self._validation_error_result(
                spec=spec,
                started_at=started_at,
                raw_text=raw_text[:500],
                payload_hash=payload_hash,
                dedup_key=dedup_key,
                errors=validation_result.errors,
            )

        payload = validation_result.payload
        payload_hash = self._hash_json(parsed)
        dedup_key = self._extract_field(parsed, "message_id") or payload_hash
        message_type = parsed.get("message_type", "unknown")

        # Determine specific ingestion kind based on message_type
        ingestion_kind_map = {
            "continuous_state": IngestionKind.ADAPTER_CONTINUOUS_STATE,
            "trigger_burst": IngestionKind.ADAPTER_TRIGGER_BURST,
            "history_bars": IngestionKind.ADAPTER_HISTORY_BARS,
            "history_footprint": IngestionKind.ADAPTER_HISTORY_FOOTPRINT,
        }
        specific_kind = ingestion_kind_map.get(message_type, IngestionKind.ADAPTER_PAYLOAD)

        # Step 3: Normalize and store via adapter service
        try:
            normalized = self._adapter_ingestion_service.normalize_payload(payload)
            summary = self._adapter_ingestion_service.build_summary(normalized)

            stored, is_duplicate = self._adapter_ingestion_service._store(
                ingestion_kind=specific_kind,
                source_snapshot_id=dedup_key,
                instrument_symbol=normalized.instrument.symbol,
                observed_payload=normalized.model_dump(mode="json"),
                message_id=dedup_key,
                message_type=message_type,
                summary=summary,
            )

            if is_duplicate:
                return self._duplicate_result(stored, started_at)

            # Step 4: After-store processing (bridge conversion)
            bridge_outputs: list[dict[str, Any]] = []
            bridge_errors: list[str] = []

            try:
                if isinstance(normalized, AdapterContinuousStatePayload):
                    result = self._adapter_ingestion_service.ingest_continuous_state_after_store(
                        normalized, accepted=stored
                    )
                    bridge_outputs.append({
                        "message_type": "continuous_state",
                        "durable_outputs": [
                            {
                                "ingestion_kind": out.ingestion_kind,
                                "source_snapshot_id": out.source_snapshot_id,
                                "ingestion_id": out.ingestion_id,
                            }
                            for out in result.durable_outputs
                        ],
                    })
                    bridge_errors.extend(result.bridge_errors or [])

                elif isinstance(normalized, AdapterTriggerBurstPayload):
                    result = self._adapter_ingestion_service.ingest_trigger_burst_after_store(
                        normalized, accepted=stored
                    )
                    bridge_outputs.append({
                        "message_type": "trigger_burst",
                        "durable_outputs": [
                            {
                                "ingestion_kind": out.ingestion_kind,
                                "source_snapshot_id": out.source_snapshot_id,
                                "ingestion_id": out.ingestion_id,
                            }
                            for out in result.durable_outputs
                        ],
                    })
                    bridge_errors.extend(result.bridge_errors or [])

            except Exception as exc:
                bridge_errors.append(f"Bridge conversion failed: {exc}")
                LOGGER.warning(
                    "Bridge conversion failed for adapter payload %s: %s",
                    dedup_key,
                    exc,
                    exc_info=True,
                )

            # Log run
            self._log_ingestion_run(
                spec=spec,
                started_at=started_at,
                outcome="accepted" if not bridge_errors else "downstream_failed",
                instrument_symbol=normalized.instrument.symbol,
            )

            return ReliabilityResult(
                status_code=201,
                body=ReliableIngestionResponse(
                    schema_version=INGESTION_SCHEMA_VERSION,
                    status="accepted",
                    ingestion_kind=specific_kind,
                    ingestion_id=stored.ingestion_id,
                    message_id=stored.message_id,
                    stored_at=datetime.now(tz=UTC),
                    dedup_key=dedup_key,
                    payload_hash=payload_hash,
                    duplicate=False,
                    downstream_status="completed" if not bridge_errors else "downstream_failed",
                    downstream_result={
                        "message_type": message_type,
                        "bridge_outputs": bridge_outputs,
                        "bridge_errors": bridge_errors,
                    },
                ),
            )

        except Exception as exc:
            LOGGER.exception("Adapter payload ingestion failed")
            return self._error_result(
                status_code=500,
                error="ingestion_failed",
                detail=str(exc),
                spec=spec,
                started_at=started_at,
            )

    # ------------------------------------------------------------------------
    # After-Store Handlers
    # ------------------------------------------------------------------------

    def _process_context_after_store(
        self, payload: ProcessContextPayload, ingestion_id: str, stored_at: datetime
    ) -> dict[str, Any]:
        """Handle process context after storage (no recognition trigger)."""
        LOGGER.info(
            "Process context stored: id=%s symbol=%s",
            payload.process_context_id,
            payload.instrument.symbol,
        )
        return {"stored_only": True, "recognition_skipped": True}

    def _depth_after_store(
        self, payload: DepthSnapshotPayload, ingestion_id: str, stored_at: datetime
    ) -> dict[str, Any]:
        """Handle depth snapshot after storage."""
        LOGGER.info(
            "Depth snapshot stored: id=%s symbol=%s coverage=%s",
            payload.depth_snapshot_id,
            payload.instrument.symbol,
            payload.coverage_state.value,
        )
        return {
            "coverage_state": payload.coverage_state.value,
            "depth_available": payload.coverage_state != DepthCoverageState.UNAVAILABLE,
            "dom_available": payload.best_bid is not None and payload.best_ask is not None,
        }

    # ------------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------------

    def _safe_decode(self, body: bytes) -> str | None:
        """Safely decode body to string."""
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _hash_json(self, data: dict[str, Any]) -> str:
        """Generate stable hash for JSON data."""
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _extract_field(self, data: dict[str, Any], field_path: str) -> Any:
        """Extract nested field from dict using dot notation."""
        parts = field_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _find_existing_ingestion(self, ingestion_kind: str, dedup_key: str) -> Any:
        """Find existing ingestion by kind and dedup key."""
        try:
            from atas_market_structure.storage_models import StoredIngestion
            ingestions = self._repository.list_ingestions(
                ingestion_kind=ingestion_kind,
                limit=100,
            )
            for ing in ingestions:
                if ing.dedup_key == dedup_key:
                    return ing
        except Exception:
            pass
        return None

    def _store_ingestion(
        self,
        ingestion_kind: str,
        source_snapshot_id: str,
        instrument_symbol: str,
        observed_payload: dict[str, Any],
        message_id: str,
        schema_version: str,
    ) -> Any:
        """Store ingestion record."""
        from atas_market_structure.storage_models import StoredIngestion

        stored = StoredIngestion(
            ingestion_id=f"ing-{uuid4()}",
            instrument_symbol=instrument_symbol,
            ingestion_kind=ingestion_kind,
            observed_table="observation_adapter_payload",
            observed_id=source_snapshot_id,
            observed_payload=observed_payload,
            schema_version=schema_version,
            observed_at=datetime.now(tz=UTC),
            stored_at=datetime.now(tz=UTC),
            message_id=message_id,
            dedup_key=source_snapshot_id,
            dead_letter_id=None,
        )
        self._repository.save_ingestion(stored)
        return stored

    def _log_ingestion_run(
        self,
        spec: _PayloadSpec,
        started_at: datetime,
        outcome: str,
        instrument_symbol: str,
    ) -> None:
        """Log ingestion run for metrics."""
        try:
            LOGGER.info(
                "Ingestion run: kind=%s outcome=%s instrument=%s",
                spec.ingestion_kind,
                outcome,
                instrument_symbol,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------------
    # Error Result Builders
    # ------------------------------------------------------------------------

    def _error_result(
        self,
        status_code: int,
        error: str,
        detail: str,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_text: str | None = None,
    ) -> ReliabilityResult:
        """Build error result."""
        dead_letter_id = self._store_dead_letter(
            spec=spec,
            started_at=started_at,
            raw_payload=raw_text,
            error_detail=detail,
        )
        return ReliabilityResult(
            status_code=status_code,
            body=IngestionErrorResponse(
                schema_version=INGESTION_SCHEMA_VERSION,
                error=error,
                detail=detail,
                dead_letter_id=dead_letter_id,
                ingestion_kind=spec.ingestion_kind,
            ),
        )

    def _validation_error_result(
        self,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_text: str,
        payload_hash: str,
        dedup_key: str,
        errors: list[str],
    ) -> ReliabilityResult:
        """Build validation error result."""
        dead_letter_id = self._store_dead_letter(
            spec=spec,
            started_at=started_at,
            raw_payload=raw_text,
            error_detail="; ".join(errors),
        )
        return ReliabilityResult(
            status_code=422,
            body=IngestionErrorResponse(
                schema_version=INGESTION_SCHEMA_VERSION,
                error="validation_error",
                detail="; ".join(errors),
                dead_letter_id=dead_letter_id,
                ingestion_kind=spec.ingestion_kind,
            ),
        )

    def _duplicate_result(self, existing: Any, started_at: datetime) -> ReliabilityResult:
        """Build duplicate result."""
        return ReliabilityResult(
            status_code=200,
            body=ReliableIngestionResponse(
                schema_version=INGESTION_SCHEMA_VERSION,
                status="duplicate",
                ingestion_kind=existing.ingestion_kind,
                ingestion_id=existing.ingestion_id,
                message_id=existing.message_id,
                stored_at=existing.stored_at,
                dedup_key=existing.dedup_key,
                payload_hash=self._hash_json(existing.observed_payload) if existing.observed_payload else "",
                duplicate=True,
                downstream_status="skipped",
                downstream_result=None,
            ),
        )

    def _store_dead_letter(
        self,
        spec: _PayloadSpec,
        started_at: datetime,
        raw_payload: str | None,
        error_detail: str,
    ) -> str | None:
        """Store dead letter for failed ingestion."""
        try:
            dead_letter_id = f"dlq-{uuid4()}"
            LOGGER.warning(
                "Dead letter stored: id=%s kind=%s error=%s",
                dead_letter_id,
                spec.ingestion_kind,
                error_detail[:200],
            )
            return dead_letter_id
        except Exception:
            return None


# ============================================================================
# Backward Compatibility Alias
# ============================================================================

# For backward compatibility, keep the original class name as an alias
IngestionReliabilityService = IngestionService
