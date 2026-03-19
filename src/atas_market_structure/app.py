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
from atas_market_structure.analysis_orchestration_services import (
    DeepRegionAnalysisService,
    FullMarketAnalysisService,
    LightweightMonitorService,
)
from atas_market_structure.focus_region_review_services import (
    FocusRegionReviewService,
    ScreenshotAnalysisInput,
)
from atas_market_structure.strategy_selection_engine import StrategySelectionEngine
from atas_market_structure.ai_review_services import (
    ReplayAiChatService,
    ReplayAiReviewNotFoundError,
    ReplayAiReviewService,
    ReplayAiReviewUnavailableError,
)
from atas_market_structure.depth_services import DepthMonitoringService
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
    ReplayWorkbenchAtasBackfillAcceptedResponse,
    ReplayWorkbenchAtasBackfillRequest,
    ReplayWorkbenchBuildRequest,
    ReplayWorkbenchBuildResponse,
    ReplayWorkbenchCacheEnvelope,
    ReplayWorkbenchInvalidationRequest,
    ReplayWorkbenchInvalidationResponse,
    ReplayWorkbenchLiveTailResponse,
    ReplayWorkbenchRebuildLatestRequest,
    ReplayWorkbenchRebuildLatestResponse,
    ReplayWorkbenchSnapshotPayload,
    Timeframe,
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

            if method == "GET" and route_path in {"/workbench/replay", "/static/replay_workbench.html"}:
                html = (STATIC_DIR / "replay_workbench.html").read_text(encoding="utf-8")
                # Avoid browser caching during rapid UI iterations (timeframe switching, etc.).
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
                # Minimal static file handler (helps when operators bookmark /static/...)
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

            if method == "GET" and route_path == "/api/v1/adapter/backfill-command":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                if instrument_symbol is None:
                    return self._json_response(
                        400,
                        {"error": "missing_query_parameter", "detail": "instrument_symbol is required."},
                    )
                chart_instance_id = query.get("chart_instance_id", [None])[0]
                response = self._replay_workbench_service.poll_atas_backfill(
                    instrument_symbol=instrument_symbol,
                    chart_instance_id=chart_instance_id,
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
                    # UI may request larger tails (e.g. 50 bars). Keep a reasonable cap to avoid accidental abuse.
                    lookback_bars=max(1, min(500, lookback_bars)),
                )
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

            # --- Analysis Pipeline endpoints (new) ---

            if method == "POST" and route_path == "/api/v1/analysis/lightweight-monitor":
                req = json.loads(body or b"{}")
                snapshot = self._resolve_snapshot_for_analysis(req)
                entries = self._resolve_entries_for_analysis(req, snapshot)
                engine = StrategySelectionEngine()
                svc = LightweightMonitorService(strategy_engine=engine)
                result = svc.run(snapshot, entries, previous_focus_region_count=req.get("previous_focus_region_count", 0))
                return self._json_response(200, result.to_dict())

            if method == "POST" and route_path == "/api/v1/analysis/full-market":
                req = json.loads(body or b"{}")
                snapshot = self._resolve_snapshot_for_analysis(req)
                entries = self._resolve_entries_for_analysis(req, snapshot)
                engine = StrategySelectionEngine()
                svc = FullMarketAnalysisService(strategy_engine=engine)
                result = svc.analyze(snapshot, entries)
                return self._json_response(200, result.to_dict())

            if method == "POST" and route_path == "/api/v1/analysis/deep-region":
                req = json.loads(body or b"{}")
                snapshot = self._resolve_snapshot_for_analysis(req)
                entries = self._resolve_entries_for_analysis(req, snapshot)
                region_data = req.get("region")
                if region_data is None:
                    return self._json_response(400, {"error": "missing_field", "detail": "region is required."})
                from atas_market_structure.models import ReplayManualRegionAnnotationRecord
                region = ReplayManualRegionAnnotationRecord(**region_data)
                engine = StrategySelectionEngine()
                svc = DeepRegionAnalysisService(strategy_engine=engine)
                source_type = req.get("source_type", "manual_marked")
                result = svc.analyze_region(snapshot, region, entries, source_type=source_type)
                return self._json_response(200, result.to_dict())

            if method == "POST" and route_path == "/api/v1/analysis/store-review":
                req = json.loads(body or b"{}")
                snapshot = self._resolve_snapshot_for_analysis(req)
                entries = self._resolve_entries_for_analysis(req, snapshot)
                region_data = req.get("region")
                if region_data is None:
                    return self._json_response(400, {"error": "missing_field", "detail": "region is required."})
                from atas_market_structure.models import ReplayManualRegionAnnotationRecord
                region = ReplayManualRegionAnnotationRecord(**region_data)
                engine = StrategySelectionEngine()
                deep_svc = DeepRegionAnalysisService(strategy_engine=engine)
                deep_result = deep_svc.analyze_region(snapshot, region, entries, source_type=req.get("source_type", "manual_marked"))
                review_svc = FocusRegionReviewService(repository=self._repository)
                record = review_svc.store_review(
                    deep_result,
                    replay_ingestion_id=req.get("replay_ingestion_id", ""),
                    market_context=req.get("market_context"),
                    reviewer_notes=req.get("reviewer_notes", ""),
                )
                return self._json_response(201, record.to_dict())

            if method == "POST" and route_path == "/api/v1/analysis/confirm-review":
                req = json.loads(body or b"{}")
                review_id = req.get("review_id")
                if not review_id:
                    return self._json_response(400, {"error": "missing_field", "detail": "review_id is required."})
                review_svc = FocusRegionReviewService(repository=self._repository)
                record = review_svc.confirm_review(review_id, reviewer_notes=req.get("reviewer_notes", ""))
                if record is None:
                    return self._json_response(404, {"error": "not_found", "detail": f"review '{review_id}' not found"})
                return self._json_response(200, record.to_dict())

            if method == "POST" and route_path == "/api/v1/analysis/reject-review":
                req = json.loads(body or b"{}")
                review_id = req.get("review_id")
                if not review_id:
                    return self._json_response(400, {"error": "missing_field", "detail": "review_id is required."})
                review_svc = FocusRegionReviewService(repository=self._repository)
                record = review_svc.reject_review(review_id, reviewer_notes=req.get("reviewer_notes", ""))
                if record is None:
                    return self._json_response(404, {"error": "not_found", "detail": f"review '{review_id}' not found"})
                return self._json_response(200, record.to_dict())

            if method == "GET" and route_path == "/api/v1/analysis/reviews":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                status_filter = query.get("status", [None])[0]
                review_svc = FocusRegionReviewService(repository=self._repository)
                records = review_svc.list_reviews(instrument_symbol=instrument_symbol, status_filter=status_filter)
                return self._json_response(200, {"reviews": [r.to_dict() for r in records]})

            if method == "GET" and route_path == "/api/v1/analysis/review-feedback":
                instrument_symbol = query.get("instrument_symbol", [None])[0]
                if not instrument_symbol:
                    return self._json_response(400, {"error": "missing_query_parameter", "detail": "instrument_symbol is required."})
                review_svc = FocusRegionReviewService(repository=self._repository)
                feedback = review_svc.get_feedback_for_briefing(instrument_symbol)
                return self._json_response(200, {"feedback": feedback})

            if method == "POST" and route_path == "/api/v1/analysis/screenshot-input":
                req = json.loads(body or b"{}")
                from uuid import uuid4 as _uuid4
                inp = ScreenshotAnalysisInput(
                    input_id=req.get("input_id", f"si-{_uuid4().hex[:8]}"),
                    source_type=req.get("source_type", "atas_screenshot"),
                    instrument_symbol=req.get("instrument_symbol"),
                    timeframe=req.get("timeframe"),
                    session=req.get("session"),
                    time_range_start=datetime.fromisoformat(req["time_range_start"]) if req.get("time_range_start") else None,
                    time_range_end=datetime.fromisoformat(req["time_range_end"]) if req.get("time_range_end") else None,
                    price_range_low=req.get("price_range_low"),
                    price_range_high=req.get("price_range_high"),
                    image_url=req.get("image_url"),
                    observed_visual_cues=req.get("observed_visual_cues", []),
                    chart_id=req.get("chart_id"),
                    snapshot_id=req.get("snapshot_id"),
                    pane_type=req.get("pane_type"),
                    selected_at=datetime.fromisoformat(req["selected_at"]) if req.get("selected_at") else datetime.now(tz=UTC),
                    selected_by=req.get("selected_by", "operator"),
                    linked_replay_ingestion_id=req.get("linked_replay_ingestion_id"),
                    notes=req.get("notes", ""),
                )
                review_svc = FocusRegionReviewService(repository=self._repository)
                ingestion_id = review_svc.store_screenshot_input(inp)
                return self._json_response(201, {"ingestion_id": ingestion_id, "input_id": inp.input_id})

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

    def _resolve_snapshot_for_analysis(self, req: dict[str, Any]) -> ReplayWorkbenchSnapshotPayload:
        """Resolve a snapshot for analysis endpoints. Accepts either inline snapshot or cache_key."""
        if "snapshot" in req:
            return ReplayWorkbenchSnapshotPayload.model_validate(req["snapshot"])
        cache_key = req.get("cache_key")
        if cache_key:
            cache_record = self._replay_workbench_service.get_cache_record(cache_key)
            return ReplayWorkbenchSnapshotPayload.model_validate_json(
                json.dumps(cache_record.snapshot_payload).encode()
            )
        raise NotFoundError("Either 'snapshot' or 'cache_key' must be provided.")

    def _resolve_entries_for_analysis(
        self, req: dict[str, Any], snapshot: ReplayWorkbenchSnapshotPayload,
    ) -> list:
        """Resolve operator entries for analysis. Uses inline entries or fetches from repository."""
        if "entries" in req:
            from atas_market_structure.models import ReplayOperatorEntryRecord
            return [ReplayOperatorEntryRecord(**e) for e in req["entries"]]
        replay_ingestion_id = req.get("replay_ingestion_id")
        if replay_ingestion_id:
            envelope = self._replay_workbench_service.list_operator_entries(replay_ingestion_id)
            return envelope.entries
        return []

    @staticmethod
    def _json_model_response(
        status_code: int,
        model: BaseModel | IngestionAcceptedResponse | AnalysisEnvelope | IngestionEnvelope | DepthSnapshotAcceptedResponse | LiquidityMemoryEnvelope | LiquidityMemoryRecord | AdapterAcceptedResponse | AdapterBackfillDispatchResponse | AdapterBackfillAcknowledgeResponse | ReplayWorkbenchAcceptedResponse | ReplayWorkbenchAtasBackfillAcceptedResponse | ReplayWorkbenchCacheEnvelope | ReplayWorkbenchInvalidationResponse | ReplayWorkbenchBuildResponse | ReplayAiReviewResponse | ReplayAiChatResponse | ReplayOperatorEntryAcceptedResponse | ReplayOperatorEntryEnvelope | ReplayManualRegionAnnotationAcceptedResponse | ReplayManualRegionAnnotationEnvelope | ReplayFootprintBarDetail,
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
    """Recover timezone offsets where '+' was decoded into a space by query parsing."""
    if "T" in value and "+" not in value and value.count(" ") == 1:
        date_part, offset_part = value.split(" ", maxsplit=1)
        if ":" in offset_part:
            return f"{date_part}+{offset_part}"
    return value
