from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from atas_market_structure.adapter_services import AdapterIngestionService
from atas_market_structure.ai_review_services import (
    ReplayAiChatResponse,
    ReplayAiReviewNotFoundError,
    ReplayAiReviewResponse,
    ReplayAiReviewService,
    ReplayAiReviewUnavailableError,
    ReplayAiChatService,
)
from atas_market_structure.app_routes import (
    handle_analysis_routes,
    handle_chat_routes,
    handle_health_routes,
    handle_ingestion_routes,
    handle_options_routes,
    handle_review_routes,
    handle_tuning_routes,
    handle_workbench_event_outcome_routes,
    handle_workbench_event_routes,
    handle_workbench_prompt_trace_routes,
    handle_workbench_routes,
)
from atas_market_structure.chart_candle_service import ChartCandleService
from atas_market_structure.app_shared import NotFoundError
from atas_market_structure.config import AppConfig
from atas_market_structure.continuous_contract_service import (
    ContinuousContractService,
    ContinuousContractServiceError,
)
from atas_market_structure.depth_services import DepthMonitoringService
from atas_market_structure.evaluation_services import EpisodeEvaluationService
from atas_market_structure.ingestion_reliability_services import IngestionReliabilityService
from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterAcceptedResponse,
    AdapterContinuousStatePayload,
    AdapterBackfillDispatchResponse,
    AdapterHistoryBarsPayload,
    AdapterHistoryInventoryPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    AnalysisEnvelope,
    BeliefLatestEnvelope,
    BeliefStateSnapshot,
    ChartCandleEnvelope,
    ContinuousAdjustmentMode,
    ContinuousBarsEnvelope,
    DataQualityResponse,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    EventSnapshotPayload,
    EpisodeEvaluation,
    EpisodeEvaluationEnvelope,
    EpisodeListEnvelope,
    EventEpisode,
    IngestionErrorResponse,
    IngestionAcceptedResponse,
    IngestionEnvelope,
    IngestionHealthResponse,
    LiquidityMemoryEnvelope,
    LiquidityMemoryRecord,
    MarketStructurePayload,
    MirrorBarsEnvelope,
    ProcessContextPayload,
    ReplayFootprintBarDetail,
    ReplayManualRegionAnnotationAcceptedResponse,
    ReplayManualRegionAnnotationEnvelope,
    ReplayManualRegionAnnotationRequest,
    ReplayOperatorEntryAcceptedResponse,
    ReplayOperatorEntryEnvelope,
    ReplayOperatorEntryRequest,
    ReplayWorkbenchAcceptedResponse,
    ReplayWorkbenchAtasBackfillAcceptedResponse,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchBackfillProgressResponse,
    ReplayProjectionQuery,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchBeliefTimelineEnvelope,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchEpisodeEvaluationListEnvelope,
    ReplayWorkbenchEpisodeReviewEnvelope,
    ReplayWorkbenchHealthStatusEnvelope,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchProfileEngineEnvelope,
    ReplayWorkbenchProjectionEnvelope,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
    ReplayWorkbenchTuningReviewEnvelope,
    ReliableIngestionResponse,
    RollMode,
    Timeframe,
)
from atas_market_structure.repository import AnalysisRepository
from atas_market_structure.recognition import DeterministicRecognitionService
from atas_market_structure.services import IngestionOrchestrator
from atas_market_structure.workbench_projection_services import ReplayWorkbenchProjectionService
from atas_market_structure.workbench_event_service import ReplayWorkbenchEventService
from atas_market_structure.workbench_event_outcome_service import ReplayWorkbenchEventOutcomeService
from atas_market_structure.workbench_prompt_trace_service import ReplayWorkbenchPromptTraceService
from atas_market_structure.workbench_services import (
    ReplayWorkbenchChatError,
    ReplayWorkbenchChatUnavailableError,
    ReplayWorkbenchChatService,
    ReplayWorkbenchNotFoundError,
    ReplayWorkbenchService,
)


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    stream_chunks: tuple[bytes, ...] | None = None


class MarketStructureApplication:
    """Framework-free HTTP application for Windows-friendly local deployment."""

    def __init__(
        self,
        repository: AnalysisRepository,
        orchestrator: IngestionOrchestrator | None = None,
        depth_monitoring_service: DepthMonitoringService | None = None,
        adapter_ingestion_service: AdapterIngestionService | None = None,
        recognition_service: DeterministicRecognitionService | None = None,
        replay_workbench_service: ReplayWorkbenchService | None = None,
        continuous_contract_service: ContinuousContractService | None = None,
        replay_ai_review_service: ReplayAiReviewService | None = None,
        replay_ai_chat_service: ReplayAiChatService | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self._repository = repository
        self._config = config or AppConfig.from_env()
        self._recognition_service = recognition_service or DeterministicRecognitionService(
            repository=repository,
            ai_available=(replay_ai_review_service is not None or replay_ai_chat_service is not None),
        )
        self._orchestrator = orchestrator or IngestionOrchestrator(
            repository=repository,
            recognition_service=self._recognition_service,
        )
        self._depth_monitoring_service = depth_monitoring_service or DepthMonitoringService(repository=repository)
        self._adapter_ingestion_service = adapter_ingestion_service or AdapterIngestionService(
            repository=repository,
            orchestrator=self._orchestrator,
            recognition_service=self._recognition_service,
        )
        self._ingestion_reliability_service = IngestionReliabilityService(
            repository=repository,
            orchestrator=self._orchestrator,
            depth_monitoring_service=self._depth_monitoring_service,
            adapter_ingestion_service=self._adapter_ingestion_service,
            ai_available=(
                replay_ai_review_service is not None
                or replay_ai_chat_service is not None
            ),
            recognition_service=self._recognition_service,
        )
        self._replay_workbench_service = replay_workbench_service or ReplayWorkbenchService(repository=repository)
        self._continuous_contract_service = continuous_contract_service or ContinuousContractService(repository=repository)
        self._workbench_projection_service = ReplayWorkbenchProjectionService(
            repository=repository,
            ingestion_reliability_service=self._ingestion_reliability_service,
        )
        self._replay_ai_review_service = replay_ai_review_service
        self._replay_ai_chat_service = replay_ai_chat_service
        self._replay_workbench_event_service = ReplayWorkbenchEventService(repository=repository)
        self._replay_workbench_event_outcome_service = ReplayWorkbenchEventOutcomeService(repository=repository)
        self._replay_workbench_prompt_trace_service = ReplayWorkbenchPromptTraceService(
            repository=repository,
            replay_ai_chat_service=self._replay_ai_chat_service,
        )
        self._replay_workbench_chat_service = ReplayWorkbenchChatService(
            repository=repository,
            replay_ai_chat_service=self._replay_ai_chat_service,
            event_service=self._replay_workbench_event_service,
            prompt_trace_service=self._replay_workbench_prompt_trace_service,
        )
        self._episode_evaluation_service = EpisodeEvaluationService(repository=repository)
        self._chart_candle_service = ChartCandleService(repository=repository)
        self._analysis_pattern = re.compile(r"^/api/v1/analyses/(?P<analysis_id>[^/]+)$")
        self._ingestion_pattern = re.compile(r"^/api/v1/ingestions/(?P<ingestion_id>[^/]+)$")
        self._episode_evaluation_pattern = re.compile(r"^/api/v1/review/episode-evaluation/(?P<episode_id>[^/]+)$")
        self._logger = LOGGER
        self._static_dir = STATIC_DIR
        self._http_response_type = HttpResponse
        self._not_found_error = NotFoundError
        self._analysis_envelope_type = AnalysisEnvelope
        self._ingestion_envelope_type = IngestionEnvelope
        self._roll_mode_type = RollMode
        self._parse_utc = _parse_utc
        self._normalize_query_datetime = _normalize_query_datetime

    def dispatch(self, method: str, path: str, body: bytes | None = None) -> HttpResponse:
        route = urlsplit(path)
        route_path = route.path
        query = parse_qs(route.query)
        try:
            for handler in (
                lambda: handle_health_routes(self, method, route_path, query),
                lambda: handle_ingestion_routes(self, method, route_path, query, body),
                lambda: handle_review_routes(self, method, route_path, query, body),
                lambda: handle_workbench_routes(self, method, route_path, query, body),
                lambda: handle_workbench_event_routes(self, method, route_path, query, body),
                lambda: handle_workbench_event_outcome_routes(self, method, route_path, query),
                lambda: handle_workbench_prompt_trace_routes(self, method, route_path, query),
                lambda: handle_chat_routes(self, method, route_path, query, body),
                lambda: handle_options_routes(self, method, route_path, query, body),
                lambda: handle_analysis_routes(self, method, route_path, query, body),
                lambda: handle_tuning_routes(self, method, route_path, query, body),
            ):
                response = handler()
                if response is not None:
                    return response

            return self._json_response(404, {"error": "not_found", "detail": f"No route for {method} {route_path}"})
        except ValidationError as exc:
            detail = json.loads(exc.json())
            body_preview = ""
            if body:
                try:
                    body_preview = body.decode("utf-8", errors="replace")[:4000]
                except Exception:  # pragma: no cover
                    body_preview = "<unable_to_decode_body>"
            self._logger.warning(
                "Validation error on %s %s: detail=%s body_preview=%s",
                method,
                route_path,
                detail,
                body_preview,
            )
            return self._json_response(422, {"error": "validation_error", "detail": detail})
        except (NotFoundError, ReplayWorkbenchNotFoundError, ReplayAiReviewNotFoundError) as exc:
            return self._json_response(404, {"error": "not_found", "detail": str(exc)})
        except ReplayWorkbenchChatUnavailableError as exc:
            return self._json_response(503, {"error": "chat_unavailable", "detail": str(exc)})
        except ReplayWorkbenchChatError as exc:
            return self._json_response(400, {"error": "chat_error", "detail": str(exc)})
        except ReplayAiReviewUnavailableError as exc:
            return self._json_response(503, {"error": "ai_review_unavailable", "detail": str(exc)})
        except ValueError as exc:
            return self._json_response(400, {"error": "invalid_parameter", "detail": str(exc)})
        except json.JSONDecodeError:
            return self._json_response(400, {"error": "invalid_json", "detail": "Request body is not valid JSON."})
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Unhandled application error: %s", exc)
            return self._json_response(500, {"error": "internal_error", "detail": "Unexpected server error."})

    @staticmethod
    def _json_model_response(
        status_code: int,
        model: BaseModel | IngestionAcceptedResponse | AnalysisEnvelope | BeliefLatestEnvelope | EpisodeEvaluationEnvelope | EpisodeListEnvelope | IngestionEnvelope | DepthSnapshotAcceptedResponse | LiquidityMemoryEnvelope | LiquidityMemoryRecord | AdapterAcceptedResponse | AdapterBackfillDispatchResponse | AdapterBackfillAcknowledgeResponse | ReplayWorkbenchAcceptedResponse | ReplayWorkbenchAtasBackfillAcceptedResponse | ReplayWorkbenchBackfillProgressResponse | ReplayWorkbenchCacheEnvelope | ReplayWorkbenchInvalidationResponse | ReplayWorkbenchBuildResponse | ReplayAiReviewResponse | ReplayAiChatResponse | ReplayOperatorEntryAcceptedResponse | ReplayOperatorEntryEnvelope | ReplayManualRegionAnnotationAcceptedResponse | ReplayManualRegionAnnotationEnvelope | ReplayFootprintBarDetail | ReplayWorkbenchLiveTailResponse | ReplayWorkbenchRebuildLatestResponse | ChartCandleEnvelope | ContinuousBarsEnvelope | MirrorBarsEnvelope | ReliableIngestionResponse | IngestionErrorResponse | IngestionHealthResponse | DataQualityResponse,
    ) -> HttpResponse:
        payload = model.model_dump(mode="json")
        return MarketStructureApplication._json_response(status_code, payload)

    @staticmethod
    def _sse_response(events: list[dict[str, Any]]) -> HttpResponse:
        chunks: list[bytes] = []
        for item in events:
            event_name = item.get("event", "message")
            data = json.dumps(item.get("data", {}), ensure_ascii=True, separators=(",", ":"), default=_default_json_serializer)
            chunks.append(f"event: {event_name}\ndata: {data}\n\n".encode("utf-8"))
        content_length = sum(len(chunk) for chunk in chunks)
        return HttpResponse(
            status_code=200,
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-store",
                "Content-Length": str(content_length),
                "Connection": "close",
                "X-Accel-Buffering": "no",
            },
            stream_chunks=tuple(chunks),
        )

    @staticmethod
    def _parse_datetime_arg(value: str | None) -> datetime:
        """Parse a datetime query-string value, supporting bare ISO or space-separated."""
        if not value:
            raise TypeError("datetime value must not be None")
        normalized = _normalize_query_datetime(value)
        return datetime.fromisoformat(normalized).astimezone(UTC)

    def _parse_projection_query(self, query: dict[str, list[str]]) -> ReplayProjectionQuery:
        instrument_symbol = self._query_value(query, "instrument_symbol", "instrument")
        if instrument_symbol is None:
            raise ValueError("instrument or instrument_symbol is required.")
        window_start_raw = self._query_value(query, "window_start", "from")
        window_end_raw = self._query_value(query, "window_end", "to")
        limit_raw = self._query_value(query, "limit")
        limit = 100
        if limit_raw is not None:
            try:
                limit = max(1, min(1000, int(limit_raw)))
            except ValueError as exc:
                raise ValueError("limit must be an integer.") from exc
        return ReplayProjectionQuery(
            instrument_symbol=instrument_symbol,
            window_start=self._parse_datetime_arg(window_start_raw) if window_start_raw is not None else None,
            window_end=self._parse_datetime_arg(window_end_raw) if window_end_raw is not None else None,
            session_date=query.get("session_date", [None])[0] or query.get("date", [None])[0],
            limit=limit,
        )

    @staticmethod
    def _parse_positive_int_arg(value: str | None, *, default: int) -> int:
        if value is None or value == "":
            return default
        parsed = int(value)
        if parsed <= 0:
            raise ValueError("limit must be greater than zero")
        return parsed

    @staticmethod
    def _parse_bool_arg(value: str | None, *, default: bool) -> bool:
        if value is None or value == "":
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        raise ValueError(f"invalid boolean value: {value}")

    @staticmethod
    def _parse_csv_list(value: str | None) -> list[str] | None:
        if value is None or value.strip() == "":
            return None
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _query_value(query: dict[str, list[str]], *names: str) -> str | None:
        for name in names:
            values = query.get(name)
            if values:
                return values[0]
        return None

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
    def _text_response(status_code: int, content: str, content_type: str, headers: dict[str, str] | None = None) -> HttpResponse:
        body = content.encode("utf-8")
        merged_headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        }
        if headers:
            merged_headers.update(headers)
        return HttpResponse(
            status_code=status_code,
            body=body,
            headers=merged_headers,
        )


def _default_json_serializer(value: Any) -> str:
    if isinstance(value, datetime):
        timestamp = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return timestamp.isoformat()
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def _normalize_query_datetime(value: str) -> str:
    if "T" in value and "+" not in value and value.count(" ") == 1:
        date_part, offset_part = value.split(" ", maxsplit=1)
        if ":" in offset_part:
            return f"{date_part}+{offset_part}"
    return value
