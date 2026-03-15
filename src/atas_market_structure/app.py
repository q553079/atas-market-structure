from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ValidationError

from atas_market_structure.depth_services import DepthMonitoringService
from atas_market_structure.models import (
    AnalysisEnvelope,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    EventSnapshotPayload,
    IngestionAcceptedResponse,
    IngestionEnvelope,
    LiquidityMemoryEnvelope,
    LiquidityMemoryRecord,
    MarketStructurePayload,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.services import IngestionOrchestrator


LOGGER = logging.getLogger(__name__)


class NotFoundError(RuntimeError):
    """Raised when a requested resource does not exist."""


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class MarketStructureApplication:
    """Framework-free HTTP application for Windows-friendly local deployment."""

    def __init__(
        self,
        repository: AnalysisRepository,
        orchestrator: IngestionOrchestrator | None = None,
        depth_monitoring_service: DepthMonitoringService | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator or IngestionOrchestrator(repository=repository)
        self._depth_monitoring_service = depth_monitoring_service or DepthMonitoringService(repository=repository)
        self._analysis_pattern = re.compile(r"^/api/v1/analyses/(?P<analysis_id>[^/]+)$")
        self._ingestion_pattern = re.compile(r"^/api/v1/ingestions/(?P<ingestion_id>[^/]+)$")

    def dispatch(self, method: str, path: str, body: bytes | None = None) -> HttpResponse:
        route = urlsplit(path)
        route_path = route.path
        query = parse_qs(route.query)
        try:
            if method == "GET" and route_path == "/health":
                return self._json_response(200, {"status": "ok", "timestamp": datetime.now(tz=UTC)})

            if method == "POST" and route_path == "/api/v1/ingestions/market-structure":
                payload = MarketStructurePayload.model_validate_json(body or b"{}")
                response = self._orchestrator.ingest_market_structure(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/ingestions/event-snapshot":
                payload = EventSnapshotPayload.model_validate_json(body or b"{}")
                response = self._orchestrator.ingest_event_snapshot(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/ingestions/depth-snapshot":
                payload = DepthSnapshotPayload.model_validate_json(body or b"{}")
                response = self._depth_monitoring_service.ingest_depth_snapshot(payload)
                return self._json_model_response(201, response)

            if method == "GET" and route_path == "/api/v1/liquidity-memory":
                instrument_symbol = query.get("symbol", [None])[0]
                response = self._depth_monitoring_service.list_liquidity_memory(instrument_symbol=instrument_symbol)
                return self._json_model_response(200, response)

            analysis_match = self._analysis_pattern.match(route_path)
            if method == "GET" and analysis_match:
                analysis_id = analysis_match.group("analysis_id")
                stored = self._repository.get_analysis(analysis_id)
                if stored is None:
                    raise NotFoundError(f"analysis '{analysis_id}' not found")
                response = AnalysisEnvelope.model_validate({"analysis": stored.analysis_payload})
                return self._json_model_response(200, response)

            ingestion_match = self._ingestion_pattern.match(route_path)
            if method == "GET" and ingestion_match:
                ingestion_id = ingestion_match.group("ingestion_id")
                stored = self._repository.get_ingestion(ingestion_id)
                if stored is None:
                    raise NotFoundError(f"ingestion '{ingestion_id}' not found")
                response = IngestionEnvelope(
                    ingestion_id=stored.ingestion_id,
                    ingestion_kind=stored.ingestion_kind,
                    source_snapshot_id=stored.source_snapshot_id,
                    observed_payload=stored.observed_payload,
                    stored_at=stored.stored_at,
                )
                return self._json_model_response(200, response)

            return self._json_response(404, {"error": "not_found", "detail": f"No route for {method} {route_path}"})
        except ValidationError as exc:
            return self._json_response(422, {"error": "validation_error", "detail": json.loads(exc.json())})
        except NotFoundError as exc:
            return self._json_response(404, {"error": "not_found", "detail": str(exc)})
        except json.JSONDecodeError:
            return self._json_response(400, {"error": "invalid_json", "detail": "Request body is not valid JSON."})
        except Exception as exc:  # pragma: no cover - last-resort path
            LOGGER.exception("Unhandled application error: %s", exc)
            return self._json_response(500, {"error": "internal_error", "detail": "Unexpected server error."})

    @staticmethod
    def _json_model_response(
        status_code: int,
        model: BaseModel | IngestionAcceptedResponse | AnalysisEnvelope | IngestionEnvelope | DepthSnapshotAcceptedResponse | LiquidityMemoryEnvelope | LiquidityMemoryRecord,
    ) -> HttpResponse:
        payload = model.model_dump(mode="json")
        return MarketStructureApplication._json_response(status_code, payload)

    @staticmethod
    def _json_response(status_code: int, payload: dict[str, Any]) -> HttpResponse:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=_default_json_serializer).encode("utf-8")
        return HttpResponse(
            status_code=status_code,
            body=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": str(len(body)),
            },
        )


def _default_json_serializer(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return timestamp.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")
