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
    ReplayAiChatResponse,
    ReplayAiReviewNotFoundError,
    ReplayAiReviewResponse,
    ReplayAiReviewService,
    ReplayAiReviewUnavailableError,
    ReplayAiChatService,
)
from atas_market_structure.app_routes import handle_analysis_routes, handle_chat_routes, handle_options_routes
from atas_market_structure.chart_candle_service import ChartCandleService
from atas_market_structure.app_shared import NotFoundError
from atas_market_structure.config import AppConfig
from atas_market_structure.continuous_contract_service import (
    ContinuousContractService,
    ContinuousContractServiceError,
)
from atas_market_structure.depth_services import DepthMonitoringService
from atas_market_structure.ingestion_reliability_services import IngestionReliabilityService
from atas_market_structure.models import (
    AdapterBackfillAcknowledgeRequest,
    AdapterBackfillAcknowledgeResponse,
    AdapterAcceptedResponse,
    AdapterContinuousStatePayload,
    AdapterBackfillDispatchResponse,
    AdapterHistoryBarsPayload,
    AdapterHistoryFootprintPayload,
    AdapterTriggerBurstPayload,
    AnalysisEnvelope,
    ChartCandleEnvelope,
    ContinuousAdjustmentMode,
    ContinuousBarsEnvelope,
    DataQualityResponse,
    DepthSnapshotAcceptedResponse,
    DepthSnapshotPayload,
    EventSnapshotPayload,
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
from atas_market_structure.workbench_services import (
    ReplayWorkbenchChatError,
    ReplayWorkbenchChatUnavailableError,
    ReplayWorkbenchChatService,
    ReplayWorkbenchNotFoundError,
    ReplayWorkbenchService,
)


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


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
        self._replay_workbench_chat_service = ReplayWorkbenchChatService(
            repository=repository,
            replay_ai_chat_service=self._replay_ai_chat_service,
        )
        self._chart_candle_service = ChartCandleService(repository=repository)
        self._analysis_pattern = re.compile(r"^/api/v1/analyses/(?P<analysis_id>[^/]+)$")
        self._ingestion_pattern = re.compile(r"^/api/v1/ingestions/(?P<ingestion_id>[^/]+)$")
        self._logger = LOGGER

    def dispatch(self, method: str, path: str, body: bytes | None = None) -> HttpResponse:
        route = urlsplit(path)
        route_path = route.path
        query = parse_qs(route.query)
        try:
            if method == "GET" and route_path == "/health":
                return self._json_response(200, {"status": "ok", "timestamp": datetime.now(tz=UTC)})

            if method == "GET" and route_path == "/health/ingestion":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                result = self._ingestion_reliability_service.get_ingestion_health(
                    instrument_symbol=instrument_symbol,
                )
                return self._json_model_response(result.status_code, result.body)

            if method == "GET" and route_path == "/health/data-quality":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                result = self._ingestion_reliability_service.get_data_quality(
                    instrument_symbol=instrument_symbol,
                )
                return self._json_model_response(result.status_code, result.body)

            if method == "GET" and route_path in {"/workbench/replay", "/static/replay_workbench.html"}:
                html = (STATIC_DIR / "replay_workbench.html").read_text(encoding="utf-8")
                return self._text_response(
                    200,
                    html,
                    "text/html; charset=utf-8",
                    headers={
                        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                        "Pragma": "no-cache",
                    },
                )

            if method == "GET" and route_path.startswith("/static/"):
                rel = route_path.removeprefix("/static/")
                candidate = (STATIC_DIR / rel).resolve()
                if STATIC_DIR not in candidate.parents and candidate != STATIC_DIR:
                    raise NotFoundError("invalid static path")
                if not candidate.exists() or not candidate.is_file():
                    raise NotFoundError(f"static resource '{rel}' not found")
                content = candidate.read_bytes()
                content_type = "application/octet-stream"
                suffix = candidate.suffix.lower()
                if suffix in {".html", ".htm"}:
                    content_type = "text/html; charset=utf-8"
                elif suffix == ".js":
                    content_type = "application/javascript; charset=utf-8"
                elif suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif suffix == ".json":
                    content_type = "application/json; charset=utf-8"
                elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
                    content_type = f"image/{suffix.lstrip('.')}"
                return HttpResponse(
                    status_code=200,
                    body=content,
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(len(content)),
                        "Cache-Control": "no-store",
                    },
                )

            if method == "POST" and route_path == "/api/v1/ingestions/market-structure":
                payload = MarketStructurePayload.model_validate_json(body or b"{}")
                response = self._orchestrator.ingest_market_structure(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/ingest/market-structure":
                result = self._ingestion_reliability_service.ingest_market_structure(body or b"")
                return self._json_model_response(result.status_code, result.body)

            if method == "POST" and route_path == "/api/v1/ingestions/event-snapshot":
                payload = EventSnapshotPayload.model_validate_json(body or b"{}")
                response = self._orchestrator.ingest_event_snapshot(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/ingest/event-snapshot":
                result = self._ingestion_reliability_service.ingest_event_snapshot(body or b"")
                return self._json_model_response(result.status_code, result.body)

            if method == "POST" and route_path == "/api/v1/ingestions/depth-snapshot":
                payload = DepthSnapshotPayload.model_validate_json(body or b"{}")
                response = self._depth_monitoring_service.ingest_depth_snapshot(payload)
                return self._json_model_response(201, response)

            if method == "POST" and route_path == "/api/v1/ingest/process-context":
                result = self._ingestion_reliability_service.ingest_process_context(body or b"")
                return self._json_model_response(result.status_code, result.body)

            if method == "POST" and route_path == "/api/v1/ingest/depth-snapshot":
                result = self._ingestion_reliability_service.ingest_depth_snapshot(body or b"")
                return self._json_model_response(result.status_code, result.body)

            if method == "POST" and route_path == "/api/v1/ingest/adapter-payload":
                result = self._ingestion_reliability_service.ingest_adapter_payload(body or b"")
                return self._json_model_response(result.status_code, result.body)

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

            if method == "GET" and route_path == "/api/v1/adapter/backfill-command":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                contract_symbol = query.get("contract_symbol", [None])[0]
                root_symbol = query.get("root_symbol", [None])[0]
                if instrument_symbol is None:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "instrument_symbol is required."},
                    )
                chart_instance_id = query.get("chart_instance_id", [None])[0]
                response = self._replay_workbench_service.poll_atas_backfill(
                    instrument_symbol=instrument_symbol,
                    chart_instance_id=chart_instance_id,
                    contract_symbol=contract_symbol,
                    root_symbol=root_symbol,
                )
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/adapter/backfill-ack":
                payload = AdapterBackfillAcknowledgeRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.acknowledge_atas_backfill(payload)
                return self._json_model_response(200, response)

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
                response = self._replay_workbench_service.get_cache_record(cache_key, allow_fuzzy=True)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-cache/invalidate":
                payload = ReplayWorkbenchInvalidationRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.invalidate_cache_record(payload)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/replay-cache/rebuild-latest":
                payload = ReplayWorkbenchRebuildLatestRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.rebuild_cache_from_latest_sync(payload)
                return self._json_model_response(200, response)

            if method == "POST" and route_path == "/api/v1/workbench/atas-backfill-requests":
                payload = ReplayWorkbenchAtasBackfillRequest.model_validate_json(body or b"{}")
                response = self._replay_workbench_service.request_atas_backfill(payload)
                return self._json_model_response(201, response)

            if method == "GET" and route_path == "/api/v1/workbench/live-status":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                if instrument_symbol is None:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "instrument_symbol is required."},
                    )
                replay_ingestion_id = query.get("replay_ingestion_id", [None])[0]
                response = self._replay_workbench_service.get_live_status(
                    instrument_symbol=instrument_symbol,
                    replay_ingestion_id=replay_ingestion_id,
                )
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/live-tail":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                display_timeframe = query.get("display_timeframe", [None])[0]
                if instrument_symbol is None or display_timeframe is None:
                    return self._json_response(
                        400,
                        {
                            "error": "missing_query_parameter",
                            "detail": "instrument_symbol and display_timeframe are required.",
                        },
                    )
                chart_instance_id = query.get("chart_instance_id", [None])[0]
                lookback_bars_raw = query.get("lookback_bars", [None])[0]
                try:
                    timeframe = Timeframe(display_timeframe)
                except ValueError:
                    return self._json_response(
                        400,
                        {"error": "invalid_query_parameter", "detail": "display_timeframe is invalid."},
                    )
                try:
                    lookback_bars = int(lookback_bars_raw) if lookback_bars_raw is not None else 4
                except ValueError:
                    return self._json_response(
                        400,
                        {"error": "invalid_query_parameter", "detail": "lookback_bars must be an integer."},
                    )
                response = self._replay_workbench_service.get_live_tail(
                    instrument_symbol=instrument_symbol,
                    display_timeframe=timeframe,
                    chart_instance_id=chart_instance_id,
                    lookback_bars=max(1, min(500, lookback_bars)),
                )
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/belief-state-timeline":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_belief_state_timeline(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/event-episodes":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_event_episode_reviews(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/episode-evaluations":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_episode_evaluations(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/tuning-recommendations":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_tuning_reviews(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/profile-engine":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_profile_engine_metadata(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/health-status":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.get_health_status(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/review/projection":
                projection_query = self._parse_projection_query(query)
                response = self._workbench_projection_service.build_projection(projection_query)
                return self._json_model_response(200, response)

            if method == "GET" and route_path == "/api/v1/workbench/instruments":
                try:
                    ingestions = self._repository.list_ingestions(limit=1000)
                    symbols = sorted(set(i.instrument_symbol for i in ingestions))
                    return self._json_response(200, {"instruments": symbols})
                except Exception as e:
                    return self._json_response(500, {"error": str(e)})

            # ── Chart Candles ────────────────────────────────────────────────
            # GET /api/v1/workbench/chart-candles?symbol=NQ&timeframe=1m&window_start=...&window_end=...
            if method == "GET" and route_path == "/api/v1/workbench/chart-candles":
                symbol = query.get("symbol", [None])[0]
                tf_raw = query.get("timeframe", [None])[0]
                ws_raw = query.get("window_start", [None])[0]
                we_raw = query.get("window_end", [None])[0]
                if not symbol or not tf_raw or not ws_raw or not we_raw:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "symbol, timeframe, window_start, window_end are required."},
                    )
                try:
                    tf = Timeframe(tf_raw)
                    ws = self._parse_datetime_arg(ws_raw)
                    we = self._parse_datetime_arg(we_raw)
                    limit = int(query.get("limit", ["20000"])[0])
                except (ValueError, TypeError) as e:
                    return self._json_response(400, {"error": "invalid_parameter", "detail": str(e)})
                candles = self._chart_candle_service.get_candles(symbol, tf, ws, we, limit=limit)
                return self._json_model_response(
                    200,
                    ChartCandleEnvelope(
                        symbol=symbol,
                        timeframe=tf,
                        window_start=ws,
                        window_end=we,
                        count=len(candles),
                        candles=candles,
                    ),
                )

            # POST /api/v1/workbench/chart-candles/backfill
            if method == "POST" and route_path == "/api/v1/workbench/chart-candles/backfill":
                from atas_market_structure.models._replay import ChartCandleBackfillRequest, ChartCandleBackfillEnvelope
                req = ChartCandleBackfillRequest.model_validate_json(body or b"{}")
                started = datetime.now(tz=UTC)
                result = self._chart_candle_service.backfill_from_ingestions(req.symbol, req.to_timeframes)
                total_written = sum(result.values())
                env = ChartCandleBackfillEnvelope(
                    symbol=req.symbol,
                    backfill_started=started,
                    bars_aggregated=0,
                    candles_written=total_written,
                )
                return self._json_model_response(200, env)

            # ── Chart Mirror (raw contract bars) ───────────────────────────────
            # GET /api/v1/chart/mirror-bars
            # Returns raw contract bars without continuous/roll adjustments.
            if method == "GET" and route_path == "/api/v1/chart/mirror-bars":
                chart_instance_id = query.get("chart_instance_id", [None])[0]
                contract_symbol = query.get("contract_symbol", [None])[0]
                tf_raw = query.get("timeframe", [None])[0]
                ws_raw = query.get("window_start_utc", [None])[0]
                we_raw = query.get("window_end_utc", [None])[0]
                if not contract_symbol or not tf_raw or not ws_raw or not we_raw:
                    return self._json_response(
                        400,
                        {
                            "error": "missing_query_parameter",
                            "detail": "contract_symbol, timeframe, window_start_utc, window_end_utc are required.",
                        },
                    )
                try:
                    tf = Timeframe(tf_raw)
                    ws = self._parse_datetime_arg(ws_raw)
                    we = self._parse_datetime_arg(we_raw)
                    limit = self._parse_positive_int_arg(query.get("limit", [None])[0], default=5000)
                except (ValueError, TypeError) as e:
                    return self._json_response(400, {"error": "invalid_parameter", "detail": str(e)})
                bars = self._repository.list_atas_chart_bars_raw(
                    chart_instance_id=chart_instance_id,
                    contract_symbol=contract_symbol,
                    timeframe=tf.value,
                    window_start=ws,
                    window_end=we,
                    limit=limit,
                )
                return self._json_model_response(
                    200,
                    MirrorBarsEnvelope(
                        chart_instance_id=chart_instance_id,
                        contract_symbol=contract_symbol,
                        timeframe=tf,
                        window_start=ws,
                        window_end=we,
                        count=len(bars),
                        bars=bars,
                    ),
                )

            # ── Chart Continuous (roll-adjusted bars) ──────────────────────────
            # GET /api/v1/chart/continuous-bars
            # Returns continuous-series bars with roll adjustments applied.
            if method == "GET" and route_path == "/api/v1/chart/continuous-bars":
                root_symbol = query.get("root_symbol", [None])[0]
                tf_raw = query.get("timeframe", [None])[0]
                roll_mode_raw = query.get("roll_mode", [None])[0]
                ws_raw = query.get("window_start_utc", [None])[0]
                we_raw = query.get("window_end_utc", [None])[0]
                if not root_symbol or not tf_raw or not roll_mode_raw or not ws_raw or not we_raw:
                    return self._json_response(
                        400,
                        {
                            "error": "missing_query_parameter",
                            "detail": "root_symbol, timeframe, roll_mode, window_start_utc, window_end_utc are required.",
                        },
                    )
                try:
                    tf = Timeframe(tf_raw)
                    roll_mode = RollMode(roll_mode_raw)
                    adjustment_mode = ContinuousAdjustmentMode(
                        query.get("adjustment_mode", [ContinuousAdjustmentMode.NONE.value])[0]
                    )
                    ws = self._parse_datetime_arg(ws_raw)
                    we = self._parse_datetime_arg(we_raw)
                    limit = self._parse_positive_int_arg(query.get("limit", [None])[0], default=5000)
                    include_contract_markers = self._parse_bool_arg(
                        query.get("include_contract_markers", [None])[0],
                        default=False,
                    )
                except (ValueError, TypeError) as e:
                    return self._json_response(400, {"error": "invalid_parameter", "detail": str(e)})
                manual_sequence = self._parse_csv_list(query.get("contract_sequence", [None])[0])
                try:
                    envelope = self._continuous_contract_service.query_continuous_bars(
                        root_symbol=root_symbol,
                        timeframe=tf,
                        roll_mode=roll_mode,
                        window_start=ws,
                        window_end=we,
                        limit=limit,
                        include_contract_markers=include_contract_markers,
                        adjustment_mode=adjustment_mode,
                        manual_sequence=manual_sequence,
                    )
                except ContinuousContractServiceError as exc:
                    return self._json_response(
                        400,
                        {"error": "continuous_query_invalid", "detail": str(exc)},
                    )
                return self._json_model_response(200, envelope)

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

            chat_response = handle_chat_routes(self, method, route_path, query, body)
            if chat_response is not None:
                return chat_response

            options_response = handle_options_routes(self, method, route_path, query, body)
            if options_response is not None:
                return options_response

            analysis_response = handle_analysis_routes(self, method, route_path, query, body)
            if analysis_response is not None:
                return analysis_response

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
            body_preview = ""
            if body:
                try:
                    body_preview = body.decode("utf-8", errors="replace")[:4000]
                except Exception:  # pragma: no cover
                    body_preview = "<unable_to_decode_body>"
            self._logger.warning(
                "Validation error for %s %s: %s | body=%s",
                method,
                route_path,
                exc.json(),
                body_preview,
            )
            return self._json_response(422, {"error": "validation_error", "detail": json.loads(exc.json())})
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
        model: BaseModel | IngestionAcceptedResponse | AnalysisEnvelope | IngestionEnvelope | DepthSnapshotAcceptedResponse | LiquidityMemoryEnvelope | LiquidityMemoryRecord | AdapterAcceptedResponse | AdapterBackfillDispatchResponse | AdapterBackfillAcknowledgeResponse | ReplayWorkbenchAcceptedResponse | ReplayWorkbenchAtasBackfillAcceptedResponse | ReplayWorkbenchCacheEnvelope | ReplayWorkbenchInvalidationResponse | ReplayWorkbenchBuildResponse | ReplayAiReviewResponse | ReplayAiChatResponse | ReplayOperatorEntryAcceptedResponse | ReplayOperatorEntryEnvelope | ReplayManualRegionAnnotationAcceptedResponse | ReplayManualRegionAnnotationEnvelope | ReplayFootprintBarDetail | ReplayWorkbenchLiveTailResponse | ReplayWorkbenchRebuildLatestResponse | ChartCandleEnvelope | ContinuousBarsEnvelope | MirrorBarsEnvelope | ReliableIngestionResponse | IngestionErrorResponse | IngestionHealthResponse | DataQualityResponse,
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
        instrument_symbol = query.get("instrument_symbol", [None])[0]
        if instrument_symbol is None:
            raise ValueError("instrument_symbol is required.")
        window_start_raw = query.get("window_start", [None])[0] or query.get("from", [None])[0]
        window_end_raw = query.get("window_end", [None])[0] or query.get("to", [None])[0]
        limit_raw = query.get("limit", [None])[0]
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
