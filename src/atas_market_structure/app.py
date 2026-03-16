from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ValidationError

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.ai_review_services import (
    ReplayAiChatService,
    ReplayAiReviewNotFoundError,
    ReplayAiReviewService,
    ReplayAiReviewUnavailableError,
)
from atas_market_structure.depth_services import DepthMonitoringService
from atas_market_structure.models import (
    AdapterAcceptedResponse,
    AdapterContinuousStatePayload,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    AnalysisEnvelope,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    EventSnapshotPayload,
    IngestionAcceptedResponse,
    IngestionEnvelope,
    LiquidityMemoryEnvelope,
    LiquidityMemoryRecord,
    MarketStructurePayload,
    ReplayAiReviewRequest,
    ReplayAiReviewResponse,
    ReplayAiChatRequest,
    ReplayAiChatResponse,
    ReplayOperatorEntryAcceptedResponse,
    ReplayOperatorEntryEnvelope,
    ReplayOperatorEntryRequest,
    ReplayManualRegionAnnotationAcceptedResponse,
    ReplayManualRegionAnnotationEnvelope,
    ReplayManualRegionAnnotationRequest,
    ReplayFootprintBarDetail,
    ReplayWorkbenchAcceptedResponse,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchSnapshotPayload,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.services import IngestionOrchestrator
from atas_market_structure.workbench_services import ReplayWorkbenchNotFoundError, ReplayWorkbenchService


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


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
        adapter_ingestion_service: AdapterIngestionService | None = None,
        replay_workbench_service: ReplayWorkbenchService | None = None,
        replay_ai_review_service: ReplayAiReviewService | None = None,
        replay_ai_chat_service: ReplayAiChatService | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator or IngestionOrchestrator(repository=repository)
        self._depth_monitoring_service = depth_monitoring_service or DepthMonitoringService(repository=repository)
        self._adapter_ingestion_service = adapter_ingestion_service or AdapterIngestionService(
            repository=repository,
            orchestrator=self._orchestrator,
        )
        self._replay_workbench_service = replay_workbench_service or ReplayWorkbenchService(repository=repository)
        self._replay_ai_review_service = replay_ai_review_service
        self._replay_ai_chat_service = replay_ai_chat_service
        self._analysis_pattern = re.compile(r"^/api/v1/analyses/(?P<analysis_id>[^/]+)$")
        self._ingestion_pattern = re.compile(r"^/api/v1/ingestions/(?P<ingestion_id>[^/]+)$")

    def dispatch(self, method: str, path: str, body: bytes | None = None) -> HttpResponse:
        route = urlsplit(path)
        route_path = route.path
        query = parse_qs(route.query)
        try:
            if method == "GET" and route_path == "/health":
                return self._json_response(200, {"status": "ok", "timestamp": datetime.now(tz=UTC)})

            if method == "GET" and route_path == "/workbench/replay":
                html = (STATIC_DIR / "replay_workbench.html").read_text(encoding="utf-8")
                return self._text_response(200, html, "text/html; charset=utf-8")

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

            if method == "POST" and route_path == "/api/v1/adapter/continuous-state":
                payload = AdapterContinuousStatePayload.model_validate_json(body or b"{}")
                response = self._adapter_ingestion_service.ingest_continuous_state(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/adapter/history-bars":
                payload = AdapterHistoryBarsPayload.model_validate_json(body or b"{}")
                response = self._adapter_ingestion_service.ingest_history_bars(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/adapter/history-footprint":
                payload = AdapterHistoryFootprintPayload.model_validate_json(body or b"{}")
                response = self._adapter_ingestion_service.ingest_history_footprint(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/adapter/trigger-burst":
                payload = AdapterTriggerBurstPayload.model_validate_json(body or b"{}")
                response = self._adapter_ingestion_service.ingest_trigger_burst(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-snapshots":
                payload = ReplayWorkbenchSnapshotPayload.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.ingest_replay_snapshot(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-builder/build":
                payload = ReplayWorkbenchBuildRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.build_replay_snapshot(payload)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/replay-cache":
                cache_key = query.get("cache_key", [None])[0]
                if cache_key is None:
                    return self._json_response(400, {"error": "missing_query_parameter", "detail": "cache_key is required."})
                response = self._replay_workbench_service.get_cache_record(cache_key)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-cache/invalidate":
                payload = ReplayWorkbenchInvalidationRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.invalidate_cache_record(payload)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/operator-entries":
                payload = ReplayOperatorEntryRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.record_operator_entry(payload)
                return self._json_model_response(201, response)

            if method == "GET" and route_path == "/api/v1/workbench/operator-entries":
                replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
                if replay_ingestion_id is None:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "replay_ingestion_id is required."},
                    )
                response = self._replay_workbench_service.list_operator_entries(replay_ingestion_id)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/manual-regions":
                payload = ReplayManualRegionAnnotationRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.record_manual_region(payload)
                return self._json_model_response(201, response)

            if method == "GET" and route_path == "/api/v1/workbench/manual-regions":
                replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
                if replay_ingestion_id is None:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "replay_ingestion_id is required."},
                    )
                response = self._replay_workbench_service.list_manual_regions(replay_ingestion_id)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/footprint-bar":
                replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
                bar_started_at_raw = query.get("bar_started_at", [None])[0]
                if replay_ingestion_id is None or bar_started_at_raw is None:
                    return self._json_response(
                        400,
                        {
                            "error": "missing_query_parameter",
                            "detail": "replay_ingestion_id and bar_started_at are required.",
                        },
                    )
                response = self._replay_workbench_service.get_footprint_bar_detail(
                    replay_ingestion_id=replay_ingestion_id,
                    bar_started_at=datetime.fromisoformat(_normalize_query_datetime(bar_started_at_raw)),
                )
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-ai-review":
                if self._replay_ai_review_service is None:
                    return self._json_response(
                        503,
                        {
                            "error": "ai_review_unavailable",
                            "detail": "Replay AI review service is not configured.",
                        },
                    )
                payload = ReplayAiReviewRequest.model_validate_json(body or b"{}")
                response = self._replay_ai_review_service.review_replay(payload)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-ai-chat":
                if self._replay_ai_chat_service is None:
                    return self._json_response(
                        503,
                        {
                            "error": "ai_chat_unavailable",
                            "detail": "Replay AI chat service is not configured.",
                        },
                    )
                payload = ReplayAiChatRequest.model_validate_json(body or b"{}")
                response = self._replay_ai_chat_service.chat(payload)
                return self._json_model_response(200, response)

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
        except (NotFoundError, ReplayWorkbenchNotFoundError, ReplayAiReviewNotFoundError) as exc:
            return self._json_response(404, {"error": "not_found", "detail": str(exc)})
        except ReplayAiReviewUnavailableError as exc:
            return self._json_response(503, {"error": "ai_review_unavailable", "detail": str(exc)})
        except json.JSONDecodeError:
            return self._json_response(400, {"error": "invalid_json", "detail": "Request body is not valid JSON."})
        except Exception as exc:  # pragma: no cover - last-resort path
            LOGGER.exception("Unhandled application error: %s", exc)
            return self._json_response(500, {"error": "internal_error", "detail": "Unexpected server error."})

    @staticmethod
    def _json_model_response(
        status_code: int,
        model: BaseModel | IngestionAcceptedResponse | AnalysisEnvelope | IngestionEnvelope | DepthSnapshotAcceptedResponse | LiquidityMemoryEnvelope | LiquidityMemoryRecord | AdapterAcceptedResponse | ReplayWorkbenchAcceptedResponse | ReplayWorkbenchCacheEnvelope | ReplayWorkbenchInvalidationResponse | ReplayWorkbenchBuildResponse | ReplayAiReviewResponse | ReplayAiChatResponse | ReplayOperatorEntryAcceptedResponse | ReplayOperatorEntryEnvelope | ReplayManualRegionAnnotationAcceptedResponse | ReplayManualRegionAnnotationEnvelope | ReplayFootprintBarDetail,
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

    @staticmethod
    def _text_response(status_code: int, content: str, content_type: str) -> HttpResponse:
        body = content.encode("utf-8")
        return HttpResponse(
            status_code=status_code,
            body=body,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
            },
        )


def _default_json_serializer(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return timestamp.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _normalize_query_datetime(value: str) -> str:
    """Recover timezone offsets where '+' was decoded into a space by query parsing."""
    if "T" in value and "+" not in value and value.count(" ") == 1:
        date_part, offset_part = value.split(" ", maxsplit=1)
        if ":" in offset_part:
            return f"{date_part}+{offset_part}"
    return value
